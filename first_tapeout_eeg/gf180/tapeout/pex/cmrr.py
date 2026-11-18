#!/usr/bin/env python3
"""The chip's common-mode rejection (11/17, r12): afe_startup.py's start deck (power-on; the extracted afe_top, eeg_bias
and eeg_ref on the chip wiring with the pads, bond wires and the board; AFE_IBIAS 3; the AFE released at 5 ms) with the
body moving against the board's VCM (--cm A mV pk at --fcm, from 2.5 ms under a 2 ms raised-cosine envelope) and the
legs' impedances set by --zp / --zn (e.g. ELP 100 ohm + 51 kohm || 47 nF, the electrode imbalance of the ECG
standards' common-mode test).

Each common-mode run is compared with its baseline, the same deck with --cm 0 (the same legs, seed and release), so
that the start-up's own drift drops out exactly (a polynomial of order 2 takes what the common mode itself leaves
slowly, through the input's common-mode loop); a run whose baseline has not finished is fitted alone (order 4; 2 with
fewer than 3 periods). A leg with a capacitor (R|C) also gets an exponential with that RC's time constant and its
first-order correction, (t - t0) / tau x exp(-(t - t0) / tau), from the window's start: until the release the
amplifier's inputs are held, so the body sees far more capacitance through each leg (about 795 pF instead of 139),
and the charge that leaves on the capacitor drains through the leg's resistor (51 kohm x 47 nF = 2.4 ms) into the
window; the baseline has none of it. That tail is fitted on the output and the pins only (11/18): the chip's side (the
body, the board VCM, the amplifier's input common mode, the legs' currents) carries none of it (the capacitor's
discharge stays inside the electrode; its tens of uV at the pins drive a few pA through a leg), and with a single
period (50 Hz in 6-26 ms) the extra columns let those fits trade the sine for slow drift (a leg's admittance moved by
up to 30 %, the body by 0.2 %). With fewer than 3 periods the polynomial stays at order 2 (a cubic follows one period
of the sine). Over a whole number of the common mode's periods from T0 = 6 ms, on chopper-period means (edges a quarter
period after the chopper's; exact differences of the running integrals qo, qip, qin):
  - Vcm is the body's own movement against ground, v(body): the legs' currents return through the board's VCM (the
    reference electrode's node), which moves with them (CVCM; 2.5 % of the source, -165 deg, at 1 kHz), so the body
    moves by a little less than the source's formula (kept as a check, body_ratio);
  - OUTP - OUTN at the ADC's input: its component at fcm (and 2 fcm, 3 fcm), referred to the electrodes by the AFE's
    gain on this deck (the typical 2 kHz full-scale run of figure 38, fitted the same way), and the CMRR,
    20 log10(Vcm / Vdm);
  - each leg's current: the admittance the body sees through it, Y = I / Vcm (conductance and capacitance);
  - the amplifier's input common mode (INP + INN) / 2 against Vcm, and the board VCM's movement;
  - the electrodes' share of the conversion: the legs' currents through their own impedances, -(Ip Zp - In Zn), as a
    differential voltage at the pins (the chip's own conversion is the rest; not taken for legs that differ with
    fewer than 3 periods, where the legs' phase is a few degrees loose: the balanced run gives the chip's own);
  - for legs that differ, the pins' differential v(ELP) - v(ELN) as simulated (the electrodes' drop, fitted like the
    output), and the output over it: the AFE's gain at fcm (with balanced legs the pins carry only the input
    chopper's switching, which the amplifier does not take with that gain, so neither is kept);
  - the output's spread over variants of the fit (the polynomial one order lower; the RC time constants x 0.9 and
    x 1.1): vdm_span_uv, cmrr_span_db;
  - inband (11/18): the output, the body, the legs' drops and the pins in band, as the chip's CIC sees them (psrr.py's
    three 62.5 us boxcars), and the conversion between the choppers, which the output chopper turns into a square
    wave at the ADC's input (fc -+ f). Chopper-period means alias that square wave onto f (x 0.0078 at 1 kHz): the
    balanced 1 kHz run's 0.52 uV above is that; where the in-band part dominates the two agree.
Phasors are complex amplitudes against Vcm (a phase of 0 moves with the body). Against the baseline, also the
admittance through each leg while the AFE is still held (from 0.5 ms after the common mode starts to just before the
chopper does): the legs' charge regressed on the body's movement and its integral. Besides, switches(): the input
chopper's eight switches alone in a small AC deck (the PDK's models): their share of each leg's capacitance, and the
conductance ngspice's default gmin (1 pS x M per junction) puts on each leg through them. The start deck keeps the
default gmin, so the legs' conductance from these runs carries it; silicon does not.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/cmrr.py      (every common-mode run of r12; runs/cmrr_r12/results.json)
"""
import glob
import json
import os
import re
import subprocess

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
         "mim_a", "res_a", "dac_mag", "zp", "zn", "tmax", "moscap", "t_write", "tramp", "rip")     # rip: psrr.py's runs


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


def basis(tc, f, nh=3, poly=1, taus=(), t0=None):
    """the fit's columns: a polynomial (order poly) about the window's middle; for each time constant tau,
    exp(-x) and x exp(-x) with x = (t - t0) / tau (t0: the window's start); then cos and sin of harmonics 1..nh of f.
    Returns the matrix and the number of columns before the harmonics."""
    tm = tc - tc.mean()
    cols = [tm ** p for p in range(poly + 1)]
    for tau in taus:
        x = (tc - (tc[0] if t0 is None else t0)) / tau
        cols += [np.exp(-x), x * np.exp(-x)]
    nb = len(cols)
    for h in range(1, nh + 1):
        w = 2 * np.pi * h * f * tc
        cols += [np.cos(w), np.sin(w)]
    return np.column_stack(cols), nb


def fit(tc, y, f, nh=3, poly=1, taus=(), t0=None, full=False):
    """least squares on basis(): returns the complex amplitudes of harmonics 1..nh (a - j b for a cos + b sin, the
    period average's sinc taken out) and the residual rms (and, with full, the coefficients and the number of
    columns before the harmonics)"""
    A, nb = basis(tc, f, nh, poly, taus, t0)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    ph = np.array([(c[nb + 2 * h] - 1j * c[nb + 1 + 2 * h]) / np.sinc((h + 1) * f * TCH) for h in range(nh)])
    r = float(np.std(y - A @ c))
    return (ph, r, c, nb) if full else (ph, r)


def taus_of(m):
    """the legs' RC time constants (each R|C term of --zp / --zn), s"""
    out = []
    for spec in (m["zp"], m["zn"]):
        for t in spec.split("+"):
            r, _, c = t.partition("|")
            if c and not any(abs(si(r) * si(c) - x) < 1e-12 for x in out):
                out.append(si(r) * si(c))
    return out


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
    if "elp" in v and "eln" in v:
        s["pins"] = means(t, integral(t, v["elp"] - v["eln"]), edges)
    for k in ("body", "vcm_p9"):
        if k in v:
            s[k] = means(t, integral(t, v[k]), edges)
    return s


def source(m, tc):
    """the common mode's chopper-period means (the B source's formula)"""
    return sine_means(tc, m["cm"] * 1e-3, m["fcm"], m["t_cm"], m["cm_ramp"])


def held(v, vb, m):
    """the admittance through each leg while the AFE is still held, against the baseline: from 0.5 ms after the common
    mode starts to 50 us before the chopper starts, on a 100 ns grid, each leg's charge regressed on the body's
    movement and its integral (C, G and a constant); and the amplifier's input common mode against the body"""
    tg = np.arange(m["t_cm"] + 0.5e-3, m["t_reset"] - 50e-6, 1e-7)

    def on(vv, k):
        return np.interp(tg, vv["t"], vv[k])

    db = on(v, "body") - on(vb, "body")
    A = np.column_stack([db, integral(tg, db), np.ones_like(tg)])
    out = dict(held_window=[float(tg[0]), float(tg[-1])], held_swing_mv=float(np.ptp(db) * 1e3))
    for leg, k in (("p", "qip"), ("n", "qin")):
        q = on(v, k) - on(vb, k)
        c, *_ = np.linalg.lstsq(A, q, rcond=None)
        out[f"held_c{leg}_pf"], out[f"held_g{leg}_ns"] = float(c[0] * 1e12), float(c[1] * 1e9)
        out[f"held_resid{leg}_fc"] = float(np.std(q - A @ c) * 1e15)
    dcm = 0.5 * (on(v, "inp") + on(v, "inn") - on(vb, "inp") - on(vb, "inn"))
    c, *_ = np.linalg.lstsq(np.column_stack([db, np.ones_like(tg)]), dcm, rcond=None)
    out["held_incm_ratio"] = float(c[0])
    return out


def baseline_of(m, runs):
    for d, mb in runs:
        if mb.get("cm") == 0 and all(mb.get(k) == m.get(k) for k in MATCH):
            return d, mb
    return None, None


def analyse(d, m, base, g):
    names = ["qo", "qip", "qin", "inp", "inn", "body", "vcm_p9", "elp", "eln", "outp_adc", "outn_adc"]
    v, _ = load(d, names)
    f = m["fcm"]
    t_end = v["t"][-1]
    n = int(np.floor((t_end - T0) * f + 1e-9))
    if n < 1:
        return None
    s = series(v, m, t_end)
    poly = 4 if n >= 3 else 2
    vb = None
    if base is not None:
        vb, mb = load(base, names)
        if vb["t"][-1] >= t_end - 1e-12:
            sb = series(vb, mb, t_end)
            k = min(len(s["tc"]), len(sb["tc"]))
            assert np.allclose(s["tc"][:k], sb["tc"][:k])
            s = {key: (s[key][:k] - sb[key][:k] if key != "tc" else s[key][:k]) for key in s if key in sb}
            poly = 2
        else:
            base, vb = None, None
    we = min(T0 + n / f, s["tc"][-1] + TCH / 2 + 1e-12)          # the window: n whole periods, inside the run
    t0 = we - n / f
    a = (s["tc"] >= t0) & (s["tc"] < we)
    tc = s["tc"][a]
    taus = taus_of(m)

    def F(y, full=False):                                               # the output and the pins: with the RC tails
        return fit(tc, y, f, poly=poly, taus=taus, t0=t0, full=full)

    def Fc(y):                                                          # the chip's side: without them
        return fit(tc, y, f, poly=poly)

    xcm, _ = fit(tc, source(m, tc), f)
    vcm = xcm[0]
    body = None
    if "body" in s:                                                     # the body's own movement against ground
        xb, _ = Fc(s["body"][a])
        body, vcm = xb[0] / vcm, xb[0]
    po, ro, co, nb = F(s["out"][a], full=True)
    vdm = po[0] / g                                                     # at the electrodes
    span = [abs(vdm)]
    for pv, tv in ((poly - 1, taus), (poly, tuple(x * 0.9 for x in taus)), (poly, tuple(x * 1.1 for x in taus))):
        span.append(abs(fit(tc, s["out"][a], f, poly=pv, taus=tv, t0=t0)[0][0] / g))
    r = dict(run=os.path.basename(d), base=os.path.basename(base) if base else None, fcm=f, cm_mv=m["cm"], zp=m["zp"],
             zn=m["zn"], corner=m["corner"], seed=m["seed"], periods=n, window=[t0, we], poly=poly, gain=g,
             taus_ms=[x * 1e3 for x in taus],
             trans_uv=[float(co[poly + 1 + 2 * i] / g * 1e6) for i in range(len(taus))],   # at the window's start
             vcm_mv=abs(vcm) * 1e3, out_uv=abs(po[0]) * 1e6, out_phase=float(np.degrees(np.angle(po[0] / vcm))),
             vdm_uv=abs(vdm) * 1e6, cmrr_db=float(20 * np.log10(abs(vcm) / abs(vdm))),
             hd2_db=float(20 * np.log10(abs(po[1]) / abs(po[0]))), hd3_db=float(20 * np.log10(abs(po[2]) / abs(po[0]))),
             out_resid_uv=ro * 1e6, vdm_span_uv=[min(span) * 1e6, max(span) * 1e6],
             cmrr_span_db=[float(20 * np.log10(abs(vcm) / max(span))), float(20 * np.log10(abs(vcm) / min(span)))])
    if body is not None:
        r["body_ratio"], r["body_phase"] = float(abs(body)), float(np.degrees(np.angle(body)))
    if "vcm_p9" in s:
        xv, _ = Fc(s["vcm_p9"][a])
        r["vcm_ratio"], r["vcm_phase"] = float(abs(xv[0] / vcm)), float(np.degrees(np.angle(xv[0] / vcm)))
    ic, _ = Fc(s["icm"][a])
    r["incm_ratio"], r["incm_phase"] = float(abs(ic[0] / vcm)), float(np.degrees(np.angle(ic[0] / vcm)))
    if "pins" in s and m["zp"] != m["zn"]:
        pp, rpn = F(s["pins"][a])
        r.update(pins_uv=abs(pp[0]) * 1e6, pins_phase=float(np.degrees(np.angle(pp[0] / vcm))), pins_resid_uv=rpn * 1e6,
                 gain_fcm=float(abs(po[0] / pp[0])), gain_fcm_phase=float(np.degrees(np.angle(po[0] / pp[0]))))
    if vb is not None and "qip" in v:
        r.update(held(v, vb, m))
    if "qip" in s:
        ip, rip = Fc(s["qip"][a])
        im, rin = Fc(s["qin"][a])
        r["leg_resid_na"] = [rip * 1e9, rin * 1e9]
        yp, yn = ip[0] / vcm, im[0] / vcm
        w = 2 * np.pi * f
        r.update(gp_ns=yp.real * 1e9, cp_pf=yp.imag / w * 1e12, gn_ns=yn.real * 1e9, cn_pf=yn.imag / w * 1e12)
        el = -(ip[0] * zleg(m["zp"], f) - im[0] * zleg(m["zn"], f))       # the legs' drops, differential at the pins
        r["elec_uv"], r["elec_phase"] = abs(el) * 1e6, float(np.degrees(np.angle(el / vcm)))
        if n >= 3 or m["zp"] == m["zn"]:      # one period leaves the legs' phase a few degrees loose: no remainder
            own = vdm - el
            r["own_uv"], r["own_phase"] = abs(own) * 1e6, float(np.degrees(np.angle(own / vcm)))
    r["inband"] = inband(v, vb, m, r, g, taus)
    r["done"] = bool(v["done"])
    return r


def inband(v, vb, m, r, g, taus):
    """11/18: the same quantities in band, as the chip's CIC sees them: psrr.py's three boxcars of 62.5 us on the 100 ns
    grid from the running integrals (zeros at every multiple of 16 kHz), the harmonics f, 2f, 3f fitted. Chopper-period
    means alias the output chopper's square wave (the conversion between the choppers, at fc -+ f, 3 fc -+ f) onto f, x
    0.0078 at 1 kHz: the balanced 1 kHz run's 0.52 uV was that. Also that square wave's amplitude at the ADC's input
    (pi / 2 x the fc -+ f pair on the raw grid): out of band, but it takes the ADC's range."""
    import psrr as S                                  # psrr.py imports this module
    f = m["fcm"]
    t0, t1 = r["window"]
    n = len(v["t"]) if vb is None else min(len(v["t"]), len(vb["t"]))
    t = v["t"][:n]

    def d(k):
        return v[k][:n] - (vb[k][:n] if vb is not None else 0)

    fh = [f, 2 * f, 3 * f]
    po, ro = S.inband(t, d("qo"), fh, taus, r["poly"], t0, t1)
    pb, _ = S.inband(t, integral(t, d("body")), fh, (), r["poly"], t0, t1)
    ip, _ = S.inband(t, d("qip"), fh, (), r["poly"], t0, t1)
    im, _ = S.inband(t, d("qin"), fh, (), r["poly"], t0, t1)
    vcm, vdm = pb[0], po[0] / g
    el = -(ip[0] * zleg(m["zp"], f) - im[0] * zleg(m["zn"], f))
    w = (t >= t0) & (t < t1)
    pq, _ = S.fit_tones(t[w], d("outp_adc")[w] - d("outn_adc")[w], [1 / TCH - f, 1 / TCH + f], poly=2)
    sq = np.pi / 2 * 0.5 * (abs(pq[0]) + abs(pq[1]))
    x = dict(vcm_mv=abs(vcm) * 1e3, vdm_uv=abs(vdm) * 1e6, cmrr_db=float(20 * np.log10(abs(vcm) / abs(vdm))),
             out_resid_uv=ro * 1e6, elec_uv=abs(el) * 1e6, chopped_mv=sq * 1e3, chopped_ratio=sq / abs(vcm),
             chopped_sidebands_mv=[abs(y) * 1e3 for y in pq])
    if r["periods"] >= 3 or m["zp"] == m["zn"]:      # one period leaves the legs' phase loose (as above)
        x["own_uv"] = abs(vdm - el) * 1e6
    if m["zp"] != m["zn"]:
        pp, _ = S.inband(t, integral(t, d("elp") - d("eln")), fh, taus, r["poly"], t0, t1)
        x.update(pins_uv=abs(pp[0]) * 1e6, gain_fcm=float(abs(po[0] / pp[0])))
    return {k: float(y) if not isinstance(y, list) else y for k, y in x.items()}


def switches(deck, vcm=1.648, f=1e3):
    """the input chopper's switches alone under the common mode: the run's extracted afe_top devices whose drain and
    source are both on ELP / ELN / WPT / WNT, with every source and drain on one node at vcm (the electrodes' DC), the
    gates as in one phase (CIA, NCIB high) and the PDK's typical models; AC at f, with ngspice's default gmin and with
    1e-15. Per leg: the capacitance, and the conductance the default gmin puts across their junctions (1 pS x M each,
    in every deck that keeps the default, such as the start deck; not in silicon)."""
    txt = open(deck, encoding="utf-8").read()
    head = [ln for ln in txt.splitlines()[:12] if re.match(r"\.(include .*design\.ngspice|lib .*sm141064\.ngspice typical)$", ln)]
    sub = txt[txt.index(".subckt afe_top"):]
    sub = sub[:sub.index("\n.ends")]
    pins = {"ELP", "ELN", "WPT", "WNT"}
    dev = []
    for ln in sub.splitlines():
        t = ln.split()
        if len(t) > 5 and t[0].startswith("X") and t[5] in ("pfet_03v3", "nfet_03v3") and {t[1], t[3]} <= pins:
            dev.append(" ".join([t[0], "N", t[2], "N", "0" if t[4] == "AVSS" else t[4]] + t[5:]))
    assert len(dev) == 8, dev
    out = {}
    d = os.path.join(OUT, "switches")
    os.makedirs(d, exist_ok=True)
    for tag, opt in (("default", ""), ("gmin1e-15", ".options gmin=1e-15")):
        deckf = os.path.join(d, f"sw_{tag}.cir")
        open(deckf, "w").write("\n".join(
            ["* the input chopper's switches under the common mode (cmrr.py switches)"] + head
            + ["VAVDD AVDD 0 3.3", "VCIA CIA 0 3.3", "VNCIA NCIA 0 0", "VCIB CIB 0 0", "VNCIB NCIB 0 3.3",
               f"VCM N 0 DC {vcm} AC 1"] + dev + [opt, ".temp 27", ".control", f"ac lin 1 {f:g} {f:g}",
                                                   "let y = -i(vcm)", "print real(y) imag(y)", ".endc", ".end", ""]))
        log = subprocess.run(["ngspice", "-b", deckf], capture_output=True, text=True, cwd=d).stdout
        re_ = float(re.search(r"real\(y\)\s*=\s*(\S+)", log).group(1))
        im_ = float(re.search(r"imag\(y\)\s*=\s*(\S+)", log).group(1))
        out[tag] = (re_, im_ / (2 * np.pi * f))
    # the on-resistance of one conducting pair (a PMOS and an NMOS of them, gates on) at vcm, +-1 mV
    pm = next(x for x in dev if " pfet_03v3 " in x).split()
    nm = next(x for x in dev if " nfet_03v3 " in x).split()
    deckf = os.path.join(d, "sw_ron.cir")
    open(deckf, "w").write("\n".join(
        ["* one conducting pair of the input chopper (cmrr.py switches)"] + head
        + ["VAVDD AVDD 0 3.3", "VGP GP 0 0", "VGN GN 0 3.3", f"VA A 0 {vcm}", f"VC C 0 {vcm}",
           " ".join([pm[0], "A", "GP", "C", "AVDD"] + pm[5:]), " ".join([nm[0], "A", "GN", "C", "0"] + nm[5:]),
           ".options gmin=1e-15", ".temp 27", ".control", f"dc VC {vcm - 1e-3} {vcm + 1e-3} 1e-3",
           "let r = abs(0.002 / (i(vc)[2] - i(vc)[0]))", "print r", ".endc", ".end", ""]))
    log = subprocess.run(["ngspice", "-b", deckf], capture_output=True, text=True, cwd=d).stdout
    ron = float(re.search(r"\br\s*=\s*(\S+)", log).group(1))
    return dict(devices=len(dev), vcm=vcm, f=f, c_pf_leg=out["default"][1] / 2 * 1e12,
                g_gmin_ns_leg=(out["default"][0] - out["gmin1e-15"][0]) / 2 * 1e9, g_real_ns_leg=out["gmin1e-15"][0] / 2 * 1e9,
                ron_ohm=ron)


def main():
    runs = []
    for d in sorted(glob.glob(os.path.join(RUNS, f"start_*_cm*Hz*_chip_{REV}"))):
        if os.path.exists(os.path.join(d, "tr.csv")):
            runs.append((d, json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))))
    sw = switches(os.path.join(runs[0][0], "tb.spice"))
    print(f"the input chopper's switches alone ({sw['devices']} devices, one phase on, {sw['vcm']} V, {sw['f']:g} Hz): "
          f"{sw['c_pf_leg']:.2f} pF per leg; ngspice's default gmin puts {sw['g_gmin_ns_leg']:.3f} nS per leg across their "
          f"junctions (with gmin 1e-15: {sw['g_real_ns_leg']:.4f} nS); a conducting pair's on-resistance {sw['ron_ohm']:.3f} ohm")
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
        print(f"{r['run']}\n  {r['periods']} period(s) of {r['fcm']:g} Hz, {'minus ' + r['base'] if r['base'] else 'fitted alone'}"
              f" (polynomial {r['poly']}): Vcm {r['vcm_mv']:.3f} mV pk; out {r['out_uv']:.2f} uV pk ({r['out_phase']:+.1f} deg),"
              f" at the electrodes {r['vdm_uv']:.4f} uV pk, CMRR {r['cmrr_db']:.1f} dB; HD2 {r['hd2_db']:.1f}, HD3"
              f" {r['hd3_db']:.1f} dB; resid {r['out_resid_uv']:.2f} uV")
        print(f"  over the fit's variants {r['vdm_span_uv'][0]:.4f}-{r['vdm_span_uv'][1]:.4f} uV, CMRR"
              f" {r['cmrr_span_db'][0]:.2f}-{r['cmrr_span_db'][1]:.2f} dB")
        if "pins_uv" in r:
            print(f"  the pins' differential {r['pins_uv']:.4f} uV ({r['pins_phase']:+.2f} deg, resid {r['pins_resid_uv']:.2f}"
                  f" uV); the output over it {r['gain_fcm']:.3f} ({r['gain_fcm_phase']:+.2f} deg)")
        if "body_ratio" in r:
            print(f"  the body against the source {r['body_ratio']:.4f} ({r['body_phase']:+.2f} deg); the board VCM / Vcm"
                  f" {r['vcm_ratio']:.4f} ({r['vcm_phase']:+.1f} deg)")
        print(f"  input CM / Vcm {r['incm_ratio']:.4f} ({r['incm_phase']:+.2f} deg)")
        for tau, x in zip(r["taus_ms"], r["trans_uv"]):
            print(f"  the leg's RC ({tau:.3f} ms): {x:+.2f} uV at the electrodes at the window's start")
        if "gp_ns" in r:
            print(f"  legs: P {r['gp_ns']:.3f} nS + {r['cp_pf']:.2f} pF, N {r['gn_ns']:.3f} nS + {r['cn_pf']:.2f} pF"
                  f" (resid {r['leg_resid_na'][0]:.4f}, {r['leg_resid_na'][1]:.4f} nA);"
                  f" the legs' drops {r['elec_uv']:.4f} uV ({r['elec_phase']:+.1f} deg)"
                  + (f", the chip's own {r['own_uv']:.4f} uV ({r['own_phase']:+.1f} deg)" if "own_uv" in r else ""))
        x = r["inband"]
        print(f"  in band (the CIC's view; three 62.5 us boxcars): {x['vdm_uv']:.4f} uV pk, CMRR {x['cmrr_db']:.2f} dB; the"
              f" legs' drops {x['elec_uv']:.4f} uV" + (f", the chip's own {x['own_uv']:.4f} uV" if "own_uv" in x else "")
              + (f"; the pins {x['pins_uv']:.4f} uV, gain {x['gain_fcm']:.3f}" if "pins_uv" in x else "")
              + f"; between the choppers a square wave of {x['chopped_mv']:.2f} mV pk at the ADC's input"
              f" ({x['chopped_ratio']:.4f} x Vcm)")
        if "held_cp_pf" in r:
            print(f"  while held ({r['held_window'][0] * 1e3:.2f}-{r['held_window'][1] * 1e3:.2f} ms, the body over"
                  f" {r['held_swing_mv']:.1f} mV): P {r['held_gp_ns']:.1f} nS + {r['held_cp_pf']:.1f} pF, N"
                  f" {r['held_gn_ns']:.1f} nS + {r['held_cn_pf']:.1f} pF (resid {r['held_residp_fc']:.0f},"
                  f" {r['held_residn_fc']:.0f} fC); input CM / body {r['held_incm_ratio']:+.4f}")
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(gain=g, switches=sw, runs=res), open(os.path.join(OUT, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
