# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Build an OpenNest plate with your hole pattern. See AGENTS.md.

    uv run cad/nest.py check --material 6082 --screw M3 --head cap --spacing 110x60
    uv run cad/nest.py make  --material 6082 --screw M3 --head cap --spacing 110x60 --name deck-a --label "Slot A3"
    uv run cad/nest.py make  --material pla --blank
    uv run cad/nest.py make  --config out/deck-a/nest.toml
    uv run cad/nest.py materials
    uv run cad/nest.py spec

Holes are in mm from the plate centre. `check` needs no CAD and returns at once, so call it until
the pattern passes. Exit codes: 0 ok, 2 the request cannot be built, 3 a built part failed its checks.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from opennest import spec as s
from opennest.plan import PROCESS_TITLES, Plan, Request, make_plan, summary


def parse_holes(text: str) -> tuple[tuple[float, float], ...]:
    holes = []
    for item in text.replace(";", " ").split():
        x, y = item.split(",")
        holes.append((float(x), float(y)))
    return tuple(holes)


def parse_spacing(text: str) -> tuple[tuple[float, float], ...]:
    """110x60 is four holes on a centred rectangle. 110 is two holes on the X axis."""
    parts = text.lower().split("x")
    a = float(parts[0]) / 2
    if len(parts) == 1:
        return ((-a, 0.0), (a, 0.0))
    b = float(parts[1]) / 2
    return ((-a, -b), (-a, b), (a, -b), (a, b))


def request_from(args) -> Request:
    if not args.material:
        raise SystemExit("--material is required, unless you build from --config.")
    if args.holes and args.spacing:
        raise SystemExit("Use --holes or --spacing, not both.")
    try:
        holes = parse_holes(args.holes) if args.holes else parse_spacing(args.spacing) if args.spacing else ()
    except ValueError:
        raise SystemExit("Could not read the holes. Use --holes \"x,y x,y\" or --spacing 110x60.") from None
    return Request(
        name=args.name,
        material=args.material,
        holes=holes,
        screw=args.screw,
        head=args.head,
        hole_d=args.hole_d,
        blank=args.blank,
        label=args.label,
        branding=not args.no_branding,
        xy_scale=args.xy_scale,
    )


def print_plan(plan: Plan, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary(plan), indent=1))
        return
    for error in plan.errors:
        print("ERROR  ", error)
    for warning in plan.warnings:
        print("WARNING", warning)
    if plan.ok:
        print(f"OK      {plan.material.title}, pocket {plan.pocket_x:g} x {plan.pocket_y:g} mm, {len(plan.request.holes)} holes.")


def make(plan: Plan, out: Path, as_json: bool) -> int:
    import cadquery as cq

    from opennest.bambu import write_plain_3mf, write_project
    from opennest.drawing import write_drawing
    from opennest.geometry import build
    from opennest.record import write_record
    from opennest.verify import clean_stl, verify_mesh, verify_step

    start = time.time()
    out.mkdir(parents=True, exist_ok=True)
    body, log = build(plan)
    step, stl = out / "nest.step", out / "nest.stl"
    cq.exporters.export(body, str(step))
    cq.exporters.export(body, str(stl), tolerance=0.02, angularTolerance=0.2)
    clean_stl(stl, plan.request.xy_scale)
    solid_checks, mesh_checks = verify_step(plan, step), verify_mesh(stl)
    failures = solid_checks.failures + mesh_checks.failures
    record = out / "nest.toml"
    write_record(plan, record)
    files = [step, stl, record]
    if not failures:
        if plan.material.process == "3d-print":
            project = out / "nest.3mf"
            if plan.request.material == "pla":
                write_project(plan, stl, project)
            else:
                write_plain_3mf(stl, project)
            files.append(project)
        else:
            drawing = out / "drawing.pdf"
            write_drawing(plan, drawing)
            files.append(drawing)

    report = summary(plan)
    report.update(
        {
            "ok": not failures,
            "checks": {"count": solid_checks.count + mesh_checks.count, "failures": failures},
            "fillets": log,
            "fit_clearance_mm": s.fit_rows(plan.material, plan.pocket_x, plan.pocket_y),
            "volume_cm3": round(body.val().Volume() / 1000, 2),
            "not_checked": ["Whether the holes match your deck: measure it before you cut.", "Fit on real plates and on a robot."],
            "files": [f.name for f in files] + ["report.json"],
            "seconds": round(time.time() - start),
        }
    )
    (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    if as_json:
        print(json.dumps(report, indent=1))
    else:
        for warning in plan.warnings:
            print("WARNING", warning)
        print(f"{report['checks']['count'] - len(failures)}/{report['checks']['count']} checks passed in {report['seconds']} s.")
        for failure in failures:
            print("FAILED ", failure)
        print("Wrote  ", ", ".join(str(out / name) for name in report["files"]))
    return 3 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "make"):
        p = sub.add_parser(name)
        p.add_argument("--config", type=Path, help="build from a nest.toml design record, instead of the flags below")
        p.add_argument("--material", choices=list(s.MATERIALS))
        p.add_argument("--holes", help='mm from the plate centre, for example "55,30 55,-30 -55,30 -55,-30"')
        p.add_argument("--spacing", help="110x60 for four holes on a centred rectangle, 110 for two on the X axis")
        p.add_argument("--screw", choices=list(s.SCREWS))
        p.add_argument("--head", choices=["cap", "flat", "plain"])
        p.add_argument("--hole-d", type=float, help="through hole diameter, only with --head plain")
        p.add_argument("--blank", action="store_true", help="a plate with no holes")
        p.add_argument("--name", default="nest", help="output folder name under out/")
        p.add_argument("--label", help="free text engraved under the title and version, such as a slot name")
        p.add_argument("--no-branding", action="store_true", help="engrave OpenNest only, with no Adaptyv name or mark")
        p.add_argument("--xy-scale", type=float, default=1.0, help="print shrink correction, target / measured")
        p.add_argument("--out", type=Path, help="output folder, default out/<name>")
        p.add_argument("--json", action="store_true", help="print the result as JSON")
    sub.add_parser("materials")
    sub.add_parser("spec", help="print every fixed dimension of this version")
    args = parser.parse_args()

    if args.command == "materials":
        for m in s.MATERIALS.values():
            x, y = s.pocket_for(m)
            print(f"{m.key:7s} {PROCESS_TITLES[m.process]:14s} {m.title:18s} pocket {x:g} x {y:g} mm")
        return 0

    if args.command == "spec":
        from opennest.record import to_toml, version_reference

        print(to_toml(version_reference(), f"OpenNest v{s.VERSION}. All dimensions in mm."), end="")
        return 0

    if args.config:
        from opennest.record import read_request

        request, built_version, commit = read_request(args.config)
        plan = make_plan(request)
        if built_version != s.VERSION:
            where = f"Check out commit {commit} to build it exactly." if commit else "Check out that version to build it exactly."
            plan.warnings.append(f"This record is from v{built_version}, and this repo is v{s.VERSION}, so the fixed geometry may differ. {where}")
    else:
        plan = make_plan(request_from(args))
    if not plan.ok or args.command == "check":
        print_plan(plan, args.json)
        return 0 if plan.ok else 2
    return make(plan, args.out or s.REPO / "out" / args.name, args.json)


if __name__ == "__main__":
    sys.exit(main())
