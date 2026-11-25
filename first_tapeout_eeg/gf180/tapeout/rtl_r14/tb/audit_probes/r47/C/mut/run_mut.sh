#!/usr/bin/env bash
# run one RTL mutant through the r14 groups (as run_tests_r14.sh), stopping at the first group that fails.
# usage: run_mut.sh <tag> <python-file-with-edit>   (the edit file defines EDITS = [(file, old, new), ...])
set -u
TAG=$1; EDIT=$2
BASE=/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad/audit47_C
PY=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python
D=$BASE/mut/$TAG
rm -rf "$D"; mkdir -p "$D/gf180/tapeout"
rsync -a --exclude build "$BASE/gf180/tapeout/rtl" "$BASE/gf180/tapeout/rtl_r14" "$D/gf180/tapeout/"
cp -R "$BASE/documentation" "$D/"
mkdir -p "$D/gf180/tapeout/rtl/build/e2e"
ln -s /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/rtl/build/e2e/s4.codes /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/rtl/build/e2e/s20.codes "$D/gf180/tapeout/rtl/build/e2e/"
for R in typical_ov2.5V_150u_then_dc-39mV_300u typical_ov2.5V_50u_rec60u_f20k_a0.28; do
  mkdir -p "$D/gf180/tapeout/pex/runs/adc_overload_r12/$R"
  ln -s /Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv "$D/gf180/tapeout/pex/runs/adc_overload_r12/$R/out.csv"
done
$PY - "$D" "$EDIT" << 'PYEOF' || { echo "EDIT NOT APPLIED"; exit 3; }
import sys, os
d, ef = sys.argv[1], sys.argv[2]
ns = {}; exec(open(ef).read(), ns)
for f, old, new in ns["EDITS"]:
    p = os.path.join(d, "gf180/tapeout/rtl_r14", f) if os.path.exists(os.path.join(d, "gf180/tapeout/rtl_r14", f)) else os.path.join(d, "gf180/tapeout/rtl", f)
    t = open(p).read()
    if t.count(old) != 1:
        print(f"edit not applied: {old!r} occurs {t.count(old)} times in {p}"); sys.exit(1)
    open(p, "w").write(t.replace(old, new))
print("edits applied:", len(ns["EDITS"]))
PYEOF
S=$D/gf180/tapeout/rtl_r14/run_tests_r14.sh
# early exit after each failing group; skip the spec group (RTL edits cannot change it); order: cheap groups first
$PY - "$S" "${ORDER:-}" << 'PYEOF'
import sys, re
p = sys.argv[1]; t = open(p).read()
lines = t.split("\n")
runs = [l for l in lines if l.startswith("run ")]
order = ["codes", "tb_regs", "tb_seq", "tb_fifo", "tb_fifo4", "tb_tick", "tb_clkgen", "tb_chop1", "tb_cic_arm", "tb_ovl",
         "tb_rnd_sat", "outputs", "tb_spi_r14", "tb_top_r14", "tb_top_r14_fifo4"]
byname = {l.split()[1]: l for l in runs}
assert set(byname) == set(order) | {"spec"}, sorted(byname)
new = []
for n in order:
    new.append(byname[n])
    new.append('[[ ${RES[${#RES[@]}-1]} == FAIL* ]] && { printf "%s\\n" "${RES[@]}"; echo "DETECTED by ' + n + '"; exit 1; }')
idx0 = lines.index(runs[0]); idx1 = lines.index(runs[-1])
lines = lines[:idx0] + new + lines[idx1 + 1:]
open(p, "w").write("\n".join(lines))
PYEOF
W=$BASE/mut/vvp_watch.sh
sed -i '' -e "s|vvp -n build/tb_top_r14.vvp|$W -n build/tb_top_r14.vvp|" -e "s|vvp -n build/tb_top_r14_f4.vvp|$W -n build/tb_top_r14_f4.vvp|" -e "s|vvp -n build/tb_spi_r14.vvp|$W -n build/tb_spi_r14.vvp|" "$S"
grep -c vvp_watch "$S"
cd "$D/gf180/tapeout/rtl_r14" && PYTHON=$PY nice -n 5 ./run_tests_r14.sh
rc=$?
echo "exit $rc"
[ $rc -eq 0 ] && echo "SURVIVED all groups"
