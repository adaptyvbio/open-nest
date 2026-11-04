# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Build one OpenNest plate from a plan as a single CadQuery solid."""
import xml.etree.ElementTree as ET

import cadquery as cq
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from svgpathtools import CubicBezier, Line, QuadraticBezier, parse_path

from . import spec as s
from .plan import Plan


def _outline_solid():
    """Rounded rectangle minus the two U notches. Shared by the deck and the tabs."""
    plate = cq.Workplane("XY").rect(s.L, s.W).extrude(1).edges("|Z").fillet(s.R_CORNER)
    for sy in (-1, 1):
        slot = cq.Workplane("XY").center(0, sy * (s.W / 2 - s.NOTCH_D / 2 + 1)).rect(s.NOTCH_W, s.NOTCH_D + 2).extrude(1)
        inner = [e for e in slot.edges("|Z").vals() if abs(abs(e.Center().y) - (s.W / 2 - s.NOTCH_D)) < 1e-3]
        plate = plate.cut(slot.newObject(inner).fillet(s.R_NOTCH))
    mouths = [
        e
        for e in plate.edges("|Z").vals()
        if abs(abs(e.Center().x) - s.NOTCH_W / 2) < 1e-3 and abs(abs(e.Center().y) - s.W / 2) < 1e-3
    ]
    return plate.newObject(mouths).fillet(s.R_MOUTH)


def _sharp_edges(wp):
    """Edges whose two faces are not tangent; fillet seams and cylinder blends are skipped."""
    by_edge = {}
    for face in wp.val().Faces():
        for edge in face.Edges():
            by_edge.setdefault(edge.hashCode(), (edge, []))[1].append(face)
    out = []
    for edge, faces in by_edge.values():
        if len(faces) == 2:
            p = edge.positionAt(0.5)
            if abs(faces[0].normalAt(p).dot(faces[1].normalAt(p))) < 0.995:
                out.append(edge)
    return out


class _Fillets:
    """Fillet by predicate, keep going on failure, and remember the failures so a build can refuse them."""

    def __init__(self):
        self.log, self.failed = [], []

    def __call__(self, wp, predicate, r, label):
        selected = wp.newObject([e for e in _sharp_edges(wp) if predicate(e)])
        n = len(selected.vals())
        try:
            out = selected.fillet(r)
        except Exception as exc:  # noqa: BLE001, OpenCascade raises bare errors
            self.log.append(f"{label}: FAILED on {n} edges: {exc}")
            self.failed.append(label)
            return wp
        before, after = wp.val().BoundingBox(), out.val().BoundingBox()
        same = all(abs(a - b) < 1e-3 for a, b in ((before.xlen, after.xlen), (before.ylen, after.ylen), (before.zlen, after.zlen)))
        if not out.val().isValid() or not same:
            self.log.append(f"{label}: reverted, {n} edges R{r} made an invalid solid")
            self.failed.append(label)
            return wp
        self.log.append(f"{label}: {n} edges R{r} ok")
        return out


def _at_z(edge, z, tol=1e-3):
    return abs(edge.startPoint().z - z) < tol and abs(edge.endPoint().z - z) < tol


def _near(a, b, tol=1e-3):
    return abs(a - b) < tol


def _svg_faces(svg_path, height, center, z):
    """The SVG mark as one face at height z, with true curves: a polygon would give a CNC toolpath thousands of facets."""
    root = ET.parse(svg_path).getroot()
    d = next(el for el in root.iter() if el.tag.endswith("path")).attrib["d"]
    subpaths = parse_path(d).continuous_subpaths()
    points = [p for sub in subpaths for seg in sub for p in (seg.point(i / 8) for i in range(9))]
    xs, ys = [p.real for p in points], [-p.imag for p in points]
    scale = height / (max(ys) - min(ys))
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    def vec(p):
        return cq.Vector((p.real - cx) * scale + center[0], (-p.imag - cy) * scale + center[1], z)

    wires = []
    for sub in subpaths:
        edges = []
        for seg in sub:
            if isinstance(seg, Line):
                if abs(seg.start - seg.end) > 1e-6:
                    edges.append(cq.Edge.makeLine(vec(seg.start), vec(seg.end)))
            elif isinstance(seg, (CubicBezier, QuadraticBezier)):
                edges.append(cq.Edge.makeBezier([vec(c) for c in seg.bpoints()]))
            else:
                edges.append(cq.Edge.makeSpline([vec(seg.point(i / 12)) for i in range(13)]))
        wires.append(cq.Wire.assembleEdges(edges))
    wires.sort(key=lambda w: cq.Face.makeFromWires(w).Area(), reverse=True)
    return cq.Face.makeFromWires(wires[0], wires[1:])


class _OutlinePen(BasePen):
    """Collect a glyph as closed contours of line and Bezier segments, in font units."""

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.contours = []

    def _moveTo(self, pt):
        self.contours.append([])
        self._last = pt

    def _lineTo(self, pt):
        if pt != self._last:
            self.contours[-1].append((self._last, pt))
        self._last = pt

    def _qCurveToOne(self, pt1, pt2):
        self.contours[-1].append((self._last, pt1, pt2))
        self._last = pt2

    def _curveToOne(self, pt1, pt2, pt3):
        self.contours[-1].append((self._last, pt1, pt2, pt3))
        self._last = pt3

    def _closePath(self):
        first = self.contours[-1][0][0]
        if self._last != first:
            self.contours[-1].append((self._last, first))


def _signed_area(points):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1])) / 2


def _contains(points, q):
    inside = False
    for a, b in zip(points, points[1:] + points[:1]):
        if (a[1] > q[1]) != (b[1] > q[1]) and q[0] < a[0] + (q[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            inside = not inside
    return inside


def _sample(segment, n=6):
    """Points along one segment, for winding and containment tests only."""
    if len(segment) == 2:
        return [segment[0]]
    out = []
    for i in range(n):
        t, u = i / n, 1 - i / n
        if len(segment) == 3:
            w = (u * u, 2 * u * t, t * t)
        else:
            w = (u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t)
        out.append((sum(a * p[0] for a, p in zip(w, segment)), sum(a * p[1] for a, p in zip(w, segment))))
    return out


def _text_tool(text, size, x, y, z, height, halign="center", valign="center"):
    """Engraving tool for a line of text, built straight from the font's curves: OpenCascade's own
    text builder makes inverted solids from this font, and these outlines cut as true curves."""
    font = TTFont(s.FONT)
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    placed, pen_x = [], 0.0
    for ch in text:
        name = cmap[ord(ch)]
        pen = _OutlinePen(glyphs)
        glyphs[name].draw(pen)
        placed.append((pen.contours, pen_x))
        pen_x += hmtx[name][0]
    samples = [(px + sx, sy) for contours, px in placed for c in contours for seg in c for sx, sy in _sample(seg)]
    xs, ys = [p[0] * scale for p in samples], [p[1] * scale for p in samples]
    dx = {"center": x - (max(xs) + min(xs)) / 2, "right": x - max(xs), "left": x - min(xs)}[halign]
    dy = {"center": y - (max(ys) + min(ys)) / 2, "top": y - max(ys), "bottom": y - min(ys)}[valign]

    def vec(p, offset):
        return cq.Vector((p[0] + offset) * scale + dx, p[1] * scale + dy, z)

    solids = []
    for contours, offset in placed:
        loops = []
        for contour in contours:
            edges = [
                cq.Edge.makeLine(vec(seg[0], offset), vec(seg[1], offset)) if len(seg) == 2 else cq.Edge.makeBezier([vec(q, offset) for q in seg])
                for seg in contour
            ]
            points = [q for seg in contour for q in _sample(seg)]
            loops.append((abs(_signed_area(points)), points, cq.Wire.assembleEdges(edges)))
        loops.sort(key=lambda loop: loop[0], reverse=True)
        outers, holes = [], {}
        for area, points, wire in loops:
            parent = next((o for o in outers if _contains(o[1], points[0])), None)
            if parent is None:
                outers.append((area, points, wire))
                holes[id(wire)] = []
            else:
                holes[id(parent[2])].append(wire)
        for _, _, wire in outers:
            face = cq.Face.makeFromWires(wire, holes[id(wire)])
            solids.append(cq.Solid.extrudeLinear(face, cq.Vector(0, 0, height)))
    bounds = (min(xs) + dx, max(xs) + dx, min(ys) + dy, max(ys) + dy)
    return solids, bounds


def build(plan: Plan):
    """Return (workplane, log lines). A failed fillet raises, so a broken plate never leaves the builder."""
    if not plan.ok:
        raise ValueError(plan.errors)
    req = plan.request
    wall_x, wall_y = plan.pocket_x / 2, plan.pocket_y / 2
    outer_x, outer_y = s.L / 2, s.W / 2
    fillet = _Fillets()

    outer = max(_outline_solid().faces("<Z").wires().vals(), key=lambda w: w.Length())

    def prism(z0, z1):
        return cq.Workplane("XY").add(cq.Solid.extrudeLinear(cq.Face.makeFromWires(outer), cq.Vector(0, 0, z1 - z0))).translate((0, 0, z0))

    def tab_x(sx, sy):
        pts = [(wall_x, s.SEAT), (outer_x + 1, s.SEAT), (outer_x + 1, s.TOP), (wall_x + s.CHAMFER_IN, s.TOP), (wall_x, s.TOP - s.CHAMFER_UP)]
        y0, y1 = sorted((sy * plan.corner_y0[(sx, sy)], sy * (outer_y + 1)))
        return cq.Workplane("XZ", origin=(0, y0, 0)).polyline([(sx * x, z) for x, z in pts]).close().extrude(-(y1 - y0))

    def tab_y(sx, sy):
        pts = [(wall_y, s.SEAT), (outer_y + 1, s.SEAT), (outer_y + 1, s.TOP), (wall_y + s.CHAMFER_IN, s.TOP), (wall_y, s.TOP - s.CHAMFER_UP)]
        x0, x1 = sorted((sx * s.SIDE_TAB_X[0], sx * s.SIDE_TAB_X[1]))
        return cq.Workplane("YZ", origin=(x0, 0, 0)).polyline([(sy * y, z) for y, z in pts]).close().extrude(x1 - x0)

    tabs = None
    for sx in (-1, 1):
        for sy in (-1, 1):
            for tab in (tab_x(sx, sy), tab_y(sx, sy)):
                tabs = tab if tabs is None else tabs.union(tab)
    body = prism(0, s.SEAT).union(tabs.intersect(prism(0, s.TOP + 1)), clean=True)

    tab_starts = set(plan.corner_y0.values())

    def is_tab_base(e):
        if not _at_z(e, s.SEAT):
            return False
        c = e.Center()
        x, y = abs(c.x), abs(c.y)
        return (
            _near(x, wall_x)
            or _near(y, wall_y)
            or (_near(x, s.SIDE_TAB_X[1]) and y > wall_y)
            or (_near(x, s.SIDE_TAB_X[0]) and y > wall_y)
            or (any(_near(y, y0) for y0 in tab_starts) and x > wall_x)
        )

    def is_seat_perimeter(e):
        if not _at_z(e, s.SEAT):
            return False
        c = e.Center()
        x, y = abs(c.x), abs(c.y)
        on_side = _near(x, outer_x, 0.01) or _near(y, outer_y, 0.01)
        on_corner = x > outer_x - s.R_CORNER - 0.01 and y > outer_y - s.R_CORNER - 0.01
        in_notch = x < s.NOTCH_W / 2 + 0.01 and y > outer_y - s.NOTCH_D - 0.01
        return (on_side or on_corner or in_notch) and not is_tab_base(e)

    body = fillet(body, is_tab_base, s.R_BASE, "tab base (construction)")
    above = lambda e: e.Center().z > s.SEAT + s.R_BASE + 0.05  # noqa: E731
    body = fillet(body, lambda e: above(e) or is_seat_perimeter(e), s.R_EDGE, "convex edges")

    # ---- screw holes, from the seat side
    if req.holes:
        holes = cq.Workplane("XY").pushPoints(list(req.holes)).circle(plan.through_d / 2).extrude(s.TOP + 2).translate((0, 0, -1))
        body = body.cut(holes)
    if plan.cbore:
        d, depth = plan.cbore
        cbores = cq.Workplane("XY").pushPoints(list(req.holes)).circle(d / 2).extrude(depth + 1).translate((0, 0, s.SEAT - depth))
        body = body.cut(cbores)

        def is_mouth(e):
            if not (_at_z(e, s.SEAT) and e.geomType() == "CIRCLE" and abs(e.radius() - d / 2) < 0.01):
                return False
            c = e.Center()
            return any(_near(c.x, x, 0.01) and _near(c.y, y, 0.01) for x, y in req.holes)

        body = fillet(body, is_mouth, s.R_CBORE, "counterbore mouths")
    if plan.csk_d:
        r = plan.csk_d / 2
        for x, y in req.holes:  # 90 deg, so the cone loses 1 mm of radius per mm of depth
            cone = cq.Solid.makeCone(r + 1, 0, r + 1, pnt=cq.Vector(x, y, s.SEAT + 1), dir=cq.Vector(0, 0, -1))
            body = body.cut(cq.Workplane("XY").add(cone))

    body = fillet(body, lambda e: _at_z(e, 0) and e.geomType() != "CIRCLE", s.BOTTOM_EDGE, "underside perimeter")

    # ---- cut the construction fillet away: the tab section just above it, extruded down to the seat
    z_wall = s.SEAT + s.R_BASE + 0.05
    walls = [
        cq.Solid.extrudeLinear(f.translate(cq.Vector(0, 0, s.SEAT - z_wall)), cq.Vector(0, 0, z_wall - s.SEAT))
        for f in body.section(z_wall).faces().vals()
    ]
    base_cut = cq.Workplane("XY", origin=(0, 0, s.SEAT)).rect(s.L + 2, s.W + 2).extrude(z_wall - s.SEAT)
    for wall in walls:
        base_cut = base_cut.cut(cq.Workplane("XY").add(wall))
    body = body.cut(base_cut)

    # ---- engraving, recessed into the seat
    floor_z = s.SEAT - s.ENGRAVE_DEPTH
    tool_height = s.ENGRAVE_DEPTH + 1

    def engrave(wp, solids):
        for solid in solids:
            wp = wp.cut(cq.Workplane("XY").add(solid))
        return wp

    if plan.engrave_logo:
        logo = _svg_faces(s.LOGO_SVG, s.LOGO_H, s.LOGO_CENTER, floor_z)
        body = body.cut(cq.Workplane("XY").add(cq.Solid.extrudeLinear(logo, cq.Vector(0, 0, tool_height))))
    if plan.engrave_title:
        solids, bounds = _text_tool(plan.title, s.TITLE_H, *s.TITLE_CENTER, floor_z, tool_height)
        body = engrave(body, solids)
        if plan.label:
            solids, _ = _text_tool(plan.label, s.SUB_H, bounds[1], bounds[2] - s.SUB_GAP, floor_z, tool_height, halign="right", valign="top")
            body = engrave(body, solids)

    if fillet.failed:
        raise RuntimeError(f"{req.name}: fillets failed: {fillet.failed}\n" + "\n".join(fillet.log))
    return body, fillet.log
