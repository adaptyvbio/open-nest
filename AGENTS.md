# OpenNest for coding agents

OpenNest is an open hardware deck plate that holds an SBS microplate. The pocket, tabs and notches
are fixed. The user chooses the holes, the screws and the material. Your job is to turn their
request into files with `cad/nest.py`.

## Build a plate

1. Get the four inputs below. Ask only for what is missing.
2. Run `check` until it exits 0. It needs no CAD and returns at once.
3. Run `make` with the same arguments. It takes about 15 s.
4. Read `out/<name>/report.json`. Pass on every warning, and the `not_checked` list, to the user.

```sh
uv run cad/nest.py check --material 6082 --screw M3 --head cap --spacing 110x60
uv run cad/nest.py make  --material 6082 --screw M3 --head cap --spacing 110x60 --name deck-a --label "Slot A3"
```

Add `--json` for machine-readable output. Exit codes: 0 ok, 2 the request cannot be built and the
errors say why, 3 a built part failed its checks.

## Inputs

| Input | Flags | Notes |
| --- | --- | --- |
| Holes | `--holes "x,y x,y"` or `--spacing 110x60` | mm from the plate centre. `--spacing` is a centred rectangle, or two holes on the X axis with one number |
| Screws | `--screw M3 --head cap` or `--head flat` | `--head plain --hole-d 4.2` makes a plain through hole, for example to tap |
| Material | `--material` | Sets the process and sizes the pocket. List them with `uv run cad/nest.py materials` |
| Name | `--name deck-a` | Output folder under `out/` |
| Deck | `--deck 8` | Optional. Deck thickness in mm, underside to seat, 2 to 30, default 5. Tabs stay 6 mm above the seat |

No holes at all: `--blank`.

Optional: `--label "Slot A3"` engraves free text under the title and version. It can be a slot name
or anything else the user wants to read on the part. Offer it, because it is how they will tell
plates apart. If a hole lands on it, `check` warns and it is left off, so move the hole.

Common names: aluminium means `6082` unless they say 6061. Delrin or acetal means `pom-c`. Teflon
means `ptfe`. Convert inches to mm yourself. For a screw not listed, use `--head plain` with the
clearance diameter from ISO 273 and say what you chose.

## Output

| Process | Files in `out/<name>/` |
| --- | --- |
| 3D print | `nest.step`, `nest.stl`, `nest.toml`, `nest.3mf`, `report.json` |
| CNC | `nest.step`, `nest.stl`, `nest.toml`, `drawing.pdf`, `report.json` |

`nest.toml` is the design record: the version, the commit, the inputs and every dimension. Tell the
user to keep it with the part. To find a dimension later, read that file. To build the same part
again, run `uv run cad/nest.py make --config path/to/nest.toml`.

If only the plate survives, its engraved version leads to `docs/versions/v<version>.toml`, which
holds every fixed dimension of that version. `uv run cad/nest.py spec` prints the current one.

For `--material pla`, `nest.3mf` is a Bambu Studio project for the H2D with tuned settings. Other
print materials get a plain 3MF, so the user sets up their own slicer profile.

## After a print

If a printed pocket measures off (accept X 128.1 to 128.5, Y 85.8 to 86.2), rebuild with
`--xy-scale target/measured`, for example `--xy-scale 1.0031`. Use one factor for both axes.

## Deck thickness

A thicker deck lets larger screw heads sink flush: `check` says the smallest deck a head needs. It
also moves the seat, so tell the user to teach plate heights again. Only the default 5 mm deck has
been printed.

## Rules

- Do not edit `cad/opennest/spec.py` to make a pattern fit. Move the holes, or change `--deck`. If the
  user really wants different fixed geometry, say that it leaves the reference design, and use `--no-branding`.
- Be exact about testing. The only real test of v1.4 is a plate printed in PLA on a Bambu H2D. No
  plate has been machined, made in another material or run on a robot. `check` and `make` print
  this for the chosen material as their first warning, so always pass it on.
- `report.json` shows that the file matches its plan. That is a software check, not a part test. It
  cannot show that the holes match the user's deck, or that a plate fits their robot. Tell them to
  measure.
- Solid PTFE changes size at room temperature. Only suggest it if they ask, and pass on its warning.
- Do not commit anything in `out/`.

## Working on the repo

`uv run pytest -m "not slow"` runs the fast checks, and `uv run pytest` builds real parts as well.
`uv run cad/release.py` rebuilds the reference plates in `models/`. Fixed dimensions live only in
`cad/opennest/spec.py`. The figures and guide come from `design/opennest.pen`; see `design/README.md`.
Write plainly, with no em dashes.
