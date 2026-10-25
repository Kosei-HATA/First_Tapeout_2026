#!/usr/bin/env python3
"""Figures and the summary table of the E2E with parasitics (pex_e2e.py; tracker D4 / D6):
the four runs d4, sch, pex, pexchip in the same colours and line styles in every figure.

  1 electrode input and the AFE output averaged over each chopper period
  2 the ADC input OUTP - OUTN as it is (instantaneous), with the full-scale lines
  3 O1 and O2 (first and second integrator outputs)
  4 the DAC1 level (mid-frame samples) with the fitted sine, and its residual
  5 the AVDD current
  6 differences pex - sch and pexchip - pex (AFE output period averages, DAC1 level)
  7 the summary table

Metrics (window from --t0): the fits of tr_window.py (electrode, AFE output period averages,
DAC1 level), the AVDD current, the extremes of OUTP - OUTN, O1 and O2, and the AFE output's
phase-A / phase-B difference: the held value of each chopper half period (outside the
blanking) fitted with the signal sine; twice the mean of the residual times (-1)^k is the
A - B difference of the held levels (the ripple's square wave, p-p).

Usage: python3 gf180/tapeout/pex/plot_e2e.py [--runs d4 sch pex pexchip] [--date 20261024] [--t0 20e-6]
       [--suffix _smoke] [--out <folder>]
"""
import argparse
import json
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RUNS = os.path.join(HERE, "runs", "e2e")
FIGS = os.path.join(REPO, "documentation", "figures")

FS = 1.024e6
T = 1 / FS
TM = T / 32
T0_LOAD = 2.0784625e-06
TCH = 1 / 128e3
E0 = T0_LOAD - 3 * TM                    # strobe of the frame whose DLOAD is T0; first CHOP edge
FULL = 0.30                              # ADC full scale (differential, V pk)
SIGNAL = 0.26                            # the part kept for the signal (V pk)

# categorical palette (dataviz reference, light), fixed order; line styles as second encoding
STYLE = {
    "d4": dict(color="#2a78d6", ls=":", label="D4 のデッキ（回路図、AFE とドライバを AVDD に直接）"),
    "sch": dict(color="#eb6834", ls="--", label="回路図（afe_top のラッパ、抽出と同じ区切り）"),
    "pex": dict(color="#1baf7a", ls="-", label="寄生込み（最終のチップの抽出）"),
    "pexchip": dict(color="#eda100", ls="-.", label="寄生込み＋チップの最上位の配線（OUTP／OUTN）"),
}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "font.family": ["Hiragino Sans", "Hiragino Maru Gothic Pro"],
    "font.size": 10, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
    "axes.facecolor": SURF, "savefig.facecolor": SURF, "legend.frameon": False,
    "axes.unicode_minus": False,
})


def fit(t, y, f):
    m = np.vstack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones_like(t)]).T
    c, *_ = np.linalg.lstsq(m, y, rcond=None)
    return c, y - m @ c


def load(folder, fsig, t0, blank):
    x = np.loadtxt(os.path.join(folder, "out.csv"))
    t = x[:, 0]
    col = lambda k: x[:, 2 * k + 1]
    d = dict(t=t, sig=col(0), vo=col(1) - col(2), o1=col(3) - col(4), o2=col(7) - col(8),
             norm1=col(9), idd=-col(10))
    m = t >= t0
    cs, _ = fit(t[m], d["sig"][m], fsig)
    s_amp = np.hypot(cs[0], cs[1])
    # AFE output averaged over whole chopper periods (edges as tr_window.py)
    q = np.concatenate([[0.0], np.cumsum(0.5 * (d["vo"][1:] + d["vo"][:-1]) * np.diff(t))])
    e = np.arange(np.ceil(t0 / TCH), np.floor(t[-1] / TCH)) * TCH
    per = np.diff(np.interp(e, t, q)) / TCH
    tp = e[:-1] + TCH / 2
    co, _ = fit(tp, per, fsig)
    o_amp = np.hypot(co[0], co[1])
    # DAC1 level at mid-frame
    k0 = int(np.ceil((t0 - T0_LOAD) / T))
    k1 = int((t[-1] - T0_LOAD) / T) - 1
    tk = T0_LOAD + (np.arange(k0, k1) + 0.5) * T
    n1 = np.interp(tk, t, d["norm1"])
    cn, rn = fit(tk, n1, fsig)
    n_amp = np.hypot(cn[0], cn[1])
    # held levels per chopper half period (CHOP edges every 4 frames from E0; blanking from
    # 1 MCLK before to `blank` MCLK after each edge)
    he = E0 + np.arange(int(np.ceil((t0 - E0) / (4 * T))), int((t[-1] - E0) / (4 * T))) * 4 * T
    hv, ht = [], []
    for a, b in zip(he[:-1], he[1:]):
        w = (t >= a + (blank + 0.5) * TM) & (t <= b - 1.5 * TM)
        hv.append(d["vo"][w].mean())
        ht.append(0.5 * (a + b))
    hv, ht = np.array(hv), np.array(ht)
    ch, rh = fit(ht, hv, fsig)
    sgn = (-1.0) ** np.arange(len(rh))
    ab = 2 * np.mean(rh * sgn)
    met = dict(electrode_mv=s_amp * 1e3, afe_mv=o_amp * 1e3, gain_afe=o_amp / s_amp,
               dac1_mv=n_amp * 0.96875 * 1e3, gain_adc=n_amp * 0.96875 / o_amp,
               gain_all=n_amp * 0.96875 / s_amp, residual=float(rn.std()), avdd_ma=float(d["idd"][m].mean() * 1e3),
               adc_in_min_mv=float(d["vo"][m].min() * 1e3), adc_in_max_mv=float(d["vo"][m].max() * 1e3),
               o1_min_mv=float(d["o1"][m].min() * 1e3), o1_max_mv=float(d["o1"][m].max() * 1e3),
               o2_min_mv=float(d["o2"][m].min() * 1e3), o2_max_mv=float(d["o2"][m].max() * 1e3),
               ab_mv=float(ab * 1e3), held_res_rms_mv=float(np.std(rh - ab / 2 * sgn) * 1e3))
    d.update(m=m, tp=tp, per=per, tk=tk, n1=n1, cn=cn, rn=rn, met=met, ht=ht, hv=hv)
    return d


def legend_handles(runs):
    return [plt.Line2D([], [], color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.6, label=STYLE[r]["label"])
            for r in runs]


def top_legend(ax, runs, extra=()):
    """The runs' legend (and what the marks mean) just above the axes, outside the data."""
    ax.legend(handles=legend_handles(runs) + list(extra), loc="lower left", bbox_to_anchor=(0, 1.01), ncol=2,
              fontsize=8)


def key_line(label, ls="-", color=INK2, lw=1.4):
    return plt.Line2D([], [], color=color, ls=ls, lw=lw, label=label)


def key_dot(label, color=INK2):
    return plt.Line2D([], [], color=color, ls="none", marker="o", ms=5, label=label)


def sliding(d, key="vo"):
    """d[key] (OUTP - OUTN by default) averaged over one chopper period centred on each sample,
    where the period lies inside the record."""
    t = d["t"]
    q = np.concatenate([[0.0], np.cumsum(0.5 * (d[key][1:] + d[key][:-1]) * np.diff(t))])
    w = (t >= t[0] + TCH / 2) & (t <= t[-1] - TCH / 2)
    tt = t[w]
    return tt, (np.interp(tt + TCH / 2, t, q) - np.interp(tt - TCH / 2, t, q)) / TCH


def save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(path, REPO))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["d4", "sch", "pex", "pexchip"])
    ap.add_argument("--date", default="20261024")
    ap.add_argument("--fsig", type=float, default=16e3)
    ap.add_argument("--t0", type=float, default=20e-6)
    ap.add_argument("--blank", type=int, default=7)
    ap.add_argument("--suffix", default="", help="run folder suffix (e.g. _smoke)")
    ap.add_argument("--out", default=FIGS)
    a = ap.parse_args()
    runs = [r for r in a.runs if os.path.exists(os.path.join(RUNS, r + a.suffix, "out.csv"))]
    D = {r: load(os.path.join(RUNS, r + a.suffix), a.fsig, a.t0, a.blank) for r in runs}
    pre = os.path.join(a.out, f"gf180_e2e_pex_{a.date}")
    us = lambda t: t * 1e6

    # 1 electrode input and AFE output (period averages)
    fig, ax = plt.subplots(2, 1, figsize=(9, 6.6), sharex=True, gridspec_kw=dict(height_ratios=[1, 2], hspace=0.55))
    r0 = runs[0]
    ax[0].plot(us(D[r0]["t"]), D[r0]["sig"] * 1e3, color=INK2, lw=1.2)
    ax[0].set_ylabel("電極の入力 (mV)")
    ax[0].set_title("電極の入力（全部の版で同じ）", fontsize=10, loc="left", color=INK)
    for r in runs:
        tt, av = sliding(D[r])
        ax[1].plot(us(tt), av * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.6)
        ax[1].plot(us(D[r]["tp"]), D[r]["per"] * 1e3, color=STYLE[r]["color"], ls="none", marker="o", ms=5)
    ax[1].set_ylabel("AFE の出力、チョッパ周期の平均 (mV)")
    ax[1].set_xlabel("時間 (µs)")
    ax[1].axvline(a.t0 * 1e6, color=INK2, lw=0.8, ls=(0, (2, 2)))
    ax[1].text(a.t0 * 1e6, ax[1].get_ylim()[1], " 評価の窓の始まり", color=INK2, fontsize=8, va="top")
    top_legend(ax[1], runs, [key_line("線：1 チョッパ周期（7.8 µs）の移動平均"), key_dot("点：利得の当てはめに使った周期平均")])
    save(fig, f"{pre}_1_afe.png")

    # 2 ADC input instantaneous
    fig, ax = plt.subplots(2, 1, figsize=(9, 6.5), gridspec_kw=dict(height_ratios=[3, 2]))
    for r in runs:
        ax[0].plot(us(D[r]["t"]), D[r]["vo"] * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=0.9)
    for y, txt in ((FULL, "ADC のフルスケール ±300 mV"), (SIGNAL, "信号に使う範囲 ±260 mV")):
        for s in (1, -1):
            ax[0].axhline(s * y * 1e3, color=INK2, lw=0.8, ls=(0, (4, 2)) if y == FULL else (0, (1, 2)))
        ax[0].text(us(D[r0]["t"][-1]), y * 1e3, txt + " ", color=INK2, fontsize=8, ha="right", va="bottom")
    ax[0].set_ylabel("ADC の入力の瞬時値 OUTP − OUTN (mV)")
    ax[0].set_xlabel("時間 (µs)")
    top_legend(ax[0], runs)
    # zoom: two chopper periods around the largest output
    rz = "pex" if "pex" in runs else r0
    iz = np.argmax(np.where(D[rz]["m"], np.abs(D[rz]["vo"]), 0))
    tz = D[rz]["t"][iz]
    for r in runs:
        w = (D[r]["t"] > tz - TCH) & (D[r]["t"] < tz + TCH)
        ax[1].plot(us(D[r]["t"][w]), D[r]["vo"][w] * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.4)
    ax[1].set_ylabel("OUTP − OUTN (mV)")
    ax[1].set_xlabel("時間 (µs)：振幅の最も大きい所の前後 2 チョッパ周期")
    save(fig, f"{pre}_2_adcin.png")

    # 3 O1, O2
    fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    for r in runs:
        ax[0].plot(us(D[r]["t"]), D[r]["o1"] * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=0.9)
        ax[1].plot(us(D[r]["t"]), D[r]["o2"] * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=0.9)
    ax[0].set_ylabel("第 1 積分器の出力 O1 (mV)")
    ax[1].set_ylabel("第 2 積分器の出力 O2 (mV)")
    for s in (1, -1):
        ax[1].axhline(s * 46.9, color=INK2, lw=0.8, ls=(0, (4, 2)))
    ax[1].text(us(D[r0]["t"][-1]), 46.9, "量子化器の範囲 ±46.9 mV ", color=INK2, fontsize=8, ha="right", va="bottom")
    ax[1].set_xlabel("時間 (µs)")
    top_legend(ax[0], runs)
    save(fig, f"{pre}_3_o1o2.png")

    # 4 DAC1 level and residual
    fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True, gridspec_kw=dict(height_ratios=[2, 1]))
    gref = D["sch"]["met"]["gain_all"] if "sch" in D else D[r0]["met"]["gain_all"]
    w = D[r0]["t"] >= D[r0]["tk"][0]
    ax[0].plot(us(D[r0]["t"][w]), D[r0]["sig"][w] * gref * 1e3, color=INK, lw=0.8)
    for r in runs:
        d = D[r]
        ax[0].plot(us(d["tk"]), -d["n1"] * 0.96875 * 1e3, color=STYLE[r]["color"], ls="none", marker="o", ms=2.5,
                   alpha=0.8)
        c = d["cn"]
        tt = np.linspace(d["tk"][0], d["tk"][-1], 600)
        fitv = c[0] * np.cos(2 * np.pi * a.fsig * tt) + c[1] * np.sin(2 * np.pi * a.fsig * tt) + c[2]
        ax[0].plot(us(tt), -fitv * 0.96875 * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.2)
        ax[1].plot(us(d["tk"]), d["rn"], color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.0, marker="o", ms=2)
    ax[0].set_ylabel("DAC1 のレベル、符号を反転 (mV)")
    ax[1].set_ylabel("量子化の残差（DAC1 の範囲 = 1）")
    ax[1].set_xlabel("時間 (µs)")
    top_legend(ax[0], runs, [key_dot("点：フレームの中ほどの値"), key_line("線：16 kHz の正弦波の当てはめ"),
                             key_line(f"電極の入力 × {gref:.1f}（sch の全体の利得）", color=INK, lw=0.8)])
    save(fig, f"{pre}_4_dac1.png")

    # 5 AVDD current
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for r in runs:
        tt, sm = sliding(D[r], "idd")
        ax.plot(us(tt), sm * 1e3, color=STYLE[r]["color"], ls=STYLE[r]["ls"], lw=1.4)
    mid = np.mean([D[r]["met"]["avdd_ma"] for r in runs])
    ax.set_ylim(mid - 0.6, mid + 0.6)
    ax.set_ylabel("AVDD の電流、チョッパ周期の平均 (mA)")
    ax.set_xlabel("時間 (µs)")
    top_legend(ax, runs)
    save(fig, f"{pre}_5_avdd.png")

    # 6 differences
    pairs = [(x, y) for x, y in (("pex", "sch"), ("pexchip", "pex")) if x in D and y in D]
    if pairs:
        fig, ax = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
        for x, y in pairs:
            tx, ax_ = sliding(D[x])
            ty, ay_ = sliding(D[y])
            w = tx >= a.t0
            ax[0].plot(us(tx[w]), (ax_[w] - np.interp(tx[w], ty, ay_)) * 1e3, color=STYLE[x]["color"],
                       ls=STYLE[x]["ls"], lw=1.6, label=f"{x} − {y}（1 チョッパ周期の移動平均）")
            n = min(len(D[x]["n1"]), len(D[y]["n1"]))
            dn = (D[x]["n1"][:n] - D[y]["n1"][:n]) * 31
            ax[1].plot(us(D[x]["tk"][:n]), dn, color=STYLE[x]["color"], ls="none", marker="o", ms=2.5, alpha=0.7)
            ax[1].plot(us(D[x]["tk"][:n]), np.convolve(dn, np.ones(8) / 8, mode="same"), color=STYLE[x]["color"],
                       ls=STYLE[x]["ls"], lw=1.6, label=f"{x} − {y}（8 フレームの移動平均）")
        ax[0].set_ylabel("AFE の出力の差 (mV)")
        ax[1].set_ylabel("DAC1 のレベルの差 (LSB)")
        ax[1].set_xlabel("時間 (µs)")
        ax[0].legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=8)
        ax[1].legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=8)
        save(fig, f"{pre}_6_diff.png")

    # 7 table
    rows = [("AFE の利得（周期平均の当てはめ）", "gain_afe", "{:.1f}"), ("全体の利得（電極 → DAC1）", "gain_all", "{:.1f}"),
            ("ADC の利得（AFE の出力 → DAC1）", "gain_adc", "{:.3f}"), ("量子化の残差（DAC1 の範囲 = 1、rms）", "residual", "{:.4f}"),
            ("AVDD の電流 (mA)", "avdd_ma", "{:.2f}"), ("AFE の出力の相 A − B の差 (mV)", "ab_mv", "{:+.2f}"),
            ("ADC の入力の瞬時値 最小 (mV)", "adc_in_min_mv", "{:.1f}"), ("同 最大 (mV)", "adc_in_max_mv", "{:.1f}"),
            ("O1 最小／最大 (mV)", ("o1_min_mv", "o1_max_mv"), "{:.1f}／{:.1f}"),
            ("O2 最小／最大 (mV)", ("o2_min_mv", "o2_max_mv"), "{:.1f}／{:.1f}")]
    cells = []
    for name, key, f in rows:
        if isinstance(key, tuple):
            cells.append([name] + [f.format(D[r]["met"][key[0]], D[r]["met"][key[1]]) for r in runs])
        else:
            cells.append([name] + [f.format(D[r]["met"][key]) for r in runs])
    fig, ax = plt.subplots(figsize=(10.5, 0.34 * (len(rows) + 1)))
    ax.axis("off")
    tb = ax.table(cellText=cells, colLabels=["項目"] + runs, cellLoc="right", colLoc="center", bbox=[0, 0, 1, 1],
                  colWidths=[0.34] + [0.66 / len(runs)] * len(runs))
    tb.auto_set_font_size(False)
    tb.set_fontsize(9)
    for (i, j), c in tb.get_celld().items():
        c.set_edgecolor(GRID)
        if j == 0:
            c.set_text_props(ha="left")
            c._loc = "left"
        if i == 0:
            c.set_text_props(weight="bold", color=INK)
            if j > 0:
                c.set_facecolor(STYLE[runs[j - 1]]["color"] + "33")
    ax.set_title(f"E2E（70 µs、16 kHz・0.943 mV pk、typical、窓 {a.t0 * 1e6:g} µs 〜）の主な値", fontsize=10,
                 loc="left", color=INK)
    save(fig, f"{pre}_7_table.png")
    json.dump({r: D[r]["met"] for r in runs}, open(os.path.join(RUNS, f"summary{a.suffix}.json"), "w"), indent=1)
    for r in runs:
        print(r, json.dumps({k: round(v, 4) for k, v in D[r]["met"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
