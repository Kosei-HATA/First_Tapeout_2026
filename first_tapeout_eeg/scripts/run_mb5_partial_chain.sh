#!/usr/bin/env bash
# chain2 部分チェーン解析: 完走済み seg1..K を時刻オフセット付きで連結し
# ストリーム SNDR 解析を実行する（早期指標用。最終は run_mb5_full_chain2.sh が自動実行）
# 使い方: bash scripts/run_mb5_partial_chain.sh <K>   例: 3 -> seg1..3 (0-161.25 ms, 5cyc)
set -e
cd "$(dirname "$0")/.."
K=${1:?usage: run_mb5_partial_chain.sh <K>}
OUT=/tmp/mb5_partial_chain_k${K}.csv.gz
python3 - "$K" "$OUT" <<'EOF'
import gzip, sys
K = int(sys.argv[1]); outpath = sys.argv[2]
B0 = 0.000661e-3; seg = 53.75e-3
tend = 0.0; nlines = 0
with gzip.open(outpath, "wt") as out:
    for k in range(1, K + 1):
        Bk = B0 + (k - 1) * seg
        src = f"gf180/results/sdm3_mb5_512k_full_seg{k}.csv.gz"
        with gzip.open(src, "rt") as f:
            for line in f:
                p = line.split()
                t = float(p[0]) + Bk
                if t <= tend: continue
                p[0] = f"{t:.9e}"
                out.write(" ".join(p) + "\n")
                tend = t; nlines += 1
print(f"concat seg1..{K}: {nlines} lines, t_end={tend*1e3:.6f} ms -> {outpath}")
EOF
python3 scripts/sdm_mb_bitstream_stream.py "$OUT" \
  --ncols 31 --fs 512000 --fsig 32 --skip-ms 2
