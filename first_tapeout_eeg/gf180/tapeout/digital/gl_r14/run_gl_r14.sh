#!/bin/zsh
# Gate level of the r14 macro without delays (requirement VER-05; tracker C4): the final netlist of a LibreLane run
# (runs/<tag>/final/nl) in lockstep with the RTL (gl_shadow_r14.sv) in tb_top_r14 (the whole block through its pins,
# every phase) and tb_spi_r14 (SPI frames), the benches' own checks and checkers as run_tests_r14.sh runs them.
#
# The sources (RTL, benches, spec package, the spec document gen_reg_tests.py checks its counts against) are taken
# from git at the commit the macro was built from (git archive, into the run folder): the audit session edits
# gf180/tapeout/rtl_r14 and its build/ in this checkout, which this never touches. The benches' generated inputs are
# made in that copy (tb/gen_codes.py from the CT loop model's stream rtl/build/e2e/s4.codes and the extracted overload
# runs, both checked by SHA-256 there; tb/gen_reg_tests.py).
#
# usage: run_gl_r14.sh <macro run tag> <git commit> [top|spi|seq|all|sdf|prep]   (from a Terminal panel tab; hours)
#        all = top, spi and seq (gl_sdf_r14.sv without delays); sdf = gl_sdf_r14.sv with the SDF of 3 corners at once
# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/gl_<tag>/{gl_top.log,gl_spi.log,summary.txt}
set -u
TAG=$1
REV=$2
WHAT=${3:-all}
ROOT=/Users/noah/Codings/First_Tapeout_2026
T=$ROOT/first_tapeout_eeg/gf180/tapeout
HERE=$T/digital/gl_r14
MAC=$T/digital/eeg_digital_top_r14/runs/$TAG
RUN=$T/digital/eeg_digital_top_r14/runs/gl_$TAG
PY=$ROOT/first_tapeout_eeg/gf180/tools/venv310/bin/python
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/verilog
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
shasum -a 256 $MAC/final/nl/eeg_digital_top.nl.v > $RUN/netlist.sha256
$PY $HERE/gl_names.py $MAC/final/nl/eeg_digital_top.nl.v $RUN/gl_names.svh > $RUN/gl_names.log || { cat $RUN/gl_names.log; exit 1; }
CELLS=($SCL/primitives.v $SCL/gf180mcu_fd_sc_mcu9t5v0.v)
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
cd $SRC/rtl_r14 || exit 1
comp() {   # out.vvp, top, extra flags (one word, may be empty), iverilog arguments...
    local out=$1 top=$2 flags=$3; shift 3
    rm -f $out
    iverilog -g2012 -I ../rtl/spec -I tb -I build -I $RUN ${=flags} -DTB=$top -s $top -s gl_shadow_r14 -o $out "$@" \
        $HERE/gl_shadow_r14.sv $RUN/eeg_digital_top_gl.v > $out.log 2>&1
    local rc=$?
    grep -v "sorry: constant" $out.log | head -20
    if grep -q "warning: Port .* expects" $out.log; then echo "FAIL: a port connected at another width ($out)"; return 1; fi
    [ $rc -eq 0 ] && [ -f $out ]
}
res=()
verdict() {   # name, log: the bench's own checks passed and the gate level matched
    if grep -q "^PASS: gate level" $2 && ! grep -qE "FAIL|ERROR|GL MISMATCH" $2 && grep -q "PASS" $2; then
        res+=("PASS  $1  $(grep '^PASS: gate level' $2)")
    else
        res+=("FAIL  $1  (see $2)")
    fi
}
date
if [[ $WHAT == top || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/gl_top.vvp tb_top_r14 -DFUNCTIONAL $RTL tb/tb_top_r14.sv $CELLS &&
      vvp -n build/gl_top.vvp && $PY tb/check_top_r14.py && $PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover
      echo "exit $?"; } > $RUN/gl_top.log 2>&1
    echo "tb_top_r14 + gate level: $((SECONDS - t0)) s" >> $RUN/gl_top.log
    verdict tb_top_r14_gl $RUN/gl_top.log
fi
if [[ $WHAT == spi || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/gl_spi.vvp tb_spi_r14 -DFUNCTIONAL $RTL tb/tb_spi_r14.sv $CELLS &&
      vvp -n build/gl_spi.vvp +n=1500 +seed=5 +log=build/spi_trace.txt && $PY tb/check_spi_trace.py build/spi_trace.txt
      echo "exit $?"; } > $RUN/gl_spi.log 2>&1
    echo "tb_spi_r14 + gate level: $((SECONDS - t0)) s" >> $RUN/gl_spi.log
    verdict tb_spi_r14_gl $RUN/gl_spi.log
fi
if [[ $WHAT == seq || $WHAT == all ]]; then
    t0=$SECONDS
    { comp build/gl_seq0.vvp gl_sdf_r14 -DFUNCTIONAL $RTL $HERE/gl_sdf_r14.sv $CELLS && vvp -n build/gl_seq0.vvp
      echo "exit $?"; } > $RUN/gl_seq_zero.log 2>&1
    echo "gl_sdf_r14 without delays: $((SECONDS - t0)) s" >> $RUN/gl_seq_zero.log
    verdict gl_sdf_r14_zero_delay $RUN/gl_seq_zero.log
fi
if [[ $WHAT == sdf ]]; then
    # the SDF of 3 corners (LibreLane final/sdf), the design's CELLTYPE renamed as the netlist's module; the cell models
    # with the mux / xor ifnone edge paths written as plain paths (Icarus drops "ifnone (posedge S => ...)", so those
    # arcs would get no delay: gf180/tapeout/rtl/gl_sdf_prep.sh, the same transform)
    mkdir -p $RUN/sdf
    src=$SCL/gf180mcu_fd_sc_mcu9t5v0.v
    perl -0777 -pe 's/ifnone[ \t]*\n((?:[ \t]*\/\/[^\n]*\n)?)([ \t]*)\(posedge (\w+) => \((\w+):\w+\)\) = (\([^)]*\));/$1$2($3 => $4) = $5;/g;
                    s/ifnone[ \t]*\n(?:[ \t]*\/\/[^\n]*\n)?[ \t]*\(negedge \w+ => \(\w+:\w+\)\) = \([^)]*\);[ \t]*\n//g' \
        $src > $RUN/sdf/cells_9t.v
    pids=()
    for c in max_ss_125C_3v00 nom_tt_025C_3v30 min_ff_n40C_3v60; do
        sed 's/(CELLTYPE "eeg_digital_top")/(CELLTYPE "eeg_digital_top_gl")/' $MAC/final/sdf/$c/eeg_digital_top__$c.sdf > $RUN/sdf/$c.sdf
        case $c in max_*) t=max ;; min_*) t=min ;; *) t=typ ;; esac
        ( t0=$SECONDS
          { comp build/gl_sdf_$c.vvp gl_sdf_r14 "-gspecify -ginterconnect -T$t -DGL_SDF -DGL_SDF_FILE=\"$RUN/sdf/$c.sdf\"" \
                 $RTL $HERE/gl_sdf_r14.sv $SCL/primitives.v $RUN/sdf/cells_9t.v && vvp -n build/gl_sdf_$c.vvp
            echo "exit $?"; } > $RUN/gl_sdf_$c.log 2>&1
          echo "gl_sdf_r14 with the SDF of $c: $((SECONDS - t0)) s" >> $RUN/gl_sdf_$c.log ) &
        pids+=($!)
    done
    wait
    for c in max_ss_125C_3v00 nom_tt_025C_3v30 min_ff_n40C_3v60; do
        n=$(grep -E "^SDF (ERROR|WARNING)" $RUN/gl_sdf_$c.log | grep -c -v "TIMINGCHECK not supported")
        echo "SDF $c: $n SDF errors / warnings besides the timing checks" >> $RUN/gl_sdf_$c.log
        verdict "gl_sdf_r14_$c" $RUN/gl_sdf_$c.log
    done
fi
date
printf '%s\n' "${res[@]}" | tee -a $RUN/summary.txt
