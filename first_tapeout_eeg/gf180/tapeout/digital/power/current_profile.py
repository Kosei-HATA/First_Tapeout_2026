#!/usr/bin/env python3
"""Supply current of the digital macros per MCLK edge, for the chip-level supply-noise
deck (gf180/tapeout/pex/digital_noise.py; written 11/8, the chip version selectable since 11/25).

Sources (tt 25 C 3.3 V), per chip version (REVS):
  r13  the 10/29 power run of the two macros of the 13th chip (run_power.sh: eeg_digital_top f2 and
       eeg_adc_dig f3 in one VCD, build/macros.vcd) -> build/current_profile.json
  r14  the 11/24 power run of the 14th chip's macro (run_power_r14.sh: eeg_digital_top r14f5_20261124,
       build/r14/macro.vcd) -> build/r14/current_profile.json. eeg_adc_dig is the same macro (f3) in
       both chips and is not in this VCD: digital_noise.py takes it from r13's file.
  - OpenSTA's report_power with the gate-level VCD activity (power_<macro>_tt_025C_3v30_vcd.log):
    the totals by group (sequential / combinational / clock, internal / switching).
  - The liberty (tt_025C_3v30): every flip-flop's CLK internal energy on the rising and on the
    falling edge (how the sequential internal power splits between the two edges), and the
    input-pin capacitance of every cell (the SPEF is PIN_CAP NONE: wire only).
  - The final netlist and the nominal SPEF: the clock tree from MCLK (its nets' polarity, so
    which edge charges them) and every net's capacitance (wire + fanout pins).
  - The VCD (1 ms, 32768 cycles, RUN with the host reading the samples): every data net's 0 -> 1
    transitions by the frame cycle (0..31, frame cycle 0 = CMP_STROBE high) in which they happen.

Per macro the result is the charge drawn from VDD (returned to VSS) at each MCLK edge:
  rising edge of frame cycle c:  seq_int * f_rise + clk_int / 2 + clk_sw * f_clk_rise + data[c]
  falling edge:                  seq_int * (1 - f_rise) + clk_int / 2 + clk_sw * (1 - f_clk_rise)
where seq_int, clk_int, clk_sw are OpenSTA's powers / (VDD * f_MCLK), and data[c] distributes
OpenSTA's combinational + sequential-switching power over the frame cycles in proportion to the
VCD's switched capacitance (C_net * VDD per 0 -> 1 transition). Zero-delay simulation: every
data transition is at a rising MCLK edge, glitches are not in it.

usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/power/current_profile.py [--rev r13|r14] [--out FILE]
writes REVS[rev]["out"] (or FILE)
"""
import argparse
import json
import os
import re
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DIG = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
PDK = os.environ.get("PDK_ROOT_D", "/Users/noah/.ciel/ciel/gf180mcu/versions/"
                     "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD")
VDD = 3.3
FMCLK = 32.768e6
NCYC = 32                                    # MCLK cycles per modulator frame
# per chip version: the VCD, the folder of OpenSTA's logs, the output, and each macro's cell library track, LibreLane
# run (final/nl, final/spef/nom) and VCD scope. r13's runs f2 / f3 are archived; their 11/19 reruns have the same
# netlists (sha256 = gf180/tapeout/layout/gds/eeg_*.nl.v) and reproduce the 11/8 file (every charge to the bit; only
# eeg_adc_dig's C_clock_pF rise, a sum over a set, differs in its last digit with the summing order).
REVS = {
    "r13": {"vcd": os.path.join(BUILD, "macros.vcd"), "logs": BUILD, "out": os.path.join(BUILD, "current_profile.json"),
            "macros": {"eeg_digital_top": (9, "eeg_digital_top/runs/f2_rerun_20261119", ("gl_shadow", "g_top")),
                       "eeg_adc_dig": (7, "eeg_adc_dig/runs/f3_rerun_20261119", ("gl_shadow", "g_adc"))}},
    "r14": {"vcd": os.path.join(BUILD, "r14", "macro.vcd"), "logs": os.path.join(BUILD, "r14"),
            "out": os.path.join(BUILD, "r14", "current_profile.json"),
            "macros": {"eeg_digital_top": (9, "eeg_digital_top_r14/runs/r14f5_20261124", ("gl_shadow_r14", "g"))}},
}
BUFS = re.compile(r"__(clk)?buf_\d+$")        # clock-tree cells (CTS uses clkbuf / buf)
INVS = re.compile(r"__(clk)?inv_\d+$")


def liberty(t):
    """{cell: {"pins": {input pin: cap pF}, "clk": (rise pJ, fall pJ) or None}}."""
    path = f"{PDK}/libs.ref/gf180mcu_fd_sc_mcu{t}t5v0/lib/gf180mcu_fd_sc_mcu{t}t5v0__tt_025C_3v30.lib"
    txt = open(path).read()
    heads = [m.start() for m in re.finditer(r"^\s*cell\s*\(", txt, re.M)] + [len(txt)]
    out = {}
    for a, b in zip(heads[:-1], heads[1:]):
        s = txt[a:b]
        name = re.match(r"\s*cell\s*\(\s*\"?([\w]+)\"?\s*\)", s).group(1)
        pins, clk = {}, None
        pheads = [m for m in re.finditer(r"\n\s*pin\s*\(\s*\"?(\w+)\"?\s*\)\s*\{", s)]
        for i, m in enumerate(pheads):
            body = s[m.end(): pheads[i + 1].start() if i + 1 < len(pheads) else len(s)]
            if re.search(r"direction\s*:\s*\"?input", body):
                c = re.search(r"\n\s*capacitance\s*:\s*([-+0-9.eE]+)", body)
                pins[m.group(1)] = float(c.group(1)) if c else 0.0
                if m.group(1) in ("CLK", "CLKN") and "internal_power" in body:
                    def mid(kind):
                        v = []
                        for mm in re.finditer(kind + r"\s*\(\s*\"?\w+\"?\s*\)\s*\{\s*(?:index_1[^;]*;)?\s*values\s*\(\s*\"([^)]*)\)", body):
                            nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", mm.group(1))]
                            v.append(sorted(nums)[len(nums) // 2])
                        return float(np.mean(v)) if v else 0.0
                    clk = (mid("rise_power"), mid("fall_power"))
        out[name] = {"pins": pins, "clk": clk}
    return out


def netlist(path):
    """[(cell, inst, {pin: net})] of the gate-level netlist (escaped names unescaped)."""
    txt = open(path).read()
    insts = []
    for m in re.finditer(r"^\s*(gf180mcu_fd_sc_mcu\w+)\s+(\S+)\s*\((.*?)\);", txt, re.M | re.S):
        conn = {p: n.strip().lstrip("\\").strip() for p, n in re.findall(r"\.(\w+)\s*\(([^()]*)\)", m.group(3))}
        insts.append((m.group(1), m.group(2).lstrip("\\"), conn))
    return insts


def spef(path):
    """{net: wire cap pF}."""
    names, caps = {}, {}
    with open(path) as f:
        sect = None
        for line in f:
            if line.startswith("*NAME_MAP"):
                sect = "map"
                continue
            if sect == "map":
                if line.startswith("*") and not line.startswith("*D_NET") and " " in line.strip():
                    k, v = line.split(None, 1)
                    if k[1:].isdigit():
                        names[k] = v.strip().replace("\\", "")
                        continue
                if line.strip() and not line.startswith("*") or line.startswith("*PORTS") or line.startswith("*D_NET"):
                    sect = None
            if line.startswith("*D_NET"):
                _, k, c = line.split()[:3]
                caps[names.get(k, k)] = float(c)
    return caps


def opensta(macro, logs=BUILD):
    """OpenSTA's tt VCD power groups (W): {(group, kind): value}."""
    out = {}
    for line in open(os.path.join(logs, f"power_{macro}_tt_025C_3v30_vcd.log")):
        m = re.match(r"(Sequential|Combinational|Clock)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", line)
        if m:
            g = m.group(1)
            out[(g, "int")], out[(g, "sw")], out[(g, "leak")] = (float(x) for x in m.groups()[1:])
    return out


def vcd_activity(scope, netcap, path=os.path.join(BUILD, "macros.vcd")):
    """Switched capacitance (pF, 0 -> 1 transitions) of the scope's data nets per MCLK cycle, the
    MCLK rising edges, and the rising edges of TH_CAPTURE (the frame phase) and of CMP_STROBE (where
    the scope has it: a check of that phase). scope: the VCD's scope path, e.g. ("gl_shadow", "g_top")."""
    ids, stack = {}, []
    strobe_rise = []
    with open(path) as f:
        for line in f:
            if line.startswith("$scope"):
                stack.append(line.split()[2])
            elif line.startswith("$upscope"):
                stack.pop()
            elif line.startswith("$var") and stack == list(scope):
                p = line.split()
                w, code, name = int(p[2]), p[3], p[4].lstrip("\\")
                ids.setdefault(code, []).append((name, w))
            elif line.startswith("$enddefinitions"):
                break
        clk = next(c for c, v in ids.items() if any(n == "MCLK" for n, _ in v))
        mark = next((c for c, v in ids.items() if any(n == "TH_CAPTURE" for n, _ in v)), None)
        strobe = next((c for c, v in ids.items() if any(n == "CMP_STROBE" for n, _ in v)), None)
        val = {}
        t = 0
        rises = []                                   # MCLK rising edge times
        mark_rise = []
        events = []                                  # (time, code, new value)
        for line in f:
            if line[0] == "#":
                t = int(line[1:])
                continue
            if line[0] in "01xz":
                code, v = line[1:].strip(), line[0]
            elif line[0] == "b":
                v, code = line[1:].split()
            else:
                continue
            if code == strobe and v == "1" and val.get(code) == "0":     # (its switching stays in the data below)
                strobe_rise.append(t)
            if code == clk:
                if v == "1" and val.get(code) == "0":
                    rises.append(t)
            elif code == mark and v == "1" and val.get(code) == "0":
                mark_rise.append(t)
            elif code in ids:
                events.append((t, code, val.get(code), v))
            val[code] = v
    rises = np.array(rises)
    # per-code capacitance (sum over the names sharing the code; vectors: per bit)
    cap = {}
    for code, lst in ids.items():
        cap[code] = [netcap.get(n if w == 1 else f"{n}[{i}]", netcap.get(n, 0.0)) for n, w in lst for i in range(w)][:max(w for _, w in lst)]
    sw = np.zeros(len(rises))
    for t, code, old, new in events:
        if old is None or code == clk:
            continue
        n = np.searchsorted(rises, t, side="right") - 1     # the cycle that starts at the edge <= t
        if n < 0:
            continue
        c = cap.get(code, [0.0])
        if len(new) == 1 and len(old) == 1:
            if old == "0" and new == "1":
                sw[n] += c[0]
        else:                                        # vector: bitwise 0 -> 1 (MSB first in VCD)
            o, nn = old.rjust(len(new), "0"), new.rjust(len(old), "0")
            for i, (a, b) in enumerate(zip(o[::-1], nn[::-1])):
                if a == "0" and b == "1":
                    sw[n] += c[i] if i < len(c) else (np.mean(c) if c else 0.0)
    return rises, np.array(mark_rise), sw, np.array(strobe_rise)


def main(rev="r13", out_path=None):
    R_ = REVS[rev]
    out = {}
    for macro, (t, run, scope) in R_["macros"].items():
        R = os.path.join(DIG, run, "final")
        lib = liberty(t)
        insts = netlist(os.path.join(R, "nl", f"{macro}.nl.v"))
        wire = spef(os.path.join(R, "spef", "nom", f"{macro}.nom.spef"))
        pincap = defaultdict(float)
        drivers = {}
        for cell, inst, conn in insts:
            for p, n in conn.items():
                if p in lib.get(cell, {}).get("pins", {}):
                    pincap[n] += lib[cell]["pins"][p]
                elif p not in ("VDD", "VSS", "VNW", "VPW"):
                    drivers[n] = (cell, inst, p)
        netcap = {n: wire.get(n, 0.0) + pincap.get(n, 0.0) for n in set(wire) | set(pincap)}
        # clock tree: from MCLK through buffers (and inverters, if any) to the flops' CLK pins
        fan = defaultdict(list)
        for cell, inst, conn in insts:
            if BUFS.search(cell) or INVS.search(cell):
                i = conn.get("I")
                o = conn.get("Z", conn.get("ZN"))
                if i and o:
                    fan[i].append((o, bool(INVS.search(cell))))
        pol, todo = {"MCLK": False}, ["MCLK"]
        while todo:
            n = todo.pop()
            for o, inv in fan.get(n, []):
                if o not in pol:
                    pol[o] = pol[n] ^ inv
                    todo.append(o)
        clk_nets = {n for n in pol if n == "MCLK" or n.startswith("clknet") or n.startswith("clkbuf")}
        c_clk_rise = sum(netcap.get(n, 0.0) for n in clk_nets if not pol[n])
        c_clk_fall = sum(netcap.get(n, 0.0) for n in clk_nets if pol[n])
        # flops' CLK internal energy split between the edges (counted over the instances)
        er = ef = 0.0
        nff = 0
        for cell, inst, conn in insts:
            ck = lib.get(cell, {}).get("clk")
            if ck and "CLK" in conn:
                er, ef, nff = er + ck[0], ef + ck[1], nff + 1
        f_rise = er / (er + ef) if er + ef else 0.5
        P = opensta(macro, R_["logs"])
        q = lambda w: w / (VDD * FMCLK)                     # W -> C per MCLK cycle
        seq_int, clk_int, clk_sw = q(P[("Sequential", "int")]), q(P[("Clock", "int")]), q(P[("Clock", "sw")])
        data_tot = q(P[("Combinational", "int")] + P[("Combinational", "sw")] + P[("Sequential", "sw")])
        # VCD: switched capacitance per frame cycle (clock nets excluded)
        netcap_data = {n: c for n, c in netcap.items() if n not in clk_nets}
        rises, marks, sw, strobes = vcd_activity(scope, netcap_data, R_["vcd"])
        # frame phase: TH_CAPTURE rises at the edge that starts frame cycle MARK_CYCLE
        n_mark = np.searchsorted(rises, marks, side="right") - 1
        ph = int(np.bincount(n_mark % NCYC).argmax())
        cyc = (np.arange(len(rises)) - ph + MARK_CYCLE) % NCYC
        if len(strobes):                                    # frame cycle 0 = CMP_STROBE high
            n_s = np.searchsorted(rises, strobes, side="right") - 1
            c_s = np.bincount(cyc[n_s[n_s >= 0]], minlength=NCYC)
            assert c_s.argmax() == 0 and c_s.sum() == c_s[0], f"{macro}: CMP_STROBE rises in frame cycles {c_s}"
        per_c = np.array([sw[cyc == c].mean() for c in range(NCYC)])
        data = data_tot * per_c / per_c.sum() * NCYC if per_c.sum() else np.full(NCYC, data_tot / NCYC)
        f_clk_rise = c_clk_rise / (c_clk_rise + c_clk_fall) if c_clk_rise + c_clk_fall else 1.0
        q_rise = seq_int * f_rise + clk_int / 2 + clk_sw * f_clk_rise + data
        q_fall = seq_int * (1 - f_rise) + clk_int / 2 + clk_sw * (1 - f_clk_rise)
        out[macro] = {
            "opensta_W": {f"{g}_{k}": v for (g, k), v in P.items()},
            "flops": nff, "f_seq_rise": f_rise, "clk_nets": len(clk_nets),
            "C_clock_pF": {"rise": c_clk_rise, "fall": c_clk_fall,
                           "from_opensta": P[("Clock", "sw")] / (VDD ** 2 * FMCLK) * 1e12},
            "vcd_cycles": int(len(rises)), "switched_pF_per_cycle": float(sw.mean()),
            "data_pattern_pF": per_c.tolist(),
            "q_rise_pC": (q_rise * 1e12).tolist(), "q_fall_pC": float(q_fall * 1e12),
            "I_avg_mA": float((q_rise.mean() + q_fall) * FMCLK * 1e3),
        }
        o = out[macro]
        print(f"{macro}: {nff} flops (CLK energy rise share {f_rise:.3f}), {len(clk_nets)} clock nets "
              f"(C rise {c_clk_rise:.2f} pF, fall {c_clk_fall:.2f} pF; OpenSTA's clock switching = "
              f"{o['C_clock_pF']['from_opensta']:.2f} pF)")
        print(f"   VCD {len(rises)} cycles, data switched {sw.mean():.3f} pF/cycle; per frame cycle (pF): "
              + " ".join(f"{x:.2f}" for x in per_c))
        print(f"   charge per edge: rising {q_rise.min()*1e12:.1f}..{q_rise.max()*1e12:.1f} pC "
              f"(mean {q_rise.mean()*1e12:.1f}), falling {q_fall*1e12:.1f} pC; mean current {o['I_avg_mA']:.3f} mA"
              + (f"; CMP_STROBE rises {len(strobes)} times, all in frame cycle 0" if len(strobes) else ""))
    out_path = out_path or R_["out"]
    json.dump(out, open(out_path, "w"), indent=1)
    print("wrote", out_path)


MARK_CYCLE = 1          # TH_CAPTURE is high in frame cycle 1 (eeg_adc_dig samples TH at e2)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rev", default="r13", choices=tuple(REVS), help="the chip version (default r13)")
    ap.add_argument("--out", default=None, help="write here instead of the version's file")
    a = ap.parse_args()
    main(a.rev, a.out)
