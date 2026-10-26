"""Synthetic stroke generator.

The project claims a 50,000-100,000 document dataset, which nobody is going to
draw by hand. Indexing and aggregation results are also meaningless at a few
hundred documents, so this script produces a realistically shaped corpus:
a long tail of short pen strokes, a handful of large ones, a mix of tools, undone
strokes for the undo-rate analytics, and timestamps spread over hours so the
time-bucketed pipeline has something to bucket.

    python scripts/seed.py --strokes 80000 --rooms 5
"""

import argparse
import asyncio
import math
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import ROOMS, STROKES, close, db, ensure_indexes, redis  # noqa: E402
from app.models import RoomCreate  # noqa: E402
from app.repositories import rooms as rooms_repo  # noqa: E402
from app.repositories.strokes import seq_key  # noqa: E402
from app.util import bbox_of_points, now  # noqa: E402

TOOLS = ["pen"] * 68 + ["eraser"] * 9 + ["rect"] * 8 + ["ellipse"] * 7 + ["line"] * 6 + ["text"] * 2
COLORS = ["#111827", "#dc2626", "#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2"]
NAMES = ["Devesh", "Prakrit", "Lakshya", "Aarav", "Meera", "Rohan", "Isha", "Karthik"]
WORDS = ["sprint", "schema", "replay", "index", "pub/sub", "undo", "seq", "atlas", "shard", "TTL"]

LOGICAL_W, LOGICAL_H = 1600, 900


def freehand(cx: float, cy: float, count: int) -> list[dict]:
    """A jittered arc, which is roughly what a real pen stroke looks like."""
    radius = random.uniform(15, 160)
    start = random.uniform(0, math.tau)
    sweep = random.uniform(0.4, 2.6)
    pts = []
    for i in range(count):
        t = start + sweep * (i / max(count - 1, 1))
        pts.append(
            {
                "x": round(min(max(cx + math.cos(t) * radius + random.gauss(0, 1.6), 0), LOGICAL_W), 2),
                "y": round(min(max(cy + math.sin(t) * radius + random.gauss(0, 1.6), 0), LOGICAL_H), 2),
                "p": round(random.uniform(0.25, 1.0), 2),
            }
        )
    return pts


def point_count() -> int:
    """Long-tailed: most strokes are short flicks, a few are long curves."""
    roll = random.random()
    if roll < 0.55:
        return random.randint(3, 18)
    if roll < 0.88:
        return random.randint(19, 60)
    if roll < 0.985:
        return random.randint(61, 180)
    return random.randint(181, 600)


def build_stroke(room_id, seq: int, user: dict, created_at) -> dict:
    tool = random.choice(TOOLS)
    cx, cy = random.uniform(60, LOGICAL_W - 60), random.uniform(60, LOGICAL_H - 60)

    # Roughly one stroke in nine was undone and never redone, which is a plausible
    # rate for freehand drawing and gives the undo analytics real numbers.
    active = random.random() > 0.11

    doc = {
        "roomId": room_id,
        "seq": seq,
        "userId": user["userId"],
        "userName": user["userName"],
        "tool": tool,
        "style": {
            "color": "#000000" if tool == "eraser" else random.choice(COLORS),
            "width": round(random.uniform(14, 34), 1) if tool == "eraser" else round(random.uniform(1.5, 12), 1),
            "opacity": 1.0,
            "blend": "destination-out" if tool == "eraser" else "source-over",
        },
        "active": active,
        "undoneAt": None if active else created_at + timedelta(seconds=random.randint(1, 30)),
        "undoneBy": None if active else user["userId"],
        "clientMsgId": None,
        "createdAt": created_at,
        "updatedAt": created_at,
    }

    if tool in ("pen", "eraser"):
        pts = freehand(cx, cy, point_count())
        doc["points"] = pts
        doc["pointCount"] = len(pts)
        doc["bbox"] = bbox_of_points(pts)
    elif tool == "text":
        doc["points"] = [{"x": round(cx, 2), "y": round(cy, 2), "p": 0.5}]
        doc["pointCount"] = 1
        doc["text"] = " ".join(random.sample(WORDS, random.randint(1, 3)))
        doc["font"] = f"{random.choice([14, 16, 20, 26])}px Inter, sans-serif"
        doc["bbox"] = {"minX": cx, "minY": cy, "maxX": cx + 120, "maxY": cy + 26}
    else:
        w = random.uniform(40, 420) * random.choice([1, -1])
        h = random.uniform(30, 300) * random.choice([1, -1])
        doc["geometry"] = {"x": round(cx, 2), "y": round(cy, 2), "w": round(w, 2), "h": round(h, 2)}
        doc["bbox"] = {
            "minX": round(min(cx, cx + w), 2),
            "minY": round(min(cy, cy + h), 2),
            "maxX": round(max(cx, cx + w), 2),
            "maxY": round(max(cy, cy + h), 2),
        }

    return doc


async def seed_room(index: int, stroke_target: int, user_count: int, batch_size: int) -> dict:
    room = await rooms_repo.create_room(
        RoomCreate(name=f"Seeded board {index + 1}", createdBy="seed_user_1")
    )
    room_id = room["_id"]

    users = [
        {"userId": f"seed_user_{i + 1}", "userName": NAMES[i % len(NAMES)]}
        for i in range(user_count)
    ]
    for u in users:
        await rooms_repo.upsert_participant(
            room["code"], u["userId"], u["userName"], random.choice(COLORS)
        )

    # Spread creation times across a plausible session so $dateTrunc has buckets.
    session_start = now() - timedelta(hours=random.uniform(2, 20))
    span = timedelta(minutes=random.randint(25, 110))

    written = 0
    batch: list[dict] = []
    for seq in range(1, stroke_target + 1):
        # Weighted so one or two people dominate, as in a real session.
        user = random.choices(users, weights=[6, 4, 3] + [1] * (len(users) - 3))[0] \
            if len(users) > 3 else random.choice(users)
        created = session_start + span * (seq / stroke_target)
        batch.append(build_stroke(room_id, seq, user, created))

        if len(batch) >= batch_size:
            await db()[STROKES].insert_many(batch, ordered=False)
            written += len(batch)
            batch.clear()
            print(f"  room {room['code']}: {written:,}/{stroke_target:,}", end="\r", flush=True)

    if batch:
        await db()[STROKES].insert_many(batch, ordered=False)
        written += len(batch)

    # The Redis counter is the source of new sequence numbers, so it has to start
    # above whatever was just written or the next live stroke collides.
    await redis().set(seq_key(room_id), stroke_target)
    await db()[ROOMS].update_one(
        {"_id": room_id},
        {"$set": {"strokeCount": written, "lastActivityAt": session_start + span}},
    )

    print(f"  room {room['code']}: {written:,} strokes written        ")
    return {"code": room["code"], "strokes": written}


async def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic whiteboard data")
    ap.add_argument("--strokes", type=int, default=80_000, help="total strokes across all rooms")
    ap.add_argument("--rooms", type=int, default=5, help="number of rooms to create")
    ap.add_argument("--users", type=int, default=5, help="distinct users per room")
    ap.add_argument("--batch", type=int, default=2_000, help="insert_many batch size")
    ap.add_argument("--wipe", action="store_true", help="drop existing rooms and strokes first")
    args = ap.parse_args()

    await ensure_indexes()

    if args.wipe:
        await db()[STROKES].delete_many({})
        await db()[ROOMS].delete_many({})
        await db()["snapshots"].delete_many({})
        print("wiped existing collections")

    # The first room gets most of the data so there is one genuinely large room
    # to benchmark against, plus smaller ones to populate the leaderboard.
    weights = [0.6] + [0.4 / max(args.rooms - 1, 1)] * (args.rooms - 1)
    targets = [max(int(args.strokes * w), 50) for w in weights[: args.rooms]]

    print(f"seeding {sum(targets):,} strokes across {args.rooms} rooms")
    created = []
    for i, target in enumerate(targets):
        created.append(await seed_room(i, target, args.users, args.batch))

    total = await db()[STROKES].count_documents({})
    stats = await db().command({"collStats": STROKES})
    print("\ndone")
    print(f"  strokes collection: {total:,} documents")
    print(f"  data size:          {stats['size'] / 1024 / 1024:.1f} MB")
    print(f"  index size:         {stats['totalIndexSize'] / 1024 / 1024:.1f} MB")
    print(f"  avg document:       {stats.get('avgObjSize', 0):.0f} bytes")
    print("\nlargest room for demos and benchmarks: " + created[0]["code"])

    await close()


if __name__ == "__main__":
    asyncio.run(main())
