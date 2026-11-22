#!/bin/zsh
SP=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
P=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
S=$SP/specsweep/gf180/tapeout/rtl/spec
cd $SP
nice -n 10 $P c29tools/sweep_regmove.py $S $SP/sweep_regmove.txt
nice -n 10 $P c29tools/sweep_replace.py $S SPI $SP/sweep_rep_SPI.txt
