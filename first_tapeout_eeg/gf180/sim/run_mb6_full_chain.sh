#!/usr/bin/env bash
# Acceptance full-run chain: 6 segments x 53.75 ms of the fixed nodwa mb deck.
# Each segment < 62.5 ms local (dodges the run-relative timestep collapse).
# Sequential; log progress to stdout (nohup target: /tmp/mb6_full_chain.log).
set -e
cd "$(dirname "$0")"
TPL=tb_gf180_sdm3_mb6_512k_short.spice
BASE=sdm3_mb6_512k_full
NG=/opt/homebrew/bin/ngspice
NS=none
for k in 1 2 3 4 5 6; do
  prev=$((k-1))
  B=$(python3 -c "print(0.000661 + $prev*53.75)")          # PH1-rise boundary (ms)
  E=$(python3 -c "print(0.000661 + $k*53.75)")
  L=$(python3 -c "print(min($E,322.5)-$B)")
  echo "[$(date '+%m-%d %H:%M')] seg$k start: global $B .. $(python3 -c "print(min($E,322.5))") ms (L=$L ms)"
  python3 mb_seg6.py make $TPL $k $B $L $BASE $NS /tmp/tb_mb6_full_seg$k.spice
  $NG -b /tmp/tb_mb6_full_seg$k.spice > /tmp/mb6_full_seg$k.log 2>&1
  n=$(grep -c "Timestep too small" /tmp/mb6_full_seg$k.log || true)
  echo "[$(date '+%m-%d %H:%M')] seg$k done (tts=$n)"
  if [ "$n" != "0" ]; then echo "seg$k DIED: $(grep -o 'trouble with node \"[^\"]*\"' /tmp/mb6_full_seg$k.log | tail -1)"; exit 1; fi
  python3 mb_seg6.py snap /tmp/mb6_full_seg$k.log /tmp/nodesets_mb6_full_seg$((k+1)).ic
  NS=/tmp/nodesets_mb6_full_seg$((k+1)).ic
  gzip -f ../results/${BASE}_seg$k.csv
  echo "[$(date '+%m-%d %H:%M')] seg$k csv gzipped"
done
python3 - <<'EOF'
import gzip, glob
B0=0.000661e-3; seg=53.75e-3
out=open("../results/sdm3_mb6_512k_full_chain.csv","w")
tend=0.0
for k in range(1,7):
    Bk=B0+(k-1)*seg
    with gzip.open(f"../results/sdm3_mb6_512k_full_seg{k}.csv.gz","rt") as f:
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
gzip -f ../results/sdm3_mb6_512k_full_chain.csv
python3 /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/scripts/sdm_mb_bitstream_stream.py \
  ../results/sdm3_mb6_512k_full_chain.csv.gz --ncols 63 --fs 512000 --fsig 32 --skip-ms 2 \
  > ../results/mb6_full_chain_sndr.txt 2>&1
echo "[$(date '+%m-%d %H:%M')] FULL CHAIN DONE"
cat ../results/mb6_full_chain_sndr.txt
