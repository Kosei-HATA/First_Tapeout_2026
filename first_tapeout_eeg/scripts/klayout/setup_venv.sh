#!/bin/bash
# Create the Python venv used by gen_core.py.
#
# The sky130A KLayout pcell generators (libs.tech/klayout/pymacros) are
# written against the gdsfactory 8.x API (gf.Component as a kfactory KCell
# with `_kdb_cell`, gf.boolean, ...), which needs Python >= 3.10.  The
# KLayout.app binary bundles Python 3.9, so gen_core.py runs on the pip
# `klayout` wheel inside this venv instead of inside the app; DRC/LVS still
# run on the KLayout.app binary.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON310:-/opt/homebrew/bin/python3.10}

"$PY" -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install --upgrade pip
"$HERE/.venv/bin/pip" install "gdsfactory==8.0.0" "klayout==0.30.12"
echo "venv ready: $HERE/.venv"
