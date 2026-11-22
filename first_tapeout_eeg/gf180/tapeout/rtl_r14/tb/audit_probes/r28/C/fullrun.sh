#!/bin/zsh
# fullrun.sh <mut dir>: the unchanged run_tests_r14.sh (all 16 groups) in that copy; the summary in <dir>/full.log
D=$1
cd $D/gf180/tapeout/rtl_r14 || exit 1
date "+start %H:%M:%S" > $D/full.log
PYTHON=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python nice -n 5 bash ./run_tests_r14.sh >> $D/full.log 2>&1
echo "rc $?" >> $D/full.log
date "+end %H:%M:%S" >> $D/full.log
