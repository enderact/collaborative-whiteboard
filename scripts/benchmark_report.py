"""Run the index benchmark and print a report suitable for pasting into the document.

    python scripts/benchmark_report.py --room LNCSJ5

Results are also written to docs/benchmark.json so the document generator can
quote real measured numbers instead of invented ones.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", required=True, help="room code to benchmark")
    ap.add_argument("--base", default="http://127.0.0.1:8002", help="running API base URL")
    args = ap.parse_args()

    with httpx.Client(timeout=300.0) as client:
        print(f"benchmarking room {args.room} via {args.base} …\n")
        bench = client.post(f"{args.base}/api/admin/benchmark", params={"room": args.room})
        bench.raise_for_status()
        data = bench.json()

        stats = client.get(f"{args.base}/api/admin/stats").json()

        pipelines = client.get(f"{args.base}/api/analytics").json()["pipelines"]
        timings = []
        for spec in pipelines:
            res = client.get(f"{args.base}/api/analytics/{spec['key']}", params={"room": args.room})
            if res.status_code == 200:
                body = res.json()
                timings.append(
                    {
                        "key": spec["key"],
                        "title": spec["title"],
                        "stages": spec["stages"],
                        "elapsedMs": body["elapsedMs"],
                        "resultCount": body["resultCount"],
                    }
                )

    print("INDEX BENCHMARK")
    print("=" * 78)
    print(f"room {data['room']} holds {data.get('strokesInRoom', 0):,} strokes")
    print(f"indexes dropped for the test: {', '.join(data['indexesDroppedForTest'])}\n")

    def side(label: str, s: dict, extra: str = "") -> str:
        # A query with no supporting index can be rejected outright rather than
        # merely being slow, so the timing may legitimately be absent.
        if s.get("error"):
            return f"    {label:<14}: REJECTED  {s['error']}"
        ms = f"{s['ms']:>9.2f} ms" if s.get("ms") is not None else "        — "
        return (f"    {label:<14}: {ms}   {str(s.get('scanType')):<9}"
                f" docs examined {s.get('docsExamined', 0):>8,}{extra}")

    for name, c in data["comparison"].items():
        print(f"  {name.replace('_', ' ')}")
        print(f"    {c['why']}")
        print(side("without index", c["withoutIndex"]))
        print(side("with index", c["withIndex"], f"   [{c['withIndex'].get('indexName')}]"))
        speed = f"{c['speedup']}x" if c.get("speedup") else "n/a"
        print(f"    {'speedup':<14}: {speed:<9}  fewer documents read: {c['docsExaminedReduction']:,}\n")

    print("AGGREGATION PIPELINE TIMINGS")
    print("=" * 78)
    for t in timings:
        print(f"  {t['title']:<34} {t['elapsedMs']:>8.2f} ms   {t['resultCount']:>4} rows   {' '.join(t['stages'])}")

    print("\nCOLLECTION STATISTICS")
    print("=" * 78)
    for coll, s in stats.items():
        print(f"  db.{coll}")
        print(f"    documents {s['documents']:>10,}   data {s['dataSizeKB'] / 1024:>8.1f} MB"
              f"   indexes {s['indexSizeKB'] / 1024:>6.1f} MB   avg doc {s['avgDocSizeBytes']:>6,} B")

    out_dir = ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    payload = {"room": args.room, "benchmark": data, "pipelineTimings": timings, "stats": stats}
    (out_dir / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwritten to {out_dir / 'benchmark.json'}")


if __name__ == "__main__":
    main()
