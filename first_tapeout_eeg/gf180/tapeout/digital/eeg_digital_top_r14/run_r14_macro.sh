#!/bin/zsh
# The r14 digital macro (config.yaml, 440 x 900 um) in LibreLane: the same PDK (ciel 792ef670) and nix shell
# (ws_gf180/eeg_padring) as the r13 macro (f2) and the area trial. On the efficiency cores (taskpolicy -b) so that the
# running ngspice jobs keep the performance cores. Run from a Terminal panel tab. Usage: run_r14_macro.sh <run tag>
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
TAG=${1:-r14m1_20261119}
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml --pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0 --run-tag $TAG" > $D/runs/$TAG.log 2>&1
echo "exit $?"
date
tail -5 $D/runs/$TAG.log
