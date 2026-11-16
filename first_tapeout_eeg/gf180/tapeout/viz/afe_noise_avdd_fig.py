#!/usr/bin/env python3
"""Figure 42 (r12, 11/16): the AFE's noise against the board AVDD and BOOST_TRIM, on the chip's own wiring
(gf180/tapeout/pex/afe_chip_noise.py --avdd --boost --corner: afe_top, eeg_bias and eeg_ref extracted on the chip
wiring, pads, board, one chopper phase frozen, the chopped in-band noise 0.5-100 Hz at the input, AFE_IBIAS 3, the
corner's typical models, 27 C). With it, the PMOS input pair's margin (VSD - VDSAT at the operating point,
afe_chip_noise.op_margins) that sets it, and the noise budget's ENOB with each case's AFE noise.

The trims are BTRIM_P/BTRIM_N in units (2 / 4 / 6 / 8), the order of the margin map's NBLN/NBLP and of figure 41:
BTRIM_P sets the PMOS-cascode boosters (their NMOS loads, the BLN leg).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/afe_noise_avdd_fig.py
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import ACCENT, INK, INK2, LIGHT, MUTED, plt  # noqa: E402

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
os.environ.setdefault("EEG_PEX_REV", V.CHIP)
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "pex"))
_argv, sys.argv = sys.argv, sys.argv[:1]
import afe_chip_noise as N  # noqa: E402
sys.argv = _argv

SU = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
TEAL, AMBER, PLUM = "#0d9488", "#b45309", "#a21caf"
CODE = {2: 0, 4: 1, 6: 2, 8: 3}
# the corners with the 3.40 V trims of figure 41 (the margin map's), and typical's reset value 4/4
SERIES = [("typical", 2, 2, INK, "-", "typical 2/2 (the 3.40 V map's trim)"),
          ("typical", 4, 4, INK, (0, (5, 2.5)), "typical 4/4 (the reset value)"),
          ("typical", 4, 2, INK, (0, (1, 1.6)), "typical 4/2 (the proposal for 11/18)"),
          ("ss", 2, 2, ACCENT, "-", "ss 2/2"), ("ff", 8, 2, AMBER, "-", "ff 8/2"),
          ("sf", 8, 2, PLUM, "-", "sf 8/2 (PMOS fast)"), ("fs", 2, 2, TEAL, "-", "fs 2/2 (NMOS fast)")]
AVDDS = {("typical", 2, 2): [3.3, 3.35, 3.4, 3.415, 3.43, 3.44, 3.45, 3.465], ("ss", 2, 2): [3.3, 3.366, 3.4, 3.43, 3.45, 3.465],
         ("ff", 8, 2): [3.3, 3.4, 3.43, 3.434, 3.45, 3.465], ("sf", 8, 2): [3.3, 3.4, 3.43, 3.434, 3.45, 3.465]}
TRIMS = [(p, n) for n in (2, 4) for p in (2, 4, 6, 8) if (p, n) != (8, 4)]   # typical's trim sweep (8/4 not run)
TRIM_AVDDS = [3.3, 3.4, 3.43, 3.45]
WINDOW = (3.394, 3.456)        # figure 41: the chip window with the 3.40 V trims
FIXED = (3.413, 3.447)         # the fixed option, 3.43 V +-0.5 %
# the noise budget (gf180_realistic_eval_20261028.md, 11/12): 16.57 bit with typical's AFE noise at 3.30 V, 4/4,
# AFE_IBIAS 3; the rest (ADC side, blanking) 1.683 nVrms in quadrature
BUDGET_BITS, REST = 16.57, 1.683


def case(c, p, n, av):
    d = N.run_dir("chip", "A", 3, None, "fill", av, (CODE[p], CODE[n]), c)
    if not os.path.exists(os.path.join(d, "noise.raw")):
        return None
    r = N.analyze(d)
    r.update(N.op_margins(d))
    return r


def bits(noise, ref):
    return BUDGET_BITS - math.log2(math.hypot(noise, REST) / math.hypot(ref, REST))


NOISE_TYPES = {"id", "1overf", "igs", "igd", "igb", "rd", "rs", "rg", "rb", "thermal", "1overfsw", "idsw", "corl", "ig"}


def device_noise(c, p, n, av):
    """the chopped in-band noise at the input per device (V^2), the noise sources of a device summed"""
    d = N.run_dir("chip", "A", 3, None, "fill", av, (CODE[p], CODE[n]), c)
    ac = np.loadtxt(os.path.join(d, "ac.csv"))
    f, h = ac[:, 0], ac[:, 1] + 1j * ac[:, 3]
    nz = N.afe_noise.read_raw(os.path.join(d, "noise.raw"))
    fn = nz["frequency"]
    kmax = int(fn[-1] / N.P.FCH) - 1
    g = abs(N.afe_noise.chop_sum(f, h.real, kmax, N.P.FCH))
    bw = N.P.BAND[1] - N.P.BAND[0]
    ent = {k[7:]: v for k, v in nz.items() if k.startswith("onoise.") or (k.startswith("onoise_") and k != "onoise_spectrum")}
    dev = {}
    for e, sp in ent.items():
        for sep in (".", "_"):
            par, _, typ = e.rpartition(sep)
            if par and typ in NOISE_TYPES:
                break
        else:
            par, typ = e, ""
        if typ and par in ent:          # a part of a device total that is itself in the file
            continue
        dev[par] = dev.get(par, 0.0) + N.afe_noise.chop_sum(fn, np.nan_to_num(sp) ** 2, kmax, N.P.FCH) * bw / g ** 2
    return dev


def chip_hd3(p, n, av):
    """typical with BTRIM_P/BTRIM_N p/n units at the chip level (afe_trim_start.py, tag _bt<p>-<n>), analysed as figure
    41 analyses its chip runs (corner_start_fig.analyse) and cached in the same file; None while the run is missing or
    unfinished"""
    import corner_start_fig as CS
    fc = os.path.join(SU, f"corner_release_340_{V.CHIP}.json")
    cache = json.load(open(fc)) if os.path.exists(fc) else {}
    key = f"typical|{av:g}|{p}/{n}"
    if key not in cache:
        r = CS.load(CS.name("typical", av, f"_bt{p}-{n}"))
        if r is None:
            return None
        a = CS.analyse(*r)
        if not a["done"]:
            return None
        cache[key] = dict(hd2=float(a["hd2"]), hd3=float(a["hd3"]), gain=float(a["gain"]), off=float(a["off"]))
        json.dump(cache, open(fc, "w"), indent=1)
    return cache[key]["hd3"]


def main():
    data = {}
    for c, p, n, *_ in SERIES:
        for av in AVDDS.get((c, p, n), TRIM_AVDDS):
            r = case(c, p, n, av)
            if r is not None:
                data[(c, p, n, av)] = r
    for p, n in TRIMS:
        for av in TRIM_AVDDS:
            r = case("typical", p, n, av)
            if r is not None:
                data[("typical", p, n, av)] = r
    ref = data[("typical", 4, 4, 3.3)]["total"]
    hd = {(p, n, av): chip_hd3(p, n, av) for p, n, av in ((4, 4, 3.4), (4, 4, 3.45), (4, 2, 3.4))}
    interim = any(v is None for v in hd.values())

    fig = V.figure(12.8, 10.4, "The AFE's noise against AVDD and BOOST_TRIM: the PMOS input pair's margin sets it" +
                   (" (interim)" if interim else ""),
                   "afe_top, eeg_bias and eeg_ref extracted on the r12 chip's own wiring, pads, board and bond wires · one "
                   "chopper phase frozen, the chopped in-band noise (0.5–100 Hz) at the electrodes · AFE_IBIAS 3 · each "
                   "corner's typical models (no Monte Carlo) · 27 °C · trims BTRIM_P/BTRIM_N in units (2/4/6/8), the "
                   "order of figure 41",
                   note="afe_chip_noise.py --avdd --boost --corner (runs/chip_noise_r12/), the board AVDD alone raised "
                        "(DVDD and the trim lines at 3.3 V). The margin: |VDS| − |VDSAT| of the input pair's devices at the "
                        "operating point (op_margins, the smaller half). ENOB: the noise budget of 11/12 (16.57 bit with "
                        "typical's AFE noise at 3.30 V, 4/4), only the AFE's noise changed, the rest 1.683 nVrms in "
                        "quadrature. Window and fixed option: figure 41.")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.86])

    # (a) noise against AVDD
    ax = fig.add_subplot(gs[0, 0])
    ax.axvspan(*WINDOW, color=ACCENT, alpha=0.06, lw=0)
    ax.text(np.mean(WINDOW), 6.03, "figure 41's window", ha="center", va="top", fontsize=7.4, color=ACCENT)
    for x in FIXED:
        ax.axvline(x, color=LIGHT, lw=0.8, ls=(0, (2, 2)))
    ax.text(FIXED[1] + 0.002, 5.02, "3.43 V\n±0.5 %", fontsize=7, color=MUTED, va="bottom")
    for c, p, n, col, ls, lab in SERIES:
        pts = sorted((av, r["total"]) for (cc, pp, nn, av), r in data.items() if (cc, pp, nn) == (c, p, n))
        if not pts:
            continue
        x, y = zip(*pts)
        ax.plot(x, y, color=col, ls=ls, lw=1.6 if (c, p, n) == ("typical", 2, 2) else 1.2,
                marker="s" if (c, p, n) == ("typical", 4, 2) else "o", ms=3.2, label=lab)
    ax.set_xlim(3.29, 3.475)
    ax.set_ylim(5.0, 6.05)
    ax.set_xlabel("Board AVDD (V)")
    ax.set_ylabel("AFE noise at the input, 0.5–100 Hz (nVrms)")
    ax.legend(loc="upper left", fontsize=7.6)
    t22 = {av: data[("typical", 2, 2, av)]["total"] for av in (3.3, 3.45) if ("typical", 2, 2, av) in data}
    ax.set_title("Typical with the map's 2/2 trim gets noisier as AVDD rises" +
                 (f":\n{t22[3.3]:.2f} nVrms at 3.30 V, {t22[3.45]:.2f} at 3.45 V; with 4/2 or 4/4 it stays flat" if len(t22) == 2 else ""),
                 loc="left")

    # (b) noise against the PMOS pair's margin
    ax = fig.add_subplot(gs[0, 1])
    col = {c: k for c, _, _, k, *_ in SERIES}
    for (c, p, n, av), r in sorted(data.items()):
        filled = not (c == "typical" and p != 2)
        ax.plot(r["pmos_pair"] * 1e3, r["total"], ls="none", marker="o", ms=4.6, color=col[c],
                mfc=col[c] if filled else "white", mew=1.0)
    for c, _, _, k, _, lab in (s for s in SERIES if s[0] != "typical"):
        ax.plot([], [], ls="none", marker="o", ms=4.6, color=k, label=lab)
    ax.plot([], [], ls="none", marker="o", ms=4.6, color=INK, label="typical, BTRIM_P 2 (2/2, 2/4)")
    ax.plot([], [], ls="none", marker="o", ms=4.6, color=INK, mfc="white", mew=1.0, label="typical, BTRIM_P 4, 6, 8")
    ax.set_xlim(0, 400)
    ax.set_ylim(5.0, 6.05)
    ax.set_xlabel("PMOS input pair's margin, |VSD| − |VSDsat| at the operating point (mV)")
    ax.set_ylabel("AFE noise at the input (nVrms)")
    ax.legend(loc="upper right", fontsize=7.6)
    ax.set_title("Each corner has its own level, and its noise rises once the PMOS\npair's margin falls below about 100 mV",
                 loc="left")

    # (c) typical against BTRIM_P
    ax = fig.add_subplot(gs[1, 0])
    shades = {3.3: LIGHT, 3.4: MUTED, 3.43: INK2, 3.45: INK}
    for av in TRIM_AVDDS:
        for n, ls in ((2, "-"), (4, (0, (4, 2)))):
            pts = [(p, data[("typical", p, n, av)]["total"]) for p in (2, 4, 6, 8) if ("typical", p, n, av) in data]
            if len(pts) < 2:
                continue
            x, y = zip(*pts)
            ax.plot(x, y, color=shades[av], ls=ls, lw=1.2, marker="o", ms=3.2,
                    label=f"{av:.2f} V" + (", BTRIM_N 2" if n == 2 else ", BTRIM_N 4"))
    ax.set_xticks([2, 4, 6, 8])
    ax.set_xlabel("BTRIM_P (units of the PMOS-cascode boosters' current)")
    ax.set_ylabel("AFE noise at the input (nVrms)")
    ax.set_ylim(5.2, 5.8)
    ax.legend(loc="upper right", fontsize=7.2, ncol=2)
    ax.set_title("Typical: BTRIM_P of 4 or more keeps the noise flat; BTRIM_N hardly matters", loc="left")

    # (d) the numbers
    ax = fig.add_subplot(gs[1, 1])
    ax.set_axis_off()
    lines = ["ENOB of the noise budget with each case's AFE noise:"]
    for c, p, n, avs in (("typical", 2, 2, (3.4, 3.43, 3.45)), ("typical", 4, 4, (3.4, 3.43, 3.45)),
                         ("typical", 4, 2, (3.4, 3.43, 3.45)),
                         ("ss", 2, 2, (3.3, 3.45)), ("ff", 8, 2, (3.43, 3.45)), ("sf", 8, 2, (3.43, 3.45)), ("fs", 2, 2, (3.43, 3.45))):
        got = [(av, data[(c, p, n, av)]["total"]) for av in avs if (c, p, n, av) in data]
        if got:
            lines.append(f"  {c} {p}/{n}: " + ", ".join(f"{bits(x, ref):.2f} bit at {av:.2f} V" for av, x in got))
    da, db = device_noise("typical", 2, 2, 3.3), device_noise("typical", 2, 2, 3.45)
    dd = {k: db.get(k, 0.0) - da.get(k, 0.0) for k in set(da) | set(db)}
    boost = sum(dd.get(f"m.xdut.{x}.m0", 0.0) for x in ("x429", "x430", "x419", "x420"))
    pairs = sum(dd.get(f"m.xdut.{x}.m0", 0.0) for x in ("x424", "x425", "x427", "x428"))
    sw = {av: case("ff", 2, 8, av) for av in (3.3, 3.4)}
    m22 = {av: data[("typical", 2, 2, av)]["pmos_pair"] for av in (3.3, 3.4, 3.45) if ("typical", 2, 2, av) in data}
    m44 = data.get(("typical", 4, 4, 3.45), {}).get("pmos_pair")
    lines += ["",
              "Why: the PMOS-cascode boosters are referenced to AVDD, so raising AVDD",
              "raises the PMOS input pair's drain and its VSD shrinks",
              "  typical 2/2: " + ", ".join(f"{m * 1e3:.0f} mV at {av:.2f} V" for av, m in m22.items()) +
              (f"; 4/4 at 3.45 V: {m44 * 1e3:.0f} mV" if m44 else ""),
              f"  of the {sum(dd.values()) * 1e18:.2f} nV² added from 3.30 to 3.45 V (typical 2/2), {boost * 1e18:.2f} nV² are "
              "the boosters'",
              f"  (X429/X430) and their loads' (X419/X420); the pairs themselves add {pairs * 1e18:.2f} nV²",
              ""]
    if all(sw.values()) and ("ff", 8, 2, 3.3) in data:
        g0 = data[("ff", 8, 2, 3.3)]["gain"]
        lines += ["The trims swapped (BTRIM_P 2, BTRIM_N 8) at ff: the PMOS pair leaves saturation",
                  (f"even at 3.30 V (margin {sw[3.3]['pmos_pair'] * 1e3:.0f} mV), {sw[3.3]['total']:.1f} nVrms, gain "
                   f"{(sw[3.3]['gain'] / g0 - 1) * 100:+.0f} %; at 3.40 V {sw[3.4]['total']:.0f} nVrms").replace("-", "−"),
                  ""]
    h22 = json.load(open(os.path.join(SU, f"corner_release_340_{V.CHIP}.json")))["typical|3.4|2/2"]["hd3"]
    lines += ["Chip HD3 of typical with BTRIM_P 4 (2 kHz, figure 41's requirement −111 dBc;",
              f"2/2 at 3.40 V: {h22:.1f} dBc):".replace("-", "−")]
    for (p, n, av), h in hd.items():
        lines.append(f"  {p}/{n} at {av:.2f} V: " + (f"{h:.1f} dBc".replace("-", "−") if h is not None else "running"))
    if not interim:
        worst = max(hd.values())
        dd3 = {pn: hd[(*pn, 3.4)] - h22 for pn in ((4, 2), (4, 4))}
        word = lambda d: f"{abs(d):.1f} dB " + ("better" if d < 0 else "worse")     # noqa: E731
        lines += [f"So at 3.40 V, 4/2 is {word(dd3[(4, 2)])} than 2/2 and 4/4 {word(dd3[(4, 4)])}; every case",
                  f"   leaves {-111 - worst:.1f} dB or more to the requirement, and the noise stays flat"]
    ax.text(0.0, 1.0, "\n".join(lines), transform=ax.transAxes, va="top", fontsize=8.4, color=INK, linespacing=1.5)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"gf180_viz_{V.CHIP}_42_afe_noise_avdd.png")
    fig.savefig(path)
    plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    main()
