#!/bin/zsh
# The r14 macro, fourth run (11/24): r14f6_20261124, as r14f5_20261124 (config.yaml with eeg_digital_top_r14.sdc and
# the H-tree buffers every 150 um) with the post-GRT timing repair's setup margin 0.5 ns (1.5 in config.yaml) and the
# detailed placement's vertical displacement limit 300 um (100): f3 and f4 (slew margins 40 % / 40 %) stopped at the
# detailed placement after that repair (DPL-0036, 3 and 18 cells). Run from a Terminal panel tab, beside f5.
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r14 rtl &&
         shasum -a 256 rtl_r14/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl/spec/*.svh) }
src > $D/runs/r14f6_src_before_20261124.txt
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f6_20261124 -c CTS_DISTANCE_BETWEEN_BUFFERS=150 -c GRT_RESIZER_SETUP_SLACK_MARGIN=0.5 -c PL_MAX_DISPLACEMENT_Y=300" > $D/runs/r14f6_20261124.log 2>&1 &
wait
date
src > $D/runs/r14f6_src_after_20261124.txt
cmp -s $D/runs/r14f6_src_before_20261124.txt $D/runs/r14f6_src_after_20261124.txt && echo "RTL sources unchanged during the runs" || echo "RTL SOURCES CHANGED during the runs"
tail -3 $D/runs/r14f6_20261124.log
