#!/bin/zsh
cd /private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/mutC_S/gf180/tapeout/rtl_r14 || exit 1
PYTHON=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python nice -n 10 ./run_tests_stopfirst.sh > ../../../run_result.txt 2>&1
echo "EXIT $?" >> ../../../run_result.txt
