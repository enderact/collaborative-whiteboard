"""Aggregation pipelines backing the room analytics panel.

Each entry records the question it answers and the stages it uses, because the
API returns the pipeline alongside its results. The demo can then show the query
and its output side by side instead of asserting that a pipeline exists.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from app.db import ROOMS, STROKES, db


@dataclass
class Pipeline:
    key: str
    title: str
    question: str
    collection: str
    stages: list[str]
    build: Callable[[Any], list[dict]]
    chart: str = "table"
    notes: str = ""
    tags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# 1. Who contributed what
# --------------------------------------------------------------------------
def _contributors(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id}},
        {
            "$group": {
                "_id": {"userId": "$userId", "userName": "$userName"},
                "totalStrokes": {"$sum": 1},
                "activeStrokes": {"$sum": {"$cond": ["$active", 1, 0]}},
                "undoneStrokes": {"$sum": {"$cond": ["$active", 0, 1]}},
                "totalPoints": {"$sum": {"$ifNull": ["$pointCount", 0]}},
                "toolsUsed": {"$addToSet": "$tool"},
                "firstStrokeAt": {"$min": "$createdAt"},
                "lastStrokeAt": {"$max": "$createdAt"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "userId": "$_id.userId",
                "userName": "$_id.userName",
                "totalStrokes": 1,
                "activeStrokes": 1,
                "undoneStrokes": 1,
                "totalPoints": 1,
                "toolsUsed": 1,
                "avgPointsPerStroke": {
                    "$round": [
                        {"$divide": ["$totalPoints", {"$max": ["$totalStrokes", 1]}]},
                        1,
                    ]
                },
                "undoRatePct": {
                    "$round": [
                        {
                            "$multiply": [
                                {"$divide": ["$undoneStrokes", {"$max": ["$totalStrokes", 1]}]},
                                100,
                            ]
                        },
                        1,
                    ]
                },
                "activeSeconds": {
                    "$round": [
                        {
                            "$divide": [
                                {"$subtract": ["$lastStrokeAt", "$firstStrokeAt"]},
                                1000,
                            ]
                        },
                        0,
                    ]
                },
            }
        },
        {"$sort": {"totalStrokes": -1}},
    ]


# --------------------------------------------------------------------------
# 2. Tool usage mix
# --------------------------------------------------------------------------
def _tool_usage(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id}},
        {
            "$group": {
                "_id": "$tool",
                "count": {"$sum": 1},
                "avgPoints": {"$avg": {"$ifNull": ["$pointCount", 0]}},
                "avgWidth": {"$avg": "$style.width"},
                "distinctColors": {"$addToSet": "$style.color"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "tool": "$_id",
                "count": 1,
                "avgPoints": {"$round": ["$avgPoints", 1]},
                "avgWidth": {"$round": ["$avgWidth", 2]},
                "colorCount": {"$size": "$distinctColors"},
            }
        },
        {"$sort": {"count": -1}},
    ]


# --------------------------------------------------------------------------
# 3. Drawing activity over time
# --------------------------------------------------------------------------
def _activity_timeline(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id}},
        {
            "$group": {
                "_id": {"$dateTrunc": {"date": "$createdAt", "unit": "minute", "binSize": 1}},
                "strokes": {"$sum": 1},
                "points": {"$sum": {"$ifNull": ["$pointCount", 0]}},
                "contributors": {"$addToSet": "$userId"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "bucket": "$_id",
                "strokes": 1,
                "points": 1,
                "contributorCount": {"$size": "$contributors"},
            }
        },
        {"$sort": {"bucket": 1}},
        {"$limit": 240},
    ]


# --------------------------------------------------------------------------
# 4. Stroke complexity distribution
# --------------------------------------------------------------------------
def _complexity_buckets(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id, "pointCount": {"$exists": True}}},
        {
            "$bucket": {
                "groupBy": "$pointCount",
                "boundaries": [0, 10, 25, 50, 100, 250, 1000],
                "default": "1000+",
                "output": {
                    "strokes": {"$sum": 1},
                    "totalPoints": {"$sum": "$pointCount"},
                    "avgWidth": {"$avg": "$style.width"},
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "minPoints": "$_id",
                "strokes": 1,
                "totalPoints": 1,
                "avgWidth": {"$round": ["$avgWidth", 2]},
            }
        },
    ]


# --------------------------------------------------------------------------
# 5. Colour palette actually in use
# --------------------------------------------------------------------------
def _color_palette(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id, "active": True, "tool": {"$ne": "eraser"}}},
        {
            "$group": {
                "_id": "$style.color",
                "strokes": {"$sum": 1},
                "users": {"$addToSet": "$userName"},
                "totalInk": {"$sum": {"$multiply": ["$style.width", {"$ifNull": ["$pointCount", 1]}]}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "color": "$_id",
                "strokes": 1,
                "userCount": {"$size": "$users"},
                "totalInk": {"$round": ["$totalInk", 0]},
            }
        },
        {"$sort": {"strokes": -1}},
        {"$limit": 12},
    ]


# --------------------------------------------------------------------------
# 6. Bounding box of everything drawn ("fit canvas to content")
# --------------------------------------------------------------------------
def _content_bounds(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id, "active": True, "bbox": {"$exists": True}}},
        {
            "$group": {
                "_id": None,
                "minX": {"$min": "$bbox.minX"},
                "minY": {"$min": "$bbox.minY"},
                "maxX": {"$max": "$bbox.maxX"},
                "maxY": {"$max": "$bbox.maxY"},
                "strokes": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "minX": {"$round": ["$minX", 1]},
                "minY": {"$round": ["$minY", 1]},
                "maxX": {"$round": ["$maxX", 1]},
                "maxY": {"$round": ["$maxY", 1]},
                "width": {"$round": [{"$subtract": ["$maxX", "$minX"]}, 1]},
                "height": {"$round": [{"$subtract": ["$maxY", "$minY"]}, 1]},
                "strokes": 1,
            }
        },
    ]


# --------------------------------------------------------------------------
# 7. Room leaderboard across the whole database, joining rooms to strokes
# --------------------------------------------------------------------------
def _room_leaderboard(_room_id) -> list[dict]:
    return [
        {"$match": {"isArchived": False}},
        {
            "$lookup": {
                "from": STROKES,
                "localField": "_id",
                "foreignField": "roomId",
                "as": "strokeStats",
                # The sub-pipeline aggregates inside the join so the 100k stroke
                # documents are never materialised into the parent document.
                "pipeline": [
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "active": {"$sum": {"$cond": ["$active", 1, 0]}},
                            "points": {"$sum": {"$ifNull": ["$pointCount", 0]}},
                            "contributors": {"$addToSet": "$userId"},
                        }
                    }
                ],
            }
        },
        {"$set": {"stats": {"$first": "$strokeStats"}}},
        {
            "$project": {
                "_id": 0,
                "code": 1,
                "name": 1,
                "createdAt": 1,
                "participantCount": {"$size": "$participants"},
                "totalStrokes": {"$ifNull": ["$stats.total", 0]},
                "activeStrokes": {"$ifNull": ["$stats.active", 0]},
                "totalPoints": {"$ifNull": ["$stats.points", 0]},
                "contributorCount": {"$size": {"$ifNull": ["$stats.contributors", []]}},
            }
        },
        {"$sort": {"totalStrokes": -1}},
        {"$limit": 20},
    ]


# --------------------------------------------------------------------------
# 8. One-request dashboard
# --------------------------------------------------------------------------
def _dashboard(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id}},
        {
            # $facet runs independent sub-pipelines over the same matched set, so
            # the analytics panel loads from a single round trip instead of five.
            "$facet": {
                "totals": [
                    {
                        "$group": {
                            "_id": None,
                            "strokes": {"$sum": 1},
                            "active": {"$sum": {"$cond": ["$active", 1, 0]}},
                            "points": {"$sum": {"$ifNull": ["$pointCount", 0]}},
                            "contributors": {"$addToSet": "$userId"},
                            "maxSeq": {"$max": "$seq"},
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "strokes": 1,
                            "active": 1,
                            "points": 1,
                            "maxSeq": 1,
                            "contributorCount": {"$size": "$contributors"},
                        }
                    },
                ],
                "byTool": [
                    {"$group": {"_id": "$tool", "count": {"$sum": 1}}},
                    {"$project": {"_id": 0, "tool": "$_id", "count": 1}},
                    {"$sort": {"count": -1}},
                ],
                "topContributors": [
                    {"$group": {"_id": "$userName", "strokes": {"$sum": 1}}},
                    {"$project": {"_id": 0, "userName": "$_id", "strokes": 1}},
                    {"$sort": {"strokes": -1}},
                    {"$limit": 5},
                ],
                "recent": [
                    {"$sort": {"seq": -1}},
                    {"$limit": 5},
                    {
                        "$project": {
                            "_id": 0,
                            "seq": 1,
                            "tool": 1,
                            "userName": 1,
                            "active": 1,
                            "color": "$style.color",
                        }
                    },
                ],
            }
        },
    ]


# --------------------------------------------------------------------------
# 9. Storage footprint per tool, for the scalability discussion
# --------------------------------------------------------------------------
def _storage_profile(room_id) -> list[dict]:
    return [
        {"$match": {"roomId": room_id}},
        {"$set": {"docBytes": {"$bsonSize": "$$ROOT"}}},
        {
            "$group": {
                "_id": "$tool",
                "docs": {"$sum": 1},
                "totalBytes": {"$sum": "$docBytes"},
                "avgBytes": {"$avg": "$docBytes"},
                "maxBytes": {"$max": "$docBytes"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "tool": "$_id",
                "docs": 1,
                "totalKB": {"$round": [{"$divide": ["$totalBytes", 1024]}, 1]},
                "avgBytes": {"$round": ["$avgBytes", 0]},
                "maxBytes": 1,
            }
        },
        {"$sort": {"totalKB": -1}},
    ]


REGISTRY: dict[str, Pipeline] = {
    p.key: p
    for p in [
        Pipeline(
            key="contributors",
            title="Contribution breakdown by user",
            question="Who drew how much in this room, and how often did they undo?",
            collection=STROKES,
            stages=["$match", "$group", "$project", "$sort"],
            build=_contributors,
            chart="table",
            notes="Uses $cond inside $group to count active and undone strokes in a "
            "single pass instead of issuing two queries.",
            tags=["group", "conditional"],
        ),
        Pipeline(
            key="tool_usage",
            title="Tool usage mix",
            question="Which tools dominate, and how complex is a typical stroke for each?",
            collection=STROKES,
            stages=["$match", "$group", "$project", "$sort"],
            build=_tool_usage,
            chart="bar",
            notes="$addToSet collects the distinct palette per tool; supported by "
            "the ix_stroke_tool index.",
            tags=["group", "set"],
        ),
        Pipeline(
            key="activity",
            title="Drawing activity over time",
            question="How did drawing intensity vary minute by minute?",
            collection=STROKES,
            stages=["$match", "$group", "$project", "$sort", "$limit"],
            build=_activity_timeline,
            chart="line",
            notes="$dateTrunc buckets timestamps server-side so no raw timestamps "
            "cross the wire.",
            tags=["time-series", "group"],
        ),
        Pipeline(
            key="complexity",
            title="Stroke complexity distribution",
            question="Are strokes mostly short taps or long freehand curves?",
            collection=STROKES,
            stages=["$match", "$bucket", "$project"],
            build=_complexity_buckets,
            chart="bar",
            notes="$bucket produces a histogram in the database; the equivalent in "
            "SQL needs a CASE expression per band.",
            tags=["bucket", "histogram"],
        ),
        Pipeline(
            key="palette",
            title="Colour palette in use",
            question="Which colours carry the most ink on the active canvas?",
            collection=STROKES,
            stages=["$match", "$group", "$project", "$sort", "$limit"],
            build=_color_palette,
            chart="table",
            notes="Derives an 'ink' metric by multiplying stroke width by point "
            "count inside $sum.",
            tags=["group", "computed"],
        ),
        Pipeline(
            key="bounds",
            title="Content bounding box",
            question="What canvas region actually contains drawing?",
            collection=STROKES,
            stages=["$match", "$group", "$project"],
            build=_content_bounds,
            chart="table",
            notes="$min and $max over the precomputed bbox subdocument drive the "
            "'fit to content' button without reading any point arrays.",
            tags=["group", "geometry"],
        ),
        Pipeline(
            key="leaderboard",
            title="Room leaderboard (joined)",
            question="Across all rooms, which are the busiest?",
            collection=ROOMS,
            stages=["$match", "$lookup", "$set", "$project", "$sort", "$limit"],
            build=_room_leaderboard,
            chart="table",
            notes="$lookup with a sub-pipeline aggregates strokes inside the join, "
            "demonstrating a referenced relationship without embedding.",
            tags=["lookup", "join"],
        ),
        Pipeline(
            key="dashboard",
            title="Single-request dashboard",
            question="Can the whole analytics panel load in one query?",
            collection=STROKES,
            stages=["$match", "$facet"],
            build=_dashboard,
            chart="facet",
            notes="$facet evaluates four sub-pipelines over one matched set, "
            "replacing four separate round trips to the database.",
            tags=["facet", "optimisation"],
        ),
        Pipeline(
            key="storage",
            title="Storage footprint by tool",
            question="How many bytes does each kind of stroke document cost?",
            collection=STROKES,
            stages=["$match", "$set", "$group", "$project", "$sort"],
            build=_storage_profile,
            chart="bar",
            notes="$bsonSize measures real on-disk document size, which grounds the "
            "capacity estimate for 100k strokes.",
            tags=["group", "capacity"],
        ),
    ]
}


async def run(key: str, room_id) -> list[dict]:
    spec = REGISTRY[key]
    cursor = await db()[spec.collection].aggregate(spec.build(room_id))
    return [doc async for doc in cursor]


async def explain(key: str, room_id) -> dict:
    """Ask the server how it plans to execute the pipeline (for the index demo)."""
    spec = REGISTRY[key]
    return await db().command(
        {
            "explain": {
                "aggregate": spec.collection,
                "pipeline": spec.build(room_id),
                "cursor": {},
            },
            "verbosity": "executionStats",
        }
    )


def describe(key: str) -> dict:
    spec = REGISTRY[key]
    return {
        "key": spec.key,
        "title": spec.title,
        "question": spec.question,
        "collection": spec.collection,
        "stages": spec.stages,
        "chart": spec.chart,
        "notes": spec.notes,
        "tags": spec.tags,
    }
