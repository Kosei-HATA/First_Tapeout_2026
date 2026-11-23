#!/bin/bash
# audit38 C: tb_top_r14 (8-deep) with the round-37 coverage monitor as a second top module, in the cov copy
set -u
cd "$(dirname "$0")"
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
T=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit38_C/tools
mkdir -p build
$PY tb/gen_codes.py && $PY tb/gen_reg_tests.py || exit 1
RTL="eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv"
iverilog -g2012 -I ../rtl/spec -I tb -I build -o build/tb_cov.vvp $RTL tb/tb_top_r14.sv $T/mon_cov.sv $T/mon_c38.sv > build/tb_cov.vvp.log 2>&1 || { cat build/tb_cov.vvp.log; exit 1; }
vvp -n build/tb_cov.vvp > build/tb_cov.log 2>&1
tail -3 build/tb_cov.log
$PY $T/cov_summary.py build/cov_apply.txt > build/cov_summary.txt
echo COV DONE
