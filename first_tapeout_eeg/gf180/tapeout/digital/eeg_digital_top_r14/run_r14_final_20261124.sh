#!/bin/zsh
# The r14 macro from the RTL of the audit (gf180/tapeout/rtl_r14, unchanged in logic since audit round 10), 11/24:
# config.yaml (the r14m3 settings, 440 x 900 um, plus the STA hook of VER-05) in two variants at once, to clear the
# design-rule warnings r14m3 kept (the clock root clkbuf_0_MCLK drove 16 level-4 buffers, 0.61 pF against 0.2 pF and
# fanout 10; DAC_LOAD's flip-flop drove the long wire to its output buffer at 3.07 ns against 3 ns, max_ss):
#   r14f1_20261124  repair_clock_nets on clock wires over 250 um (CTS_CLK_MAX_WIRE_LENGTH), post-GRT slew margin 50 %
#   r14f2_20261124  H-tree buffers every 150 um (CTS_DISTANCE_BETWEEN_BUFFERS), long-wire repair over 300 um after
#                   placement and after global routing (DESIGN_REPAIR_MAX_WIRE_LENGTH, GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH)
# The same PDK (ciel 792ef670) and nix shell (ws_gf180/eeg_padring) as the r13 macro and r14m1-m3. On the efficiency
# cores (taskpolicy -b). Run from a Terminal panel tab. The git commit and the sha256 of every RTL source are written
# before and after the runs (the audit session edits the same checkout).
# nix: /etc/zshrc lost its nix lines in the macOS update (11/21; /etc/bashrc keeps them), so a Terminal tab's zsh
# has no nix-shell on its PATH: read the daemon profile here
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r14 rtl &&
         shasum -a 256 rtl_r14/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl/spec/*.svh) }
src > $D/runs/r14f_src_before_20261124.txt
date
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f1_20261124 -c CTS_CLK_MAX_WIRE_LENGTH=250 -c GRT_DESIGN_REPAIR_MAX_SLEW_PCT=50" > $D/runs/r14f1_20261124.log 2>&1 &
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag r14f2_20261124 -c CTS_DISTANCE_BETWEEN_BUFFERS=150 -c DESIGN_REPAIR_MAX_WIRE_LENGTH=300 -c GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH=300" > $D/runs/r14f2_20261124.log 2>&1 &
wait
date
src > $D/runs/r14f_src_after_20261124.txt
cmp -s $D/runs/r14f_src_before_20261124.txt $D/runs/r14f_src_after_20261124.txt && echo "RTL sources unchanged during the runs" || echo "RTL SOURCES CHANGED during the runs"
tail -3 $D/runs/r14f1_20261124.log
tail -3 $D/runs/r14f2_20261124.log
