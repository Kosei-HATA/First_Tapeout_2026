#!/bin/zsh
# runmut.sh NAME: all 16 groups of run_tests_r14.sh on the mutant copy, the summary in mut/NAME.result
M=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit25_C/mut
cd $M/$1/gf180/tapeout/rtl_r14 || exit 1
t0=$SECONDS
PYTHON=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python nice -n 5 ./run_tests_r14.sh > $M/$1.result 2>&1
echo "rc $? after $((SECONDS - t0)) s" >> $M/$1.result
