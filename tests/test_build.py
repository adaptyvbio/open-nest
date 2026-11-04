# SPDX-License-Identifier: MIT
"""Build real parts and read them back. Each takes about 15 s."""
import json

import pytest

from nest import make, parse_spacing
from opennest.plan import Request, make_plan

pytestmark = pytest.mark.slow


def build(tmp_path, **kw):
    plan = make_plan(Request(name="t", **kw))
    assert plan.ok, plan.errors
    code = make(plan, tmp_path, False)
    report = json.loads((tmp_path / "report.json").read_text())
    assert code == 0, report["checks"]["failures"]
    return report


def test_blank_aluminium(tmp_path):
    report = build(tmp_path, material="6082", blank=True)
    assert report["checks"]["count"] > 40
    for name in ("nest.step", "nest.stl", "nest.toml", "drawing.pdf", "report.json"):
        assert (tmp_path / name).exists()


def test_cap_heads_with_a_shortened_tab(tmp_path):
    report = build(tmp_path, material="6082", holes=((62.0, 24.0), (62.0, -24.0), (-62.0, 24.0), (-62.0, -24.0)), screw="M3", head="cap")
    assert report["corner_tab_start_y_mm"] == [29.0]


def test_flat_heads_print_as_a_bambu_project(tmp_path):
    report = build(tmp_path, material="pla", holes=parse_spacing("110x60"), screw="M4", head="flat")
    assert (tmp_path / "nest.3mf").stat().st_size > 100_000
    assert report["process"] == "3d-print"


def test_xy_scale_scales_the_mesh_and_not_the_step(tmp_path):
    import trimesh

    build(tmp_path, material="pla", blank=True, xy_scale=1.003)
    x, y, z = trimesh.load_mesh(tmp_path / "nest.stl").extents
    assert x == pytest.approx(134 * 1.003, abs=0.01) and y == pytest.approx(94 * 1.003, abs=0.01) and z == pytest.approx(11, abs=0.01)
    assert "1.003" in (tmp_path / "nest.toml").read_text()


def test_ptfe_builds_with_its_wider_pocket(tmp_path):
    report = build(tmp_path, material="ptfe", holes=parse_spacing("110x60"), screw="M3", head="cap")
    assert report["pocket_mm"] == [129.0, 86.5]
    assert report["sleeve"] is True
