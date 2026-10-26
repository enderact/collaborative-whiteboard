"""MongoDB and Redis connections, plus the index definitions for the project.

Index rationale is kept next to the definitions because the review asks for a
justification of every index rather than just its existence.
"""

import logging

import redis.asyncio as aioredis
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient

from app.config import settings

log = logging.getLogger("whiteboard.db")

ROOMS = "rooms"
STROKES = "strokes"
SNAPSHOTS = "snapshots"

_mongo: AsyncMongoClient | None = None
_redis: aioredis.Redis | None = None


# (collection, keys, options, why-it-exists)
INDEX_PLAN: list[tuple[str, list[tuple[str, int]], dict, str]] = [
    (
        ROOMS,
        [("code", ASCENDING)],
        {"name": "ix_room_code", "unique": True},
        "Every join is a lookup by short room code; unique prevents duplicate codes.",
    ),
    (
        ROOMS,
        [("lastActivityAt", DESCENDING)],
        {"name": "ix_room_activity"},
        "Powers the 'recent rooms' list without scanning the whole collection.",
    ),
    (
        STROKES,
        [("roomId", ASCENDING), ("seq", ASCENDING)],
        {"name": "ix_stroke_replay"},
        "The hot path: replay a room's strokes in order. Covers range queries "
        "on seq for incremental loading after a snapshot.",
    ),
    (
        STROKES,
        [
            ("roomId", ASCENDING),
            ("userId", ASCENDING),
            ("active", ASCENDING),
            ("seq", DESCENDING),
        ],
        {"name": "ix_stroke_undo"},
        "Per-user undo claims the newest active stroke belonging to that user. "
        "Descending seq lets the atomic findOneAndUpdate stop at the first hit.",
    ),
    (
        STROKES,
        [("roomId", ASCENDING), ("tool", ASCENDING)],
        {"name": "ix_stroke_tool"},
        "Supports the tool-distribution aggregation without a collection scan.",
    ),
    (
        STROKES,
        [("roomId", ASCENDING), ("createdAt", ASCENDING)],
        {"name": "ix_stroke_time"},
        "Supports the time-bucketed activity aggregation ($dateTrunc grouping).",
    ),
    (
        SNAPSHOTS,
        [("roomId", ASCENDING), ("upToSeq", DESCENDING)],
        {"name": "ix_snapshot_latest"},
        "Fetches the newest snapshot for a room in a single index seek.",
    ),
]


def mongo() -> AsyncMongoClient:
    global _mongo
    if _mongo is None:
        _mongo = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    return _mongo


def db():
    return mongo()[settings.mongo_db]


def redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def ensure_indexes() -> list[dict]:
    """Create every planned index. Returns what was created, for the demo UI."""
    created = []
    for coll, keys, opts, why in INDEX_PLAN:
        name = await db()[coll].create_index(keys, **opts)
        created.append(
            {
                "collection": coll,
                "name": name,
                "keys": {k: v for k, v in keys},
                "unique": opts.get("unique", False),
                "rationale": why,
            }
        )
    log.info("ensured %d indexes", len(created))
    return created


async def drop_demo_indexes() -> list[str]:
    """Drop the non-unique indexes so a before/after benchmark can be shown."""
    dropped = []
    for coll, _keys, opts, _why in INDEX_PLAN:
        if opts.get("unique"):
            continue
        try:
            await db()[coll].drop_index(opts["name"])
            dropped.append(f"{coll}.{opts['name']}")
        except Exception:
            pass
    return dropped


async def close() -> None:
    if _redis is not None:
        await _redis.aclose()
    if _mongo is not None:
        await _mongo.close()
