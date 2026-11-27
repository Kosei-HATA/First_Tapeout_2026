#!/bin/zsh
# The r15 control macro with the ADC's digital block (gl_r14/run_sys_r14.sh of 11/25 for the r15 tree, mk_sys_r15.py,
# 11/28) (eeg_adc_dig, the macro f3 on every chip r12..r14) (11/25; tracker
# C3): sys_adc_r15.sv hangs the block on the control's outputs in tb_top_r14 (every phase, the testbench unchanged) and
# checks the CODE the control takes and SEL1 / SEL2 against a reference DWA; with gl, both netlists run in lockstep with
# their RTL and the loop is closed at gate level (the control netlist's CODE from the block's netlist).
#
# The sources are taken from git at the given commit (git archive into the run folder, as run_gl_r14.sh does): the audit
# session edited the r14 tree in this checkout; r15: the commit's rtl_r15, never the checkout's.
#
# usage: run_sys_r15.sh <macro run tag> <git commit> [rtl|gl|all]   (from a Terminal panel tab; all = rtl then gl, hours)
# out:   gf180/tapeout/digital/eeg_digital_top_r15/runs/sys_<tag>/{sys_rtl.log,sys_gl.log,summary.txt}
set -u
TAG=$1
REV=$2
WHAT=${3:-all}
ROOT=/Users/noah/Codings/First_Tapeout_2026
T=$ROOT/first_tapeout_eeg/gf180/tapeout
HERE=$T/digital/gl_r15
MAC=$T/digital/eeg_digital_top_r15/runs/$TAG
RUN=$T/digital/eeg_digital_top_r15/runs/sys_$TAG
PY=$ROOT/first_tapeout_eeg/gf180/tools/venv310/bin/python
LIB=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref
SRC=$RUN/src/first_tapeout_eeg/gf180/tapeout
mkdir -p $RUN/src
if [ ! -f $RUN/src/.done ]; then
    (cd $ROOT && git archive $REV first_tapeout_eeg/gf180/tapeout/rtl_r15 first_tapeout_eeg/gf180/tapeout/rtl \
        first_tapeout_eeg/documentation/gf180_digital_control_spec_r15_20261127.md) | tar -x -C $RUN/src || exit 1
    mkdir -p $SRC/rtl/build/e2e && cp $T/rtl/build/e2e/s4.codes $SRC/rtl/build/e2e/ || exit 1
    for d in $T/pex/runs/adc_overload_r12/*(/); do
        mkdir -p $SRC/pex/runs/adc_overload_r12/${d:t} && cp $d/out.csv $SRC/pex/runs/adc_overload_r12/${d:t}/
    done
    (cd $SRC/rtl_r15 && $PY tb/gen_codes.py && $PY tb/gen_reg_tests.py) > $RUN/gen.log 2>&1 || { cat $RUN/gen.log; exit 1; }
    echo "$REV" > $RUN/src/.done
fi
[ "$(cat $RUN/src/.done)" = "$REV" ] || { echo "the copy in $RUN/src is of $(cat $RUN/src/.done), not $REV"; exit 1; }
# the netlists: the r14 control (the macro run) and the ADC block as on the chips (layout/gds, the f3 run's final netlist)
sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' $MAC/final/nl/eeg_digital_top.nl.v > $RUN/eeg_digital_top_gl.v
sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' $T/layout/gds/eeg_adc_dig.nl.v > $RUN/eeg_adc_dig_gl.v
shasum -a 256 $MAC/final/nl/eeg_digital_top.nl.v $T/layout/gds/eeg_adc_dig.nl.v \
    $T/digital/eeg_adc_dig/runs/f3_rerun_20261119/final/nl/eeg_adc_dig.nl.v $SRC/rtl/eeg_adc_dig.sv $SRC/rtl/eeg_dwa.sv \
    $SRC/rtl/eeg_therm2bin.sv > $RUN/inputs.sha256
$PY $HERE/gl_names_r15.py $MAC/final/nl/eeg_digital_top.nl.v $RUN/gl_names.svh > $RUN/gl_names.log || { cat $RUN/gl_names.log; exit 1; }
CELLS=($LIB/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $LIB/gf180mcu_fd_sc_mcu9t5v0/verilog/gf180mcu_fd_sc_mcu9t5v0.v
       $LIB/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $LIB/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v)
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv ../rtl/eeg_adc_dig.sv ../rtl/eeg_therm2bin.sv ../rtl/eeg_dwa.sv)
cd $SRC/rtl_r15 || exit 1
comp() {   # out.vvp, top, extra flags (one word, may be empty), iverilog arguments...
    local out=$1 top=$2 flags=$3; shift 3
    rm -f $out
    iverilog -g2012 -I spec -I tb -I build -I $RUN ${=flags} -DTB=$top -s $top -o $out "$@" > $out.log 2>&1
    local rc=$?
    grep -v "sorry: constant" $out.log | head -20
    if grep -q "warning: Port .* expects" $out.log; then echo "FAIL: a port connected at another width ($out)"; return 1; fi
    [ $rc -eq 0 ] && [ -f $out ]
}
res=()
verdict() {   # name, log, the PASS lines required
    local name=$1 log=$2; shift 2
    local ok=1 p
    for p in "$@"; do grep -q "^PASS: $p" $log || ok=0; done
    grep -qE "FAIL|ERROR|GL MISMATCH" $log && ok=0
    if [ $ok -eq 1 ]; then
        res+=("PASS  $name  $(grep -h '^ADC block' $log | cut -c1-160)")
    else
        res+=("FAIL  $name  (see $log)")
    fi
}
date
if [[ $WHAT == rtl || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/sys_top.vvp tb_top_r14 "" -s sys_adc_r15 $RTL tb/tb_top_r14.sv $HERE/sys_tb_top_r15.svh $HERE/sys_adc_r15.sv &&
      vvp -n build/sys_top.vvp && $PY tb/check_top_r14.py && $PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover
      echo "exit $?"; } > $RUN/sys_rtl.log 2>&1
    echo "tb_top_r14 + eeg_adc_dig (RTL): $((SECONDS - t0)) s" >> $RUN/sys_rtl.log
    verdict tb_top_r14_sys_rtl $RUN/sys_rtl.log "tb_top_r14" "ADC block on the r15 control"
fi
if [[ $WHAT == gl || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/sys_gl.vvp tb_top_r14 "-DFUNCTIONAL -DSYS_GL -DGL_CODE_SRC=sys_adc_r15.code_gl" -s gl_shadow_r15 -s sys_adc_r15 \
          $RTL tb/tb_top_r14.sv $HERE/sys_tb_top_r15.svh $HERE/sys_adc_r15.sv $HERE/gl_shadow_r15.sv \
          $RUN/eeg_digital_top_gl.v $RUN/eeg_adc_dig_gl.v $CELLS &&
      vvp -n build/sys_gl.vvp && $PY tb/check_top_r14.py && $PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover
      echo "exit $?"; } > $RUN/sys_gl.log 2>&1
    echo "tb_top_r14 + eeg_adc_dig, both netlists, the loop closed at gate level: $((SECONDS - t0)) s" >> $RUN/sys_gl.log
    verdict tb_top_r14_sys_gl $RUN/sys_gl.log "tb_top_r14" "ADC block on the r15 control" "gate level ==" "eeg_adc_dig gate level =="
fi
date
printf '%s\n' "${res[@]}" | tee -a $RUN/summary.txt
