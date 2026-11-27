#!/bin/zsh
# VER-04 (11/28): the r15 block with a whole code stream of the CT loop model, read like the host, every sample bit-exact
# with the golden CIC (tb/tb_e2e_r15.sv, tb/check_e2e_r15.py). The streams are rtl/run_e2e.sh's (rtl/build/e2e/s4.codes,
# s20.codes: rtl/model/ct2_codes.py; s4 4.26 s, 4,362,... frames; s20 20.26 s).
# usage: run_e2e_r15.sh <case> <nsamp> [start] [tag]
#   case   s4 | s20 (or a path to a .codes file)
#   nsamp  samples to read (s4: 4,240 fit the stream from the reset; s20: 20,240)
#   start  the stream position at the RESET_N release (a chunk), default 0
# out: build/e2e_r15/<tag>.{log,run.out,check.out} (tag default <case>_<start>)
set -u
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python}
CASE=${1:?usage: run_e2e_r15.sh <case> <nsamp> [start] [tag]}
NS=${2:?nsamp}
ST=${3:-0}
CODES=$CASE
[[ -f $CODES ]] || CODES=../rtl/build/e2e/$CASE.codes
[[ -f $CODES ]] || { echo "no stream $CODES"; exit 1; }
TAG=${4:-$(basename $CASE .codes)_$ST}
B=build/e2e_r15
mkdir -p $B
RTL=(eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv
     ../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv)
{
    date "+start %Y-%m-%d %H:%M:%S"
    echo "commit $(git rev-parse --short HEAD) (sources below by sha256)"
    shasum -a 256 $RTL tb/tb_e2e_r15.sv tb/spi_bfm_r14.svh tb/check_e2e_r15.py spec/eeg_regs_defs.svh $CODES
} > $B/$TAG.run.out
iverilog -g2012 -I spec -I tb -I build -o $B/$TAG.vvp $RTL tb/tb_e2e_r15.sv > $B/$TAG.comp.log 2>&1 || {
    cat $B/$TAG.comp.log; echo "FAIL: compile"; exit 1; }
t0=$(date +%s)
vvp -n $B/$TAG.vvp +codes=$CODES +nsamp=$NS +start=$ST +log=$B/$TAG.log >> $B/$TAG.run.out 2>&1
rc=$?
echo "vvp rc $rc, $(( $(date +%s) - t0 )) s" >> $B/$TAG.run.out
tail -4 $B/$TAG.run.out
$PY tb/check_e2e_r15.py $CODES $B/$TAG.log > $B/$TAG.check.out 2>&1
crc=$?
cat $B/$TAG.check.out
if [[ $rc -eq 0 && $crc -eq 0 ]] && grep -q '^PASS: tb_e2e_r15' $B/$TAG.run.out && ! grep -q '^FAIL' $B/$TAG.run.out; then
    echo "E2E_R15 PASS $TAG"
else
    echo "E2E_R15 FAIL $TAG"
fi
