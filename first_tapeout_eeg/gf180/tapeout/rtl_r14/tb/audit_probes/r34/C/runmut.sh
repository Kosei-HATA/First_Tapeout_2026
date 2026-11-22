#!/usr/bin/env bash
# runmut.sh <name>: make the mutant copy (mk.py) and run fastrun.sh on it; result in mut34C/<name>.result
SP=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
n=$1
mkdir -p $SP/mut34C
d=$($PY $SP/a34C_tools/mk.py "$n") || { echo "$n: mk failed: $d" > $SP/mut34C/$n.result; exit 2; }
t0=$(date +%s)
{ echo "== $n $(date +%H:%M:%S) in $d"; PYTHON=$PY bash $SP/a34C_tools/fastrun.sh "$d"; echo "rc $? after $(( $(date +%s) - t0 )) s"; } > $SP/mut34C/$n.result 2>&1
