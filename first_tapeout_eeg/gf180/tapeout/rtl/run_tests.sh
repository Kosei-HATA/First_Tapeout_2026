#!/usr/bin/env bash
# Run all digital-block tests: golden-model self checks, vector generation,
# unit testbenches and the integrated top-level tests.
#
# usage: ./run_tests.sh [--quick]
#   --quick  skip the long CIC stream test (20,000+ outputs, about 1 minute)
#
# Tools (override with environment variables):
#   IVERILOG (default: iverilog), VVP (default: vvp),
#   PYTHON   (default: /opt/homebrew/anaconda3/bin/python3 if present, else python3)
# Outputs go to build/ (vectors, compiled simulations, one log per test).
# No waveform files are written.

set -u
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
IVERILOG=${IVERILOG:-iverilog}
VVP=${VVP:-vvp}
if [ -z "${PYTHON:-}" ]; then
    if [ -x /opt/homebrew/anaconda3/bin/python3 ]; then
        PYTHON=/opt/homebrew/anaconda3/bin/python3
    else
        PYTHON=python3
    fi
fi

QUICK=0
[ "${1:-}" = "--quick" ] && QUICK=1

BUILD=build
LOGS=$BUILD/logs
mkdir -p "$LOGS"

RTL="eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv
     eeg_fifo.sv eeg_regs.sv eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv"
IVFLAGS="-g2012 -Wall -I tb"

npass=0
nfail=0

record() {   # name status seconds detail
    printf "%-4s  %-16s %4ss  %s\n" "$2" "$1" "$3" "$4"
    if [ "$2" = "PASS" ]; then npass=$((npass + 1)); else nfail=$((nfail + 1)); fi
}

# run_python name command...
run_python() {
    local name=$1; shift
    local log=$LOGS/$name.log t0=$SECONDS
    if "$@" > "$log" 2>&1; then
        record "$name" PASS $((SECONDS - t0)) "$(tail -n 1 "$log")"
    else
        record "$name" FAIL $((SECONDS - t0)) "see $log"
    fi
}

# run_sim name top "extra iverilog args" "plusargs"
run_sim() {
    local name=$1 top=$2 ivargs=$3 plusargs=$4
    local log=$LOGS/$name.log t0=$SECONDS
    # shellcheck disable=SC2086
    if ! $IVERILOG $IVFLAGS $ivargs -o "$BUILD/$name.vvp" -s "$top" $RTL "tb/$top.sv" > "$log" 2>&1; then
        record "$name" FAIL $((SECONDS - t0)) "compile error, see $log"
        return
    fi
    # shellcheck disable=SC2086
    $VVP -n "$BUILD/$name.vvp" $plusargs >> "$log" 2>&1
    local result
    result=$(grep -E "^(PASS|FAIL)" "$log" | tail -n 1)
    if [ -n "$result" ] && ! grep -q -E "^FAIL" "$log"; then
        record "$name" PASS $((SECONDS - t0)) "${result#PASS: }"
    else
        record "$name" FAIL $((SECONDS - t0)) "${result:-no result line, see $log}"
    fi
}

echo "== GF180 EEG ADC digital block: RTL tests =="
echo "iverilog: $($IVERILOG -V 2>&1 | head -n 1)"
echo "python:   $($PYTHON --version 2>&1)"
echo

run_python golden_selfcheck $PYTHON model/cic_golden.py
run_python gen_vectors      $PYTHON model/gen_vectors.py "$BUILD"
if [ $nfail -ne 0 ]; then
    echo "model self check or vector generation failed, stopping"
    exit 1
fi

run_sim therm2bin   tb_therm2bin "" ""
run_sim dwa         tb_dwa       "" ""
run_sim clkgen      tb_clkgen    "" ""
run_sim chop1       tb_chop1     "" ""
run_sim rnd_sat     tb_rnd_sat   "" "+vec=$BUILD/rnd_sat.vec"
run_sim cic_impulse tb_cic       "" "+ops=$BUILD/cic_impulse.ops +gold=$BUILD/cic_impulse.gold +name=impulse +gaps"
run_sim cic_step    tb_cic       "" "+ops=$BUILD/cic_step.ops +gold=$BUILD/cic_step.gold +name=step +gaps"
if [ $QUICK -eq 0 ]; then
    run_sim cic_stream tb_cic "" "+ops=$BUILD/cic_stream.ops +gold=$BUILD/cic_stream.gold +name=stream +gaps"
fi
run_sim spi_fifo_regs tb_spi     "" ""
run_sim top_dlc2      tb_top     "-Ptb_top.DLC=2 -Ptb_top.NSAMP=40" ""
run_sim top_dlc5      tb_top     "-Ptb_top.DLC=5 -Ptb_top.NSAMP=12" ""

echo
echo "== summary: $npass passed, $nfail failed =="
[ $nfail -eq 0 ]
