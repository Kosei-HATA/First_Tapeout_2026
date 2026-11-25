#!/usr/bin/env bash
# vvp_watch.sh <vvp args>: vvp, killed at its first ERROR / SPI ERROR / FAIL line (a detected mutant need not run on)
out=$(mktemp /private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit47_C/mut/vw.XXXXXX)
vvp "$@" > "$out" 2>&1 &
pid=$!
while kill -0 "$pid" 2>/dev/null; do
    if grep -qE "^(FAIL|ERROR|SPI ERROR)" "$out"; then
        kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
        cat "$out"; rm -f "$out"
        echo "FAIL: stopped at the first failure line (vvp_watch)"
        exit 1
    fi
    sleep 3
done
wait "$pid"; rc=$?
cat "$out"; rm -f "$out"
exit $rc
