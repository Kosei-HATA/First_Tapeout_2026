#!/bin/zsh
# The r15 macro into the chip (tracker C4, E7): the final views of a LibreLane run of this directory to
# gf180/tapeout/layout/gds/r15/ (chip_lay.py takes them with EEG_DIG_REV=r15: layout/digrev.py) and the
# gate-level CDL for the chip's LVS (../pnl2cdl.py, the 9-track library's SPICE of the PDK LibreLane used).
# usage: install_r15_macro.sh <run tag>        writes gds/r15/{eeg_digital_top.gds,.lef,.nl.v,.pnl.v,.cdl,SHA256SUMS}
set -eu
D=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/eeg_digital_top_r15
G=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/layout/gds/r15
SPICE=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu9t5v0/spice/gf180mcu_fd_sc_mcu9t5v0.spice
F=$D/runs/$1/final
mkdir -p $G
cp $F/gds/eeg_digital_top.gds $F/lef/eeg_digital_top.lef $F/nl/eeg_digital_top.nl.v $F/pnl/eeg_digital_top.pnl.v $G/
python3 $D/../pnl2cdl.py $G/eeg_digital_top.pnl.v $SPICE $G/eeg_digital_top.cdl
(cd $G && shasum -a 256 eeg_digital_top.gds eeg_digital_top.lef eeg_digital_top.nl.v eeg_digital_top.pnl.v eeg_digital_top.cdl > SHA256SUMS)
echo "run $1" >> $G/SHA256SUMS
cat $G/SHA256SUMS
