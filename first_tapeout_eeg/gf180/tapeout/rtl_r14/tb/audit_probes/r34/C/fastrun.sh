#!/usr/bin/env bash
# fastrun (audit 34, C): the functions of run_tests_r14.sh at 5e1c8f6c, run in early-exit order on a mutant copy
# usage: fastrun.sh <rtl_r14 dir of the copy>
set -u
cd "$1" || exit 2
PY=${PYTHON:-/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python}
IV="iverilog -g2012 -I ../rtl/spec -I tb -I build"
RTL="eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv \
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv"
mkdir -p build
set -o pipefail
declare -a RES
# compile: a failed compile fails the group (the stale .vvp is removed first, so it can never run instead)
comp() {   # out.vvp, iverilog arguments...
    local out=$1; shift
    rm -f "$out"
    $IV -o "$out" "$@" > "$out.log" 2>&1
    local rc=$?
    grep -v "sorry: constant" "$out.log"
    # a port connected at another width is only a warning in iverilog (audit round 33, auditor C: an eeg_regs whose
    # t_warm port was 7 bits passed all 16 groups): it fails the compile here
    if grep -q "warning: Port .* expects" "$out.log"; then echo "FAIL: a port connected at another width ($out)"; return 1; fi
    [ $rc -eq 0 ] && [ -f "$out" ]
}
killtree() { local c; for c in $(pgrep -P "$1"); do killtree "$c"; done; kill -TERM "$1" 2>/dev/null; }
run() {   # name, time limit [s], command
    local name=$1 lim=$2; shift 2
    local t0=$SECONDS rc
    "$@" > "build/$name.log" 2>&1 &
    local pid=$!
    while kill -0 "$pid" 2>/dev/null && (( SECONDS - t0 < lim )); do sleep 1; done
    if kill -0 "$pid" 2>/dev/null; then
        killtree "$pid"
        wait "$pid" 2>/dev/null
        echo "FAIL: $name stopped at its time limit of $lim s" >> "build/$name.log"
        RES+=("FAIL  $name  (time limit $lim s; build/$name.log)")
        return
    fi
    wait "$pid"; rc=$?
    if [ $rc -eq 0 ] && grep -q "PASS" "build/$name.log" && ! grep -qE "FAIL|ERROR" "build/$name.log"; then
        RES+=("PASS  $name  $((SECONDS - t0)) s")
    else
        RES+=("FAIL  $name  (build/$name.log)")
    fi
}
# spec: every checker and self-test must exit 0 (PASS is printed only then)
spec() { (cd ../rtl/spec && $PY fsm_spec.py check && $PY fsm_spec.py selftest && $PY regmap.py check &&
          $PY regmap.py selftest && $PY wave.py selftest && $PY fsm_spec.py fresh && $PY regmap.py fresh &&
          $PY wave.py fresh) &&
        echo "PASS: spec checks, self-tests, generated files up to date"; }
codes() { $PY tb/gen_codes.py && echo "PASS: code streams"; }
seq_t() { comp build/tb_seq.vvp eeg_seq.sv tb/tb_seq.sv &&
          vvp -n build/tb_seq.vvp +n=600000 +seed=11 +trace=build/seq_trace.txt && $PY tb/check_seq_trace.py build/seq_trace.txt &&
          comp build/tb_seq_exh.vvp eeg_seq.sv tb/tb_seq_exh.sv &&
          vvp -n build/tb_seq_exh.vvp +trace=build/seq_exh.txt && $PY tb/check_seq_exh.py build/seq_exh.txt; }
tick_t() { comp build/tb_tick.vvp eeg_clkgen.sv tb/tb_tick.sv && vvp -n build/tb_tick.vvp; }
clkgen_t() { comp build/tb_clkgen.vvp eeg_clkgen.sv ../rtl/tb/tb_clkgen.sv && vvp -n build/tb_clkgen.vvp; }
# CHOP1 with the r14 clock generator: rates, e16 edges, phase lengths, the rate taken at the 1 ms boundary (ANA-04)
chop1_t() { comp build/tb_chop1.vvp eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/tb/tb_chop1.sv && vvp -n build/tb_chop1.vvp; }
cic_t() { $PY tb/check_cic_arm.py gen 7 13 && comp build/tb_cic_arm.vvp eeg_cic3.sv ../rtl/eeg_rnd_sat.sv tb/tb_cic_arm.sv &&
          for k in 3 5 7 9; do vvp -n build/tb_cic_arm.vvp +k=$k > /dev/null && $PY tb/check_cic_arm.py check $k || return 1; done &&
          for k2 in 6 7; do vvp -n build/tb_cic_arm.vvp +k=5 +k2=$k2 > /dev/null && $PY tb/check_cic_arm.py check 5 $k2 || return 1; done; }
# the overload rule on every frame of the extracted overload runs (it must fire) and of the full scale (never)
ovl_t() { comp build/tb_ovl.vvp eeg_ovl.sv tb/tb_ovl.sv && vvp -n build/tb_ovl.vvp > /dev/null && $PY tb/check_ovl.py; }
regs_t() { $PY tb/gen_ok_vectors.py && comp build/tb_regs.vvp eeg_regs.sv tb/tb_regs.sv && vvp -n build/tb_regs.vvp; }
rnd_t() { $PY -c "import sys; sys.path.insert(0, '../rtl/model'); import gen_vectors as G; G.gen_rnd_sat('build', sys.stdout)" &&
          comp build/tb_rnd_sat.vvp ../rtl/eeg_rnd_sat.sv ../rtl/tb/tb_rnd_sat.sv && vvp -n build/tb_rnd_sat.vvp +vec=build/rnd_sat.vec; }
outputs_t() { $PY tb/check_outputs_registered.py; }
fifo_t() { comp build/tb_fifo.vvp eeg_fifo.sv tb/tb_fifo.sv &&
           vvp -n build/tb_fifo.vvp +n=400000 +trace=build/fifo_trace.txt && $PY tb/check_fifo_trace.py build/fifo_trace.txt; }
fifo4_t() { comp build/tb_fifo4.vvp -DDEPTH4 eeg_fifo.sv tb/tb_fifo.sv &&
            vvp -n build/tb_fifo4.vvp +n=400000 +trace=build/fifo4_trace.txt && $PY tb/check_fifo_trace.py build/fifo4_trace.txt; }
top_t() { $PY tb/gen_reg_tests.py && comp build/tb_top_r14.vvp $RTL tb/tb_top_r14.sv &&
          vvp -n build/tb_top_r14.vvp && $PY tb/check_top_r14.py &&
          $PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover; }
spi_t() { comp build/tb_spi_r14.vvp $RTL tb/tb_spi_r14.sv &&
          vvp -n build/tb_spi_r14.vvp +n=1500 +seed=5 +log=build/spi_trace.txt && $PY tb/check_spi_trace.py build/spi_trace.txt; }
top4_t() { comp build/tb_top_r14_f4.vvp -DFIFO4 $RTL tb/tb_top_r14.sv &&
           vvp -n build/tb_top_r14_f4.vvp && $PY tb/check_top_r14.py &&
           $PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover; }
ORDER=(codes:600:codes tb_regs:600:regs_t tb_seq:1200:seq_t tb_tick:600:tick_t tb_clkgen:600:clkgen_t tb_chop1:600:chop1_t
       tb_cic_arm:600:cic_t tb_ovl:600:ovl_t tb_rnd_sat:600:rnd_t tb_fifo:900:fifo_t tb_fifo4:900:fifo4_t outputs:1200:outputs_t
       ${EXTRA_ORDER:-tb_spi_r14:3600:spi_t tb_top_r14:5400:top_t tb_top_r14_fifo4:5400:top4_t})
for g in "${ORDER[@]}"; do
    IFS=: read -r nm lim fn <<< "$g"
    run "$nm" "$lim" "$fn"
    last="${RES[${#RES[@]}-1]}"
    echo "$(date +%H:%M:%S) $last"
    if [[ "$last" == FAIL* ]]; then echo "DETECTED by $nm"; exit 1; fi
done
echo "ALL RTL GROUPS PASS (mutant MISSED; spec and codes read no RTL)"
exit 0
