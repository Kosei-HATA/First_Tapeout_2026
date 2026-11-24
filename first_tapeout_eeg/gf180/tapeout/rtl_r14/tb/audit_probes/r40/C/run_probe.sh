#!/bin/zsh
# usage: run_probe.sh <rtl_r14 dir of a copy> <out file>
D=$1; O=$2
P=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/a40c/probe
cd $D || exit 1
mkdir -p $P/build
iverilog -g2012 -I ../rtl/spec -I tb -o $P/build/$(basename $O).vvp eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv $P/tb_c40_first.sv 2>&1 | grep -v sorry
vvp -n $P/build/$(basename $O).vvp > $O 2>&1
tail -12 $O
