# SPDX-License-Identifier: MIT
"""Fast checks that this version is ready to release, and on what a release contains. No CAD."""
import sys
import tomllib
import zipfile

import pytest

import package_release
from opennest import spec as s
from opennest.plan import Request, make_plan
from opennest.record import design_record, to_toml
from release import REFERENCES


def test_this_version_is_ready_to_release():
    assert package_release.problems() == []


def test_a_bumped_version_is_not_ready(monkeypatch, capsys):
    monkeypatch.setattr(s, "VERSION", "9.9")
    found = "\n".join(package_release.problems())
    for name in ("CHANGELOG.md", "README.md", "ONLY_TEST", "docs/versions", "OpenNest-Guide.pdf", "pyproject.toml", "okh.toml", "CITATION.cff", "models/cnc-aluminium"):
        assert name in found
    assert package_release.main() == 2
    assert capsys.readouterr().out == ""  # CI sends stdout to $GITHUB_OUTPUT


@pytest.mark.parametrize("folder,material", [r[:2] for r in REFERENCES])
def test_reference_plate_matches_the_code(folder, material):
    built = tomllib.loads(to_toml(design_record(make_plan(Request(name=f"blank-{folder}", material=material, blank=True)))))
    kept = tomllib.loads((s.REPO / "models" / folder / "nest.toml").read_text())
    for record in built, kept:
        record["design"].pop("built")
        record["design"].pop("commit", None)
    assert built == kept, f"run cad/release.py: models/{folder} is out of date"


def test_package_has_a_zip_per_plate_and_the_documents(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["package_release.py", str(tmp_path)])
    assert package_release.main() == 0
    tag = f"v{s.VERSION}"
    assert capsys.readouterr().out == f"tag={tag}\n"
    assets = {f.name for f in (tmp_path / "assets").iterdir()}
    assert assets == {f"opennest-{tag}-{r[0]}.zip" for r in REFERENCES} | {f"OpenNest-Guide-{tag}.pdf", f"opennest-{tag}-dimensions.toml"}
    with zipfile.ZipFile(tmp_path / "assets" / f"opennest-{tag}-cnc-aluminium.zip") as z:
        names = {name.split("/", 1)[1] for name in z.namelist()}
    assert {"nest.step", "drawing.pdf", "nest.toml", "report.json", "LICENSE", "LICENSES/CERN-OHL-P-2.0.txt"} <= names


def test_notes_pass_on_the_test_status_and_every_warning():
    text = package_release.notes()
    assert s.ONLY_TEST in text and "| 3D print in other materials | Not tested |" in text
    for plate in package_release._plates():
        report = package_release._report(plate)
        for line in [*report["warnings"], *report["not_checked"]]:
            assert line in text
    assert "—" not in text
