# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Turn a request into a plate plan, or say exactly why it cannot be built.

No CAD happens here, so an agent can call this in a loop until a pattern passes.
"""
import math
from dataclasses import dataclass, field
from functools import lru_cache

from fontTools.ttLib import TTFont

from . import spec as s

PROCESS_TITLES = {
    "3d-print": "3D print",
    "cnc-aluminium": "CNC aluminium",
    "cnc-polymer": "CNC polymer",
    "cnc-ptfe": "CNC PTFE",
}


@dataclass(frozen=True)
class Request:
    name: str
    material: str
    holes: tuple[tuple[float, float], ...] = ()
    screw: str | None = None
    head: str | None = None  # cap, flat or plain
    hole_d: float | None = None  # only for plain holes
    blank: bool = False
    label: str | None = None
    branding: bool = True
    xy_scale: float = 1.0
    deck: float = s.DEFAULT_DECK


@dataclass
class Plan:
    request: Request
    material: s.Material | None = None
    pocket_x: float = s.POCKET_X
    pocket_y: float = s.POCKET_Y
    through_d: float | None = None
    cbore: tuple[float, float] | None = None
    csk_d: float | None = None
    head_r: float = 0.0
    corner_y0: dict = field(default_factory=lambda: {(sx, sy): s.CORNER_TAB_Y0 for sx in (-1, 1) for sy in (-1, 1)})
    engrave_logo: bool = True
    engrave_title: bool = True
    engrave_label: bool = True
    label: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def seat(self) -> float:
        return self.request.deck

    @property
    def top(self) -> float:
        return self.request.deck + s.TAB_H

    @property
    def chamfer_x(self) -> float:
        """A wider pocket thins the corner tabs, so the lead-in gives way to keep room for the edge rounds."""
        return min(s.CHAMFER_IN, s.L / 2 - self.pocket_x / 2 - s.MIN_TAB_LAND)

    @property
    def sleeve_text(self) -> str | None:
        """Solid PTFE only: the screw head bears on a metal sleeve, as long as the floor is thick."""
        if not (self.material and self.material.process == "cnc-ptfe" and self.request.holes and self.cbore):
            return None
        return f"stainless, {self.through_d:g} x 3.2 x {self.seat - self.cbore[1]:g} mm"

    @property
    def title(self) -> str:
        prefix = "Adaptyv OpenNest" if self.request.branding else "OpenNest"
        return f"{prefix} v{s.VERSION}"

    @property
    def ok(self) -> bool:
        return not self.errors


@lru_cache(maxsize=1)
def _font():
    font = TTFont(s.FONT)
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


def text_width(text: str, size: float) -> float:
    cmap, hmtx, em = _font()
    return sum(hmtx[cmap[ord(ch)]][0] for ch in text) * size / em


def can_engrave(text: str) -> bool:
    cmap, _, _ = _font()
    return all(ord(ch) in cmap for ch in text)


def _segment_distance(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy or 1.0)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _inside(p, poly):
    inside = False
    for a, b in zip(poly, poly[1:] + poly[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            inside = not inside
    return inside


def _rect_gap(p, x0, x1, y0, y1):
    """Distance from a point to a rectangle, zero when inside it."""
    return math.hypot(max(x0 - p[0], 0, p[0] - x1), max(y0 - p[1], 0, p[1] - y1))


def _plan_screws(plan: Plan) -> None:
    req, material = plan.request, plan.material
    if req.blank:
        if req.holes or req.screw or req.head:
            plan.errors.append("--blank means no holes: remove --holes, --spacing, --screw and --head.")
        return
    if not req.holes:
        plan.errors.append("No holes given. Pass --holes or --spacing, or --blank for a plate with no holes.")
        return
    if req.head not in ("cap", "flat", "plain"):
        plan.errors.append(f"--head must be cap, flat or plain, not {req.head!r}.")
        return
    if req.head == "plain":
        if not req.hole_d or req.hole_d <= 0:
            plan.errors.append("--head plain needs --hole-d, the through hole diameter in mm.")
            return
        if req.screw:
            plan.errors.append("--head plain takes --hole-d instead of --screw.")
            return
        plan.through_d, plan.head_r = req.hole_d, req.hole_d / 2
        return
    screw = s.SCREWS.get(req.screw or "")
    if screw is None:
        plan.errors.append(f"--screw must be one of {', '.join(s.SCREWS)}, not {req.screw!r}.")
        return
    plan.through_d = screw.clear
    if req.head == "cap":
        if screw.cap is None:
            plan.errors.append(f"No cap head size is defined for {req.screw}. Use --head flat.")
            return
        depth = screw.cap[1]
        plan.cbore = screw.cap
        plan.head_r = screw.cap[0] / 2
    else:
        if screw.flat is None:
            plan.errors.append(f"No flat head size is defined for {req.screw}. Use --head cap, or M3 and up.")
            return
        depth = (screw.flat - screw.clear) / 2
        plan.csk_d = screw.flat
        plan.head_r = screw.flat / 2
    floor = plan.seat - depth
    if floor < s.MIN_FLOOR - 1e-9:
        plan.errors.append(
            f"An {req.screw} {req.head} head sinks {depth:g} mm into the {plan.seat:g} mm deck and leaves {floor:g} mm under it. "
            f"The minimum is {s.MIN_FLOOR} mm. Use --deck {depth + s.MIN_FLOOR:g} or more"
            + (", or --head flat." if req.head == "cap" else ".")
        )
        return
    if material and material.process == "cnc-ptfe":
        if req.head != "cap" or screw.sleeve_od is None:
            plan.errors.append("Solid PTFE creeps under a screw head, so it takes M3 cap heads on metal sleeves only.")
            return
        plan.through_d = screw.sleeve_od


def _plan_holes(plan: Plan) -> None:
    req = plan.request
    if len(req.holes) > s.MAX_HOLES:
        plan.errors.append(f"{len(req.holes)} holes is more than the limit of {s.MAX_HOLES}.")
        return
    poly = s.outline()
    edges = list(zip(poly, poly[1:] + poly[:1]))
    wall_x, wall_y = plan.pocket_x / 2, plan.pocket_y / 2
    r = plan.head_r
    for p in req.holes:
        x, y = p
        tag = f"Hole at X {x:g}, Y {y:g}"
        if not _inside(p, poly):
            plan.errors.append(f"{tag} is outside the plate. The plate spans X +-{s.L / 2:g}, Y +-{s.W / 2:g}, with notches at |X| < {s.NOTCH_W / 2:g}, |Y| > {s.W / 2 - s.NOTCH_D:g}.")
            continue
        land = min(_segment_distance(p, a, b) for a, b in edges) - r
        if land < s.MIN_LAND:
            plan.errors.append(f"{tag}: its {2 * r:g} mm head leaves {land:.2f} mm to the plate edge or a notch. Move it at least {s.MIN_LAND - land:.2f} mm inward.")
        sx, sy = (1 if x >= 0 else -1), (1 if y >= 0 else -1)
        ax, ay = abs(x), abs(y)
        side_gap = _rect_gap((ax, ay), *s.SIDE_TAB_X, wall_y, s.W / 2) - r
        if side_gap < s.MIN_TAB_GAP:
            plan.errors.append(f"{tag}: its head is {side_gap:.2f} mm from a side tab, which spans |X| {s.SIDE_TAB_X[0]:g} to {s.SIDE_TAB_X[1]:g} at |Y| > {wall_y:g}. Keep {s.MIN_TAB_GAP} mm clear.")
        corner_gap = _rect_gap((ax, ay), wall_x, s.L / 2, s.CORNER_TAB_Y0, s.W / 2) - r
        if corner_gap < s.MIN_TAB_GAP:
            start = ay + r + s.CORNER_TAB_GAP
            if start > s.CORNER_TAB_Y0_MAX:
                plan.errors.append(f"{tag}: its head hits a corner tab, and moving the tab start to |Y| {start:g} would leave it too short. Move the hole to |Y| <= {s.CORNER_TAB_Y0_MAX - r - s.CORNER_TAB_GAP:g}, or inward of |X| {wall_x - r - s.MIN_TAB_GAP:g}.")
            else:
                plan.corner_y0[(sx, sy)] = max(plan.corner_y0[(sx, sy)], start)
    for i, a in enumerate(req.holes):
        for b in req.holes[i + 1 :]:
            gap = math.hypot(a[0] - b[0], a[1] - b[1]) - 2 * r
            if gap < s.MIN_HOLE_GAP:
                plan.errors.append(f"Holes at {a} and {b} leave {gap:.2f} mm between their heads. Keep {s.MIN_HOLE_GAP} mm.")
    shortened = {k: v for k, v in plan.corner_y0.items() if v > s.CORNER_TAB_Y0}
    if shortened:
        starts = ", ".join(f"{v:g}" for v in sorted(set(shortened.values())))
        plan.warnings.append(f"{len(shortened)} corner tab(s) start at |Y| {starts} instead of {s.CORNER_TAB_Y0:g} to clear screw heads. The plate is still guided by all eight tabs.")
    if req.holes:
        cx, cy = sum(p[0] for p in req.holes) / len(req.holes), sum(p[1] for p in req.holes) / len(req.holes)
        if math.hypot(cx, cy) > 0.5:
            plan.warnings.append(f"The holes are centred on X {cx:.2f}, Y {cy:.2f}, not on the plate. Check that is what your deck needs.")


def _plan_engraving(plan: Plan) -> None:
    req = plan.request
    plan.label = req.label if req.label is not None else ("Blank" if req.blank else None)
    if plan.label is not None and not plan.label.strip():
        plan.errors.append("--label is empty. Leave it out for no label.")
        plan.label = None
    if plan.label and not can_engrave(plan.label):
        cmap, _, _ = _font()
        missing = "".join(sorted({ch for ch in plan.label if ord(ch) not in cmap}))
        plan.errors.append(f"--label {plan.label!r} has characters the engraving font lacks: {missing!r}. Use Latin, Greek or Cyrillic text.")
        return
    if plan.label and text_width(plan.label, s.SUB_H) > text_width(plan.title, s.TITLE_H):
        plan.errors.append(f"--label {plan.label!r} is wider than the title line above it, {text_width(plan.title, s.TITLE_H):.0f} mm at this size. Shorten it.")
    if not req.branding:
        plan.engrave_logo = False
    r = plan.head_r + 1.0
    half_logo = s.LOGO_H / 2
    half_title = text_width(plan.title, s.TITLE_H) / 2 + 0.5
    title_bottom = s.TITLE_CENTER[1] - s.TITLE_H / 2
    for x, y in req.holes:
        if plan.engrave_logo and _rect_gap((x, y), s.LOGO_CENTER[0] - half_logo, s.LOGO_CENTER[0] + half_logo, s.LOGO_CENTER[1] - half_logo, s.LOGO_CENTER[1] + half_logo) < r:
            plan.engrave_logo = False
            plan.warnings.append("A hole lands on the engraved mark, so the mark is left off.")
        if plan.engrave_title and _rect_gap((x, y), -half_title, half_title, title_bottom, s.TITLE_CENTER[1] + s.TITLE_H / 2) < r:
            plan.engrave_title = False
            plan.warnings.append("A hole lands on the engraved title and version, so they are left off the plate. Move the hole if you want them.")
        if plan.label and plan.engrave_label:
            left = half_title - text_width(plan.label, s.SUB_H) - 0.5
            if _rect_gap((x, y), left, half_title, title_bottom - s.SUB_GAP - s.SUB_H, title_bottom - s.SUB_GAP) < r:
                plan.engrave_label = False
                plan.warnings.append(f"A hole lands on the engraved label {plan.label!r}, so it is left off the plate. Move the hole if you want it.")


def make_plan(req: Request) -> Plan:
    plan = Plan(req)
    plan.material = s.MATERIALS.get(req.material)
    if plan.material is None:
        plan.errors.append(f"--material must be one of {', '.join(s.MATERIALS)}, not {req.material!r}.")
        return plan
    if not req.name or any(c in req.name for c in "/\\ ") or req.name.startswith("."):
        plan.errors.append(f"--name {req.name!r} must be a plain folder name, with no spaces or slashes.")
    if not s.MIN_DECK <= req.deck <= s.MAX_DECK:
        plan.errors.append(f"--deck {req.deck:g} is outside {s.MIN_DECK:g} to {s.MAX_DECK:g} mm.")
        return plan
    plan.pocket_x, plan.pocket_y = s.pocket_for(plan.material)
    plan.warnings.append(s.test_status(plan.material))
    if req.deck != s.DEFAULT_DECK:
        plan.warnings.append(f"The deck is {req.deck:g} mm, not the default {s.DEFAULT_DECK:g} mm, so the seat is {abs(req.deck - s.DEFAULT_DECK):g} mm {'higher' if req.deck > s.DEFAULT_DECK else 'lower'} than the printed reference. Teach plate heights again. This deck thickness has not been made.")
    _plan_screws(plan)
    if plan.errors:
        return plan
    _plan_holes(plan)
    _plan_engraving(plan)
    process = plan.material.process
    if req.xy_scale != 1.0:
        if process != "3d-print":
            plan.errors.append("--xy-scale corrects print shrink, so it applies to 3D printed materials only.")
        elif not 0.98 <= req.xy_scale <= 1.02:
            plan.errors.append(f"--xy-scale {req.xy_scale} is more than 2% from 1. Check the measurement.")
    if process == "3d-print":
        plan.warnings.append("Print shrink closes the pocket. Measure it (X 128.1 to 128.5, Y 85.8 to 86.2) and rebuild with --xy-scale target/measured if it is off.")
    if process == "cnc-ptfe":
        fx, fy = (plan.pocket_x - s.PLATE_X) / 2, (plan.pocket_y - s.PLATE_Y) / 2
        plan.warnings.append(f"Solid PTFE changes size through 19 to 23 C. The pocket is {plan.pocket_x:g} x {plan.pocket_y:g} mm, so a nominal plate floats about +-{fx:.2f} mm in X and +-{fy:.2f} mm in Y. Use it for 96-well plates only.")
    if process == "cnc-polymer":
        plan.warnings.append("Polymers creep under screw heads. Keep torque low and recheck it after a day.")
    return plan


def summary(plan: Plan) -> dict:
    req = plan.request
    return {
        "name": req.name,
        "version": s.VERSION,
        "ok": plan.ok,
        "errors": plan.errors,
        "warnings": plan.warnings,
        "material": plan.material.title if plan.material else req.material,
        "test_status": s.test_status(plan.material) if plan.material else None,
        "process": plan.material.process if plan.material else None,
        "deck_mm": req.deck,
        "height_mm": plan.top,
        "pocket_mm": [plan.pocket_x, plan.pocket_y],
        "catch_per_side_mm": [round(v, 2) for v in s.capture_per_side(plan.pocket_x, plan.pocket_y)],
        "holes": [list(p) for p in req.holes],
        "screw": req.screw,
        "head": req.head,
        "through_d_mm": plan.through_d,
        "counterbore_mm": plan.cbore,
        "countersink_d_mm": plan.csk_d,
        "sleeve": plan.sleeve_text,
        "corner_tab_start_y_mm": sorted(set(plan.corner_y0.values())),
        "engraving": {"title": plan.title if plan.engrave_title else None, "label": plan.label if plan.engrave_label else None, "mark": plan.engrave_logo},
        "xy_scale": req.xy_scale,
    }
