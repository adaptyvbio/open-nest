# Changelog

The version is engraved on every plate, so a plate always says which design it is.

## v1.4

- Printed in PLA on a Bambu H2D. This is the only real test of this version so far.
- The pocket opens in X from 128.0 to 128.3 mm, so every plate within SLAS 1-2004 fits at 20 C.
- Holes become user-defined. `cad/nest.py` builds any pattern that passes its checks, and fixed
  mounting variants are gone.
- Every build writes `nest.toml`, a design record with the version, commit, inputs and every
  dimension, and `--config` builds the same part from it. `docs/versions/` keeps each version's
  fixed dimensions.
- `--label` engraves free text under the title and version, such as a slot name.
- The flat head countersink is a true 90 degrees, 6.5 mm at the seat for M3. Earlier versions cut
  about 5.1 mm at the seat, so a flat head could sit above it.
- The pocket is sized by material, and Solid PTFE gets its own pocket and metal sleeves.
- One parametric builder replaces a script per plate. The engraved mark is now true curves, which
  cuts the STEP file from about 6.8 MB to about 4 MB and gives a CNC cleaner toolpaths.
- The frame moves to the underside of the plate: seat at Z 5, tab tops at Z 11.

## v1.3

- The fillet between the tab walls and the seat is gone. A centred plate's edge rode on it, up to
  0.38 mm high. There is no v1.2.
- Printed on a Bambu H2D on 2026-11-04, with no visible layer lines on the lead-in slopes.

## v1.1

- A longer lead-in at the same 30 degrees, starting 3 mm above the seat.
- A plate with no holes, called Blank.

## v1.0

- The first plate: 5 mm deck, eight guide tabs, two gripper notches, engraved seat.
