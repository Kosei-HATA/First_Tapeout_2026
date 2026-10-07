#!/usr/bin/env bash
# Autonomous segmented-path pipeline (2026-10-04, after the fixed-deck nodwa
# screen still died at 62.5046 ms -> segmentation is the primary path).
# Chain: [DWA single screen exit] -> DWA seg screen -> analyze both seg
# screens (nodwa seg screen was launched separately) -> if healthy, launch
# both 6-segment FULL runs in parallel -> analyze. Max 2 ngspice jobs.
# Log: /tmp/mb_seg_pipeline.log
set -u
SIM=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/sim
RES=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/results
STREAM=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/scripts/sdm_mb_bitstream_stream.py
MIN_SNDR=60

log() { echo "[$(date '+%m-%d %H:%M')] $*"; }
wait_gone() { while pgrep -f "$1" >/dev/null 2>&1; do sleep 300; done; }

analyze() { # $1 csv (plain), $2 out txt, $3 seg-prefix for cleanup
  [ -f "$1" ] || { log "missing $1"; return 1; }
  python3 "$STREAM" "$1" --ncols 15 --fs 512000 --fsig 32 --skip-ms 2 > "$2" 2>&1
  local s n
  s=$(awk -F'= ' '/SNDR/{print $2}' "$2" | awk '{print $1}')
  n=$(grep -o "([0-9]* coherent" "$2" | tr -d '(' | awk '{print $1}')
  log "$(basename "$2"): SNDR=${s:-na} dB ncyc=${n:-0}"
  gzip -f "$1"
  rm -f "$RES/${3}"_seg*.csv
  [ -n "$s" ] && [ -n "$n" ] && [ "$n" -ge 2 ] && \
    python3 -c "import sys; sys.exit(0 if float('$s') >= $MIN_SNDR else 1)"
}

cd "$SIM"
log "seg pipeline watcher started"

# 1) DWA single-process screen exits (expected crash ~62.5 ms), then DWA seg screen
wait_gone "tb_gf180_sdm3_mb_512k_short_dwa.spice"
log "DWA single screen exited; launching DWA seg screen"
nohup bash run_mb_screen_seg_dwa.sh > /tmp/mb_screen_seg_dwa_run.log 2>&1 &

# 2) nodwa seg screen (already running) -> analyze
wait_gone "run_mb_screen_seg\.sh"
log "nodwa seg screen wrapper exited"
ok_n=1
analyze "$RES/sdm3_mb_512k_short.csv" "$RES/screen_nodwa_seg_sndr.txt" sdm3_mb_512k_short && ok_n=0

# 3) DWA seg screen -> analyze
wait_gone "run_mb_screen_seg_dwa\.sh"
log "DWA seg screen wrapper exited"
ok_d=1
analyze "$RES/sdm3_mb_512k_short_dwa.csv" "$RES/screen_dwa_seg_sndr.txt" sdm3_mb_512k_short_dwa && ok_d=0

# 4) full runs (2 parallel max)
pids=""
if [ $ok_n -eq 0 ]; then
  log "launching nodwa seg FULL"
  nohup bash run_mb_full_seg.sh tb_gf180_sdm3_mb_512k_full.spice sdm3_mb_512k_full > /tmp/mb_full_seg_run.log 2>&1 &
  pids="$pids $!"
fi
if [ $ok_d -eq 0 ]; then
  log "launching DWA seg FULL"
  nohup bash run_mb_full_seg.sh tb_gf180_sdm3_mb_512k_full_dwa.spice sdm3_mb_512k_full_dwa > /tmp/mb_full_seg_dwa_run.log 2>&1 &
  pids="$pids $!"
fi
for p in $pids; do wait "$p"; done
log "full seg wrappers exited (if any)"

[ $ok_n -eq 0 ] && analyze "$RES/sdm3_mb_512k_full.csv" "$RES/full_nodwa_seg_sndr.txt" sdm3_mb_512k_full
[ $ok_d -eq 0 ] && analyze "$RES/sdm3_mb_512k_full_dwa.csv" "$RES/full_dwa_seg_sndr.txt" sdm3_mb_512k_full_dwa
log "seg pipeline done"
