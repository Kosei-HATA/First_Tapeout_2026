#!/bin/zsh
# r14 area trial (11/19): the r14 digital control in LibreLane with the r13 macro's settings, in two outlines at once:
# 440 x 700 um (trial_h700.yaml, the r13 macro) and 440 x 900 um (trial_h900.yaml); run on 11/19 as config.yaml and config_h900.yaml. The same PDK (ciel 792ef670) and nix
# shell (ws_gf180/eeg_padring) as the r13 macro (f2) and its 11/19 rerun. On the efficiency cores (taskpolicy -b) so
# that the running ngspice jobs keep the performance cores. Run from a Terminal panel tab.
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
date
taskpolicy -b nix-shell --run "librelane $D/trial_h700.yaml $OPTS --run-tag t14_h700_20261119" > $D/runs/t14_h700_20261119.log 2>&1 &
taskpolicy -b nix-shell --run "librelane $D/trial_h900.yaml $OPTS --run-tag t14_h900_20261119" > $D/runs/t14_h900_20261119.log 2>&1 &
wait
date
tail -3 $D/runs/t14_h700_20261119.log
tail -3 $D/runs/t14_h900_20261119.log
