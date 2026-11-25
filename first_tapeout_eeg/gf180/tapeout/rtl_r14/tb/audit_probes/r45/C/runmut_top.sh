#!/bin/zsh
# Audit 45, auditor C: make the mutant copy <tag> and run only run_tests_r14.sh's codes and tb_top_r14 groups (the
# 8-deep FIFO), as that script runs them. usage: runmut_top.sh <tag>   (output: a45C_mut/<tag>.top.out)
T=$1
S=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
O=$S/a45C_mut/$T.top.out
$PY $S/a45C_tools/mkmut.py $T > $O 2>&1 || exit 1
cd $S/a45C_mut/$T/gf180/tapeout/rtl_r14 || exit 1
mkdir -p build
date >> $O
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
$PY tb/gen_codes.py >> $O 2>&1 && $PY tb/gen_reg_tests.py >> $O 2>&1 &&
iverilog -g2012 -I ../rtl/spec -I tb -I build -o build/tb_top_r14.vvp $RTL tb/tb_top_r14.sv > build/tb_top_r14.vvp.log 2>&1 &&
vvp -n build/tb_top_r14.vvp > build/tb_top_r14.out 2>&1; grep -c "warning: Port .* expects" build/tb_top_r14.vvp.log >> $O
echo "vvp rc=$?" >> $O
grep -E "ERROR|^tb_top_r14:|PASS|FAIL" build/tb_top_r14.out >> $O
$PY tb/check_top_r14.py >> $O 2>&1; echo "check_top rc=$?" >> $O
$PY tb/check_seq_trace.py build/top_seq_trace.txt --no-cover | grep -E "mismatches|PASS|FAIL" >> $O 2>&1; echo "check_seq rc=$?" >> $O
date >> $O
