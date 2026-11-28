#!/bin/zsh
# Power of the r15 macro (eeg_digital_top, LibreLane run r15m13_20261128; run_power_r14.sh for r15, 11/28) from the switching of its gate-level
# simulation, as run_power.sh did for the r13 macros on 10/29 (documentation/gf180_verification_coverage_20261029.md):
# gl_sdf_r15 without delays with the netlist in lockstep (gf180/tapeout/digital/gl_r15), the VCD of the netlist for
# 1 ms of RUN (power_vcd_r15.sv), then OpenSTA's report_power (power.tcl) at tt 25 C 3.3 V (nominal SPEF) and
# ff -40 C 3.6 V (minimum SPEF), and with OpenSTA's default activity (what LibreLane's STA reports).
#
# usage: run_power_r15.sh [<macro run tag> [<git commit of its RTL>]]   (about 15 minutes)
# Needs run_gl_r15.sh's copy of the sources (eeg_digital_top_r15/runs/gl_<tag>/src, made by any of its modes) and
# the LibreLane nix shell (sta). Results: build/r15/ (power_*.log, sim.log).
set -u
TAG=${1:-r15m13_20261128}
REV=${2:-d977f2c8}
HERE=$(cd "$(dirname "$0")" && pwd)
T=$(cd "$HERE/../.." && pwd)
MAC=$T/digital/eeg_digital_top_r15/runs/$TAG/final
RUN=$T/digital/eeg_digital_top_r15/runs/gl_$TAG
SRC=$RUN/src/first_tapeout_eeg/gf180/tapeout
OUT=$HERE/build/r15
NIX=${NIX_DIR:-/Users/noah/Codings/ws_gf180/eeg_padring}
SCL=$NIX/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
[ "$(cat $RUN/src/.done 2>/dev/null)" = "$REV" ] || { echo "no source copy of $REV in $RUN/src (run_gl_r15.sh first)"; exit 1; }
[ -f $RUN/eeg_digital_top_gl.v ] && [ -f $RUN/gl_names.svh ] || { echo "no netlist copy in $RUN"; exit 1; }
mkdir -p $OUT
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_rnd_sat.sv ../rtl/eeg_raw.sv)
cd $SRC/rtl_r15 || exit 1
iverilog -g2012 -I spec -I tb -I build -I $RUN -DFUNCTIONAL -DTB=gl_sdf_r15 -DVCD=\"$OUT/macro.vcd\" \
    -s gl_sdf_r15 -s gl_shadow_r15 -s power_vcd_r15 -o $OUT/gl.vvp $RTL $T/digital/gl_r15/gl_sdf_r15.sv \
    $SCL/verilog/primitives.v $SCL/verilog/gf180mcu_fd_sc_mcu9t5v0.v $T/digital/gl_r15/gl_shadow_r15.sv \
    $RUN/eeg_digital_top_gl.v $HERE/power_vcd_r15.sv > $OUT/compile.log 2>&1 || { echo "compile failed: $OUT/compile.log"; exit 1; }
vvp -n $OUT/gl.vvp > $OUT/sim.log 2>&1
grep -E "power_vcd_r15|GL MISMATCH|FAIL" $OUT/sim.log | head -5
printf "%-16s %-24s %10s %10s\n" macro case "P (mW)" "I (mA)"
for c in "tt_025C_3v30 nom 3.3 gl_shadow_r15/g" "ff_n40C_3v60 min 3.6 gl_shadow_r15/g" "tt_025C_3v30 nom 3.3 -"; do
    set -- ${=c}
    cor=$1 sp=$2 v=$3 sc=$4
    [ "$sc" = "-" ] && sc="" && tag="${cor}_default" || tag="${cor}_vcd"
    env_="LIB=$SCL/lib/gf180mcu_fd_sc_mcu9t5v0__$cor.lib NL=$MAC/nl/eeg_digital_top.nl.v TOP=eeg_digital_top"
    env_+=" SDC=$MAC/sdc/eeg_digital_top.sdc SPEF=$MAC/spef/$sp/eeg_digital_top.$sp.spef SCOPE=$sc VCD=$OUT/macro.vcd"
    (cd $NIX && nix-shell --run "env $env_ sta -no_init -exit $HERE/power.tcl") > $OUT/power_eeg_digital_top_$tag.log 2>&1
    p=$(awk '/^Total /{print $5 * 1e3}' $OUT/power_eeg_digital_top_$tag.log)
    printf "%-16s %-24s %10.2f %10.2f\n" eeg_digital_top "$tag" "$p" "$(echo "$p / $v" | bc -l)"
done
