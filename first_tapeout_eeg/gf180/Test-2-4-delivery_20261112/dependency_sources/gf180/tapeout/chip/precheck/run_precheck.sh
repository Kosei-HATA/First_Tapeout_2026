#!/bin/bash
# wafer.space precheck of the chip (tracker E8): the official precheck image (pinned by
# digest, run without network) on the filled chip GDS, slot 1x0p5, top cell chip_top. Then
# the CoB pad-mask check from the same image, and a check that the precheck's Magic DRC
# step really finished: LibreLane runs Magic with check=False and reads an empty report as
# 0 errors, so a Magic crash passes silently (documentation/gf180_chip_assembly_20261023.md).
#
# usage: gf180/tapeout/chip/precheck/run_precheck.sh [GDS] [run tag]
#        GDS defaults to gf180/tapeout/layout/runs/chip_top/chip_top_fill.gds (chip_lay.py --fill)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
TAPEOUT=$(cd "$HERE/../.." && pwd)
GDS=${1:-$TAPEOUT/layout/runs/chip_top/chip_top_fill.gds}
TAG=${2:-pre_$(date +%Y%m%d_%H%M)}
# ghcr.io/wafer-space/gf180mcu-precheck, built 2026-07-22 (revision 8d58ff75, PDK d658698b)
IMAGE=ghcr.io/wafer-space/gf180mcu-precheck@sha256:e24fd3963dae3b0bad09d82178b34cab1a17f21b5fbed7111dceab07a70f5ca6
DIR=$TAPEOUT/layout/runs/precheck
RUN=$DIR/runs/$TAG

mkdir -p "$DIR"
cp "$GDS" "$DIR/chip_top.gds"
echo "input: $GDS"
shasum -a 256 "$DIR/chip_top.gds"

echo "precheck ($TAG): about 45 min"
docker run --rm --network=none --platform linux/amd64 -v "$DIR":/data "$IMAGE" \
    python precheck.py --input /data/chip_top.gds --top chip_top --slot 1x0p5 --dir /data \
    --run-tag "$TAG" --output "/data/chip_top_$TAG.gds" > "$DIR/precheck_$TAG.log" 2>&1
status=$?
if grep -q "Precheck successfully completed" "$DIR/precheck_$TAG.log"; then
    echo "precheck: passed (exit $status)"
else
    echo "precheck: FAILED (exit $status), see $DIR/precheck_$TAG.log"
fi
[ -f "$RUN/final/metrics.json" ] && cat "$RUN/final/metrics.json" && echo

# Magic DRC: the step's script prints "DRC Checking DONE" only when it got to the end
MLOG=$RUN/12-magic-drc/magic-drc.log
if [ -f "$MLOG" ] && ! grep -q "DRC Checking DONE" "$MLOG"; then
    echo "Magic DRC: did NOT finish (its 0 errors is no result); run magic_check.py"
fi

echo "CoB pad mask (slot 1x0p5):"
docker run --rm --network=none --platform linux/amd64 -v "$DIR":/data "$IMAGE" \
    klayout -b -zz -r /workspace/scripts/klayout/check_mask.drc -rd input=/data/chip_top.gds \
    -rd mask=/workspace/assets/golden_masks/mask_1x0p5.gds -rd "output=/data/masked_$TAG.gds" 2>&1 | tail -1
exit $status
