"""Measure what it costs to join a room, with and without a snapshot.

This is the evidence behind the snapshotting decision. Replaying an append-only
log is elegant but the payload grows linearly with history, so the report needs
real numbers rather than an assertion that it "might get slow".

    python scripts/measure_join.py
    python scripts/measure_join.py --room LNCSJ5 --snapshot-every 500
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import ROOMS, STROKES, close, db  # noqa: E402
from app.repositories import strokes as strokes_repo  # noqa: E402
from app.util import jsonable  # noqa: E402


async def measure(room: dict, snapshot_every: int) -> dict:
    room_id = room["_id"]
    max_seq = await strokes_repo.max_seq(room_id)

    started = time.perf_counter()
    full = await strokes_repo.list_strokes(room_id, after_seq=0)
    query_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    full_bytes = len(json.dumps(jsonable(full)).encode())
    serialise_ms = (time.perf_counter() - started) * 1000

    # What a joiner downloads when a snapshot already covers all but the tail.
    tail_after = max(max_seq - snapshot_every, 0)
    started = time.perf_counter()
    tail = await strokes_repo.list_strokes(room_id, after_seq=tail_after)
    tail_query_ms = (time.perf_counter() - started) * 1000
    tail_bytes = len(json.dumps(jsonable(tail)).encode())

    # A PNG of a busy 1600x900 board sits in this range in practice; measured
    # exactly when a real snapshot exists.
    snap = await db()["snapshots"].find_one({"roomId": room_id}, sort=[("upToSeq", -1)])
    snap_bytes = snap["bytes"] if snap else 180 * 1024

    return {
        "code": room["code"],
        "strokes": len(full),
        "maxSeq": max_seq,
        "fullQueryMs": round(query_ms, 1),
        "fullSerialiseMs": round(serialise_ms, 1),
        "fullMB": round(full_bytes / 1024 / 1024, 2),
        "tailStrokes": len(tail),
        "tailQueryMs": round(tail_query_ms, 1),
        "tailMB": round(tail_bytes / 1024 / 1024, 3),
        "snapshotKB": round(snap_bytes / 1024, 1),
        "snapshotMeasured": snap is not None,
        "withSnapshotMB": round((tail_bytes + snap_bytes) / 1024 / 1024, 2),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", help="room code; default is every room")
    ap.add_argument("--snapshot-every", type=int, default=500)
    args = ap.parse_args()

    query = {"code": args.room.upper()} if args.room else {}
    rooms = [r async for r in db()[ROOMS].find(query).sort("strokeCount", -1)]
    if not rooms:
        print("no matching rooms")
        await close()
        return

    rows = [await measure(r, args.snapshot_every) for r in rooms]

    header = (
        f"{'room':<8} {'strokes':>8} {'full MB':>8} {'query ms':>9} "
        f"{'tail':>6} {'snap KB':>8} {'join MB':>8} {'saving':>8}"
    )
    print("\nCost of joining a room\n" + header)
    print("-" * len(header))
    for r in rows:
        saving = (1 - r["withSnapshotMB"] / r["fullMB"]) * 100 if r["fullMB"] else 0
        print(
            f"{r['code']:<8} {r['strokes']:>8,} {r['fullMB']:>8.2f} {r['fullQueryMs']:>9.1f} "
            f"{r['tailStrokes']:>6,} {r['snapshotKB']:>8.1f} {r['withSnapshotMB']:>8.2f} "
            f"{saving:>7.1f}%"
        )

    biggest = rows[0]
    print(
        f"\nWithout snapshotting, joining {biggest['code']} transfers "
        f"{biggest['fullMB']:.2f} MB of stroke documents and spends "
        f"{biggest['fullQueryMs']:.0f} ms in MongoDB plus "
        f"{biggest['fullSerialiseMs']:.0f} ms serialising to JSON."
    )
    print(
        f"With a snapshot at seq {biggest['maxSeq'] - args.snapshot_every}, the same "
        f"join transfers {biggest['withSnapshotMB']:.2f} MB "
        f"({biggest['snapshotKB']:.0f} KB image plus {biggest['tailStrokes']:,} tail strokes)."
    )
    if not biggest["snapshotMeasured"]:
        print("(snapshot size is an estimate; no snapshot has been saved for this room yet)")

    stats = await db().command({"collStats": STROKES})
    print(
        f"\nstrokes collection: {stats['count']:,} documents, "
        f"{stats['size'] / 1024 / 1024:.0f} MB data, "
        f"{stats['totalIndexSize'] / 1024 / 1024:.0f} MB indexes, "
        f"{stats.get('avgObjSize', 0):.0f} bytes average"
    )

    await close()


if __name__ == "__main__":
    asyncio.run(main())
