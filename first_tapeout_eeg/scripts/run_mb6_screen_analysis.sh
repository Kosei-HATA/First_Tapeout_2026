#!/usr/bin/env bash
# mb6 35ms スクリーン完走後の A/B 解析（mb5 ベースライン 110.68 dB と同一条件）
# 使い方: bash scripts/run_mb6_screen_analysis.sh
set -e
cd "$(dirname "$0")/.."
CSV=gf180/results/sdm3_mb6_512k_short.csv
OUT=gf180/results/screen_mb6_512k_sndr.txt
test -f "$CSV" || { echo "not found: $CSV (screen still running?)"; exit 1; }
python3 scripts/sdm_mb_bitstream_stream.py "$CSV" \
  --ncols 63 --fs 512000 --fsig 32 --skip-ms 2 | tee "$OUT"
echo "---"
echo "mb5 baseline (same window/analysis): SNDR = 110.68 dB, signal = 0.6261"
echo "判定（行為モデル較正済み）: >=118 dB → 窓改善の強い証拠・6bitフルチェーン投入;"
echo "  110-118 dB → 暧昧・chain2確定値待ち; <=110 dB → 6bit窓改善無しとして棄却"
