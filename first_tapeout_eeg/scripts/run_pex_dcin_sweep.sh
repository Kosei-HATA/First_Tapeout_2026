#!/bin/bash
# PEX DC-input oscillation sweep: 0..50 mV in 10 mV steps, sequential,
# max 2 concurrent ngspice on the host (agents may be running too).
set -u
cd "$(dirname "$0")/../source/trials/20260902/xschem"
NG=/opt/homebrew/bin/ngspice
wait_for_slot() {
  while [ "$(pgrep -c ngspice || true)" -ge 2 ]; do sleep 30; done
}
for MV in 0 10 20 30 40 50; do
  wait_for_slot
  sed -e "s|VOFF=0|VOFF=${MV}m|" -e "s|@OFF@|${MV}mv|" tb_pex_dcin.spice > tb_pex_dcin_${MV}mv.spice
  echo "start ${MV} mV  $(date +%H:%M:%S)"
  $NG -b tb_pex_dcin_${MV}mv.spice > ../results/tb_pex_dcin_${MV}mv.log 2>&1
  echo "done  ${MV} mV  $(date +%H:%M:%S)"
done
echo "ALL DONE"
