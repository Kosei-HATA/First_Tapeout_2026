#!/bin/zsh
# The r14 macro, second batch (11/24): config.yaml with eeg_digital_top_r14.sdc (the reset exceptions of VER-05, the
# preset / clear arcs on in every OpenROAD step, so that the timing repair sees the SOFT_RESET paths).
# f1 (clock wires over 250 um repaired, post-GRT slew margin 50 %) was stopped at its post-GRT repair (over 20 min);
# f2 (H-tree buffers every 150 um, long-wire repair over 300 um) cleared the clock root's warnings but missed setup
# (-1.58 ns at max_ss, the CIC; the SOFT_RESET paths into the CIC -0.88 ns) and kept 6 slew warnings (4.67 ns).
#   r14f3_20261124  H-tree buffers every 150 um (f2's clock tree), no long-wire repair, slew margins 40 % (after
#                   placement) and 40 % (after global routing)
#   r14f4_20261124  clock wires over 250 um repaired (repair_clock_nets), the same slew margins
# The same PDK, nix shell and RTL check as run_r14_final_20261124.sh. Run from a Terminal panel tab.
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
SLEW="-c DESIGN_REPAIR_MAX_SLEW_PCT=40 -c GRT_DESIGN_REPAIR_MAX_SLEW_PCT=40"
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r14 rtl &&
         shasum -a 256 rtl_r14/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl/spec/*.svh) }
src > $D/runs/r14f34_src_before_20261124.txt
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f3_20261124 -c CTS_DISTANCE_BETWEEN_BUFFERS=150 $SLEW" > $D/runs/r14f3_20261124.log 2>&1 &
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f4_20261124 -c CTS_CLK_MAX_WIRE_LENGTH=250 $SLEW" > $D/runs/r14f4_20261124.log 2>&1 &
wait
date
src > $D/runs/r14f34_src_after_20261124.txt
cmp -s $D/runs/r14f34_src_before_20261124.txt $D/runs/r14f34_src_after_20261124.txt && echo "RTL sources unchanged during the runs" || echo "RTL SOURCES CHANGED during the runs"
tail -3 $D/runs/r14f3_20261124.log
tail -3 $D/runs/r14f4_20261124.log
