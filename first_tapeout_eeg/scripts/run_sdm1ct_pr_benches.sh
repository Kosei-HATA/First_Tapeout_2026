#!/bin/bash
# Run pseudo-R SDM benches sequentially (memory safety): DC offset sweep + PVT.
set -u
cd "$(dirname "$0")/../source/trials/20260902/xschem"
NG=/opt/homebrew/bin/ngspice

# --- DC offset sweep (PR version): DC differential input, no AC ---
# name: VINP expr : VINN expr
while IFS=: read NAME VP VN; do
  sed -e "s|^VINP VINP 0 SIN.*|VINP VINP 0 {$VP}|" \
      -e "s|^VINN VINN 0 SIN.*|VINN VINN 0 {$VN}|" \
      -e "s|results/sdm1ct_pr\.csv|results/sdm1ct_pr_dc_$NAME.csv|" \
      tb_sdm1ct_pr.spice > tb_sdm1ct_pr_dc_$NAME.spice
  $NG -b tb_sdm1ct_pr_dc_$NAME.spice > ../results/sdm1ct_pr_dc_$NAME.log 2>&1
  echo "dc $NAME done"
done <<'EOF'
m15:VCM-7.5m:VCM+7.5m
m5:VCM-2.5m:VCM+2.5m
z:VCM:VCM
p5:VCM+2.5m:VCM-2.5m
p15:VCM+7.5m:VCM-7.5m
EOF

# --- PVT corners (PR version, AC 32 Hz input) ---
# corner:VDD:temp
while IFS=: read CORNER V T; do
  sed -e "s|sky130.lib.spice tt|sky130.lib.spice $CORNER|" \
      -e "s|.param VDD=1.80|.param VDD=$V|" \
      -e "s|results/sdm1ct_pr\.csv|results/sdm1ct_pr_$CORNER.csv|" \
      -e "s|^\.end$|.temp $T\\n.end|" \
      tb_sdm1ct_pr.spice > tb_sdm1ct_pr_$CORNER.spice
  $NG -b tb_sdm1ct_pr_$CORNER.spice > ../results/sdm1ct_pr_$CORNER.log 2>&1
  echo "pvt $CORNER done"
done <<'EOF'
ss:1.62:125
ff:1.98:-40
sf:1.80:27
fs:1.80:27
EOF
echo "ALL DONE"
