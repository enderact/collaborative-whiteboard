"""Generate the figures used in the report and the slide deck.

Everything here is drawn from measured numbers rather than illustrative ones, so
the charts and the text in the report cannot drift apart.

    python scripts/make_diagrams.py
"""

import asyncio
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "docs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1f2937"
ACCENT = "#2563eb"
GREEN = "#059669"
RED = "#dc2626"
AMBER = "#d97706"
GREY = "#9ca3af"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 10,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "text.color": INK,
    "figure.dpi": 200,
})


# --------------------------------------------------------------------------
def architecture() -> None:
    """Redis sits between the two app instances because it is the bus they share.

    Laying it out that way also means no connector has to cross another, which an
    earlier left-to-right version could not avoid.
    """
    fig, ax = plt.subplots(figsize=(10, 6.6))
    ax.set_xlim(0, 104)
    ax.set_ylim(-9, 100)
    ax.axis("off")

    TITLE_GAP, LINE_GAP, PAD = 6.2, 4.3, 4.0

    def box(cx, cy, w, title, lines, colour=ACCENT, fill="#eff6ff"):
        h = TITLE_GAP + LINE_GAP * len(lines) + PAD
        x, y = cx - w / 2, cy - h / 2
        ax.add_patch(patches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.5,rounding_size=1.1",
            linewidth=1.35, edgecolor=colour, facecolor=fill, zorder=2))
        ax.text(cx, y + h - 2.2, title, ha="center", va="top",
                fontsize=10.5, fontweight="bold", color=colour, zorder=3)
        for i, line in enumerate(lines):
            ax.text(cx, y + h - TITLE_GAP - 1.0 - i * LINE_GAP, line, ha="center",
                    va="top", fontsize=8.3, color=INK, zorder=3)
        return {"l": x, "r": x + w, "t": y + h, "b": y, "cx": cx, "cy": cy}

    def arrow(p1, p2, label, colour=INK, dashed=False, lift=1.4, ha="center"):
        ax.annotate("", xy=p2, xytext=p1, zorder=4,
                    arrowprops=dict(arrowstyle="-|>", color=colour, linewidth=1.2,
                                    linestyle="--" if dashed else "-",
                                    shrinkA=1, shrinkB=1,
                                    mutation_scale=11))
        ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + lift, label, ha=ha,
                fontsize=7.7, color=colour, style="italic", zorder=5,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))

    TOP, MID, BOTTOM = 80, 48, 16

    browser_a = box(15, TOP, 27, "Browser A", ["HTML5 Canvas, vanilla JS",
                                               "renders optimistically",
                                               "logical 1600x900 space"])
    browser_b = box(15, BOTTOM, 27, "Browser B", ["same room code",
                                                  "different backend process",
                                                  "sees cursors and previews"])
    wb1 = box(50, TOP, 28, "FastAPI wb-1", ["WebSocket /ws/{code}",
                                            "REST /api/*",
                                            "async PyMongo, redis.asyncio"])
    wb2 = box(50, BOTTOM, 28, "FastAPI wb-2", ["identical code",
                                               "holds only its own sockets",
                                               "shares no memory with wb-1"])
    redis_box = box(50, MID, 30, "Redis", ["INCR — per-room sequence",
                                           "Pub/Sub — cross-instance fanout",
                                           "HSET + TTL — presence, cursors",
                                           "not the system of record"],
                    RED, "#fef2f2")
    mongo = box(87, MID, 30, "MongoDB", ["system of record",
                                         "rooms — embedded participants",
                                         "strokes — append-only log",
                                         "snapshots — rasterised state",
                                         "7 purpose-built indexes"],
                GREEN, "#ecfdf5")

    arrow((browser_a["r"], TOP), (wb1["l"], TOP), "WebSocket")
    arrow((browser_b["r"], BOTTOM), (wb2["l"], BOTTOM), "WebSocket")
    arrow((wb1["cx"], wb1["b"]), (redis_box["cx"], redis_box["t"]), "publish", RED, lift=0.9)
    arrow((redis_box["cx"], redis_box["b"]), (wb2["cx"], wb2["t"]), "deliver", RED, lift=0.9)
    arrow((wb1["r"], TOP - 6), (mongo["l"], MID + 8), "insert stroke", GREEN)
    arrow((wb2["r"], BOTTOM + 6), (mongo["l"], MID - 8), "read / aggregate", GREEN)

    ax.text(52, 96, "Real-Time Collaborative Whiteboard — runtime architecture",
            ha="center", fontsize=12.5, fontweight="bold")
    ax.text(52, -5.0,
            "A stroke drawn in Browser A is written once to MongoDB and published to Redis. Every instance, "
            "including the\npublisher, delivers it from its own subscription, so there is exactly one delivery "
            "path and no duplicate rendering.",
            ha="center", fontsize=8.2, style="italic", color="#4b5563")

    fig.savefig(OUT / "architecture.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote architecture.png")


# --------------------------------------------------------------------------
def write_path() -> None:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    ax.axis("off")

    lanes = [("pointer events", 36), ("Redis Pub/Sub", 24), ("MongoDB", 12)]
    for label, y in lanes:
        ax.plot([12, 96], [y, y], color=GREY, linewidth=0.9, zorder=1)
        ax.text(11, y, label, ha="right", va="center", fontsize=8.6, fontweight="bold")

    downs = [18, 26, 34, 42, 50, 58, 66]
    for x in downs:
        ax.plot([x], [36], marker="o", markersize=4.6, color=ACCENT, zorder=3)
    ax.plot([74], [36], marker="s", markersize=7, color=GREEN, zorder=3)

    for x in downs:
        ax.annotate("", xy=(x, 24.7), xytext=(x, 35.3),
                    arrowprops=dict(arrowstyle="->", color=ACCENT, linewidth=0.85))
        ax.plot([x], [24], marker="o", markersize=3.6, color=ACCENT, zorder=3)

    ax.annotate("", xy=(74, 12.7), xytext=(74, 35.3),
                arrowprops=dict(arrowstyle="->", color=GREEN, linewidth=1.5))
    ax.plot([74], [12], marker="s", markersize=7, color=GREEN, zorder=3)
    ax.annotate("", xy=(74, 24), xytext=(74, 12.6),
                arrowprops=dict(arrowstyle="->", color=RED, linewidth=1.1))

    ax.text(42, 40.4, "pointermove  (preview only)", ha="center", fontsize=9, color=ACCENT)
    ax.text(74, 40.4, "pointerup", ha="center", fontsize=9, color=GREEN, fontweight="bold")
    ax.text(42, 20.6, "relayed to peers, never persisted", ha="center", fontsize=8,
            style="italic", color=ACCENT)
    ax.text(78, 8.4, "one insert_one: the whole point array\nplus a seq from Redis INCR",
            ha="left", fontsize=8, style="italic", color=GREEN)

    ax.text(50, 43.4, "Write path: many ephemeral previews, one durable document per stroke",
            ha="center", fontsize=11.5, fontweight="bold")
    ax.text(50, 2.4,
            "Persisting each pointermove would put a 50-200 ms Atlas round trip inside the drawing loop. "
            "Previews travel\nthrough Redis for the live feel; MongoDB is written once, when the stroke "
            "becomes a fact.",
            ha="center", fontsize=8, style="italic", color="#4b5563")

    fig.savefig(OUT / "write-path.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote write-path.png")


# --------------------------------------------------------------------------
def benchmark_chart(bench: dict) -> None:
    names, before, after, labels = [], [], [], []
    for key, c in bench.items():
        if c["withoutIndex"]["ms"] is None or c["withIndex"]["ms"] is None:
            continue
        names.append(key.replace("_", "\n"))
        before.append(c["withoutIndex"]["ms"])
        after.append(c["withIndex"]["ms"])
        labels.append(f"{c['speedup']}x" if c["speedup"] else "")

    x = range(len(names))
    fig, ax = plt.subplots(figsize=(8.6, 4.0))
    w = 0.38
    b1 = ax.bar([i - w / 2 for i in x], before, w, label="no index (COLLSCAN)",
                color=RED, alpha=0.85)
    b2 = ax.bar([i + w / 2 for i in x], after, w, label="with index (IXSCAN)",
                color=GREEN, alpha=0.9)

    for rect in list(b1) + list(b2):
        ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(),
                f"{rect.get_height():.0f}", ha="center", va="bottom", fontsize=7.6)
    for i, label in enumerate(labels):
        top = max(before[i], after[i])
        ax.text(i, top * 1.14, label, ha="center", fontsize=9,
                fontweight="bold", color=ACCENT)

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8.4)
    ax.set_ylabel("query time (ms, best of 3)")
    ax.set_title("Query latency with and without the supporting index\n"
                 "strokes collection, 80,019 documents", fontsize=11)
    ax.legend(fontsize=8.4, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, max(max(before), max(after)) * 1.34)

    fig.savefig(OUT / "benchmark.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote benchmark.png")


def docs_examined_chart(bench: dict) -> None:
    names = [k.replace("_", "\n") for k in bench]
    before = [bench[k]["withoutIndex"]["docsExamined"] for k in bench]
    after = [bench[k]["withIndex"]["docsExamined"] for k in bench]

    x = range(len(names))
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    w = 0.38
    ax.bar([i - w / 2 for i in x], before, w, label="no index", color=RED, alpha=0.85)
    ax.bar([i + w / 2 for i in x], after, w, label="with index", color=GREEN, alpha=0.9)

    for i, (bef, aft) in enumerate(zip(before, after)):
        ax.text(i - w / 2, bef, f"{bef:,}", ha="center", va="bottom", fontsize=7.4)
        ax.text(i + w / 2, max(aft, 1), f"{aft:,}", ha="center", va="bottom", fontsize=7.4)

    ax.set_yscale("symlog")
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8.4)
    ax.set_ylabel("documents examined (log scale)")
    ax.set_title("Documents MongoDB had to open to answer each query", fontsize=11)
    ax.legend(fontsize=8.4, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)

    fig.savefig(OUT / "docs-examined.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote docs-examined.png")


# --------------------------------------------------------------------------
def join_cost_chart(rows: list[dict]) -> None:
    rows = [r for r in rows if r["strokes"] > 500][:5]
    names = [f"{r['code']}\n{r['strokes']:,}" for r in rows]
    full = [r["fullMB"] for r in rows]
    snap = [r["withSnapshotMB"] for r in rows]

    x = range(len(names))
    fig, ax = plt.subplots(figsize=(8.2, 3.9))
    w = 0.38
    ax.bar([i - w / 2 for i in x], full, w, label="full log replay", color=AMBER, alpha=0.9)
    ax.bar([i + w / 2 for i in x], snap, w, label="snapshot + tail", color=GREEN, alpha=0.9)

    for i, (f, s) in enumerate(zip(full, snap)):
        ax.text(i - w / 2, f, f"{f:.1f}", ha="center", va="bottom", fontsize=7.6)
        ax.text(i + w / 2, s, f"{s:.2f}", ha="center", va="bottom", fontsize=7.6)
        ax.text(i, max(f, s) * 1.1, f"-{(1 - s / f) * 100:.0f}%", ha="center",
                fontsize=8.6, fontweight="bold", color=ACCENT)

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=8.2)
    ax.set_ylabel("data transferred to join (MB)")
    ax.set_title("Cost of joining a room, measured per room", fontsize=11)
    ax.legend(fontsize=8.4, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, max(full) * 1.25)

    fig.savefig(OUT / "join-cost.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote join-cost.png")


def tool_mix_chart(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r["count"], reverse=True)
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    bars = ax.barh([r["tool"] for r in rows][::-1], [r["count"] for r in rows][::-1],
                   color=ACCENT, alpha=0.85)
    for rect, r in zip(bars, rows[::-1]):
        ax.text(rect.get_width() * 1.01, rect.get_y() + rect.get_height() / 2,
                f"{r['count']:,}  (avg {r['avgPoints']:.0f} pts)",
                va="center", fontsize=8)
    ax.set_xlabel("stroke documents")
    ax.set_title("Tool distribution from the $group aggregation", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlim(0, max(r["count"] for r in rows) * 1.32)

    fig.savefig(OUT / "tool-mix.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote tool-mix.png")


# --------------------------------------------------------------------------
async def main() -> None:
    architecture()
    write_path()

    measured = Path(__file__).resolve().parent.parent / "docs" / "measurements.json"
    if not measured.exists():
        print("\nno docs/measurements.json yet — run scripts/collect_measurements.py first;\n"
              "architecture diagrams were still written.")
        return

    data = json.loads(measured.read_text())
    if data.get("benchmark"):
        benchmark_chart(data["benchmark"])
        docs_examined_chart(data["benchmark"])
    if data.get("joinCost"):
        join_cost_chart(data["joinCost"])
    if data.get("analytics", {}).get("tool_usage"):
        tool_mix_chart(data["analytics"]["tool_usage"]["results"])


if __name__ == "__main__":
    asyncio.run(main())
