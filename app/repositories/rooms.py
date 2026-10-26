"""Room CRUD.

Rooms hold their participant list as an embedded array while strokes are a
separate referenced collection. That split is deliberate: participants are few,
bounded, and always read with the room, whereas strokes are unbounded and would
blow past the 16 MB document limit if embedded.
"""

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import ROOMS, SNAPSHOTS, STROKES, db
from app.models import RoomCreate, RoomUpdate
from app.util import now, room_code


# ---------------------------------------------------------------- CREATE
async def create_room(payload: RoomCreate) -> dict:
    ts = now()
    for _ in range(5):  # retry on the astronomically unlikely code collision
        doc = {
            "code": room_code(),
            "name": payload.name,
            "background": payload.background,
            "settings": {"gridVisible": payload.gridVisible, "width": 1920, "height": 1080},
            "participants": [],
            "strokeCount": 0,
            "createdBy": payload.createdBy,
            "createdAt": ts,
            "updatedAt": ts,
            "lastActivityAt": ts,
            "isArchived": False,
        }
        try:
            res = await db()[ROOMS].insert_one(doc)
        except DuplicateKeyError:
            continue
        doc["_id"] = res.inserted_id
        return doc
    raise RuntimeError("could not allocate a unique room code")


# ------------------------------------------------------------------ READ
async def get_room_by_code(code: str) -> dict | None:
    return await db()[ROOMS].find_one({"code": code.upper()})


async def get_room_by_id(room_id) -> dict | None:
    return await db()[ROOMS].find_one({"_id": room_id})


async def list_rooms(limit: int = 50, include_archived: bool = False) -> list[dict]:
    query = {} if include_archived else {"isArchived": False}
    cursor = db()[ROOMS].find(query).sort("lastActivityAt", -1).limit(limit)
    return [doc async for doc in cursor]


# ---------------------------------------------------------------- UPDATE
async def update_room(code: str, payload: RoomUpdate) -> dict | None:
    changes: dict = {}
    if payload.name is not None:
        changes["name"] = payload.name
    if payload.background is not None:
        changes["background"] = payload.background
    if payload.gridVisible is not None:
        changes["settings.gridVisible"] = payload.gridVisible
    if payload.isArchived is not None:
        changes["isArchived"] = payload.isArchived
    if not changes:
        return await get_room_by_code(code)

    changes["updatedAt"] = now()
    return await db()[ROOMS].find_one_and_update(
        {"code": code.upper()},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )


async def upsert_participant(code: str, user_id: str, user_name: str, color: str) -> dict | None:
    """Add or refresh a participant inside the embedded array.

    Two writes because a positional update cannot also insert: first try to
    refresh an existing entry, and only append when nothing matched.
    """
    ts = now()
    updated = await db()[ROOMS].find_one_and_update(
        {"code": code.upper(), "participants.userId": user_id},
        {
            "$set": {
                "participants.$.lastSeenAt": ts,
                "participants.$.userName": user_name,
                "lastActivityAt": ts,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return updated

    return await db()[ROOMS].find_one_and_update(
        {"code": code.upper()},
        {
            "$push": {
                "participants": {
                    "userId": user_id,
                    "userName": user_name,
                    "color": color,
                    "lastSeenAt": ts,
                }
            },
            "$set": {"lastActivityAt": ts},
        },
        return_document=ReturnDocument.AFTER,
    )


async def remove_participant(code: str, user_id: str) -> None:
    await db()[ROOMS].update_one(
        {"code": code.upper()},
        {"$pull": {"participants": {"userId": user_id}}, "$set": {"lastActivityAt": now()}},
    )


async def touch_room(room_id, stroke_delta: int = 0) -> None:
    update: dict = {"$set": {"lastActivityAt": now()}}
    if stroke_delta:
        update["$inc"] = {"strokeCount": stroke_delta}
    await db()[ROOMS].update_one({"_id": room_id}, update)


# ---------------------------------------------------------------- DELETE
async def delete_room(code: str) -> dict:
    """Hard delete with cascade.

    MongoDB has no foreign keys, so the cascade is the application's job. This is
    the clearest place in the project where a document store pushes referential
    integrity up into code, and it is worth saying so during the review.
    """
    room = await get_room_by_code(code)
    if not room:
        return {"deleted": False}

    strokes = await db()[STROKES].delete_many({"roomId": room["_id"]})
    snapshots = await db()[SNAPSHOTS].delete_many({"roomId": room["_id"]})
    await db()[ROOMS].delete_one({"_id": room["_id"]})
    return {
        "deleted": True,
        "roomsDeleted": 1,
        "strokesDeleted": strokes.deleted_count,
        "snapshotsDeleted": snapshots.deleted_count,
    }
