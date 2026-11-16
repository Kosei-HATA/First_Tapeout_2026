#!/usr/bin/env python3
"""The chip's common-mode rejection (11/17, r12): afe_startup.py's start deck (power-on; the extracted afe_top, eeg_bias
and eeg_ref on the chip wiring with the pads, bond wires and the board; AFE_IBIAS 3; the AFE released at 5 ms) with the
body moving against the board's VCM (--cm A mV pk at --fcm, from 2.5 ms under a 2 ms raised-cosine envelope) and the
legs' impedances set by --zp / --zn (e.g. ELP 100 ohm + 51 kohm || 47 nF, the electrode imbalance of the ECG
standards' common-mode test).

Each common-mode run is compared with its baseline, the same deck with --cm 0 (the same legs, seed and release), so
that the start-up's own drift drops out exactly; a run whose baseline has not finished is fitted alone (a quadratic
takes the drift). Over a whole number of the common mode's periods from T0 = 6 ms, on chopper-period means (edges a
quarter period after the chopper's; exact differences of the running integrals qo, qip, qin):
  - OUTP - OUTN at the ADC's input: its component at fcm (and 2 fcm, 3 fcm), referred to the electrodes by the AFE's
    gain on this deck (the typical 2 kHz full-scale run of figure 38, fitted the same way), and the CMRR,
    20 log10(Vcm / Vdm);
  - each leg's current: the admittance the body sees through it, Y = I / Vcm (conductance and capacitance);
  - the amplifier's input common mode (INP + INN) / 2 against Vcm;
  - the electrodes' share of the conversion: the legs' currents through their own impedances, -(Ip Zp - In Zn), as a
    differential voltage at the pins (the chip's own conversion is the rest).
Phasors are complex amplitudes against the common mode's own (a phase of 0 moves with the body).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/cmrr.py      (every common-mode run of r12; runs/cmrr_r12/results.json)
"""
import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs", "startup")
OUT = os.path.join(HERE, "runs", "cmrr_r12")
REV = "r12"
TCH = 256 / 32.768e6
T0 = 6e-3
SINE_RUN = f"start_c1e-08_v3.3_typical_+0mV_sine0.943mV2000Hz_afe5ms_ib3_chip_{REV}"     # figure 38's typical run
SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6, "G": 1e9}
MATCH = ("vdd", "corner", "temp", "vin", "variant", "cvcm", "t_afe", "t_reset", "ibias", "chip", "rafe", "iadc", "seed",
         "mim_a", "res_a", "dac_mag", "zp", "zn", "tmax", "moscap", "t_write", "tramp")


def si(x):
    return float(x[:-1]) * SI[x[-1]] if x[-1] in SI else float(x)


def zleg(spec, f):
    """a leg's impedance at f: terms joined by '+', each R or R|C"""
    z = 0j
    for t in spec.split("+"):
        r, _, c = t.partition("|")
        z += si(r) if not c else 1 / (1 / si(r) + 2j * np.pi * f * si(c))
    return z


def load(d, names):
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    vec = meta["vectors"]
    use = [n for n in names if n in vec]
    cols = [0] + [2 * vec.index(n) + 1 for n in use]
    x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=cols)[cols].to_numpy()
    v = {n: x[:, i + 1] for i, n in enumerate(use)}
    v["t"] = x[:, 0]
    log = open(os.path.join(d, "run.log"), errors="replace").read().lower()
    v["done"] = "timestep too small" not in log and v["t"][-1] >= meta["tstop"] * (1 - 1e-6)
    return v, meta


def integral(t, y):
    return np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])


def means(t, q, edges):
    """chopper-period means from a running integral q"""
    return np.diff(np.interp(edges, t, q)) / TCH


def fit(tc, y, f, nh=3, poly=1):
    """least squares: polynomial (order poly) + harmonics 1..nh of f; returns the complex amplitudes (a - j b for
    a cos + b sin, the period average's sinc taken out) and the residual rms"""
    tm = tc - tc.mean()
    cols = [tm ** p for p in range(poly + 1)]
    for h in range(1, nh + 1):
        w = 2 * np.pi * h * f * tc
        cols += [np.cos(w), np.sin(w)]
    A = np.column_stack(cols)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    ph = np.array([(c[poly + 1 + 2 * h] - 1j * c[poly + 2 + 2 * h]) / np.sinc((h + 1) * f * TCH) for h in range(nh)])
    return ph, float(np.std(y - A @ c))


def sine_means(tc, amp, f, td, ramp=None):
    """chopper-period means of amp sin(2 pi f (t - td)) from td (under a raised-cosine envelope over ramp), 10 ns grid"""
    t = np.arange(tc[0] - TCH, tc[-1] + TCH, 1e-8)
    w = 0.5 * (1 - np.cos(np.pi * np.clip(t - td, 0, ramp) / ramp)) if ramp else (t >= td).astype(float)
    x = amp * np.sin(2 * np.pi * f * (t - td)) * w
    edges = np.concatenate([tc - TCH / 2, [tc[-1] + TCH / 2]])
    return means(t, integral(t, x), edges)


def gain():
    """the AFE's gain on this deck, with its sign (the AFE's phase at 2 kHz is a few degrees): figure 38's typical run
    (0.943 mV pk at 2 kHz from 20 us after the release), its last 1.5 ms"""
    v, m = load(os.path.join(RUNS, SINE_RUN), ["qo"])
    edges = m["t_reset"] + TCH / 4 + TCH * np.arange(int((v["t"][-1] - m["t_reset"] - TCH / 4) / TCH) + 1)
    y = means(v["t"], v["qo"], edges)
    tc = 0.5 * (edges[1:] + edges[:-1])
    a = tc >= v["t"][-1] - 1.5e-3
    ph, _ = fit(tc[a], y[a], m["fsig"], nh=1, poly=1)
    px, _ = fit(tc[a], sine_means(tc[a], m["sine"] * 1e-3, m["fsig"], m["t_afe"] + 20e-6), m["fsig"], nh=1, poly=1)
    g = ph[0] / px[0]
    print(f"AFE gain on this deck (figure 38's typical run): {abs(g):.2f}, phase {np.degrees(np.angle(g)):+.2f} deg at "
          f"{m['fsig']:g} Hz")
    return float(np.sign(g.real) * abs(g))


def series(v, m, t_end):
    """chopper-period means on the run's own grid up to t_end: OUTP - OUTN, the legs' currents, the input CM"""
    edges = m["t_reset"] + TCH / 4 + TCH * np.arange(int((t_end - m["t_reset"] - TCH / 4) / TCH) + 1)
    t = v["t"]
    s = {"tc": 0.5 * (edges[1:] + edges[:-1]), "out": means(t, v["qo"], edges)}
    for k in ("qip", "qin"):
        if k in v:
            s[k] = means(t, v[k], edges)
    s["icm"] = means(t, integral(t, 0.5 * (v["inp"] + v["inn"])), edges)
    return s


def source(m, tc):
    """the common mode's chopper-period means (the B source's formula)"""
    return sine_means(tc, m["cm"] * 1e-3, m["fcm"], m["t_cm"], m["cm_ramp"])


def baseline_of(m, runs):
    for d, mb in runs:
        if mb.get("cm") == 0 and all(mb.get(k) == m.get(k) for k in MATCH):
            return d, mb
    return None, None


def analyse(d, m, base, g):
    names = ["qo", "qip", "qin", "inp", "inn"]
    v, _ = load(d, names)
    f = m["fcm"]
    t_end = v["t"][-1]
    n = int(np.floor((t_end - T0) * f + 1e-9))
    if n < 1:
        return None
    s = series(v, m, t_end)
    poly = 2
    if base is not None:
        vb, mb = load(base, names)
        if vb["t"][-1] >= t_end - 1e-12:
            sb = series(vb, mb, t_end)
            k = min(len(s["tc"]), len(sb["tc"]))
            assert np.allclose(s["tc"][:k], sb["tc"][:k])
            s = {key: (s[key][:k] - sb[key][:k] if key != "tc" else s[key][:k]) for key in s if key in sb}
            poly = 1
        else:
            base = None
    we = min(T0 + n / f, s["tc"][-1] + TCH / 2 + 1e-12)          # the window: n whole periods, inside the run
    a = (s["tc"] >= we - n / f) & (s["tc"] < we)
    tc = s["tc"][a]
    xcm, _ = fit(tc, source(m, tc), f)
    vcm = xcm[0]
    po, ro = fit(tc, s["out"][a], f, poly=poly)
    vdm = po[0] / g                                                     # at the electrodes
    r = dict(run=os.path.basename(d), base=os.path.basename(base) if base else None, fcm=f, cm_mv=m["cm"], zp=m["zp"],
             zn=m["zn"], corner=m["corner"], seed=m["seed"], periods=n, window=[we - n / f, we], gain=g,
             out_uv=abs(po[0]) * 1e6, out_phase=float(np.degrees(np.angle(po[0] / vcm))),
             vdm_uv=abs(vdm) * 1e6, cmrr_db=float(20 * np.log10(abs(vcm) / abs(vdm))),
             hd2_db=float(20 * np.log10(abs(po[1]) / abs(po[0]))), hd3_db=float(20 * np.log10(abs(po[2]) / abs(po[0]))),
             out_resid_uv=ro * 1e6)
    ic, _ = fit(tc, s["icm"][a], f, poly=poly)
    r["incm_ratio"], r["incm_phase"] = float(abs(ic[0] / vcm)), float(np.degrees(np.angle(ic[0] / vcm)))
    if "qip" in s:
        ip, _ = fit(tc, s["qip"][a], f, poly=poly)
        im, _ = fit(tc, s["qin"][a], f, poly=poly)
        yp, yn = ip[0] / vcm, im[0] / vcm
        w = 2 * np.pi * f
        r.update(gp_ns=yp.real * 1e9, cp_pf=yp.imag / w * 1e12, gn_ns=yn.real * 1e9, cn_pf=yn.imag / w * 1e12)
        el = -(ip[0] * zleg(m["zp"], f) - im[0] * zleg(m["zn"], f))       # the legs' drops, differential at the pins
        r["elec_uv"], r["elec_phase"] = abs(el) * 1e6, float(np.degrees(np.angle(el / vcm)))
        own = vdm - el
        r["own_uv"], r["own_phase"] = abs(own) * 1e6, float(np.degrees(np.angle(own / vcm)))
    r["done"] = bool(v["done"])
    return r


def main():
    runs = []
    for d in sorted(glob.glob(os.path.join(RUNS, f"start_*_cm*Hz*_chip_{REV}"))):
        if os.path.exists(os.path.join(d, "tr.csv")):
            runs.append((d, json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))))
    g = gain()
    res = []
    for d, m in runs:
        if not m.get("cm"):
            continue
        b, _ = baseline_of(m, runs)
        r = analyse(d, m, b, g)
        if r is None:
            continue
        res.append(r)
        print(f"{r['run']}\n  {r['periods']} period(s) of {r['fcm']:g} Hz, {'minus ' + r['base'] if r['base'] else 'fitted alone'}:"
              f" out {r['out_uv']:.2f} uV pk ({r['out_phase']:+.1f} deg), at the electrodes {r['vdm_uv']:.4f} uV pk,"
              f" CMRR {r['cmrr_db']:.1f} dB; HD2 {r['hd2_db']:.1f}, HD3 {r['hd3_db']:.1f} dB; resid {r['out_resid_uv']:.2f} uV")
        print(f"  input CM / Vcm {r['incm_ratio']:.4f} ({r['incm_phase']:+.2f} deg)")
        if "gp_ns" in r:
            print(f"  legs: P {r['gp_ns']:.3f} nS + {r['cp_pf']:.2f} pF, N {r['gn_ns']:.3f} nS + {r['cn_pf']:.2f} pF;"
                  f" the legs' drops {r['elec_uv']:.4f} uV ({r['elec_phase']:+.1f} deg), the chip's own {r['own_uv']:.4f} uV"
                  f" ({r['own_phase']:+.1f} deg)")
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(gain=g, runs=res), open(os.path.join(OUT, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
