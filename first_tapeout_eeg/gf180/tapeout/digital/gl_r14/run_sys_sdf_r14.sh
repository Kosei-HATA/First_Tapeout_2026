#!/bin/zsh
# The r14 control macro and the ADC's digital block (eeg_adc_dig, f3) together at gate level with delays (11/25; tracker
# C3): gl_sys_sdf_r14.sv with both netlists back-annotated with the SDF of one corner (the r14 run's final/sdf, the f3
# re-run's final/sdf: the chips' macros), the loop closed at gate level (gl_shadow_r14 takes CODE from the block's
# netlist, sys_adc_r14 puts the block's netlist on the control netlist's outputs), TH launched 15 ns after each CMP_STROBE
# rise as the quantizer drives it (eeg_adc_dig's constraints). zero: the same without delays.
#
# The cell models as for run_gl_r14.sh sdf and rtl/gl_sdf_prep.sh: the mux / xor ifnone edge paths written as plain paths
# (Icarus drops "ifnone (posedge S => ...)"), for the 9-track (control) and the 7-track (ADC block) library.
# Sources from git at the given commit (git archive), as run_gl_r14.sh.
#
# usage: run_sys_sdf_r14.sh <macro run tag> <git commit> [zero|sdf|all]   (from a Terminal panel tab; hours)
# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_<tag>/{syssdf_zero.log,syssdf_<corner>.log,summary.txt}
set -u
TAG=$1
REV=$2
WHAT=${3:-all}
ROOT=/Users/noah/Codings/First_Tapeout_2026
T=$ROOT/first_tapeout_eeg/gf180/tapeout
HERE=$T/digital/gl_r14
MAC=$T/digital/eeg_digital_top_r14/runs/$TAG
ADC=$T/digital/eeg_adc_dig/runs/f3_rerun_20261119/final
RUN=$T/digital/eeg_digital_top_r14/runs/sys_$TAG
PY=$ROOT/first_tapeout_eeg/gf180/tools/venv310/bin/python
LIB=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref
SRC=$RUN/src/first_tapeout_eeg/gf180/tapeout
mkdir -p $RUN/src
if [ ! -f $RUN/src/.done ]; then
    (cd $ROOT && git archive $REV first_tapeout_eeg/gf180/tapeout/rtl_r14 first_tapeout_eeg/gf180/tapeout/rtl \
        first_tapeout_eeg/documentation/gf180_digital_control_spec_20261119.md) | tar -x -C $RUN/src || exit 1
    mkdir -p $SRC/rtl/build/e2e && cp $T/rtl/build/e2e/s4.codes $SRC/rtl/build/e2e/ || exit 1
    for d in $T/pex/runs/adc_overload_r12/*(/); do
        mkdir -p $SRC/pex/runs/adc_overload_r12/${d:t} && cp $d/out.csv $SRC/pex/runs/adc_overload_r12/${d:t}/
    done
    (cd $SRC/rtl_r14 && $PY tb/gen_codes.py && $PY tb/gen_reg_tests.py) > $RUN/gen.log 2>&1 || { cat $RUN/gen.log; exit 1; }
    echo "$REV" > $RUN/src/.done
fi
[ "$(cat $RUN/src/.done)" = "$REV" ] || { echo "the copy in $RUN/src is of $(cat $RUN/src/.done), not $REV"; exit 1; }
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' $MAC/final/nl/eeg_digital_top.nl.v > $RUN/eeg_digital_top_gl.v
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' $T/layout/gds/eeg_adc_dig.nl.v > $RUN/eeg_adc_dig_gl.v
$PY $HERE/gl_names.py $MAC/final/nl/eeg_digital_top.nl.v $RUN/gl_names.svh > $RUN/gl_names.log || { cat $RUN/gl_names.log; exit 1; }
mkdir -p $RUN/sdf
for t in 9t 7t; do
    perl -0777 -pe 's/ifnone[ \t]*\n((?:[ \t]*\/\/[^\n]*\n)?)([ \t]*)\(posedge (\w+) => \((\w+):\w+\)\) = (\([^)]*\));/$1$2($3 => $4) = $5;/g;
                    s/ifnone[ \t]*\n(?:[ \t]*\/\/[^\n]*\n)?[ \t]*\(negedge \w+ => \(\w+:\w+\)\) = \([^)]*\);[ \t]*\n//g' \
        $LIB/gf180mcu_fd_sc_mcu${t}5v0/verilog/gf180mcu_fd_sc_mcu${t}5v0.v > $RUN/sdf/cells_$t.v
done
CORNERS=(max_ss_125C_3v00 nom_tt_025C_3v30 min_ff_n40C_3v60)
for c in $CORNERS; do
    sed 's/(CELLTYPE "eeg_digital_top")/(CELLTYPE "eeg_digital_top_gl")/' $MAC/final/sdf/$c/eeg_digital_top__$c.sdf > $RUN/sdf/top_$c.sdf
    sed 's/(CELLTYPE "eeg_adc_dig")/(CELLTYPE "eeg_adc_dig_gl")/' $ADC/sdf/$c/eeg_adc_dig__$c.sdf > $RUN/sdf/adc_$c.sdf
done
shasum -a 256 $MAC/final/nl/eeg_digital_top.nl.v $T/layout/gds/eeg_adc_dig.nl.v $ADC/nl/eeg_adc_dig.nl.v \
    $MAC/final/sdf/*/eeg_digital_top__*.sdf(N) $ADC/sdf/*/eeg_adc_dig__*.sdf(N) > $RUN/inputs_sdf.sha256
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv ../rtl/eeg_adc_dig.sv ../rtl/eeg_therm2bin.sv ../rtl/eeg_dwa.sv)
BENCH=($HERE/gl_sys_sdf_r14.sv $HERE/sys_sys_sdf_r14.svh $HERE/sys_adc_r14.sv $HERE/gl_shadow_r14.sv
       $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v)
cd $SRC/rtl_r14 || exit 1
comp() {   # out.vvp, extra flags (one word), iverilog arguments...
    local out=$1 flags=$2; shift 2
    rm -f $out
    iverilog -g2012 -I ../rtl/spec -I tb -I build -I $RUN ${=flags} -DTB=gl_sys_sdf_r14 -DGL_CODE_SRC=sys_adc_r14.code_gl -DSYS_GL \
        -s gl_sys_sdf_r14 -s gl_shadow_r14 -s sys_adc_r14 -o $out "$@" > $out.log 2>&1
    local rc=$?
    grep -v "sorry: constant" $out.log | grep -v "Timing checks are not supported" | head -20
    if grep -q "warning: Port .* expects" $out.log; then echo "FAIL: a port connected at another width ($out)"; return 1; fi
    [ $rc -eq 0 ] && [ -f $out ]
}
res=()
verdict() {   # name, log
    local name=$1 log=$2 ok=1 p
    for p in "gl_sys_sdf_r14" "ADC block on the r14 control" "gate level" "eeg_adc_dig gate level"; do
        grep -q "^PASS: $p" $log || ok=0
    done
    grep -qE "FAIL|ERROR|GL MISMATCH" $log && ok=0
    if [ $ok -eq 1 ]; then res+=("PASS  $name  $(grep -h '^PASS: gl_sys_sdf_r14' $log)"); else res+=("FAIL  $name  (see $log)"); fi
}
date
if [[ $WHAT == zero || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/syssdf_zero.vvp "-DFUNCTIONAL" $RTL $BENCH $LIB/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v \
          $LIB/gf180mcu_fd_sc_mcu9t5v0/verilog/gf180mcu_fd_sc_mcu9t5v0.v $LIB/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v \
          $LIB/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v && vvp -n build/syssdf_zero.vvp
      echo "exit $?"; } > $RUN/syssdf_zero.log 2>&1
    echo "gl_sys_sdf_r14 without delays: $((SECONDS - t0)) s" >> $RUN/syssdf_zero.log
    verdict gl_sys_sdf_r14_zero_delay $RUN/syssdf_zero.log
fi
if [[ $WHAT == sdf || $WHAT == all ]]; then
    for c in $CORNERS; do
        case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
        ( t0=$SECONDS
          { comp build/syssdf_$c.vvp "-gspecify -ginterconnect -T$t -DGL_SDF -DGL_SDF_FILE=\"$RUN/sdf/top_$c.sdf\" -DSYS_SDF_ADC=\"$RUN/sdf/adc_$c.sdf\" -DSYS_TH_LAUNCH=15.0" \
                 $RTL $BENCH $LIB/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $RUN/sdf/cells_9t.v \
                 $LIB/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $RUN/sdf/cells_7t.v && vvp -n build/syssdf_$c.vvp
            echo "exit $?"; } > $RUN/syssdf_$c.log 2>&1
          n=$(grep -E "^SDF (ERROR|WARNING)" $RUN/syssdf_$c.log | grep -c -v "TIMINGCHECK not supported")
          echo "SDF $c: $n SDF errors / warnings besides the timing checks" >> $RUN/syssdf_$c.log
          echo "gl_sys_sdf_r14 with the SDF of $c: $((SECONDS - t0)) s" >> $RUN/syssdf_$c.log ) &
    done
    wait
    for c in $CORNERS; do verdict "gl_sys_sdf_r14_$c" $RUN/syssdf_$c.log; done
fi
date
printf '%s\n' "${res[@]}" | tee -a $RUN/summary.txt
