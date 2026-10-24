#!/usr/bin/env bash
# Chip-level STA of the digital interface (tracker C3): the two LibreLane macros as
# their timing models, the MCLK pad, a timing model of the quantizer and the chip
# wiring extracted from the core's LVS database.
#
#   1. chip_nets.py (KLayout): parasitics of the interface nets -> build/
#   2. OpenSTA (the LibreLane nix shell) for the nine corners of the macros, the chip
#      wiring with the matching coupling (min / nom / max) -> build/<top run>_<adc run>/<corner>/.
#      The macros' timing models (LibreLane write_timing_model) copy the output
#      buffers' transition tables from the cell libraries, which are characterized with
#      slew_derate_from_library 0.5, but declare 1.0; OpenSTA then reads the output
#      slews twice too large (SPICE of buf_1 on CMP_STROBE: 3.77 ns 30-70 %, table 7.36).
#      Copies with the derate set to 0.5 are used here (build/etm/).
#   3. chip_sta_report.py: tables of the results -> build/<top run>_<adc run>/report.md
#
# usage: ./run_chip_sta.sh
# Environment: PYTHON (default gf180/tools/venv310/bin/python), NIXDIR (the LibreLane
# work copy with shell.nix), TOP_RUN / ADC_RUN (macro runs, default f2 / f3).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
PY=${PYTHON:-$REPO/gf180/tools/venv310/bin/python}
NIXDIR=${NIXDIR:-/Users/noah/Codings/ws_gf180/eeg_padring}
IO=$NIXDIR/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_io/lib
TOP_RUN=${TOP_RUN:-f2}
ADC_RUN=${ADC_RUN:-f3}
TOP=$HERE/../eeg_digital_top/runs/$TOP_RUN/final/lib
ADC=$HERE/../eeg_adc_dig/runs/$ADC_RUN/final/lib
RES=$HERE/build/${TOP_RUN}_$ADC_RUN

"$PY" "$HERE/chip_nets.py"

mkdir -p "$RES/etm"
for rc in nom min max; do
    for pv in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
        c=${rc}_$pv
        sed 's/slew_derate_from_library *: *1.0;/slew_derate_from_library : 0.5;/' "$TOP/$c/eeg_digital_top__$c.lib" > "$RES/etm/eeg_digital_top__$c.lib"
        sed 's/slew_derate_from_library *: *1.0;/slew_derate_from_library : 0.5;/' "$ADC/$c/eeg_adc_dig__$c.lib" > "$RES/etm/eeg_adc_dig__$c.lib"
    done
done

cmds=""
for rc in nom min max; do
    for pv in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
        c=${rc}_$pv
        case $pv in
            tt*) pad=tt_025C_3v30; q=tt ;;
            ss*) pad=ss_125C_2v97; q=ss ;;
            ff*) pad=ff_n40C_3v63; q=ff ;;
        esac
        mkdir -p "$RES/$c"
        rm -f "$RES/$c"/*.rpt
        cmds+="PAD_LIB=$IO/gf180mcu_fd_io__$pad.lib TOP_LIB=$RES/etm/eeg_digital_top__$c.lib "
        cmds+="ADC_LIB=$RES/etm/eeg_adc_dig__$c.lib Q_LIB=$HERE/build/eeg_quantizer_tm_$q.lib "
        cmds+="SPEF=$HERE/build/chip_dig_$rc.spef OUT=$RES/$c HERE=$HERE "
        cmds+="sta -no_splash $HERE/chip_sta.tcl > $RES/$c/sta.log 2>&1; "
    done
done
(cd "$NIXDIR" && nix-shell --run "$cmds")

"$PY" "$HERE/chip_sta_report.py" "$RES"
