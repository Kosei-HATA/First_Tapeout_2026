#!/bin/zsh
# The transistor-level checks of the long digital-to-analog nets for one chip (requirement VER-08; rev.py: EEG_DIG_REV,
# r14 by default, CHIP_LVSDB): the bus couplings (xtalk.py, KLayout, from the core LVS database), then the edges and the
# receivers (drive_check.py: the AFE clock driver and OTA1's chopper driver), the quantizer's TH with the strobe as on
# the chip (strobe_check.py), DAC1's common break (dac1_brk_check.py) and the crosstalk at the receivers
# (xtalk_check.py). chip_nets.py must have run (run_chip_sta.sh). Each one's output goes to <build>/<name>.log.
# usage: run_checks.sh          (from a Terminal panel tab: about an hour under load)
set -u
HERE=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/digital/chip_sta
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
REV=${EEG_DIG_REV:-r14}
export EEG_DIG_REV=$REV
B=$($PY -c "import sys; sys.path.insert(0, '$HERE'); import rev; print(rev.BUILD)")
echo "chip $REV, results in $B"
cd $HERE || exit 1
for s in xtalk drive_check strobe_check dac1_brk_check xtalk_check; do
    date
    t0=$SECONDS
    $PY -u $s.py > $B/$s.log 2>&1
    echo "$s: exit $? ($((SECONDS - t0)) s)"
done
date
