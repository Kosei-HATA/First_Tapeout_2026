#!/usr/bin/env python3
"""Figure 44 (r12, 11/17-): the chip's common-mode rejection and the electrodes' imbalance.

cmrr.py's results (gf180/tapeout/pex/runs/cmrr_r12/results.json) and its runs: afe_startup.py's start deck (power-on;
the extracted afe_top, eeg_bias and eeg_ref on the chip wiring with the pads, bond wires and the board; typical,
27 C, AFE_IBIAS 3, the AFE released at 5 ms) with the body moving against the board's VCM, balanced legs (100 ohm
each) or ELP 100 ohm + 51 kohm || 47 nF. Vcm is the body's own movement against ground.
  (a), (b) the AFE's output referred to the electrodes over the fitted window (50 Hz, one period, from 11/18), with
           its drift taken out (minus the baseline run, then cmrr.py's fitted polynomial and, for a leg with a
           capacitor, the RC's exponential tail), against the pins' differential v(ELP) - v(ELN) as simulated (its
           drift taken out the same way) and the legs' currents through their own impedances (-(Ip Zp - In Zn));
  (c) the admittance the body sees through each leg against frequency: these runs, and the chopped transients of
      the AFE alone (runs/viz_r12/afe_zin.csv, figures 23 and 24);
  (d) the conversion through an electrode imbalance: |Vdm / Vcm| = |Y| |dZ| per frequency, with the runs' points
      and the chip's own conversion (balanced legs).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/cmrr_fig.py     (after gf180/tapeout/pex/cmrr.py)
"""
import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, BAD, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
sys.path.insert(0, PEX)
import cmrr as C  # noqa: E402
import psrr as S  # noqa: E402  (the in-band boxcars)

OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
ZIN = os.path.join(PEX, "runs", f"viz_{V.CHIP}", "afe_zin.csv")
TEAL, PLUM, AMBER, BLUE = "#0d9488", "#a21caf", "#b45309", "#1f5aa8"
IMB, BAL = "100+51k|47n", "100"
CIN = 636e-12                       # the input capacitor, 32 x (99.7 um)^2 MIM
FS_UV = 943.0                       # the full scale at the electrodes, uV pk
FCOL = {50.0: ACCENT, 1000.0: TEAL}


def minus(s):
    return s.replace("-", "−")


def trace(r):
    """the output at the electrodes (uV) over the run's window without its drift (cmrr.py's polynomial and RC tails),
    the fitted harmonics, and the electrodes' share as a sinusoid (uV); chopper-period means"""
    names = ["qo", "qip", "qin", "inp", "inn", "body", "elp", "eln"]
    v, m = C.load(os.path.join(C.RUNS, r["run"]), names)
    s = C.series(v, m, v["t"][-1])
    if r["base"]:
        vb, mb = C.load(os.path.join(C.RUNS, r["base"]), names)
        sb = C.series(vb, mb, v["t"][-1])
        k = min(len(s["tc"]), len(sb["tc"]))
        s = {key: (s[key][:k] - sb[key][:k] if key != "tc" else s[key][:k]) for key in s if key in sb}
    a = (s["tc"] >= r["window"][0]) & (s["tc"] < r["window"][1])
    tc, f, p, t0 = s["tc"][a], r["fcm"], r["poly"], r["window"][0]
    taus = [x * 1e-3 for x in r["taus_ms"]]
    y = s["out"][a] / r["gain"] * 1e6
    A, nb = C.basis(tc, f, poly=p, taus=taus, t0=t0)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    y_d = y - A[:, :nb] @ c[:nb]
    fitted = A[:, nb:] @ c[nb:]
    vb_ph, _ = C.fit(tc, s["body"][a], f, poly=p)                    # the chip's side: no RC tail (cmrr.py)
    el = r["elec_uv"] * np.exp(1j * np.radians(r["elec_phase"])) * vb_ph[0] / abs(vb_ph[0])
    el_t = (el * np.exp(2j * np.pi * f * tc)).real
    pins = None
    if "pins_uv" in r:                                                  # the pins, their drift taken out alike
        yp = s["pins"][a] * 1e6
        cp, *_ = np.linalg.lstsq(A, yp, rcond=None)
        pins = yp - A[:, :nb] @ cp[:nb]
    return tc, y_d, fitted, el_t, pins


def trace_inband(r):
    """the output at the electrodes (nV) in band (psrr.py's three 62.5 us boxcars, as the chip's CIC sees it) over the
    run's window, its drift taken out by cmrr.py's in-band fit, and the fitted harmonics; the times moved back by the
    boxcars' delay (1.5 x 62.5 us)"""
    v, _ = C.load(os.path.join(C.RUNS, r["run"]), ["qo"])
    t, q = v["t"], v["qo"]
    if r["base"]:
        vb, _ = C.load(os.path.join(C.RUNS, r["base"]), ["qo"])
        n = min(len(t), len(vb["t"]))
        t, q = t[:n], q[:n] - vb["qo"][:n]
    tt, mm = S.boxcar3(t, q)
    t0, t1 = r["window"]
    a = (tt >= t0) & (tt < t1)
    tt, mm = tt[a][::S.DEC], mm[a][::S.DEC]
    u = (tt - 0.5 * (tt[0] + tt[-1])) / (0.5 * (tt[-1] - tt[0]))
    cols = [u ** p for p in range(r["poly"] + 1)]
    for tau in (x * 1e-3 for x in r["taus_ms"]):
        x = (tt - t0) / tau
        cols += [np.exp(-x), x * np.exp(-x)]
    nb = len(cols)
    for h in (1, 2, 3):
        w = 2 * np.pi * h * r["fcm"] * tt
        cols += [np.cos(w), np.sin(w)]
    A = np.column_stack(cols)
    y = mm / r["gain"] * 1e9
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    return tt - 1.5 * S.LBOX, y - A[:, :nb] @ c[:nb], A[:, nb:] @ c[nb:]


def afe_alone():
    """the AFE alone's chopped transients (per leg, common mode): (f, G nS, B nS) for the extraction and the schematic"""
    rows = {"pex": [], "sch": []}
    with open(ZIN, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["method"] != "transient-chopped-cm":
                continue
            z = float(row["re_ohm"]) + 1j * float(row["im_ohm"])
            y = 1 / z
            rows[row["netlist"]].append((float(row["f_hz"]), y.real * 1e9, y.imag * 1e9))
    return rows


def leg_y(r):
    """the two legs' mean admittance (S) at the run's frequency"""
    w = 2 * np.pi * r["fcm"]
    return 0.5 * ((r["gp_ns"] + r["gn_ns"]) * 1e-9 + 1j * w * (r["cp_pf"] + r["cn_pf"]) * 1e-12)


def main():
    allres = json.load(open(os.path.join(C.OUT, "results.json"), encoding="utf-8"))
    res, sw = allres["runs"], allres["switches"]
    runs = {(r["fcm"], r["zp"]): r for r in res if r["zn"] == BAL}
    freqs = sorted({f for f, _ in runs})
    f_show = min(freqs)                                        # the time traces: the lowest frequency measured
    have50 = (50.0, BAL) in runs and (50.0, IMB) in runs
    based = all(r["base"] for r in runs.values())
    interim = not (have50 and based)
    r1b, r1i = runs[(1000.0, BAL)], runs[(1000.0, IMB)]
    y1k = leg_y(r1b)
    g_ref, c_ref = y1k.real, y1k.imag / (2 * np.pi * 1000)
    y50 = leg_y(runs[(50.0, BAL)]) if (50.0, BAL) in runs else g_ref + 2j * np.pi * 50 * c_ref
    z50 = abs(C.zleg("51k|47n", 50.0))
    conv50 = abs(y50) * z50
    y50r = y50 - sw["g_gmin_ns_leg"] * 1e-9                     # without ngspice's gmin on the switches' junctions
    conv50r = abs(y50r) * z50
    tag = "measured" if (50.0, BAL) in runs else "projected from 1 kHz"
    r50i = runs.get((50.0, IMB))
    if r50i is not None:                                       # the run itself, per 100 mV pk; without the gmin, scaled
        uv50 = r50i["vdm_uv"] / r50i["vcm_mv"] * 100
        db50, uv50r = r50i["cmrr_db"], uv50 * conv50r / conv50
    else:
        uv50, db50, uv50r = 100e3 * conv50, -20 * np.log10(conv50), 100e3 * conv50r
    db50r = 20 * np.log10(100e3 / uv50r)
    # the input common mode follows the body through a high-pass: its lead at 50 Hz gives the time constant, and
    # through Cin each leg then also carries a conductance, (high-frequency ratio) x Cin / tau
    r50b = runs.get((50.0, BAL))
    tau_cm = 1 / (2 * np.pi * 50 * np.tan(np.radians(r50b["incm_phase"]))) if r50b else None
    g_cin = r1b["incm_ratio"] * CIN / tau_cm if tau_cm else None
    waiting = []
    if not have50:
        waiting.append("the 50 Hz runs (to 26 ms) are still running")
    if not based:
        waiting.append("the baselines (the common mode at 0) are still running, so the runs are fitted alone with a polynomial")

    fig = V.figure(12.8, 12.0, "Common-mode rejection and the electrodes' imbalance" + (" (interim)" if interim else ""),
                   "The body moved against the board's VCM (100 mV pk from the source, from 2.5 ms under a 2 ms envelope) "
                   "in the start deck: power-on, the extracted AFE, bias and reference on the chip wiring with the pads, "
                   "bond wires and board · typical, 27 °C, AFE_IBIAS 3, the AFE released at 5 ms · Vcm is the body's own "
                   "movement against ground · the output referred to the electrodes by the AFE's gain on this deck "
                   f"({r1b['gain']:.2f})",
                   note=minus("The legs' currents return through the board's VCM node (the reference electrode's), which "
                        f"moves with them ({r1b['vcm_ratio'] * 100:.1f} % of Vcm at 1 kHz, {r1b['vcm_phase']:+.0f}°, "
                        "through CVCM 10 nF), so the body moves by "
                        f"{r1b['body_ratio']:.4f} of the source. "
                        + (f"Until the release the amplifier's inputs are held (their common mode moves "
                           f"{r1b['held_incm_ratio']:+.2f} of the body), so each leg carries "
                           f"{0.5 * (r1b['held_cp_pf'] + r1b['held_cn_pf']):.0f} pF (balanced legs, 1 kHz); the charge "
                           f"this leaves on the 47 nF drains through the 51 kΩ ({r1i['taus_ms'][0]:.2f} ms) into the "
                           f"window and is fitted as an exponential on the output and the pins ({r1i['trans_uv'][0]:+.0f} µV "
                           f"at the electrodes at {r1i['window'][0] * 1e3:.0f} ms, 1 kHz); the chip's side (the legs' "
                           "currents, the body, the input CM) carries none of it and is fitted without. "
                           if "held_cp_pf" in r1b else "")
                        + (f"At 50 Hz the window ({r50i['window'][0] * 1e3:.0f}–{r50i['window'][1] * 1e3:.0f} ms) holds "
                           "one period, so the polynomial stays at order 2 (a cubic follows one period of the sine); the "
                           f"fit's variants (order 1, the RC × 0.9 and × 1.1) give {r50i['cmrr_span_db'][0]:.2f}–"
                           f"{r50i['cmrr_span_db'][1]:.2f} dB, and the legs' admittance is good to a few % there. "
                           if r50i is not None else "")
                        + (f"The amplifier's inputs follow the body by {r1b['incm_ratio']:.3f} above a high-pass of "
                           f"{tau_cm * 1e3:.0f} ms (their lead at 50 Hz, {r50b['incm_phase']:.2f}°; figure 39's recovery), "
                           f"so through Cin each leg also carries {r1b['incm_ratio']:.3f} × 636 pF / {tau_cm * 1e3:.0f} ms "
                           f"= {g_cin * 1e9:.1f} nS. " if g_cin else "")
                        + ("The balanced legs are given in band (11/18), as the chip's CIC sees them (three 62.5 µs "
                           "boxcars on the exact running integral): chopper-period means alias onto fcm the conversion "
                           "between the choppers, which the output chopper turns into a square wave at the ADC's input "
                           f"(out of band: {r1b['inband']['chopped_mv']:.1f} mV pk for {r1b['inband']['vcm_mv']:.1f} mV pk "
                           "at 1 kHz" + (f", {r50b['inband']['chopped_mv']:.1f} mV for {r50b['inband']['vcm_mv']:.1f} mV at "
                                         "50 Hz" if r50b else "")
                           + f"), and gave {r1b['vdm_uv']:.2f} µV ({r1b['cmrr_db']:.0f} dB) for them at 1 kHz until then; "
                           f"with 51 kΩ || 47 nF the two agree to {abs(r1i['inband']['vdm_uv'] / r1i['vdm_uv'] - 1) * 100:.2f} %. ")
                        + "The start deck keeps "
                        "ngspice's default gmin, which puts 1 pS × M across every junction: "
                        f"{sw['g_gmin_ns_leg']:.1f} nS per leg through the input chopper's switches, not in silicon "
                        "(the switches alone in a small AC deck with the PDK's models). The AFE alone's chopped "
                        "transients (figures 23 and 24; gmin 1e-15) have no pads or bond wires."
                        + (" Interim: " + "; ".join(waiting) + "." if waiting else "")))
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.4])

    # (a) the imbalanced legs: the output against the pins and the legs' currents through the imbalance
    ax = fig.add_subplot(gs[0, 0])
    r = runs[(f_show, IMB)]
    tc, y, fitted, el_t, pins = trace(r)
    t_ms = tc * 1e3
    ax.plot(t_ms, y, ".", ms=2.2, color=ACCENT, alpha=0.5, label="AFE output at the electrodes (chopper-period means)")
    if pins is not None:
        ax.plot(t_ms, pins, color=TEAL, lw=0.7, alpha=0.85, label="the pins' differential, simulated")
    ax.plot(t_ms, el_t, color=INK, lw=1.1, ls=(0, (4, 2)), label="the legs' currents through their impedances")
    ax.set_xlabel("time from power-on (ms)")
    ax.set_ylabel("differential at the electrodes (µV)")
    ax.legend(loc="upper right", fontsize=7.6)
    head = (f"ELP with 51 kΩ || 47 nF, {f_show:g} Hz: {r['vdm_uv']:.1f} µV pk for {r['vcm_mv']:.1f} mV pk, "
            f"CMRR {r['cmrr_db']:.1f} dB\n")
    if "pins_uv" in r:
        head += (f"the pins {r['pins_uv']:.1f} µV (the output over them {r['gain_fcm']:.2f}, {r['gain_fcm_phase']:+.2f}°); "
                 f"the legs' currents {r['elec_uv']:.1f} µV")
    else:
        head += f"the legs' currents through the imbalance give {r['elec_uv']:.1f} µV"
    ax.set_title(minus(head), loc="left")
    lim = 1.25 * max(abs(y).max(), abs(el_t).max())
    ax.set_ylim(-lim, 1.35 * lim)

    # (b) the balanced legs: the chip's own conversion, in band (the chopper-period means alias the conversion between
    # the choppers onto fcm: 11/18)
    ax = fig.add_subplot(gs[0, 1])
    r = runs[(f_show, BAL)]
    xb = r["inband"]
    tb, y, fitted = trace_inband(r)
    t_ms = tb * 1e3
    ax.plot(t_ms, y, color=TEAL, lw=3.2, alpha=0.45, label="AFE output at the electrodes, in band (three 62.5 µs boxcars)")
    ax.plot(t_ms, fitted, color=INK, lw=0.9, ls=(0, (4, 2)), label="fitted: fcm, 2 fcm, 3 fcm")
    ax.set_xlabel("time from power-on (ms)")
    ax.set_ylabel("differential at the electrodes (nV)")
    ax.legend(loc="upper right", fontsize=7.6)
    ax.set_title(f"Balanced legs (100 Ω each), {f_show:g} Hz: {xb['vdm_uv'] * 1e3:.1f} nV pk for {xb['vcm_mv']:.1f} mV pk,"
                 f" CMRR {xb['cmrr_db']:.0f} dB\n(the chip's own conversion with the 100 Ω legs' drops, "
                 f"{xb['elec_uv'] * 1e3:.0f} nV; in band, as the CIC sees it)", loc="left")
    lim = 1.25 * abs(y).max()
    ax.set_ylim(-lim, 1.35 * lim)

    # (c) the legs' admittance against frequency
    ax = fig.add_subplot(gs[1, 0])
    fx = np.logspace(0, 4.3, 200)
    ax.loglog(fx, 2 * np.pi * fx * c_ref * 1e9, color=PLUM, lw=1.2,
              label=f"susceptance ωC, C = {c_ref * 1e12:.1f} pF (this deck at 1 kHz)")
    ax.loglog(fx, np.full_like(fx, g_ref * 1e9), color=AMBER, lw=1.2,
              label=f"conductance G = {g_ref * 1e9:.1f} nS (this deck at 1 kHz)")
    ax.loglog(fx, np.full_like(fx, g_ref * 1e9 - sw["g_gmin_ns_leg"]), color=AMBER, lw=0.9, ls=(0, (1, 2)),
              label=f"G without ngspice's gmin on the switches ({g_ref * 1e9 - sw['g_gmin_ns_leg']:.1f} nS)")
    for f in freqs:
        rr = runs[(f, BAL)]
        w = 2 * np.pi * f
        for leg, mk in (("p", "o"), ("n", "s")):
            ax.loglog([f], [w * rr[f"c{leg}_pf"] * 1e-3], mk, color=PLUM, ms=5.5,
                      label=f"this deck, {'ELP' if leg == 'p' else 'ELN'} (filled: ωC purple, G amber)" if f == freqs[0] else None)
            ax.loglog([f], [rr[f"g{leg}_ns"]], mk, color=AMBER, ms=5.5)
    alone = afe_alone()
    for net, mk, lab in (("pex", "D", "the AFE alone, extracted (chopped transients; open)"),
                         ("sch", "^", "the AFE alone, schematic (chopped transients; open)")):
        pts = alone[net]
        fs = np.array([p[0] for p in pts])
        gg = np.array([p[1] for p in pts])
        bb = np.array([p[2] for p in pts])
        ff = np.where(fs == 0, 1.0, fs)                         # DC at the left edge
        ax.loglog(ff, gg, mk, mfc="none", mec=AMBER, ms=6, mew=1.0)
        k = fs > 0
        ax.loglog(ff[k], bb[k], mk, mfc="none", mec=PLUM, ms=6, mew=1.0, label=lab)
    ax.axvline(50, color=LIGHT, lw=0.9, ls=(0, (4, 2)))
    ax.text(1.15, g_ref * 1e9 * 0.62, "DC", fontsize=7.8, color=MUTED)
    ax.set_xlim(0.9, 2e4)
    ax.set_ylim(1, 1e5)
    ax.set_xlabel("frequency (Hz)")
    ax.set_ylabel("per leg, common mode (nS)")
    ax.legend(loc="upper left", fontsize=7.4)
    ax.set_title(f"What the body sees through each leg: {g_ref * 1e9:.1f} nS || {c_ref * 1e12:.1f} pF;\nat 50 Hz "
                 f"|Y| = {abs(y50) * 1e9:.1f} nS ({1 / abs(y50) / 1e6:.0f} MΩ, {tag}), the capacitance dominates",
                 loc="left")

    # (d) the conversion through an imbalance
    ax = fig.add_subplot(gs[1, 1])
    dz = np.logspace(2, 6.5, 200)
    for f, yy, ls, lab in ((50.0, y50, "-", f"50 Hz: |Y| = {abs(y50) * 1e9:.1f} nS ({tag})"),
                           (1000.0, y1k, (0, (4, 2)), f"1 kHz: |Y| = {abs(y1k) * 1e9:.0f} nS")):
        ax.semilogx(dz / 1e3, -20 * np.log10(abs(yy) * dz), color=FCOL[f], lw=1.3, ls=ls, label=lab)
    bal = [(f, runs[(f, BAL)]["inband"]["cmrr_db"]) for f in freqs]
    for f in freqs:
        rr = runs[(f, IMB)]
        ax.semilogx([abs(C.zleg("51k|47n", f)) / 1e3], [rr["cmrr_db"]], "o", color=FCOL[f], ms=6.5)
    if all(db > 113 for _, db in bal):
        ax.axhline(113, color=MUTED, lw=0.9, ls=(0, (1, 2)))
        ax.text(0.12, 113 - 3.6, "balanced legs, in band: " + ", ".join(f"{db:.0f} dB at {f:g} Hz" for f, db in bal)
                + " (the chip's own; off the scale)", fontsize=7.8, color=INK2)
    else:
        for f, db in bal:
            ax.axhline(min(db, 113), color=FCOL[f], lw=0.9, ls=(0, (1, 2)))
            ax.text(0.12, min(db, 113) - (3.6 if db > 113 else -1.2), f"balanced legs, {f:g} Hz, in band: {db:.0f} dB "
                    "(the chip's own" + ("; off the scale)" if db > 113 else ")"), fontsize=7.8, color=INK2)
    if r50i is None:
        ax.semilogx([z50 / 1e3], [db50], "o", mfc="white", mec=ACCENT, ms=6.5, mew=1.3)
    ax.annotate(f"51 kΩ || 47 nF at 50 Hz: {z50 / 1e3:.1f} kΩ,\n{db50:.1f} dB ({'run' if r50i else tag}); 100 mV pk on "
                f"the body\ngives {uv50:.0f} µV pk ({uv50 / FS_UV * 100:.0f} % of the full scale)",
                (z50 / 1e3, db50), (60, 72), fontsize=7.8, color=INK2,
                arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.8))
    z1 = abs(C.zleg("51k|47n", 1000.0))
    ax.annotate(f"51 kΩ || 47 nF at 1 kHz: {z1 / 1e3:.2f} kΩ, {r1i['cmrr_db']:.1f} dB (run)",
                (z1 / 1e3, r1i["cmrr_db"]), (0.13, 36), fontsize=7.8, color=INK2,
                arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.8))
    ax.set_xlim(0.1, 3e3)
    ax.set_ylim(20, 115)
    ax.set_xlabel("|ΔZ|, the legs' impedances' difference at that frequency (kΩ)")
    ax.set_ylabel("CMRR at the electrodes (dB)")
    ax.legend(loc="lower left", fontsize=7.6)
    ax.set_title(f"Through an imbalance: |Vdm / Vcm| = |Y| · |ΔZ|\n50 Hz, 51 kΩ || 47 nF: {db50:.1f} dB "
                 f"({'run' if r50i else tag}); without the gmin {db50r:.1f} dB", loc="left")

    # (e) the numbers
    ax = fig.add_subplot(gs[2, :])
    ax.set_axis_off()
    left, right = [], []
    for f in freqs:
        rb, ri = runs[(f, BAL)], runs[(f, IMB)]
        how = "minus the baseline" if rb["base"] else f"fitted alone (polynomial {rb['poly']})"
        left.append(f"{f:g} Hz, {rb['periods']} period(s), {how}:")
        xb = rb["inband"]
        left.append(f"  balanced: Vcm {rb['vcm_mv']:.2f} mV pk, in band {xb['vdm_uv'] * 1e3:.1f} nV pk, CMRR {xb['cmrr_db']:.1f} dB"
                    f" (chopper-period means {rb['vdm_uv'] * 1e3:.1f} nV)")
        line = f"  51 kΩ || 47 nF: {ri['vdm_uv']:.2f} µV pk, CMRR {ri['cmrr_db']:.2f} dB"
        if ri["periods"] < 3:
            line += f" ({ri['cmrr_span_db'][0]:.2f}–{ri['cmrr_span_db'][1]:.2f})"
        if "pins_uv" in ri:
            line += f"; the pins {ri['pins_uv']:.2f} µV, gain {ri['gain_fcm']:.2f}"
        left.append(line)
        left.append(f"  legs P {rb['gp_ns']:.2f} nS + {rb['cp_pf']:.2f} pF, N {rb['gn_ns']:.2f} nS + {rb['cn_pf']:.2f} pF;"
                    f" the input CM {rb['incm_ratio']:.4f} of Vcm ({rb['incm_phase']:+.2f}°)")
    via_cin = (1 - r1b["incm_ratio"]) * CIN
    right.append(f"Of the {c_ref * 1e12:.1f} pF per leg (1 kHz):")
    right.append(f"  {via_cin * 1e12:.1f} pF through Cin (636 pF; the amplifier's inputs follow the body by "
                 f"{r1b['incm_ratio']:.3f})")
    right.append(f"  {sw['c_pf_leg']:.1f} pF the input chopper's switches (PMOS 10.24 mm, NMOS 5.12 mm wide each;")
    right.append("    alone with the PDK's models, one phase on, at the electrodes' 1.648 V)")
    right.append(f"  {(c_ref - via_cin) * 1e12 - sw['c_pf_leg']:.1f} pF the rest: pads and bond wires, wiring, Cin's lower plate")
    if g_cin:
        right.append(f"Of the {g_ref * 1e9:.1f} nS: {sw['g_gmin_ns_leg']:.1f} gmin, {g_cin * 1e9:.1f} through Cin "
                     f"(the input CM's {tau_cm * 1e3:.0f} ms), {g_ref * 1e9 - sw['g_gmin_ns_leg'] - g_cin * 1e9:.1f} the rest")
    right.append(f"The AFE alone (chopped transient, extracted): {alone['pex'][1][1]:.1f} nS, "
                 f"{alone['pex'][1][2] / (2 * np.pi * 1e3) * 1e3:.1f} pF at 1 kHz; DC {1e3 / alone['pex'][0][1]:.1f} MΩ")
    right.append(minus(f"50 Hz, 51 kΩ || 47 nF ({'run' if r50i else tag}): {db50:.1f} dB, {uv50:.0f} µV pk per 100 mV pk;"
                       f" without the gmin {db50r:.1f} dB, {uv50r:.0f} µV pk"))
    ax.text(0.0, 0.98, minus("\n".join(left)), transform=ax.transAxes, va="top", fontsize=8.5, color=INK, linespacing=1.5)
    ax.text(0.55, 0.98, "\n".join(right), transform=ax.transAxes, va="top", fontsize=8.5, color=INK, linespacing=1.5)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_44_cmrr.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path, "(interim)" if interim else "")
    print(f"legs at 1 kHz: {g_ref * 1e9:.2f} nS + {c_ref * 1e12:.2f} pF; 50 Hz |Y| {abs(y50) * 1e9:.2f} nS ({tag}); "
          f"51k||47n at 50 Hz {z50 / 1e3:.2f} kohm -> line {-20 * np.log10(conv50):.2f} dB; run {db50:.2f} dB, "
          f"{uv50:.1f} uV pk per 100 mV; without the gmin |Y| {abs(y50r) * 1e9:.2f} nS, {db50r:.2f} dB, {uv50r:.1f} uV pk")
    if g_cin:
        print(f"input CM high-pass {tau_cm * 1e3:.2f} ms; through Cin {g_cin * 1e9:.2f} nS per leg")


if __name__ == "__main__":
    main()
