# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Every fixed dimension of Adaptyv OpenNest, in millimetres.

Frame: X = length, Y = depth, Z up. Origin at the centre of the underside, so the seat is at
Z 5 and the tab tops are at Z 11. The pocket depends on the material, and the holes on the user.
"""
import math
from dataclasses import dataclass
from pathlib import Path

VERSION = "1.4"
REPO = Path(__file__).resolve().parents[2]
LOGO_SVG = REPO / "design/brand/adaptyv-mark.svg"
FONT = REPO / "cad/assets/LiberationSans-Bold.ttf"  # the engraving font; Geist outlines overlap themselves and cannot be cut cleanly
BAMBU_TEMPLATE = REPO / "cad/assets/bambu-h2d-template.3mf"

# ---- envelope and heights
L, W = 134.0, 94.0
SEAT = 5.0  # underside to seat; the seat is the height a deck definition uses
TOP = 11.0  # underside to tab top
R_CORNER = 3.0  # plan-view radius on the four plate corners
R_EDGE = 0.5  # every exposed convex edge; Type II anodise needs no more, thick hardcoat does
BOTTOM_EDGE = 0.5  # underside perimeter break

# ---- tolerances a shop works to
TOL_POCKET = "+0.10/0"
TOL_SEAT = "\u00b10.05"
TOL_FLATNESS = 0.05
TOL_GENERAL = "\u00b10.1, ISO 2768-f"

# ---- guide tabs. The inward wall position comes from the pocket.
CORNER_TAB_Y0 = 24.0  # corner tabs run from here to the plate edge, on the short sides
CORNER_TAB_Y0_MAX = 33.0  # a hole may push a corner tab start back this far, no further
SIDE_TAB_X = (30.0, 56.0)  # side tabs on the long sides
CHAMFER_IN, CHAMFER_UP = 1.732, 3.0  # 30 deg from vertical, starting 3 mm above the seat
MIN_TAB_LAND = 0.85  # top of a tab, room for the R_EDGE rounds on both of its edges
R_BASE = 0.8  # construction only: the R_EDGE rounds chain through this fillet, then it is cut away

# ---- gripper notches, centred on each long side
NOTCH_W, NOTCH_D = 40.0, 8.5
R_NOTCH, R_MOUTH = 4.0, 2.0  # internal corners for an 8 mm end mill, convex mouth corners

# ---- engraving, recessed into the seat so a plate still sits flat
ENGRAVE_DEPTH = 0.3
LOGO_H, LOGO_CENTER = 30.0, (0.0, 7.0)
TITLE_H, TITLE_CENTER = 6.0, (0.0, -17.0)
SUB_H, SUB_GAP = 4.0, 1.5

# ---- rules for user holes
MIN_LAND = 1.0  # screw head to plate edge or notch
MIN_TAB_GAP = 0.5  # screw head to a tab
CORNER_TAB_GAP = 2.0  # screw head to the start of a corner tab it pushed back
MIN_FLOOR = 1.5  # material left under a screw head
MIN_HOLE_GAP = 1.0  # between neighbouring screw heads
MAX_HOLES = 32
R_CBORE = 0.3  # edge break on a counterbore mouth


@dataclass(frozen=True)
class Screw:
    clear: float  # through hole, ISO 273 medium
    cap: tuple[float, float] | None = None  # counterbore diameter and depth, ISO 4762 head flush
    flat: float | None = None  # 90 deg countersink diameter, ISO 10642 head flush
    sleeve_od: float | None = None  # metal sleeve at the screw, for materials that creep


SCREWS = {
    "M2": Screw(2.4, cap=(4.4, 2.1)),
    "M2.5": Screw(2.9, cap=(5.0, 2.6)),
    "M3": Screw(3.4, cap=(6.0, 3.0), flat=6.5, sleeve_od=5.0),
    "M4": Screw(4.5, flat=8.6),  # an M4 cap head needs 4 mm of depth, which leaves 1 mm of floor
    "M5": Screw(5.5, flat=10.8),
    "M6": Screw(6.6, flat=12.9),
}


@dataclass(frozen=True)
class Material:
    key: str
    title: str
    process: str  # 3d-print, cnc-aluminium, cnc-polymer or cnc-ptfe
    cte: float  # um/m/K, a typical handbook value, not measured on any part here
    ref_t: float = 20.0  # temperature the part is made at
    transition: float = 0.0  # linear shrink across a phase change below 19 C


MATERIALS = {
    m.key: m
    for m in (
        Material("pla", "PLA", "3d-print", 68.0),
        Material("petg", "PETG", "3d-print", 68.0),
        Material("asa", "ASA", "3d-print", 90.0),
        Material("6082", "EN AW-6082-T651", "cnc-aluminium", 23.4),
        Material("6061", "6061-T651", "cnc-aluminium", 23.6),
        Material("pom-c", "POM-C", "cnc-polymer", 110.0),
        Material("peek", "PEEK", "cnc-polymer", 47.0),
        Material("ptfe", "Solid PTFE", "cnc-ptfe", 135.0, ref_t=23.0, transition=0.0045),
    )
}

# ---- ANSI SLAS 1-2004, at 20 C. Tolerances do not include draft.
PLATE_X, PLATE_Y = 127.76, 85.48
TOL_CORNER, TOL_SIDE = 0.25, 0.5  # within 12.7 mm of the corners, and anywhere along a side
PLATE_CTE = 70.0  # polystyrene, um/m/K

# ---- pocket sizing
POCKET_X, POCKET_Y = 128.3, 86.0  # the reference pocket
FIT_T_MIN = 15.0  # a machined pocket must still take the largest SLAS plate at this temperature
FIT_MARGIN_X, FIT_MARGIN_Y = 0.04, 0.02  # the reference pocket's own margins at 20 C


def plate_size(tol: float, t: float = 20.0) -> tuple[float, float]:
    k = 1 + PLATE_CTE * 1e-6 * (t - 20.0)
    return (PLATE_X + tol) * k, (PLATE_Y + tol) * k


def pocket_at(nominal: float, material: Material, t: float) -> float:
    size = nominal * (1 + material.cte * 1e-6 * (t - material.ref_t))
    return size * (1 - material.transition) if t < 19.0 else size


def pocket_for(material: Material) -> tuple[float, float]:
    """A print takes the reference pocket and a measured scale. A machined part gets the reference
    pocket, or the next 0.1 mm up that still takes the largest SLAS plate at FIT_T_MIN."""
    if material.process == "3d-print":
        return POCKET_X, POCKET_Y
    max_x, max_y = plate_size(TOL_SIDE, FIT_T_MIN)
    factor = pocket_at(1.0, material, FIT_T_MIN)
    need_x, need_y = (max_x + FIT_MARGIN_X) / factor, (max_y + FIT_MARGIN_Y) / factor
    return (
        max(POCKET_X, math.ceil(need_x * 10 - 1e-9) / 10),
        max(POCKET_Y, math.ceil(need_y * 10 - 1e-9) / 10),
    )


def fit_rows(material: Material, pocket_x: float, pocket_y: float) -> list[dict]:
    """Total clearance in mm for a polystyrene plate. Negative means it does not fit."""
    rows = []
    for t in (15.0, 20.0, 25.0, 37.0):
        for plate, tol in (("nominal", 0.0), ("SLAS max, corner zone", TOL_CORNER), ("SLAS max, along a side", TOL_SIDE)):
            px, py = plate_size(tol, t)
            rows.append(
                {
                    "t_c": t,
                    "plate": plate,
                    "x": round(pocket_at(pocket_x, material, t) - px, 3),
                    "y": round(pocket_at(pocket_y, material, t) - py, 3),
                }
            )
    return rows


def capture_per_side(pocket_x: float, pocket_y: float) -> tuple[float, float]:
    """How far off centre a nominal plate can land and still be caught by the lead-in."""
    return CHAMFER_IN + (pocket_x - PLATE_X) / 2, CHAMFER_IN + (pocket_y - PLATE_Y) / 2


def outline() -> list[tuple[float, float]]:
    """The plate outline as a polygon, for checks and drawings. Corners and notches are sampled arcs."""

    def arc(cx, cy, r, a0, a1, n=12):
        return [
            (cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)
        ]

    x, y = L / 2, W / 2
    nx, ny = NOTCH_W / 2, y - NOTCH_D
    return [
        *arc(-x + R_CORNER, -y + R_CORNER, R_CORNER, 180, 270),
        *arc(-nx - R_MOUTH, -y + R_MOUTH, R_MOUTH, 270, 360),
        *arc(-nx + R_NOTCH, -ny - R_NOTCH, R_NOTCH, 180, 90),
        *arc(nx - R_NOTCH, -ny - R_NOTCH, R_NOTCH, 90, 0),
        *arc(nx + R_MOUTH, -y + R_MOUTH, R_MOUTH, 180, 270),
        *arc(x - R_CORNER, -y + R_CORNER, R_CORNER, 270, 360),
        *arc(x - R_CORNER, y - R_CORNER, R_CORNER, 0, 90),
        *arc(nx + R_MOUTH, y - R_MOUTH, R_MOUTH, 90, 180),
        *arc(nx - R_NOTCH, ny + R_NOTCH, R_NOTCH, 0, -90),
        *arc(-nx + R_NOTCH, ny + R_NOTCH, R_NOTCH, -90, -180),
        *arc(-nx - R_MOUTH, y - R_MOUTH, R_MOUTH, 0, 90),
        *arc(-x + R_CORNER, y - R_CORNER, R_CORNER, 90, 180),
    ]
