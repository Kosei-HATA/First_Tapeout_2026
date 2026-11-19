#!/usr/bin/env bash
# r14 digital control: the specification checks and every RTL test, with a summary.
#   1. gf180/tapeout/rtl/spec: fsm_spec.py check + selftest, regmap.py check + selftest
#   2. tb_seq    the sequencer on random events, replayed through fsm_spec.seq_tick (every cell of the table; the
#                timer modelled independently: every load, decrement and restart)
#   3. tb_tick   the tick in the middle of chopper phase A, once per period, both rates, rate changes
#   4. tb_cic_arm the CIC cleared at an output time == golden CIC (four positions), output grid kept
#   5. tb_ovl    the overload detector == the rule (overload runs + full-scale stream)
#   6. tb_top_r14 the whole block through its pins: generated register tests (regmap.py), CRC and frame errors,
#                START timing, APPLY pulse, APPLY_NR, errors, pending command at 64 kHz, FLUSH, overrun,
#                a read across a FLUSH, DRDY_N pulses, SOFT_RESET (also with a command pending), analog pins only
#                at ticks; samples == golden CIC (check_top_r14.py)
#   7. tb_spi_r14 random SPI frames into the whole block, replayed through fsm_spec's SPI table (every frame, every
#                branch covered; check_spi_trace.py)
#   8. tb_top_r14 again with a 4-deep FIFO (FIFO4)
#   The testbenches' own mutation self-test (each listed RTL error must be detected): tb/mutate_top_r14.py
# usage: ./run_tests_r14.sh
set -u
cd "$(dirname "$0")"
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
    [ $rc -eq 0 ] && [ -f "$out" ]
}
run() {   # name, command
    local name=$1; shift
    local t0=$SECONDS
    if "$@" > "build/$name.log" 2>&1 && grep -q "PASS" "build/$name.log" && ! grep -q "FAIL" "build/$name.log"; then
        RES+=("PASS  $name  $((SECONDS - t0)) s")
    else
        RES+=("FAIL  $name  (build/$name.log)")
    fi
}
# spec: every checker and self-test must exit 0 (PASS is printed only then)
spec() { (cd ../rtl/spec && $PY fsm_spec.py check && $PY fsm_spec.py selftest && $PY regmap.py check &&
          $PY regmap.py selftest) && echo "PASS: spec checks and self-tests"; }
codes() { $PY tb/gen_codes.py && echo "PASS: code streams"; }
seq_t() { comp build/tb_seq.vvp eeg_seq.sv tb/tb_seq.sv &&
          vvp -n build/tb_seq.vvp +n=600000 +seed=11 +trace=build/seq_trace.txt && $PY tb/check_seq_trace.py build/seq_trace.txt; }
tick_t() { comp build/tb_tick.vvp eeg_clkgen.sv tb/tb_tick.sv && vvp -n build/tb_tick.vvp; }
cic_t() { $PY tb/check_cic_arm.py gen 7 13 && comp build/tb_cic_arm.vvp eeg_cic3.sv ../rtl/eeg_rnd_sat.sv tb/tb_cic_arm.sv &&
          for k in 3 5 7 9; do vvp -n build/tb_cic_arm.vvp +k=$k > /dev/null && $PY tb/check_cic_arm.py check $k || return 1; done; }
# the overload rule on every frame of the extracted overload runs (it must fire) and of the full scale (never)
ovl_t() { comp build/tb_ovl.vvp eeg_ovl.sv tb/tb_ovl.sv && vvp -n build/tb_ovl.vvp > /dev/null &&
          $PY - <<'EOF'
import numpy as np
c = np.loadtxt("build/ovl.codes", dtype=int); g = np.loadtxt("build/ovl.out", dtype=int)
split = int(open("build/ovl.split").read()) + 32   # the full scale after the 32-frame window left the overload runs
e = (np.convolve(np.isin(c, (0, 31)).astype(int), np.ones(32, dtype=int))[:len(c)] >= 4).astype(int)
bad = int((g != e).sum()) if len(g) == len(e) else -1
print(f"{len(g)} of {len(c)} frames compared, {bad} mismatches; detections: overload runs {int(g[:split].sum())}, "
      f"full scale {int(g[split:].sum())}")
print("PASS" if bad == 0 and g[:split].sum() > 0 and g[split:].sum() == 0 else "FAIL")
EOF
}
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
run spec spec
run codes codes
run tb_seq seq_t
run tb_tick tick_t
run tb_cic_arm cic_t
run tb_ovl ovl_t
run tb_fifo fifo_t
run tb_fifo4 fifo4_t
run tb_top_r14 top_t
run tb_spi_r14 spi_t
run tb_top_r14_fifo4 top4_t
printf '%s\n' "${RES[@]}"
! printf '%s\n' "${RES[@]}" | grep -q FAIL
