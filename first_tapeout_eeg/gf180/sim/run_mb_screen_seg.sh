#!/usr/bin/env bash
# Segmented mb screen run: seg1 0 -> 60.000661 ms, seg2 -> 103.75 ms global.
# Dodges the ngspice artifact at 62.502 ms / PH1 edge of cycle 32001.
set -e
cd "$(dirname "$0")"
B1=60.000661
L1=60.000661
L2=$(python3 -c "print(103.75-$B1)")
python3 mb_seg.py make tb_gf180_sdm3_mb_512k_short.spice 1 0 $L1 sdm3_mb_512k_short none /tmp/tb_mb_seg1.spice
ngspice -b /tmp/tb_mb_seg1.spice > /tmp/mb_seg1.log 2>&1
python3 mb_seg.py snap /tmp/mb_seg1.log /tmp/nodesets_seg2.ic
python3 mb_seg.py make tb_gf180_sdm3_mb_512k_short.spice 2 $B1 $L2 sdm3_mb_512k_short /tmp/nodesets_seg2.ic /tmp/tb_mb_seg2.spice
ngspice -b /tmp/tb_mb_seg2.spice > /tmp/mb_seg2.log 2>&1
python3 - <<'EOF'
import pandas as pd, numpy as np
B1 = 60.000661e-3
a = pd.read_csv("../results/sdm3_mb_512k_short_seg1.csv", sep=r"\s+", header=None).to_numpy()
b = pd.read_csv("../results/sdm3_mb_512k_short_seg2.csv", sep=r"\s+", header=None).to_numpy()
b[:, ::2] += B1   # shift all scale (time) columns
b = b[b[:, 0] > a[-1, 0]]   # keep times strictly increasing
out = np.vstack([a, b])
np.savetxt("../results/sdm3_mb_512k_short.csv", out, fmt="%.9e")
print("concatenated:", out.shape, "t_end:", out[-1,0])
EOF
echo SEGMENTED SCREEN DONE
