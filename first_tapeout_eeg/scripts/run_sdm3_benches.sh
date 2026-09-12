#!/bin/bash
# Run sdm3 PVT + DC benches, max 2 ngspice on the host (waits for a slot).
set -u
cd "$(dirname "$0")/../source/trials/20260902/xschem"
NG=/opt/homebrew/bin/ngspice

wait_slot() {
  while [ "$(pgrep -x ngspice | wc -l)" -ge 2 ]; do sleep 60; done
}

for C in ss ff; do
  wait_slot
  $NG -b tb_sdm3_256k_${C}.spice > ../results/sdm3_256k_${C}.log 2>&1
  echo "pvt $C done"
done
for NM in m15 z p15; do
  wait_slot
  $NG -b tb_sdm3_dc_${NM}.spice > ../results/sdm3_dc_${NM}.log 2>&1
  echo "dc $NM done"
done
echo "ALL DONE"
