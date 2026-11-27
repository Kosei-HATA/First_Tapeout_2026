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
# work copy with shell.nix), EEG_DIG_REV (the chip: r14 by default, the 14th chip with the r14
# macro, results in build/r14/; r13, the 13th chip, results in build/: rev.py), CHIP_STA_BUILD
# (another results folder, e.g. build/r13 for the 13th chip's own wiring), TOP_RUN / ADC_RUN
# (macro runs; r13: f2 / f3, r14: the r14 macro run R14_RUN below / f3_rerun_20261119, the re-run
# identical to f3, gf180/tapeout/digital/README_rerun_20261119.md).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../../.." && pwd)
PY=${PYTHON:-$REPO/gf180/tools/venv310/bin/python}
NIXDIR=${NIXDIR:-/Users/noah/Codings/ws_gf180/eeg_padring}
IO=$NIXDIR/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_io/lib
REV=${EEG_DIG_REV:-r14}
R14_RUN=r14f5_20261124           # the r14 macro on the 14th chip (gf180/tapeout/layout/gds/r14/README.md)
R15_RUN=r15m1_20261127           # the r15 macro on the 15th chip (gf180/tapeout/layout/gds/r15/README.md)
if [ "$REV" = r13 ]; then
    TOP_RUN=${TOP_RUN:-f2}; ADC_RUN=${ADC_RUN:-f3}; TOP_DIR=eeg_digital_top; BUILD=${CHIP_STA_BUILD:-$HERE/build}
elif [ "$REV" = r15 ]; then
    TOP_RUN=${TOP_RUN:-$R15_RUN}; ADC_RUN=${ADC_RUN:-f3_rerun_20261119}; TOP_DIR=eeg_digital_top_r15
    BUILD=${CHIP_STA_BUILD:-$HERE/build/$REV}
else
    TOP_RUN=${TOP_RUN:-$R14_RUN}; ADC_RUN=${ADC_RUN:-f3_rerun_20261119}; TOP_DIR=eeg_digital_top_r14
    BUILD=${CHIP_STA_BUILD:-$HERE/build/$REV}
fi
export CHIP_STA_BUILD=$BUILD   # chip_nets.py (rev.py) writes there too
TOP=$HERE/../$TOP_DIR/runs/$TOP_RUN/final/lib
ADC=$HERE/../eeg_adc_dig/runs/$ADC_RUN/final/lib
RES=$BUILD/${TOP_RUN}_$ADC_RUN
export EEG_DIG_REV=$REV

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
        cmds+="ADC_LIB=$RES/etm/eeg_adc_dig__$c.lib Q_LIB=$BUILD/eeg_quantizer_tm_$q.lib "
        cmds+="SPEF=$BUILD/chip_dig_$rc.spef OUT=$RES/$c HERE=$HERE BUILD=$BUILD "
        cmds+="sta -no_splash $HERE/chip_sta.tcl > $RES/$c/sta.log 2>&1; "
    done
done
(cd "$NIXDIR" && nix-shell --run "$cmds")

"$PY" "$HERE/chip_sta_report.py" "$RES"
