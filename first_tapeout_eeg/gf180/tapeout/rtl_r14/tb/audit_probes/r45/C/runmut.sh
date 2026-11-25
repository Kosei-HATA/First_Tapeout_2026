#!/bin/zsh
# Audit 45, auditor C: make the mutant copy <tag> and run run_tests_r14.sh (all 16 groups) in it.
# usage: runmut.sh <tag>   (output: a45C_mut/<tag>.out, the copy's build/*.log)
T=$1
S=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
mkdir -p $S/a45C_mut
$PY $S/a45C_tools/mkmut.py $T > $S/a45C_mut/$T.out 2>&1 || exit 1
cd $S/a45C_mut/$T/gf180/tapeout/rtl_r14 || exit 1
date >> $S/a45C_mut/$T.out
PYTHON=$PY ./run_tests_r14.sh >> $S/a45C_mut/$T.out 2>&1
echo "exit=$?" >> $S/a45C_mut/$T.out
date >> $S/a45C_mut/$T.out
