#!/bin/zsh
# VER-06 (11/28): the model host procedure (requirement 5.4) in Python (tb/host_r15.py) driving two r15 chips on the
# board tb/tb_host_r15.sv through named pipes; then optionally its mutation self-test (tb/mutate_host_r15.py).
# usage: run_host_r15.sh [mut]
# out: build/host_r15/ (host_r15.log, board.log), build/host_r15_mut/ (one folder per mutant)
set -u
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python}
B=build/host_r15
mkdir -p $B
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
{
    date "+start %Y-%m-%d %H:%M:%S"
    echo "commit $(git rev-parse --short HEAD) (sources below by sha256)"
    shasum -a 256 $RTL tb/tb_host_r15.sv tb/host_r15.py spec/eeg_regs_defs.svh
} > $B/run.out
iverilog -g2012 -I spec -I tb -o $B/tb_host_r15.vvp $RTL tb/tb_host_r15.sv > $B/comp.log 2>&1 || {
    grep -v 'sorry: constant selects' $B/comp.log; echo "FAIL: compile"; exit 1; }
$PY tb/host_r15.py --vvp $B/tb_host_r15.vvp --out $B >> $B/run.out 2>&1
rc=$?
tail -3 $B/run.out
if [[ ${1:-} == mut ]]; then
    $PY tb/mutate_host_r15.py -j 3 | tee build/host_r15_mut.out
    rc2=${pipestatus[1]}
else
    rc2=0
fi
[[ $rc -eq 0 && $rc2 -eq 0 ]] && echo "HOST_R15 PASS" || echo "HOST_R15 FAIL"
