# Contributing

The most useful thing you can send is a measurement. Make a plate, measure it, try it with real
plates and a real robot, then open a [fit report](.github/ISSUE_TEMPLATE/fit-report.yml). A failed
fit helps as much as a good one.

When a real part is made in a new material or runs on a robot, update the test status in three
places: `TESTED_MATERIALS` in `cad/opennest/spec.py`, the table at the top of `README.md`, and page 2
of the guide. Say only what was really done.

## Changing the design

Fixed dimensions live in `cad/opennest/spec.py`. A change there changes every plate, so say what
you measured that calls for it. New materials and screw sizes are welcome: add them to the tables
in that file with a source for the numbers.

## Before you open a pull request

```sh
uv sync
uv run pytest
```

If the geometry changed, bump `VERSION` in `spec.py`, since it is engraved on the part. Then run
`uv run cad/release.py` to rebuild `models/`, and add a line to `CHANGELOG.md`.

Do not add files taken from an instrument vendor's software, such as labware definitions or 3D
models. Interface dimensions you measured yourself are fine.

## Writing

Short sentences, present tense, no em dashes. Say what was measured and what was only calculated.

## Licensing

By contributing you agree that your work is licensed as described in [LICENSE](LICENSE).
