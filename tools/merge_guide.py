# SPDX-License-Identifier: MIT
"""Merge one-page Pencil exports into the guide, in page order and at true A4.

    uv run tools/merge_guide.py <folder with pNN/export.pdf> docs/OpenNest-Guide.pdf
"""
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

A4 = (595.28, 841.89)


def main() -> None:
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    writer = PdfWriter()
    for page_file in sorted(folder.glob("p[0-9][0-9]/export.pdf")):
        page = PdfReader(page_file).pages[0]
        page.scale_to(*A4)
        writer.add_page(page).compress_content_streams()
    writer.add_metadata({"/Title": "OpenNest: design and manufacturing guide", "/Author": "Adaptyv"})
    with out.open("wb") as f:
        writer.write(f)
    print(f"{len(writer.pages)} pages, A4, {out}")


if __name__ == "__main__":
    main()
