import random
import string
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

# Ambiguous glyphs removed so a room code can be read aloud without confusion.
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "OI01")


def now() -> datetime:
    return datetime.now(timezone.utc)


def room_code(length: int = 6) -> str:
    return "".join(random.choice(_CODE_ALPHABET) for _ in range(length))


def jsonable(value: Any) -> Any:
    """Recursively convert BSON types into something FastAPI can serialise."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {("id" if k == "_id" else k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def bbox_of_points(points: list[dict]) -> dict[str, float]:
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    return {"minX": min(xs), "minY": min(ys), "maxX": max(xs), "maxY": max(ys)}
