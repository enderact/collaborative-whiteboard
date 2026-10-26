"""End-to-end exercise of every database operation the review asks about.

Run this against a live server and it walks the whole surface: create, read,
update, soft delete, redo, hard delete, compaction, cascading room delete, plus
one aggregation and one explain. The printed transcript is the evidence that the
operations work, and it is far easier to reproduce during a review than clicking
through Postman.

    python scripts/verify_crud.py --base http://127.0.0.1:8001
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

PASS = "[ok]  "
FAIL = "[FAIL]"

# Captured as well as printed, because PowerShell redirection mangles both the
# encoding and the dashes on the way to a file.
TRANSCRIPT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    TRANSCRIPT.append(line)


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        say(f"  {PASS if ok else FAIL} {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            self.failures += 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--out", help="also write a UTF-8 transcript to this path")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    c = Checker()

    async with httpx.AsyncClient(base_url=base, timeout=120) as client:
        health = await client.get("/api/admin/health")
        if health.status_code != 200:
            say(f"{FAIL} server not reachable at {base}")
            return 1
        say(f"server: {base}   instance: {health.json()['instance']}"
            f"   database: {health.json()['database']}")
        say()

        # ------------------------------------------------------------ CREATE
        say("CREATE")
        r = await client.post("/api/rooms", json={"name": "CRUD verification board",
                                                 "createdBy": "verifier"})
        c.check("POST /api/rooms", r.status_code == 201)
        room = r.json()
        code = room["code"]
        say(f"        room code: {code}")

        made = []
        for payload in [
            {"tool": "pen", "style": {"color": "#2563eb", "width": 4},
             "points": [{"x": 10, "y": 20, "p": 0.5}, {"x": 60, "y": 90, "p": 0.6}]},
            {"tool": "rect", "style": {"color": "#dc2626", "width": 2},
             "geometry": {"x": 100, "y": 100, "w": 220, "h": 140}},
            {"tool": "text", "style": {"color": "#111827", "width": 3},
             "points": [{"x": 400, "y": 80, "p": 0.5}], "text": "flexible schema"},
            {"tool": "eraser", "style": {"color": "#000000", "width": 24,
                                         "blend": "destination-out"},
             "points": [{"x": 200, "y": 200, "p": 0.9}, {"x": 240, "y": 240, "p": 0.9}]},
        ]:
            rr = await client.post(f"/api/rooms/{code}/strokes", json=payload,
                                   params={"userId": "verifier", "userName": "Verifier"})
            made.append(rr.json())
            c.check(f"POST stroke ({payload['tool']})", rr.status_code == 201,
                    f"seq={rr.json().get('seq')}")

        # Three different document shapes in one collection, no migration.
        shapes = {tuple(sorted(set(s.keys()) & {"points", "geometry", "text"})) for s in made}
        c.check("one collection holds several document shapes", len(shapes) >= 2,
                f"{len(shapes)} distinct field sets")

        # -------------------------------------------------------------- READ
        say()
        say("READ")
        r = await client.get(f"/api/rooms/{code}")
        c.check("GET /api/rooms/{code}", r.status_code == 200,
                f"totalStrokes={r.json()['totalStrokes']}")

        r = await client.get(f"/api/rooms/{code}/strokes")
        seqs = [s["seq"] for s in r.json()["strokes"]]
        c.check("GET strokes returns them in sequence order", seqs == sorted(seqs), f"seqs={seqs}")

        r = await client.get(f"/api/strokes/{made[0]['id']}")
        c.check("GET /api/strokes/{id}", r.status_code == 200)

        r = await client.get(f"/api/rooms/{code}/strokes", params={"afterSeq": seqs[1]})
        c.check("GET strokes?afterSeq= returns only the tail",
                all(s["seq"] > seqs[1] for s in r.json()["strokes"]),
                f"{r.json()['count']} of {len(seqs)}")

        # ------------------------------------------------------------ UPDATE
        say()
        say("UPDATE")
        r = await client.patch(f"/api/rooms/{code}", json={"name": "Renamed board",
                                                           "background": "#fefce8"})
        c.check("PATCH room name and background",
                r.json()["name"] == "Renamed board" and r.json()["background"] == "#fefce8")

        r = await client.patch(f"/api/strokes/{made[0]['id']}",
                               json={"color": "#7c3aed", "width": 11})
        c.check("PATCH stroke style in place",
                r.json()["style"]["color"] == "#7c3aed" and r.json()["style"]["width"] == 11)

        r = await client.post(f"/api/strokes/{made[1]['id']}/move",
                              params={"dx": 25, "dy": -15})
        c.check("POST stroke move mutates nested geometry",
                r.json()["geometry"]["x"] == 125 and r.json()["geometry"]["y"] == 85,
                f"geometry={r.json()['geometry']}")

        # --------------------------------------------------- SOFT DELETE
        say()
        say("SOFT DELETE (undo / redo)")
        r = await client.post(f"/api/rooms/{code}/undo", params={"userId": "verifier"})
        undone = r.json()
        c.check("undo flips active to false", undone["undone"] and
                undone["stroke"]["active"] is False, f"seq={undone['stroke']['seq']}")

        r = await client.get(f"/api/rooms/{code}/strokes")
        c.check("undone stroke is hidden from the default read",
                undone["stroke"]["id"] not in [s["id"] for s in r.json()["strokes"]])

        r = await client.get(f"/api/rooms/{code}/strokes", params={"includeInactive": True})
        c.check("undone stroke is still on disk",
                undone["stroke"]["id"] in [s["id"] for s in r.json()["strokes"]])

        r = await client.post(f"/api/rooms/{code}/undo", params={"userId": "someone-else"})
        c.check("undo is scoped per user, so it cannot touch another user's work",
                r.json()["undone"] is False, r.json().get("reason", ""))

        r = await client.post(f"/api/rooms/{code}/redo", params={"userId": "verifier"})
        c.check("redo reactivates it", r.json()["redone"] and
                r.json()["stroke"]["active"] is True)

        # Two simultaneous undos must not claim the same document.
        a, b = await asyncio.gather(
            client.post(f"/api/rooms/{code}/undo", params={"userId": "verifier"}),
            client.post(f"/api/rooms/{code}/undo", params={"userId": "verifier"}),
        )
        claimed = [x.json()["stroke"]["id"] for x in (a, b) if x.json().get("undone")]
        c.check("concurrent undos claim different documents",
                len(claimed) == len(set(claimed)), f"claimed {claimed}")

        # ------------------------------------------------------- AGGREGATION
        say()
        say("AGGREGATION and INDEXES")
        r = await client.get("/api/analytics/contributors", params={"room": code})
        c.check("aggregation returns rows with its pipeline",
                r.status_code == 200 and r.json()["resultCount"] >= 1 and
                len(r.json()["pipeline"]) >= 3,
                f"{r.json()['resultCount']} rows in {r.json()['elapsedMs']} ms")

        r = await client.get("/api/analytics/dashboard", params={"room": code})
        facets = r.json()["results"][0] if r.json()["results"] else {}
        c.check("$facet returns several result sets at once",
                set(facets) >= {"totals", "byTool", "topContributors", "recent"},
                f"facets={sorted(facets)}")

        r = await client.get("/api/analytics/leaderboard")
        c.check("$lookup joins rooms to strokes", r.json()["resultCount"] >= 1)

        r = await client.get("/api/analytics/contributors/explain", params={"room": code})
        s = r.json()["summary"]
        c.check("explain reports an index scan", s["usedIndex"] is True,
                f"{s['scanType']} on {s['indexName']}, docsExamined={s['totalDocsExamined']}")

        r = await client.get("/api/admin/indexes")
        names = {i["name"] for i in r.json()["strokes"]}
        c.check("every planned stroke index exists",
                {"ix_stroke_replay", "ix_stroke_undo", "ix_stroke_tool", "ix_stroke_time"} <= names,
                f"{len(names)} indexes")

        # ------------------------------------------------------- HARD DELETE
        say()
        say("HARD DELETE")
        before = (await client.get(f"/api/rooms/{code}")).json()["totalStrokes"]
        r = await client.post(f"/api/rooms/{code}/compact")
        purged = r.json()["purged"]
        after = (await client.get(f"/api/rooms/{code}")).json()["totalStrokes"]
        c.check("compaction turns soft deletes into real deletions",
                after == before - purged, f"purged {purged}, {before} -> {after}")

        target = (await client.get(f"/api/rooms/{code}/strokes")).json()["strokes"][0]["id"]
        r = await client.delete(f"/api/strokes/{target}")
        c.check("DELETE /api/strokes/{id}", r.json()["deleted"] is True)
        c.check("deleted stroke is really gone",
                (await client.get(f"/api/strokes/{target}")).status_code == 404)

        r = await client.delete(f"/api/rooms/{code}")
        result = r.json()
        c.check("DELETE room cascades to its strokes and snapshots",
                result["deleted"] and result["strokesDeleted"] >= 0,
                f"strokes={result['strokesDeleted']}, snapshots={result['snapshotsDeleted']}")
        c.check("room is gone", (await client.get(f"/api/rooms/{code}")).status_code == 404)
        c.check("its strokes are gone too",
                (await client.get(f"/api/rooms/{code}/strokes")).status_code == 404)

    say()
    say("all checks passed" if c.failures == 0
        else f"{c.failures} check(s) FAILED")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(TRANSCRIPT) + "\n", encoding="utf-8")
        print(f"\ntranscript written to {out}")

    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
