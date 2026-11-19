#!/usr/bin/env python3
"""NFR-06 on the structure: every output of eeg_digital_top is driven by a flip-flop (audit round 4, 11/20: a copy
that drove DRDY_N combinationally passed every functional test; a functional bench cannot tell a register from the
same function of registers).

Yosys reads the RTL (read_verilog -sv, hierarchy, proc, flatten, opt) and writes the netlist as JSON; every bit of
every output port must come from a flip-flop cell (a type with "dff": $dff, $adff, $dffe, $adffe, ...), except:
  CHOP_EN     a $not of one flip-flop (the active copy of CHOP_STOP): one input, no glitch
  CHOP_BLANK  a $or of two flip-flops: the frame's blanking (it changes at frame cycle 31 and when the window ends,
              cycle 15 at the longest) and the active copy of ADC_ZERO (it changes at a tick, e25, or in a reset),
              which never change at one edge
  MISO_OE     combinational, as in r13 (NFR-06)
For CHOP_EN and CHOP_BLANK every input of that one gate must itself come from a flip-flop.

Usage: check_outputs_registered.py [rtl_r14 directory]   (default: this one; the mutation runner passes its copy,
       which also holds the blocks kept from rtl/)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
R14 = os.path.normpath(os.path.join(HERE, ".."))
RTL_OLD = os.path.normpath(os.path.join(R14, "..", "rtl"))
SPEC = os.path.join(RTL_OLD, "spec")
SRC = ["eeg_digital_top.sv", "eeg_seq.sv", "eeg_regs.sv", "eeg_spi_slave.sv", "eeg_fifo.sv", "eeg_ovl.sv",
       "eeg_cic3.sv", "eeg_clkgen.sv"]
OLD = ["eeg_chop1.sv", "eeg_raw.sv", "eeg_rnd_sat.sv"]
YOSYS = os.environ.get("YOSYS", "/nix/store/0inxmdvzndxxzsiyjrfjzslay6qllx96-yosys-0.69/bin/yosys")
ALLOWED = {"CHOP_EN": ("$not", True), "CHOP_BLANK": ("$or", True), "MISO_OE": (None, False)}


def main():
    d = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else R14
    files = [os.path.join(d, f) for f in SRC]
    files += [os.path.join(d, f) if os.path.exists(os.path.join(d, f)) else os.path.join(RTL_OLD, f) for f in OLD]
    if not os.path.exists(YOSYS):
        print(f"FAIL: yosys not found at {YOSYS} (set YOSYS)")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, "top.json")
        cmd = (f"read_verilog -sv -I{SPEC} -I{os.path.join(R14, 'build')} {' '.join(files)}; "
               f"hierarchy -top eeg_digital_top; proc; flatten; opt_clean; opt -purge; write_json {js}")
        r = subprocess.run([YOSYS, "-q", "-p", cmd], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(js):
            print("FAIL: yosys: " + (r.stderr.strip().splitlines() or ["no output"])[-1])
            return 1
        m = json.load(open(js))["modules"]["eeg_digital_top"]
    drv = {}
    for name, c in m["cells"].items():
        for p, direction in c["port_directions"].items():
            if direction == "output":
                for b in c["connections"][p]:
                    if isinstance(b, int):
                        drv[b] = (c["type"], name, c)
    is_ff = lambda b: isinstance(b, int) and b in drv and "dff" in drv[b][0]
    bad, notes, nbits = [], [], 0
    for port, p in sorted(m["ports"].items()):
        if p["direction"] != "output":
            continue
        for i, b in enumerate(p["bits"]):
            nbits += 1
            if is_ff(b):
                continue
            kind = drv[b][0] if isinstance(b, int) and b in drv else ("constant" if isinstance(b, str) else "undriven")
            if port in ALLOWED:
                want, one_level = ALLOWED[port]
                if want is None:
                    notes.append(f"{port}: {kind} (allowed: as in r13)")
                    continue
                if kind == want and one_level:
                    c = drv[b][2]
                    ins = [x for q, dirn in c["port_directions"].items() if dirn == "input" for x in c["connections"][q]]
                    if all(is_ff(x) for x in ins):
                        notes.append(f"{port}: {kind} of {len(ins)} flip-flop output(s) (allowed)")
                        continue
                    bad.append(f"{port}[{i}]: {kind} whose inputs are not all flip-flops")
                    continue
            bad.append(f"{port}[{i}]: driven by {kind}, not a flip-flop")
    print(f"{nbits} output bits of eeg_digital_top: {nbits - len(bad) - len(notes)} from flip-flops; " + "; ".join(notes))
    for x in bad:
        print("  " + x)
    print("PASS: every output is a register's (NFR-06)" if not bad else f"FAIL: {len(bad)} output bits not from a register")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
