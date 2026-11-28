#!/bin/zsh
# 11/28: formal equivalence (eqy) of the r15 macro's final netlist (layout/gds/r15/eeg_digital_top.nl.v, LibreLane run
# r15m13_20261128, the cells' functions from the PDK liberty tt) with its RTL (rtl_r15, the sources of 8cbe4bd7).
#
# Match points (ff_names.py, 11/28): the ports and the flip-flops' outputs, one name per signal, nothing combinational.
#   * A matched combinational net is a free input of the partitions it feeds, and the netlist after it may recompute
#     the same function from the registers: false counterexamples (u_cic.dcnt with dec = 1 while dcnt != CNT_LAST,
#     drdy_pulse with drdy_nxt != 0 while push_ok = 0 and drdy_cnt = 0).
#   * eqy's insbuf chains the names of one signal and cuts the consumers at the last matched one; the chains run in
#     different orders in the RTL and the netlist (a_azero / TEST_CFG[5], u_regs.o_ofs / OFS, ...), so two matched
#     names of one signal gave two free inputs for it (OFS, OFM, OFEN, a_azero, MISO, ... in the first runs).
#   * insbuf off is no way out: it drops the matches of names that are only aliases (16 of the 25 output ports were
#     compared nowhere); check_cover.py fails the run if any matched bit or output port is not a compare point.
# The synthesis renumbered the FIFO's status bits (ff_names.py GATE_AS_GOLD). Flip-flops it removed (constant or
# unused with CHOP_DLY tied to 0, FIFO status bits that are always 0 or 1) stay unmatched on the RTL side; their x
# initial value only makes the comparison vacuous until they are loaded.
# The RTL side gets opt_dff -nosdff and opt_merge after flatten, as the synthesis does: it merges registers with the
# same inputs (eeg_adc_dig's two DWAs sample the same k: the netlist has u_dwa1.k_q only), and an RTL register without
# its netlist twin would be state inside a partition while the netlist's logic reads a free input (false
# counterexamples SEL2, u_dwa2.ptr). opt_dff turns a register's hold multiplexer into an enable (the same function),
# so that the two k_q registers have the same inputs, and replaces registers whose D is the constant they reset to by
# that constant (the RTL's value before the first clock is x; the comparison only gets stricter); opt_merge merges
# cells with the same type and inputs. Neither changes what the RTL computes.
# Strategy: PDR only (sby, abc pdr; bitwuzla for the witness), on every partition. eqy's sat strategy is vacuous here
# (found by mutate_eqy_r15.py, 11/28: a netlist with OFS's load condition broken and one with TEST_CFG[5]'s reset value
# changed both "passed"): it runs `sat -tempinduct -set-init-undef -set-def-formal ...` after `formalff -ff2anyinit`
# on the gate, and the gate's $anyinit flip-flops are then both undefined and defined at the start, so the problem
# has no model as soon as a partition holds a gate flip-flop (`sat -seq 1 -set-init-undef -set-def-formal` alone:
# no model found) and every assertion counts as proved. The sby flow (xprop on the miter, PDR) has no such clash.
# usage: run_eqy_r15.sh [tag (r15m13)]; out: gl_r15/eqy/work_<tag>/ (eqy's work directory eqy_r15/, the log, summary)
#        EQY_NL=<netlist> run_eqy_r15.sh mut_<id>: another netlist (mutate_eqy_r15.py's mutants), not recorded
#        EQY_DESIGN=adc_dig run_eqy_r15.sh adc_dig: the chip's other digital macro, eeg_adc_dig (layout/gds, the f3 run
#        of 10/23, in every chip since; RTL rtl/eeg_adc_dig.sv, eeg_therm2bin.sv, eeg_dwa.sv of the same commit ce7d27fe)
set -u
TAG=${1:-r15m13}
ROOT=/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg
T=$ROOT/gf180/tapeout
HERE=$T/digital/gl_r15/eqy
W=$HERE/work_$TAG
DESIGN=${EQY_DESIGN:-top}
case $DESIGN in
    top)     TOP=eeg_digital_top; NL0=$T/layout/gds/r15/eeg_digital_top.nl.v; SUM=a8d1c089; REC=eeg_digital_top_r15.eqy
             SCL=gf180mcu_fd_sc_mcu9t5v0 ;;
    adc_dig) TOP=eeg_adc_dig; NL0=$T/layout/gds/eeg_adc_dig.nl.v; SUM=c39fe2cf; REC=eeg_adc_dig.eqy
             SCL=gf180mcu_fd_sc_mcu7t5v0 ;;     # the ADC's macro uses the 7-track cells
    *)       echo "EQY_DESIGN: top or adc_dig"; exit 1 ;;
esac
NL=${EQY_NL:-$NL0}
LIB=/Users/noah/Codings/ws_gf180/eeg_padring/gf180mcu/gf180mcuD/libs.ref/$SCL/lib/${SCL}__tt_025C_3v30.lib
PY=$ROOT/gf180/tools/venv310/bin/python
YB=/nix/store/3gz0fa36lbx3a699lhgigzdv48kzff7w-yosys-with-plugins-0.69/bin
BW=/nix/store/22gfimhz05m364nb82bjm9idz07yqll8-bitwuzla-0.9.0/bin
export PATH=$YB:$BW:$PATH
R=$T/rtl_r15
if [[ $DESIGN == top ]]; then
    SRC="-I $R/spec $R/eeg_digital_top.sv $R/eeg_seq.sv $R/eeg_regs.sv $R/eeg_spi_slave.sv $R/eeg_fifo.sv $R/eeg_ovl.sv
         $R/eeg_cic3.sv $R/eeg_clkgen.sv $T/rtl/eeg_chop1.sv $T/rtl/eeg_raw.sv $T/rtl/eeg_rnd_sat.sv"
    SUMS="rtl_r15/eeg_*.sv rtl/eeg_chop1.sv rtl/eeg_raw.sv rtl/eeg_rnd_sat.sv rtl_r15/spec/eeg_regs_defs.svh layout/gds/r15/eeg_digital_top.nl.v"
else
    SRC="$T/rtl/eeg_adc_dig.sv $T/rtl/eeg_therm2bin.sv $T/rtl/eeg_dwa.sv"
    SUMS="rtl/eeg_adc_dig.sv rtl/eeg_therm2bin.sv rtl/eeg_dwa.sv layout/gds/eeg_adc_dig.nl.v"
fi
SRC=${SRC//$'\n'/ }
SRC=${SRC//  / }
GOLD="read_verilog -sv $SRC
prep -top $TOP
memory_map
opt_clean
flatten
opt_dff -nosdff
opt_merge
splitnets -format []
opt_clean"
GATE="read_liberty -ignore_miss_func $LIB
read_verilog $NL
prep -top $TOP"
mkdir -p $W
cd $W || exit 1
if [[ -z ${EQY_NL:-} ]]; then
    shasum -a 256 $NL | grep -q "^$SUM" || { echo "FAIL: $NL is not the recorded one ($SUM...)"; exit 1; }
fi
(cd $T && git log -1 --format='HEAD %H %ad' --date=iso && shasum -a 256 ${~=SUMS}; shasum -a 256 $NL) > src_sha256.txt
# the register names on both sides, with the same scripts as eqy's [gold] / [gate] + [script] flatten
yosys -q -p "${GOLD//$'\n'/; }; write_json gold_ff.json" > gold_ff.log 2>&1 || { echo "FAIL: gold json"; exit 1; }
yosys -q -p "${GATE//$'\n'/; }; flatten; opt_clean; write_json gate_ff.json" > gate_ff.log 2>&1 || { echo "FAIL: gate json"; exit 1; }
$PY $HERE/ff_names.py gold_ff.json gate_ff.json match.txt > ff_names.txt || { cat ff_names.txt; echo "FAIL: ff_names"; exit 1; }
head -4 ff_names.txt
{
    echo "# generated by run_eqy_r15.sh ($(date '+%Y-%m-%d %H:%M')); see its header"
    echo "[gold]"
    echo "$GOLD"
    echo
    echo "[gate]"
    echo "$GATE"
    echo
    echo "[match *]"
    echo "nodefault"
    cat match.txt
    echo
    echo "[script]"
    echo "flatten"
    echo "async2sync"
    echo "opt_clean"
    echo
    echo "[strategy pdr]"
    echo "use sby"
    echo "engine abc pdr"
    echo "depth 20"
    echo "timeout 3600"
    echo "option aigsmt bitwuzla"
} > eqy_r15.eqy
[[ -z ${EQY_NL:-} ]] && cp eqy_r15.eqy $HERE/$REC
rm -rf eqy_r15
date
eqy -j 4 -f eqy_r15.eqy > eqy.log 2>&1
rc=$?
date
{
    echo "eqy rc $rc"
    echo "partitions: $(grep -c '^' eqy_r15/partition.list 2>/dev/null)"
    echo "proved by pdr: $(grep 'Proved equivalence of partition' eqy.log | grep -c "strategy 'pdr'")"
    echo "not proved:"
    grep 'Failed to prove equivalence of partition' eqy.log | sed 's/.*partition /  /'
    grep 'DONE' eqy.log | tail -1
    $PY $HERE/check_cover.py gold_ff.json match.txt eqy_r15 && echo "COVER PASS" || echo "COVER FAIL"
} | tee summary.txt
