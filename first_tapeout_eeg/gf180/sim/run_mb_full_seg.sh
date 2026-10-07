#!/usr/bin/env bash
# Segmented FULL run (322.5 ms) for sdm3_mb: 5x60 ms + 22.5 ms segments,
# each < 62.5 ms process-time (dodges the ngspice 62.502 ms artifact).
# Usage: run_mb_full_seg.sh <template> <csvbase>
set -e
cd "$(dirname "$0")"
TPL=${1:-tb_gf180_sdm3_mb_512k_full.spice}
BASE=${2:-sdm3_mb_512k_full}
B=0.000661   # 0.661us offset already inside template TDs; boundaries at 60.000661k ms
BMS=60.000661
PREV=0
NSF=none
for k in 1 2 3 4 5 6; do
  if [ $k -lt 6 ]; then LK=$BMS; else LK=$(python3 -c "print(322.5-5*$BMS)"); fi
  python3 mb_seg.py make $TPL $k $PREV $LK $BASE $NSF /tmp/tb_mb_full_seg$k.spice
  ngspice -b /tmp/tb_mb_full_seg$k.spice > /tmp/mb_full_seg$k.log 2>&1
  python3 mb_seg.py snap /tmp/mb_full_seg$k.log /tmp/nodesets_full_seg$((k+1)).ic
  PREV=$(python3 -c "print($PREV+$LK)")
  NSF=/tmp/nodesets_full_seg$((k+1)).ic
  echo "seg$k done ($(date))"
done
python3 - <<EOF
import pandas as pd, numpy as np
BMS = $BMS * 1e-3
parts = []
for k in range(1, 7):
    d = pd.read_csv(f"../results/${BASE}_seg{k}.csv", sep=r"\s+", header=None).to_numpy()
    d[:, ::2] += (k - 1) * BMS
    if parts:
        d = d[d[:, 0] > parts[-1][-1, 0]]
    parts.append(d)
out = np.vstack(parts)
np.savetxt("../results/${BASE}.csv", out, fmt="%.9e")
print("concatenated:", out.shape, "t_end:", out[-1, 0])
EOF
echo SEGMENTED FULL DONE
