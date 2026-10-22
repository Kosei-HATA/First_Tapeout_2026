#!/usr/bin/env python3
"""Checks of the DAC1 array eeg_dac1 (gf180/tapeout/adc/eeg_dac1.spice: 31 steered
cells, common-break drive), tracker B3/B6.

Frames of 1/1.024 MHz; SEL changes 0.5 ns after e3, DAC_CLK is high in cycle 4 (as
eeg_digital_top). Outputs at ideal virtual grounds (VCM -+ voff/2), references at
VCM +- 0.25 V.

  even   charge error per toggle that does not depend on its direction (ISI), from
         two runs with the same frames on and off but twice the toggles (pattern
         totals, so the break that every cell takes every frame drops out):
         one cell toggling (the others half on, half off), or all 31 toggling.
         Requirement 0.016 fC per toggle for all elements erring alike
         (gf180/sim/dac1_cell/run_cell.py; behavioral 107.5 dB at 1e-5 of the
         element charge 2 Iu T)
  ref    reference charge per frame for steady codes and for toggling codes:
         VRP current over a frame minus its static value, per toggle
  brk    BRK width, BRK rise to D / DB fall of a cell (both directions)

Usage: python3 dac1_check.py [--corner typical] [--temp 27] [--voff 0] [--mc seeds]
       [--tests even ref brk] [--tol A|B|C]
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
DAC1 = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_dac1.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
VDD, VCM = 3.3, 1.65
T = 1 / 1.024e6
TM = T / 32
T0 = 2e-6
TOLS = {  # as gf180/sim/dac2_cell/run_cell.py
    "A": "method=gear maxord=2 reltol=1e-5 abstol=1e-13 vntol=1e-7 chgtol=1e-17",
    "B": "method=trap reltol=1e-5 abstol=1e-13 vntol=1e-7 chgtol=1e-17",
    "C": "method=gear maxord=2 reltol=1e-6 abstol=1e-12 vntol=1e-6 chgtol=1e-16",
}
RES_CORNER = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff", "sf": "res_typical",
              "fs": "res_typical"}


def sel_pwl(bits, tr=0.5e-9):
    """SEL level per frame, changing 0.5 ns after e3 of the frame"""
    pts = [(0.0, VDD * bits[0])]
    for k in range(1, len(bits)):
        if bits[k] != bits[k - 1]:
            t = T0 + k * T + 3 * TM + 0.5e-9
            pts += [(t, VDD * bits[k - 1]), (t + tr, VDD * bits[k])]
    return " ".join(f"{t:.12e} {v:g}" for t, v in pts)


def deck(o, sels, nframes, seed, save):
    """sels: 31 per-frame bit lists"""
    dclk = f"PULSE(0 {VDD} {T0 + 4 * TM:.10e} 0.3n 0.3n {TM - 0.3e-9:.10e} {T:.10e})"
    srcs = "\n".join(f"VS{i} SEL{i} 0 PWL({sel_pwl(b)})" if len(set(b)) > 1 else f"VS{i} SEL{i} 0 {VDD * b[0]:g}"
                     for i, b in enumerate(sels))
    sel_nodes = " ".join(f"SEL{i}" for i in range(31))
    return f"""* eeg_dac1 check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {o.corner}
.lib {PDK}/sm141064.ngspice {RES_CORNER[o.corner]}
.param sw_stat_mismatch={1 if seed else 0}
.include {DAC1}
.temp {o.temp}
.options sparse {TOLS[o.tol]} seed={seed or 1}
VDD VDD 0 {VDD}
VRP VRP 0 {VCM + 0.25}
VRN VRN 0 {VCM - 0.25}
VOP OUTP 0 {VCM - o.voff * 1e-3 / 2}
VON OUTN 0 {VCM + o.voff * 1e-3 / 2}
VDCLK DAC_CLK 0 {dclk}
{srcs}
XD OUTP OUTN VRP VRN {sel_nodes} DAC_CLK VDD 0 eeg_dac1
.control
set noaskquit
tran 0.05n {T0 + nframes * T:.9e} 0 0.5n
wrdata tr.csv {save}
quit
.endc
.end
"""


def run(o, name, sels, nframes, seed=0, save="i(vop) i(von) i(vrp)"):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(o, sels, nframes, seed, save))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    os.remove(os.path.join(d, "tr.csv"))
    return x


def integ(t, i, a, b):
    m = (t >= a) & (t <= b)
    return np.trapezoid(i[m], t[m])


def even(o, seed=0):
    """even error per toggle: one cell, and all 31 cells"""
    lead, tail = [0] * 4, [0] * 4
    p1 = lead + [0, 1] * 32 + tail
    p2 = lead + [0, 0, 1, 1] * 16 + tail
    nf = len(p1)
    tog = lambda p: sum(p[k] != p[k - 1] for k in range(1, len(p)))
    static = [[1] * nf if i < 15 else [0] * nf for i in range(31)]  # 15 on, 16 off (cell 0 varies)
    jobs = [("one", [p1] + static[1:], [p2] + static[1:], 1), ("all", [p1] * 31, [p2] * 31, 31)]

    def q_of(args):
        tag, k, s = args
        x = run(o, f"even_{tag}{k}_{o.corner}{o.temp:g}_v{o.voff:g}_s{seed}", s, nf, seed)
        t, idiff = x[:, 0], x[:, 1] - x[:, 3]
        # from the DAC update of the first pattern frame to the end of the last one
        return integ(t, idiff, T0 + 4 * T + 4 * TM, T0 + (nf - 2) * T + 4 * TM)
    runs = [(tag, k, s) for tag, s1, s2, _ in jobs for k, s in enumerate((s1, s2))]
    with ThreadPoolExecutor(1 if seed else 4) as ex:
        q = list(ex.map(q_of, runs))
    return {tag: (q[2 * j] - q[2 * j + 1]) / ((tog(p1) - tog(p2)) * ncell)
            for j, (tag, _, _, ncell) in enumerate(jobs)}


def ref(o):
    """reference charge per frame: steady codes, then a rotating (DWA-like) code"""
    nf = 12
    out = {}
    for k in (0, 8, 15, 23, 31):
        sels = [[1] * nf if i < k else [0] * nf for i in range(31)]
        x = run(o, f"ref_k{k}_{o.corner}{o.temp:g}", sels, nf)
        t, ivrp = x[:, 0], -x[:, 5]
        out[f"VRP current, steady k = {k} (uA)"] = integ(t, ivrp, T0 + 6 * T, T0 + 10 * T) / (4 * T) * 1e6
    # rotation: k = 15 elements on, the window advancing by 15 every frame (DWA at code 15)
    sels = [[0] * nf for _ in range(31)]
    p = 0
    for f in range(nf):
        for j in range(15):
            sels[(p + j) % 31][f] = 1
        p = (p + 15) % 31
    x = run(o, f"ref_rot_{o.corner}{o.temp:g}", sels, nf)
    t, ivrp = x[:, 0], -x[:, 5]
    tog = sum(sum(sels[i][f] != sels[i][f - 1] for i in range(31)) for f in range(7, 11))
    q_rot = integ(t, ivrp, T0 + 6 * T + 4 * TM, T0 + 10 * T + 4 * TM)
    q_st = out["VRP current, steady k = 15 (uA)"] * 1e-6 * 4 * T
    out["rotating k = 15: toggles per frame"] = tog / 4
    out["extra VRP charge per toggle (fC)"] = (q_rot - q_st) / tog * 1e15
    return out


def brk(o):
    nf = 6
    bits = [0, 0, 1, 0, 1, 0]
    sels = [bits] + [[1] * nf if i < 15 else [0] * nf for i in range(1, 31)]
    x = run(o, f"brk_{o.corner}{o.temp:g}", sels, nf,
            save="v(xd.brk) v(xd.xc0.d) v(xd.xc0.db) v(xd.brkl) v(xd.xc0.q) v(xd.xc0.qb)")
    t, b, dd, ddb, bl, q, qb = x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7], x[:, 9], x[:, 11]

    def cross(v, lvl, rising, after):
        m = t > after
        tt, vv = t[m], v[m]
        s = (vv[:-1] < lvl) & (vv[1:] >= lvl) if rising else (vv[:-1] > lvl) & (vv[1:] <= lvl)
        i = np.flatnonzero(s)
        if not i.size:
            return float("nan")
        i = i[0]
        return tt[i] + (lvl - vv[i]) * (tt[i + 1] - tt[i]) / (vv[i + 1] - vv[i])
    out = {}
    e2 = T0 + 2 * T + 4 * TM  # 0 -> 1 in frame 2 (DB was on)
    e3 = T0 + 3 * T + 4 * TM  # 1 -> 0 in frame 3 (D was on)
    b2 = cross(b, VDD / 2, True, e2 - 1e-9)
    out["BRK width (ns)"] = (cross(b, VDD / 2, False, b2) - b2) * 1e9
    out["DAC_CLK to BRK 50 % (ns)"] = (b2 - e2) * 1e9
    out["BRK to DB fall, 0 -> 1 (ns)"] = (cross(ddb, VDD / 2, False, e2 - 1e-9) - b2) * 1e9
    b3 = cross(b, VDD / 2, True, e3 - 1e-9)
    out["BRK to D fall, 1 -> 0 (ns)"] = (cross(dd, VDD / 2, False, e3 - 1e-9) - b3) * 1e9
    out["D rise after BRK fall, 0 -> 1 (ns)"] = (cross(dd, VDD / 2, True, e2 - 1e-9)
                                                 - cross(b, VDD / 2, False, b2)) * 1e9
    # the latch may only move after every switch is off, and must be settled at the end
    out["BRK rise to BRKL rise (ns)"] = (cross(bl, VDD / 2, True, e2 - 1e-9) - b2) * 1e9
    out["BRK rise to Q rise, 0 -> 1 (ns)"] = (cross(q, VDD / 2, True, e2 - 1e-9) - b2) * 1e9
    out["BRK rise to QB rise, 1 -> 0 (ns)"] = (cross(qb, VDD / 2, True, e3 - 1e-9) - b3) * 1e9
    out["BRKL fall to BRK fall (ns)"] = (cross(b, VDD / 2, False, b2) - cross(bl, VDD / 2, False, b2)) * 1e9
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--voff", type=float, default=0.0, help="OUTN - OUTP (mV)")
    ap.add_argument("--mc", type=int, default=0)
    ap.add_argument("--tests", nargs="+", default=["even", "ref", "brk"])
    ap.add_argument("--tol", choices=sorted(TOLS), default="A")
    o = ap.parse_args()
    print(f"{o.corner} {o.temp:g} C, voff {o.voff:g} mV, tol {o.tol}")
    if o.mc:
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(lambda s: even(o, s), range(1, o.mc + 1)))
        for tag in ("one", "all"):
            v = np.array([r[tag] for r in res]) * 1e15
            print(f"even per toggle, {tag}: mean {v.mean():+.5f} fC, sigma {v.std(ddof=1):.5f} fC, "
                  f"max abs {np.abs(v).max():.5f} fC over {len(v)} seeds")
        return
    if "brk" in o.tests:
        for k, v in brk(o).items():
            print(f"  {k}: {v:.3f}")
    if "even" in o.tests:
        r = even(o)
        print(f"  even per toggle: one cell {r['one'] * 1e15:+.5f} fC, all cells {r['all'] * 1e15:+.5f} fC "
              f"(requirement 0.016 fC)")
    if "ref" in o.tests:
        for k, v in ref(o).items():
            print(f"  {k}: {v:.4f}")


if __name__ == "__main__":
    main()
