"""Report what consumes vertical space in each section of the built document.

Prose is cheap to cut and easy to over-blame; figures, code listings and wide
tables are usually where a page budget actually goes. This prints both so the
trimming can be aimed.
"""

import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

DOC = Path(__file__).resolve().parent.parent / "docs" / "Review2_Design_and_Implementation_NS02.docx"


def main() -> None:
    doc = Document(str(DOC))
    section = "front matter"
    acc: dict[str, dict[str, int]] = {}

    def slot() -> dict[str, int]:
        return acc.setdefault(section, {"prose": 0, "figs": 0, "code": 0, "tbls": 0, "rows": 0})

    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            p = Paragraph(child, doc)
            if p.style.name == "Heading 1":
                section = p.text.strip()
                slot()
                continue
            s = slot()
            if "graphic" in child.xml:
                s["figs"] += 1
            elif p.runs and p.runs[0].font.name == "Consolas":
                s["code"] += p.text.count("\n") + 1
            elif p.style.name in ("Normal", "List Bullet"):
                size = p.runs[0].font.size if p.runs else None
                if size is None or size.pt >= 9:
                    s["prose"] += len(p.text.split())
        elif child.tag.endswith("}tbl"):
            s = slot()
            s["tbls"] += 1
            s["rows"] += len(Table(child, doc).rows)

    # Rough vertical cost in pages, to rank sections rather than to predict Word.
    print(f"{'section':<42}{'prose':>7}{'figs':>6}{'code':>7}{'tbls':>6}{'rows':>6}{'est pp':>8}")
    for name, s in acc.items():
        est = s["prose"] / 520 + s["figs"] * 0.33 + s["code"] / 78 + s["rows"] / 46
        print(f"{name[:40]:<42}{s['prose']:>7}{s['figs']:>6}{s['code']:>7}"
              f"{s['tbls']:>6}{s['rows']:>6}{est:>8.1f}")
    tot = {k: sum(s[k] for s in acc.values()) for k in ("prose", "figs", "code", "tbls", "rows")}
    print(f"{'TOTAL':<42}{tot['prose']:>7}{tot['figs']:>6}{tot['code']:>7}"
          f"{tot['tbls']:>6}{tot['rows']:>6}")


if __name__ == "__main__":
    sys.exit(main())
