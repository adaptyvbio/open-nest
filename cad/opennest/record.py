# SPDX-License-Identifier: CERN-OHL-P-2.0
"""The design record: every dimension of a built plate, its version, and how to build it again."""
import json
import subprocess
import tomllib
from datetime import date
from pathlib import Path

from . import spec as s
from .plan import Plan, Request


def _git_commit() -> str | None:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=s.REPO, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "cad"], cwd=s.REPO, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}-modified" if dirty else commit


def command_for(req: Request) -> str:
    parts = ["uv run cad/nest.py make", f"--material {req.material}", f"--name {req.name}"]
    if req.blank:
        parts.append("--blank")
    if req.holes:
        parts.append('--holes "' + " ".join(f"{x:g},{y:g}" for x, y in req.holes) + '"')
    if req.screw:
        parts.append(f"--screw {req.screw}")
    if req.head:
        parts.append(f"--head {req.head}")
    if req.hole_d:
        parts.append(f"--hole-d {req.hole_d:g}")
    if req.label is not None:
        parts.append(f"--label {json.dumps(req.label, ensure_ascii=False)}")
    if not req.branding:
        parts.append("--no-branding")
    if req.xy_scale != 1.0:
        parts.append(f"--xy-scale {req.xy_scale:g}")
    return " ".join(parts)


def fixed_dimensions() -> dict:
    """What every plate of this version shares, in mm. The pocket depends on the material."""
    return {
        "plate": {
            "length_x": s.L,
            "depth_y": s.W,
            "height_z": s.TOP,
            "seat_above_underside": s.SEAT,
            "tab_above_seat": s.TOP - s.SEAT,
            "corner_radius": s.R_CORNER,
            "edge_radius": s.R_EDGE,
            "underside_break": s.BOTTOM_EDGE,
        },
        "tolerances": {
            "pocket": s.TOL_POCKET,
            "seat_height": s.TOL_SEAT,
            "seat_flatness": s.TOL_FLATNESS,
            "general": s.TOL_GENERAL,
        },
        "tabs": {
            "count": 8,
            "corner_tab_y_from": s.CORNER_TAB_Y0,
            "corner_tab_y_to": s.W / 2,
            "side_tab_x_from": s.SIDE_TAB_X[0],
            "side_tab_x_to": s.SIDE_TAB_X[1],
            "lead_in_degrees_from_vertical": 30,
            "lead_in_up": s.CHAMFER_UP,
            "lead_in_inward": s.CHAMFER_IN,
            "straight_wall_above_seat": s.CHAMFER_UP,
        },
        "notches": {"count": 2, "width_x": s.NOTCH_W, "depth_y": s.NOTCH_D, "inside_radius": s.R_NOTCH, "mouth_radius": s.R_MOUTH},
        "engraving": {"depth": s.ENGRAVE_DEPTH, "title_em": s.TITLE_H, "label_em": s.SUB_H, "mark_height": s.LOGO_H},
        "plate_standard": {
            "standard": "ANSI SLAS 1-2004, at 20 C",
            "nominal_x": s.PLATE_X,
            "nominal_y": s.PLATE_Y,
            "tolerance_within_12_7_mm_of_corners": s.TOL_CORNER,
            "tolerance_along_a_side": s.TOL_SIDE,
        },
    }


def version_reference() -> dict:
    """The reference file kept in the repo for this version."""
    pockets = {key: {"process": m.process, "pocket_x": s.pocket_for(m)[0], "pocket_y": s.pocket_for(m)[1]} for key, m in s.MATERIALS.items()}
    return {"design": {"opennest_version": s.VERSION, "origin": "plate centre, Z 0 at the underside", "units": "mm"}, **fixed_dimensions(), "pocket_by_material": pockets}


def design_record(plan: Plan) -> dict:
    req = plan.request
    data = fixed_dimensions()
    data["tabs"]["corner_tab_y_from"] = sorted(set(plan.corner_y0.values()))
    data["tabs"]["lead_in_inward_corner_tabs"] = round(plan.chamfer_x, 3)
    data["engraving"].update({"title": plan.title if plan.engrave_title else "", "label": (plan.label or "") if plan.engrave_label else "", "mark": plan.engrave_logo})
    design = {
        "opennest_version": s.VERSION,
        "name": req.name,
        "label": plan.label or "",
        "built": date.today().isoformat(),
        "command": command_for(req),
        "origin": "plate centre, Z 0 at the underside",
        "units": "mm",
    }
    commit = _git_commit()
    if commit:
        design["commit"] = commit
    request = {"name": req.name, "material": req.material, "branding": req.branding, "xy_scale": req.xy_scale, "blank": req.blank}
    if req.label is not None:
        request["label"] = req.label
    if req.holes:
        request["holes"] = [[x, y] for x, y in req.holes]
    if req.screw:
        request["screw"] = req.screw
    if req.head:
        request["head"] = req.head
    if req.hole_d:
        request["hole_d"] = req.hole_d
    holes = {"count": len(req.holes)}
    if req.holes:
        holes["positions_xy"] = [[x, y] for x, y in req.holes]
        holes["through_d"] = plan.through_d
        if plan.cbore:
            holes["counterbore_d"], holes["counterbore_depth"] = plan.cbore
            holes["floor_under_head"] = round(s.SEAT - plan.cbore[1], 3)
        if plan.csk_d:
            holes["countersink_d"] = plan.csk_d
            holes["countersink_degrees"] = 90
        if plan.material.process == "cnc-ptfe":
            holes["sleeve"] = "stainless, 5 x 3.2 x 2.0 mm"
    catch_x, catch_y = s.capture_per_side(plan.pocket_x, plan.pocket_y)
    catch_x -= s.CHAMFER_IN - plan.chamfer_x
    return {
        "design": design,
        "request": request,
        "material": {"title": plan.material.title, "process": plan.material.process},
        "pocket": {
            "x": plan.pocket_x,
            "y": plan.pocket_y,
            "catch_per_side_x": round(catch_x, 2),
            "catch_per_side_y": round(catch_y, 2),
            "float_per_side_x": round((plan.pocket_x - s.PLATE_X) / 2, 2),
            "float_per_side_y": round((plan.pocket_y - s.PLATE_Y) / 2, 2),
        },
        "holes": holes,
        **data,
    }


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return "[" + ", ".join(_value(i) for i in v) + "]"


def to_toml(data: dict, header: str = "") -> str:
    lines = [f"# {line}" for line in header.splitlines()]
    for section, values in data.items():
        lines.append("")
        lines.append(f"[{section}]")
        nested = {k: v for k, v in values.items() if isinstance(v, dict)}
        for key, value in values.items():
            if not isinstance(value, dict):
                lines.append(f"{key} = {_value(value)}")
        for key, value in nested.items():
            lines.append("")
            lines.append(f"[{section}.{key}]")
            for k, v in value.items():
                lines.append(f"{k} = {_value(v)}")
    return "\n".join(lines).lstrip("\n") + "\n"


def write_record(plan: Plan, path: Path) -> None:
    header = f"OpenNest design record, v{s.VERSION}. All dimensions in mm.\nTo build this part again: uv run cad/nest.py make --config {path.name}"
    path.write_text(to_toml(design_record(plan), header))


def read_request(path: Path) -> tuple[Request, str, str | None]:
    """A request from a design record, with the version and commit it was built from."""
    with path.open("rb") as f:
        data = tomllib.load(f)
    r = data["request"]
    design = data.get("design", {})
    request = Request(
        name=r.get("name", "nest"),
        material=r["material"],
        label=r.get("label"),
        holes=tuple(tuple(p) for p in r.get("holes", ())),
        screw=r.get("screw"),
        head=r.get("head"),
        hole_d=r.get("hole_d"),
        blank=r.get("blank", False),
        branding=r.get("branding", True),
        xy_scale=r.get("xy_scale", 1.0),
    )
    return request, design.get("opennest_version", "unknown"), design.get("commit")
