#!/usr/bin/env bash
# chain4 recovery: seg5 died (tts, b.xsdm.xint1.bnopn14#branch) at local
# 15.6289 ms (global 230.63 ms), 2026-10-12 16:12, same periodic hazard as
# seg4's local-15.63 ms death -> every 53.75 ms segment dies ~15.63 ms in.
# Strategy: seg5 and seg6 as 4x13.4375 ms chunks each; the chunk containing
# local 15.63 ms (52 for seg5, 62 for seg6) uses method=gear; others trap.
set -e
cd "$(dirname "$0")"
TPL=tb_gf180_sdm3_mb5_512k_short.spice
BASE=sdm3_mb5_512k_full
NG=/opt/homebrew/bin/ngspice
NS=/tmp/nodesets_mb5_full_seg45.ic   # snapshot at seg4 end (seg5 start state)

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

# ---- seg5 as 4 chunks (global 215.000661..268.750661); chunk 52 contains the ----
# ---- local-15.63 ms death point -> gear for chunk 52 only ----
for c in 51 52 53 54; do
  B=$(python3 -c "print(215.000661 + ($c-51)*13.4375)")
  if [ "$c" = "52" ]; then run_seg $c $B 13.4375 gear; else run_seg $c $B 13.4375; fi
done
merge_chunks 5 51 54

# ---- seg6 as 4 chunks (global 268.750661..322.500661); chunk 62 -> gear ----
for c in 61 62 63 64; do
  B=$(python3 -c "print(268.750661 + ($c-61)*13.4375)")
  if [ "$c" = "62" ]; then run_seg $c $B 13.4375 gear; else run_seg $c $B 13.4375; fi
done
merge_chunks 6 61 64

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
