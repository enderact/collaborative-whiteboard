"""The WebSocket protocol.

Two message classes matter for performance:

`preview` carries in-flight points while a pointer is still down. It is relayed
through Redis and never written to MongoDB, because a stroke in progress is not
yet a fact about the document.

`commit` fires once on pointer-up and writes a single document holding the whole
point array. Persisting per point instead would put an Atlas round trip of
50-200 ms inside the drawing loop, which is the latency the split avoids.
"""

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.models import StrokeCreate
from app.realtime.hub import hub
from app.repositories import rooms as rooms_repo
from app.repositories import snapshots as snap_repo
from app.repositories import strokes as strokes_repo
from app.util import jsonable, now

log = logging.getLogger("whiteboard.ws")
router = APIRouter()

PALETTE = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2"]


def color_for(user_id: str) -> str:
    return PALETTE[hash(user_id) % len(PALETTE)]


@router.websocket("/ws/{code}")
async def whiteboard_socket(ws: WebSocket, code: str):
    code = code.upper()
    room = await rooms_repo.get_room_by_code(code)
    if not room:
        await ws.close(code=4404, reason="room not found")
        return

    await ws.accept()
    conn_id = uuid.uuid4().hex
    room_id = room["_id"]

    user_id = ws.query_params.get("userId") or f"anon_{conn_id[:6]}"
    user_name = ws.query_params.get("userName") or "Guest"
    color = color_for(user_id)

    await hub.register(code, conn_id, ws)
    # Register the participant before building the init payload, otherwise the
    # joining client receives a roster that is missing itself.
    room = await rooms_repo.upsert_participant(code, user_id, user_name, color) or room

    # Redis may have been restarted since these strokes were written, so realign
    # the counter with what is actually persisted before handing out new numbers.
    persisted_max = await strokes_repo.max_seq(room_id)
    await strokes_repo.sync_seq_floor(room_id, persisted_max)

    snapshot = await snap_repo.latest_snapshot(room_id)
    after = snapshot["upToSeq"] if snapshot else 0
    tail, truncated, available = await strokes_repo.list_strokes_capped(
        room_id, after_seq=after, cap=settings.max_initial_strokes
    )

    await ws.send_json(
        {
            "type": "init",
            "instance": settings.instance_id,
            "connId": conn_id,
            "you": {"userId": user_id, "userName": user_name, "color": color},
            "room": jsonable(room),
            "snapshot": jsonable(snapshot) if snapshot else None,
            "snapshotImage": snapshot["image"] if snapshot else None,
            "strokes": jsonable(tail),
            "replayedFromSeq": after,
            "truncated": truncated,
            "availableAfterSnapshot": available,
            "maxSeq": persisted_max,
            "presence": await hub.get_presence(code),
            "snapshotInterval": settings.snapshot_interval,
        }
    )

    await hub.set_presence(
        code, user_id, {"userId": user_id, "userName": user_name, "color": color, "x": -1, "y": -1}
    )
    await hub.publish(
        code,
        {"type": "joined", "userId": user_id, "userName": user_name, "color": color},
        skip_conn=conn_id,
    )

    try:
        while True:
            msg = await ws.receive_json()
            await _handle(msg, ws, code, room_id, conn_id, user_id, user_name, color)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("socket error in room %s", code)
    finally:
        await hub.unregister(code, conn_id)
        await hub.clear_presence(code, user_id)
        await rooms_repo.remove_participant(code, user_id)
        await hub.publish(code, {"type": "left", "userId": user_id, "userName": user_name})


async def _handle(msg, ws, code, room_id, conn_id, user_id, user_name, color):
    kind = msg.get("type")

    if kind == "preview":
        await hub.publish(
            code,
            {
                "type": "preview",
                "userId": user_id,
                "color": color,
                "tool": msg.get("tool", "pen"),
                "style": msg.get("style", {}),
                "points": msg.get("points", []),
                "seg": msg.get("seg", 0),
            },
            skip_conn=conn_id,
        )
        return

    if kind == "cursor":
        await hub.set_presence(
            code,
            user_id,
            {
                "userId": user_id,
                "userName": user_name,
                "color": color,
                "x": msg.get("x", 0),
                "y": msg.get("y", 0),
            },
        )
        await hub.publish(
            code,
            {
                "type": "cursor",
                "userId": user_id,
                "userName": user_name,
                "color": color,
                "x": msg.get("x", 0),
                "y": msg.get("y", 0),
            },
            skip_conn=conn_id,
        )
        return

    if kind == "commit":
        payload = StrokeCreate(**msg.get("stroke", {}))
        stroke = await strokes_repo.create_stroke(room_id, user_id, user_name, payload)
        await rooms_repo.touch_room(room_id, stroke_delta=1)

        # The author already rendered this stroke optimistically, so it gets a
        # lightweight ack with the authoritative seq while everyone else gets the
        # full document.
        await ws.send_json(
            {
                "type": "ack",
                "clientMsgId": payload.clientMsgId,
                "id": str(stroke["_id"]),
                "seq": stroke["seq"],
            }
        )
        await hub.publish(code, {"type": "stroke", "stroke": jsonable(stroke)}, skip_conn=conn_id)
        return

    if kind in ("undo", "redo"):
        fn = strokes_repo.undo_last if kind == "undo" else strokes_repo.redo_last
        stroke = await fn(room_id, user_id)
        if not stroke:
            await ws.send_json({"type": "noop", "of": kind})
            return
        # Undo and redo both change visibility, so every client including the
        # author must re-evaluate; no skip here.
        await hub.publish(
            code,
            {
                "type": kind,
                "strokeId": str(stroke["_id"]),
                "seq": stroke["seq"],
                "userId": user_id,
                "stroke": jsonable(stroke) if kind == "redo" else None,
            },
        )
        return

    if kind == "clear":
        deleted = await strokes_repo.clear_room(room_id)
        await rooms_repo.touch_room(room_id)
        await hub.publish(code, {"type": "cleared", "deleted": deleted, "by": user_name})
        return

    if kind == "snapshot":
        stroke_count = await strokes_repo.count_strokes(room_id, active_only=False)
        snap = await snap_repo.create_snapshot(
            room_id, msg.get("upToSeq", 0), msg.get("image", ""), stroke_count
        )
        await snap_repo.prune_snapshots(room_id)
        await ws.send_json({"type": "snapshotSaved", "snapshot": jsonable(snap)})
        return

    if kind == "ping":
        await hub.set_presence(
            code,
            user_id,
            {"userId": user_id, "userName": user_name, "color": color, "x": -1, "y": -1},
        )
        await ws.send_json({"type": "pong", "at": now().isoformat()})
        return
