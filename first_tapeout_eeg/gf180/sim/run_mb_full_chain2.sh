#!/usr/bin/env bash
# Recovery chain after seg4 death at local 15.63 ms (bnonp9#branch).
# seg4 (global 161.250661..215.000661) split into 4 x 13.4375 ms chunks
# (CSV names seg41..44, merged into seg4.csv with local-time offsets),
# then seg5, seg6 as before, then concat + SNDR analysis.
set -e
cd "$(dirname "$0")"
TPL=tb_gf180_sdm3_mb_512k_full.spice
BASE=sdm3_mb_512k_full
NG=/opt/homebrew/bin/ngspice
NS=/tmp/nodesets_full_seg4.ic

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

# ---- seg4 as 4 chunks ----
for c in 41 42 43 44; do
  B=$(python3 -c "print(161.250661 + ($c-41)*13.4375)")
  run_seg $c $B 13.4375
done
# merge chunk CSVs -> seg4.csv (local time 0..53.75)
python3 - <<'EOF'
out = open("../results/sdm3_mb_512k_full_seg4.csv", "w")
tend = 0.0
for c in range(41, 45):
    off = (c - 41) * 13.4375e-3
    for line in open(f"../results/sdm3_mb_512k_full_seg{c}.csv"):
        p = line.split()
        t = float(p[0]) + off
        if t <= tend: continue
        p[0] = f"{t:.9e}"
        out.write(" ".join(p) + "\n")
        tend = t
out.close()
print("seg4 merged, t_end=", tend)
EOF
gzip -f ../results/sdm3_mb_512k_full_seg4.csv
echo "[$(date '+%m-%d %H:%M')] seg4 merged+gzipped"

# ---- seg5, seg6 ----
run_seg 5 215.000661 53.75
gzip -f ../results/sdm3_mb_512k_full_seg5.csv
echo "[$(date '+%m-%d %H:%M')] seg5 csv gzipped"
run_seg 6 268.750661 53.75
gzip -f ../results/sdm3_mb_512k_full_seg6.csv
echo "[$(date '+%m-%d %H:%M')] seg6 csv gzipped"

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
