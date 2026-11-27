#!/bin/zsh
# Trials of the r15 macro (11/28) against r15m1's design-rule warnings at the max RC corners (LibreLane's checkers:
# max slew at max_ss on net29, _11912_/Q (the DAC_LOAD register) -> output29/I, 3.07 ns against 3.0, a 0.39 mm Metal2
# wire to the output buffer; max cap at max_ss / tt / ff on the clock leaf buffer clkbuf_5_24_0_MCLK, 0.21 pF against
# 0.2): the r15m1 settings (config.yaml, the H-tree buffers every 150 um) plus the overrides given. The same PDK, nix
# shell and RTL record as r15m1. Run from a Terminal tab.
# usage: [DIST=<um>] run_r15_trial.sh <tag> [-c VAR=value ...]   (DIST: CTS_DISTANCE_BETWEEN_BUFFERS, 150 as r15m1)
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
command -v nix-shell > /dev/null || { echo "no nix-shell"; exit 1; }
cd /Users/noah/Codings/ws_gf180/eeg_padring || exit 1
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r15
T=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout
OPTS="--pdk gf180mcuD --pdk-root gf180mcu --manual-pdk --scl gf180mcu_fd_sc_mcu9t5v0"
TAG=$1; shift
src() { (cd $T && git log -1 --format='HEAD %H %ad' --date=iso && git status --short rtl_r15 rtl &&
         shasum -a 256 rtl_r15/*.sv rtl/eeg_chop1.sv rtl/eeg_rnd_sat.sv rtl/eeg_raw.sv rtl_r15/spec/*.svh) }
src > $D/runs/${TAG}_src_before.txt
date
DIST=${DIST:-150}
echo "overrides: -c CTS_DISTANCE_BETWEEN_BUFFERS=$DIST $*" > $D/runs/${TAG}_overrides.txt
taskpolicy -b nix-shell --run "librelane $D/config.yaml $OPTS --run-tag $TAG -c CTS_DISTANCE_BETWEEN_BUFFERS=$DIST $*" > $D/runs/$TAG.log 2>&1
echo "librelane rc $?"
date
src > $D/runs/${TAG}_src_after.txt
cmp -s $D/runs/${TAG}_src_before.txt $D/runs/${TAG}_src_after.txt && echo "RTL sources unchanged during the run" || echo "RTL SOURCES CHANGED during the run"
grep -A4 'Checker.MaxSlewViolations\]\|Checker.MaxCapViolations\]\|Checker.SetupViolations\]\|Checker.HoldViolations\]' $D/runs/$TAG.log | tail -20
python3 -c "
import json; m=json.load(open('$D/runs/$TAG/final/metrics.json'))
print({k: m[k] for k in ('design__max_slew_violation__count','design__max_cap_violation__count','design__max_fanout_violation__count','timing__setup__ws','timing__hold__ws','route__drc_errors','magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count','antenna__violating__nets__count') if k in m})
" 2>&1 | tail -2
