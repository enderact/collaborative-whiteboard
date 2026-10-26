"""Stroke persistence, ordering, and the three deletion semantics.

Ordering comes from a Redis counter rather than a timestamp. Client clocks drift
and ObjectId only carries one-second precision, so neither can order strokes that
arrive milliseconds apart from different machines. `INCR` is atomic across every
backend instance and gives a room a single authoritative sequence.
"""

from bson import ObjectId
from pymongo import DESCENDING, ReturnDocument

from app.db import STROKES, db, redis
from app.models import StrokeCreate, StrokeStyleUpdate
from app.util import bbox_of_points, now


def seq_key(room_id) -> str:
    return f"room:{room_id}:seq"


async def next_seq(room_id) -> int:
    return int(await redis().incr(seq_key(room_id)))


async def sync_seq_floor(room_id, value: int) -> None:
    """Keep the Redis counter ahead of what is already stored.

    Redis is a cache here, not the system of record. If it restarts the counter
    is gone, so on room load we push it back up to the highest persisted seq.
    """
    current = await redis().get(seq_key(room_id))
    if current is None or int(current) < value:
        await redis().set(seq_key(room_id), value)


# ---------------------------------------------------------------- CREATE
async def create_stroke(room_id, user_id: str, user_name: str, payload: StrokeCreate) -> dict:
    points = [p.model_dump() for p in payload.points] if payload.points else None

    doc: dict = {
        "roomId": room_id,
        "seq": await next_seq(room_id),
        "userId": user_id,
        "userName": user_name,
        "tool": payload.tool,
        "style": payload.style.model_dump(),
        "active": True,
        "undoneAt": None,
        "undoneBy": None,
        "clientMsgId": payload.clientMsgId,
        "createdAt": now(),
        "updatedAt": now(),
    }

    # Only the fields that a given tool actually uses are stored. A rectangle
    # document has no `points` key at all rather than a null column.
    if points:
        doc["points"] = points
        doc["pointCount"] = len(points)
        doc["bbox"] = bbox_of_points(points)
    if payload.geometry:
        g = payload.geometry.model_dump()
        doc["geometry"] = g
        doc["bbox"] = {
            "minX": min(g["x"], g["x"] + g["w"]),
            "minY": min(g["y"], g["y"] + g["h"]),
            "maxX": max(g["x"], g["x"] + g["w"]),
            "maxY": max(g["y"], g["y"] + g["h"]),
        }
    if payload.text is not None:
        doc["text"] = payload.text
        doc["font"] = payload.font or "16px Inter, sans-serif"

    res = await db()[STROKES].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def insert_many(docs: list[dict]) -> int:
    res = await db()[STROKES].insert_many(docs, ordered=False)
    return len(res.inserted_ids)


# ------------------------------------------------------------------ READ
async def list_strokes(
    room_id, after_seq: int = 0, include_inactive: bool = False, limit: int = 200_000
) -> list[dict]:
    query: dict = {"roomId": room_id, "seq": {"$gt": after_seq}}
    if not include_inactive:
        query["active"] = True
    cursor = db()[STROKES].find(query).sort("seq", 1).limit(limit)
    return [doc async for doc in cursor]


async def list_strokes_capped(room_id, after_seq: int, cap: int) -> tuple[list[dict], bool, int]:
    """Replay strokes after `after_seq`, but never more than `cap` of them.

    A room seeded with 48,000 strokes serialises to roughly 70 MB of JSON, which
    would stall the browser on join. When a snapshot exists this cap is never
    reached, because only the tail after the snapshot is replayed. Without one,
    the newest `cap` strokes are sent and the client is told the history was
    truncated so it can offer to rasterise a snapshot.
    """
    query = {"roomId": room_id, "seq": {"$gt": after_seq}, "active": True}
    total = await db()[STROKES].count_documents(query)

    if total <= cap:
        cursor = db()[STROKES].find(query).sort("seq", 1)
        return [doc async for doc in cursor], False, total

    cursor = db()[STROKES].find(query).sort("seq", DESCENDING).limit(cap)
    newest = [doc async for doc in cursor]
    newest.reverse()
    return newest, True, total


async def get_stroke(stroke_id: str) -> dict | None:
    return await db()[STROKES].find_one({"_id": ObjectId(stroke_id)})


async def max_seq(room_id) -> int:
    cursor = db()[STROKES].find({"roomId": room_id}, {"seq": 1}).sort("seq", DESCENDING).limit(1)
    docs = [d async for d in cursor]
    return docs[0]["seq"] if docs else 0


async def count_strokes(room_id, active_only: bool = True) -> int:
    query: dict = {"roomId": room_id}
    if active_only:
        query["active"] = True
    return await db()[STROKES].count_documents(query)


# ---------------------------------------------------------------- UPDATE
async def restyle_stroke(stroke_id: str, patch: StrokeStyleUpdate) -> dict | None:
    """A true in-place update: recolour or resize a stroke already on the canvas."""
    changes = {
        f"style.{field}": value
        for field, value in patch.model_dump(exclude_none=True).items()
    }
    if not changes:
        return await get_stroke(stroke_id)
    changes["updatedAt"] = now()
    return await db()[STROKES].find_one_and_update(
        {"_id": ObjectId(stroke_id)},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )


async def move_stroke(stroke_id: str, dx: float, dy: float) -> dict | None:
    """Translate a shape by mutating nested geometry fields in place."""
    return await db()[STROKES].find_one_and_update(
        {"_id": ObjectId(stroke_id), "geometry": {"$exists": True}},
        {
            "$inc": {"geometry.x": dx, "geometry.y": dy},
            "$set": {"updatedAt": now()},
        },
        return_document=ReturnDocument.AFTER,
    )


# ------------------------------------------------- SOFT DELETE (undo / redo)
async def undo_last(room_id, user_id: str) -> dict | None:
    """Claim this user's newest active stroke and flag it inactive.

    Scoping by userId matters for correctness, not politeness: a room-wide "undo
    the last stroke" lets one user erase another's work. The single atomic
    findOneAndUpdate also means two simultaneous undos cannot claim the same
    document, because the second one no longer matches `active: True`.
    """
    return await db()[STROKES].find_one_and_update(
        {"roomId": room_id, "userId": user_id, "active": True},
        {"$set": {"active": False, "undoneAt": now(), "undoneBy": user_id}},
        sort=[("seq", DESCENDING)],
        return_document=ReturnDocument.AFTER,
    )


async def redo_last(room_id, user_id: str) -> dict | None:
    """Reactivate the most recently undone stroke for this user."""
    return await db()[STROKES].find_one_and_update(
        {"roomId": room_id, "userId": user_id, "active": False, "undoneAt": {"$ne": None}},
        {"$set": {"active": True, "undoneAt": None, "undoneBy": None}},
        sort=[("undoneAt", DESCENDING)],
        return_document=ReturnDocument.AFTER,
    )


# ----------------------------------------------------------- HARD DELETE
async def hard_delete_stroke(stroke_id: str) -> bool:
    res = await db()[STROKES].delete_one({"_id": ObjectId(stroke_id)})
    return res.deleted_count == 1


async def clear_room(room_id) -> int:
    res = await db()[STROKES].delete_many({"roomId": room_id})
    await redis().delete(seq_key(room_id))
    return res.deleted_count


async def purge_undone(room_id) -> int:
    """Compaction step: permanently drop strokes that were undone and never redone.

    This is what makes the soft-delete flag a cache-invalidation decision rather
    than a leak, and it is the contrast the design document draws between soft
    and hard deletion.
    """
    res = await db()[STROKES].delete_many({"roomId": room_id, "active": False})
    return res.deleted_count
