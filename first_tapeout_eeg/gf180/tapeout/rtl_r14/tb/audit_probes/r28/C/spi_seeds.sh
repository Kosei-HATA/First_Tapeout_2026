#!/bin/zsh
# spi_seeds.sh <rtl_r14 dir> <seed>...: tb_spi_r14 (+n=1500) and its checker per seed; for each, the committed writes of
# 0xA5 to a writable address other than COMMAND (the frames at which a data-only SOFT_RESET decode would show)
D=$1; shift
P=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
cd $D || exit 1
RTL="eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv"
iverilog -g2012 -I ../rtl/spec -I tb -I build -o build/seeds_spi.vvp ${=RTL} tb/tb_spi_r14.sv || exit 1
for s in "$@"; do
  nice -n 5 vvp -n build/seeds_spi.vvp +n=1500 +seed=$s +log=build/seeds_spi_$s.txt > build/seeds_spi_$s.log 2>&1
  k=$($P tb/check_spi_trace.py build/seeds_spi_$s.txt | head -1)
  a5=$(grep " we=1 " build/seeds_spi_$s.txt | grep "wd=a5" | grep -v "wa=10 " | grep -c "wok=1\|aerr=0")
  print -r -- "seed $s: $k; committed 0xA5 writes outside COMMAND: $(grep ' we=1 ' build/seeds_spi_$s.txt | grep 'wd=a5' | grep -v 'wa=10 ' | awk '{print $2, $10}' | tr '\n' ' ')"
done
