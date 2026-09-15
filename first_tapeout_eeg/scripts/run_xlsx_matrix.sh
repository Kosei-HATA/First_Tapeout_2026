#!/bin/bash
# test.xlsx matrix runner: 68 runs, xargs -P 2 (memory-safe).
set -u
cd "$(dirname "$0")/../source/trials/20260902/xschem"

run_one() {  # tag voff fsig cfb wave
  local TAG=$1 VOFF=$2 FSIG=$3 CFB=$4 WAVE=$5
  local DECK=tb_xlsx_${TAG}.spice
  sed -e "s|VOFF=0|VOFF=$VOFF|" -e "s|FSIG=8|FSIG=$FSIG|" -e "s|CFB=1p|CFB=$CFB|" -e "s|@TAG@|$TAG|" tb_xlsx.spice > $DECK
  if [ "$WAVE" = "sq" ]; then
    local T TH
    T=$(python3 -c "print(1.0/$FSIG)"); TH=$(python3 -c "print(0.5/$FSIG)")
    sed -i '' -e "s|^VSIGP SIGP 0 SIN.*|VSIGP SIGP 0 PULSE({VCM-AMP} {VCM+AMP} 0 100n 100n ${TH} ${T})|" \
              -e "s|^VSIGN SIGN 0 SIN.*|VSIGN SIGN 0 PULSE({VCM+AMP} {VCM-AMP} 0 100n 100n ${TH} ${T})|" $DECK
  fi
  if [ "$WAVE" = "dc" ]; then
    sed -i '' "s|AMP=100u|AMP=0|" $DECK
  fi
  /opt/homebrew/bin/ngspice -b $DECK > ../results/xlsx_${TAG}.log 2>&1
  echo "done $TAG $(date +%H:%M:%S)"
}
export -f run_one

JOBS=$(mktemp)
for G in x8:4p x16:2p x32:1p x64:0.5p; do
  IFS=: read GN CFB <<< "$G"
  for MV in 50 40 30 20 10 0 m10 m20 m30 m40 m50; do
    case $MV in m*) V="-${MV#m}m";; *) V="${MV}m";; esac
    echo "dc_${GN}_${MV} $V 8 $CFB dc" >> $JOBS
  done
  for F in 4 10 24; do
    echo "sin_${GN}_${F} 0 $F $CFB sin" >> $JOBS
    echo "sq_${GN}_${F} 0 $F $CFB sq" >> $JOBS
  done
done
wc -l < $JOBS
xargs -P 2 -L 1 bash -c 'run_one "$@"' _ < $JOBS
echo "ALL DONE"
