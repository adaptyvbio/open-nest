# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Rebuild the reference plates, with no holes, in models/.

    uv run cad/release.py
"""
import json
import sys

from nest import make
from opennest import spec as s
from opennest.plan import Request, make_plan
from opennest.record import to_toml, version_reference

# folder, material, and the built files that do not belong in that folder
REFERENCES = (
    ("3d-print", "pla", ("nest.step",)),
    ("cnc-aluminium", "6082", ("nest.stl",)),
    ("cnc-pom-c", "pom-c", ("nest.stl",)),
    ("cnc-ptfe", "ptfe", ("nest.stl",)),
)


def main() -> int:
    status = 0
    versions = s.REPO / "docs" / "versions"
    versions.mkdir(exist_ok=True)
    (versions / f"v{s.VERSION}.toml").write_text(to_toml(version_reference(), f"OpenNest v{s.VERSION}. All dimensions in mm."))
    for folder, material, drop in REFERENCES:
        out = s.REPO / "models" / folder
        plan = make_plan(Request(name=f"blank-{folder}", material=material, blank=True))
        code = make(plan, out, False)
        status = status or code
        for name in drop:
            (out / name).unlink(missing_ok=True)
        record = out / "nest.toml"  # a committed file cannot name the commit that adds it
        record.write_text("".join(line for line in record.read_text().splitlines(keepends=True) if not line.startswith("commit = ")))
        report_path = out / "report.json"
        report = json.loads(report_path.read_text())
        report["files"] = [f for f in report["files"] if f not in drop]
        report.pop("seconds", None)
        report_path.write_text(json.dumps(report, indent=1) + "\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
