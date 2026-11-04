# SPDX-License-Identifier: CERN-OHL-P-2.0
"""One-page A4 shop drawing for a machined plate, with its hole table. The STEP file stays the master."""
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from svgpathtools import parse_path

from . import spec as s
from .plan import Plan, text_width

INK = HexColor("#142933")
SOFT = Color(0x14 / 255, 0x29 / 255, 0x33 / 255, 0.62)
FAINT = Color(0x14 / 255, 0x29 / 255, 0x33 / 255, 0.28)
ACCENT = HexColor("#1183BC")
TAB = HexColor("#36B7F6")
LEAD = HexColor("#A6DEFB")


def _fonts() -> None:
    for name, file in (("Geist", "Geist-400.ttf"), ("GeistM", "Geist-500.ttf"), ("Mono", "GeistMono-400.ttf"), ("MonoM", "GeistMono-500.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(s.REPO / "design/fonts" / file)))
    pdfmetrics.registerFont(TTFont("Engrave", str(s.FONT)))


class Sheet:
    def __init__(self, path: Path):
        self.c = canvas.Canvas(str(path), pagesize=landscape(A4))
        self.w, self.h = landscape(A4)

    def poly(self, pts, close=True, stroke=INK, width=0.8, fill=None):
        path = self.c.beginPath()
        path.moveTo(*pts[0])
        for p in pts[1:]:
            path.lineTo(*p)
        if close:
            path.close()
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(width)
        if fill is not None:
            self.c.setFillColor(fill)
        self.c.drawPath(path, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)

    def line(self, a, b, color=SOFT, width=0.45, dash=None):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.setDash(*(dash or ([], 0)))
        self.c.line(a[0], a[1], b[0], b[1])
        self.c.setDash([], 0)

    def text(self, x, y, value, font="Mono", size=7.5, color=INK, align="left", angle=0):
        self.c.saveState()
        self.c.translate(x, y)
        if angle:
            self.c.rotate(angle)
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        {"left": self.c.drawString, "center": self.c.drawCentredString, "right": self.c.drawRightString}[align](0, 0, value)
        self.c.restoreState()

    def arrow(self, tip, dx, dy, color):
        self.poly([tip, (tip[0] + dx * 5 - dy * 1.5, tip[1] + dy * 5 + dx * 1.5), (tip[0] + dx * 5 + dy * 1.5, tip[1] + dy * 5 - dx * 1.5)], stroke=None, fill=color)

    def hdim(self, x0, x1, y, ext0, ext1, label, key=False):
        color = ACCENT if key else SOFT
        for x, e in ((x0, ext0), (x1, ext1)):
            sign = 1 if y > e else -1
            self.line((x, e), (x, y + sign * 2.5), color, 0.4)
        self.line((x0, y), (x1, y), color, 0.5)
        self.arrow((x0, y), 1, 0, color)
        self.arrow((x1, y), -1, 0, color)
        self.text((x0 + x1) / 2, y + 2.5, label, "MonoM", 7.5, ACCENT if key else INK, "center")

    def vdim(self, y0, y1, x, ext0, ext1, label, key=False):
        color = ACCENT if key else SOFT
        for y, e in ((y0, ext0), (y1, ext1)):
            sign = 1 if x > e else -1
            self.line((e, y), (x + sign * 2.5, y), color, 0.4)
        self.line((x, y0), (x, y1), color, 0.5)
        self.arrow((x, y0), 0, 1, color)
        self.arrow((x, y1), 0, -1, color)
        self.text(x - 2.5, (y0 + y1) / 2, label, "MonoM", 7.5, ACCENT if key else INK, "center", 90)


def _mark_loops():
    root = ET.parse(s.LOGO_SVG).getroot()
    d = next(el for el in root.iter() if el.tag.endswith("path")).attrib["d"]
    loops = [[seg.point(i / 8) for seg in sub for i in range(8)] for sub in parse_path(d).continuous_subpaths()]
    xs = [p.real for loop in loops for p in loop]
    ys = [-p.imag for loop in loops for p in loop]
    k = s.LOGO_H / (max(ys) - min(ys))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return [[((p.real - cx) * k + s.LOGO_CENTER[0], (-p.imag - cy) * k + s.LOGO_CENTER[1]) for p in loop] for loop in loops]


def _plan_view(sh: Sheet, plan: Plan, ox: float, oy: float) -> None:
    def m(x, y):
        return ox + x * mm, oy + y * mm

    wx, wy = plan.pocket_x / 2, plan.pocket_y / 2
    sh.poly([m(*p) for p in s.outline()], width=1.0, fill=HexColor("#FFFFFF"))
    for sx in (-1, 1):
        for sy in (-1, 1):
            y0 = plan.corner_y0[(sx, sy)]
            corner = [(wx, y0), (s.L / 2, y0), (s.L / 2, s.W / 2 - 3), (s.L / 2 - 3, s.W / 2), (wx, s.W / 2)]
            sh.poly([m(sx * x, sy * y) for x, y in corner], width=0.5, fill=TAB)
            lead = [(wx, y0), (wx + s.CHAMFER_IN, y0), (wx + s.CHAMFER_IN, s.W / 2 - 0.1), (wx, s.W / 2)]
            sh.poly([m(sx * x, sy * y) for x, y in lead], width=0.4, fill=LEAD)
            side = [(s.SIDE_TAB_X[0], wy), (s.SIDE_TAB_X[1], wy), (s.SIDE_TAB_X[1], s.W / 2), (s.SIDE_TAB_X[0], s.W / 2)]
            sh.poly([m(sx * x, sy * y) for x, y in side], width=0.5, fill=TAB)
            lead = [(s.SIDE_TAB_X[0], wy), (s.SIDE_TAB_X[1], wy), (s.SIDE_TAB_X[1], wy + s.CHAMFER_IN), (s.SIDE_TAB_X[0], wy + s.CHAMFER_IN)]
            sh.poly([m(sx * x, sy * y) for x, y in lead], width=0.4, fill=LEAD)
    sh.line(m(-s.L / 2 - 4, 0), m(s.L / 2 + 4, 0), FAINT, 0.4, ([6, 2, 1, 2], 0))
    sh.line(m(0, -s.W / 2 - 4), m(0, s.W / 2 + 4), FAINT, 0.4, ([6, 2, 1, 2], 0))
    if plan.engrave_logo:
        for loop in _mark_loops():
            sh.poly([m(*p) for p in loop], stroke=FAINT, width=0.35)
    tx, ty = m(*s.TITLE_CENTER)
    if plan.engrave_title:
        sh.text(tx, ty - 2.2 * mm, plan.title, "Engrave", s.TITLE_H * mm, FAINT, "center")
    if plan.label and plan.engrave_label:
        right = tx + text_width(plan.title, s.TITLE_H) / 2 * mm
        sh.text(right, ty - (s.TITLE_H / 2 + s.SUB_GAP + s.SUB_H * 0.72) * mm, plan.label, "Engrave", s.SUB_H * mm, FAINT, "right")
    for i, (x, y) in enumerate(plan.request.holes, 1):
        c = m(x, y)
        sh.c.setStrokeColor(INK)
        sh.c.setLineWidth(0.7)
        sh.c.circle(c[0], c[1], plan.through_d / 2 * mm)
        if plan.cbore or plan.csk_d:
            sh.c.circle(c[0], c[1], plan.head_r * mm)
        sh.text(c[0], c[1] + (plan.head_r + 1.0) * mm, f"H{i}", "MonoM", 6.5, ACCENT, "center")

    top, bottom, left, right = m(0, s.W / 2)[1], m(0, -s.W / 2)[1], m(-s.L / 2, 0)[0], m(s.L / 2, 0)[0]
    sh.hdim(*[m(-wx, 0)[0], m(wx, 0)[0]], top + 26, m(0, 30)[1], m(0, 30)[1], f"{plan.pocket_x:.2f} {s.TOL_POCKET}", key=True)
    sh.hdim(m(s.SIDE_TAB_X[0], 0)[0], m(s.SIDE_TAB_X[1], 0)[0], top + 9, top, top, f"{s.SIDE_TAB_X[1] - s.SIDE_TAB_X[0]:g}")
    sh.hdim(m(0, 0)[0], m(s.SIDE_TAB_X[0], 0)[0], top + 9, top + 4, top, f"{s.SIDE_TAB_X[0]:g}")
    y0 = plan.corner_y0[(1, 1)]
    sh.vdim(m(0, y0)[1], top, right + 10, right, right, f"{s.W / 2 - y0:g}")
    sh.hdim(m(-s.NOTCH_W / 2, 0)[0], m(s.NOTCH_W / 2, 0)[0], bottom - 14, m(0, -s.W / 2 + s.NOTCH_D)[1], m(0, -s.W / 2 + s.NOTCH_D)[1], f"{s.NOTCH_W:g}")
    sh.hdim(left, right, bottom - 30, bottom + 3 * mm, bottom + 3 * mm, f"{s.L:g}")
    sh.vdim(m(0, -wy)[1], m(0, wy)[1], left - 18, m(-50, 0)[0], m(-50, 0)[0], f"{plan.pocket_y:.2f} {s.TOL_POCKET}", key=True)
    sh.vdim(bottom, top, right + 22, right - 3 * mm, right - 3 * mm, f"{s.W:g}")
    sh.vdim(bottom, m(0, -s.W / 2 + s.NOTCH_D)[1], m(-s.NOTCH_W / 2, 0)[0] + 16, m(-8, 0)[0], m(-8, 0)[0], f"{s.NOTCH_D:g}")


def _section(sh: Sheet, plan: Plan, ox: float, oy: float, k: float) -> None:
    """Corner tab section, at k drawing mm per part mm."""
    wall = plan.pocket_x / 2
    x0 = wall - 3.0

    def m(x, z):
        return ox + (x - x0) * k * mm, oy + z * k * mm

    pts = [(x0, 0), (s.L / 2 - 0.5, 0), (s.L / 2, 0.5), (s.L / 2, s.TOP - 0.5), (s.L / 2 - 0.5, s.TOP), (wall + s.CHAMFER_IN, s.TOP), (wall, s.TOP - s.CHAMFER_UP), (wall, s.SEAT), (x0, s.SEAT)]
    sh.poly([m(*p) for p in pts], width=0.9, fill=HexColor("#FFFFFF"))
    tab = [(wall, s.SEAT), (s.L / 2, s.SEAT), (s.L / 2, s.TOP - 0.5), (s.L / 2 - 0.5, s.TOP), (wall + s.CHAMFER_IN, s.TOP), (wall, s.TOP - s.CHAMFER_UP)]
    sh.poly([m(*p) for p in tab], width=0.9, fill=TAB)
    right = m(s.L / 2, 0)[0]
    sh.vdim(m(0, s.SEAT)[1], m(0, s.TOP - s.CHAMFER_UP)[1], right + 14, right, right, f"{s.CHAMFER_UP:g}")
    sh.vdim(m(0, s.TOP - s.CHAMFER_UP)[1], m(0, s.TOP)[1], right + 14, right, right, f"{s.CHAMFER_UP:g}")
    sh.vdim(m(0, 0)[1], m(0, s.SEAT)[1], right + 14, right, right, f"{s.SEAT:.2f} {s.TOL_SEAT}", key=True)
    sh.hdim(m(wall, 0)[0], m(wall + plan.chamfer_x, 0)[0], m(0, s.TOP)[1] + 9, m(0, s.TOP - s.CHAMFER_UP)[1], m(0, s.TOP)[1], f"{plan.chamfer_x:.2f}")
    sh.hdim(m(wall, 0)[0], right, m(0, s.TOP)[1] + 22, m(0, s.TOP - s.CHAMFER_UP)[1], m(0, s.TOP)[1], f"{s.L / 2 - wall:.2f}")
    sh.text(m(wall, 0)[0] - 5, m(0, s.TOP - s.CHAMFER_UP / 2)[1], "LEAD-IN", "MonoM", 6.5, INK, "right")
    sh.text(m(x0, 0)[0], m(0, 0)[1] - 11, f"SECTION AT A CORNER TAB, {k:g}:1", "Mono", 6.2, SOFT)


def _table(sh: Sheet, x, y, cols, rows, size=7.0, row_h=11.5):
    width = sum(c[1] for c in cols)
    cx = x
    for title, w in cols:
        sh.text(cx, y, title, "Mono", 6.2, SOFT)
        cx += w
    y -= 4
    sh.line((x, y), (x + width, y), FAINT, 0.5)
    for row in rows:
        y -= row_h - 3
        cx = x
        for (title, w), value in zip(cols, row):
            sh.text(cx, y, str(value), "Mono", size)
            cx += w
        y -= 3
        sh.line((x, y), (x + width, y), FAINT, 0.3)
    return y


def write_drawing(plan: Plan, path: Path) -> None:
    _fonts()
    sh = Sheet(path)
    req, material = plan.request, plan.material
    sh.text(36, sh.h - 40, "OpenNest deck plate", "GeistM", 19, INK)
    sh.text(36, sh.h - 54, " / ".join(filter(None, (plan.label, material.title, f"v{s.VERSION}"))).upper(), "Mono", 7.5, SOFT)
    _plan_view(sh, plan, 275, 298)

    col = 556
    _section(sh, plan, col + 4, sh.h - 186, 4.2)

    y = sh.h - 216
    sh.text(col, y, "TOLERANCES", "MonoM", 7, ACCENT)
    y = _table(sh, col, y - 13, (("FEATURE", 130), ("VALUE", 120)), [
        ("Pocket X", f"{plan.pocket_x:.2f} {s.TOL_POCKET}"),
        ("Pocket Y", f"{plan.pocket_y:.2f} {s.TOL_POCKET}"),
        ("Seat height", f"{s.SEAT:.2f} {s.TOL_SEAT}"),
        ("Seat flatness", f"{s.TOL_FLATNESS}"),
        ("Everything else", s.TOL_GENERAL),
    ])
    finish = {
        "cnc-aluminium": "Anodize per MIL-PRF-8625, Type II, Class 2.",
        "cnc-polymer": "No coating. Check dimensions at 20 C.",
        "cnc-ptfe": "No coating. Dimensions at 23 C, above the 19 C transition.",
    }.get(material.process, "")
    coated = "Dimensions apply after coating. " if material.process == "cnc-aluminium" else ""
    notes = [finish, f"{coated}Tab walls meet the seat in a", "sharp corner: use a square end mill. External edges R0.5.", f"Plate corners R{s.R_CORNER:g}. Notch R{s.R_NOTCH:g} inside, R{s.R_MOUTH:g} at the mouth.", f"Engraving {s.ENGRAVE_DEPTH} mm deep. The STEP file is the master."]
    notes.append("Status: this version has not been machined yet. Calculated, not proven.")
    if material.process == "cnc-ptfe" and req.holes:
        notes.append("Fit a stainless sleeve, 5 x 3.2 x 2.0 mm, in each hole.")
    y -= 15
    for line in filter(None, notes):
        sh.text(col, y, line, "Geist", 7.2, INK)
        y -= 10

    if req.holes:
        y -= 7
        sh.text(col, y, "HOLES", "MonoM", 7, ACCENT)
        head = f"{plan.cbore[0]:g} x {plan.cbore[1]:g} deep" if plan.cbore else (f"{plan.csk_d:g}, 90 deg" if plan.csk_d else "")
        rows = [(f"H{i}", f"{x:g}", f"{yy:g}", f"{plan.through_d:g}", head) for i, (x, yy) in enumerate(req.holes, 1)]
        size, row_h = (7.0, 11.0) if len(rows) <= 9 else (5.4, 7.0)
        rows = rows[:16]
        _table(sh, col, y - 12, (("ID", 28), ("X", 42), ("Y", 42), ("THRU", 38), ("HEAD", 100)), rows, size, row_h)
        if len(req.holes) > 16:
            sh.text(col, 44, f"{len(req.holes) - 16} more holes: see report.json and the STEP file.", "Geist", 6.5, SOFT)

    sh.line((36, 34), (sh.w - 36, 34), FAINT, 0.5)
    sh.text(36, 22, f"ORIGIN AT PLATE CENTRE, Z 0 AT THE UNDERSIDE / UNITS MM / SCALE 1:1 ON A4 / {date.today().isoformat()}", "Mono", 6.5, SOFT)
    sh.text(sh.w - 36, 22, "OPEN HARDWARE / AGENT READY", "Mono", 6.5, SOFT, "right")
    sh.c.setTitle(f"OpenNest {req.name} drawing")
    sh.c.save()
