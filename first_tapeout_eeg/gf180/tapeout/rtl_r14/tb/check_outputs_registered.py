#!/usr/bin/env python3
"""NFR-06 on the structure: every output of eeg_digital_top is driven by a flip-flop (audit round 4, 11/20: a copy
that drove DRDY_N combinationally passed every functional test; a functional bench cannot tell a register from the
same function of registers).

Yosys reads the RTL (read_verilog -sv, hierarchy, proc, flatten, opt) and writes the netlist as JSON; every bit of
every output port must come from a flip-flop cell (a type with "dff": $dff, $adff, $dffe, $adffe, ...), except:
  CHOP_EN     a $not of one flip-flop (the active copy of CHOP_STOP): one input, no glitch
  CHOP_BLANK  a $or of two flip-flops: the frame's blanking (it changes at frame cycle 31 and when the window ends,
              cycle 15 at the longest) and the active copy of ADC_ZERO (it changes at a tick, e25), which never change
              at one edge in operation; a SOFT_RESET in the ADC_ZERO test mode clears the latter after the reset
              tree's delay, later than the blanking flip-flop's clock-to-Q at the same edge, so the OR changes once
  MISO_OE     combinational, as in r13 (NFR-06)
For CHOP_EN and CHOP_BLANK every input of that one gate must itself come from a flip-flop.

Also the synchronizers of the asynchronous inputs (audit round 9, auditor C: single-flop synchronizers passed every
functional test; their metastability cannot be simulated):
  RESET_N   only the asynchronous resets of a 2-flop release chain: the first flop takes the constant 1, the second
            the first's output, and the first's output goes nowhere else (the second's output is the reset used)
  CS_N, SCLK, MOSI   each feeds exactly one first flop, whose output feeds only the next flop (logic sees the second
            flop or later); CS_N also goes, combinationally, to MISO_OE only (its cut at the CS_N rise, as in r13)

Exit: 0 every output a flip-flop's (PASS), 1 an output that is not (FAIL), 2 the tool did not run (TOOL ERROR).
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
        print(f"TOOL ERROR: yosys not found at {YOSYS} (set YOSYS)")
        return 2                                     # not a finding about the design (audit round 6)
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, "top.json")
        cmd = (f"read_verilog -sv -I{SPEC} -I{os.path.join(R14, 'build')} {' '.join(files)}; "
               f"hierarchy -top eeg_digital_top; proc; flatten; opt_clean; opt -purge; write_json {js}")
        r = subprocess.run([YOSYS, "-q", "-p", cmd], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(js):
            print("TOOL ERROR: yosys: " + (r.stderr.strip().splitlines() or ["no output"])[-1])
            return 2
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
    sbad, snotes = check_synchronizers(m)
    print("synchronizers: " + "; ".join(snotes))
    for x in bad + sbad:
        print("  " + x)
    if bad or sbad:
        print(f"FAIL: {len(bad)} output bits not from a register, {len(sbad)} synchronizer faults")
    else:
        print("PASS: every output is a register's (NFR-06); every asynchronous input passes 2 flip-flops")
    return 1 if bad or sbad else 0


def check_synchronizers(m):
    """The release of RESET_N and the SPI inputs' first flops, bit by bit on the word-level netlist."""
    sinks, ffbit = {}, {}                              # bit -> [(cell, port, index)], Q bit -> (cell, index)
    for name, c in m["cells"].items():
        for p, direction in c["port_directions"].items():
            for i, b in enumerate(c["connections"][p]):
                if not isinstance(b, int):
                    continue
                if direction == "input":
                    sinks.setdefault(b, []).append((name, p, i))
                elif "dff" in c["type"] and p == "Q":
                    ffbit[b] = (name, i)
    outbits = {b: port for port, pp in m["ports"].items() if pp["direction"] == "output" for b in pp["bits"]
               if isinstance(b, int)}
    port_bit = lambda n: m["ports"][n]["bits"][0]
    bad, notes = [], []

    def d_of(cell, i):                                  # the D input bit i of a flop cell
        return m["cells"][cell]["connections"]["D"][i]

    # RESET_N: only asynchronous resets, of a 2-flop chain
    rn = port_bit("RESET_N")
    rs = sinks.get(rn, [])
    if any(p not in ("ARST", "CLR", "SET") for _c, p, _i in rs):
        bad.append("RESET_N reaches logic other than the asynchronous resets of its synchronizer")
    stage = [(c, i) for c in {c for c, _p, _i in rs} for i in range(len(m["cells"][c]["connections"]["Q"]))]
    if len(stage) != 2:
        bad.append(f"RESET_N resets {len(stage)} flip-flop bits directly, expected the 2 of its release chain")
    else:
        first = [x for x in stage if d_of(*x) == "1"]
        if len(first) != 1:
            bad.append("RESET_N's release chain: no single first flop taking the constant 1")
        else:
            q1 = m["cells"][first[0][0]]["connections"]["Q"][first[0][1]]
            nxt = sinks.get(q1, [])
            if len(nxt) != 1 or nxt[0][1] != "D" or q1 in outbits:
                bad.append("RESET_N's first release flop drives more than the second (a single-flop release)")
            else:
                notes.append("RESET_N released through 2 flip-flops")
    # CS_N, SCLK, MOSI: a first flop that feeds only the next one
    for n in ("CS_N", "SCLK", "MOSI"):
        b = port_bit(n)
        ff1 = [(c, i) for c, p, i in sinks.get(b, []) if "dff" in m["cells"][c]["type"] and p == "D"]
        other = [(c, p) for c, p, i in sinks.get(b, []) if not ("dff" in m["cells"][c]["type"] and p == "D")]
        if len(ff1) != 1:
            bad.append(f"{n} feeds {len(ff1)} flip-flops directly, expected 1")
            continue
        q1 = m["cells"][ff1[0][0]]["connections"]["Q"][ff1[0][1]]
        nxt = sinks.get(q1, [])
        if len(nxt) != 1 or nxt[0][1] != "D" or "dff" not in m["cells"][nxt[0][0]]["type"] or q1 in outbits:
            bad.append(f"{n}'s first flip-flop drives more than the next flip-flop (a single-flop synchronizer)")
            continue
        if other:                                       # combinational use: CS_N to MISO_OE only
            ok = n == "CS_N"
            seen, todo = set(), [c for c, _p in other]
            while todo and ok:
                c = todo.pop()
                if c in seen:
                    continue
                seen.add(c)
                if "dff" in m["cells"][c]["type"]:
                    ok = False
                    break
                for p, direction in m["cells"][c]["port_directions"].items():
                    if direction != "output":
                        continue
                    for ob in m["cells"][c]["connections"][p]:
                        if ob in outbits and outbits[ob] != "MISO_OE":
                            ok = False
                        todo += [c2 for c2, _p2, _i2 in sinks.get(ob, [])]
            if not ok:
                bad.append(f"{n} reaches logic other than its synchronizer" + (" and MISO_OE" if n == "CS_N" else ""))
                continue
        notes.append(f"{n} through 2 flip-flops" + (" (and MISO_OE's cut)" if other else ""))
    return bad, notes


if __name__ == "__main__":
    sys.exit(main())
