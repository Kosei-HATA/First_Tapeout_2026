#!/bin/zsh
# audit39 C: the spec-table sweeps (round 37's directive classes, round 38's classes) and the regmap.REGS sweep, one after another
B=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit39_C
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
SP=$B/sweep/gf180/tapeout/rtl/spec
cd $B/tools/probes
date; $PY fsm_sweep_c37.py $SP $B/sweep_c37.txt; date
$PY fsm_sweep_c38.py $SP $B/sweep_c38.txt; date
$PY regmap_sweep2.py $SP $B/sweep_regmap.txt; date
