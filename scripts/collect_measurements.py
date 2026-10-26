"""Capture every measured number the report and the slide deck quote.

Writing these to one file means the document, the charts, and the presentation all
read from the same measurements, so none of them can quietly go stale after a
reseed. Run this after seeding, then build the figures and the report.

    python scripts/collect_measurements.py --base http://127.0.0.1:8001
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import aggregations  # noqa: E402
from app.db import ROOMS, SNAPSHOTS, STROKES, close, db  # noqa: E402
from app.util import jsonable  # noqa: E402
from scripts.measure_join import measure as measure_join  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "measurements.json"


def trim_points(doc: dict, keep: int = 3) -> dict:
    """Shorten point arrays so a sample document fits on a page."""
    doc = dict(doc)
    pts = doc.get("points")
    if isinstance(pts, list) and len(pts) > keep:
        doc["points"] = pts[:keep] + [f"... {len(pts) - keep} more points ..."]
    return doc


async def sample_documents() -> dict:
    samples: dict = {"rooms": None, "strokes": {}, "snapshots": None}

    room = await db()[ROOMS].find_one({"strokeCount": {"$gt": 100}}) or await db()[ROOMS].find_one()
    if room:
        samples["rooms"] = jsonable(room)

    # One example per tool, to show several document shapes in one collection.
    for tool in ("pen", "rect", "text", "eraser"):
        doc = await db()[STROKES].find_one({"tool": tool})
        if doc:
            samples["strokes"][tool] = jsonable(trim_points(doc))

    snap = await db()[SNAPSHOTS].find_one({}, sort=[("upToSeq", -1)])
    if snap:
        snap = dict(snap)
        image = snap.pop("image", "")
        snap["image"] = f"<data:image/png;base64 ... {len(image):,} characters ...>"
        samples["snapshots"] = jsonable(snap)

    return samples


async def collection_stats() -> dict:
    out = {}
    for coll in (ROOMS, STROKES, SNAPSHOTS):
        s = await db().command({"collStats": coll})
        out[coll] = {
            "documents": s.get("count", 0),
            "dataSizeMB": round(s.get("size", 0) / 1024 / 1024, 2),
            "storageSizeMB": round(s.get("storageSize", 0) / 1024 / 1024, 2),
            "indexSizeMB": round(s.get("totalIndexSize", 0) / 1024 / 1024, 2),
            "avgDocBytes": round(s.get("avgObjSize", 0)),
            "indexSizesKB": {k: round(v / 1024, 1) for k, v in s.get("indexSizes", {}).items()},
        }
    return out


async def index_catalogue() -> dict:
    from app.db import INDEX_PLAN

    live = {}
    for coll in (ROOMS, STROKES, SNAPSHOTS):
        live[coll] = [jsonable(dict(ix)) async for ix in await db()[coll].list_indexes()]

    planned = [
        {
            "collection": coll,
            "name": opts["name"],
            "keys": {k: v for k, v in keys},
            "unique": opts.get("unique", False),
            "rationale": why,
        }
        for coll, keys, opts, why in INDEX_PLAN
    ]
    return {"planned": planned, "live": live}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--room", help="room to profile; defaults to the largest")
    ap.add_argument("--skip-benchmark", action="store_true",
                    help="the benchmark briefly drops indexes; skip it if the app is in use")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    rooms = [r async for r in db()[ROOMS].find().sort("strokeCount", -1)]
    if not rooms:
        print("no rooms found — run scripts/seed.py first")
        await close()
        return

    target = next((r for r in rooms if r["code"] == args.room.upper()), None) if args.room else rooms[0]
    target = target or rooms[0]
    print(f"profiling room {target['code']} ({target.get('strokeCount', 0):,} strokes)")

    data: dict = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "room": target["code"],
        "roomCount": len(rooms),
        "collectionStats": await collection_stats(),
        "indexes": await index_catalogue(),
        "samples": await sample_documents(),
        "joinCost": [await measure_join(r, 500) for r in rooms],
        "analytics": {},
        "benchmark": None,
        "crudTranscript": None,
    }

    # Aggregations are read straight from the registry so the report shows the
    # same pipeline text the application executes.
    for key in aggregations.REGISTRY:
        spec = aggregations.REGISTRY[key]
        room_id = None if key == "leaderboard" else target["_id"]
        import time

        started = time.perf_counter()
        results = await aggregations.run(key, room_id)
        elapsed = (time.perf_counter() - started) * 1000
        data["analytics"][key] = {
            "meta": aggregations.describe(key),
            "pipeline": jsonable(spec.build(room_id)),
            "elapsedMs": round(elapsed, 2),
            "resultCount": len(results),
            "results": jsonable(results)[:20],
        }
        print(f"  {key:<14} {len(results):>5} rows  {elapsed:>8.1f} ms")

    async with httpx.AsyncClient(base_url=base, timeout=600) as client:
        try:
            await client.get("/api/admin/health")
            if not args.skip_benchmark:
                print("running the index benchmark (drops and rebuilds indexes) ...")
                r = await client.post("/api/admin/benchmark", params={"room": target["code"]})
                data["benchmark"] = r.json()["comparison"]
                for name, c in data["benchmark"].items():
                    print(f"  {name:<18} {c['withoutIndex']['ms']} ms -> "
                          f"{c['withIndex']['ms']} ms  ({c['speedup']}x)")
        except Exception as exc:
            print(f"  server at {base} unavailable, skipping benchmark: {exc}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(Path.cwd())} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")

    await close()


if __name__ == "__main__":
    asyncio.run(main())
