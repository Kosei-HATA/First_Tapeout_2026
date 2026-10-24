#!/usr/bin/env bash
# Run all digital-block tests: golden-model self checks, vector generation,
# unit testbenches and the integrated top-level tests.
#
# usage: ./run_tests.sh [--quick] [--gl]
#   --quick  skip the long CIC stream test (20,000+ outputs, about 1 minute)
#   --gl     also run tb_spi and tb_top (DAC_LOAD_CYCLE = 2) with the LibreLane
#            gate-level netlists of both macros in lockstep (tb/gl_shadow.sv):
#            every output and inter-block wire equal to the RTL at every MCLK
#            (about 10 minutes more)
#
# Tools (override with environment variables):
#   IVERILOG (default: iverilog), VVP (default: vvp),
#   PYTHON   (default: /opt/homebrew/anaconda3/bin/python3 if present, else python3)
#   PDK_ROOT (default: the LibreLane work copy's gf180mcu; cell models for --gl)
#   GL_TOP_NL, GL_ADC_NL (default: the chip's netlists in ../layout/gds/), GL_TAG (a
#   suffix for the names of the --gl tests, e.g. a candidate macro run)
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
GL=0
for arg in "$@"; do
    case $arg in
        --quick) QUICK=1 ;;
        --gl)    GL=1 ;;
        *) echo "usage: $0 [--quick] [--gl]"; exit 1 ;;
    esac
done
PDK_ROOT=${PDK_ROOT:-/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu}
SCL=$PDK_ROOT/gf180mcuD/libs.ref
GL_TOP_NL=${GL_TOP_NL:-../layout/gds/eeg_digital_top.nl.v}
GL_ADC_NL=${GL_ADC_NL:-../layout/gds/eeg_adc_dig.nl.v}
GLS=${GL_TAG:+_$GL_TAG}

BUILD=build
LOGS=$BUILD/logs
mkdir -p "$LOGS" "$BUILD/gl"

RTL="eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv
     eeg_fifo.sv eeg_regs.sv eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv
     eeg_digital_sys.sv"
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

# run_sim name top "extra iverilog args" "plusargs" [gl]
# gl: add the gate-level netlists in lockstep (second root gl_shadow); no -Wall,
# since the cell models warn about implicit wires and inherited timescales
run_sim() {
    local name=$1 top=$2 ivargs=$3 plusargs=$4 gl=${5:-}
    local log=$LOGS/$name.log t0=$SECONDS
    local flags=$IVFLAGS extra="" roots="-s $top"
    if [ -n "$gl" ]; then
        sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' "$GL_TOP_NL" > $BUILD/gl/eeg_digital_top_gl.v
        sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' "$GL_ADC_NL" > $BUILD/gl/eeg_adc_dig_gl.v
        flags="-g2012 -I tb -DFUNCTIONAL -DTB=$top"
        roots="-s $top -s gl_shadow"
        extra="tb/gl_shadow.sv $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/gf180mcu_fd_sc_mcu9t5v0.v
               $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v
               $BUILD/gl/eeg_digital_top_gl.v $BUILD/gl/eeg_adc_dig_gl.v"
    fi
    # shellcheck disable=SC2086
    if ! $IVERILOG $flags $ivargs -o "$BUILD/$name.vvp" $roots $RTL "tb/$top.sv" $extra > "$log" 2>&1; then
        record "$name" FAIL $((SECONDS - t0)) "compile error, see $log"
        return
    fi
    # shellcheck disable=SC2086
    $VVP -n "$BUILD/$name.vvp" $plusargs >> "$log" 2>&1
    local result
    result=$(grep -E "^(PASS|FAIL)" "$log" | tail -n 1)
    if [ -n "$gl" ] && ! grep -q -E "^PASS: gate level" "$log"; then
        record "$name" FAIL $((SECONDS - t0)) "no gate-level result, see $log"
    elif [ -n "$result" ] && ! grep -q -E "^FAIL" "$log"; then
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
if [ $GL -eq 1 ]; then
    echo "gate level: $GL_TOP_NL, $GL_ADC_NL"
    run_sim spi_fifo_regs_gl$GLS tb_spi "" "" gl
    run_sim top_dlc2_gl$GLS      tb_top "-Ptb_top.DLC=2 -Ptb_top.NSAMP=40" "" gl
fi

echo
echo "== summary: $npass passed, $nfail failed =="
[ $nfail -eq 0 ]
