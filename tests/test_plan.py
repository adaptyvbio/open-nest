# SPDX-License-Identifier: MIT
"""Fast checks on the rules a hole pattern must pass. No CAD."""
import pytest

from nest import parse_holes, parse_spacing
from opennest import spec as s
from opennest.plan import Request, make_plan
from opennest.record import command_for, design_record, read_request, to_toml, version_reference, write_record


def plan(**kw):
    kw.setdefault("name", "t")
    kw.setdefault("material", "6082")
    return make_plan(Request(**kw))


def cap(holes, **kw):
    return plan(holes=holes, screw="M3", head="cap", **kw)


def test_spacing_is_centred():
    assert set(parse_spacing("110x60")) == {(-55, -30), (-55, 30), (55, -30), (55, 30)}
    assert set(parse_spacing("110")) == {(-55, 0), (55, 0)}


def test_holes_parse():
    assert parse_holes("55,30 -55,-30") == ((55, 30), (-55, -30))


def test_rectangle_passes():
    p = cap(parse_spacing("110x60"))
    assert p.ok and p.through_d == 3.4 and p.cbore == (6.0, 3.0)
    assert set(p.corner_y0.values()) == {s.CORNER_TAB_Y0}


def test_blank_is_labelled_and_needs_no_screws():
    p = plan(blank=True)
    assert p.ok and p.label == "Blank"
    assert not plan(blank=True, holes=((0, 30),)).ok


def test_no_holes_without_blank_is_an_error():
    assert not plan().ok


@pytest.mark.parametrize(
    "hole, message",
    [
        ((80, 0), "outside the plate"),
        ((0, 42), "outside the plate"),
        ((65, 0), "plate edge"),
        ((40, 40), "side tab"),
    ],
)
def test_bad_holes_say_why(hole, message):
    p = cap((hole,))
    assert not p.ok and any(message in e for e in p.errors)


def test_a_hole_near_a_corner_tab_pushes_only_that_tab_back():
    p = cap(((62.0, 24.0), (-62.0, -24.0)))
    assert p.ok
    assert p.corner_y0[(1, 1)] == 29.0 and p.corner_y0[(-1, -1)] == 29.0
    assert p.corner_y0[(1, -1)] == s.CORNER_TAB_Y0
    assert any("corner tab" in w for w in p.warnings)


def test_a_tab_cannot_be_pushed_back_too_far():
    p = cap(((62.0, 30.0),))
    assert not p.ok and any("corner tab" in e for e in p.errors)


def test_heads_must_not_touch():
    assert not cap(((10, 30), (15, 30))).ok


def test_m4_cap_head_needs_a_thicker_deck():
    thin = plan(holes=parse_spacing("110x60"), screw="M4", head="cap")
    assert not thin.ok and any("--deck 5.5" in e for e in thin.errors)
    assert plan(holes=parse_spacing("110x60"), screw="M4", head="cap", deck=5.5).ok
    flat = plan(holes=parse_spacing("110x60"), screw="M4", head="flat")
    assert flat.ok and flat.csk_d == 8.6


def test_deck_sets_the_seat_and_height():
    p = plan(blank=True, deck=8.0)
    assert p.ok and p.seat == 8.0 and p.top == 14.0


@pytest.mark.parametrize("deck", [1.0, 40.0])
def test_deck_must_be_in_range(deck):
    p = plan(blank=True, deck=deck)
    assert not p.ok and any("--deck" in e for e in p.errors)


def test_thin_deck_rejects_a_flat_head_that_would_break_through():
    p = plan(holes=parse_spacing("110x60"), screw="M6", head="flat", deck=3.0)
    assert not p.ok and any("--deck" in e for e in p.errors)


def test_a_non_default_deck_warns_about_height_and_testing():
    p = plan(blank=True, deck=8.0)
    assert any("Teach plate heights again" in w and "has not been made" in w for w in p.warnings)
    assert not any("Teach" in w for w in plan(blank=True).warnings)


def test_deck_is_in_the_record(tmp_path):
    req = Request(name="thick", material="6082", blank=True, deck=7.5)
    path = tmp_path / "nest.toml"
    write_record(make_plan(req), path)
    back, _, _ = read_request(path)
    assert back == req
    record = design_record(make_plan(req))
    assert record["plate"]["deck_thickness"] == 7.5 and record["plate"]["height_z"] == 13.5
    assert "--deck 7.5" in command_for(req)


def test_ptfe_sleeve_length_follows_the_deck():
    p = plan(material="ptfe", holes=parse_spacing("110x60"), screw="M3", head="cap", deck=6.0)
    assert p.ok and p.sleeve_text == "stainless, 5 x 3.2 x 3 mm"


def test_plain_hole_needs_a_diameter():
    assert not plan(holes=((0, 30),), head="plain").ok
    assert plan(holes=((0, 30),), head="plain", hole_d=4.2).ok


def test_off_centre_pattern_warns():
    p = cap(((30, 20), (40, 20)))
    assert p.ok and any("centred" in w for w in p.warnings)


def test_holes_on_the_engraving_drop_it():
    p = cap(((-5, 7), (5, -17)))
    assert p.ok and not p.engrave_logo and not p.engrave_title


def test_label_is_free_text():
    p = plan(blank=True, label="Slot A3, left deck")
    assert p.ok and p.label == "Slot A3, left deck"
    assert plan(holes=parse_spacing("110x60"), screw="M3", head="cap").label is None


def test_label_must_fit_under_the_title():
    assert not plan(blank=True, label="x" * 80).ok


@pytest.mark.parametrize("label", ["Slot \u2603", "   "])
def test_bad_labels_are_errors_and_not_crashes(label):
    p = plan(blank=True, label=label)
    assert not p.ok and any("--label" in e for e in p.errors)


def test_a_hole_on_the_label_drops_only_the_label():
    p = cap(((26, -24), (-26, 24)), label="Slot A3")
    assert p.ok and p.engrave_title and not p.engrave_label
    assert any("Slot A3" in w for w in p.warnings)


def test_design_record_round_trips(tmp_path):
    req = Request(name="deck-a", material="6082", holes=((-55.0, -30.0), (55.0, 30.0)), screw="M3", head="cap", label='Slot "A3"')
    path = tmp_path / "nest.toml"
    write_record(make_plan(req), path)
    back, version, _ = read_request(path)
    assert back == req and version == s.VERSION


def test_every_material_says_how_far_it_is_tested():
    assert "Tested: v1.4 has been printed on a Bambu H2D in PLA" in plan(material="pla", blank=True).warnings[0]
    for key in s.MATERIALS:
        if key != "pla":
            assert plan(material=key, blank=True).warnings[0].startswith("Not tested: no v1.4 plate")


def test_only_pla_is_marked_as_tested():
    assert set(s.TESTED_MATERIALS) == {"pla"}
    assert version_reference()["pocket_by_material"]["pla"]["tested"] is True
    assert version_reference()["pocket_by_material"]["6082"]["tested"] is False
    assert "Not tested" in design_record(plan(blank=True))["status"]["this_material"]


def test_design_record_holds_the_dimensions(tmp_path):
    p = cap(parse_spacing("110x60"), label="Slot A3")
    record = design_record(p)
    assert record["design"]["opennest_version"] == s.VERSION and record["design"]["label"] == "Slot A3"
    assert record["pocket"]["x"] == 128.3 and record["pocket"]["catch_per_side_x"] == 2.0
    assert record["holes"]["through_d"] == 3.4 and record["holes"]["counterbore_depth"] == 3.0
    assert record["plate"]["seat_above_underside"] == s.DEFAULT_DECK
    assert '--label "Slot A3"' in command_for(p.request)


def test_version_reference_is_committed():
    path = s.REPO / "docs" / "versions" / f"v{s.VERSION}.toml"
    assert path.read_text() == to_toml(version_reference(), f"OpenNest v{s.VERSION}. All dimensions in mm.")


def test_no_branding_removes_name_and_mark():
    p = plan(blank=True, branding=False)
    assert p.title.startswith("OpenNest") and not p.engrave_logo


@pytest.mark.parametrize(
    "material, x, y",
    [("pla", 128.3, 86.0), ("6082", 128.3, 86.0), ("peek", 128.3, 86.0), ("pom-c", 128.4, 86.1), ("ptfe", 129.0, 86.5)],
)
def test_pocket_by_material(material, x, y):
    assert s.pocket_for(s.MATERIALS[material]) == (x, y)


def test_every_slas_plate_fits_the_reference_pocket_at_20c():
    max_x, max_y = s.plate_size(s.TOL_SIDE)
    assert s.POCKET_X - max_x == pytest.approx(0.04)
    assert s.POCKET_Y - max_y == pytest.approx(0.02)


@pytest.mark.parametrize("key", s.MATERIALS)
def test_machined_parts_take_the_largest_plate_when_cold(key):
    m = s.MATERIALS[key]
    if m.process == "3d-print":
        return
    x, y = s.pocket_for(m)
    max_x, max_y = s.plate_size(s.TOL_SIDE, s.FIT_T_MIN)
    assert s.pocket_at(x, m, s.FIT_T_MIN) > max_x and s.pocket_at(y, m, s.FIT_T_MIN) > max_y


def test_ptfe_takes_m3_cap_heads_on_sleeves_only():
    assert not plan(material="ptfe", holes=parse_spacing("110x60"), screw="M3", head="flat").ok
    p = plan(material="ptfe", holes=parse_spacing("110x60"), screw="M3", head="cap")
    assert p.ok and p.through_d == 5.0


def test_ptfe_keeps_room_for_the_edge_rounds_on_the_tab():
    p = plan(material="ptfe", blank=True)
    assert s.L / 2 - p.pocket_x / 2 - p.chamfer_x == pytest.approx(s.MIN_TAB_LAND)
    assert plan(blank=True).chamfer_x == s.CHAMFER_IN


def test_xy_scale_is_for_prints_and_small():
    assert not plan(blank=True, xy_scale=1.003).ok
    assert plan(material="pla", blank=True, xy_scale=1.003).ok
    assert not plan(material="pla", blank=True, xy_scale=1.05).ok


def test_unknown_material_is_an_error():
    assert not plan(material="wood", blank=True).ok


@pytest.mark.parametrize(
    "args",
    [
        ["check", "--screw", "M3"],
        ["check", "--material", "6082", "--holes", "abc"],
        ["check", "--material", "6082", "--holes", "1,2", "--spacing", "110x60"],
        ["check", "--config", "/nonexistent.toml"],
        ["check", "--material", "6082", "--screw", "M3", "--head", "cap", "--holes", "80,0"],
    ],
)
def test_bad_requests_exit_2_with_a_message(args, capsys, monkeypatch):
    import nest

    monkeypatch.setattr("sys.argv", ["nest.py", *args])
    with pytest.raises(SystemExit) as stop:
        raise SystemExit(nest.main())
    assert stop.value.code == 2
    assert "ERROR" in capsys.readouterr().out


def test_a_good_check_exits_0(monkeypatch):
    import nest

    monkeypatch.setattr("sys.argv", ["nest.py", "check", "--material", "6082", "--screw", "M3", "--head", "cap", "--spacing", "110x60"])
    assert nest.main() == 0
