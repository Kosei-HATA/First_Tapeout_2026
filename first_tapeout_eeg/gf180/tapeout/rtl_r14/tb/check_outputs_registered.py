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
              tree's delay, later than the blanking flip-flop's clock-to-Q at the same edge, so at that edge the OR
              changes once. The exception (requirements NFR-06; audit round 26, auditor A): that SOFT_RESET committed
              at cycle 29 before a window clears the copy at e30 + d and the window starts at e31, a low of about
              1 MCLK - d; harmless, as AFE_RST rises in the same reset (the test mode only; the RTL is unchanged)
  MISO_OE     combinational, as in r13 (NFR-06)
For CHOP_EN and CHOP_BLANK every input of that one gate must itself come from a flip-flop.

Also the synchronizers of the asynchronous inputs (audit round 9, auditor C: single-flop synchronizers passed every
functional test; their metastability cannot be simulated):
  RESET_N   only the asynchronous resets of a 2-flop release chain: the first flop takes the constant 1, the second
            the first's output, and the first's output goes nowhere else (the second's output is the reset used)
  CS_N, SCLK, MOSI   each feeds exactly one first flop, whose output feeds only the next flop (logic sees the second
            flop or later); CS_N also goes, combinationally, to MISO_OE only (its cut at the CS_N rise, as in r13)

And the resets (audit round 12, auditor C: an eeg_regs whose reset was synchronous passed every functional test, as
every bench held RESET_N across MCLK edges; RST-01 asks for an asynchronous one): every flip-flop has an asynchronous,
active-low reset ($adff, $adffe), from RESET_N (the release chain's 2 flops only), from the release chain's output
(the timing and data path), or from a flop reset by that output (the control reset of SOFT_RESET, used only as a
reset); the only storage without a reset is the FIFO's memory (its words are read only below the level).

And one clock (RST-05; audit round 27, auditor C: a CHOP1 divider clocked by a frame-counter bit and a SEQ counter
on the falling edge of the CIC's strobe passed all 16 groups with the counts unchanged, and Verilator said nothing):
every flip-flop and every memory write port takes MCLK's rising edge (CLK the MCLK port bit, CLK_POLARITY 1).

And r14's fixed parameters (audit round 33, auditor A: DAC_LOAD_CYCLE was documented "legal range 2..31", while the
tick placement, fsm_spec.TIMING's busy cycles and the ADC loop's excess loop delay assume 2, and nothing compared them):
the DAC_LOAD_CYCLE defaults of eeg_digital_top (the synthesized value) and eeg_clkgen, eeg_digital_top's pass-through
to eeg_clkgen, and the instantiation value of every bench the r14 groups compile (rtl_r14/tb and the rtl/tb benches
run_tests_r14.sh names; audit round 34, auditor C: only rtl_r14/tb was scanned) equal fsm_spec.TIMING's
dac_load_cycle, but for PARAM_EXEMPT: tb_clkgen's dut_b at 7, the clock generator's own parameter test. Every
instantiation of eeg_digital_top and eeg_clkgen in those benches is read (comments and strings left out; a named
value with any spacing, the module's default, a positional override or a defparam is a fault) and their number
equals PARAM_INSTANCES_RECORDED (audit round 35, auditor C: the scan matched only ".DAC_LOAD_CYCLE(" without a space
and compared its count with nothing); the scan's own self-test edits the benches' texts six ways, each a fault.

Exit: 0 every output a flip-flop's (PASS), 1 an output that is not, or yosys rejects the design (FAIL; audit round
28, auditor C: a latch from an always_comb, which yosys stops at, was reported as TOOL ERROR, so the mutation runner
could never call it detected), 2 yosys is missing or did not end normally (TOOL ERROR).
Usage: check_outputs_registered.py [rtl_r14 directory]   (default: this one; the mutation runner passes its copy,
       which also holds the blocks kept from rtl/)
"""
import json
import os
import re
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
FSM_NOT_RECODED = ("u_seq.state", "u_spi.st")          # (* fsm_encoding = "none" *) in the RTL (NFR-05)


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
            err = next((ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("ERROR")), "")
            if r.returncode > 0 and err and "Can't open" not in err:   # yosys ran and refused the design
                print("FAIL: yosys rejects the design: " + err[:200])
                return 1
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
    rbad, rnote = check_resets(m)
    print("resets: " + rnote)
    cbad, cnote = check_clocks(m)
    print("clocks: " + cnote)
    # NFR-05 through synthesis (audit round 14, auditor A: the illegal codes' recovery survived only because yosys judged
    # recoding of no benefit; a recoded FSM drops the unreachable codes 9..15 and the FRAME_ERR of the SPI's illegal codes)
    fbad = []                                           # (audit round 15, auditor C: named in the log and the summary)
    for net in FSM_NOT_RECODED:
        a = m["netnames"].get(net, {}).get("attributes", {})
        if a.get("fsm_encoding") != "none":
            fbad.append(f"{net}: fsm_encoding {a.get('fsm_encoding')!r}, not \"none\" (synthesis may recode the state "
                        f"and drop the illegal codes' recovery, NFR-05)")
    print("state registers: " + (f"{', '.join(FSM_NOT_RECODED)} keep fsm_encoding \"none\" (NFR-05 through synthesis)"
                                 if not fbad else f"{len(fbad)} of {len(FSM_NOT_RECODED)} open to recoding"))
    pbad, pnote = check_parameters(d)
    print("parameters: " + pnote)
    sbad_, snote_ = param_selftest()
    print("parameter scan self-test: " + snote_)
    pbad += sbad_
    for x in bad + sbad + rbad + cbad + fbad + pbad:
        print("  " + x)
    if bad or sbad or rbad or cbad or fbad or pbad:
        print(f"FAIL: {len(bad)} output bits not from a register, {len(sbad)} synchronizer faults, {len(rbad)} reset faults, "
              f"{len(cbad)} clock faults, {len(fbad)} state registers open to recoding, {len(pbad)} parameter faults")
    else:
        print("PASS: every output is a register's (NFR-06); every asynchronous input passes 2 flip-flops; every flip-flop "
              "resets asynchronously from the RESET_N release (RST-01); every flip-flop and memory write port on MCLK's "
              "rising edge (RST-05); the state registers keep fsm_encoding \"none\" (NFR-05); DAC_LOAD_CYCLE as "
              "fsm_spec.TIMING")
    return 1 if bad or sbad or rbad or cbad or fbad or pbad else 0


# the one bench instance at another DAC_LOAD_CYCLE on purpose (path from gf180/tapeout, instance): tb_clkgen's second
# clock generator, at 7, shows the DAC strobe following the parameter (audit round 34, auditor C)
PARAM_EXEMPT = {("rtl/tb/tb_clkgen.sv", "dut_b")}


def check_parameters(d):
    """r14's fixed parameters (audit round 33, auditor A): DAC_LOAD_CYCLE's defaults in eeg_digital_top (the value
    synthesized) and eeg_clkgen, eeg_digital_top's pass-through to eeg_clkgen, and the instantiation value of every
    bench the r14 groups compile against fsm_spec.TIMING's dac_load_cycle: rtl_r14/tb and the rtl/tb benches
    run_tests_r14.sh names (audit round 34, auditor C: only rtl_r14/tb was scanned, while tb_clkgen and tb_chop1 come
    from rtl/tb), but for PARAM_EXEMPT (an exemption whose instance is gone is a fault). d: the RTL directory checked
    (the benches are this checkout's)."""
    sys.path.insert(0, SPEC)
    import fsm_spec as FSP
    want, bad, seen = FSP.TIMING["dac_load_cycle"], [], []
    for f in ("eeg_digital_top.sv", "eeg_clkgen.sv"):
        vals = [int(v) for v in re.findall(r"parameter\s+int\s+DAC_LOAD_CYCLE\s*=\s*(\d+)",
                                           open(os.path.join(d, f), encoding="utf-8").read())]
        seen.append(f"{f} {vals}")
        if vals != [want]:
            bad.append(f"{f}: DAC_LOAD_CYCLE default {vals}, fsm_spec.TIMING's dac_load_cycle {want}")
    top = open(os.path.join(d, "eeg_digital_top.sv"), encoding="utf-8").read()
    if not re.search(r"eeg_clkgen\s*#\(\s*\.DAC_LOAD_CYCLE\(\s*DAC_LOAD_CYCLE\s*\)\s*\)", top):
        bad.append("eeg_digital_top.sv: eeg_clkgen is not given eeg_digital_top's DAC_LOAD_CYCLE")
    bbad, bnote = check_bench_parameters(bench_texts(), want)
    bad += bbad
    return bad, (f"DAC_LOAD_CYCLE {want} (fsm_spec.TIMING) in " + ", ".join(seen) + " and " + bnote
                 + ("" if not bad else f"; {len(bad)} faults"))


# the instantiations of eeg_digital_top and eeg_clkgen in the benches the r14 groups compile, by directory (audit round
# 35, auditor C): a scan finding another number is a fault
PARAM_INSTANCES_RECORDED = {"rtl/tb": 3, "rtl_r14/tb": 3}
PARAM_MODULES = ("eeg_digital_top", "eeg_clkgen")


def bench_texts():
    """{path from gf180/tapeout: text} of the benches the r14 groups compile: rtl_r14/tb and the rtl/tb ones
    run_tests_r14.sh names."""
    tapeout = os.path.normpath(os.path.join(HERE, "..", ".."))
    script = open(os.path.join(HERE, "..", "run_tests_r14.sh"), encoding="utf-8").read()
    paths = [os.path.join(HERE, f) for f in sorted(os.listdir(HERE)) if f.endswith(".sv")]
    paths += [os.path.join(tapeout, "rtl", "tb", f) for f in sorted(set(re.findall(r"\.\./rtl/tb/(\w+\.sv)", script)))]
    return {os.path.relpath(p, tapeout): open(p, encoding="utf-8").read() for p in paths}


def _strip_sv(txt):
    """The text without comments and string literals (their words are no instantiations)."""
    txt = re.sub(r"/\*.*?\*/", " ", txt, flags=re.S)
    txt = re.sub(r"//[^\n]*", " ", txt)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', txt)


def _paren(txt, i):
    """(the text inside the parentheses opening at txt[i], the index after the closing one)"""
    depth = 0
    for j in range(i, len(txt)):
        depth += (txt[j] == "(") - (txt[j] == ")")
        if depth == 0:
            return txt[i + 1:j], j + 1
    raise ValueError("unbalanced parentheses")


def bench_instances(txt):
    """[(module, instance, {parameter: value} or None)] of eeg_digital_top and eeg_clkgen in a bench's text (None: a
    positional override or one the scan cannot read), and whether the text has a defparam of DAC_LOAD_CYCLE."""
    t = _strip_sv(txt)
    out = []
    for m in re.finditer(r"\b(" + "|".join(PARAM_MODULES) + r")\b", t):
        j, params = m.end(), {}
        k = re.match(r"\s*#\s*", t[j:])
        if k:
            j += k.end()
            if j >= len(t) or t[j] != "(":
                out.append((m.group(1), "?", None))
                continue
            inner, j = _paren(t, j)
            for item in [x.strip() for x in re.split(r",(?![^()]*\))", inner) if x.strip()]:
                mm = re.fullmatch(r"\.\s*(\w+)\s*\(\s*(.*?)\s*\)", item, flags=re.S)
                if not mm:
                    params = None
                    break
                params[mm.group(1)] = mm.group(2)
        mi = re.match(r"\s*(\w+)\s*\(", t[j:])
        if mi:
            out.append((m.group(1), mi.group(1), params))
    return out, bool(re.search(r"\bdefparam\b[^;]*\bDAC_LOAD_CYCLE\b", t))


def check_bench_parameters(texts, want):
    """(faults, note) for DAC_LOAD_CYCLE in the benches' texts: every instantiation at want by name or at the module's
    default (checked against TIMING above), but for PARAM_EXEMPT; no positional override, no defparam; their number
    by directory equal to PARAM_INSTANCES_RECORDED (audit rounds 34, 35, auditor C)."""
    bad, n_dir, n_named, n_default, found = [], {}, 0, 0, set()
    for rel, txt in sorted(texts.items()):
        insts, has_defparam = bench_instances(txt)
        if has_defparam:
            bad.append(f"{rel}: a defparam of DAC_LOAD_CYCLE (name the value in the instantiation)")
        for mod, inst, params in insts:
            key = os.path.dirname(rel)
            n_dir[key] = n_dir.get(key, 0) + 1
            if (rel, inst) in PARAM_EXEMPT:
                found.add((rel, inst))
                continue
            if params is None:
                bad.append(f"{rel}: {inst} ({mod}) overrides its parameters by position or in a form the scan cannot "
                           f"read (name DAC_LOAD_CYCLE)")
                continue
            v = params.get("DAC_LOAD_CYCLE")
            if v is None:
                n_default += 1
            elif v != str(want):
                bad.append(f"{rel}: {inst} ({mod}) instantiated with DAC_LOAD_CYCLE {v}, fsm_spec.TIMING's "
                           f"dac_load_cycle {want}")
            else:
                n_named += 1
    for rel, inst in sorted(PARAM_EXEMPT - found):
        bad.append(f"{rel}: the exempted instance {inst} (PARAM_EXEMPT) is not there")
    if n_dir != PARAM_INSTANCES_RECORDED:
        bad.append(f"the r14 groups' benches instantiate {' and '.join(PARAM_MODULES)} {n_dir} times by directory, "
                   f"PARAM_INSTANCES_RECORDED holds {PARAM_INSTANCES_RECORDED}")
    note = (f"{sum(n_dir.values())} bench instantiations of the r14 groups (" + ", ".join(f"{k} {v}" for k, v in sorted(n_dir.items()))
            + (", as recorded" if n_dir == PARAM_INSTANCES_RECORDED else ", NOT as recorded")
            + f"; {n_named} at {want} by name, {n_default} at the default; {len(found)} exempted: "
            + ", ".join(f"{r} {i}" for r, i in sorted(found)) + ")")
    return bad, note


def param_selftest():
    """The bench scan's own mutation test (audit round 35, auditor C): the clean texts give no fault and each edit of
    them gives one: (faults, note)."""
    sys.path.insert(0, SPEC)
    import fsm_spec as FSP
    want = FSP.TIMING["dac_load_cycle"]
    base = bench_texts()
    c1, c2 = "rtl/tb/tb_chop1.sv", "rtl/tb/tb_clkgen.sv"
    line = f"eeg_clkgen #(.DAC_LOAD_CYCLE({want})) u_clkgen ("
    edits = [("a space before the value's parenthesis", c1, line, "eeg_clkgen #(.DAC_LOAD_CYCLE (7)) u_clkgen ("),
             ("a positional override", c1, line, "eeg_clkgen #(7) u_clkgen ("),
             ("a defparam", c1, "endmodule", "defparam u_clkgen.DAC_LOAD_CYCLE = 7;\nendmodule"),
             ("an instantiation more (at the default)", c1, line, "eeg_clkgen u_more ();\n    " + line),
             ("the exempted instance renamed", c2, "eeg_clkgen #(.DAC_LOAD_CYCLE(7)) dut_b (",
              "eeg_clkgen #(.DAC_LOAD_CYCLE(7)) dut_c ("),
             ("a value of 7 by name", c1, line, "eeg_clkgen #( .DAC_LOAD_CYCLE( 7 ) ) u_clkgen (")]
    bad = []
    b0, _ = check_bench_parameters(base, want)
    if b0:
        bad.append(f"the parameter scan's self-test: the clean benches give {b0}")
    missed = []
    for name, rel, old, new in edits:
        if rel not in base or base[rel].count(old) < 1:
            bad.append(f"the parameter scan's self-test: the edit '{name}' does not apply to {rel}")
            continue
        t = dict(base)
        t[rel] = t[rel].replace(old, new, 1)
        if not check_bench_parameters(t, want)[0]:
            missed.append(name)
    bad += [f"the parameter scan's self-test: the edit '{n}' gives no fault" for n in missed]
    return bad, f"{len(edits) - len(missed)} of {len(edits)} edits of the benches' texts give a fault" + ("" if not b0 else ", the clean ones too")


def check_clocks(m):
    """RST-05, one clock: every flip-flop and every memory write port on MCLK's rising edge (audit round 27, auditor C).
    Yosys gives CLK and CLK_POLARITY on the flip-flops and $memwr_v2, WR_CLK, WR_CLK_ENABLE and WR_CLK_POLARITY per
    port on $mem_v2; a latch (no clock) is reported by check_resets."""
    mclk = m["ports"]["MCLK"]["bits"][0]
    names = {}
    for n, v in m["netnames"].items():
        for i, b in enumerate(v["bits"]):
            if isinstance(b, int):
                names.setdefault(b, f"{n}[{i}]" if len(v["bits"]) > 1 else n)
    bits = lambda v: [int(c) for c in reversed(str(v))] if isinstance(v, str) else [(int(v) >> k) & 1 for k in range(64)]
    bad, nff, nwr = [], 0, 0
    for cn, c in m["cells"].items():
        t, cc, p = c["type"], c["connections"], c["parameters"]
        if "dff" in t:
            nff += 1
            q = cc.get("Q", [None])[0]
            who = names.get(q, cn) if isinstance(q, int) else cn
            pol = bits(p.get("CLK_POLARITY", "1"))[0]
            if cc.get("CLK", [None])[0] != mclk or pol != 1:
                clk = cc.get("CLK", [None])[0]
                bad.append(f"{who} ({t}): clocked by {names.get(clk, clk)}{'' if pol == 1 else ' (falling edge)'}, "
                           f"not MCLK's rising edge (RST-05)")
        elif t.startswith("$memwr"):
            nwr += 1
            pol, en = bits(p.get("CLK_POLARITY", "1"))[0], bits(p.get("CLK_ENABLE", "1"))[0]
            if cc.get("CLK", [None])[0] != mclk or pol != 1 or en != 1:
                bad.append(f"{cn}: a memory write port not on MCLK's rising edge (RST-05)")
        elif t in ("$mem", "$mem_v2"):
            k = int(str(p.get("WR_PORTS", "0")), 2) if isinstance(p.get("WR_PORTS"), str) else int(p.get("WR_PORTS", 0))
            clks, pols, ens = cc.get("WR_CLK", []), bits(p.get("WR_CLK_POLARITY", "0")), bits(p.get("WR_CLK_ENABLE", "0"))
            for j in range(k):
                nwr += 1
                if j >= len(clks) or clks[j] != mclk or pols[j] != 1 or ens[j] != 1:
                    bad.append(f"{cn}: write port {j} not on MCLK's rising edge (RST-05)")
    if nwr == 0:
        bad.append("no memory write port seen (the FIFO's memory writes on MCLK): the clock check saw no memory")
    return bad, (f"{nff} flip-flop cells and {nwr} memory write port(s), all on MCLK's rising edge" if not bad else
                 f"{len(bad)} faults")


def check_resets(m):
    """Every flip-flop resets asynchronously (active low) from RESET_N's release chain, directly or through the control
    reset's flop; no other storage than the FIFO's memory (audit round 12)."""
    names = {}
    for n, v in m["netnames"].items():
        for i, b in enumerate(v["bits"]):
            if isinstance(b, int):
                names.setdefault(b, f"{n}[{i}]" if len(v["bits"]) > 1 else n)
    rn = m["ports"]["RESET_N"]["bits"][0]
    ffs = {cn: c for cn, c in m["cells"].items() if "dff" in c["type"] or "latch" in c["type"]}
    # the storage cells that are not flip-flops (audit round 26, auditor C: this list was named "other", a name the
    # control-reset loop below reused, so the check at the end walked an empty list and never saw a memory)
    mems = [cn for cn, c in m["cells"].items() if c["type"].startswith(("$mem", "$sr", "$aldff"))]
    fifo_mems = [cn for cn in mems if cn.startswith("$flatten\\u_fifo.")]
    bad, nbits = [], 0
    arst_of = lambda c: c["connections"]["ARST"][0] if "ARST" in c["connections"] else None
    chain = [cn for cn, c in ffs.items() if arst_of(c) == rn]          # RESET_N's release chain (checked above)
    # the release chain's output: the bit whose D is not the constant 1 (the second flop)
    q_chain = {c["connections"]["Q"][i] for cn, c in ffs.items() if cn in chain
               for i, d in enumerate(c["connections"]["D"]) if d != "1"}
    if len(q_chain) != 1:
        bad.append(f"RESET_N's release chain has {len(q_chain)} output bits, expected 1")
    outbits = {b for pp in m["ports"].values() if pp["direction"] == "output" for b in pp["bits"] if isinstance(b, int)}
    uses = {}                                          # bit -> the input ports it reaches
    for cc in m["cells"].values():
        for pn, bb in cc["connections"].items():
            if cc["port_directions"][pn] == "input":
                for b in bb:
                    if isinstance(b, int):
                        uses.setdefault(b, []).append(pn)
    # the control reset (SOFT_RESET's): a 1-bit flop reset by the release chain whose output is the asynchronous reset
    # of other flops, and nothing else (a synchronous use, e.g. a block reset synchronously, is reported as such)
    ctrl = {c["connections"]["Q"][0] for cn, c in ffs.items() if arst_of(c) in q_chain and len(c["connections"]["Q"]) == 1
            and "ARST" in uses.get(c["connections"]["Q"][0], [])}
    for q in sorted(ctrl):
        other = sorted({pn for pn in uses[q] if pn != "ARST"})
        if other or q in outbits:
            bad.append(f"{names.get(q, q)}: the control reset also reaches {other or ['an output']} "
                       f"(only asynchronous resets may use it)")
    allowed = q_chain | ctrl
    for cn, c in ffs.items():
        w = len(c["connections"].get("Q", []))
        nbits += w
        if cn in chain:
            continue
        q = c["connections"].get("Q", [None])[0]
        who = names.get(q, cn) if isinstance(q, int) else cn
        if c["type"] not in ("$adff", "$adffe"):
            bad.append(f"{who} ({w} bits): {c['type']}, not a flip-flop with an asynchronous reset")
        elif str(c["parameters"].get("ARST_POLARITY", "")).strip("0") != "":
            bad.append(f"{who} ({w} bits): an active-high asynchronous reset")
        elif arst_of(c) not in allowed:
            bad.append(f"{who} ({w} bits): reset from {names.get(arst_of(c), arst_of(c))}, not from RESET_N's release")
    for cn in mems:
        if cn not in fifo_mems:
            bad.append(f"{cn}: storage without a reset outside the FIFO's memory")
    if not fifo_mems:                                  # the check saw the memory it exempts (audit round 26)
        bad.append("the FIFO's memory not found among the storage cells: the storage check saw no memory")
    return bad, (f"{nbits} flip-flop bits, all with an asynchronous reset from RESET_N's release ("
                 f"{len(ctrl)} control-reset flop); the FIFO's memory ({len(fifo_mems)} memory cells) without one" if not bad else
            f"{len(bad)} faults")


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
