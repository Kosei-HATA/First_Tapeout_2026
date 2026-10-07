#!/usr/bin/env bash
# Recovery chain after seg5 death at local 15.63 ms (bnopp2#branch).
# seg5 (global 215.000661..268.750661) and seg6 (268.750661..322.500661)
# both split into 4 x 13.4375 ms chunks (seg51..54, seg61..64),
# merged with local-time offsets, then concat + SNDR analysis.
set -e
cd "$(dirname "$0")"
TPL=tb_gf180_sdm3_mb_512k_full.spice
BASE=sdm3_mb_512k_full
NG=/opt/homebrew/bin/ngspice
NS=/tmp/nodesets_full_seg45.ic

run_seg () {  # k B L
  k=$1; B=$2; L=$3
  echo "[$(date '+%m-%d %H:%M')] seg$k start: global $B .. $(python3 -c "print($B+$L)") ms (L=$L ms)"
  python3 mb_seg.py make $TPL $k $B $L $BASE $NS /tmp/tb_mb_full_seg$k.spice
  $NG -b /tmp/tb_mb_full_seg$k.spice > /tmp/mb_full_seg$k.log 2>&1
  n=$(grep -c "Timestep too small" /tmp/mb_full_seg$k.log || true)
  echo "[$(date '+%m-%d %H:%M')] seg$k done (tts=$n)"
  if [ "$n" != "0" ]; then echo "seg$k DIED: $(grep -o 'trouble with node \"[^\"]*\"' /tmp/mb_full_seg$k.log | tail -1)"; exit 1; fi
  nxt=$(python3 -c "print($k+1)")
  python3 mb_seg.py snap /tmp/mb_full_seg$k.log /tmp/nodesets_full_seg$nxt.ic
  NS=/tmp/nodesets_full_seg$nxt.ic
}

merge_chunks () {  # out_k c0 c1
  python3 - "$1" "$2" "$3" <<'EOF'
import sys
out_k, c0, c1 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
out = open(f"../results/sdm3_mb_512k_full_seg{out_k}.csv", "w")
tend = 0.0
for c in range(c0, c1 + 1):
    off = (c - c0) * 13.4375e-3
    for line in open(f"../results/sdm3_mb_512k_full_seg{c}.csv"):
        p = line.split()
        t = float(p[0]) + off
        if t <= tend: continue
        p[0] = f"{t:.9e}"
        out.write(" ".join(p) + "\n")
        tend = t
out.close()
print(f"seg{out_k} merged, t_end=", tend)
EOF
  gzip -f "../results/sdm3_mb_512k_full_seg$1.csv"
  echo "[$(date '+%m-%d %H:%M')] seg$1 merged+gzipped"
}

# ---- seg5 as 4 chunks ----
for c in 51 52 53 54; do
  B=$(python3 -c "print(215.000661 + ($c-51)*13.4375)")
  run_seg $c $B 13.4375
done
merge_chunks 5 51 54

# ---- seg6 as 4 chunks ----
for c in 61 62 63 64; do
  B=$(python3 -c "print(268.750661 + ($c-61)*13.4375)")
  run_seg $c $B 13.4375
done
merge_chunks 6 61 64

# ---- concat all 6 segments + analysis ----
python3 - <<'EOF'
import gzip
B0=0.000661e-3; seg=53.75e-3
out=open("../results/sdm3_mb_512k_full_chain.csv","w")
tend=0.0
for k in range(1,7):
    Bk=B0+(k-1)*seg
    with gzip.open(f"../results/sdm3_mb_512k_full_seg{k}.csv.gz","rt") as f:
        for line in f:
            p=line.split()
            t=float(p[0])+Bk
            if t<=tend: continue
            p[0]=f"{t:.9e}"
            out.write(" ".join(p)+"\n")
            tend=t
out.close()
print("chain csv written, t_end=",tend)
EOF
gzip -f ../results/sdm3_mb_512k_full_chain.csv
python3 /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/scripts/sdm_mb_bitstream_stream.py \
  ../results/sdm3_mb_512k_full_chain.csv.gz --ncols 15 --fs 512000 --fsig 32 --skip-ms 2 \
  > ../results/full_chain_sndr.txt 2>&1
echo "[$(date '+%m-%d %H:%M')] FULL CHAIN DONE"
cat ../results/full_chain_sndr.txt
