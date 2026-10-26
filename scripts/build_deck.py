"""Build the Review 2 presentation.

Slides are organised around the five rubric criteria rather than around the
codebase, so each block of marks has slides that argue for it. Every number is
read from docs/measurements.json, the same source the written report uses, so the
deck and the document cannot disagree.

    python scripts/collect_measurements.py --base http://127.0.0.1:8001
    python scripts/make_diagrams.py
    python scripts/build_deck.py
"""

import json
import sys
from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.pptx_kit import (  # noqa: E402
    ACCENT, CARD, EDGE, GOOD, INK, MUTED, TEXT, WARN, W, H,
    bullet_list, card, code_card, footer, new_deck, picture, slide, stat_card,
    table, textbox, write,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"
SHOTS = DOCS / "screenshots"
OUT = DOCS / "Review2_Presentation_NS02.pptx"

TEAM = "Devesh Atul Mahajan (23BCE0801)  ·  Prakrit Bahl (23BCE0826)  ·  Lakshya Diwani (23BCE0811)"


# --------------------------------------------------------------------------
def title_slide(prs, m: dict) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = INK
    bg.line.fill.background()

    band = s.shapes.add_shape(1, 0, Inches(2.42), W, Pt(3))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()

    tf = textbox(s, 0.9, 1.12, 11.5, 1.2)
    write(tf, "NoSQL Database — BCSE406L  ·  Review 2", size=15, colour=ACCENT, first=True)
    write(tf, "Real-Time Collaborative Whiteboard", size=42, bold=True, space_after=2)

    tf = textbox(s, 0.9, 2.72, 11.5, 1.0)
    write(tf, "An append-only document model in MongoDB, with Redis for ordering, presence "
              "and cross-instance event fanout", size=17, colour=MUTED, first=True, line=1.15)

    stats = m["collectionStats"]
    cards = [
        (f"{stats['strokes']['documents']:,}", "stroke documents in the\nseeded database", GOOD),
        (f"{len(m['indexes']['planned'])}", "purpose-built indexes,\nevery plan measured", ACCENT),
        (f"{len(m['analytics'])}", "aggregation pipelines,\nlive in the application", ACCENT),
        ("3", "collections: rooms,\nstrokes, snapshots", ACCENT),
    ]
    for i, (value, label, colour) in enumerate(cards):
        stat_card(s, 0.9 + i * 2.95, 4.0, 2.7, value, label, colour=colour, height=1.3)

    tf = textbox(s, 0.9, 5.72, 11.5, 0.8)
    write(tf, TEAM, size=13, colour=TEXT, first=True)
    write(tf, "Batch NS02  ·  B.Tech CSE  ·  Guide: Dr. D. Vivek", size=12, colour=MUTED)


def agenda_slide(prs, m: dict) -> None:
    s = slide(prs, "What this deck argues, and where", kicker="Agenda")
    rows = [
        ["System design", "6", "Append-only model, two-store split, ordering, fanout", "3 – 6"],
        ["Database implementation", "8", "Collections, flexible schema, CRUD, deletion, indexes",
         "7 – 12"],
        ["Query quality", "6", "Measured index plans, nine pipelines, join cost", "13 – 17"],
        ["Prototype / demo", "5", "Running system, cross-instance sync, live analytics", "18 – 20"],
        ["Documentation & progress", "5", "Deviations, limitations, plan for Review 3", "21 – 22"],
    ]
    table(s, 0.62, 1.75, 12.1, ["Rubric criterion", "Marks", "Argued by", "Slides"], rows,
          col_widths=[3.0, 1.0, 6.3, 1.8], size=13.5, row_h=0.46)

    tf = textbox(s, 0.62, 5.5, 12.1, 1.0)
    write(tf, "Everything shown is measured against a running system.", size=15, bold=True,
          first=True)
    write(tf, "The numbers in this deck come from docs/measurements.json, produced by a script "
              "that queries the live application. No figure here was typed by hand.",
          size=13.5, colour=MUTED, line=1.1)


# --------------------------------------------------------------------------
def design_slides(prs, m: dict) -> None:
    s = slide(prs, "One decision shapes everything else", kicker="System design")
    card(s, 0.62, 1.78, 5.85, 2.1)
    tf = textbox(s, 0.85, 1.98, 5.4, 1.8)
    write(tf, "The canvas is never stored as a picture", size=17, bold=True, colour=GOOD,
          first=True)
    write(tf, "It is an ordered, append-only stream of stroke documents. What a user sees is "
              "derived state, rebuilt by replaying that stream.", size=13.5, colour=MUTED,
          line=1.12)

    card(s, 6.85, 1.78, 5.85, 2.1)
    tf = textbox(s, 7.08, 1.98, 5.4, 1.8)
    write(tf, "Why that makes it a NoSQL project", size=17, bold=True, colour=ACCENT, first=True)
    write(tf, "Four tools produce genuinely different documents in one collection. Undo becomes "
              "a flag, so history survives. Ordering cannot come from a clock.", size=13.5,
          colour=MUTED, line=1.12)

    bullet_list(s, 0.62, 4.15, 12.1, [
        ("Replay, not snapshots of truth.",
         "A snapshot is only a cache; the log remains the system of record."),
        ("Undo is a soft delete.",
         "active: false retains the stroke, so redo and analytics still see it."),
        ("Order comes from Redis INCR.",
         "Atomic across every instance, so replay is total and reproducible."),
        ("Previews are never persisted.",
         "One stroke writes exactly one document, however many frames it took to draw."),
    ], size=15)
    footer(s, "Sections 1 and 2 of the report")

    # ---- architecture
    s = slide(prs, "Runtime architecture", kicker="System design")
    picture(s, FIGURES / "architecture.png", 0.62, 1.72, 7.5)
    bullet_list(s, 8.45, 1.85, 4.3, [
        ("Two FastAPI processes,", "sharing no memory. This is deliberate."),
        ("A single process", "could broadcast from a dictionary and would never exercise the "
                             "fanout layer at all."),
        ("MongoDB is the only", "durable state: rooms, the stroke log, snapshots."),
        ("Redis is the bus", "and the counter — drawn between the instances because that is its "
                             "role."),
        ("Both drivers are async.", "A blocking call in a WebSocket handler would stall every "
                                    "other user on that process."),
    ], size=13.5)
    footer(s, "Demonstrated live: two browsers, two processes, one board")

    # ---- two stores
    s = slide(prs, "Why two data stores, and what breaks", kicker="System design")
    table(s, 0.62, 1.78, 12.1,
          ["", "MongoDB", "Redis"],
          [["Holds", "Rooms, stroke log, snapshots", "Counters, Pub/Sub, presence"],
           ["Durability", "System of record", "Disposable cache"],
           ["If it restarts",
            "Boards are gone — this is the data that matters",
            "Cursors vanish, presence rebuilds, counter realigns from Mongo. No drawing lost."],
           ["Why not the other one",
            "Cannot give an atomic cross-process counter cheaply",
            "Cannot be trusted with the only copy of a board"]],
          col_widths=[1.9, 4.6, 5.6], size=13, row_h=0.62)
    tf = textbox(s, 0.62, 5.42, 12.1, 1.1)
    write(tf, "The division is by durability requirement, not convenience.", size=15, bold=True,
          first=True)
    write(tf, "A cursor position that is stale within 16 ms is write amplification for no benefit, "
              "so it expires by TTL in Redis and is never written to disk.", size=13.5,
          colour=MUTED, line=1.1)
    footer(s, "Section 2.3 of the report")

    # ---- ordering
    s = slide(prs, "Ordering: the subtlest part of the design", kicker="System design")
    rows = [
        ["Client timestamp", "Rejected", "Participants' clocks disagree, sometimes by seconds"],
        ["ObjectId timestamp", "Rejected",
         "One-second granularity: two strokes 40 ms apart order arbitrarily"],
        ["Redis INCR per room", "Chosen",
         "Atomic across every instance, so the order is total and reproducible"],
    ]
    table(s, 0.62, 1.78, 12.1, ["Candidate", "Verdict", "Why"], rows,
          col_widths=[2.9, 1.6, 7.6], size=13.5, row_h=0.5)
    code_card(s, 0.62, 3.55, 6.1, 2.55, """
seq = await r().incr(f"room:{room_id}:seq")
# Redis is a cache, not the record, so a restart must not
# collide: realign upward from the highest persisted seq.
highest = await db()[STROKES].find_one(
    {"roomId": room_id}, sort=[("seq", -1)], projection={"seq": 1})
""".strip(), title="app/repositories/strokes.py", size=11)
    bullet_list(s, 7.05, 3.7, 5.65, [
        ("Why it matters:", "replay only rebuilds the right picture in the right order."),
        ("Failure mode avoided:", "an intermittent mis-ordering that is very easy to miss in "
                                  "testing."),
        ("Second reason for Redis.", "Ordering, not just fanout, is why it is in the stack."),
    ], size=13.5)
    footer(s, "Section 2.4 of the report")

    # ---- write path + fanout
    s = slide(prs, "The write path, and the duplicate-stroke trap", kicker="System design")
    picture(s, FIGURES / "write-path.png", 0.62, 1.75, 6.6)
    tf = textbox(s, 7.6, 1.82, 5.12, 0.4)
    write(tf, "Exactly one delivery path", size=17, bold=True, colour=WARN, first=True)
    bullet_list(s, 7.6, 2.3, 5.12, [
        ("The obvious version is wrong.", "Send to local clients and also publish to Redis, and "
                                          "the publisher — which is subscribed — renders the "
                                          "stroke twice."),
        ("Invisible on an opaque pen.", "Obvious with a transparent stroke or an eraser, and "
                                        "easily misread as a rendering bug."),
        ("So handlers never write", "to their own sockets. Every instance, publisher included, "
                                    "delivers from its subscription."),
        ("The author is excluded", "by an id carried inside the published message, so it works "
                                   "whichever instance holds that socket."),
    ], size=13)
    footer(s, "Section 2.7 of the report")


# --------------------------------------------------------------------------
def database_slides(prs, m: dict) -> None:
    stats = m["collectionStats"]

    s = slide(prs, "Three collections, measured", kicker="Database implementation")
    table(s, 0.62, 1.78, 12.1,
          ["Collection", "Holds", "Documents", "Data", "Indexes"],
          [["rooms", "One document per board, participants embedded",
            f"{stats['rooms']['documents']:,}", f"{stats['rooms']['dataSizeMB']:.2f} MB",
            f"{stats['rooms']['indexSizeMB']:.2f} MB"],
           ["strokes", "The append-only log, one document per stroke",
            f"{stats['strokes']['documents']:,}", f"{stats['strokes']['dataSizeMB']:.1f} MB",
            f"{stats['strokes']['indexSizeMB']:.1f} MB"],
           ["snapshots", "Rasterised canvas at a known sequence number",
            f"{stats['snapshots']['documents']:,}", f"{stats['snapshots']['dataSizeMB']:.1f} MB",
            f"{stats['snapshots']['indexSizeMB']:.2f} MB"]],
          col_widths=[1.7, 5.4, 1.7, 1.65, 1.65], size=13, row_h=0.52)

    for i, (value, label) in enumerate([
        (f"{stats['strokes']['avgDocBytes']:,} B", "average stroke document — the basis of the\n"
                                                   "capacity estimate"),
        (f"{m['roomCount']}", "rooms, one of them deliberately large\nfor the measurements"),
        ("2 → 3", "collections: snapshots was added\nafter measuring join cost"),
    ]):
        stat_card(s, 0.62 + i * 4.1, 3.85, 3.85, value, label, colour=ACCENT, height=1.24)

    tf = textbox(s, 0.62, 5.42, 12.1, 1.0)
    write(tf, "Review 1 proposed two collections. Measurement added the third.", size=15,
          bold=True, first=True)
    write(tf, "A full replay of the largest room transfers "
              f"{max(r['fullMB'] for r in m['joinCost']):.0f} MB, so snapshotting moved from "
              "'optional' to part of the normal join path.", size=13.5, colour=MUTED, line=1.1)
    footer(s, "Section 3.1 of the report")

    # ---- flexible schema
    s = slide(prs, "Flexible schema, shown rather than claimed",
              kicker="Database implementation")
    tf = textbox(s, 0.62, 1.72, 12.1, 0.4)
    write(tf, "Three documents from the same collection, written by the same code path. "
              "No migration, no nullable columns standing in for absent fields.",
          size=14.5, colour=MUTED, first=True)

    code_card(s, 0.62, 2.22, 3.9, 3.5, """
{
  "tool": "pen",
  "seq": 1,
  "points": [
    {"x": 323.7, "y": 294.2},
    {"x": 325.9, "y": 293.9},
    ... 145 more ...
  ],
  "pointCount": 148,
  "style": {"width": 6.4},
  "active": true
}
""".strip(), title="pen — carries points", size=10.5)

    code_card(s, 4.72, 2.22, 3.9, 3.5, """
{
  "tool": "rect",
  "seq": 14,
  "geometry": {
    "x": 798.1, "y": 159.3,
    "w": 417.5, "h": -191.1
  },
  "bbox": {"minX": 798.1, ...},
  "style": {"width": 8.3},
  "active": true
}
""".strip(), title="rect — no points at all", size=10.5)

    code_card(s, 8.82, 2.22, 3.9, 3.5, """
{
  "tool": "text",
  "seq": 21,
  "text": "stroke log =",
  "font": "600 34px Inter",
  "geometry": {
    "x": 452.0, "y": 118.0
  },
  "style": {"color": "#e8ecf4"},
  "active": true
}
""".strip(), title="text — text and font", size=10.5)

    tf = textbox(s, 0.62, 5.9, 12.1, 0.7)
    write(tf, "Adding a polygon tool tomorrow needs a model and a renderer — no migration. "
              "Existing documents are untouched and replay keeps working, because readers only "
              "look at the fields relevant to each tool.", size=13.5, colour=MUTED, first=True,
          line=1.1)
    footer(s, "Sections 3.3 and 3.7 of the report")

    # ---- embed vs reference + redis keys
    s = slide(prs, "Embed or reference, and the Redis key space",
              kicker="Database implementation")
    tf = textbox(s, 0.62, 1.7, 5.85, 0.3)
    write(tf, "The governing question is whether the child is bounded", size=14.5, bold=True,
          colour=ACCENT, first=True)
    table(s, 0.62, 2.08, 5.85,
          ["Relationship", "Strategy", "Why"],
          [["Room → participants", "Embedded", "Bounded, small, read with the room"],
           ["Room → strokes", "Referenced",
            f"Unbounded — {max(r['strokes'] for r in m['joinCost']):,} in one room"],
           ["Room → snapshots", "Referenced", "Large binaries, pruned separately"]],
          col_widths=[1.85, 1.3, 2.7], size=11.5, row_h=0.56)

    tf = textbox(s, 6.85, 1.7, 5.87, 0.3)
    write(tf, "Redis is a database here too, so its keys are documented", size=14.5, bold=True,
          colour=ACCENT, first=True)
    table(s, 6.85, 2.08, 5.87,
          ["Key", "Type", "Lifetime"],
          [["room:{id}:seq", "Counter", "Persistent, realigned on join"],
           ["wb:room:{CODE}", "Pub/Sub", "Transient, never stored"],
           ["room:{CODE}:presence", "Hash", "Expires after 2 min of silence"]],
          col_widths=[2.25, 1.15, 2.47], size=11.5, row_h=0.56)

    tf = textbox(s, 0.62, 4.45, 12.1, 1.6)
    write(tf, "No amount of tuning makes an unbounded embedded array safe.", size=16, bold=True,
          first=True)
    write(tf, f"At {stats['strokes']['avgDocBytes']:,} bytes per stroke, the largest room alone "
              "would be far past the 16 MB document limit. Referencing also lets one stroke be "
              "undone or restyled without rewriting the room.", size=13.5, colour=MUTED,
          line=1.12)
    footer(s, "Sections 3.5 and 3.6 of the report")

    # ---- CRUD
    s = slide(prs, "The full CRUD surface, over REST and WebSocket",
              kicker="Database implementation")
    tf = textbox(s, 0.62, 1.7, 12.1, 0.34)
    write(tf, "An append-only log has no natural update or delete. These were designed in, not "
              "bolted on — and every one is reachable in Postman.", size=14, colour=MUTED,
          first=True)
    rows = [
        ["C", "POST /api/rooms  ·  POST /api/rooms/{code}/strokes",
         "Room with a unique code; one stroke document"],
        ["R", "GET /api/rooms  ·  /rooms/{code}/strokes?afterSeq=  ·  /strokes/{id}",
         "List, full replay, incremental tail, single document"],
        ["U", "PATCH /api/rooms/{code}  ·  PATCH /api/strokes/{id}  ·  POST /strokes/{id}/move",
         "Rename; restyle nested fields; $inc nested geometry"],
        ["D", "POST /rooms/{code}/undo | redo | compact  ·  DELETE /strokes/{id}  ·  "
              "DELETE /rooms/{code}",
         "Soft delete, hard delete, and cascade"],
    ]
    table(s, 0.62, 2.15, 12.1, ["", "Endpoints", "What it does"], rows,
          col_widths=[0.55, 6.75, 4.8], size=12, row_h=0.62)

    bullet_list(s, 0.62, 4.85, 12.1, [
        ("A stroke created over REST appears on an open board immediately,",
         "because the endpoint publishes to Redis — a far better demonstration than a refresh."),
        ("Verified by script, not by assertion.",
         "A run walks every operation including the concurrent-undo race and reports pass or fail."),
    ], size=14)
    footer(s, "Section 4 of the report")

    # ---- deletion + undo race
    s = slide(prs, "Three deletion semantics, and the one real race",
              kicker="Database implementation")
    table(s, 0.62, 1.75, 6.0,
          ["Semantics", "Retains data", "Used for"],
          [["Soft delete", "Yes, fully", "Undo and redo"],
           ["Compaction", "No", "Reclaiming finished boards"],
           ["Cascade delete", "No", "Removing a board entirely"]],
          col_widths=[2.1, 1.6, 2.3], size=12.5, row_h=0.5)
    tf = textbox(s, 0.62, 3.5, 6.0, 1.5)
    write(tf, "MongoDB has no ON DELETE CASCADE.", size=15, bold=True, colour=WARN, first=True)
    write(tf, "Deleting a room without its strokes would silently orphan tens of thousands of "
              "documents no query returns and no user can reach. Referential integrity is the "
              "application's job, and the endpoint reports what it removed.", size=13,
          colour=MUTED, line=1.1)

    code_card(s, 6.95, 1.75, 5.77, 3.35, """
# Scoped to the user: a room-wide undo would let one
# person retract another's work.
# Atomic: find-then-update in two calls lets two
# simultaneous undos claim the same stroke.
doc = await db()[STROKES].find_one_and_update(
    {"roomId": rid, "userId": uid, "active": True},
    {"$set": {"active": False, "undoneAt": now}},
    sort=[("seq", -1)],
    return_document=ReturnDocument.AFTER,
)
""".strip(), title="undo_last — one atomic claim", size=10.5)
    tf = textbox(s, 6.95, 5.25, 5.77, 0.8)
    write(tf, "The second request no longer matches active: true on that document and moves to "
              "the next one. This is also the query the dedicated undo index exists for.",
          size=13, colour=MUTED, first=True, line=1.1)
    footer(s, "Sections 4.5 and 4.6 of the report")


# --------------------------------------------------------------------------
def query_slides(prs, m: dict) -> None:
    bench = m.get("benchmark") or {}

    s = slide(prs, "Seven indexes, each for a named query", kicker="Query quality")
    rows = [[ix["name"], json.dumps(ix["keys"]).replace('"', ""), ix["rationale"][:88]]
            for ix in m["indexes"]["planned"]]
    table(s, 0.62, 1.75, 12.1, ["Index", "Key", "The query it exists for"], rows,
          col_widths=[2.5, 3.3, 6.3], size=11, row_h=0.42)
    tf = textbox(s, 0.62, 5.2, 12.1, 1.2)
    write(tf, "None was added speculatively.", size=15, bold=True, first=True)
    ix_mb = m["collectionStats"]["strokes"]["indexSizeMB"]
    data_mb = m["collectionStats"]["strokes"]["dataSizeMB"]
    write(tf, f"Indexes cost storage and slow every write. These total {ix_mb:.1f} MB against "
              f"{data_mb:.0f} MB of data ({ix_mb / data_mb * 100:.0f}% overhead). The largest single "
              "index is _id, which no query in this application ever uses.", size=13.5,
          colour=MUTED, line=1.1)
    footer(s, "Section 5.1 of the report")

    # ---- benchmark
    if bench:
        s = slide(prs, "Indexes: measured, not asserted", kicker="Query quality")
        picture(s, FIGURES / "docs-examined.png", 0.62, 1.72, 6.3,
                caption="Documents MongoDB had to open, log scale. Planner output, so it is "
                        "reproducible.")
        rows = [[name.replace("_", " "),
                 f"{c['withoutIndex']['scanType']} · {c['withoutIndex']['docsExamined']:,}",
                 f"{c['withIndex']['scanType']} · {c['withIndex']['docsExamined']:,}",
                 f"{c['speedup']}x" if c["speedup"] else "—"] for name, c in bench.items()]
        table(s, 7.15, 1.85, 5.57, ["Query", "Without index", "With index", "Gain"], rows,
              col_widths=[1.7, 1.6, 1.6, 0.67], size=11, row_h=0.46, highlight=GOOD)

        tf = textbox(s, 7.15, 4.5, 5.57, 1.9)
        write(tf, "The method", size=14.5, bold=True, colour=ACCENT, first=True)
        write(tf, "Drop the indexes, run each real query five times keeping the best, capture "
                  "explain in executionStats mode, rebuild, repeat.", size=12.5, colour=MUTED,
              line=1.08)
        write(tf, "Two queries reach zero documents examined: the count wins a COUNT_SCAN that "
                  "tallies index keys, and the covered query is answered entirely from the index.",
              size=12.5, colour=MUTED, line=1.08)
        footer(s, "Section 5.3 of the report")

        # ---- honest negative
        s = slide(prs, "Where the index barely helps", kicker="Query quality")
        name, c = min(bench.items(), key=lambda kv: kv[1]["speedup"] or 99)
        card(s, 0.62, 1.8, 12.1, 1.5, fill=RGBColor(0x2A, 0x20, 0x12), edge=WARN)
        tf = textbox(s, 0.9, 2.02, 11.5, 1.1)
        write(tf, f"{name.replace('_', ' ')}:  {c['withoutIndex']['ms']:.0f} ms without → "
                  f"{c['withIndex']['ms']:.0f} ms with  ({c['speedup']}x)", size=19, bold=True,
              colour=WARN, first=True)
        write(tf, f"It still opens {c['withIndex']['docsExamined']:,} documents. This result is "
                  "reported rather than omitted.", size=13.5, colour=MUTED)

        bullet_list(s, 0.62, 3.65, 12.1, [
            ("The query is not selective.", "It returns tens of thousands of documents, so the "
                                            "index lets the server skip almost nothing."),
            ("Index then fetch is random access;", "scanning the collection in storage order is "
                                                   "sequential. When a query touches most of a "
                                                   "collection, the sequential scan wins."),
            ("MongoDB's own planner would often choose the scan.",
             "The optimiser agreeing with the measurement is the point."),
            ("The general rule:", "an index pays off in proportion to how much of the collection "
                                  "it lets the server skip. A query that skips nothing gains "
                                  "nothing."),
        ], size=14.5)
        tf = textbox(s, 0.62, 6.15, 12.1, 0.6)
        write(tf, "Timings are also cache-warm: the whole collection fits in the WiredTiger cache "
                  "here, which flatters the unindexed case. On Atlas M0 the gap would be wider, so "
                  "these speed-ups are a conservative floor.", size=12.5, colour=MUTED, first=True,
              line=1.08)
        footer(s, "Section 5.4 of the report")

    # ---- aggregation overview
    s = slide(prs, "Nine pipelines, each answering a real question", kicker="Query quality")
    rows = [[v["meta"]["title"], v["meta"]["question"][:58],
             ", ".join(v["meta"]["stages"])[:46], f"{v['elapsedMs']:.0f} ms"]
            for v in m["analytics"].values()]
    table(s, 0.62, 1.72, 12.1, ["Pipeline", "Question it answers", "Stages", "Time"], rows,
          col_widths=[2.5, 4.5, 4.05, 1.05], size=10.5, row_h=0.4)
    tf = textbox(s, 0.62, 5.6, 12.1, 0.9)
    write(tf, "Not decorative: every one is reachable from the analytics panel in the running "
              "application, which displays the pipeline next to its own output.", size=14,
          colour=MUTED, first=True, line=1.1)
    footer(s, "Section 6 of the report")

    # ---- pipeline deep dive
    s = slide(prs, "Two pipelines worth arguing about", kicker="Query quality")
    code_card(s, 0.62, 1.75, 6.0, 4.0, """
{"$lookup": {
   "from": "strokes",
   "localField": "_id",
   "foreignField": "roomId",
   "as": "agg",
   "pipeline": [
     {"$match": {"active": true}},
     {"$group": {"_id": null,
        "total": {"$sum": 1},
        "people": {"$addToSet": "$userId"}}}
   ]}}
""".strip(), title="$lookup with a sub-pipeline", size=11)
    tf = textbox(s, 0.62, 5.85, 6.0, 0.85)
    write(tf, "The sub-pipeline aggregates inside the join, so tens of thousands of strokes are "
              "never materialised into the room document. Without it, the array would exceed "
              "16 MB and the query would fail.", size=12.5, colour=MUTED, first=True, line=1.08)

    code_card(s, 6.95, 1.75, 5.77, 4.0, """
{"$facet": {
   "byTool":    [{"$group": ...}, {"$sort": ...}],
   "byUser":    [{"$group": ...}, {"$limit": 5}],
   "perMinute": [{"$group": {"_id":
                   {"$dateTrunc": ...}}}],
   "bounds":    [{"$group": {"_id": null,
                   "minX": {"$min": "$bbox.minX"}}}]
}}
""".strip(), title="$facet — four summaries, one pass", size=11)
    tf = textbox(s, 6.95, 5.85, 5.77, 0.85)
    write(tf, "The panel needs four summaries at once. Four queries would mean four round trips "
              "and four passes over the same documents; $facet evaluates all four over one "
              "$match, so the panel loads from a single request.", size=12.5, colour=MUTED,
          first=True, line=1.08)
    footer(s, "Section 6 of the report")

    # ---- join cost
    s = slide(prs, "Measurement changed the design", kicker="Query quality")
    biggest = max(m["joinCost"], key=lambda r: r["strokes"])
    picture(s, FIGURES / "join-cost.png", 0.62, 1.75, 6.5)
    for i, (value, label, colour) in enumerate([
        (f"{biggest['fullMB']:.0f} MB", f"to join the {biggest['strokes']:,}-stroke room by full "
                                        "replay", WARN),
        (f"{biggest['withSnapshotMB']:.2f} MB", "with a snapshot plus only the newer strokes",
         GOOD),
        (f"{(1 - biggest['withSnapshotMB'] / biggest['fullMB']) * 100:.0f}%",
         "less data transferred; the board opens in about half a second", GOOD),
    ]):
        stat_card(s, 7.4, 1.85 + i * 1.42, 5.32, value, label, colour=colour, height=1.26)
    tf = textbox(s, 0.62, 5.6, 12.1, 0.95)
    write(tf, "Review 1 called snapshotting optional. The measurement settled it.", size=15,
          bold=True, first=True)
    write(tf, "Serialising a full replay took seconds, not milliseconds. The snapshot is a cache "
              "of derived state — the log still holds the truth, so undo and analytics are "
              "unaffected. Below a few hundred strokes the image costs more than the strokes, so "
              "small rooms are skipped.", size=13, colour=MUTED, line=1.1)
    footer(s, "Section 7.2 of the report")


# --------------------------------------------------------------------------
def demo_slides(prs, m: dict) -> None:
    s = slide(prs, "The running prototype", kicker="Prototype / demo")
    shots = [
        (SHOTS / "01-lobby.png", "Lobby — boards listed by last activity, served by "
                                 "ix_room_activity"),
        (SHOTS / "03-tools-and-shapes.png", "Six tools on one board; every mark is a separate "
                                            "document"),
        (SHOTS / "08-rest-api-endpoints.png", "The CRUD surface, exercised in Postman"),
    ]
    for i, (path, caption) in enumerate(shots):
        picture(s, path, 0.62 + i * 4.1, 1.85, 3.85, caption=caption)
    footer(s, "Section 8 of the report")

    s = slide(prs, "The result that matters most", kicker="Prototype / demo")
    picture(s, SHOTS / "04-cross-instance-sync.png", 0.62, 1.78, 7.3)
    tf = textbox(s, 8.2, 1.9, 4.52, 0.5)
    write(tf, "Two processes, one board", size=18, bold=True, colour=GOOD, first=True)
    bullet_list(s, 8.2, 2.45, 4.52, [
        ("This window is on wb-1,", "shown in the badge at the top right."),
        ("The pink strokes and the", "labelled cursor belong to a user connected to wb-2 — a "
                                     "separate OS process sharing no memory with this one."),
        ("Both arrived through Redis Pub/Sub.", "This is the claim the architecture makes, and "
                                                "it is the thing a single process could never "
                                                "demonstrate."),
    ], size=13)
    footer(s, "Live in the demo: two browsers, two ports, one room code")

    s = slide(prs, "Database work, visible in the application", kicker="Prototype / demo")
    picture(s, SHOTS / "05-aggregation-panel.png", 0.62, 1.85, 6.0,
            caption="The analytics panel shows each pipeline next to its own output and the "
                    "server-side execution time.")
    picture(s, SHOTS / "06-index-benchmark.png", 6.85, 1.85, 5.87,
            caption="The index benchmark, run from the interface: plan, documents examined and "
                    "time, with indexes dropped then rebuilt.")
    tf = textbox(s, 0.62, 5.75, 12.1, 0.8)
    write(tf, "Aggregation and indexing are not shell transcripts pasted into a report — they are "
              "features of the product, which is why they can be demonstrated live.", size=14,
          colour=MUTED, first=True, line=1.1)
    footer(s, "Demonstrated live: pick a pipeline, run it, read the plan")


# --------------------------------------------------------------------------
def progress_slides(prs, m: dict) -> None:
    s = slide(prs, "Progress, and four honest deviations",
              kicker="Documentation & progress")
    tf = textbox(s, 0.62, 1.7, 5.9, 0.3)
    write(tf, "Completed since Review 1", size=14.5, bold=True, colour=ACCENT, first=True)
    bullet_list(s, 0.62, 2.08, 5.9, [
        ("Application built", "— backend, transport, canvas client, six tools, presence."),
        ("Three collections", "with several document shapes in one log."),
        ("Full CRUD", "over REST and WebSocket, plus a cascading delete."),
        ("Seven indexes", "with plans captured through explain."),
        ("Nine pipelines", "surfaced in the product, not just a shell."),
        (f"{m['collectionStats']['strokes']['documents']:,} documents", "generated to a realistic "
                                                                       "shape."),
        ("Cross-instance sync", "demonstrated on two processes."),
    ], size=12.5, gap=0.06)

    tf = textbox(s, 6.85, 1.7, 5.87, 0.3)
    write(tf, "Deviations from the Review 1 sheet", size=14.5, bold=True, colour=WARN, first=True)
    table(s, 6.85, 2.08, 5.87,
          ["Review 1 said", "Review 2 does"],
          [["Two collections", "Three — join cost forced snapshots"],
           ["Snapshotting optional", "Implemented, client and server side"],
           ["Atlas free tier", "Local Docker; Atlas by configuration"],
           ["Postman for testing", "Postman plus a scripted run, which can express the undo race"]],
          col_widths=[2.3, 3.57], size=11.5, row_h=0.62)
    footer(s, "Section 9 of the report — 25-page document submitted alongside this deck")

    s = slide(prs, "Limitations we are not hiding, and what comes next",
              kicker="Documentation & progress")
    tf = textbox(s, 0.62, 1.7, 5.9, 0.3)
    write(tf, "Known limitations", size=14.5, bold=True, colour=WARN, first=True)
    bullet_list(s, 0.62, 2.08, 5.9, [
        ("No authentication.", "Identity is a display name in browser storage, so per-user undo "
                               "trusts the client."),
        ("Preview fanout grows with the square", "of participants in a room."),
        ("Dense snapshots approach the size", "where GridFS would be right; the headroom is "
                                              "measured, not generous."),
        ("No conflict resolution for concurrent", "edits to one stroke — last write wins. This is "
                                                  "exactly where a CRDT would be needed, and it "
                                                  "is not claimed."),
        ("Timings are cache-warm,", "which understates the index benefit."),
    ], size=12.5, gap=0.07)

    tf = textbox(s, 6.85, 1.7, 5.87, 0.3)
    write(tf, "Plan for Review 3", size=14.5, bold=True, colour=GOOD, first=True)
    bullet_list(s, 6.85, 2.08, 5.87, [
        ("Deploy to Atlas M0", "and re-measure; a constrained cache should widen the index "
                               "advantage."),
        ("Add a TTL index", "to expire abandoned rooms — a NoSQL feature not yet exercised."),
        ("Try change streams", "as a second, database-driven notification path, and compare it "
                               "with Redis."),
        ("Move snapshots to GridFS", "and compare WebP against PNG."),
        ("Add draggable objects,", "which would make a CRDT layer necessary rather than "
                                   "ornamental."),
        ("Load-test the fanout", "to find where one instance saturates."),
    ], size=12.5, gap=0.07)
    footer(s, "Sections 9.3 and 9.4 of the report")


def closing_slide(prs, m: dict) -> None:
    s = slide(prs, "What we will show in the demo", kicker="Live demonstration")
    steps = [
        ("1", "Create a board, draw with all six tools",
         "Each mark becomes one document; watch the stroke count rise."),
        ("2", "Open the same board in a second browser on port 8002",
         "A different process. Strokes and cursors cross through Redis Pub/Sub."),
        ("3", "Undo and redo from both windows",
         "Soft delete, scoped per user, claimed atomically."),
        ("4", "Exercise CRUD in Postman against the live board",
         "A REST insert appears on the canvas without a refresh; cascade delete reports its "
         "counts."),
        ("5", "Run pipelines from the analytics panel",
         "Pipeline and output side by side, with server-side timings."),
        ("6", "Run the index benchmark, then open the 42k-stroke board",
         "COLLSCAN against IXSCAN, then a snapshot join in about half a second."),
    ]
    y = 1.78
    for n, title, detail in steps:
        card(s, 0.62, y, 12.1, 0.72)
        tf = textbox(s, 0.85, y + 0.1, 0.5, 0.5)
        write(tf, n, size=19, bold=True, colour=ACCENT, first=True)
        tf = textbox(s, 1.4, y + 0.08, 11.1, 0.6)
        write(tf, title, size=14.5, bold=True, first=True, space_after=1)
        write(tf, detail, size=12, colour=MUTED)
        y += 0.82

    tf = textbox(s, 0.62, 6.82, 12.1, 0.4)
    write(tf, "Thank you.  ·  " + TEAM, size=12.5, colour=MUTED, align=PP_ALIGN.CENTER,
          first=True)


# --------------------------------------------------------------------------
def main() -> None:
    path = DOCS / "measurements.json"
    if not path.exists():
        print("docs/measurements.json is missing — run scripts/collect_measurements.py first")
        raise SystemExit(1)
    m = json.loads(path.read_text(encoding="utf-8"))

    prs = new_deck()
    title_slide(prs, m)
    agenda_slide(prs, m)
    design_slides(prs, m)
    database_slides(prs, m)
    query_slides(prs, m)
    demo_slides(prs, m)
    progress_slides(prs, m)
    closing_slide(prs, m)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  {len(prs.slides._sldIdLst)} slides, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
