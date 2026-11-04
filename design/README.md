# Design

`opennest.pen` is the source for the identity, the README figures and the guide. It opens in
[pen.dev](https://pen.dev). The design follows Adaptyv's brand rules: Geist and Geist Mono, ink,
cyan and steel, a flat isometric style and no hairline rules on ink.

| Frame | Exported to |
| --- | --- |
| `00 Identity` | `identity-board.png` |
| `01 README banner` | `docs/img/banner.png` at 2x, `docs/img/social-preview.png` at 1x |
| `02 Anatomy` | `docs/img/anatomy.png` |
| `03 Plan drawing` | `docs/img/plan-drawing.png` |
| `04 Tab section` | `docs/img/tab-section.png` |
| `05 Agent ready` | `docs/img/agent-ready.png` |
| `06 Manufacturing` | `docs/img/manufacturing.png` |
| `07 Avatar` | `logo/avatar-512.png` |
| `PDF 1` to `PDF 10` | `docs/OpenNest-Guide.pdf` |

The drawings are computed from the plate's real dimensions, so change them with the plate.

## Rebuilding the guide

Export each `PDF n` frame on its own, as `<folder>/pNN/export.pdf`, then merge them:

```sh
uv run tools/merge_guide.py <folder> docs/OpenNest-Guide.pdf
```

This fixes the page order and scales the pages to true A4. Pencil exports a page at 794 x 1123 pt.

`logo/opennest-glyph.svg` is the glyph for dark backgrounds, and `opennest-glyph-ink.svg` for light
ones. It is the plate's real outline with its eight guide tabs.

`fonts/` holds Geist and Geist Mono under the SIL Open Font License. `brand/` holds the Adaptyv logo,
which is not licensed for reuse: see `TRADEMARKS.md`.
