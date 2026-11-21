#!/usr/bin/env bash
# r14 digital control: the specification checks and every RTL test, with a summary. A group passes only if every
# command in it exits 0 (a failed compile included) and its log has PASS and no FAIL or ERROR.
#   spec        gf180/tapeout/rtl/spec: fsm_spec.py check, selftest, fresh; regmap.py check, selftest, fresh;
#               wave.py selftest, fresh (the generated diagrams, tables and timing diagrams equal what the sources
#               give; the timing diagrams agree with the tables, audit round 15)
#   codes       the CT loop model's code streams (tb/gen_codes.py)
#   tb_seq      the sequencer on random events, replayed through fsm_spec.seq_tick (every cell of the table; the
#               timer modelled independently: every load, decrement and restart), and tb_seq_exh: every state
#               value x event x command x condition x timer deposited for one step, every branch 8 times or
#               more, independent of the random seed (audit round 22)
#   tb_tick     the tick in the middle of chopper phase A, once per period, both rates, rate changes
#   tb_clkgen   the frame timing and the chopper clocks (rtl/tb/tb_clkgen.sv with the r14 clock generator)
#   tb_chop1    CHOP1: rates, e16 edges, phase lengths, the rate taken at the 1 ms boundary on the output grid
#               (rtl/tb/tb_chop1.sv with the r14 clock generator; ANA-04)
#   tb_cic_arm  the CIC cleared at an output time == golden CIC (four positions), output grid kept
#   tb_ovl      the overload detector, the hits and the interval flags == regmap.OVL_RULE (overload runs +
#               full-scale stream; tb/check_ovl.py)
#   tb_rnd_sat  the CIC output's rounding (ties to even) and saturation against the Python golden model's vectors
#               (rtl/tb/tb_rnd_sat.sv, rtl/model/gen_vectors.py)
#   tb_regs     the W1C flags: a set in the cycle of its clear wins; per-bit clear; cfg_ok and nr_ok against
#               regmap over the full 10-bit M (build/ok_vectors.txt from tb/gen_ok_vectors.py)
#   tb_fifo, tb_fifo4  the FIFO (depth 8 and 4) against fsm_spec.fifo_step and an identity model
#   tb_top_r14  the whole block through its pins (phases A to V, K, then W, X and Y, listed in the bench's header, and the
#               pad monitors); samples == golden
#               CIC (check_top_r14.py); every sequencer event replayed through fsm_spec (check_seq_trace.py)
#   tb_spi_r14  random SPI frames into the whole block, replayed through fsm_spec's SPI table (check_spi_trace.py)
#   tb_top_r14_fifo4  tb_top_r14 with a 4-deep FIFO (FIFO4)
#   outputs     every output of eeg_digital_top is a flip-flop's (NFR-06); every asynchronous input passes 2 flops; every
#               flip-flop resets asynchronously from RESET_N's release (RST-01); the state registers of eeg_seq and
#               eeg_spi_slave keep fsm_encoding "none" (NFR-05 through synthesis) (yosys, tb/check_outputs_registered.py)
#   The testbenches' own mutation self-test (each listed RTL error must be detected): tb/mutate_top_r14.py
#   A bench run alone needs this script's generated inputs first (codes: build/top_r14.codes and ovl.codes;
#   tb/gen_reg_tests.py: build/reg_tests.svh and pin_tests.svh): without the code stream tb_top_r14's CODE is X and
#   every phase fails (audit round 15)
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
    if "$@" > "build/$name.log" 2>&1 && grep -q "PASS" "build/$name.log" && ! grep -qE "FAIL|ERROR" "build/$name.log"; then
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
          for k in 3 5 7 9; do vvp -n build/tb_cic_arm.vvp +k=$k > /dev/null && $PY tb/check_cic_arm.py check $k || return 1; done; }
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
run spec spec
run codes codes
run tb_seq seq_t
run tb_tick tick_t
run tb_clkgen clkgen_t
run tb_chop1 chop1_t
run tb_cic_arm cic_t
run tb_ovl ovl_t
run tb_rnd_sat rnd_t
run tb_regs regs_t
run tb_fifo fifo_t
run tb_fifo4 fifo4_t
run tb_top_r14 top_t
run tb_spi_r14 spi_t
run tb_top_r14_fifo4 top4_t
run outputs outputs_t
printf '%s\n' "${RES[@]}"
! printf '%s\n' "${RES[@]}" | grep -q FAIL
