#!/bin/zsh
# Timing models (write_timing_model, as LibreLane's signoff STA writes final/lib) of a r14 macro run for the 9 corners,
# with the flip-flops' preset / clear arcs on and off (sta_r14.tcl with ETM; VER-05, VER-08).
#   arcs on:  as final/lib: the SOFT_RESET paths through the clear / preset arcs merge into the outputs' arcs (the fall
#             of CHOP_BLANK, the rise of CHOP_EN, AFE_RST and DWA_EN are then those paths; 11/24: CHOP_BLANK's fall
#             18.9 ns at max ss against 9.9 ns for its clocked rise)
#   arcs off: the clocked arcs alone, for the chip-level checks of clocked edges (the blanking margins:
#             chip_sta/run_chip_sta.sh with TOP_RUN=<tag>_etmoff, the folder this script fills with links)
# usage: run_etm_r14.sh <run tag>     out: runs/<tag>/etm_r14/{arcs_on,arcs_off}/<corner>/ (the lib, sta.log, reports),
#        runs/<tag>_etmoff/final/lib/<corner>/eeg_digital_top__<corner>.lib (links to the arcs-off models)
set -u
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
TAG=$1
SDC=$D/eeg_digital_top_r14.sdc
R=$D/runs/$TAG/final
NIXDIR=/Users/noah/Codings/ws_gf180/eeg_padring
LIBD=$NIXDIR/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib
OUT=$D/runs/$TAG/etm_r14
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cmds=""
for arcs in 1 0; do
    for rc in nom min max; do
        for pv in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
            c=${rc}_$pv
            o=$OUT/arcs_$([ $arcs = 1 ] && echo on || echo off)/$c
            rm -rf $o; mkdir -p $o
            cmds+="LIB=$LIBD/gf180mcu_fd_sc_mcu9t5v0__$pv.lib NL=$R/nl/eeg_digital_top.nl.v SPEF=$R/spef/$rc/eeg_digital_top.$rc.spef "
            cmds+="SDC=$SDC OUT=$o CORNER=$c PRESET=$arcs ETM=$o/eeg_digital_top__$c.lib "
            cmds+="sta -no_splash -exit $D/sta_r14.tcl > $o/sta.log 2>&1; "
        done
    done
done
(cd $NIXDIR && nix-shell --run "$cmds")
L=$D/runs/${TAG}_etmoff/final/lib
for c in $OUT/arcs_off/*(/); do
    mkdir -p $L/${c:t}
    ln -sf $c/eeg_digital_top__${c:t}.lib $L/${c:t}/eeg_digital_top__${c:t}.lib
done
ls $OUT/arcs_on/*/*.lib $OUT/arcs_off/*/*.lib | wc -l
