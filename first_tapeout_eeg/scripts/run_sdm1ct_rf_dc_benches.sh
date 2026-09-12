#!/bin/bash
# DC offset sweep for the RF=100Meg version (comparison baseline for the PR variant).
set -u
cd "$(dirname "$0")/../source/trials/20260902/xschem"
NG=/opt/homebrew/bin/ngspice
while IFS=: read NAME VP VN; do
  sed -e "s|^VINP VINP 0 SIN.*|VINP VINP 0 {$VP}|" \
      -e "s|^VINN VINN 0 SIN.*|VINN VINN 0 {$VN}|" \
      -e "s|results/sdm1ct_rf_base\.csv|results/sdm1ct_rf_dc_$NAME.csv|" \
      tb_sdm1ct_rf_base.spice > tb_sdm1ct_rf_dc_$NAME.spice
  $NG -b tb_sdm1ct_rf_dc_$NAME.spice > ../results/sdm1ct_rf_dc_$NAME.log 2>&1
  echo "dc $NAME done"
done <<'EOF'
m15:VCM-7.5m:VCM+7.5m
m5:VCM-2.5m:VCM+2.5m
z:VCM:VCM
p5:VCM+2.5m:VCM-2.5m
p15:VCM+7.5m:VCM-7.5m
EOF
echo "ALL DONE"
