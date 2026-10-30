#!/usr/bin/env bash
# Power of the two digital macros from the switching of the gate-level simulation (10/29,
# documentation/gf180_verification_coverage_20261029.md): tb_e2e on the s4 stream (full-scale
# 32 Hz + 44.5 mV DC, rtl/run_e2e.sh) with the LibreLane netlists in lockstep
# (rtl/tb/gl_shadow.sv, zero delay), the VCD of both macros for 1 ms (vcd_dump.sv), then
# OpenSTA's report_power (power.tcl) at tt 25 C 3.3 V and ff -40 C 3.6 V, and with the
# default activity for comparison (what LibreLane's STA reports).
#
# usage: gf180/tapeout/digital/power/run_power.sh
# Needs rtl/build/e2e/s4.codes and s4.gold (rtl/run_e2e.sh short makes them) and the
# template's nix shell (sta). Zero-delay simulation: glitches are not in the activity.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TAPEOUT=$(cd "$HERE/../.." && pwd)
RTLD=$TAPEOUT/rtl
DIG=$TAPEOUT/digital
OUT=$HERE/build
NIX=${NIX_DIR:-/Users/noah/Codings/ws_gf180/eeg_padring}
SCL=${PDK_ROOT:-$NIX/gf180mcu}/gf180mcuD/libs.ref
mkdir -p "$OUT"
cd "$RTLD"
RTL="eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv eeg_fifo.sv
     eeg_regs.sv eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv eeg_digital_sys.sv"
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' ../layout/gds/eeg_digital_top.nl.v > "$OUT/eeg_digital_top_gl.v"
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' ../layout/gds/eeg_adc_dig.nl.v > "$OUT/eeg_adc_dig_gl.v"
# shellcheck disable=SC2086
iverilog -g2012 -I tb -DFUNCTIONAL -DTB=tb_e2e -DVCD=\"$OUT/macros.vcd\" -o "$OUT/gl.vvp" \
    -s tb_e2e -s gl_shadow -s vcd_dump $RTL tb/tb_e2e.sv tb/gl_shadow.sv "$HERE/vcd_dump.sv" \
    $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/gf180mcu_fd_sc_mcu9t5v0.v \
    $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v \
    "$OUT/eeg_digital_top_gl.v" "$OUT/eeg_adc_dig_gl.v" > "$OUT/compile.log" 2>&1 || { echo "compile failed: $OUT/compile.log"; exit 1; }
vvp -n "$OUT/gl.vvp" +codes=build/e2e/s4.codes +gold=build/e2e/s4.gold +nsamp=100 > "$OUT/sim.log" 2>&1
grep -E "^(PASS|FAIL)" "$OUT/sim.log" | tail -1
# top, cell library track, LibreLane run, VCD scope
printf "%-16s %-24s %10s %10s\n" macro case "P (mW)" "I (mA)"
for spec in "eeg_adc_dig 7 f3 gl_shadow/g_adc" "eeg_digital_top 9 f2 gl_shadow/g_top"; do
    set -- $spec
    top=$1 t=$2 run=$3 scope=$4
    R=$DIG/$top/runs/$run/final
    for c in "tt_025C_3v30 nom 3.3 $scope" "ff_n40C_3v60 min 3.6 $scope" "tt_025C_3v30 nom 3.3 -"; do
        set -- $c
        cor=$1 sp=$2 v=$3 sc=$4
        [ "$sc" = "-" ] && sc="" && tag="${cor}_default" || tag="${cor}_vcd"
        env_="LIB=$SCL/gf180mcu_fd_sc_mcu${t}t5v0/lib/gf180mcu_fd_sc_mcu${t}t5v0__$cor.lib NL=$R/nl/$top.nl.v TOP=$top SDC=$R/sdc/$top.sdc SPEF=$R/spef/$sp/$top.$sp.spef SCOPE=$sc VCD=$OUT/macros.vcd"
        (cd "$NIX" && nix-shell --run "env $env_ sta -no_init -exit $HERE/power.tcl") > "$OUT/power_${top}_$tag.log" 2>&1
        p=$(awk '/^Total /{print $5 * 1e3}' "$OUT/power_${top}_$tag.log")
        printf "%-16s %-24s %10.2f %10.2f\n" "$top" "$tag" "$p" "$(echo "$p / $v" | bc -l)"
    done
done
