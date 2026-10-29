#!/bin/bash
# wafer.space precheck of the chip (tracker E8): the official precheck image (pinned by
# digest, run without network) on the filled chip GDS, slot 1x0p5, top cell chip_top, --cob
# (the shuttle is ordered as Chip-on-Board: the precheck then also checks that the four ID
# cells sit once each where the template puts them, and that the pads match the slot's pad
# mask). The precheck passes with Magic DRC violations (ERROR_ON_MAGIC_DRC is off), so every
# count in metrics.json is checked here, and so is that the Magic DRC step really finished:
# LibreLane runs Magic with check=False and reads an empty report as 0 errors, so a Magic
# crash passes silently (documentation/gf180_chip_assembly_20261023.md).
#
# usage: gf180/tapeout/chip/precheck/run_precheck.sh [GDS] [run tag]
#        GDS defaults to gf180/tapeout/layout/runs/chip_top/chip_top_fill.gds (chip_lay.py --fill)
#        PRECHECK_IMAGE=<image> runs another precheck image (the earlier one is below)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TAPEOUT=$(cd "$HERE/../.." && pwd)
GDS=${1:-$TAPEOUT/layout/runs/chip_top/chip_top_fill.gds}
TAG=${2:-pre_$(date +%Y%m%d_%H%M)}
# ghcr.io/wafer-space/gf180mcu-precheck, built 2026-10-20 (revision 9b4e7dab, PDK 792ef670).
# Up to pre_20261026 (without --cob): @sha256:e24fd3963dae3b0bad09d82178b34cab1a17f21b5fbed7111dceab07a70f5ca6
# (built 2026-07-22, revision 8d58ff75, PDK d658698b)
IMAGE=${PRECHECK_IMAGE:-ghcr.io/wafer-space/gf180mcu-precheck@sha256:104d9ccbc0d3e4bbffba6201b7f68cd8f64d064b5b9072b64a3a4c926d46339f}
DIR=$TAPEOUT/layout/runs/precheck
RUN=$DIR/runs/$TAG

mkdir -p "$DIR"
cp "$GDS" "$DIR/chip_top.gds"
echo "input: $GDS"
shasum -a 256 "$DIR/chip_top.gds"
echo "image: $IMAGE"

echo "precheck ($TAG): about 55 min"
# nofile 1024: with the container's default (1048576) Magic warns "RLIMIT_NOFILE is above
# 1024 and Tcl_Version<9 this may cause runtime issues"
docker run --rm --network=none --platform linux/amd64 --ulimit nofile=1024:1024 -v "$DIR":/data "$IMAGE" \
    python precheck.py --input /data/chip_top.gds --top chip_top --slot 1x0p5 --cob --dir /data \
    --run-tag "$TAG" --output "/data/chip_top_$TAG.gds" > "$DIR/precheck_$TAG.log" 2>&1
status=$?
if grep -q "Precheck successfully completed" "$DIR/precheck_$TAG.log"; then
    echo "precheck: passed (exit $status)"
else
    echo "precheck: FAILED (exit $status), see $DIR/precheck_$TAG.log"
fi
if [ -f "$RUN/final/metrics.json" ]; then
    cat "$RUN/final/metrics.json" && echo
    if grep -qE '_count": *[1-9]' "$RUN/final/metrics.json"; then
        echo "counts: NOT all 0"
        status=1
    fi
fi

# the --cob steps: GenerateID asserts the ID cells' placement, CheckPadMask the pads
grep -h "Inserted ID" "$RUN"/*-klayout-generateid/*.log 2>/dev/null
grep -h "Pad mask" "$RUN"/*-klayout-checkpadmask/*.log 2>/dev/null

# Magic DRC: the step's script prints "DRC Checking DONE" only when it got to the end
MLOG=$(ls "$RUN"/*-magic-drc/magic-drc.log 2>/dev/null | head -1)
if [ -z "$MLOG" ]; then
    echo "Magic DRC: no log"
elif grep -q "DRC Checking DONE" "$MLOG"; then
    echo "Magic DRC: finished"
else
    echo "Magic DRC: did NOT finish (its 0 errors is no result); run magic_check.py"
    status=1
fi
exit $status
