#!/bin/bash
# Run the sky130A KLayout DRC deck on the generated core GDS (batch mode).
# Usage: scripts/klayout/run_drc.sh [gds]
set -euo pipefail

KLAYOUT=/Applications/KLayout/klayout.app/Contents/MacOS/klayout
PDK=${SKY130A_PDK:-/Users/noah/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A}
HERE=$(cd "$(dirname "$0")" && pwd)
PROJ=$(cd "$HERE/../.." && pwd)

GDS=${1:-$PROJ/GDSII/eeg_fd_ota_core_soft.gds}
BASE=$(basename "$GDS" .gds)
REPORT=$PROJ/GDSII/$BASE.drc.txt

"$KLAYOUT" -b -r "$PDK/libs.tech/klayout/drc/sky130A.lydrc" \
    -rd input="$GDS" -rd report="$REPORT"

# summarize: categories with at least one violation item
python3 - "$REPORT" <<'EOF'
import sys, xml.etree.ElementTree as ET
from collections import Counter
root = ET.parse(sys.argv[1]).getroot()
desc = {c.findtext("name"): c.findtext("description")
        for c in root.iter("category") if c.findtext("name")}
count = Counter()
sample = {}
for item in root.iter("item"):
    name = item.findtext("category")
    count[name] += 1
    if name not in sample:
        v = item.find("values/value")
        sample[name] = v.text if v is not None else ""
for name, n in count.most_common():
    print(f"{name}: {n}\t{desc.get(name, '')}\te.g. {sample[name]}")
total = sum(count.values())
print(f"TOTAL VIOLATIONS: {total}")
sys.exit(1 if total else 0)
EOF
