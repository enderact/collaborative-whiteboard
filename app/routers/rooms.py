"""Room and stroke REST surface.

Every one of the four CRUD verbs is reachable from here, which is what makes the
operations demonstrable in Postman rather than only implied by the live canvas.
"""

from fastapi import APIRouter, HTTPException, Query

from app.models import RoomCreate, RoomUpdate, StrokeCreate, StrokeStyleUpdate
from app.realtime.hub import hub
from app.repositories import rooms as rooms_repo
from app.repositories import snapshots as snap_repo
from app.repositories import strokes as strokes_repo
from app.util import jsonable

router = APIRouter(prefix="/api", tags=["rooms"])


async def _require_room(code: str) -> dict:
    room = await rooms_repo.get_room_by_code(code)
    if not room:
        raise HTTPException(404, f"room {code.upper()} not found")
    return room


# =========================================================== CREATE
@router.post("/rooms", status_code=201)
async def create_room(payload: RoomCreate):
    return jsonable(await rooms_repo.create_room(payload))


@router.post("/rooms/{code}/strokes", status_code=201)
async def create_stroke(
    code: str,
    payload: StrokeCreate,
    userId: str = Query("api-user"),
    userName: str = Query("API User"),
):
    """Insert a stroke over HTTP and broadcast it to any live canvas.

    Publishing here as well as from the socket handler means a stroke created in
    Postman appears on screen instantly, which makes for a much better demo than
    a page refresh.
    """
    room = await _require_room(code)
    stroke = await strokes_repo.create_stroke(room["_id"], userId, userName, payload)
    await rooms_repo.touch_room(room["_id"], stroke_delta=1)
    await hub.publish(room["code"], {"type": "stroke", "stroke": jsonable(stroke)})
    return jsonable(stroke)


# ============================================================= READ
@router.get("/rooms")
async def list_rooms(limit: int = 50, includeArchived: bool = False):
    return jsonable(await rooms_repo.list_rooms(limit=limit, include_archived=includeArchived))


@router.get("/rooms/{code}")
async def get_room(code: str):
    room = await _require_room(code)
    return {
        **jsonable(room),
        "activeStrokes": await strokes_repo.count_strokes(room["_id"], active_only=True),
        "totalStrokes": await strokes_repo.count_strokes(room["_id"], active_only=False),
        "maxSeq": await strokes_repo.max_seq(room["_id"]),
        "liveConnectionsOnThisInstance": hub.local_count(room["code"]),
    }


@router.get("/rooms/{code}/strokes")
async def list_strokes(
    code: str,
    afterSeq: int = 0,
    includeInactive: bool = False,
    limit: int = Query(500, le=200_000),
):
    room = await _require_room(code)
    docs = await strokes_repo.list_strokes(
        room["_id"], after_seq=afterSeq, include_inactive=includeInactive, limit=limit
    )
    return {"count": len(docs), "strokes": jsonable(docs)}


@router.get("/strokes/{stroke_id}")
async def get_stroke(stroke_id: str):
    doc = await strokes_repo.get_stroke(stroke_id)
    if not doc:
        raise HTTPException(404, "stroke not found")
    return jsonable(doc)


# =========================================================== UPDATE
@router.patch("/rooms/{code}")
async def update_room(code: str, payload: RoomUpdate):
    updated = await rooms_repo.update_room(code, payload)
    if not updated:
        raise HTTPException(404, "room not found")
    await hub.publish(updated["code"], {"type": "roomUpdated", "room": jsonable(updated)})
    return jsonable(updated)


@router.patch("/strokes/{stroke_id}")
async def restyle_stroke(stroke_id: str, payload: StrokeStyleUpdate):
    updated = await strokes_repo.restyle_stroke(stroke_id, payload)
    if not updated:
        raise HTTPException(404, "stroke not found")
    room = await rooms_repo.get_room_by_id(updated["roomId"])
    if room:
        await hub.publish(room["code"], {"type": "strokeUpdated", "stroke": jsonable(updated)})
    return jsonable(updated)


@router.post("/strokes/{stroke_id}/move")
async def move_stroke(stroke_id: str, dx: float = 0, dy: float = 0):
    updated = await strokes_repo.move_stroke(stroke_id, dx, dy)
    if not updated:
        raise HTTPException(404, "stroke not found, or it has no geometry to move")
    return jsonable(updated)


@router.post("/rooms/{code}/undo")
async def undo(code: str, userId: str = Query(...)):
    room = await _require_room(code)
    stroke = await strokes_repo.undo_last(room["_id"], userId)
    if not stroke:
        return {"undone": False, "reason": "nothing left to undo for this user"}
    await hub.publish(
        room["code"], {"type": "undo", "strokeId": str(stroke["_id"]), "seq": stroke["seq"]}
    )
    return {"undone": True, "stroke": jsonable(stroke)}


@router.post("/rooms/{code}/redo")
async def redo(code: str, userId: str = Query(...)):
    room = await _require_room(code)
    stroke = await strokes_repo.redo_last(room["_id"], userId)
    if not stroke:
        return {"redone": False, "reason": "nothing left to redo for this user"}
    await hub.publish(room["code"], {"type": "redo", "stroke": jsonable(stroke)})
    return {"redone": True, "stroke": jsonable(stroke)}


# =========================================================== DELETE
@router.delete("/strokes/{stroke_id}")
async def hard_delete_stroke(stroke_id: str):
    if not await strokes_repo.hard_delete_stroke(stroke_id):
        raise HTTPException(404, "stroke not found")
    return {"deleted": True, "id": stroke_id, "mode": "hard"}


@router.delete("/rooms/{code}/strokes")
async def clear_room(code: str):
    room = await _require_room(code)
    deleted = await strokes_repo.clear_room(room["_id"])
    await hub.publish(room["code"], {"type": "cleared", "deleted": deleted, "by": "API"})
    return {"deleted": deleted, "mode": "hard", "scope": "room"}


@router.post("/rooms/{code}/compact")
async def compact_room(code: str):
    """Turn soft deletes into hard deletes for strokes nobody redid."""
    room = await _require_room(code)
    purged = await strokes_repo.purge_undone(room["_id"])
    return {"purged": purged, "mode": "soft-to-hard compaction"}


@router.delete("/rooms/{code}")
async def delete_room(code: str):
    result = await rooms_repo.delete_room(code)
    if not result["deleted"]:
        raise HTTPException(404, "room not found")
    return result


# ========================================================= SNAPSHOTS
@router.get("/rooms/{code}/snapshot")
async def get_snapshot(code: str, includeImage: bool = False):
    room = await _require_room(code)
    snap = await snap_repo.latest_snapshot(room["_id"])
    if not snap:
        return {"snapshot": None}
    if not includeImage:
        snap.pop("image", None)
    return {"snapshot": jsonable(snap)}
