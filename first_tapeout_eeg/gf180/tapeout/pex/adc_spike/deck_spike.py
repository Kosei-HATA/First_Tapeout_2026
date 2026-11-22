#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 5 (transistor level, short): the spike through figure 40's extracted ADC loop.

The deck is copied from adc_overload.py's run (runs/adc_overload_r12/typical_ov2.5V_150u_then_dc-39mV_300u, read
only: adc_loop_mc.py's loop with eeg_adc, eeg_bias and eeg_ref extracted (r12's ADC, r13's), the chip's reference
wiring, the RTL frame timing (CMP_STROBE e0, DLOAD e3, DAC_CLK e4), the XSPICE DWA controller, AVDD 3.245 V) with
  - the models of a corner (--corner ss: ss, res_ss, mimcap_ss, diode_ss, moscap 1.1, as afe_startup.head);
  - the input replaced by the start deck's ADC input (wave.py's reconstruction as a PWL, ideal +-SIG/2 around VCM as
    in the deck), mapped so that the deck's CMP_STROBE edges fall on the run's CHOP_OUT edges and every 4th strobe
    between them (eeg_clkgen: chop_out toggles at frame cycle 0);
  - tstop, and the raw (not linearized) points written as well (raw.csv) for the peaks.
PWL corners closer than 0.25 ns to a deck breakpoint (PULSE corners, the RST PWL, the d_source events) are moved by
0.4..1.6 ns (near-coincident breakpoints stop ngspice). A 1 ms run would take ~15 h on the P cores (the 460 us fig-40
run took 6.8 h), so the deck runs 30 us (6 spikes after its own reset transient): 53 min under taskpolicy -b, nice 10.

Inputs: runs/ver07_r14/adc_spike/data/ (extract.py), the fig-40 run folder above.
Outputs: runs/ver07_r14/adc_spike/xrun_<tag>_<variant>_<corner>_<tstop>u/ (circuit.spice and its netlists, events.txt,
meta.json); ngspice then writes raw.csv, out.csv (20 ns grid) and run.log there; xan.py analyses them.
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/deck_spike.py [--tag A] [--variant actual]
           [--corner ss] [--tstop 30e-6]
       then (cd <run folder> && taskpolicy -b nice -n 10 ngspice -b circuit.spice > run.log 2>&1)
"""
import argparse
import json
import os
import re
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
OUT = os.path.join(PEX, "runs", "ver07_r14", "adc_spike")
SRC = os.path.join(PEX, "runs", "adc_overload_r12", "typical_ov2.5V_150u_then_dc-39mV_300u")
sys.path.insert(0, HERE)
import wave as W  # noqa: E402  (this folder's wave.py)

FILES = ["circuit.spice", "eeg_adc_pex.spice", "eeg_bias_pex.spice", "eeg_ref_pex.spice", "quantizer.spice",
         "events.txt"]
T = W.T
E0 = 1.9866597656e-06 + 0.25e-9          # the deck's CMP_STROBE edges (PULSE midpoint), + k T
VEC = ("v(sig) v(xadc.o1p) v(xadc.o1n) v(xadc.i1p) v(xadc.i1n) v(o2p) v(o2n) v(xadc.i2p) v(xadc.i2n) v(norm1) "
       "i(vavdd)")


def pulse_corners(td, tr, tf, pw, per, tstop):
    out = []
    k = 0
    while td + k * per < tstop:
        b = td + k * per
        out += [b, b + tr, b + tr + pw, b + tr + pw + tf]
        k += 1
    return out


def breakpoints(txt, tstop):
    bp = []
    for mm in re.finditer(r"PULSE\(([^)]*)\)", txt):
        v = [float(x.replace("n", "e-9")) for x in mm.group(1).split()]
        bp += pulse_corners(v[2], v[3], v[4], v[5], v[6], tstop)
    for mm in re.finditer(r"^V\S+ \S+ \S+ PWL\(([^)]*)\)", txt, flags=re.M):
        v = mm.group(1).replace("u", "e-6").split()
        bp += [float(x) for x in v[0::2]]
    return np.array(sorted(bp))


def events(path):
    return np.array([float(ln.split()[0]) for ln in open(path) if ln.strip()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="A")
    ap.add_argument("--variant", default="actual")
    ap.add_argument("--corner", default="ss", choices=["typical", "ss"])
    ap.add_argument("--tstop", type=float, default=30e-6)
    ap.add_argument("--tol", type=float, default=1e-3, help="PWL simplification (V)")
    ap.add_argument("--edge", type=int, default=1864, help="the run's strobe (a CHOP_OUT edge) put on the deck's first strobe")
    a = ap.parse_args()
    name = f"xrun_{a.tag}_{a.variant}_{a.corner}_{a.tstop * 1e6:g}u"
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    for f in FILES:
        shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
    txt = open(os.path.join(d, "circuit.spice")).read()
    n = txt.count(SRC + "/")
    txt = txt.replace(SRC + "/", d + "/")
    assert n == 3, n
    if a.corner == "ss":
        for old, new in (("sm141064.ngspice typical\n", "sm141064.ngspice ss\n"), ("res_typical\n", "res_ss\n"),
                         ("mimcap_typical\n", "mimcap_ss\n"), ("diode_typical\n", "diode_ss\n"),
                         (".param moscap_corner=1.0\n", ".param moscap_corner=1.1\n")):
            assert txt.count(old) == 1, old
            txt = txt.replace(old, new)
        txt = txt.replace("* eeg_adc loop: typical 27 C", "* eeg_adc loop: ss 27 C")
    # the input
    i0 = txt.index("VSTEP STEP 0 PWL(")
    i1 = txt.index("BSIG SIG 0 V=v(STEP)+v(SINE)*v(GATE)\n") + len("BSIG SIG 0 V=v(STEP)+v(SINE)*v(GATE)\n")
    w = W.Wave(a.tag, tol=a.tol)
    s_edge = w.tr + a.edge * T + 0.25e-9                  # the run's CHOP_OUT edge (PULSE midpoint)
    delta = s_edge - E0                                   # run time = deck time + delta
    tA, uA = w.pwl(delta - 1e-9, delta + a.tstop + 1e-9, a.variant)
    tD = tA - delta
    keep = (tD > 0.0) & (tD < a.tstop)
    tD, uA = tD[keep], uA[keep]
    tD = np.concatenate(([0.0], tD, [a.tstop + 10e-9]))
    uA = np.concatenate(([w.u(np.array([delta]), a.variant)[0]], uA,
                         [w.u(np.array([delta + a.tstop + 10e-9]), a.variant)[0]]))
    # keep the corners away from the deck's breakpoints
    bp = np.concatenate((breakpoints(txt, a.tstop + 1e-6), events(os.path.join(d, "events.txt"))))
    bp = np.sort(bp[bp < a.tstop + 1e-6])
    moved = 0
    dist = lambda x: np.min(np.abs(bp - x))              # noqa: E731
    for i in range(1, len(tD)):
        if dist(tD[i]) < 0.25e-9:
            for sh in (0.4e-9, -0.4e-9, 0.8e-9, -0.8e-9, 1.2e-9, -1.2e-9, 1.6e-9, -1.6e-9):
                if dist(tD[i] + sh) >= 0.25e-9:
                    tD[i] += sh
                    break
            else:
                raise SystemExit(f"no place for the PWL corner at {tD[i]:.12e}")
            moved += 1
    o = np.argsort(tD, kind="stable")
    tD, uA = tD[o], uA[o]
    ok = np.concatenate(([True], np.diff(tD) > 0.1e-9))
    tD, uA = tD[ok], uA[ok]
    dmin = min(np.min(np.abs(bp[:, None] - tD[None, 1:])), 1.0)
    pts = [f"{t:.12e} {v:.9f}" for t, v in zip(tD, uA)]
    lines = ["VSIG SIG 0 PWL("]
    for k in range(0, len(pts), 6):
        lines.append("+ " + " ".join(pts[k:k + 6]))
    lines.append("+ )")
    new = (f"* input: start deck run {a.tag} ({w.meta['corner']}), ADC input {a.variant}, wave.py reconstruction; "
           f"run time = deck time + {delta:.12e}\n" + "\n".join(lines) + "\n")
    txt = txt[:i0] + new + txt[i1:]
    old = "tran 2e-08 0.00046 0 1e-05\nlinearize\n"
    assert txt.count(old) == 1
    txt = txt.replace(old, f"tran 2e-08 {a.tstop:g} 0 1e-05\nwrdata raw.csv {VEC}\nlinearize\n")
    open(os.path.join(d, "circuit.spice"), "w").write(txt)
    meta = dict(tag=a.tag, variant=a.variant, corner=a.corner, tstop=a.tstop, tol=a.tol, edge=a.edge, delta=delta,
                pwl_points=len(tD), corners_moved=moved, min_distance_to_breakpoint_ns=dmin * 1e9,
                window=[w.t0, w.t1], source=os.path.relpath(SRC, REPO), e0=E0)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
    print(name, json.dumps(meta))


if __name__ == "__main__":
    main()
