#!/bin/zsh
# 11/28: eeg_adc_dig's netlist against its RTL as one combinational question (comb_step.py): with every register
# shared by name (146 = 146 after the same RTL preprocessing as run_eqy_r15.sh's gold), the next states and the
# outputs of the two sides must agree for every input and every common state, the asynchronous resets included.
# ABC decides it with BDDs (collapse): each output of the miter must be the constant 0.
# Why: eqy proves 7 of eeg_adc_dig's 9 partitions; the two DWA rotation registers (u_dwa1/u_dwa2.rot_q: the popcount
# of the 31 TH lines, the thermometer and the rotation by the pointer) stay open under PDR (1 h), dprove (50 min),
# k-induction (bitwuzla) and dprove per pointer value: a SAT question about counting 31 lines. Functions of a
# count have small BDDs in any variable order, and collapse settles the whole design in under a second.
# usage: run_comb_step.sh [tag (adc_dig)]   (EQY_NL=<netlist> for a mutant); out: gl_r15/eqy/work_step_<tag>/
set -u
TAG=${1:-adc_dig}
ROOT=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
T=$ROOT/gf180/tapeout
HERE=$T/digital/gl_r15/eqy
W=$HERE/work_step_$TAG
NL=${EQY_NL:-$T/layout/gds/eeg_adc_dig.nl.v}
LIB=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
PY=$ROOT/gf180/tools/venv310/bin/python
YB=/nix/store/3gz0fa36lbx3a699lhgigzdv48kzff7w-yosys-with-plugins-0.69/bin
SRC="$T/rtl/eeg_adc_dig.sv $T/rtl/eeg_therm2bin.sv $T/rtl/eeg_dwa.sv"
mkdir -p $W
cd $W || exit 1
if [[ -z ${EQY_NL:-} ]]; then
    shasum -a 256 $NL | grep -q '^c39fe2cf' || { echo "FAIL: $NL is not the recorded one (c39fe2cf...)"; exit 1; }
fi
(cd $T && shasum -a 256 rtl/eeg_adc_dig.sv rtl/eeg_therm2bin.sv rtl/eeg_dwa.sv; shasum -a 256 $NL) > src_sha256.txt
$YB/yosys -q -p "read_verilog -sv $SRC; prep -top eeg_adc_dig; memory_map; opt_clean; flatten; opt_dff -nosdff; opt_merge; splitnets -format []; opt_clean; dffunmap; techmap; opt_clean; aigmap; opt_clean; write_json gold_aig.json" > gold.log 2>&1 || { echo "FAIL: gold"; exit 1; }
$YB/yosys -q -p "read_liberty -ignore_miss_func $LIB; read_verilog $NL; prep -top eeg_adc_dig; flatten; dffunmap; techmap; opt_clean; aigmap; opt_clean; write_json gate_aig.json" > gate.log 2>&1 || { echo "FAIL: gate"; exit 1; }
$PY $HERE/comb_step.py gold_aig.json gate_aig.json step.aag > step.txt 2>&1 || { cat step.txt; echo "FAIL: comb_step"; exit 1; }
cat step.txt
$YB/yosys -q -p "read_aiger -module_name step step.aag; write_aiger step.aig" > conv.log 2>&1 || { echo "FAIL: aiger"; exit 1; }
t0=$SECONDS
$YB/yosys-abc -c "read_aiger step.aig; strash; collapse; write_blif collapsed.blif" > abc.log 2>&1 || { echo "FAIL: abc"; exit 1; }
# each output after collapse: a ".names poNNN" without inputs and with the cover " 0" (or no cover) is the constant 0,
# agreement; an output with inputs, or the constant 1, names a register or port that can differ. All outputs counted.
$PY - step.aag collapsed.blif <<'EOF' | tee verdict.txt
import re, sys
names, nout = {}, None
for ln in open(sys.argv[1]):
    if nout is None:
        nout = int(ln.split()[4])
    m = re.match(r"o(\d+) (.*)", ln)
    if m:
        names[int(m[1])] = m[2].strip()
blif = open(sys.argv[2], errors="replace").read().replace("\\\n", " ").split("\n")   # join continued lines
seen, bad = set(), []
for i, ln in enumerate(blif):
    tok = ln.split()
    if len(tok) >= 2 and tok[0] == ".names" and re.fullmatch(r"po\d+", tok[-1]):
        po = int(tok[-1][2:])
        seen.add(po)
        cover = blif[i + 1] if i + 1 < len(blif) else ""
        const0 = len(tok) == 2 and (cover.strip() in ("0",) or cover.startswith(".") or cover.strip() == "")
        if not const0:
            bad.append(names.get(po, tok[-1]))
print(f"{len(seen)} of {nout} miter outputs found, {len(bad)} not constant 0")
for b in bad[:20]:
    print("  can differ:", b)
print("STEP PASS" if nout and len(seen) == nout and not bad else "STEP FAIL")
EOF
echo "abc collapse: $((SECONDS - t0)) s"
