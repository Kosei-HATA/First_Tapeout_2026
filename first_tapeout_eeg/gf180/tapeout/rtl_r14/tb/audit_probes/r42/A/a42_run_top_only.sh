#!/bin/bash
# run only the tb_top_r14 group (as run_tests_r14.sh's top_t) in the given copy's rtl_r14
set -u
cd "$1/gf180/tapeout/rtl_r14" || exit 2
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
IV="iverilog -g2012 -I ../rtl/spec -I tb -I build"
RTL="eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv"
mkdir -p build
$PY tb/gen_reg_tests.py && $IV -o build/tb_top_r14.vvp ${2:-} $RTL tb/tb_top_r14.sv > build/comp.log 2>&1 && \
  vvp -n build/tb_top_r14.vvp > build/top.log 2>&1; rc=$?
$PY tb/check_top_r14.py >> build/top.log 2>&1; rc2=$?
$PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover >> build/top.log 2>&1; rc3=$?
echo "rc vvp=$rc check_top=$rc2 seq=$rc3" >> build/top.log
