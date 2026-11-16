#!/usr/bin/env python3
"""Figure 41 (r12, 11/16): the AFE's headroom window. The full-scale HD3 of the AFE against the board AVDD at each
process corner, with BOOST_TRIM at its reset value 4/4 and at the trim with the largest full-scale margin, AFE_IBIAS 3
(the firmware's), on the bench of gf180/tapeout/sim/afe/afe_margin_map.py (eeg_afe with the real eeg_bias, the AFE's
supply and VCM as the r12 chip gives them, one chopper phase frozen, a 1 kHz full-scale sine, the ADC input as the
load), calibrated against the chip-level corner releases (figure 38: afe_startup.py / afe_trim_start.py on the chip's
own wiring, 2 kHz). Below: the calibration, the margins that set the window, and the trims.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/afe_window_fig.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
MAP = os.path.join(REPO, "gf180", "tapeout", "sim", "afe", "runs", "margin_map")
SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
HD_SPEC = -111.0
TEAL, AMBER, PLUM = "#0d9488", "#b45309", "#a21caf"
CORNER = {"typical": (INK, "typical"), "ss": (ACCENT, "ss"), "ff": (AMBER, "ff"), "fs": (TEAL, "fs (NMOS fast)"),
          "sf": (PLUM, "sf (PMOS fast)")}
# AFE supply and ground against the board in the r12 chip runs at AVDD 3.3 V (afe_margin_map.CHIP)
CHIP = {"typical": (3.2558, 0.0598), "ss": (3.2624, 0.0505), "ff": (3.2462, 0.0733), "fs": (3.2560, 0.0595),
        "sf": (3.2556, 0.0600)}
YLIM = (-132, -84)


RUNS_340 = [("typical", 2, 2), ("ss", 2, 2), ("ff", 8, 2), ("sf", 8, 2), ("fs", 2, 2)]   # run_340.py (11/16)
# chip releases beyond figure 38 (corner, board AVDD, P/N units): the five at 3.40 V, the edges of 3.40 V +-1 % (run_pm1.py)
# and, after ss failed at -1 %, ff's upper edge and ss set higher (run_edges.py)
EDGES = [("ss", 3.366, 2, 2, "3.40 V − 1 %"), ("ff", 3.434, 8, 2, "3.40 V + 1 %"), ("ss", 3.45, 2, 2, "ss set higher"),
         ("ff", 3.465, 8, 2, "ff's upper edge")]
CHIP_RUNS = [(c, 3.4, n, p) for c, n, p in RUNS_340] + [(c, av, n, p) for c, av, n, p, _ in EDGES]


def chip_points():
    """the chip-level releases: figure 38's (corner_release_<chip>.json) and the 3.40 V ones with the margin map's trims
    (analysed with corner_start_fig.py's functions, cached in corner_release_340_<chip>.json):
    {(corner, avdd, nbln, nblp, code): HD3}"""
    import corner_start_fig as CS
    out = {}
    f = os.path.join(SU, f"corner_release_{V.CHIP}.json")
    if os.path.exists(f):
        for k, r in json.load(open(f)).items():
            c, vdd, tag, ib = k.split("|")
            n, p = (4, 4) if not tag else tuple(int(q) for q in tag[3:].split("-"))
            out[(c, float(vdd), n, p, int(ib))] = r["hd3"]
    fc = os.path.join(SU, f"corner_release_340_{V.CHIP}.json")
    cache = json.load(open(fc)) if os.path.exists(fc) else {}
    for c, av, n, p in CHIP_RUNS:
        key = f"{c}|{av:g}|{n}/{p}"
        if key not in cache:
            r = CS.load(CS.name(c, av, f"_bt{n}-{p}"))
            if r is None:
                continue
            a = CS.analyse(*r)
            if not a["done"]:
                continue
            cache[key] = dict(hd2=float(a["hd2"]), hd3=float(a["hd3"]), gain=float(a["gain"]), off=float(a["off"]))
            json.dump(cache, open(fc, "w"), indent=1)
        out[(c, av, n, p, 3)] = cache[key]["hd3"]
    return out


def avdd_of(r):
    vd, vs = CHIP[r["corner"]]
    return round(r["vdd"] + vs - vd + 3.3, 4)


def main():
    # every frozen-phase run of the window: the first pass (hd_window_v1.json, trims picked on .op runs that sometimes
    # failed) and the recheck with DC sweeps (hd_window.json); per point the trim with the best HD3 is "best"
    win, seen = [], set()
    for f in ("hd_window.json", "hd_window_v1.json"):
        fp = os.path.join(MAP, f)
        if os.path.exists(fp):
            for r in json.load(open(fp)):
                k = (r["corner"], round(r["avdd"], 4), r["nbln"], r["nblp"])
                if k not in seen and r["hd_out"]:
                    seen.add(k)
                    win.append(r)
    for r in win:
        r["best"] = False
    for c in CORNER:
        for av in sorted({r["avdd"] for r in win if r["corner"] == c}):
            here = [r for r in win if r["corner"] == c and abs(r["avdd"] - av) < 1e-6]
            min(here, key=lambda r: r["hd_out"][1])["best"] = True
    cal = json.load(open(os.path.join(MAP, "calib.json")))
    f3 = os.path.join(MAP, "map_fine3.json")                       # the sweep-based map (11/16), else the first one
    fine = json.load(open(f3 if os.path.exists(f3) else os.path.join(MAP, "map_fine.json")))
    chip = chip_points()
    avdds = sorted({r["avdd"] for r in win})
    interim = any((c, av, n, p, 3) not in chip for c, av, n, p in CHIP_RUNS)
    fig = V.figure(12.8, 10.6, "The AFE's headroom window: full-scale HD3 against AVDD at each corner" +
                   (" (interim)" if interim else ""),
                   "eeg_afe (schematic) with the real eeg_bias, the AFE's supply and VCM as the r12 chip gives them "
                   "(AVDD_AFEI − AVSS_AFEI = 3.196 V at a board AVDD of 3.3 V, typical) · AFE_IBIAS 3 · one chopper phase "
                   "frozen, a full-scale 1 kHz sine, the ADC's input resistors as the load · 27 °C",
                   note="Bench: afe_margin_map.py --hd-window (the AFE output's HD3 after the output chopper's switches; "
                        "8 signal periods). 'Best trim run': candidates are the BOOST_TRIM settings (PMOS-cascode / NMOS-cascode booster "
                        "units 2/4/6/8) with the largest full-scale margin (VDS − VDSAT of the cascodes and the booster "
                        "loads at OPI − ONI = ±0.30 V, pairs and tails at least 50 mV in saturation), picked twice "
                        "(.op runs, then DC sweeps); the one with the best HD3 is drawn (4/4 included). Chip (stars): "
                        "figure 38's releases, and the 3.40 V runs with the bench's trims (also at 3.366–3.465 V), on the chip's "
                        "own wiring (2 kHz, the chopped AFE into the ADC's input resistors). The PMOS-cascode boosters sit "
                        "on AVDD while the output common mode sits on VCM, so the PMOS cascodes lose what the AFE's "
                        "supply loses; BOOST_TRIM moves the split by tens of mV.")
    gs0 = fig.add_gridspec(2, 1, height_ratios=[1.05, 1])
    top = gs0[0].subgridspec(1, 5, wspace=0.08)
    bot = gs0[1].subgridspec(1, 3, width_ratios=[1.0, 1.15, 0.62], wspace=0.28)
    for i, (c, (col, lab)) in enumerate(CORNER.items()):
        ax = fig.add_subplot(top[0, i])
        rows = [r for r in win if r["corner"] == c and r["hd_out"]]
        r44 = sorted([r for r in rows if (r["nbln"], r["nblp"]) == (4, 4)], key=lambda r: r["avdd"])
        rb = sorted([r for r in rows if r["best"]], key=lambda r: r["avdd"])
        for rr, mk, cc, ls in ((r44, "o", LIGHT, "-"), (rb, "D", col, "-")):
            if not rr:
                continue
            x = [r["avdd"] for r in rr]
            y = [min(r["hd_out"][1], YLIM[1] - 0.5) for r in rr]           # worse than the axis: at the top
            ax.plot(x, y, color=cc, lw=1.1, ls=ls, zorder=2)
            ax.plot(x, y, mk, color=cc, ms=5.2 if mk == "D" else 5.5, mfc="white" if mk == "D" else cc, mew=1.2, zorder=3)
            for r in rr:
                if r["hd_out"][1] > YLIM[1]:
                    ax.annotate(f"{r['hd_out'][1]:.0f}".replace("-", "−"), (r["avdd"], YLIM[1] - 0.5), xytext=(0, -9),
                                textcoords="offset points", ha="center", fontsize=6.6, color=cc)
        for r in rb:
            if (r["nbln"], r["nblp"]) != (4, 4):
                y0 = min(r["hd_out"][1], YLIM[1] - 0.5)
                # a chip star just below the point would cover the label: put it to the left instead
                hit = any(cc == c and abs(av - r["avdd"]) < 0.01 and 0 < y0 - min(h, YLIM[1] - 0.5) < 4.5
                          for (cc, av, n, p, ib), h in chip.items())
                ax.annotate(f"{r['nbln']}/{r['nblp']}", (r["avdd"], y0), xytext=(-7, -2) if hit else (0, -11),
                            textcoords="offset points", ha="right" if hit else "center", va="center" if hit else "baseline",
                            fontsize=6.6, color=col)
        for (cc, av, n, p, ib), h in chip.items():
            if cc == c and ib == 3:
                ax.plot(av, min(h, YLIM[1] - 0.5), "*", color=col if (n, p) != (4, 4) else INK2, ms=10, mec="white",
                        mew=0.5, zorder=4)
                if h > YLIM[1]:
                    ax.annotate(f"{h:.0f}".replace("-", "−"), (av, YLIM[1] - 0.5), xytext=(7, -4), textcoords="offset points",
                                fontsize=6.6, color=col)
        ax.axhline(HD_SPEC, color=MUTED, lw=0.9, ls=(0, (3, 2)))
        ax.axvline(3.3, color=LIGHT, lw=0.8)
        ax.set_ylim(*YLIM)
        ax.set_xlim(3.11, 3.49)
        ax.set_xticks([3.135, 3.3, 3.465], ["3.135\n(−5 %)", "3.3", "3.465\n(+5 %)"])
        ax.set_title(lab, loc="left", color=col)
        if i == 0:
            ax.set_ylabel("HD3 at full scale (dBc)")
            ax.text(3.12, HD_SPEC + 0.8, "requirement", fontsize=7, color=MUTED, va="bottom")
        else:
            ax.tick_params(labelleft=False)
        ax.set_xlabel("Board AVDD (V)", fontsize=8)
    # legend in the first panel
    ax = fig.axes[0]
    ax.plot([], [], "o-", color=LIGHT, ms=5, lw=1.1, label="bench, trim 4/4 (reset)")
    ax.plot([], [], "D-", color=INK2, ms=5, mfc="white", lw=1.1, label="bench, best trim run (P/N units)")
    ax.plot([], [], "*", color=INK2, ms=9, label="chip, 2 kHz (figure 38, and the 3.40 V trims)")
    ax.legend(loc="lower left", fontsize=6.8)

    # calibration: per chip run, the chip's 2 kHz HD3 and the bench's at the same corner, AVDD, trim and AFE_IBIAS
    ax = fig.add_subplot(bot[0, 0])
    order = list(CORNER)
    rows = sorted([r for r in cal if r["chip_hd3"] is not None and r["tran"]],
                  key=lambda r: (r["key"][4], order.index(r["key"][0]), -r["key"][1], r["key"][2], r["key"][3]))
    XL = (-123, -84)
    labels, diffs = [], []
    for i, r in enumerate(rows):
        c, code, n, p, av = r["key"]
        col = CORNER[c][0]
        xc, xb = r["chip_hd3"], r["tran"]["out"]["hd"][1]
        diffs.append((xb - xc, r["key"]))
        y = len(rows) - 1 - i
        cx, bx = min(xc, XL[1] - 0.6), min(xb, XL[1] - 0.6)
        ax.plot([cx, bx], [y, y], color=LIGHT, lw=1.6, zorder=1, solid_capstyle="round")
        ax.plot(cx, y, "*", color=col, ms=9.5, mec="white", mew=0.4, zorder=3)
        ax.plot(bx, y, "D", color=col, ms=4.8, mfc="white", mew=1.1, zorder=2)
        if max(xc, xb) > XL[1]:
            ax.text(XL[1] - 1.6, y + 0.05, f"off the axis: chip {xc:.0f}, bench {xb:.0f}".replace("-", "−"), ha="right", va="center",
                    fontsize=6.4, color=col)
        labels.append(f"{c} {av:g} V {n}/{p}" + (" (AFE_IBIAS 2)" if code == 2 else ""))
    ax.set_yticks(range(len(rows)), labels[::-1], fontsize=6.8)
    for t, r in zip(ax.get_yticklabels(), rows[::-1]):
        t.set_color(CORNER[r["key"][0]][0])
    ax.axvline(HD_SPEC, color=MUTED, lw=0.9, ls=(0, (3, 2)))
    ax.set_xlim(*XL)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xlabel("HD3 at full scale (dBc)")
    ax.grid(axis="y", visible=False)
    ax.plot([], [], "*", color=INK2, ms=9, label="chip, 2 kHz")
    ax.plot([], [], "D", color=INK2, ms=4.8, mfc="white", mew=1.1, label="bench, 1 kHz, frozen phase")
    ax.legend(loc="lower right", fontsize=6.6)
    worse = [d for d, k in diffs if d >= 0]
    better = [(d, k) for d, k in diffs if d < 0]
    tb = f"the bench reads {min(worse):.1f}–{max(worse):.1f} dB worse" if worse else ""
    if better:
        kinds = {(k[0], k[2], k[3]) for d, k in better}
        lo_, hi_ = min(-d for d, k in better), max(-d for d, k in better)
        rng_ = f"{lo_:.1f}" if abs(hi_ - lo_) < 0.05 else f"{lo_:.1f}–{hi_:.1f}"
        tb += (f",\nbetter only at {next(iter(kinds))[0]} {next(iter(kinds))[1]}/{next(iter(kinds))[2]} (by {rng_} dB)"
               if len(kinds) == 1 else f",\nbetter at {len(better)} runs (by {rng_} dB)")
    ax.set_title("Bench against chip, per chip run: " + tb.replace("-", "−"), loc="left", fontsize=8.6)

    # margins against AVDD (the fine map): best trim, and 4/4
    ax = fig.add_subplot(bot[0, 1])
    for c, (col, lab) in CORNER.items():
        rows = [r for r in fine if r["corner"] == c and r["code"] == 3]
        xs = sorted({avdd_of(r) for r in rows})
        best, r44 = [], []
        for av in xs:
            here = [r for r in rows if abs(avdd_of(r) - av) < 1e-6]
            ok = [r for r in here if min(r["pp"], r["np"], r["tail"]) >= 0.05]
            best.append(max((min(r["pc"], r["nc"], r["boost"]) for r in ok), default=np.nan))
            q = [r for r in here if (r["nbln"], r["nblp"]) == (4, 4)]
            r44.append(min(q[0]["pc"], q[0]["nc"], q[0]["boost"]) if q and min(q[0]["pp"], q[0]["np"]) >= 0 else np.nan)
        ax.plot(xs, best, color=col, lw=1.4, label=f"{c}, best trim")
        ax.plot(xs, r44, color=col, lw=0.9, ls=(0, (3, 2)), alpha=0.8)
    ax.plot([], [], color=INK2, lw=0.9, ls=(0, (3, 2)), label="trim 4/4")
    ax.axhline(0, color=LIGHT, lw=0.8)
    ax.axvline(3.3, color=LIGHT, lw=0.8)
    ax.set_xlabel("Board AVDD (V)")
    ax.set_ylabel("Smallest full-scale margin of the cascodes\nand booster loads, VDS − VDSAT (V)")
    ax.legend(loc="lower right", fontsize=6.8, ncol=2)
    ax.set_title("The margin behind it: one for one with AVDD on the PMOS\nside (solid: best of 4/4, 2/2, 4/2, 6/2, 8/2; dashed: 4/4)",
                 loc="left")

    # the trims at 3.3 V: bench best, the 10/22 table, chip
    ax = fig.add_subplot(bot[0, 2])
    ax.set_axis_off()
    table = {"typical": "4/4", "ss": "2/2", "ff": "8/6", "fs": "2/6", "sf": "8/4"}
    lines = ["Trims (P/N units), AFE_IBIAS 3, HD3 (dBc)", "",
             "          10/22    AVDD 3.3 V        AVDD 3.40 V",
             "corner    table    chip, table trim  trim  chip"]
    for c in CORNER:
        t3 = chip.get((c, 3.3) + tuple(int(q) for q in table[c].split("/")) + (3,))
        if t3 is None and c == "ff":
            t3 = chip.get(("ff", 3.3, 4, 4, 3))
        r34 = [(n, p) for cc, n, p in RUNS_340 if cc == c]
        h34 = chip.get((c, 3.4) + r34[0] + (3,)) if r34 else None
        lines.append(f"{c:9s} {table[c]:>5s}    " + (f"{t3:7.1f}" + (" (4/4)" if c == "ff" else "      ")
                                                         if t3 is not None else "      –      ") +
                     f"     {r34[0][0]}/{r34[0][1]}  " + (f"{h34:6.1f}" if h34 is not None else "(running)"))
    lines += ["", "Other AVDDs, the 3.40 V trims:"]
    for c, av, n, p, lab in sorted(EDGES, key=lambda e: e[1]):
        h = chip.get((c, av, n, p, 3))
        lines.append(f"{c:3s} {av:.3f} V {n}/{p} " + (f"{h:6.1f}" if h is not None else "(running)") + f"  {lab}")
    # the window's edges on the chip with these trims: ss's lower edge between its runs, ff's PMOS pair margin (bench)
    ssp = sorted((av, h) for (cc, av, n, p, ib), h in chip.items() if cc == "ss" and (n, p) == (2, 2) and ib == 3 and av > 3.35)
    edge = next((a0 + (HD_SPEC - h0) * (a1 - a0) / (h1 - h0) for (a0, h0), (a1, h1) in zip(ssp, ssp[1:])
                 if h0 > HD_SPEC >= h1), None)
    if edge:
        lines.append(f"ss reaches −111 dBc at {edge:.3f} V (between runs)")
    pp = {r["key"][4]: r["margins"]["pp"] for r in cal if r["key"][:4] == ["ff", 3, 8, 2] and r["margins"]}
    if 3.465 in pp and 3.4845 in pp:
        lines += [f"ff's PMOS pair margin (bench): {pp[3.465] * 1e3:.0f} mV",
                  f"at 3.465 V, {pp[3.4845] * 1e3:.0f} mV at 3.4845 V (aim: 50)"]
    lines += ["", "ff at 3.3 V: the table's 8/6 not run on the chip.", "Requirement: −111 dBc."]
    ax.text(0.0, 0.98, "\n".join(lines).replace("-", "−"), transform=ax.transAxes, va="top", fontsize=8.0, color=INK,
            family="monospace", linespacing=1.55)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_41_afe_window.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()
