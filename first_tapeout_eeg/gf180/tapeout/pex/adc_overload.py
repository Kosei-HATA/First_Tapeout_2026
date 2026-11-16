#!/usr/bin/env python3
"""The ADC driven out of range and back (11/15): what it sees while the AFE is saturated at the first power-on with an
electrode offset (afe_saturation.py), then a full-scale signal again. adc_loop_mc.py's extracted loop on the chip's
operating point (eeg_adc, eeg_bias, eeg_ref extracted, the RTL frame timing, the DWA controller), typical, with the
input sine replaced by: 0 V until --t-on, +--vov (differential, at the ADC's input pins) for --t-ov, a full-scale sine
(--amp at --fsig) for --t-rec, -vov for --t-ov, the sine again for --t-rec. The steps are 10 ns ramps placed off the
clock grid (13.7 ns past a round microsecond). Output: runs/adc_overload<_rev>/<name>/ (circuit.spice, out.csv:
the input, O1, I1, O2, I2, the DAC1 level, the AVDD current), and report: per segment the DAC1 code range, O1 / O2
(differential and common mode) and the virtual grounds, and when the loop is back (O2 inside the quantizer's range
and the DAC1 level following the input).

With --one-sided (11/16): 0 V until --t-on, +vov for --t-ov, then --rec-dc plus the sine (--amp, 0 for none) for
--t-rec: the first power-on, where the AFE comes out of saturation to a small DC residual.

Usage: EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_overload.py run [--vov 2.5] [--t-ov 50e-6]
           [--one-sided --rec-dc -0.039 --amp 0 --t-ov 150e-6 --t-rec 300e-6]
       EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_overload.py report <name>
"""
import argparse
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import adc_loop_mc as L  # noqa: E402

REV = os.environ.get("EEG_PEX_REV", "")
RUNS = os.path.join(HERE, "runs", "adc_overload" + (f"_{REV}" if REV else ""))
OFF = 13.7e-9                                   # the steps' offset from round microseconds (off the clock edges)


def segments(s):
    """[(name, t0, t1)] of the input pattern"""
    if s.one_sided:
        return [("before", 2e-6, s.t_on), ("+overload", s.t_on, s.t_on + s.t_ov),
                ("recovery", s.t_on + s.t_ov, s.t_on + s.t_ov + s.t_rec)]
    t = [s.t_on, s.t_on + s.t_ov, s.t_on + s.t_ov + s.t_rec, s.t_on + 2 * s.t_ov + s.t_rec, s.t_on + 2 * (s.t_ov + s.t_rec)]
    return [("before", 2e-6, t[0]), ("+overload", t[0], t[1]), ("recovery 1", t[1], t[2]), ("-overload", t[2], t[3]),
            ("recovery 2", t[3], t[4])]


def build(s):
    seg = segments(s)
    a = SimpleNamespace(tstop=seg[-1][2], fsig=s.fsig, amp=s.amp, chip=True, avdd=s.avdd, tmax=10e-6)
    L.RUNS = RUNS
    os.makedirs(RUNS, exist_ok=True)
    name, d = L.build(a, "typ", None)
    dc = f"_dc{s.rec_dc * 1e3:g}mV" if s.rec_dc else ""
    sine = f"_f{s.fsig / 1e3:g}k_a{s.amp:g}" if s.amp else ""
    new = os.path.join(RUNS, (f"typical_ov{s.vov:g}V_{s.t_ov * 1e6:g}u_then{dc}{sine}_{s.t_rec * 1e6:g}u" if s.one_sided else
                              f"typical_ov{s.vov:g}V_{s.t_ov * 1e6:g}u_rec{s.t_rec * 1e6:g}u{dc}_f{s.fsig / 1e3:g}k_a{s.amp:g}"))
    if os.path.exists(new):
        subprocess.run(["rm", "-rf", new], check=True)
    os.rename(d, new)
    path = os.path.join(new, "circuit.spice")
    txt = open(path).read().replace(d + "/", new + "/")     # the local copies of the netlists move with the folder
    d = new
    old = f"VSIG SIG 0 SIN(0 {a.amp} {a.fsig} 1.1u)\n"
    assert txt.count(old) == 1, "the input line moved"
    e = lambda x: f"{x + OFF:.9e}"                  # noqa: E731
    f = lambda x: f"{x + OFF + 10e-9:.9e}"          # noqa: E731
    v, dc = f"{s.vov:g}", f"{s.rec_dc:g}"
    if s.one_sided:
        t0, t1 = seg[1][1], seg[2][1]
        step = f"VSTEP STEP 0 PWL(0 0 {e(t0)} 0 {f(t0)} {v} {e(t1)} {v} {f(t1)} {dc})\n"
        gate = f"VGATE GATE 0 PWL(0 0 {f(t1)} 0 {f(t1 + 10e-9)} 1)\n"
    else:
        t0, t1, t2, t3 = [x[1] for x in seg[1:]]
        step = (f"VSTEP STEP 0 PWL(0 0 {e(t0)} 0 {f(t0)} {v} {e(t1)} {v} {f(t1)} {dc} {e(t2)} {dc} {f(t2)} {-s.vov:g} "
                f"{e(t3)} {-s.vov:g} {f(t3)} {dc})\n")
        gate = f"VGATE GATE 0 PWL(0 0 {f(t1)} 0 {f(t1 + 10e-9)} 1 {e(t2)} 1 {f(t2)} 0 {f(t3)} 0 {f(t3 + 10e-9)} 1)\n"
    sine = f"VSINE SINE 0 SIN(0 {a.amp} {a.fsig} {f(t1 + 10e-9)})\n"
    txt = txt.replace(old, step + gate + sine + "BSIG SIG 0 V=v(STEP)+v(SINE)*v(GATE)\n")
    open(path, "w").write(txt)
    m = json.load(open(os.path.join(d, "meta.json")))
    m.update(overload=dict(vov=s.vov, t_on=s.t_on, t_ov=s.t_ov, t_rec=s.t_rec, rec_dc=s.rec_dc, one_sided=s.one_sided,
                           segments=seg))
    json.dump(m, open(os.path.join(d, "meta.json"), "w"), indent=1)
    return d


def run(s):
    d = build(s)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "circuit.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    print(f"{os.path.basename(d)}: {'ok' if os.path.exists(os.path.join(d, 'out.csv')) else 'FAILED'} ({time.time() - t:.0f} s)",
          flush=True)
    return d


def report(d):
    import numpy as np
    m = json.load(open(os.path.join(d, "meta.json")))
    x = np.loadtxt(os.path.join(d, "out.csv"))
    names = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(names)}
    t = x[:, 0]
    code = np.round((v["norm1"] + 0.5) * 31)       # the DAC1 level is -0.5 + k / 31
    o1, o2 = v["o1p"] - v["o1n"], v["o2p"] - v["o2n"]
    rows = []
    for name, a, b in m["overload"]["segments"]:
        w = (t >= a) & (t < b)
        r = dict(segment=name, t0_us=a * 1e6, t1_us=b * 1e6, code_min=int(code[w].min()), code_max=int(code[w].max()),
                 o1_mv=(float(o1[w].min() * 1e3), float(o1[w].max() * 1e3)),
                 o2_mv=(float(o2[w].min() * 1e3), float(o2[w].max() * 1e3)),
                 o1_cm=(float(((v["o1p"] + v["o1n"]) / 2)[w].min()), float(((v["o1p"] + v["o1n"]) / 2)[w].max())),
                 o2_cm=(float(((v["o2p"] + v["o2n"]) / 2)[w].min()), float(((v["o2p"] + v["o2n"]) / 2)[w].max())),
                 vg1_mv=float(np.max(np.abs(v["i1p"] - v["i1n"])[w]) * 1e3),
                 vg1_cm=(float(((v["i1p"] + v["i1n"]) / 2)[w].min()), float(((v["i1p"] + v["i1n"]) / 2)[w].max())))
        if name.startswith("recovery"):
            # back: from when on O2 stays inside the outermost thresholds (+-46.9 mV) and O1 inside +-0.2 V
            bad = np.nonzero(w & ((np.abs(o2) > 46.9e-3) | (np.abs(o1) > 0.2)))[0]
            r["back_after_us"] = float((t[bad[-1]] - a) * 1e6) if len(bad) else 0.0
            rail = np.nonzero(w & ((code == 0) | (code == 31)))[0]
            r["last_rail_code_us"] = float((t[rail[-1]] - a) * 1e6) if len(rail) else 0.0
            late = w & (t >= b - 50e-6)
            r["code_mean_last50us"] = float(code[late].mean())
        rows.append(r)
        print(json.dumps(r), flush=True)
    json.dump(rows, open(os.path.join(d, "report.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "report"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--vov", type=float, default=2.5, help="the overload, differential at the ADC's input pins (V)")
    ap.add_argument("--t-on", type=float, default=10e-6)
    ap.add_argument("--t-ov", type=float, default=50e-6)
    ap.add_argument("--t-rec", type=float, default=60e-6)
    ap.add_argument("--fsig", type=float, default=20e3)
    ap.add_argument("--amp", type=float, default=0.28)
    ap.add_argument("--avdd", type=float, default=3.245)
    ap.add_argument("--one-sided", action="store_true", help="+vov, then --rec-dc (+ the sine) for --t-rec")
    ap.add_argument("--rec-dc", type=float, default=0.0, help="the DC input after the overload (V, differential)")
    s = ap.parse_args()
    if s.what == "run":
        report(run(s))
    else:
        report(os.path.join(RUNS, s.name))


if __name__ == "__main__":
    main()
