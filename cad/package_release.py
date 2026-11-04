# SPDX-License-Identifier: CERN-OHL-P-2.0
"""Package this version for a GitHub release and print its tag. CI publishes the result.

    uv run cad/package_release.py dist

Writes dist/notes.md and dist/assets/: a zip per reference plate, the guide and the fixed
dimensions. Exit code 2 means the repo is not ready to release this version, and says why.
"""
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path

from pypdf import PdfReader

from opennest import spec as s

GUIDE = s.REPO / "docs/OpenNest-Guide.pdf"


def _tag() -> str:
    return f"v{s.VERSION}"


def _read(name: str) -> str:
    return (s.REPO / name).read_text()


def _plates() -> list[Path]:
    return sorted(p for p in (s.REPO / "models").iterdir() if p.is_dir())


def _report(plate: Path) -> dict:
    return json.loads((plate / "report.json").read_text())


def _section(text: str, heading: str) -> str:
    """The text under a level 2 markdown heading."""
    found = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return found.group(1).strip() if found else ""


def problems() -> list[str]:
    """What stops this version from being released. The fast tests run this on every pull request."""
    tag = _tag()
    found = []
    if not _section(_read("CHANGELOG.md"), tag):
        found.append(f"CHANGELOG.md has no section for {tag}")
    if f"| {tag} | Status |" not in _read("README.md"):
        found.append(f"the test table in README.md is not for {tag}")
    if s.TESTED_MATERIALS and tag not in s.ONLY_TEST:
        found.append(f"TESTED_MATERIALS in spec.py claims a test of {tag}, but ONLY_TEST does not")
    if not (s.REPO / "docs/versions" / f"{tag}.toml").exists():
        found.append(f"docs/versions/{tag}.toml is missing: run cad/release.py")
    if not any(tag in page.extract_text() for page in PdfReader(GUIDE).pages):
        found.append(f"{GUIDE.name} does not mention {tag}")

    full = s.VERSION if s.VERSION.count(".") == 2 else f"{s.VERSION}.0"
    if tomllib.loads(_read("pyproject.toml"))["project"]["version"] != full:
        found.append(f"pyproject.toml is not at version {full}")
    if tomllib.loads(_read("okh.toml"))["version"] != full:
        found.append(f"okh.toml is not at version {full}")
    if not re.search(rf"^version: {re.escape(full)}$", _read("CITATION.cff"), re.M):
        found.append(f"CITATION.cff is not at version {full}")

    for plate in _plates():
        report = _report(plate)
        record = tomllib.loads((plate / "nest.toml").read_text())
        if report["version"] != s.VERSION or record["design"]["opennest_version"] != s.VERSION:
            found.append(f"models/{plate.name} is not built from {tag}: run cad/release.py")
        if not report["ok"]:
            found.append(f"models/{plate.name} failed its checks")
        found += [f"models/{plate.name}/{f} is missing" for f in report["files"] if not (plate / f).exists()]
    return found


def _zip_name(plate: Path) -> str:
    return f"opennest-{_tag()}-{plate.name}"


def _zip_plate(plate: Path, assets: Path) -> None:
    folder = _zip_name(plate)
    with zipfile.ZipFile(assets / f"{folder}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(plate.iterdir()):
            z.write(f, f"{folder}/{f.name}")
        z.write(s.REPO / "LICENSE", f"{folder}/LICENSE")
        for f in sorted((s.REPO / "LICENSES").iterdir()):
            z.write(f, f"{folder}/LICENSES/{f.name}")


def notes() -> str:
    """The release notes: the changelog, the test status as it stands today, and every warning."""
    tag = _tag()
    repo = tomllib.loads(_read("okh.toml"))["repo"]
    rows, warnings, not_checked = [], [], {}
    for plate in _plates():
        report = _report(plate)
        files = ", ".join(f"`{f}`" for f in sorted(report["files"]))
        rows.append(f"| `{_zip_name(plate)}.zip` | {report['material']} | {files} | {report['test_status']} |")
        warnings += [f"- **{report['material']}:** {w}" for w in report["warnings"] if w != report["test_status"]]
        not_checked |= dict.fromkeys(report["not_checked"])
    return "\n".join([
        "## What changed",
        "",
        re.sub(r"\n +", " ", _section(_read("CHANGELOG.md"), tag)),  # GitHub would keep the line breaks of a wrapped bullet
        "",
        "## What has been tested",
        "",
        _section(_read("README.md"), "What has been tested"),
        "",
        f"This is the status on the day of this release. The [README]({repo}#what-has-been-tested) always has the current one.",
        "",
        "## Reference plates",
        "",
        f"These plates have no holes. To build one with your holes and deck thickness, open [the repo]({repo}/tree/{tag}) in your coding agent, or run `cad/nest.py` yourself.",
        "",
        "| File | Material | Contains | Status |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
        *warnings,
        "",
        "`report.json` shows that a file matches its plan. That is a software check, not a part test. It cannot show:",
        "",
        *[f"- {item}" for item in not_checked],
        "",
        "## Documents",
        "",
        f"- `OpenNest-Guide-{tag}.pdf`: the design and manufacturing guide.",
        f"- `opennest-{tag}-dimensions.toml`: every fixed dimension of this version.",
        "",
    ])


def main() -> int:
    if found := problems():
        print(f"Cannot release {_tag()}:", *found, sep="\n  ", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for plate in _plates():
        _zip_plate(plate, assets)
    (assets / f"OpenNest-Guide-{_tag()}.pdf").write_bytes(GUIDE.read_bytes())
    (assets / f"opennest-{_tag()}-dimensions.toml").write_bytes((s.REPO / "docs/versions" / f"{_tag()}.toml").read_bytes())
    (out / "notes.md").write_text(notes())
    print(f"tag={_tag()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
