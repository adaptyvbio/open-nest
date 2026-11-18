# SPDX-License-Identifier: MIT
"""Fast checks that the wheel uvx installs carries everything a build reads. No CAD."""
import tomllib
from pathlib import Path

from opennest import spec as s

PYPROJECT = tomllib.loads((s.REPO / "pyproject.toml").read_text())


def test_the_wheel_packs_every_asset_the_build_reads():
    packed = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert packed == {path: f"opennest/assets/{Path(path).name}" for path in s.ASSETS}
    assert len({Path(path).name for path in s.ASSETS}) == len(s.ASSETS)
    for path in s.ASSETS:
        assert (s.REPO / path).is_file() and s.asset(path) == s.REPO / path


def test_the_command_is_opennest():
    assert PYPROJECT["project"]["scripts"] == {"opennest": "opennest.cli:main"}
    assert PYPROJECT["project"]["urls"]["Repository"] == s.REPO_URL == tomllib.loads((s.REPO / "okh.toml").read_text())["repo"]
