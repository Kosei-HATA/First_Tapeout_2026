#!/usr/bin/env bash
# AFE verification battery for the chopped PGA (source/trials/20260902).
# Runs the 5 PVT corners with the settled bench, then LS-fit analysis.
# Usage: verify_afe.sh [n_parallel]
# NOTE: keep parallelism low (default 2). Each run used to hold >10 GB of
# vectors in RAM; 5-way parallel exhausted swap and caused watchdog panics
# (forced reboots on 2026-09-04). Decks now `save` only needed vectors,
# but stay conservative on this 32 GB machine.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
XD=$ROOT/source/trials/20260902/xschem
PAR=${1:-2}
cd "$XD"

specs=("tt 1.80 27" "ss 1.62 125" "ff 1.98 -40" "sf 1.80 27" "fs 1.80 27")
for spec in "${specs[@]}"; do
  set -- $spec
  sed -e "s/@CORNER@/$1/" -e "s/@VDD@/$2/g" -e "s/@TEMP@/$3/" -e "s/@TAG@/$1/g" \
      tb_afe_chopped_pga.spice > tb_run_$1.spice
done
echo "launching ${#specs[@]} corner runs (1.536 s sim each)..."
# bash 3.2 (macOS) has no `wait -n`; throttle with xargs -P instead.
printf '%s\n' "${specs[@]}" | xargs -P "$PAR" -n3 bash -c \
  'ngspice -b tb_run_$0.spice > tb_run_$0.log 2>&1'
echo "runs done; analysis:"
for c in tt ss ff sf fs; do
  echo "=== $c"
  grep -E "idd_avg|vcm_avg" tb_run_$c.log | sed 's/^/  /'
  python3 $ROOT/scripts/lsfit_gain.py ../results/tb_afe_$c.csv 8 --skip 0.75 2>/dev/null | grep -E "signal|residual" | sed 's/^/  /'
done
