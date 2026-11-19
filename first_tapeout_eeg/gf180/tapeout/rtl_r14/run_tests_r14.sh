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
declare -a RES
run() {   # name, command
    local name=$1; shift
    local t0=$SECONDS
    if "$@" > "build/$name.log" 2>&1 && grep -q "PASS" "build/$name.log" && ! grep -q "FAIL" "build/$name.log"; then
        RES+=("PASS  $name  $((SECONDS - t0)) s")
    else
        RES+=("FAIL  $name  (build/$name.log)")
    fi
}
spec() { (cd ../rtl/spec && $PY fsm_spec.py check && $PY fsm_spec.py selftest && $PY regmap.py check &&
          $PY regmap.py selftest) | sed 's/^no violations$/PASS: no violations/'; }
seq_t() { $IV -o build/tb_seq.vvp eeg_seq.sv tb/tb_seq.sv 2>&1 | grep -v "sorry: constant" ;
          vvp -n build/tb_seq.vvp +n=600000 +seed=11 +trace=build/seq_trace.txt && $PY tb/check_seq_trace.py build/seq_trace.txt; }
tick_t() { $IV -o build/tb_tick.vvp eeg_clkgen.sv tb/tb_tick.sv && vvp -n build/tb_tick.vvp; }
cic_t() { $PY tb/check_cic_arm.py gen 7 13 && $IV -o build/tb_cic_arm.vvp eeg_cic3.sv ../rtl/eeg_rnd_sat.sv tb/tb_cic_arm.sv &&
          for k in 3 5 7 9; do vvp -n build/tb_cic_arm.vvp +k=$k > /dev/null && $PY tb/check_cic_arm.py check $k || return 1; done; }
ovl_t() { $IV -o build/tb_ovl.vvp eeg_ovl.sv tb/tb_ovl.sv && vvp -n build/tb_ovl.vvp > /dev/null &&
          $PY - <<'EOF'
import numpy as np
c = np.loadtxt("build/ovl.codes", dtype=int); g = np.loadtxt("build/ovl.out", dtype=int)
e = (np.convolve(np.isin(c, (0, 31)).astype(int), np.ones(32, dtype=int))[:len(c)] >= 4).astype(int)
n = min(len(g), len(e)); bad = int((g[:n] != e[:n]).sum())
print(f"{n} frames, {bad} mismatches"); print("PASS" if bad == 0 else "FAIL")
EOF
}
top_t() { $PY tb/gen_reg_tests.py && $IV -o build/tb_top_r14.vvp $RTL tb/tb_top_r14.sv 2>&1 | grep -v "sorry: constant" ;
          vvp -n build/tb_top_r14.vvp && $PY tb/check_top_r14.py; }
spi_t() { $IV -o build/tb_spi_r14.vvp $RTL tb/tb_spi_r14.sv 2>&1 | grep -v "sorry: constant" ;
          vvp -n build/tb_spi_r14.vvp +n=1500 +seed=5 +log=build/spi_trace.txt && $PY tb/check_spi_trace.py build/spi_trace.txt; }
run spec spec
run tb_seq seq_t
run tb_tick tick_t
run tb_cic_arm cic_t
[ -f build/ovl.codes ] && run tb_ovl ovl_t
run tb_top_r14 top_t
run tb_spi_r14 spi_t
top4_t() { $IV -DFIFO4 -o build/tb_top_r14_f4.vvp $RTL tb/tb_top_r14.sv 2>&1 | grep -v "sorry: constant" ;
           vvp -n build/tb_top_r14_f4.vvp && $PY tb/check_top_r14.py; }
run tb_top_r14_fifo4 top4_t
printf '%s\n' "${RES[@]}"
! printf '%s\n' "${RES[@]}" | grep -q FAIL
