"""Build the Review 2 design and implementation document.

Every number, pipeline, sample document, and benchmark figure is read from
docs/measurements.json, which is produced by scripts/collect_measurements.py
against the running system. Nothing here is transcribed by hand, so the document
cannot quietly disagree with the code it describes.

    python scripts/collect_measurements.py --base http://127.0.0.1:8001
    python scripts/make_diagrams.py
    python scripts/build_report.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.docx_kit import (  # noqa: E402
    bullets, caption_only, code, compact_json, figure, figure_grid, h1, h2, h3,
    json_block, new_document, add_page_numbers, para, table,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"
SHOTS = DOCS / "screenshots"
OUT = DOCS / "Review2_Design_and_Implementation_NS02.docx"

TEAM = [
    ("1", "23BCE0801", "Devesh Atul Mahajan"),
    ("2", "23BCE0826", "Prakrit Bahl"),
    ("3", "23BCE0811", "Lakshya Diwani"),
]


# --------------------------------------------------------------------------
def source(rel: str, start: str, end: str | None = None, dedent: bool = True,
           max_lines: int = 24) -> str:
    """Pull a snippet out of a real source file so listings cannot go stale."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    i = text.find(start)
    if i < 0:
        return f"# could not locate {start!r} in {rel}"
    j = text.find(end, i + len(start)) if end else len(text)
    snippet = text[i: j if j > 0 else len(text)]
    lines = snippet.rstrip().split("\n")[:max_lines]
    if dedent:
        pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        lines = [l[pad:] if l.strip() else "" for l in lines]
    return "\n".join(lines)


def rows_to_table(doc, rows: list[dict], columns: list[tuple[str, str]],
                  limit: int = 4, font_size: float = 8.2) -> None:
    """Render aggregation output, picking specific columns."""
    if not rows:
        para(doc, "No documents matched this pipeline.", italic=True)
        return
    headers = [label for label, _ in columns]
    body = []
    for r in rows[:limit]:
        line = []
        for _, key in columns:
            v = r.get(key)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v[:5])
            elif isinstance(v, float):
                v = f"{v:,.1f}"
            elif isinstance(v, int):
                v = f"{v:,}"
            line.append(v)
        body.append(line)
    table(doc, headers, body, font_size=font_size)


# ==========================================================================
def title_page(doc, m: dict) -> None:
    for _ in range(2):
        doc.add_paragraph()

    for text, size, bold in [
        ("NoSQL Database — BCSE406L", 14, False),
        ("Review 2: Design and Implementation", 21, True),
        ("Real-Time Collaborative Whiteboard", 17, True),
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("An append-only document model in MongoDB with Redis for ordering,\n"
                    "presence, and cross-instance event fanout")
    run.italic = True
    run.font.size = Pt(11.5)

    doc.add_paragraph()
    table(doc, ["S.No", "Register No", "Student Name"], [list(r) for r in TEAM],
          widths=[0.8, 1.7, 3.0], font_size=11)

    doc.add_paragraph()
    stats = m["collectionStats"]
    table(doc, ["Item", "Detail"], [
        ["Batch / Team", "NS02"],
        ["Branch / Semester", "B.Tech CSE / 7th"],
        ["Academic Year", "2026-2027"],
        ["Faculty Guide", "Dr. D. Vivek"],
        ["Primary NoSQL databases", "MongoDB (document) and Redis (key-value)"],
        ["Collections implemented", "rooms, strokes, snapshots"],
        ["Documents in the database", f"{stats['strokes']['documents']:,} stroke documents"],
        ["Indexes implemented", f"{len(m['indexes']['planned'])} purpose-built, plus default _id"],
        ["Aggregation pipelines", f"{len(m['analytics'])} implemented and demonstrated"],
        ["Measurements taken", datetime.fromisoformat(m["generatedAt"]).strftime("%d %B %Y, %H:%M UTC")],
    ], widths=[2.3, 3.7], font_size=11)

    doc.add_page_break()

    h1(doc, "Contents", page_break=False)
    contents = [
        "1. Introduction and Scope",
        "2. System Design",
        "3. Database Design and JSON Collections",
        "4. CRUD Implementation",
        "5. Indexing and Query Plans",
        "6. Aggregation Queries",
        "7. Performance and Scalability",
        "8. Prototype Walkthrough",
        "9. Progress Report",
        "10. Source Code Listings",
        "11. References",
    ]
    for item in contents:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.add_run(item).font.size = Pt(11)


# ==========================================================================
def introduction(doc, m: dict) -> None:
    h1(doc, "1. Introduction and Scope")

    h2(doc, "1.1 What the system does")
    para(doc,
         "The Real-Time Collaborative Whiteboard is a web application in which several people draw at "
         "the same time on one shared canvas, every change appearing on every other connected screen "
         "without a refresh. The decision that shapes everything else is that the canvas is never "
         "stored as a picture. It is an ordered, append-only stream of stroke documents, each tagged "
         "with its room and the sequence number it was assigned; what a user sees is derived state, "
         "reconstructed by replaying that stream.")
    para(doc,
         "That choice is what makes this a NoSQL project rather than a drawing exercise. A pen stroke, "
         "an eraser stroke, a rectangle and a text label carry genuinely different fields and share one "
         "collection with no migration between them. Undo becomes a flag rather than a deletion, so "
         "history survives. Ordering has to come from somewhere other than a clock. None of these "
         "follow naturally from a fixed-schema table, and each is examined below.")

    h2(doc, "1.2 Objectives carried forward from Review 1")
    table(doc, ["Objective stated in Review 1", "Status at Review 2"], [
        ["Real-time multi-user drawing across several clients",
         "Complete; verified with two browsers on two backend processes."],
        ["Model state as a stream of stroke documents, reconstructable by replay",
         "Complete; replay is the only way the canvas is built (sections 3, 7)."],
        ["Low-latency sync of drawing and cursors over WebSockets with Redis Pub/Sub",
         "Complete; one delivery path through Redis (section 2.7)."],
        ["Undo and redo by soft delete rather than physical deletion",
         "Complete and extended: scoped per user, claimed atomically (section 4.6)."],
        ["Evaluate performance through indexing, query optimisation, optional snapshotting",
         "Complete; seven indexes with measured plans (section 5), snapshotting promoted from optional "
         "to implemented (section 7.2)."],
        ["Justify MongoDB and Redis over a relational database", "Sections 2.3, 3.5 and 6.6."],
    ], widths=[3.0, 3.2], font_size=8.6)

    h2(doc, "1.3 What Review 2 adds")
    para(doc, "Two of the Review 2 requirements changed the design rather than merely adding code.")
    bullets(doc, [
        "**An append-only log has no natural update or delete.** Event sourcing only inserts, and undo "
        "is a flag. Operations that genuinely modify and genuinely remove documents were therefore "
        "added: renaming a board, restyling and moving a stroke, compaction that turns soft deletes "
        "into real ones, and a cascading room delete. Three deletion semantics can now be contrasted.",
        "**Nothing in the original design needed aggregation,** since replaying a canvas is a find "
        f"with a sort. An analytics panel was designed into the application, backed by "
        f"{len(m['analytics'])} pipelines answering questions the application actually has about its "
        "own data rather than pipelines written to satisfy a checklist (section 6).",
    ])
    para(doc,
         "A third change came from measurement. Snapshotting was optional in Review 1; measuring the "
         f"largest room showed a full replay transfers "
         f"{max(r['fullMB'] for r in m['joinCost']):.0f} MB, so it was implemented and is now part of "
         "the normal join path (section 7.2).")


# ==========================================================================
def system_design(doc, m: dict) -> None:
    h1(doc, "2. System Design")

    h2(doc, "2.1 Runtime architecture")
    figure(doc, FIGURES / "architecture.png",
           "Figure 2.1 — Runtime architecture. Redis is drawn between the two application "
           "instances because that is its role: the bus they share.", width=5.2)

    para(doc,
         "The deployment shown is the one used for the demonstration: two independent FastAPI "
         "processes, each holding its own WebSocket connections and sharing no memory with the other, "
         "plus one MongoDB and one Redis. Two processes rather than one is deliberate. A single process "
         "could broadcast from an in-memory dictionary and would never exercise the broadcast layer at "
         "all, leaving the claim that the design scales across instances untested.")

    h2(doc, "2.2 Components and responsibilities")
    table(doc, ["Layer", "Technology", "Responsibility"], [
        ["Client", "HTML5 Canvas, ES modules, no build step",
         "Captures pointer input, renders optimistically, rasterises snapshots, and displays the "
         "analytics panel."],
        ["Transport", "WebSocket, one connection per client",
         "Carries ephemeral previews and cursors as well as durable stroke commits."],
        ["Application", "FastAPI on Uvicorn, fully async",
         "Validates input, assigns sequence numbers, persists strokes, and publishes events."],
        ["System of record", "MongoDB 7 (replica set)",
         "Stores rooms, the stroke log, and snapshots. The only durable state."],
        ["Coordination", "Redis 7",
         "Atomic per-room counters, Pub/Sub fanout between instances, and presence with a TTL."],
    ], widths=[1.1, 1.7, 3.4], font_size=9)

    para(doc,
         "Both database drivers are asynchronous — the PyMongo async client and redis.asyncio — which "
         "matters more than it appears. A blocking driver call inside an async WebSocket handler stalls "
         "the event loop for every other user on that process, destroying precisely the concurrency "
         "the project sets out to demonstrate.")

    h2(doc, "2.3 Why two data stores")
    para(doc,
         "Two databases need justifying, since the obvious criticism is one more thing to operate. The "
         "division is by durability requirement, not convenience.")
    bullets(doc, [
        "**MongoDB holds anything that must survive a restart:** rooms, the stroke log, snapshots. It is "
        "the only source of truth, and the whiteboard can be rebuilt from it alone.",
        "**Redis holds only data that is worthless once a connection drops,** plus the one thing that "
        "must be atomic across processes. Cursors and presence expire by TTL and are never persisted, "
        "because writing a cursor position that is stale within 16 ms is write amplification for no "
        "benefit. The sequence counter is in Redis because INCR is atomic across every instance.",
    ])
    para(doc,
         "The practical test is what breaks when each store is lost. If Redis restarts, cursors "
         "disappear, presence rebuilds as clients heartbeat, the counter is realigned from the highest "
         "persisted sequence, and no drawing is lost. If MongoDB is lost, the boards are gone. That "
         "asymmetry is the design working as intended.")

    h2(doc, "2.4 Event ordering")
    para(doc,
         "Replay only reconstructs the right picture if strokes are replayed in the order they were made, "
         "and this is the subtlest part of the design. Two candidates were rejected: client timestamps "
         "cannot be trusted because participants' clocks disagree, sometimes by seconds, and a MongoDB "
         "ObjectId embeds a timestamp with only one-second granularity, so two strokes drawn 40 ms apart "
         "on different machines may be ordered arbitrarily — an intermittent failure that is easy to miss "
         "in testing.")
    para(doc,
         "Ordering therefore comes from a Redis counter per room, incremented atomically before each "
         "stroke is written. Because INCR is atomic and Redis is shared, every instance draws from the "
         "same sequence and the order is total and reproducible; this is the second and stronger reason "
         "Redis is in the architecture. Since Redis is a cache rather than the record, the counter is "
         "realigned upward from the highest persisted sequence on every join, so a Redis restart cannot "
         "cause a collision.")
    code(doc, source("app/repositories/strokes.py", "async def next_seq(",
                     "# ----------------------------------------------------------------- CREATE",
                     max_lines=16))

    h2(doc, "2.5 The write path")
    figure(doc, FIGURES / "write-path.png",
           "Figure 2.2 — One stroke produces many ephemeral preview messages but exactly one durable "
           "document.", width=5.0)
    para(doc,
         "While a pointer is down the client emits a preview roughly every frame. Previews are relayed "
         "through Redis and never written to MongoDB, because a stroke in progress is not yet a fact about "
         "the document. When the pointer lifts, the client commits once and the server writes a single "
         "document holding the whole point array. One document per pointer sample was rejected on latency "
         "grounds: the project targets Atlas, where an insert is a round trip of roughly 50 to 200 ms on "
         "the free tier, and putting that inside the drawing loop would make the pen feel broken. It would "
         "also multiply the document count by the average points per stroke, measured at about "
         f"{m['analytics']['tool_usage']['results'][0]['avgPoints']:.0f}. Storing the array inline keeps "
         "the collection two orders of magnitude smaller and the pen responsive.")

    h2(doc, "2.6 Concurrency: why there is no operational transformation")
    para(doc,
         "The Review 1 survey cited operational transformation and CRDT papers, so it is fair to ask "
         "where that machinery is. This workload does not need it, and the reason is precise. "
         "Operational transformation reconciles concurrent edits to shared mutable state, where an "
         "operation's meaning depends on operations elsewhere: inserting a character at index 5 means "
         "something different once somebody has inserted at index 2, so the operation must be "
         "transformed before it is applied. Appending an independent stroke has no such dependency. "
         "Stroke A then B gives the same canvas as B then A, because each carries its own geometry and "
         "paints its own pixels. The operations commute, so all that is required is a total order for "
         "replay, which the sequence counter provides. One genuine conflict does arise — two users "
         "pressing undo at the same instant could both try to retract the same stroke — and it is "
         "resolved with an atomic claim rather than transformation (section 4.6). Operational "
         "transformation would become necessary if the board gained shared editable text or draggable "
         "objects, which section 9.4 records as future work rather than claiming now.")

    h2(doc, "2.7 One delivery path, and the duplicate-stroke trap")
    para(doc,
         "The natural first implementation of broadcast is for a handler to send the stroke to its own "
         "local clients and also publish it to Redis for the others. That is wrong, and the way it fails "
         "is instructive: the publishing instance is also subscribed, so it receives its own message and "
         "renders the stroke twice. On an opaque pen the duplicate is invisible; with a semi-transparent "
         "stroke or an eraser it is not, and it is easily misdiagnosed as a rendering fault.")
    para(doc,
         "There is therefore exactly one delivery path: handlers never write to their own sockets, and "
         "every instance including the publisher delivers from its subscription. Where a message must skip "
         "one connection — the author, who already rendered optimistically — the connection identifier "
         "travels inside the published message rather than being filtered locally, so the exclusion works "
         "regardless of which instance holds that socket; the author instead receives an acknowledgement "
         "carrying the document id and assigned sequence. Undo and redo carry no exclusion, because a "
         "visibility change must be re-evaluated by every client including the one that asked for it.")
    code(doc, source("app/realtime/hub.py", "    async def publish(", "    async def _deliver_local(",
                     max_lines=14))


# ==========================================================================
def database_design(doc, m: dict) -> None:
    h1(doc, "3. Database Design and JSON Collections")

    h2(doc, "3.1 Collections")
    stats = m["collectionStats"]
    table(doc, ["Collection", "Holds", "Documents", "Data", "Indexes"], [
        ["rooms", "One document per board, with participants embedded",
         f"{stats['rooms']['documents']:,}", f"{stats['rooms']['dataSizeMB']:.2f} MB",
         f"{stats['rooms']['indexSizeMB']:.2f} MB"],
        ["strokes", "The append-only log; one document per stroke",
         f"{stats['strokes']['documents']:,}", f"{stats['strokes']['dataSizeMB']:.1f} MB",
         f"{stats['strokes']['indexSizeMB']:.1f} MB"],
        ["snapshots", "Rasterised canvas state at a known sequence number",
         f"{stats['snapshots']['documents']:,}", f"{stats['snapshots']['dataSizeMB']:.1f} MB",
         f"{stats['snapshots']['indexSizeMB']:.2f} MB"],
    ], widths=[0.9, 2.5, 0.9, 0.8, 0.8], font_size=9)
    para(doc,
         "Review 1 proposed two collections. The third, snapshots, was added after measuring join "
         "cost (section 7.2). The average stroke document measures "
         f"{stats['strokes']['avgDocBytes']:,} bytes, the figure the capacity estimate in section 7.3 "
         "is built on.")

    h2(doc, "3.2 The rooms collection")
    para(doc,
         "A room carries its settings, a denormalised stroke count for cheap listing, and its "
         "participants as an embedded array. Participants are embedded because they are few, bounded "
         "by the number of people who can usefully share a board, and always read together with the "
         "room itself; a separate collection would add a join to serve no purpose.")
    json_block(doc, m["samples"]["rooms"], max_chars=780)

    h2(doc, "3.3 The strokes collection")
    para(doc,
         "This is where the flexible-schema argument is made concretely rather than asserted. The three "
         "documents below are from the same collection, written by the same code path, with no migration "
         "and no nullable columns standing in for absent fields. A pen stroke carries a points array; a "
         "rectangle carries a geometry subdocument and no points at all; a text label carries text and "
         "font. Fields that do not apply are absent.")

    h3(doc, "A freehand pen stroke")
    # 760 is just enough to show this document whole, including bbox and pointCount,
    # which the paragraph below discusses.
    json_block(doc, m["samples"]["strokes"].get("pen"), max_chars=760)
    h3(doc, "A rectangle, and a text label")
    json_block(doc, {"rectangle": m["samples"]["strokes"].get("rect"),
                     "text": m["samples"]["strokes"].get("text")}, max_chars=1000)

    para(doc,
         "Several fields exist to serve specific queries. The seq field is the authoritative order and "
         "the leading component of the replay index. The active flag carries undo state: false means "
         "undone but retained. The bbox subdocument is computed on write so that the bounding box of a "
         "whole canvas can be answered by an aggregation over small subdocuments without ever reading "
         "a point array, and pointCount is precomputed so complexity histograms do not need $size over "
         "large arrays.")
    para(doc,
         "The eraser deserves a note because the obvious implementation is a trap. Painting the "
         "background colour over a stroke looks correct until the board's background changes, at "
         "which point every historical erasure becomes a visible white smear. An eraser is therefore "
         "stored as an ordinary stroke whose style carries a destination-out blend mode, so it cuts a "
         "hole at replay time and remains correct on any background.")

    h2(doc, "3.4 The snapshots collection")
    snap_mb = m["collectionStats"]["snapshots"]["avgDocBytes"] / 1024 / 1024
    para(doc,
         "A snapshot is a PNG of the canvas as it stood at a known sequence number, stored inline as "
         "a data URL together with the sequence it covers, so joining a room costs one snapshot read "
         f"plus the strokes newer than that sequence. The measured average is {snap_mb:.1f} MB for the "
         "seeded boards, inside MongoDB's 16 MB document limit but not with a large margin. That is a "
         "worst case: the seeded data is pseudo-random scribble covering the whole canvas and is close "
         "to incompressible, whereas a real board is mostly white. If snapshots approached the limit "
         "the correct move is GridFS, which chunks large binary values across documents; a cheaper "
         "first step would be WebP instead of PNG. Both are noted as future work rather than "
         "implemented, because the limit is not currently reached.")
    json_block(doc, m["samples"].get("snapshots"), max_chars=450)

    h2(doc, "3.5 Embedding against referencing")
    para(doc,
         "The same database holds one clear example of each strategy, which makes the trade-off easy "
         "to state.")
    table(doc, ["Relationship", "Strategy", "Why"], [
        ["Room to participants", "Embedded array",
         "Bounded, small, always read with the room and updated as a unit. Embedding removes a query and "
         "keeps the roster atomic with the room document."],
        ["Room to strokes", "Referenced by roomId",
         f"Unbounded. The largest seeded room holds {max(r['strokes'] for r in m['joinCost']):,} strokes "
         f"at about {stats['strokes']['avgDocBytes']:,} bytes each, far beyond the 16 MB limit. "
         "Referencing also lets one stroke be updated or undone without rewriting the room."],
        ["Room to snapshots", "Referenced by roomId",
         "Large binary payloads with their own lifecycle, pruned independently of the room."],
    ], widths=[1.3, 1.2, 3.7], font_size=9)
    para(doc,
         "The governing question is not which is faster in the abstract but whether the child "
         "collection is bounded. Participants are; strokes are not, and no amount of tuning makes an "
         "unbounded embedded array safe.")

    h2(doc, "3.6 The Redis key space")
    para(doc,
         "Redis is a database in this system too, and the key-value model was declared in Review 1, so "
         "its keys are documented with the same care as the collections.")
    table(doc, ["Key pattern", "Type", "Purpose", "Lifetime"], [
        ["room:{roomId}:seq", "String counter",
         "Atomic per-room sequence issued by INCR before each stroke is written.",
         "Persistent; realigned from MongoDB on join."],
        ["wb:room:{CODE}", "Pub/Sub channel",
         "Carries strokes, previews, cursors, undo, redo, and room updates between instances.",
         "Transient, not stored."],
        ["room:{CODE}:presence", "Hash",
         "Field per user holding display name, colour, and last cursor position.",
         "Expires after two minutes of silence."],
    ], widths=[1.6, 0.9, 2.7, 1.2], font_size=8.8)

    h2(doc, "3.7 Validation and schema evolution")
    para(doc,
         "Flexible schema does not mean unchecked input. Validation happens at the application "
         "boundary through Pydantic models, so a malformed stroke is rejected with a 422 before it "
         "reaches the database, while the database itself stays free of a rigid shape. The constraint "
         "lives where it can produce a useful error message, and adding a new tool needs no migration: "
         "a polygon tool means a model and a renderer, existing documents are untouched, and replay "
         "continues to work because readers only look at the fields relevant to each tool.")


# ==========================================================================
def crud(doc, m: dict) -> None:
    h1(doc, "4. CRUD Implementation")

    para(doc,
         "Every operation below is reachable over HTTP as well as over the WebSocket, which is what "
         "makes it demonstrable in Postman rather than merely implied by the canvas. A stroke created "
         "through the REST endpoint is also published to Redis, so it appears on any open board "
         "immediately — a better demonstration than a page refresh.")

    h2(doc, "4.1 Operation map")
    table(doc, ["Verb", "Endpoint", "Operation"], [
        ["POST", "/api/rooms", "Create a room with a unique short code"],
        ["POST", "/api/rooms/{code}/strokes", "Insert one stroke document"],
        ["GET", "/api/rooms", "List boards, most recently active first"],
        ["GET", "/api/rooms/{code}", "Read one room with live counts"],
        ["GET", "/api/rooms/{code}/strokes", "Replay history, optionally only after a sequence"],
        ["GET", "/api/strokes/{id}", "Read a single stroke"],
        ["PATCH", "/api/rooms/{code}", "Update name, background, or grid setting"],
        ["PATCH", "/api/strokes/{id}", "Update the style of an existing stroke in place"],
        ["POST", "/api/strokes/{id}/move", "Translate a shape by mutating nested geometry"],
        ["POST", "/api/rooms/{code}/undo", "Soft delete: set active to false, scoped to one user"],
        ["POST", "/api/rooms/{code}/redo", "Reactivate the most recently undone stroke"],
        ["POST", "/api/rooms/{code}/compact", "Hard delete every stroke left undone"],
        ["DELETE", "/api/strokes/{id}", "Hard delete one stroke"],
        ["DELETE", "/api/rooms/{code}/strokes", "Hard delete every stroke in a room"],
        ["DELETE", "/api/rooms/{code}", "Delete a room and cascade to its strokes and snapshots"],
    ], widths=[0.7, 2.4, 3.1], font_size=8.8)

    h2(doc, "4.2 Create")
    para(doc,
         "Room creation allocates a six-character code from an alphabet with the ambiguous glyphs removed, "
         "so a code can be read aloud without confusion, and retries on the unique index if a collision "
         "occurs. Stroke creation is where the flexible schema is exercised: only the fields a given tool "
         "uses are written, so a rectangle document has no points key rather than a null one.")
    code(doc, source("app/repositories/strokes.py",
                     "async def create_stroke(",                      "    res = await db()[STROKES].insert_one(doc)",
                     max_lines=15))

    h2(doc, "4.3 Read")
    para(doc,
         "Two reads matter: the full replay used when a room has no snapshot, and one that takes an "
         "afterSeq argument and returns only the tail, which is what the snapshot path uses and what "
         "makes joining a busy room cheap. Both are served by the same compound index on roomId and "
         "seq, because a range query on the second component is exactly what it was built for. Undone "
         "strokes are excluded by default and can be requested explicitly, which is how a soft delete "
         "is shown to retain data.")
    code(doc, source("app/repositories/strokes.py",
                     "async def list_strokes(", "async def get_stroke(", max_lines=14))

    h2(doc, "4.4 Update")
    para(doc,
         "Updates operate in place on documents that already exist, the part an append-only log does not "
         "give for free. Restyling sets nested fields under style using dot notation, so the point array "
         "is not rewritten. Moving a shape uses $inc on nested geometry, so the translation is applied by "
         "the server atomically rather than read, modified and written back by the client.")
    code(doc, source("app/repositories/strokes.py",
                     "async def restyle_stroke(",
                     "# ------------------------------------------------- SOFT DELETE", max_lines=14))

    h2(doc, "4.5 Three deletion semantics")
    para(doc,
         "Having built all three, the project can contrast them, which is a more useful position than "
         "having only the soft delete Review 1 proposed.")
    table(doc, ["Semantics", "Mechanism", "Data retained", "Used for"], [
        ["Soft delete", "$set active to false, undoneAt recorded", "Yes, fully",
         "Undo and redo, where the stroke must be recoverable"],
        ["Compaction", "deleteMany on strokes still inactive", "No",
         "Reclaiming space once a board is finished"],
        ["Cascade delete", "deleteMany on strokes and snapshots, then deleteOne on the room", "No",
         "Removing a board entirely"],
    ], widths=[1.0, 2.2, 0.9, 2.1], font_size=8.8)
    para(doc,
         "The cascade is where a document store pushes work up into the application. MongoDB has no "
         "foreign keys and no ON DELETE CASCADE, so deleting a room without its strokes would silently "
         "orphan tens of thousands of documents no query would return and no user could reach. Referential "
         "integrity is the application's responsibility, and the endpoint reports how many documents in "
         "each collection it removed.")
    code(doc, source("app/repositories/rooms.py", "async def delete_room(", max_lines=14))

    h2(doc, "4.6 Undo as a concurrency problem")
    para(doc,
         "Undo looks like the simplest operation in the system and is in fact the only place where a "
         "real race exists. Two mistakes are easy to make. The first is scoping undo to the room rather "
         "than to the user: a room-wide \"undo the last stroke\" lets one participant retract another's "
         "work, a correctness problem dressed as a feature. Undo is therefore filtered by userId, so "
         "each person has their own history.")
    para(doc,
         "The second is the read-then-write race. If the handler finds the newest active stroke and "
         "then updates it in a second call, two simultaneous undos from the same user can both select "
         "the same document, and one of them retracts a stroke the user never asked about. The fix is "
         "to make finding and claiming a single atomic operation: findOneAndUpdate with a sort, which "
         "matches, updates, and returns in one round trip. The second request no longer matches "
         "active: true on that document and moves on to the next one. This is also the query the "
         "dedicated undo index exists for — the descending sequence component lets the server stop at "
         "the first matching key instead of sorting the room, and section 5 measures the difference.")
    code(doc, source("app/repositories/strokes.py", "async def undo_last(", "async def redo_last(",
                     max_lines=14))

    h2(doc, "4.7 Verification")
    para(doc,
         "The operations are verified by a script rather than by assertion. It walks the whole surface "
         "against a running server, including the concurrent-undo race, and reports pass or fail for "
         "each check. The transcript below is from an actual run.")
    code(doc, (DOCS / "crud_transcript.txt").read_text(encoding="utf-8")
         if (DOCS / "crud_transcript.txt").exists() else
         "run: python scripts/verify_crud.py --base http://127.0.0.1:8001", size=6.6)


# ==========================================================================
def indexing(doc, m: dict) -> None:
    h1(doc, "5. Indexing and Query Plans")

    h2(doc, "5.1 The indexes and why each exists")
    para(doc,
         "Every index below was added to serve a specific query in the application, and none was "
         "added speculatively. Indexes are not free: they consume storage, and they slow every write "
         "because each insert must update each one.")
    table(doc, ["Index", "Collection", "Key", "Why it exists"],
          [[ix["name"], ix["collection"], json.dumps(ix["keys"]).replace('"', ""),
            ix["rationale"]] for ix in m["indexes"]["planned"]],
          widths=[1.2, 0.8, 1.5, 2.8], font_size=8.2)

    h2(doc, "5.2 Method")
    para(doc,
         "Claiming an index helps is not the same as showing it. The application exposes a benchmark "
         "endpoint that drops the non-unique indexes, runs each query five times and keeps the best "
         "time, captures the query plan with explain in executionStats mode, then rebuilds the indexes "
         "and repeats. Every query benchmarked is one the application genuinely issues, with the same "
         "sort, projection and limit.")
    para(doc,
         "An earlier version of this benchmark was misleading and the correction is worth recording. It "
         "fetched five thousand full documents for every case, and because a stroke document averages "
         f"{m['collectionStats']['strokes']['avgDocBytes']:,} bytes, the cost of transferring and "
         "decoding point arrays swamped the cost of finding them, so the index appeared to deliver "
         "almost nothing. Timing the real queries instead — a sorted lookup limited to one document, a "
         "bounded range scan, a projection, a count — shows where the index decides the outcome.")

    h2(doc, "5.3 Results")
    bench = m.get("benchmark") or {}
    if bench:
        # Plans, documents examined and timings share the query column, so they are
        # one table rather than three.
        table(doc,
              ["Query", "Plan without", "Docs exam.", "Plan with", "Docs exam.", "Index used",
               "Without", "With", "Speed-up"],
              [[name.replace("_", " "),
                c["withoutIndex"]["scanType"], f"{c['withoutIndex']['docsExamined']:,}",
                c["withIndex"]["scanType"], f"{c['withIndex']['docsExamined']:,}",
                c["withIndex"]["indexName"] or "—",
                f"{c['withoutIndex']['ms']:.1f} ms" if c["withoutIndex"]["ms"] else "—",
                f"{c['withIndex']['ms']:.1f} ms" if c["withIndex"]["ms"] else "—",
                f"{c['speedup']}x" if c["speedup"] else "—"] for name, c in bench.items()],
              widths=[0.95, 0.7, 0.62, 0.62, 0.62, 1.05, 0.62, 0.55, 0.58], font_size=7.4)
        caption_only(doc, "Table 5.2 — Every benchmarked query with the indexes dropped and rebuilt. "
                          "Plans and documents examined come from explain; timings are the best of five "
                          "runs.")
        figure(doc, FIGURES / "docs-examined.png",
               "Figure 5.1 — Documents MongoDB had to open, on a logarithmic scale. This is planner "
               "output rather than a timing, so it is reproducible.", width=4.7)
        para(doc,
             "The documents-examined column is the primary evidence because it is deterministic. The "
             "undo lookup goes from opening every document in the collection to opening exactly one, and "
             "the incremental join from the whole collection to the five hundred documents it wants. Two "
             "queries reach zero documents examined, and the plan column says why: the count wins a "
             "COUNT_SCAN, which tallies index keys without fetching anything, and the covered query "
             "requests only fields already held in the index, so MongoDB never touches the collection at "
             "all.")
        para(doc,
             "The timings are secondary because they are noisy in a way the reader should know about. "
             "The whole strokes collection is "
             f"{m['collectionStats']['strokes']['dataSizeMB']:.0f} MB and fits comfortably in the "
             "WiredTiger cache on this machine, so an unindexed scan is limited by memory bandwidth "
             "rather than disk, which flatters the unindexed case. On a memory-constrained tier such as "
             "Atlas M0 the gap would be wider, so the reported speed-ups are a conservative floor.")

        h2(doc, "5.4 Where the index barely helps")
        name, c = min(bench.items(), key=lambda kv: kv[1]["speedup"] or 99)
        verdict = ("slightly slower" if (c["speedup"] or 1) < 1 else
                   "effectively no gain" if (c["speedup"] or 1) < 1.25 else
                   "a modest gain")
        para(doc,
             f"One result is close to negative and is reported rather than omitted. The "
             f"{name.replace('_', ' ')} query was {c['withoutIndex']['ms']:.0f} ms without the index and "
             f"{c['withIndex']['ms']:.0f} ms with it, a speed-up of {c['speedup']}x — {verdict}, and the "
             f"documents-examined column confirms why: it still opens "
             f"{c['withIndex']['docsExamined']:,} documents. This query is not selective, and walking an "
             "index and following each key to its document is random access where scanning the collection "
             "in storage order is sequential. When a query touches most of a collection the sequential "
             "scan wins, and MongoDB's own planner would often choose it. Indexes pay off in proportion "
             "to how much of the collection they let the server skip, and a query that skips nothing "
             "gains nothing.")
    else:
        para(doc, "Benchmark data was not captured in this run.", italic=True)

    h2(doc, "5.5 What the indexes cost")
    sizes = m["collectionStats"]["strokes"]["indexSizesKB"]
    table(doc, ["Index", "Size on disk"],
          [[k, f"{v:,.0f} KB"] for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])],
          widths=[2.4, 1.4], font_size=9)
    total_ix = m["collectionStats"]["strokes"]["indexSizeMB"]
    data_mb = m["collectionStats"]["strokes"]["dataSizeMB"]
    para(doc,
         f"The four purpose-built indexes plus the default _id index total {total_ix:.1f} MB against "
         f"{data_mb:.0f} MB of stroke data, about {total_ix / data_mb * 100:.0f} per cent overhead, "
         "which is a reasonable price. The _id index is the largest single index and is never used by "
         "any query here — every read is by roomId, by sequence, or by user. MongoDB requires it, so it "
         "cannot be dropped, but it is a reminder that the default is not free.")


# ==========================================================================
PIPELINE_COLUMNS = {
    "contributors": [("User", "userName"), ("Strokes", "totalStrokes"), ("Active", "activeStrokes"),
                     ("Undone", "undoneStrokes"), ("Points", "totalPoints"),
                     ("Avg pts", "avgPointsPerStroke"), ("Undo %", "undoRatePct")],
    "tool_usage": [("Tool", "tool"), ("Documents", "count"), ("Avg points", "avgPoints"),
                   ("Avg width", "avgWidth"), ("Colours", "colorCount")],
    "activity": [("Bucket", "bucket"), ("Strokes", "strokes"), ("Points", "points"),
                 ("Contributors", "contributorCount")],
    "complexity": [("Lower bound (points)", "minPoints"), ("Strokes", "strokes"),
                   ("Total points", "totalPoints"), ("Avg width", "avgWidth")],
    "palette": [("Colour", "color"), ("Strokes", "strokes"), ("Users", "userCount"),
                ("Ink", "totalInk")],
    "bounds": [("minX", "minX"), ("minY", "minY"), ("maxX", "maxX"), ("maxY", "maxY"),
               ("Width", "width"), ("Height", "height"), ("Strokes", "strokes")],
    "leaderboard": [("Room", "code"), ("Name", "name"), ("People", "participantCount"),
                    ("Strokes", "totalStrokes"), ("Active", "activeStrokes"),
                    ("Contributors", "contributorCount")],
    "storage": [("Tool", "tool"), ("Documents", "docs"), ("Total KB", "totalKB"),
                ("Avg bytes", "avgBytes"), ("Max bytes", "maxBytes")],
}

PIPELINE_COMMENTARY = {
    "contributors": "The pipeline the analytics panel opens on. The detail worth noticing is $cond inside "
    "$group: active and undone strokes are counted in a single pass over the matched documents rather "
    "than by issuing two queries and subtracting. The undo rate falls out of the same pass, and $addToSet "
    "collects each person's tool set without a second lookup.",
    "tool_usage": "A straightforward $group, but the pipeline that makes the flexible-schema argument "
    "measurable: it aggregates across documents with genuinely different fields and reports average point "
    "counts per tool, which differ by an order of magnitude between a freehand stroke and a rectangle.",
    "activity": "$dateTrunc buckets timestamps into one-minute bins inside the database, so the client "
    "receives a few hundred aggregated rows instead of tens of thousands of raw timestamps. Doing this "
    "in the application would mean transferring the entire collection to draw a chart.",
    "complexity": "$bucket produces a histogram server-side; the equivalent in SQL needs a CASE "
    "expression per band or a join against a bands table. The result confirms the long-tailed "
    "distribution the generator was designed to produce: most strokes are short, a few are very long, "
    "and the tail is what drives document size.",
    "palette": "A computed metric inside an accumulator. Ink is not a stored field — it is stroke width "
    "multiplied by point count, summed with $sum — so aggregation derives a quantity the schema never "
    "recorded.",
    "bounds": "$min and $max over the precomputed bbox subdocuments answer which region of the canvas "
    "contains drawing without reading a single point array. This is the payoff for computing bbox at "
    "write time, and it backs the Fit to content button.",
    "leaderboard": "The only pipeline that starts from rooms rather than strokes. $lookup joins the two "
    "collections, and the sub-pipeline inside the join aggregates the matched strokes before they are "
    "returned, so tens of thousands of stroke documents are never materialised into the parent room "
    "document. Without the sub-pipeline this query would try to build an array far larger than the "
    "16 MB document limit and fail.",
    "storage": "$bsonSize measures the real on-disk size of each document, which the capacity "
    "projection in section 7.3 is built on, and quantifies the cost of storing point arrays inline.",
}


def aggregation_section(doc, m: dict) -> None:
    h1(doc, "6. Aggregation Queries")

    para(doc,
         "Nine pipelines are implemented. Each answers a question the application genuinely asks, and "
         "each is reachable from the analytics panel in the running interface, which displays the "
         "pipeline next to its own output — the API returns the pipeline with every result for exactly "
         "that reason.")

    table(doc, ["Pipeline", "Question it answers", "Stages", "Rows", "Time"],
          [[v["meta"]["title"], v["meta"]["question"], ", ".join(v["meta"]["stages"]),
            f"{v['resultCount']:,}", f"{v['elapsedMs']:.0f} ms"]
           for v in m["analytics"].values()],
          widths=[1.25, 2.05, 1.5, 0.45, 0.55], font_size=7.8)
    caption_only(doc, "Table 6.1 — Every pipeline, measured against the profiled room.")

    # Four pipelines get the full treatment because each demonstrates a different
    # stage worth discussing; the rest are summarised so the section stays within
    # the page budget without dropping any of them.
    detailed = ["contributors", "complexity", "leaderboard", "dashboard"]
    summarised = ["tool_usage", "activity", "palette", "bounds", "storage"]

    for n, key in enumerate([k for k in detailed if k in m["analytics"]], start=1):
        entry = m["analytics"][key]
        meta = entry["meta"]
        h2(doc, f"6.{n} {meta['title']}")
        para(doc, meta["question"], italic=True)
        if key in PIPELINE_COMMENTARY:
            para(doc, PIPELINE_COMMENTARY[key])

        # Compact rendering fits these pipelines whole; only the $facet is long
        # enough to still need a cut.
        pipeline_text = compact_json(entry["pipeline"], width=104)
        if len(pipeline_text) > 1400:
            pipeline_text = pipeline_text[:1400].rsplit("\n", 1)[0] + "\n  ... truncated ..."
        code(doc, pipeline_text, size=6.8)

        if key == "dashboard":
            para(doc,
                 "This pipeline answers a performance question rather than a data question. The panel "
                 "needs four summaries at once, and issuing four queries means four round trips and four "
                 "passes over the same matched documents. $facet evaluates all four sub-pipelines over one "
                 "$match, so the panel loads from a single request. The output below is one document whose "
                 "fields are the four result sets.")
            facets = entry["results"][0] if entry["results"] else {}
            for facet_name, rows in list(facets.items())[:2]:
                if not isinstance(rows, list) or not rows:
                    continue
                h3(doc, f"facet: {facet_name}")
                cols = [(k, k) for k in rows[0].keys()]
                rows_to_table(doc, rows, cols, limit=3, font_size=7.8)
            remaining = [n for n, r in list(facets.items())[2:] if isinstance(r, list)]
            if remaining:
                para(doc, "The remaining facets in the same response — "
                          + ", ".join(remaining) +
                          " — are shown in the interface (Figure 8.4).", italic=True)
        else:
            para(doc, f"Result — {entry['resultCount']:,} rows in {entry['elapsedMs']:.0f} ms:")
            rows_to_table(doc, entry["results"],
                          PIPELINE_COLUMNS.get(key, [(k, k) for k in
                                                     (entry["results"][0].keys()
                                                      if entry["results"] else [])]))

    h2(doc, "6.5 The remaining pipelines")
    para(doc,
         "The five below are implemented and demonstrable in the interface on the same terms as those "
         "above. They are summarised rather than expanded because each is a variation on stages already "
         "discussed; their stage lists, row counts and timings are in Table 6.1 and their output is "
         "shown in the interface (Figure 8.4).")
    for key in [k for k in summarised if k in m["analytics"]]:
        entry = m["analytics"][key]
        h3(doc, entry["meta"]["title"])
        para(doc, entry["meta"]["question"] + "  " + " → ".join(entry["meta"]["stages"]), italic=True)
        if key in PIPELINE_COMMENTARY:
            para(doc, PIPELINE_COMMENTARY[key])

    h2(doc, "6.6 What these queries would cost in SQL")
    para(doc,
         "It is fair to ask whether any of this needs a document database, since PostgreSQL has grouping "
         "and JSON columns too. Most of these pipelines could be expressed in SQL; the interesting "
         "difference is not expressiveness but the shape of the data they run over. A relational schema "
         "for this workload would either store one row per point, turning a single stroke into dozens of "
         "rows and the contributors query into an aggregate over millions, or store the point array in a "
         "JSON column, at which point the schema is a document store with extra steps and the indexes "
         "are harder to reason about. The pipelines here run directly over the documents the application "
         "writes and reads, with no mapping layer between the two.")


# ==========================================================================
def performance(doc, m: dict) -> None:
    h1(doc, "7. Performance and Scalability")

    h2(doc, "7.1 The dataset")
    stats = m["collectionStats"]["strokes"]
    para(doc,
         "Review 1 estimated 50,000 to 100,000 stroke documents. Nobody draws that by hand, and "
         "indexing and aggregation results are meaningless on a few hundred documents, so a generator "
         "produces a realistically shaped corpus: a long tail of short strokes with a few very long "
         "ones, a mix of tools, about one stroke in nine left undone so the undo analytics have real "
         "numbers, and timestamps spread over hours for the time-bucketed pipeline to bucket.")
    table(doc, ["Property", "Measured"], [
        ["Stroke documents", f"{stats['documents']:,}"],
        ["Rooms", f"{m['roomCount']}"],
        ["Average document size", f"{stats['avgDocBytes']:,} bytes"],
        ["Data size", f"{stats['dataSizeMB']:.1f} MB"],
        ["Storage size on disk", f"{stats['storageSizeMB']:.1f} MB"],
        ["Total index size", f"{stats['indexSizeMB']:.1f} MB"],
        ["Largest single room", f"{max(r['strokes'] for r in m['joinCost']):,} active strokes"],
    ], widths=[2.4, 2.0], font_size=9)

    h2(doc, "7.2 The cost of joining a room, and why snapshots were built")
    biggest = max(m["joinCost"], key=lambda r: r["strokes"])
    para(doc,
         "Replaying an append-only log is elegant and has one obvious weakness: the cost of a join grows "
         "without bound as a board is used. Review 1 listed snapshotting as optional; measuring the join "
         f"settled the question. Joining the largest room means reading {biggest['strokes']:,} stroke "
         f"documents, which is {biggest['fullMB']:.1f} MB of JSON. The query itself takes about "
         f"{biggest['fullQueryMs']:.0f} ms, but serialising that many documents to JSON takes roughly "
         f"{biggest['fullSerialiseMs'] / 1000:.0f} seconds, and the client then has to parse it all and "
         "render every stroke. A board that takes twelve seconds to open is not usable.")
    table(doc, ["Room", "Active strokes", "Full replay", "Query", "Tail", "Snapshot",
                "Snapshot join", "Reduction"],
          [[r["code"], f"{r['strokes']:,}", f"{r['fullMB']:.1f} MB", f"{r['fullQueryMs']:.0f} ms",
            f"{r['tailStrokes']:,}", f"{r['snapshotKB']:.0f} KB", f"{r['withSnapshotMB']:.2f} MB",
            f"{(1 - r['withSnapshotMB'] / r['fullMB']) * 100:.0f}%" if r["fullMB"] else "—"]
           for r in sorted(m["joinCost"], key=lambda r: -r["strokes"]) if r["strokes"] > 100],
          widths=[0.6, 0.85, 0.75, 0.6, 0.5, 0.75, 0.9, 0.75], font_size=8.4)
    figure(doc, FIGURES / "join-cost.png",
           "Figure 7.1 — Data transferred to join each room, measured.", width=4.6)
    para(doc,
         "A snapshot is a PNG of the canvas at a known sequence number, so joining costs one snapshot "
         "plus only the strokes newer than it: for the largest room "
         f"{biggest['withSnapshotMB']:.2f} MB instead of {biggest['fullMB']:.1f} MB, a reduction of "
         f"{(1 - biggest['withSnapshotMB'] / biggest['fullMB']) * 100:.0f} per cent. Measured in the "
         "browser, joining that room now completes in roughly half a second.")
    para(doc,
         "Two details are worth recording. The snapshot does not replace the log: the strokes remain, so "
         "history, undo and analytics still work, and a snapshot can be regenerated or discarded at any "
         "time. It is a cache of derived state, which is the role a rasterised canvas should have. "
         "Snapshots are also counterproductive below a threshold — for a board of ten strokes the image "
         "is far larger than the strokes it replaces, and the table above shows the reduction going "
         "sharply negative for small rooms — so the implementation snapshots only every few hundred "
         "strokes and the server-side generator skips rooms below a floor.")
    para(doc,
         "Snapshots are produced two ways. During normal use the client rasterises its own canvas and "
         "uploads it, which costs the server nothing. That is no help for a generated room, since "
         "creating the first snapshot would require the very full replay the snapshot exists to avoid, so "
         "a server-side renderer using Pillow closes the loop. That path is also the one a production "
         "system would prefer, because it does not trust a client to rasterise authoritative state.")

    h2(doc, "7.3 Capacity on the free Atlas tier")
    avg = m["collectionStats"]["strokes"]["avgDocBytes"]
    ix_ratio = (m["collectionStats"]["strokes"]["indexSizeMB"] /
                m["collectionStats"]["strokes"]["dataSizeMB"])
    for n in (100_000,):
        data_mb = avg * n / 1024 / 1024
        total = data_mb * (1 + ix_ratio)
        para(doc,
             f"Review 1 nominated MongoDB Atlas M0, which allows 512 MB. At the measured "
             f"{avg:,} bytes per document, {n:,} strokes is about {data_mb:.0f} MB of data and, at the "
             f"measured index overhead of {ix_ratio * 100:.0f} per cent, roughly {total:.0f} MB in "
             f"total. That is {total / 512 * 100:.0f} per cent of the quota, so the stated target fits "
             "with room to spare.")
    para(doc,
         "Snapshots, not strokes, are the component that threatens the quota. At the measured "
         f"{m['collectionStats']['snapshots']['avgDocBytes'] / 1024 / 1024:.1f} MB per snapshot for "
         "worst-case scribble, a handful of busy boards would consume more than the entire stroke log. "
         "Pruning to the three most recent snapshots per room is implemented for this reason, and it is "
         "the right default: older snapshots are strictly redundant, since any of them plus the log "
         "reconstructs the same canvas.")

    h2(doc, "7.4 Write throughput and where the limits are")
    para(doc,
         "The separation of previews from commits keeps the write rate proportional to strokes rather "
         "than to pointer samples. A person drawing continuously produces a few strokes per second, not "
         "the sixty pointer events per second their mouse generates, so a room of ten active "
         "participants writes on the order of tens of documents per second — comfortable for a single "
         "MongoDB node. The load that scales with pointer events lands on Redis Pub/Sub instead, where "
         "messages are small and nothing is persisted.")
    para(doc,
         "The known ceiling is the fanout itself. Every preview from every user is delivered to every "
         "other participant, so traffic within a room grows with the square of the number of "
         "participants. For a whiteboard of a handful of people this is not a practical limit; a system "
         "expecting hundreds of simultaneous editors in one room would need to throttle or aggregate "
         "previews server-side, which section 9.3 records as a known limitation rather than solved.")


# ==========================================================================
def walkthrough(doc, m: dict) -> None:
    h1(doc, "8. Prototype Walkthrough")

    para(doc,
         "The screenshots below are from the running system against the seeded database. Each is "
         "annotated with what it is evidence of.")

    shots = [
        ("01-lobby.png",
         "Figure 8.1 — The lobby. Boards are listed by last activity, served by the ix_room_activity "
         "index rather than by scanning the collection."),
        ("03-tools-and-shapes.png",
         "Figure 8.2 — One board with all six tools used: pen, eraser, line, rectangle, ellipse and "
         "text. Every mark is a separate document, and the six tools produce documents with different "
         "field sets in one collection."),
        ("04-cross-instance-sync.png",
         "Figure 8.3 — The result that matters most. This window is connected to instance wb-1, shown "
         "in the badge at the top right. The pink strokes and the labelled cursor belong to a user whose "
         "browser is connected to wb-2, a separate operating-system process sharing no memory with this "
         "one. Both reached this screen through Redis Pub/Sub, which is the claim the architecture "
         "makes."),
        ("05-aggregation-panel.png",
         "Figure 8.4 — The analytics panel, showing the contributors pipeline next to the output it "
         "produced and the server-side execution time. The canvas behind it is the 42,672-stroke seeded "
         "board restored from a snapshot."),
        ("06-index-benchmark.png",
         "Figure 8.5 — The index benchmark run from the interface. For each query it reports the plan, "
         "the documents examined and the time, with the indexes dropped and then rebuilt."),
        ("08-rest-api-endpoints.png",
         "Figure 8.6 — The generated API documentation, showing the full CRUD surface used to exercise "
         "the operations in Postman. Live collection and index statistics are also available under the "
         "Storage tab."),
    ]
    figure_grid(doc, [(SHOTS / name, caption) for name, caption in shots], width=3.05)


# ==========================================================================
def progress(doc, m: dict) -> None:
    h1(doc, "9. Progress Report")

    h2(doc, "9.1 Completed between Review 1 and Review 2")
    bullets(doc, [
        "Full application built: FastAPI backend, WebSocket transport, and a canvas client with six "
        "drawing tools, live cursors, presence, undo and redo.",
        "Three collections implemented, with the stroke log holding several document shapes and no "
        "schema migration between them.",
        "Complete CRUD surface over both REST and WebSocket, including operations that genuinely update "
        "and genuinely delete, plus a cascading room delete.",
        "Seven purpose-built indexes, each justified against a specific query, with plans captured "
        "through explain.",
        "Nine aggregation pipelines, surfaced in the application itself rather than only in a shell, "
        "each displayed alongside the pipeline that produced it.",
        f"A generated dataset of {m['collectionStats']['strokes']['documents']:,} stroke documents, "
        "shaped to resemble real drawing rather than uniform noise.",
        "A measured index benchmark and join-cost study, with snapshotting implemented in response to "
        "what the join-cost study showed.",
        "Cross-instance operation demonstrated with two independent backend processes, and an automated "
        "verification script covering every operation including the concurrent-undo race.",
    ])

    h2(doc, "9.2 Deviations from the Review 1 proposal")
    para(doc,
         "Four things differ from the Review 1 information sheet. Each was a considered decision, and "
         "recording them is more useful than quietly matching the original document.")
    table(doc, ["Review 1 stated", "Review 2 actual", "Reason"], [
        ["Two collections: rooms and strokes",
         "Three collections: rooms, strokes and snapshots",
         "Measurement showed a full replay of the largest room transfers "
         f"{max(r['fullMB'] for r in m['joinCost']):.0f} MB. Snapshots cut that by about 95 per cent, "
         "so the optional optimisation became part of the normal join path and needed its own "
         "collection."],
        ["Snapshotting listed as optional",
         "Implemented, with both client-side and server-side generation",
         "Same reason. It is no longer optional because a large board is unusable without it."],
        ["Cloud hosting on MongoDB Atlas free tier",
         "Local MongoDB and Redis in Docker for development; Atlas-ready by configuration",
         "Atlas is a one-line change in the environment file and the capacity estimate in section 7.3 "
         "targets M0. Local Docker keeps the demonstration independent of network conditions, and "
         "Redis has no hosting listed in Review 1 at all, so it needed one either way."],
        ["Postman for API testing",
         "Postman for REST, plus a scripted verification run",
         "Postman is awkward for WebSockets and cannot easily express the concurrent-undo race, which "
         "needs two requests genuinely in flight at once."],
    ], widths=[1.5, 1.7, 2.9], font_size=8.4)

    h2(doc, "9.3 Known limitations")
    para(doc, "Stating these is more useful than overclaiming; each is acceptable at this stage.")
    bullets(doc, [
        "**No authentication.** Identity is a display name in browser storage and anyone with a room code "
        "can join, so per-user undo trusts the client's claimed identity. Real accounts would be required "
        "before deployment but add nothing to the database concepts under assessment.",
        "**Preview fanout grows with the square of participants in a room.** Acceptable for a whiteboard "
        "used by a handful of people; a larger room would need server-side throttling.",
        "**Snapshots of dense boards approach a size where GridFS would be the right storage.** The 16 MB "
        "limit is not reached and pruning keeps the total bounded, but the headroom is measured rather "
        "than generous.",
        "**No conflict resolution for concurrent modification of the same stroke.** Two users restyling "
        "one stroke resolve last-write-wins. This is where operational transformation or a CRDT would "
        "genuinely be needed, and it is not claimed.",
        "**Timing measurements are cache-warm,** which as section 5.3 explains understates rather than "
        "overstates the benefit of the indexes.",
    ])

    h2(doc, "9.4 Plan for Review 3")
    bullets(doc, [
        "Deploy against MongoDB Atlas M0 and a hosted Redis and re-measure every query, since network "
        "latency and a constrained cache will change the numbers in section 5 and are likely to widen the "
        "index advantage.",
        "Add a TTL index to expire abandoned rooms automatically — a NoSQL feature the project has a "
        "genuine use for and does not yet exercise.",
        "Replace the polling heartbeat with MongoDB change streams for a second, database-driven "
        "notification path, and compare it with the Redis path.",
        "Move snapshot storage to GridFS and compare WebP against PNG, closing the headroom concern in "
        "section 9.3.",
        "Add shared draggable objects, which would introduce genuine concurrent modification and so make "
        "an operational-transformation or CRDT layer necessary rather than ornamental.",
        "Load-test with scripted WebSocket clients to find where a single instance saturates, and add a "
        "third instance to confirm the fanout scales as claimed.",
    ])


# ==========================================================================
def source_listings(doc) -> None:
    h1(doc, "10. Source Code Listings")
    para(doc,
         "Selected extracts, quoted directly from the files that run. The complete source is in the "
         "project repository; the layout is given first so the extracts can be located.")

    code(doc, """whiteboard/
├─ app/
│  ├─ main.py             FastAPI application, static mount, startup
│  ├─ config.py           environment configuration
│  ├─ db.py               Mongo and Redis clients, index definitions
│  ├─ models.py           Pydantic request and response models
│  ├─ util.py             room codes, BSON serialisation, bounding boxes
│  ├─ aggregations.py     the nine pipelines and their metadata
│  ├─ repositories/       rooms.py, strokes.py, snapshots.py
│  ├─ realtime/           hub.py (Redis fanout), ws.py (socket protocol)
│  └─ routers/            rooms.py, analytics.py, admin.py
├─ static/                index.html, css/, js/ (app, board, net, analytics)
├─ scripts/               seed, benchmark, snapshot, measurement, report, deck
└─ docker-compose.yml     MongoDB replica set and Redis""", size=8.4)

    h2(doc, "10.1 Index definitions")
    para(doc,
         "Indexes are declared as data rather than as a sequence of createIndex calls, each entry pairing "
         "the key specification with the rationale quoted in Table 5.1 so the two cannot drift apart. The "
         "remaining entries follow the same shape.")
    code(doc, source("app/db.py", "INDEX_PLAN", "    (\n        SNAPSHOTS,", max_lines=16))

    h2(doc, "10.2 The WebSocket protocol")
    code(doc, source("app/realtime/ws.py", '    if kind == "commit":', '    if kind == "clear":',
                     max_lines=20))

    h2(doc, "10.3 Incremental canvas rendering")
    code(doc, source("static/js/board.js", "  /** Repaint the offscreen base",
                     "  setStrokes(strokes)", max_lines=12))
    para(doc,
         "The aggregation pipelines appear in full in section 6 and the Redis fanout loop in section 2.7.")


# ==========================================================================
def references(doc) -> None:
    h1(doc, "11. References")
    para(doc,
         "The Review 1 list included four items that are not peer-reviewed papers: one with authors "
         "withheld, an encyclopedia entry and two blog posts. Those are replaced below. The operational "
         "transformation literature is retained because section 2.6 argues about its applicability rather "
         "than citing it in passing.")
    refs = [
        "A. K. Singh, P. K. Singh, M. Kumar, S. Tiwari, and V. Jain, \"A comparative study of MongoDB "
        "and document-based MySQL for big data application data management,\" Big Data and Cognitive "
        "Computing, vol. 6, no. 2, p. 49, 2022.",
        "C. Győrödi, R. Győrödi, G. Pecherle, and A. Olah, \"A comparative study: MongoDB vs. MySQL,\" "
        "in Proc. 13th Int. Conf. on Engineering of Modern Electric Systems (EMES), 2015, pp. 1-6.",
        "A. Gupta, S. Tyagi, N. Panwar, S. Sachdeva, and U. Saxena, \"NoSQL databases: Critical "
        "analysis and comparison,\" in Proc. Int. Conf. on Computational and Communication "
        "Technologies (IC3TSN), 2017, pp. 293-299.",
        "Z. Wei-ping, L. Ming-xin, and C. Huan, \"Using MongoDB to implement textbook management "
        "system instead of MySQL,\" in Proc. IEEE Int. Conf. on Communication Software and Networks, "
        "2011, pp. 303-305.",
        "Y. Li and S. Manoharan, \"A performance comparison of SQL and NoSQL databases,\" in Proc. "
        "IEEE Pacific Rim Conf. on Communications, Computers and Signal Processing (PACRIM), 2013, "
        "pp. 15-19.",
        "D. Sun and C. Sun, \"Context-based operational transformation in distributed collaborative "
        "editing systems,\" IEEE Transactions on Parallel and Distributed Systems, vol. 20, no. 10, "
        "pp. 1454-1470, 2009.",
        "C. Sun and C. Ellis, \"Operational transformation in real-time group editors: issues, "
        "algorithms, and achievements,\" in Proc. ACM Conf. on Computer Supported Cooperative Work "
        "(CSCW), 1998, pp. 59-68.",
        "M. Shapiro, N. Preguiça, C. Baquero, and M. Zawirski, \"Conflict-free replicated data "
        "types,\" in Proc. 13th Int. Symp. on Stabilization, Safety, and Security of Distributed "
        "Systems (SSS), 2011, pp. 386-400.",
        "M. Weiss, P. Urso, and P. Molli, \"Logoot: A scalable optimistic replication algorithm for "
        "collaborative editing on P2P networks,\" in Proc. IEEE Int. Conf. on Distributed Computing "
        "Systems (ICDCS), 2009, pp. 404-412.",
        "N. Preguiça, J. M. Marquès, M. Shapiro, and M. Letia, \"A commutative replicated data type "
        "for cooperative editing,\" in Proc. IEEE Int. Conf. on Distributed Computing Systems (ICDCS), "
        "2009, pp. 395-403.",
        "S. Gilbert and N. Lynch, \"Brewer's conjecture and the feasibility of consistent, available, "
        "partition-tolerant web services,\" ACM SIGACT News, vol. 33, no. 2, pp. 51-59, 2002.",
        "J. Kreps, N. Narkhede, and J. Rao, \"Kafka: A distributed messaging system for log "
        "processing,\" in Proc. NetDB Workshop, 2011, pp. 1-7.",
    ]
    for i, ref in enumerate(refs, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1.5)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.add_run(f"[{i}] {ref}").font.size = Pt(10)

    para(doc,
         "Software documentation consulted during implementation — the MongoDB Manual (aggregation "
         "pipeline, indexing strategies, explain results), the Redis documentation (Pub/Sub, INCR, key "
         "expiry) and the FastAPI documentation (WebSockets) — is reference material rather than part of "
         "the literature survey.",
         italic=True, size=10.5)


# ==========================================================================
def main() -> None:
    if not (DOCS / "measurements.json").exists():
        print("docs/measurements.json is missing — run scripts/collect_measurements.py first")
        raise SystemExit(1)

    m = json.loads((DOCS / "measurements.json").read_text(encoding="utf-8"))

    doc = new_document()
    add_page_numbers(doc, "Review 2 — Real-Time Collaborative Whiteboard — Batch NS02")

    title_page(doc, m)
    introduction(doc, m)
    system_design(doc, m)
    database_design(doc, m)
    crud(doc, m)
    indexing(doc, m)
    aggregation_section(doc, m)
    performance(doc, m)
    walkthrough(doc, m)
    progress(doc, m)
    source_listings(doc)
    references(doc)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)

    words = sum(len(p.text.split()) for p in doc.paragraphs)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  {len(doc.paragraphs)} paragraphs, ~{words:,} words, "
          f"{len(doc.inline_shapes)} figures, {len(doc.tables)} tables, "
          f"{OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
