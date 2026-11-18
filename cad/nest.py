# SPDX-License-Identifier: CERN-OHL-P-2.0
"""The `opennest` command, for a clone and for design records that say `uv run cad/nest.py`.

    uv run cad/nest.py check --material 6082 --screw M3 --head cap --spacing 110x60

is the same as `uv run opennest check ...`. See AGENTS.md.
"""
import sys

from opennest.cli import main

if __name__ == "__main__":
    sys.exit(main())
