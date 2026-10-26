"""Analytics endpoints.

Each response carries the pipeline that produced it. That is partly for the UI,
which renders the query next to its output, and partly so the design document can
be generated from the running system rather than transcribed by hand.
"""

import time

from fastapi import APIRouter, HTTPException

from app import aggregations
from app.repositories import rooms as rooms_repo
from app.util import jsonable

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
async def catalogue():
    return {"pipelines": [aggregations.describe(k) for k in aggregations.REGISTRY]}


@router.get("/{key}")
async def run_pipeline(key: str, room: str | None = None):
    if key not in aggregations.REGISTRY:
        raise HTTPException(404, f"unknown pipeline '{key}'")

    room_id = None
    if room:
        doc = await rooms_repo.get_room_by_code(room)
        if not doc:
            raise HTTPException(404, f"room {room.upper()} not found")
        room_id = doc["_id"]

    spec = aggregations.REGISTRY[key]
    started = time.perf_counter()
    results = await aggregations.run(key, room_id)
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "meta": aggregations.describe(key),
        "pipeline": jsonable(spec.build(room_id)),
        "elapsedMs": round(elapsed_ms, 2),
        "resultCount": len(results),
        "results": jsonable(results),
    }


@router.get("/{key}/explain")
async def explain_pipeline(key: str, room: str | None = None):
    """Trimmed executionStats: which index the planner chose and what it cost."""
    if key not in aggregations.REGISTRY:
        raise HTTPException(404, f"unknown pipeline '{key}'")

    room_id = None
    if room:
        doc = await rooms_repo.get_room_by_code(room)
        if not doc:
            raise HTTPException(404, "room not found")
        room_id = doc["_id"]

    raw = await aggregations.explain(key, room_id)
    return {"meta": aggregations.describe(key), "summary": summarise_explain(raw)}


def summarise_explain(raw: dict) -> dict:
    """Pull the few numbers that matter out of a very large explain document."""
    stages = raw.get("stages") or []
    cursor_stage = stages[0].get("$cursor", {}) if stages else raw
    query_planner = cursor_stage.get("queryPlanner", raw.get("queryPlanner", {}))
    exec_stats = cursor_stage.get("executionStats", raw.get("executionStats", {}))
    winning = query_planner.get("winningPlan", {})

    def find_stage(plan: dict, names: set[str]) -> dict | None:
        # An empty dict must terminate here; recursing into its missing children
        # would descend forever.
        if not isinstance(plan, dict) or not plan:
            return None
        if plan.get("stage") in names:
            return plan
        # MongoDB 7 nests the plan differently depending on whether the classic or
        # the slot-based engine won, so several child keys have to be covered.
        for child_key in ("inputStage", "queryPlan", "child", "thenStage", "elseStage"):
            found = find_stage(plan.get(child_key, {}), names)
            if found:
                return found
        for child in plan.get("inputStages", []) or []:
            found = find_stage(child, names)
            if found:
                return found
        return None

    # COUNT_SCAN and DISTINCT_SCAN are index scans that never fetch a document, so
    # a count or a distinct served entirely from index keys must not be reported as
    # an unrecognised plan.
    ixscan = find_stage(winning, {"IXSCAN", "COUNT_SCAN", "DISTINCT_SCAN"})
    collscan = find_stage(winning, {"COLLSCAN"})

    return {
        "usedIndex": ixscan is not None,
        "indexName": (ixscan or {}).get("indexName"),
        "keyPattern": (ixscan or {}).get("keyPattern"),
        "scanType": ixscan.get("stage") if ixscan else ("COLLSCAN" if collscan else "unknown"),
        "nReturned": exec_stats.get("nReturned"),
        "totalKeysExamined": exec_stats.get("totalKeysExamined"),
        "totalDocsExamined": exec_stats.get("totalDocsExamined"),
        "executionTimeMillis": exec_stats.get("executionTimeMillis"),
    }
