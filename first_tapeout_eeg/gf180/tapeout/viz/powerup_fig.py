#!/usr/bin/env python3
"""Figure 37 (r12, 11/15): power-on at the process corners, AVDD ±5 % and supply ramps of 10 µs to 100 ms, the AFE held
in reset (afe_startup.py power on the chip's own wiring, the start-up branch's nodes saved: runs/startup/power_*_su_*),
against the Monte Carlo dies of figure 26's runs (their code-2 bias before RESET_N).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/powerup_fig.py
"""
import json
import os
import re
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
TAG = f"_su_chip_{V.CHIP}"
TEAL, AMBER, PLUM = "#0d9488", "#b45309", "#a21caf"
CORNER = {"typical": (INK, "typical"), "ss": (ACCENT, "ss"), "ff": (AMBER, "ff"), "fs": (TEAL, "fs (NMOS fast, PMOS slow)"),
          "sf": (PLUM, "sf (NMOS slow, PMOS fast)")}
VDD_LS = {3.135: (0, (4, 2)), 3.3: "-", 3.465: (0, (1, 1.5))}
RAMPS = [("10us", 1e-5, "#86b6ef"), ("", 1e-3, "#2a78d6"), ("10ms", 1e-2, "#1f5aa8"), ("100ms", 0.1, "#0d366b")]


def load(run, cols=None):
    d = os.path.join(SU, run)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    names = meta["vectors"]
    cols = cols or names
    keep = [0] + [2 * names.index(c) + 1 for c in cols]
    df = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)
    x = df[keep].to_numpy()
    v = {c: x[:, i + 1] for i, c in enumerate(cols)}
    v["t"] = x[:, 0]
    return v, meta


def settle(t, x, fin, tol):
    bad = np.nonzero(np.abs(x - fin) >= tol)[0]
    return t[0] if not len(bad) else t[min(bad[-1] + 1, len(t) - 1)]


COLS = ["vbn_afe", "avss_afei", "avdd_bias", "avss_bias", "sb", "g1", "iavdd", "vcm_afe"]


def run_name(corner, vdd, ramp=""):
    return f"power_c1e-08_v{vdd:g}_{corner}_+0mV_su" + (f"_ramp{ramp}" if ramp else "") + f"_chip_{V.CHIP}"


def summary(v, meta):
    t = v["t"]
    vbn = v["vbn_afe"] - v["avss_afei"]
    end = t >= t[-1] - 1e-3
    fin = vbn[end].mean()
    return dict(t1=settle(t, vbn, fin, 0.01 * fin), vbn=fin, i=-v["iavdd"][end].mean(), sb=(v["sb"] - v["avss_bias"])[end].mean(),
                late_pp=np.ptp(vbn[end]))


def mc_code2():
    """VBN at the AFE (code 2, 4.7–4.8 ms) and the bias start-up time of figure 26's typical and Monte Carlo runs"""
    out = []
    for n in sorted(os.listdir(SU)):
        if not re.match(rf"start_c1e-08_v3\.3_(typical|mc\d+)_\+0mV_afe5ms_ib3_chip_{V.CHIP}$", n):
            continue
        if not os.path.exists(os.path.join(SU, n, "run.log")) or "vamax" not in open(os.path.join(SU, n, "run.log"), errors="replace").read():
            continue
        v, meta = load(n, ["vbn_afe", "avss_afei", "iavdd"])
        t, vbn = v["t"], v["vbn_afe"] - v["avss_afei"]
        w = (t >= 4.7e-3) & (t < 4.8e-3)
        fin = vbn[w].mean()
        pre = t < 4.8e-3
        out.append(dict(seed=meta["seed"], vbn=fin, i=-v["iavdd"][w].mean(), t1=settle(t[pre], vbn[pre], fin, 0.01 * fin)))
    return out


def main():
    runs = {}
    for c in CORNER:
        for vdd in VDD_LS:
            n = run_name(c, vdd)
            if os.path.exists(os.path.join(SU, n, "tr.csv")):
                runs[c, vdd, ""] = load(n, COLS)
    for tag, _, _ in RAMPS:
        if tag:
            for c, vdd in (("typical", 3.3), ("ss", 3.135), ("sf", 3.465)):
                n = run_name(c, vdd, tag)
                if os.path.exists(os.path.join(SU, n, "tr.csv")):
                    runs[c, vdd, tag] = load(n, COLS)
    s = {k: summary(*r) for k, r in runs.items()}
    mc = mc_code2()
    mc_mc = [r for r in mc if r["seed"]]

    base = {k: v for k, v in s.items() if not k[2]}
    t1 = np.array([v["t1"] for v in base.values()]) * 1e3
    sbmax = max(v["sb"] for v in base.values())
    fig = V.figure(12.8, 10.6, "Power-on at the process corners, AVDD ±5 % and slow or fast supply ramps",
                   "afe_top, eeg_bias and eeg_ref extracted on the chip's own wiring, every pad of the ring, the board "
                   "(assumed) and bond wires · RESET_N held low (the AFE in reset, choppers idle), AFE_IBIAS at its "
                   "reset value (code 2) · VCM capacitor 10 nF · 27 °C",
                   note="The corners move the MOS models with the matching resistor, MIM, diode and MOS-capacitor corners "
                        "(fs: NMOS fast, PMOS slow). The bias block's start-up branch: a weak PMOS pull-up (two W1/L50 in "
                        "series) holds SB high while the core is off, and SB high lets an NMOS pull the core's PMOS gate "
                        "GP low; once G1 (the core's NMOS gate) rises, an NMOS on G1 pulls SB back down. The supply "
                        "ramps are the regulators' (AVDD, DVDD and the external reference together) from 0 V; the "
                        f"board's 10 µF and the bond wires shape what the chip sees. Monte Carlo: the {len(mc_mc)} seeds "
                        "of figure 26 that have finished, VBN before RESET_N.")
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], width_ratios=[1.15, 1.0, 0.85])

    ax = fig.add_subplot(gs[0, 0:2])
    for (c, vdd, tag), (v, meta) in runs.items():
        if tag:
            continue
        ax.plot(v["t"] * 1e3, (v["vbn_afe"] - v["avss_afei"]) * 1e3, color=CORNER[c][0], ls=VDD_LS[vdd],
                lw=1.6 if c == "typical" else 1.1)
    ax.axvline(1.0, color=MUTED, lw=0.8, ls=(0, (1, 2)))
    ax.text(1.0, 0.60, " supplies at full scale", transform=ax.get_xaxis_transform(), fontsize=7.5, color=MUTED, va="bottom")
    v, meta = runs["typical", 3.3, ""]
    end = v["t"] >= v["t"][-1] - 1e-3
    lift = ((v["avss_afei"] - v["avss_bias"])[end].mean()) * 1e3
    ax.text(1.03, 0.52, f"the step down at the end of the ramp: the AFE's tails reach full current\nand lift their AVSS "
            f"{lift:.0f} mV above the bias block's (typical; VBN there stays put)", transform=ax.get_xaxis_transform(),
            fontsize=7.5, color=INK2, va="top")
    for c, (col, lab) in CORNER.items():
        ax.plot([], [], color=col, lw=1.4, label=lab)
    for vdd, ls in VDD_LS.items():
        ax.plot([], [], color=INK2, ls=ls, lw=1.1, label=f"AVDD {vdd:g} V")
    ax.legend(loc="lower right", ncol=2, fontsize=8)
    ax.set_xlim(0, 2.0)
    ax.set_ylim(0, 950)
    ax.set_xlabel("Time from power-on (ms)")
    ax.set_ylabel("VBN − AVSS at the AFE's tails (mV)")
    ax.set_title(f"Tail bias from power-on: within 1 % of its final value at {t1.min():.2f}–{t1.max():.2f} ms in all 15",
                 loc="left")

    ax = fig.add_subplot(gs[0, 2])
    for (c, vdd, tag), (v, meta) in runs.items():
        if tag or vdd != 3.3:
            continue
        up = v["t"] <= meta["tramp"] * 1.2
        avdd = (v["avdd_bias"] - v["avss_bias"])[up]
        ax.plot(avdd, (v["sb"] - v["avss_bias"])[up], color=CORNER[c][0], lw=1.3)
        ax.plot(avdd, (v["g1"] - v["avss_bias"])[up], color=CORNER[c][0], lw=1.0, ls=(0, (3, 1.5)))
    ax.text(0.97, 0.94, "solid: SB (the branch on while high)\ndashed: G1 (the core's NMOS gate)", transform=ax.transAxes,
            fontsize=7.6, color=INK2, ha="right", va="top")
    ax.set_xlim(0, 3.4)
    ax.set_ylim(-0.05, 1.6)
    ax.set_xlabel("AVDD at the bias block during the ramp (V)")
    ax.set_ylabel("V")
    ax.set_title(f"The start-up branch (AVDD 3.3 V): SB ends at {sbmax * 1e3:.0f} mV or less in all 15", loc="left")

    ax = fig.add_subplot(gs[1, 0])

    def fmt_t(x):
        return f"{x * 1e3:.2f} ms" if x < 0.1 else f"{x * 1e3:.0f} ms"

    for tag, tr, col in RAMPS:
        k = ("typical", 3.3, tag)
        if k not in runs:
            continue
        v, meta = runs[k]
        y = (v["vbn_afe"] - v["avss_afei"]) * 1e3
        a = v["t"] > 0
        ax.semilogx(v["t"][a] * 1e3, y[a], color=col, lw=1.4,
                    label=f"{tr * 1e6:g} µs: {fmt_t(s[k]['t1'])}" if tr < 1e-3 else f"{tr * 1e3:g} ms: {fmt_t(s[k]['t1'])}")
        ax.plot([s[k]["t1"] * 1e3], [np.interp(s[k]["t1"], v["t"], y)], "o", color=col, ms=4.5, zorder=4)
    for c, vdd in (("ss", 3.135), ("sf", 3.465)):
        k = (c, vdd, "100ms")
        if k in runs:
            v, meta = runs[k]
            y = (v["vbn_afe"] - v["avss_afei"]) * 1e3
            a = v["t"] > 0
            ax.semilogx(v["t"][a] * 1e3, y[a], color=CORNER[c][0], lw=1.0, ls=VDD_LS[vdd],
                        label=f"100 ms, {c} {vdd:g} V: {fmt_t(s[k]['t1'])}")
    ax.set_xlim(1e-3, 150)
    ax.set_ylim(0, 1250)
    ax.set_yticks(range(0, 1001, 200))
    ax.set_xlabel("Time from power-on (ms, log scale)")
    ax.set_ylabel("VBN − AVSS at the AFE's tails (mV)")
    ax.set_title("Supply ramps of 10 µs to 100 ms (typical 3.3 V unless named)", loc="left")
    ax.legend(loc="upper left", ncol=2, fontsize=7.2, title="ramp: within 1 % at (dots)", title_fontsize=7.2,
              alignment="left", columnspacing=1.2)

    ax = fig.add_subplot(gs[1, 1])
    order = [(c, vdd) for c in CORNER for vdd in VDD_LS]
    xs = {c: i for i, c in enumerate(CORNER)}
    for (c, vdd) in order:
        k = (c, vdd, "")
        if k in s:
            ax.plot(xs[c] + {3.135: -0.18, 3.3: 0.0, 3.465: 0.18}[vdd], s[k]["vbn"] * 1e3,
                    {3.135: "v", 3.3: "o", 3.465: "^"}[vdd], color=CORNER[c][0], ms=6.5, mec="white", mew=0.6, zorder=3)
    if mc_mc:
        y = np.array([r["vbn"] for r in mc_mc]) * 1e3
        rng = np.random.default_rng(3)
        ax.plot(len(CORNER) + rng.uniform(-0.18, 0.18, y.size), y, "o", color=LIGHT, ms=5, mec="white", mew=0.5, zorder=3)
    ax.set_xticks(list(range(len(CORNER))) + ([len(CORNER)] if mc_mc else []),
                  list(CORNER) + ([f"Monte Carlo\n({len(mc_mc)} dies)"] if mc_mc else []))
    for vdd, mk in (("AVDD 3.135 V", "v"), ("3.3 V", "o"), ("3.465 V", "^")):
        ax.plot([], [], mk, color=INK2, ms=6, label=vdd)
    ax.legend(loc="center", bbox_to_anchor=(0.5, 0.6), fontsize=7.8, ncol=3)
    ax.set_ylabel("VBN − AVSS at the AFE (mV, code 2)")
    ax.set_xlim(-0.5, len(CORNER) + 0.5)
    ax.set_title("Where the tail bias ends up", loc="left")
    ax.grid(axis="x", visible=False)

    ax = fig.add_subplot(gs[1, 2])
    for (c, vdd) in order:
        k = (c, vdd, "")
        if k in s:
            ax.plot(xs[c] + {3.135: -0.18, 3.3: 0.0, 3.465: 0.18}[vdd], s[k]["i"] * 1e3,
                    {3.135: "v", 3.3: "o", 3.465: "^"}[vdd], color=CORNER[c][0], ms=6.5, mec="white", mew=0.6, zorder=3)
    if mc_mc:
        y = np.array([r["i"] for r in mc_mc]) * 1e3
        rng = np.random.default_rng(4)
        ax.plot(len(CORNER) + rng.uniform(-0.18, 0.18, y.size), y, "o", color=LIGHT, ms=5, mec="white", mew=0.5, zorder=3)
    ax.set_xticks(list(range(len(CORNER))) + ([len(CORNER)] if mc_mc else []), list(CORNER) + (["MC"] if mc_mc else []))
    ax.set_xlim(-0.5, len(CORNER) + 0.5)
    ax.set_ylabel("AVDD current (mA, the ADC's 4.7 mA included)")
    ax.set_title("Supply current, code 2", loc="left")
    ax.grid(axis="x", visible=False)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_37_powerup_corners.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)
    json.dump({"runs": {"|".join(map(str, k)): {kk: float(vv) for kk, vv in val.items()} for k, val in s.items()},
               "mc_code2": mc}, open(os.path.join(SU, f"powerup_corners_{V.CHIP}.json"), "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
