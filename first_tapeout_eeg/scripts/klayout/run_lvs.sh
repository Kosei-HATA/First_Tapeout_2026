#!/bin/bash
# Run the sky130A KLayout LVS deck on the generated core GDS (batch mode)
# against scripts/klayout/core_ref.spice.
# Usage: scripts/klayout/run_lvs.sh [gds] [ref_spice]
set -euo pipefail

KLAYOUT=/Applications/KLayout/klayout.app/Contents/MacOS/klayout
PDK=${SKY130A_PDK:-/Users/noah/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A}
HERE=$(cd "$(dirname "$0")" && pwd)
PROJ=$(cd "$HERE/../.." && pwd)

GDS=${1:-$PROJ/GDSII/eeg_fd_ota_core_soft.gds}
REF=${2:-$HERE/core_ref.spice}
MODE=${3:-flat}
BASE=$(basename "$GDS" .gds)
REPORT=$PROJ/GDSII/$BASE.lvsdb
EXTRACTED=$PROJ/GDSII/${BASE}_extracted.cir
LOG=$PROJ/GDSII/${BASE}_lvs.log

# the stock deck's logger shells out to Linux `pmap`; provide a macOS shim
export PATH="$HERE/bin:$PATH"

# lvs_sub=VSS: name the global substrate net VSS (matches the ref netlist
# bulk nodes). scale=false: extracted device params in um, matching the
# "L=4u" style values in the reference. combine: merge multi-finger MOS and
# series resistor chains into single devices.
"$KLAYOUT" -b -r "$PDK/libs.tech/klayout/lvs/sky130.lvs" \
    -rd input="$GDS" \
    -rd schematic="$REF" \
    -rd report="$REPORT" \
    -rd target_netlist="$EXTRACTED" \
    -rd lvs_sub=VSS \
    -rd run_mode=$MODE -rd scale=false -rd spice_net_names=true \
    -rd combine=true -rd top_lvl_pins=true -rd purge=true -rd purge_nets=true \
    2>&1 | tee "$LOG" | grep -a "match\|MATCH\|ERROR"
