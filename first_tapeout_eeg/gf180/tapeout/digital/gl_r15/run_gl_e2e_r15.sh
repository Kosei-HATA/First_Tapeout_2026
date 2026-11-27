#!/bin/zsh
# 11/28: VER-04 at gate level: the s4 stream in N chunks (each from its own RESET_N release at a stream offset, the
# chunks overlapping by their start-up) through tb_e2e_r15 with the macro's final netlist in lockstep (gl_shadow_r15,
# zero delay, every MCLK cycle: 50 outputs and the 2 state registers), every sample checked against the golden CIC
# (check_e2e_r15.py). The netlist and its register names from a prepared gate-level run (run_gl_r15.sh <tag> <rev>
# prep); the sources from a commit (git archive), the RTL's sha256 checked against the macro's.
# usage: run_gl_e2e_r15.sh <macro tag> <commit> [chunks (5)] [samples per chunk (840)]
# out: gf180/tapeout/digital/eeg_digital_top_r15/runs/gl_<tag>/e2e/
set -u
TAG=${1:?usage: run_gl_e2e_r15.sh <macro tag> <commit> [chunks] [samples]}
REV=${2:?commit}
N=${3:-5}
NS=${4:-840}
ROOT=/Users/noah/Codings/First_Tapeout_2026
T=$ROOT/first_tapeout_eeg/gf180/tapeout
HERE=$T/digital/gl_r15
MAC=$T/digital/eeg_digital_top_r15/runs/$TAG
RUN=$T/digital/eeg_digital_top_r15/runs/gl_$TAG
E=$RUN/e2e
PY=$ROOT/first_tapeout_eeg/gf180/tools/venv310/bin/python
SCL=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/verilog
[ -f $RUN/gl_names.svh ] || { echo "no prepared netlist in $RUN (run_gl_r15.sh $TAG <rev> prep)"; exit 1; }
shasum -a 256 -c $RUN/netlist.sha256 > /dev/null || { echo "FAIL: the netlist changed since prep"; exit 1; }
SRC=$E/src/first_tapeout_eeg/gf180/tapeout
mkdir -p $E/src
if [ ! -f $E/src/.done ]; then
    (cd $ROOT && git archive $REV first_tapeout_eeg/gf180/tapeout/rtl_r15 first_tapeout_eeg/gf180/tapeout/rtl/eeg_chop1.sv \
        first_tapeout_eeg/gf180/tapeout/rtl/eeg_raw.sv first_tapeout_eeg/gf180/tapeout/rtl/eeg_rnd_sat.sv \
        first_tapeout_eeg/gf180/tapeout/rtl/model) | tar -x -C $E/src || exit 1
    echo "$REV" > $E/src/.done
fi
[ "$(cat $E/src/.done)" = "$REV" ] || { echo "the copy in $E/src is of $(cat $E/src/.done), not $REV"; exit 1; }
(cd $SRC && shasum -a 256 rtl_r15/eeg_*.sv rtl/eeg_chop1.sv rtl/eeg_raw.sv rtl/eeg_rnd_sat.sv rtl_r15/spec/eeg_regs_defs.svh) > $E/src_sha256.txt
cmp -s $E/src_sha256.txt $RUN/src_sha256.txt || { echo "FAIL: the RTL of $REV differs from the macro's (gl run's src_sha256.txt)"; exit 1; }
CODES=$T/rtl/build/e2e/s4.codes
CELLS=($SCL/primitives.v $SCL/gf180mcu_fd_sc_mcu9t5v0.v)
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
cd $SRC/rtl_r15 || exit 1
iverilog -g2012 -I spec -I tb -I $RUN -DFUNCTIONAL -DTB=tb_e2e_r15 -s tb_e2e_r15 -s gl_shadow_r15 -o $E/gl_e2e.vvp \
    $RTL tb/tb_e2e_r15.sv $CELLS $HERE/gl_shadow_r15.sv $RUN/eeg_digital_top_gl.v > $E/comp.log 2>&1 || {
    grep -v 'sorry: constant' $E/comp.log | head; echo "FAIL: compile"; exit 1; }
grep -q "warning: Port .* expects" $E/comp.log && { echo "FAIL: a port connected at another width"; exit 1; }
NF=$(stat -f %z $CODES)
STRIDE=$(( (NF + N - 1) / N ))
date
echo "s4: $NF frames, $N chunks of $NS samples from stream offsets k x $STRIDE (each chunk covers ~$(( (NS + 3) * 1024 + 6144 )) frames)"
for k in $(seq 0 $((N - 1))); do
    ( t0=$SECONDS
      vvp -n $E/gl_e2e.vvp +codes=$CODES +nsamp=$NS +start=$((k * STRIDE)) +log=$E/c$k.log > $E/c$k.run.out 2>&1
      echo "vvp rc $?, $((SECONDS - t0)) s" >> $E/c$k.run.out
      $PY tb/check_e2e_r15.py $CODES $E/c$k.log > $E/c$k.check.out 2>&1 ) &
done
wait
date
ok=1
for k in $(seq 0 $((N - 1))); do
    g=$(grep '^PASS: gate level' $E/c$k.run.out)
    b=$(grep '^PASS: tb_e2e_r15' $E/c$k.run.out)
    c=$(grep '^PASS: every sample' $E/c$k.check.out)
    if [[ -n $g && -n $b && -n $c ]] && ! grep -qE 'FAIL|GL MISMATCH' $E/c$k.run.out $E/c$k.check.out; then
        echo "PASS  chunk $k (start $((k * STRIDE))): $g; $(head -1 $E/c$k.check.out | cut -c1-90)"
    else
        echo "FAIL  chunk $k (see $E/c$k.run.out, c$k.check.out)"; ok=0
    fi
done
[[ $ok == 1 ]] && echo "GL_E2E_R15 PASS" || echo "GL_E2E_R15 FAIL"
