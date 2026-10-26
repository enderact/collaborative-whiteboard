"""Canvas snapshots, so joining a busy room does not mean replaying everything.

A snapshot is a raster of the canvas as it looked at a known sequence number.
Joining then costs one snapshot read plus the strokes with `seq > upToSeq`,
instead of a full history replay that grows without bound.

The image is rasterised by the client and stored inline as a data URL. At a few
hundred kilobytes per PNG that sits comfortably inside the 16 MB document limit;
GridFS would be the route if snapshots ever exceeded it, and the design document
covers that trade-off.
"""

from pymongo import DESCENDING

from app.db import SNAPSHOTS, db
from app.util import now


async def create_snapshot(room_id, up_to_seq: int, image: str, stroke_count: int) -> dict:
    doc = {
        "roomId": room_id,
        "upToSeq": up_to_seq,
        "strokeCount": stroke_count,
        "image": image,
        "bytes": len(image),
        "createdAt": now(),
    }
    res = await db()[SNAPSHOTS].insert_one(doc)
    doc["_id"] = res.inserted_id
    doc.pop("image", None)  # never echo the payload back
    return doc


async def latest_snapshot(room_id) -> dict | None:
    cursor = db()[SNAPSHOTS].find({"roomId": room_id}).sort("upToSeq", DESCENDING).limit(1)
    docs = [d async for d in cursor]
    return docs[0] if docs else None


async def prune_snapshots(room_id, keep: int = 3) -> int:
    """Keep only the newest few snapshots; older ones are dead weight."""
    cursor = (
        db()[SNAPSHOTS]
        .find({"roomId": room_id}, {"_id": 1})
        .sort("upToSeq", DESCENDING)
        .skip(keep)
    )
    stale = [d["_id"] async for d in cursor]
    if not stale:
        return 0
    res = await db()[SNAPSHOTS].delete_many({"_id": {"$in": stale}})
    return res.deleted_count
