#!/usr/bin/env bash
# End-to-end bit-true test of the digital block (tracker C2) with code streams from
# the CT sigma-delta behavioral loop (model/ct2_codes.py): 4 s and 20 s of 1 kSPS
# output, read over SPI and compared with the bit-exact CIC model, plus the
# spectrum of the output (model/e2e_spectrum.py).
#
# usage: ./run_e2e.sh [--gl] case...
#   short  the first 100 samples of s4 (check of the flow, about 1 minute)
#   s4     32 Hz at full scale (0.279 V pk) + 44.5 mV DC + 2 mV pk at 128 kHz,
#          4250 samples (0.25 s settling + 4 s record), about 25 minutes
#   s20    0.5 Hz at full scale - 44.5 mV DC + 900 Hz at 27.9 mV pk (alias check),
#          20250 samples (0.25 s + 20 s), about 2 hours
#   s4:K/N chunk K (0..N-1) of the s4 stream, from reset like a stream of its own
#          (the gate-level s4 split over parallel runs)
#   --gl   also run the LibreLane gate-level netlists of both macros in lockstep
#          (tb/gl_shadow.sv), about 20 times slower
#
# Tools (environment): IVERILOG, VVP, PYTHON (default: ../../tools/venv310/bin/python,
# with numpy and scipy), PDK_ROOT (default: the LibreLane work copy's gf180mcu, for
# the cell models of gf180mcu_fd_sc_mcu7t5v0 and _mcu9t5v0), GL_TOP_NL / GL_ADC_NL
# (default: the chip's netlists in ../layout/gds/) and GL_TAG (a suffix for the
# gate-level case names, e.g. a candidate macro run).
# Outputs in build/e2e/: <case>.codes / .gold (stimulus and golden), <case>[_gl].log,
# <case>[_gl].samples (the samples read over SPI) and <case>[_gl].spectrum.

set -u
cd "$(dirname "$0")"

export PYTHONDONTWRITEBYTECODE=1
IVERILOG=${IVERILOG:-iverilog}
VVP=${VVP:-vvp}
PYTHON=${PYTHON:-../../tools/venv310/bin/python}
PDK_ROOT=${PDK_ROOT:-/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu}
SCL=$PDK_ROOT/gf180mcuD/libs.ref
GL_TOP_NL=${GL_TOP_NL:-../layout/gds/eeg_digital_top.nl.v}
GL_ADC_NL=${GL_ADC_NL:-../layout/gds/eeg_adc_dig.nl.v}

GL=0
if [ "${1:-}" = "--gl" ]; then GL=1; shift; fi
[ $# -eq 0 ] && { sed -n '2,24p' "$0"; exit 1; }

B=build/e2e
mkdir -p $B

RTL="eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv
     eeg_fifo.sv eeg_regs.sv eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv
     eeg_digital_sys.sv"

gen() {   # stream name: codes and golden outputs (once)
    [ -s $B/$1.codes ] && [ -s $B/$1.gold ] && return 0
    case $1 in
        s4)  $PYTHON model/ct2_codes.py $B/s4.codes --seconds 4.26 --dc 0.0445 \
                 --tone 32:0.279 --tone 128000:0.002 --gold $B/s4.gold ;;
        s20) $PYTHON model/ct2_codes.py $B/s20.codes --seconds 20.26 --dc -0.0445 \
                 --tone 0.5:0.279 --tone 900:0.0279 --gold $B/s20.gold ;;
    esac
}

compile() {   # out.vvp tag
    local out=$1 g=$B/gl_$2
    if [ $GL -eq 0 ]; then
        # shellcheck disable=SC2086
        $IVERILOG -g2012 -Wall -I tb -o "$out" -s tb_e2e $RTL tb/tb_e2e.sv
    else
        mkdir -p "$g"
        echo "gate level: $GL_TOP_NL, $GL_ADC_NL"
        sed 's/^module eeg_digital_top (/module eeg_digital_top_gl (/' "$GL_TOP_NL" > "$g/eeg_digital_top_gl.v"
        sed 's/^module eeg_adc_dig (/module eeg_adc_dig_gl (/' "$GL_ADC_NL" > "$g/eeg_adc_dig_gl.v"
        # no -Wall: the cell models warn about implicit wires and inherited timescales
        # shellcheck disable=SC2086
        $IVERILOG -g2012 -I tb -DFUNCTIONAL -DTB=tb_e2e -o "$out" -s tb_e2e -s gl_shadow \
            $RTL tb/tb_e2e.sv tb/gl_shadow.sv \
            $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu9t5v0/verilog/gf180mcu_fd_sc_mcu9t5v0.v \
            $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/primitives.v $SCL/gf180mcu_fd_sc_mcu7t5v0/verilog/gf180mcu_fd_sc_mcu7t5v0.v \
            "$g/eeg_digital_top_gl.v" "$g/eeg_adc_dig_gl.v"
    fi
}

nfail=0
for c in "$@"; do
    case $c in
        short) s=s4;  nsamp=100 ;;
        s4)    s=s4;  nsamp=4250 ;;
        s20)   s=s20; nsamp=20250 ;;
        s4:*/*)
            k=${c#s4:}; k=${k%/*}; n=${c#*/}
            gen s4 > $B/s4.gen.log 2>&1 || { echo "FAIL  $c: stream generation"; nfail=$((nfail + 1)); continue; }
            s=s4_${k}of$n
            nsamp=$($PYTHON - "$B" "$k" "$n" <<'PY'
import sys
sys.path.insert(0, "model")
import cic_golden as g
b, k, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
codes = open(f"{b}/s4.codes", "rb").read()
size = len(codes) // n
part = codes[k * size:(k + 1) * size + 4096]
open(f"{b}/s4_{k}of{n}.codes", "wb").write(part)
outs, _ = g.cic3_run(part)
valid = [d for d, v in outs if v]
open(f"{b}/s4_{k}of{n}.gold", "w").write("".join(f"{d & 0xFFFFFF:06x}\n" for d in valid))
print(min(len(valid) - 1, (len(part) - 4096) // 1024))
PY
)
            ;;
        *) echo "unknown case $c"; exit 1 ;;
    esac
    tag=${c/:/_}; tag=${tag/\//of}
    [ $GL -eq 1 ] && tag=${tag}_gl${GL_TAG:+_$GL_TAG}
    log=$B/$tag.log
    t0=$SECONDS
    case $s in s4|s20) gen $s > $B/$s.gen.log 2>&1 || { echo "FAIL  $tag: stream generation, see $B/$s.gen.log"; nfail=$((nfail + 1)); continue; } ;; esac
    if ! compile build/e2e_$tag.vvp $tag > "$log" 2>&1; then
        echo "FAIL  $tag: compile error, see $log"; nfail=$((nfail + 1)); continue
    fi
    $VVP -n build/e2e_$tag.vvp +codes=$B/$s.codes +gold=$B/$s.gold +nsamp=$nsamp +out=$B/$tag.samples >> "$log" 2>&1
    if grep -q -E "^FAIL" "$log" || ! grep -q -E "^PASS: tb_e2e" "$log" || { [ $GL -eq 1 ] && ! grep -q -E "^PASS: gate level" "$log"; }; then
        echo "FAIL  $tag ($((SECONDS - t0)) s): $(grep -E "^(FAIL|ERROR|GL MISMATCH)" "$log" | head -n 3 | tr '\n' ' ')"
        nfail=$((nfail + 1))
        continue
    fi
    echo "PASS  $tag ($((SECONDS - t0)) s)"
    grep -E "^PASS" "$log" | sed 's/^/      /'
    case $c in
        s4)  $PYTHON model/e2e_spectrum.py $B/$tag.samples --codes $B/s4.codes --tone 32 --tone-v 0.279 --record 4000 ;;
        s20) $PYTHON model/e2e_spectrum.py $B/$tag.samples --codes $B/s20.codes --tone 0.5 --tone-v 0.279 \
                 --alias 900 --alias-v 0.0279 --record 20000 ;;
        *)   true ;;
    esac > $B/$tag.spectrum 2>&1 && sed 's/^/      /' $B/$tag.spectrum
done
[ $nfail -eq 0 ]
