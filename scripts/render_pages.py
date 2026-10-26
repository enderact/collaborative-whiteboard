"""Render pages of the exported PDF to PNG so the layout can be inspected."""

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "Review2_Design_and_Implementation_NS02.pdf"
OUT = ROOT / "docs" / "pagecheck"


def main(argv: list[str]) -> None:
    pages = [int(a) for a in argv] or [1]
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    print(f"{doc.page_count} pages")
    for n in pages:
        pix = doc[n - 1].get_pixmap(dpi=110)
        path = OUT / f"p{n:02d}.png"
        pix.save(path)
        print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
