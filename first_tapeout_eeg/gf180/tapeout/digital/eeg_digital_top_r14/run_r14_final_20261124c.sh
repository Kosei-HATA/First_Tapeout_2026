#!/bin/zsh
# The r14 macro, third batch (11/24): r14f5_20261124, config.yaml (the r14m3 settings with eeg_digital_top_r14.sdc,
# the preset / clear arcs on in every OpenROAD step) and the H-tree buffers every 150 um that cleared the clock root's
# warnings in f2, nothing else. f3 (the same with slew margins 40 % / 40 %) stopped at the detailed placement after the
# post-GRT timing repair (DPL-0036, 3 cells). The same PDK, nix shell and RTL check as before. Run from a Terminal tab.
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r14 rtl &&
         shasum -a 256 rtl_r14/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl/spec/*.svh) }
src > $D/runs/r14f5_src_before_20261124.txt
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f5_20261124 -c CTS_DISTANCE_BETWEEN_BUFFERS=150" > $D/runs/r14f5_20261124.log 2>&1 &
wait
date
src > $D/runs/r14f5_src_after_20261124.txt
cmp -s $D/runs/r14f5_src_before_20261124.txt $D/runs/r14f5_src_after_20261124.txt && echo "RTL sources unchanged during the runs" || echo "RTL SOURCES CHANGED during the runs"
tail -3 $D/runs/r14f5_20261124.log
