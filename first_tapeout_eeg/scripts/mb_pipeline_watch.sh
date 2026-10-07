#!/usr/bin/env bash
# Autonomous post-screen pipeline for the 4-bit mb 512k runs (2026-10-03).
# Waits for the two screen ngspice jobs (tb_gf180_sdm3_mb_512k_short[ _dwa])
# to exit, gzips + analyzes their CSVs, and if the screen SNDR is healthy
# (>=60 dB over >=2 coherent cycles) launches the corresponding 322.5 ms
# full run (max 2 ngspice at a time). Idempotent; safe to re-run.
# Log: /tmp/mb_pipeline_watch.log
set -u
SIM=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/sim
RES=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/results
STREAM=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/scripts/sdm_mb_bitstream_stream.py
NG=/opt/homebrew/bin/ngspice
MIN_SNDR=60

log() { echo "[$(date '+%m-%d %H:%M')] $*"; }

wait_job() { # $1 = deck basename substring unique to the job
  while pgrep -f "$1" >/dev/null 2>&1; do sleep 300; done
}

analyze() { # $1 = csv path (plain or .gz), $2 = out txt
  python3 "$STREAM" "$1" --ncols 15 --fs 512000 --fsig 32 --skip-ms 2 > "$2" 2>&1
  grep -E "SNDR|coherent" "$2" | tr '\n' ' '; echo
}

sndr_of() { awk -F'= ' '/SNDR/{print $2}' "$1" | awk '{print $1}'; }
ncyc_of() { grep -o "([0-9]* coherent" "$1" | tr -d '(' | awk '{print $1}'; }

screen_done() { # $1 = csv base, $2 = sndr txt -> 0 if healthy
  local csv="$RES/$1.csv"
  [ -f "$csv" ] && ! [ -f "$csv.gz" ] && gzip -f "$csv"
  [ -f "$csv.gz" ] || { log "missing $csv.gz"; return 1; }
  analyze "$csv.gz" "$RES/$2"
  local s n
  s=$(sndr_of "$RES/$2"); n=$(ncyc_of "$RES/$2")
  log "$2: SNDR=${s:-na} dB ncyc=${n:-0}"
  [ -n "$s" ] && [ -n "$n" ] && [ "$n" -ge 2 ] && \
    python3 -c "import sys; sys.exit(0 if float('$s') >= $MIN_SNDR else 1)"
}

cd "$SIM"
log "watcher started; waiting for screen jobs"
wait_job "512k_short_dwa.spice";  log "DWA screen job exited"
wait_job "512k_short.spice";      log "nodwa screen job exited"

ok_nodwa=1; ok_dwa=1
screen_done sdm3_mb_512k_short     screen_nodwa_fixed_sndr.txt && ok_nodwa=0
screen_done sdm3_mb_512k_short_dwa screen_dwa_fixed_sndr.txt    && ok_dwa=0

pids=""
if [ $ok_nodwa -eq 0 ]; then
  log "launching full nodwa run"
  "$NG" -b tb_gf180_sdm3_mb_512k_full.spice > /tmp/mb_full_nodwa.log 2>&1 &
  pids="$pids $!"
fi
if [ $ok_dwa -eq 0 ]; then
  log "launching full DWA run"
  "$NG" -b tb_gf180_sdm3_mb_512k_full_dwa.spice > /tmp/mb_full_dwa.log 2>&1 &
  pids="$pids $!"
fi
for p in $pids; do wait "$p"; done
log "full jobs exited (if any)"

for v in "sdm3_mb_512k_full full_nodwa_sndr.txt" "sdm3_mb_512k_full_dwa full_dwa_sndr.txt"; do
  set -- $v
  csv="$RES/$1.csv"
  [ -f "$csv" ] && ! [ -f "$csv.gz" ] && gzip -f "$csv"
  [ -f "$csv.gz" ] && { analyze "$csv.gz" "$RES/$2"; log "$2: $(sndr_of "$RES/$2") dB"; }
done
log "watcher done"
