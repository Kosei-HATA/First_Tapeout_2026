#!/bin/zsh
# OpenSTA of a r14 macro run outside LibreLane, all 9 corners (3.3 V: tt 25 C / ss 125 C 3.0 V / ff -40 C 3.6 V x the
# min / nom / max parasitics), with the flip-flops' preset / clear arcs on and off (sta_r14.tcl; VER-05).
# usage: run_sta_r14.sh <run tag> [sdc]       out: runs/<tag>/sta_r14/{arcs_on,arcs_off}/<corner>/, summary.txt
set -u
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r14
TAG=$1
SDC=${2:-$D/eeg_digital_top_r14.sdc}
R=$D/runs/$TAG/final
NIXDIR=/Users/noah/Codings/ws_gf180/eeg_padring
LIBD=$NIXDIR/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/lib
OUT=$D/runs/$TAG/sta_r14
[ -e /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh ] && . /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cmds=""
for arcs in 1 0; do
    for rc in nom min max; do
        for pv in tt_025C_3v30 ss_125C_3v00 ff_n40C_3v60; do
            c=${rc}_$pv
            o=$OUT/arcs_$([ $arcs = 1 ] && echo on || echo off)/$c
            rm -rf $o; mkdir -p $o
            cmds+="LIB=$LIBD/gf180mcu_fd_sc_mcu9t5v0__$pv.lib NL=$R/nl/eeg_digital_top.nl.v SPEF=$R/spef/$rc/eeg_digital_top.$rc.spef "
            cmds+="SDC=$SDC OUT=$o CORNER=$c PRESET=$arcs sta -no_splash -exit $D/sta_r14.tcl > $o/sta.log 2>&1 & "
        done
    done
    cmds+="wait; "
done
(cd $NIXDIR && nix-shell --run "$cmds")
cat $OUT/arcs_on/*/summary.txt $OUT/arcs_off/*/summary.txt | tee $OUT/summary.txt
