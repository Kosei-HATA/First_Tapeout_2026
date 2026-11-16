#!/usr/bin/env python3
"""Figure 38 (r12, 11/16): the AFE released at the process corners with the cascode-booster trim at its reset value
(BOOST_TRIM 4/4, as the first power-on has it) and AFE_IBIAS = 3 written by the firmware, a full-scale 2 kHz sine from
20 us after the release (afe_startup.py start on the chip's own wiring, runs/startup/start_*_sine0.943mV2000Hz_*), and
the trims of the corner table of gf180_afe_noise_20261022.md (ss 2/2, sf 8/4, fs 2/6, written with AFE_IBIAS:
afe_trim_start.py), plus ss 2/2 with AFE_IBIAS left at code 2, where those runs exist.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/corner_start_fig.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
FCH = 32.768e6 / 256
TCH = 1 / FCH
F0, VIN = 2000.0, 0.943e-3
HD_SPEC = -111.0                                  # dBc, gf180_electrode_dc_20261022.md (the distortion requirement)
YTOP = -86.0                                      # top of the harmonics axis; worse points get an arrow
TEAL, AMBER, PLUM = "#0d9488", "#b45309", "#a21caf"
CORNER = {"typical": (INK, "typical"), "ss": (ACCENT, "ss"), "ff": (AMBER, "ff"), "fs": (TEAL, "fs (NMOS fast)"),
          "sf": (PLUM, "sf (PMOS fast)")}
COLS = ["qo", "vbn_afe", "avss_afei", "iavdd", "opi", "oni"]
# (corner, AVDD, booster-trim tag, AFE_IBIAS code); the trimmed runs: (label, marker, x shift)
RUNS = ([(c, 3.3, "", 3) for c in CORNER] + [("ss", 3.135, "", 3), ("ff", 3.135, "", 3), ("typical", 3.135, "", 3)] +
        [("ss", 3.3, "_bt2-2", 3), ("sf", 3.3, "_bt8-4", 3), ("fs", 3.3, "_bt2-6", 3), ("ss", 3.3, "_bt2-2", 2)])
TRIM = {("_bt2-2", 3): ("trim 2/2", "D", 0.26), ("_bt8-4", 3): ("trim 8/4", "D", 0.26), ("_bt2-6", 3): ("trim 2/6", "D", 0.26),
        ("_bt2-2", 2): ("trim 2/2, AFE_IBIAS 2", "s", 0.42)}


def name(c, vdd, tag, ib=3):
    return f"start_c1e-08_v{vdd:g}_{c}_+0mV_sine0.943mV2000Hz_afe5ms{'_ib3' if ib == 3 else ''}{tag}_chip_{V.CHIP}"


def label(k):
    c, vdd, tag, ib = k
    return f"{c} {vdd:g} V, " + (TRIM[tag, ib][0] if tag else "trim 4/4")


def load(run):
    d = os.path.join(SU, run)
    if not os.path.exists(os.path.join(d, "tr.csv")):
        return None
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    log = open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()
    names = meta["vectors"]
    keep = [0] + [2 * names.index(c) + 1 for c in COLS]
    df = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)
    x = df[keep].to_numpy()
    v = {c: x[:, i + 1] for i, c in enumerate(COLS)}
    v["t"] = x[:, 0]
    v["done"] = "timestep too small" not in log.lower() and v["t"][-1] >= meta["tstop"] * (1 - 1e-6)
    v["vamax"] = float(log.split("vamax =")[1].split()[0]) if "vamax =" in log else np.nan
    return v, meta


def fit(t, y, nh=1):
    cols = []
    for k in range(1, nh + 1):
        w = 2 * np.pi * k * F0 * t
        cols += [np.sin(w), np.cos(w)]
    cols += [np.ones_like(t), t - t.mean()]
    c = np.linalg.lstsq(np.column_stack(cols), y, rcond=None)[0]
    return np.array([np.hypot(c[2 * k], c[2 * k + 1]) / np.sinc(k * F0 * TCH) for k in range(nh)]), c[2 * nh]


def win_mean(t, y, t0, t1):
    a = (t >= t0) & (t <= t1)
    return np.trapz(y[a], t[a]) / (t[a][-1] - t[a][0])


def analyse(v, meta):
    t = v["t"]
    ta = meta["t_afe"]
    edges = meta["t_reset"] + TCH / 4 + TCH * np.arange(int((t[-1] - meta["t_reset"] - TCH / 4) / TCH) + 1)
    m = np.diff(np.interp(edges, t, v["qo"])) / TCH
    x = 0.5 * (edges[1:] + edges[:-1]) - ta
    a = x > 0
    x, m = x[a], m[a]
    win = int(round(1 / F0 / TCH))
    tc, amp = [], []
    for i in range(0, len(x) - win, win // 8):
        A, _ = fit(x[i:i + win], m[i:i + win])
        tc.append(x[i + win // 2])
        amp.append(A[0])
    tc, amp = np.array(tc), np.array(amp)
    late = x >= x[-1] - 1.5e-3
    A, off = fit(x[late], m[late], nh=5)
    hd = 20 * np.log10(A[1:] / A[0])
    pre = t < meta["t_reset"]
    vb = (v["vbn_afe"] - v["avss_afei"])[pre]
    bad = np.nonzero(np.abs(vb - vb[-1]) >= 0.01 * vb[-1])[0]
    return dict(x=x, m=m, tc=tc, amp=amp, a1=A[0], gain=A[0] / VIN, off=off, hd2=hd[0], hd3=hd[1], hd4=hd[2], hd5=hd[3],
                tbias=t[pre][bad[-1] + 1] if len(bad) else 0.0,
                i_rel=-win_mean(t, v["iavdd"], ta - 8 * TCH, ta), vbn_rel=win_mean(t, v["vbn_afe"] - v["avss_afei"], ta - 8 * TCH, ta),
                vamax=v["vamax"], done=v["done"])


def main():
    res = {}
    for k in RUNS:
        r = load(name(*k))
        if r is not None:
            res[k] = analyse(*r)
    have = set(res)
    interim = len(have) < len(RUNS)
    typ = res["typical", 3.3, "", 3]
    fig = V.figure(12.8, 9.8, "The AFE released at the process corners: the booster trim at reset, then as the corner table sets it" +
                   (" (interim)" if interim else ""),
                   "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, pads, board, bond wires, power-on in 1 ms · "
                   "27 °C · RESET_N at 4.8 ms, AFE_IBIAS = 3 at 4.82 ms, AFE_RST released at 5 ms · BOOST_TRIM 4/4 (its "
                   "reset value) unless marked · 0.943 mV pk at 2 kHz from 20 µs after the release, electrodes 100 Ω per leg",
                   note="Corners: the MOS models with the matching resistor, MIM, diode and MOS-capacitor corners (fs: NMOS fast, "
                        "PMOS slow). Amplitude: a sine, an offset and a drift fitted to the chopper-period means over each signal "
                        "period (500 µs), the period average's sinc taken out; gain = amplitude / 0.943 mV. Harmonics: the "
                        "fundamental and harmonics 2–5 fitted together over the last 1.5 ms (three periods), each with its "
                        f"sinc. The requirement for each harmonic is −{-HD_SPEC:.0f} dBc (in band; the 2 kHz harmonics here run "
                        "a few dB above the in-band static ones: typical −113.0 here, −120.3 dBc static on the AFE's own bench). "
                        "Trims (BTRIM_P/BTRIM_N units): written with AFE_IBIAS, as the corner table of gf180_afe_noise_20261022.md "
                        "sets them (ss 2/2, sf 8/4, fs 2/6; 2/2 is the lowest setting); 'AFE_IBIAS 2': the firmware leaves the "
                        "tail bias at its reset value.")
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1])

    ax = fig.add_subplot(gs[0, 0:2])
    for (c, vdd, tag, ib), r in res.items():
        col = CORNER[c][0]
        ls = "-" if vdd == 3.3 else (0, (4, 2))
        if tag:
            ls = (0, (1, 1))
        ax.plot(r["tc"] * 1e3, r["amp"] * 1e3, marker="o", color=col, ls=ls, ms=2.6, lw=1.0)
    for c, (col, lab) in CORNER.items():
        if (c, 3.3, "", 3) in have:
            ax.plot([], [], color=col, lw=1.3, label=lab)
    ax.plot([], [], color=INK2, lw=1.0, ls=(0, (4, 2)), label="AVDD 3.135 V")
    if any(k[2] for k in have):
        ax.plot([], [], color=INK2, lw=1.0, ls=(0, (1, 1)), label="trimmed (corner table)")
    ax.set_xlim(0, 2.0)
    ax.set_xlabel("Centre of the fitted signal period (ms after the release)")
    ax.set_ylabel("Output amplitude (mV pk)")
    ax.legend(loc="lower right", ncol=3, fontsize=7.6)
    ax.set_title("The output's sine from the release: at its final amplitude from the second fitted period on, every corner",
                 loc="left")

    def dots(ax, key, scale=1.0, ref=None):
        xs = {c: i for i, c in enumerate(CORNER)}
        for (c, vdd, tag, ib), r in res.items():
            y = r[key] * scale - (ref if ref is not None else 0)
            if tag:
                _, mk, dx = TRIM[tag, ib]
                ax.plot(xs[c] + dx, y, mk, color=CORNER[c][0], ms=5.5, mfc="white", mew=1.3, zorder=3)
            else:
                ax.plot(xs[c] + (0.0 if vdd == 3.3 else -0.22), y, "o" if vdd == 3.3 else "v", color=CORNER[c][0], ms=6.5,
                        mec="white", mew=0.6, zorder=3)
        ax.set_xticks(range(len(CORNER)), list(CORNER))
        ax.set_xlim(-0.6, len(CORNER) - 0.4)
        ax.grid(axis="x", visible=False)

    ax = fig.add_subplot(gs[0, 2])
    dots(ax, "gain", 1.0)
    ax.axhline(typ["gain"], color=LIGHT, lw=0.8)
    ax.set_ylabel("Gain (output / 0.943 mV)")
    ax.plot([], [], "o", color=INK2, ms=6, label="AVDD 3.3 V, trim 4/4")
    ax.plot([], [], "v", color=INK2, ms=6, label="3.135 V, trim 4/4")
    if any(k[2] and k[3] == 3 for k in have):
        ax.plot([], [], "D", color=INK2, ms=5.5, mfc="white", mew=1.3, label="corner-table trim")
    if any(k[2] and k[3] == 2 for k in have):
        ax.plot([], [], "s", color=INK2, ms=5.5, mfc="white", mew=1.3, label="ss 2/2, AFE_IBIAS 2")
    ax.legend(loc="lower right", fontsize=7.4)
    gs_ = [r["gain"] / typ["gain"] - 1 for k, r in res.items()]
    ax.set_title(f"Gain: {100 * min(gs_):+.1f} to {100 * max(gs_):+.1f} % of typical".replace("-", "−"), loc="left")

    ax = fig.add_subplot(gs[1, 0])
    xs = {c: i for i, c in enumerate(CORNER)}
    for (c, vdd, tag, ib), r in res.items():
        col = CORNER[c][0]
        if tag:
            _, mk, dx = TRIM[tag, ib]
            kw = dict(mfc="white", mew=1.3, ms=5.5)
        else:
            mk, dx = ("o" if vdd == 3.3 else "v"), (0.0 if vdd == 3.3 else -0.22)
            kw = dict(mec="white", mew=0.6, ms=6.5)
        ax.plot(xs[c] + dx - 0.05, r["hd2"], mk, color=col, zorder=3, alpha=0.4, **kw)
        if r["hd3"] > YTOP:                       # off the axis (ss at 3.135 V): an arrow at the top and the value
            ax.annotate("", xy=(xs[c] + dx + 0.05, YTOP - 0.3), xytext=(xs[c] + dx + 0.05, YTOP - 6),
                        arrowprops=dict(arrowstyle="-|>", color=col, lw=1.2), zorder=3)
            ax.text(xs[c] + dx + 0.12, YTOP - 4.5, f"{label((c, vdd, tag, ib))}:\nHD3 {r['hd3']:.1f} dBc".replace("-", "−"),
                    fontsize=7.0, color=col, va="center", ha="left")
        else:
            ax.plot(xs[c] + dx + 0.05, r["hd3"], mk, color=col, zorder=3, **kw)
    ax.set_ylim(-145, YTOP)
    ax.axhline(HD_SPEC, color=MUTED, lw=0.9, ls=(0, (3, 2)))
    ax.text(len(CORNER) - 0.45, HD_SPEC + 1, f"requirement {HD_SPEC:.0f} dBc".replace("-", "−"), ha="right", va="bottom",
            fontsize=7.4, color=MUTED)
    ax.set_xticks(range(len(CORNER)), list(CORNER))
    ax.set_xlim(-0.6, len(CORNER) - 0.4)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("dBc")
    worst = max(res.items(), key=lambda kv: kv[1]["hd3"])
    ax.set_title(f"HD3 (solid) and HD2 (faint): worst HD3 {worst[1]['hd3']:.1f} dBc\n({label(worst[0])})".replace("-", "−"),
                 loc="left")

    ax = fig.add_subplot(gs[1, 1])
    dots(ax, "i_rel", 1e3)
    ax.set_ylabel("AVDD current at the release (mA, the ADC's 4.7 mA included)")
    ax.set_title("Supply current (AFE_IBIAS 3 unless marked)", loc="left")

    ax = fig.add_subplot(gs[1, 2])
    dots(ax, "off", 1e3)
    ax.axhline(0, color=LIGHT, lw=0.8)
    ax.set_ylabel("Output offset, sine fit (mV)")
    offs = [r["off"] * 1e3 for r in res.values()]
    ax.set_title(f"Offset: {min(offs):+.3f} to {max(offs):+.3f} mV at the output".replace("-", "−"), loc="left")

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_38_corner_release.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)
    for k, r in res.items():
        print(k, f"gain {r['gain']:.1f} ({100 * (r['gain'] / typ['gain'] - 1):+.2f} %) HD2 {r['hd2']:.1f} HD3 {r['hd3']:.1f} "
                 f"HD4 {r['hd4']:.1f} HD5 {r['hd5']:.1f} off {r['off'] * 1e3:+.3f} mV I {r['i_rel'] * 1e3:.2f} mA tbias "
                 f"{r['tbias'] * 1e3:.3f} ms vamax {r['vamax'] * 1e3:.0f} mV done {r['done']}")
    json.dump({"|".join(map(str, k)): {kk: float(vv) for kk, vv in r.items() if np.ndim(vv) == 0}
               for k, r in res.items()}, open(os.path.join(SU, f"corner_release_{V.CHIP}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
