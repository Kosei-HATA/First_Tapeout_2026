#!/bin/zsh
# The r15 macro (11/27): r15m1_20261127, the r14f5 settings (config.yaml copied from eeg_digital_top_r14 with the
# r15 sources, the H-tree buffers every 150 um) on gf180/tapeout/rtl_r15. The same PDK, nix shell and RTL record as
# r14f5. Run from a Terminal tab.
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r15
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
TAG=${1:-r15m1_20261127}
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r15 rtl &&
         shasum -a 256 rtl_r15/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl_r15/spec/*.svh) }
src > $D/runs/${TAG}_src_before.txt
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag $TAG -c CTS_DISTANCE_BETWEEN_BUFFERS=150" > $D/runs/$TAG.log 2>&1
date
src > $D/runs/${TAG}_src_after.txt
cmp -s $D/runs/${TAG}_src_before.txt $D/runs/${TAG}_src_after.txt && echo "RTL sources unchanged during the run" || echo "RTL SOURCES CHANGED during the run"
tail -3 $D/runs/$TAG.log
