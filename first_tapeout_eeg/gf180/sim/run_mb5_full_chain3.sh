#!/usr/bin/env bash
# chain2 recovery: seg4 died (tts, bnopn19#branch) at its very start
# (global 161.250661 ms, only 1 reference line after 5.3h grind, 2026-10-08 20:28).
# Strategy: seg4 as 4x13.4375 ms chunks (41..44); chunk 42 contains the
# local-15.63 ms death point and uses method=gear to get through the
# discontinuity that stalled trap; chunks 41/43/44, seg5, seg6 default (trap).
set -e
cd "$(dirname "$0")"
TPL=tb_gf180_sdm3_mb5_512k_short.spice
BASE=sdm3_mb5_512k_full
NG=/opt/homebrew/bin/ngspice
NS=/tmp/nodesets_mb5_full_seg4.ic   # snapshot at seg3 end (seg4 start state)

run_seg () {  # k B L [gear]
  k=$1; B=$2; L=$3
  echo "[$(date '+%m-%d %H:%M')] seg$k start: global $B .. $(python3 -c "print($B+$L)") ms (L=$L ms) ${4:-}"
  python3 mb_seg5.py make $TPL $k $B $L $BASE $NS /tmp/tb_mb5_full_seg$k.spice
  if [ "$4" = "gear" ]; then
    printf '.options method=gear\n' >> /tmp/tb_mb5_full_seg$k.spice
  fi
  $NG -b /tmp/tb_mb5_full_seg$k.spice > /tmp/mb5_full_seg$k.log 2>&1
  n=$(grep -c "Timestep too small" /tmp/mb5_full_seg$k.log || true)
  echo "[$(date '+%m-%d %H:%M')] seg$k done (tts=$n)"
  if [ "$n" != "0" ]; then echo "seg$k DIED: $(grep -o 'trouble with node \"[^\"]*\"' /tmp/mb5_full_seg$k.log | tail -1)"; exit 1; fi
  nxt=$(python3 -c "print($k+1)")
  python3 mb_seg5.py snap /tmp/mb5_full_seg$k.log /tmp/nodesets_mb5_full_seg$nxt.ic
  NS=/tmp/nodesets_mb5_full_seg$nxt.ic
}

merge_chunks () {  # out_k c0 c1
  python3 - "$1" "$2" "$3" <<'EOF'
import sys
out_k, c0, c1 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
out = open(f"../results/sdm3_mb5_512k_full_seg{out_k}.csv", "w")
tend = 0.0
for c in range(c0, c1 + 1):
    off = (c - c0) * 13.4375e-3
    for line in open(f"../results/sdm3_mb5_512k_full_seg{c}.csv"):
        p = line.split()
        t = float(p[0]) + off
        if t <= tend: continue
        p[0] = f"{t:.9e}"
        out.write(" ".join(p) + "\n")
        tend = t
out.close()
print(f"seg{out_k} merged, t_end=", tend)
EOF
  gzip -f "../results/sdm3_mb5_512k_full_seg$1.csv"
  echo "[$(date '+%m-%d %H:%M')] seg$1 merged+gzipped"
}

# ---- seg4 as 4 chunks (global 161.250661..215.000661); chunk 42 contains the ----
# ---- local-15.63 ms tts death point -> gear for chunk 42 only ----
for c in 41 42 43 44; do
  B=$(python3 -c "print(161.250661 + ($c-41)*13.4375)")
  if [ "$c" = "42" ]; then run_seg $c $B 13.4375 gear; else run_seg $c $B 13.4375; fi
done
merge_chunks 4 41 44

# ---- seg5, seg6 full length ----
run_seg 5 215.000661 53.75
gzip -f ../results/${BASE}_seg5.csv
run_seg 6 268.750661 53.749339
gzip -f ../results/${BASE}_seg6.csv

# ---- concat all 6 segments + analysis (mb5: ncols 31) ----
python3 - <<'EOF'
import gzip
B0=0.000661e-3; seg=53.75e-3
out=open("../results/sdm3_mb5_512k_full_chain.csv","w")
tend=0.0
for k in range(1,7):
    Bk=B0+(k-1)*seg
    with gzip.open(f"../results/sdm3_mb5_512k_full_seg{k}.csv.gz","rt") as f:
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
gzip -f ../results/sdm3_mb5_512k_full_chain.csv
python3 /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/scripts/sdm_mb_bitstream_stream.py \
  ../results/sdm3_mb5_512k_full_chain.csv.gz --ncols 31 --fs 512000 --fsig 32 --skip-ms 2 \
  > ../results/mb5_full_chain_sndr.txt 2>&1
echo "[$(date '+%m-%d %H:%M')] FULL CHAIN DONE"
cat ../results/mb5_full_chain_sndr.txt
