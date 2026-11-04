# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Check a built plate against its plan by probing the STEP file a shop would receive.

A probe asks the solid whether a point is inside it, so these checks read the geometry itself,
not the numbers that made it.
"""
import math

import cadquery as cq
import trimesh

from . import spec as s
from .plan import Plan

EPS = 0.02


class Checks:
    def __init__(self):
        self.count, self.failures = 0, []

    def __call__(self, label, ok, detail=""):
        self.count += 1
        if not ok:
            self.failures.append(f"{label} {detail}".strip())


def verify_step(plan: Plan, path) -> Checks:
    check = Checks()
    solids = cq.importers.importStep(str(path)).solids().vals()
    check("one solid", len(solids) == 1, f"got {len(solids)}")
    if not solids:
        return check
    solid = solids[0]
    check("valid solid", solid.isValid())
    bb = solid.BoundingBox()
    check("envelope", abs(bb.xlen - s.L) < 0.01 and abs(bb.ylen - s.W) < 0.01 and abs(bb.zlen - plan.top) < 0.01, f"{bb.xlen:.3f} x {bb.ylen:.3f} x {bb.zlen:.3f}")

    def inside(x, y, z):
        return solid.isInside(cq.Vector(x, y, z), 1e-4)

    wx, wy = plan.pocket_x / 2, plan.pocket_y / 2
    x_tab = sum(s.SIDE_TAB_X) / 2
    z_wall = plan.seat + 1.5
    for sx in (-1, 1):
        for sy in (-1, 1):
            y_tab = (plan.corner_y0[(sx, sy)] + wy) / 2
            tag = f"at sign X {sx}, Y {sy}"
            check("X wall", inside(sx * (wx + EPS), sy * y_tab, z_wall) and not inside(sx * (wx - EPS), sy * y_tab, z_wall), tag)
            check("Y wall", inside(sx * x_tab, sy * (wy + EPS), z_wall) and not inside(sx * x_tab, sy * (wy - EPS), z_wall), tag)
            for z in (plan.seat + 0.05, plan.top - s.CHAMFER_UP - 0.6):  # straight from the seat to where the slope starts
                check("wall straight", inside(sx * (wx + EPS), sy * y_tab, z) and not inside(sx * (wx - EPS), sy * y_tab, z), f"{tag} Z {z:.2f}")
            mid = plan.top - s.CHAMFER_UP / 2
            check("lead-in X", not inside(sx * (wx + plan.chamfer_x / 2 - EPS), sy * y_tab, mid) and inside(sx * (wx + plan.chamfer_x / 2 + EPS), sy * y_tab, mid), tag)
            check("lead-in Y", not inside(sx * x_tab, sy * (wy + s.CHAMFER_IN / 2 - EPS), mid) and inside(sx * x_tab, sy * (wy + s.CHAMFER_IN / 2 + EPS), mid), tag)
            x_top = (wx + plan.chamfer_x + s.L / 2) / 2  # middle of the land, where the two edge rounds meet or leave a flat
            check("tab top", inside(sx * x_top, sy * y_tab, plan.top - 0.05) and not inside(sx * x_top, sy * y_tab, plan.top + EPS), tag)
            # the seat is flat right up to the walls, so nothing lifts the edge of a plate
            for x, y in ((wx - 0.05, y_tab), (x_tab, wy - 0.05)):
                check("seat at the wall", inside(sx * x, sy * y, plan.seat - EPS) and not inside(sx * x, sy * y, plan.seat + EPS), f"{tag} at {x:.2f}, {y:.2f}")

    for sy in (-1, 1):
        notch_floor = s.W / 2 - s.NOTCH_D
        check("notch", not inside(0, sy * (notch_floor + 0.1), plan.seat / 2) and inside(0, sy * (notch_floor - 0.1), plan.seat / 2))

    for x, y in plan.request.holes:
        tag = f"at {x:g}, {y:g}"
        r = plan.through_d / 2
        if plan.cbore:
            d, depth = plan.cbore
            floor = plan.seat - depth
            for a in (0, 90, 180, 270):
                ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
                check("through hole", not inside(x + ux * (r - EPS), y + uy * (r - EPS), floor / 2) and inside(x + ux * (r + EPS), y + uy * (r + EPS), floor / 2), tag)
                z = floor + depth / 2
                check("counterbore wall", not inside(x + ux * (d / 2 - EPS), y + uy * (d / 2 - EPS), z) and inside(x + ux * (d / 2 + EPS), y + uy * (d / 2 + EPS), z), tag)
                mid_r = (r + d / 2) / 2
                check("counterbore floor", inside(x + ux * mid_r, y + uy * mid_r, floor - EPS) and not inside(x + ux * mid_r, y + uy * mid_r, floor + EPS), tag)
        elif plan.csk_d:
            R = plan.csk_d / 2
            for a in (0, 90, 180, 270):
                ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
                check("through hole", not inside(x + ux * (r - EPS), y + uy * (r - EPS), 0.3) and inside(x + ux * (r + EPS), y + uy * (r + EPS), 0.3), tag)
                # 90 deg: the wall steps in 1 mm per mm of depth
                for depth in (0.05, (R - r) / 2):
                    rc = R - depth
                    z = plan.seat - depth
                    check("countersink 90 deg", not inside(x + ux * (rc - 0.05), y + uy * (rc - 0.05), z) and inside(x + ux * (rc + 0.05), y + uy * (rc + 0.05), z), f"{tag} depth {depth:.2f}")
        else:
            for a in (0, 90, 180, 270):
                ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
                check("through hole", not inside(x + ux * (r - EPS), y + uy * (r - EPS), plan.seat / 2) and inside(x + ux * (r + EPS), y + uy * (r + EPS), plan.seat / 2), tag)
    return check


def clean_stl(path, xy_scale: float = 1.0) -> None:
    """Weld the exported mesh, drop the zero-area slivers that meshing a curved outline leaves, and
    apply any print shrink correction. The STEP file stays at true size."""
    mesh = trimesh.load_mesh(path)
    mesh.merge_vertices(digits_vertex=4)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    if xy_scale != 1.0:
        mesh.apply_scale((xy_scale, xy_scale, 1.0))
    mesh.export(path)


def verify_mesh(path) -> Checks:
    check = Checks()
    mesh = trimesh.load_mesh(path)
    check("watertight mesh", mesh.is_watertight)
    check("consistent winding", mesh.is_winding_consistent)
    return check
