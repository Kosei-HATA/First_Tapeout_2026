#!/usr/bin/env python3
"""Figures 59 and 60 (chip r15, 11/28): the r15 macro's simulated pin waveforms against the specification's timing
diagrams (gf180/tapeout/digital/gl_r15/wave_sim_r15.py; the VCDs of run_wave_r15.sh, the RTL and the final netlist with
the SDF of max ss, nom tt and min ff in lockstep).

  59 (a) one chopper-edge frame at the pins: the frame diagram's levels (wave_frame.json, from fsm_spec.TIMING; the
         blanking by its rule at the run's BLANK_LEN 7), the RTL and the netlist at the three corners
     (b) each output's delay after the MCLK edge that launched it, netlist, three corners (shortest to longest)
  60 (a) the LATEST read at the pins (netlist, max ss): CS_N, SCLK, MOSI, MISO and the decoded bytes
     (b) one byte boundary: MISO after SCLK's fall at the three corners and in the RTL, against the next rising edge

usage: r15_waveform_fig.py [<run folder gl_<tag>>]
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import HAIR, INK, INK2, LIGHT, MUTED  # noqa: E402

V.CHIP, V.CHIP_DATE = "r15", "20261128"
V.CHIP_LABEL = "Chip r15 (fifteenth assembly rebuilt with macro r15m13, 28 Nov 2026)"
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "digital", "gl_r15"))
import wave_sim_r15 as W  # noqa: E402

RUN = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "gf180", "tapeout", "digital", "eeg_digital_top_r15",
                                                         "runs", "gl_r15m13_20261128")
OUT = os.environ.get("R15_FIG_OUT") or os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
# the corners: one hue each in a fixed order, and a line style as the second code (never colour alone)
CORN = [("max_ss_125C_3v00", "max ss 125 °C 3.0 V", "#1d4ed8", "-"),
        ("nom_tt_025C_3v30", "nom tt 25 °C 3.3 V", "#0d9488", "--"),
        ("min_ff_n40C_3v60", "min ff −40 °C 3.6 V", "#d97706", ":")]
FRAME_PINS = ("CMP_STROBE", "TH_CAPTURE", "DAC_LOAD", "DAC_CLK", "CHOP", "CHOP_OUT", "CHOP_BLANK")
TB, SH, DUT = "gl_sdf_r15", "gl_shadow_r15", "gl_sdf_r15.dut"


def load(c):
    want = ({(TB, "MCLK"), (DUT, "cycle"), (DUT, "a_blank_len")} | {(TB, p) for p in W.PINS + W.SPI_PINS}
            | {(SH, p.lower()) for p in W.PINS})
    return W.read_vcd(os.path.join(RUN, "wave", f"{c}.vcd"), want)


def steps(ch, t0, t1):
    """x (ns), y (0/1) of a change list between t0 and t1 (ps), as a step line (the value at t0 after its changes)."""
    v0 = W.value_at(ch, t0 + 1)
    xs, ys = [t0], [v0]
    for t, v in ch:
        if t0 < t < t1:
            xs += [t, t]
            ys += [ys[-1], v]
    xs.append(t1)
    ys.append(ys[-1])
    y = np.array([1.0 if v == "1" else 0.0 if v == "0" else 0.5 for v in ys])
    return (np.array(xs) - t0) / 1e3, y


def fig59(sig, res):
    V.apply()
    fig = V.figure(12.0, 8.4, "r15 macro: the simulated pin waveforms equal the frame diagram",
                   "One chopper-edge frame at the macro's pins: the specification's levels (grey), the RTL, and the "
                   "final netlist with the SDF of three corners in lockstep; and every output's delay after its MCLK edge",
                   note="Capture: gl_sdf_r15.sv with GL_WAVE_VCD (run_wave_r15.sh), 80 frames in RUN with a LATEST "
                        "and a sample read; compared with wave_frame.json (generated from fsm_spec.TIMING) by "
                        "wave_sim_r15.py in every frame and cycle, the value just before the edge that ends the cycle. "
                        "CHOP_BLANK by its rule (cycle 31 and cycles 0 .. L − 1 of an edge frame, L the length in "
                        "effect: 15 while the offset DAC is on, as in this RUN with range 1 and in the diagram). Times "
                        "from the MCLK pin edge e0 of the frame. (b) leaves out MISO_OE, which follows CS_N, not MCLK.")
    gs = fig.add_gridspec(1, 2, width_ratios=[2.15, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    s0 = sig[CORN[0][0]]
    mclk = s0[(TB, "MCLK")]
    rise = [t for (t, v), (_t, v0) in zip(mclk[1:], mclk[:-1]) if v == "1" and v0 == "0"]
    half = (rise[1] - rise[0]) / 2
    cyc = s0[(DUT, "cycle")]
    cyc_of = [int(W.value_at(cyc, r + half), 2) for r in rise]
    lv = [W.value_at(s0[(TB, "CHOP")], rise[i + 1] - 1) for i in range(len(rise) - 1)]
    edge = next(i for i in range(1, len(lv)) if lv[i] != lv[i - 1] and cyc_of[i] == 0)
    T = rise[1] - rise[0]
    t0, t1 = rise[edge] - T, rise[edge] + 32 * T       # cycle 31 of the previous frame .. cycle 31
    S = W.spec_frame()
    blank_len = max(res[CORN[0][0]]["blank_len"])
    yb = len(FRAME_PINS)
    for k, p in enumerate(FRAME_PINS):
        base = (yb - 1 - k) * 1.6
        # the specification's level in each cycle (grey band)
        for j in range(33):
            c = 31 if j == 0 else j - 1
            if p in S["strobes"]:
                hi = c in S["strobes"][p][1]
            elif p == "CHOP_BLANK":
                hi = (j == 0) or (c < blank_len and j > 0)
            else:
                hi = None
            if hi:
                ax.fill_between([j * T / 1e3, (j + 1) * T / 1e3], base, base + 1.0, color="#e2e8f0", lw=0)
        x, y = steps(s0[(TB, p)], t0, t1)
        ax.plot(x, base + y, color=INK, lw=0.9, drawstyle="default", label="RTL" if k == 0 else None)
        for c, lab, col, ls in CORN:
            xg, yg = steps(sig[c][(SH, p.lower())], t0, t1)
            ax.plot(xg, base + yg * 0.92 + 0.04, color=col, lw=1.15, ls=ls, label=f"netlist {lab}" if k == 0 else None)
        ax.text(-1.5, base + 0.5, p, ha="right", va="center", fontsize=8.5, color=INK2)
    for j in range(34):
        ax.axvline(j * T / 1e3, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(0, 33 * T / 1e3)
    ax.set_ylim(-0.4, yb * 1.6 + 0.5)
    ax.set_yticks([])
    ax.grid(False)
    ax.set_xticks([(j + 0.5) * T / 1e3 for j in range(0, 33, 2)])
    ax.set_xticklabels(["31" if j == 0 else str(j - 1) for j in range(0, 33, 2)])
    ax.set_xlabel("frame cycle (column 0 is cycle 31 of the previous frame; 30.5 ns each)")
    ax.legend(loc="upper right", ncol=2, fontsize=8, framealpha=0.95)
    r0 = res[CORN[0][0]]
    ax.set_title("(a) A chopper-edge frame at the pins: grey = the specification's level in each cycle")
    # (b) delays
    bx = fig.add_subplot(gs[0, 1])
    pins = [p for p in W.PINS if p != "MISO_OE" and all(p in res[c]["delay"] for c, *_ in CORN)]   # MISO_OE: from CS_N
    for i, p in enumerate(pins):
        y = len(pins) - 1 - i
        for m, (c, lab, col, ls) in enumerate(CORN):
            d = res[c]["delay"][p]
            bx.plot([d["min_ns"], d["max_ns"]], [y + (m - 1) * 0.22] * 2, color=col, lw=2.2, ls="-",
                    solid_capstyle="round", label=lab if i == 0 else None)
            bx.plot([d["max_ns"]], [y + (m - 1) * 0.22], marker="o", ms=3.5, color=col)
    bx.set_yticks(range(len(pins)))
    bx.set_yticklabels(list(reversed(pins)), fontsize=8)
    bx.set_xlabel("delay after the launching MCLK pin edge (ns)")
    bx.set_xlim(0, 32)
    bx.axvline(30.5, color=LIGHT, lw=0.8, ls="--")
    bx.text(30.2, len(pins) - 0.4, "one MCLK\nperiod", ha="right", va="top", fontsize=7.5, color=MUTED)
    bx.legend(loc="center right", fontsize=7.5)
    worst = max(res[c]["delay"][p]["max_ns"] for c, *_ in CORN for p in pins if p not in ("MISO_OE",))
    bx.set_title(f"(b) Output delays, netlist with SDF (longest {worst:.1f} ns)")
    # the verdict line
    vtxt = "; ".join(f"{lab.split(' ')[0]} {lab.split(' ')[1]}: {res[c]['frames']} frames, "
                     f"{res[c]['frame']['netlist']['checks']} checks, {res[c]['frame']['netlist']['mismatches']} off"
                     for c, lab, *_ in CORN)
    fig.text(0.006, 0.06, "Netlist against the specification: " + vtxt + f" (RTL {r0['frame']['rtl']['checks']} "
             f"checks, {r0['frame']['rtl']['mismatches']} off)", fontsize=8.5, color=INK2, ha="left")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_59_frame_waveforms.png")
    fig.savefig(p)
    return p


def fig60(sig, res):
    V.apply()
    r = res[CORN[0][0]]
    lat = next(f for f in r["spi"]["frames"] if f["mosi"] and f["mosi"][0] == 0xCF)
    g = lat["miso_gl"]
    fig = V.figure(12.0, 7.2, "r15 macro: the LATEST read at the pins",
                   "The 8-byte frame of the LATEST window (0x4F, header 0xCF) from the final netlist with the SDF of "
                   "max ss, decoded at SCLK's rising edges; and MISO's change after SCLK's fall at three corners",
                   note=f"Bytes (netlist = RTL at every corner): {' '.join(f'{b:02X}' for b in g)}; the CRC "
                        f"0x{g[7]:02X} is the CRC-8 (0x07) of 0xCF and the six word bytes (it fails from the sample "
                        "header 0xC0), as the SPI diagram's LATEST frame (wave_spi.json). The bench's SPI master: SCLK "
                        "9 MCLK high and low (1.82 MHz), every edge at an MCLK falling edge; MISO through the pad "
                        "model (15 ns) to the master.")
    gs = fig.add_gridspec(1, 2, width_ratios=[2.0, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    s0 = sig[CORN[0][0]]
    cs = s0[(TB, "CS_N")]
    tf = lat["t_ns"] * 1e3
    tr = next(t for t, v in cs if v == "1" and t > tf)
    t0, t1 = tf - 2_000_000, tr + 2_000_000             # 2 µs either side (ps)
    lanes = [("CS_N", (TB, "CS_N")), ("SCLK", (TB, "SCLK")), ("MOSI", (TB, "MOSI")), ("MISO", (SH, "miso"))]
    for k, (nm, key) in enumerate(lanes):
        base = (len(lanes) - 1 - k) * 1.7
        x, y = steps(s0[key], t0, t1)
        ax.plot(x / 1e3, base + y, color=CORN[0][2] if nm == "MISO" else INK, lw=0.9)
        ax.text(-0.4, base + 0.5, nm, ha="right", va="center", fontsize=8.5, color=INK2)
    sclk = s0[(TB, "SCLK")]
    sr = [t for t, v in sclk if tf < t < tr and v == "1"]
    labs = ["STATUS", "状態", "SEQ 上", "SEQ 下", "DATA 上", "DATA 中", "DATA 下", "CRC"]
    labs_en = ["STATUS", "status", "SEQ hi", "SEQ lo", "DATA hi", "DATA mid", "DATA lo", "CRC"]
    for b in range(8):
        xa, xb = (sr[8 * b] - t0) / 1e6, (sr[8 * b + 7] - t0) / 1e6
        xm = (xa + xb) / 2
        ax.text(xm, 1.7 * 1 + 1.25, f"{lat['mosi'][b]:02X}", ha="center", fontsize=8, color=INK2)
        ax.text(xm, 1.25, f"{g[b]:02X}", ha="center", fontsize=8, color=CORN[0][2])
        ax.text(xm, -0.45, labs_en[b], ha="center", fontsize=7.5, color=MUTED)
    ax.set_xlim(0, (t1 - t0) / 1e6)
    ax.set_ylim(-0.8, 4 * 1.7)
    ax.set_yticks([])
    ax.grid(False)
    ax.set_xlabel("time from 2 µs before CS_N falls (µs)")
    ax.set_title("(a) The LATEST frame: MOSI 0xCF then zeros; MISO STATUS, the word, its CRC")
    # (b) a bit boundary where MISO changes (the first in the word's bytes): MISO after SCLK's fall, corners and RTL
    bx = fig.add_subplot(gs[0, 1])
    sf = [t for t, v in sclk if tf < t < tr and v == "0"]
    chg = [t for t, v in s0[(SH, "miso")] if sr[8] < t < tr]
    fa = max(x for x in sf if x <= chg[0])
    nxt = min(t for t in sr if t > fa)
    w0, w1 = fa - 60_000, nxt + 60_000
    x, y = steps(s0[(TB, "SCLK")], w0, w1)
    bx.plot(x, 3.3 + y, color=INK, lw=0.9)
    bx.text(-10, 3.8, "SCLK", ha="right", va="center", fontsize=8.5, color=INK2)
    x, y = steps(s0[(TB, "MISO")], w0, w1)
    bx.plot(x, 1.9 + y, color=INK, lw=0.9)
    bx.text(-10, 2.4, "MISO RTL", ha="right", va="center", fontsize=8.5, color=INK2)
    for m, (c, lab, col, ls) in enumerate(CORN):
        x, y = steps(sig[c][(SH, "miso")], w0, w1)
        bx.plot(x, 0.5 + y * 0.9, color=col, lw=1.2, ls=ls, label=lab)
    bx.text(-10, 0.95, "MISO netlist", ha="right", va="center", fontsize=8.5, color=INK2)
    bx.axvline((fa - w0) / 1e3, color=LIGHT, lw=0.7, ls="--")
    bx.axvline((nxt - w0) / 1e3, color=LIGHT, lw=0.7, ls="--")
    bx.set_yticks([])
    bx.grid(False)
    bx.set_xlim(0, (w1 - w0) / 1e3)
    bx.set_xlabel("time (ns)")
    a_ = [res[c]["spi"]["frames"] for c, *_ in CORN]
    lat_c = [next(f for f in fr if f["mosi"] and f["mosi"][0] == 0xCF) for fr in a_]
    bx.set_title("(b) MISO after SCLK falls: "
                 + ", ".join(f"{f['miso_after_sclk_fall_ns'][1]:.0f} ns" for f in lat_c)
                 + f"\n(setup to the next rise ≥ {min(f['miso_setup_ns'] for f in lat_c):.0f} ns)", fontsize=9.5)
    bx.legend(loc="upper right", fontsize=7, bbox_to_anchor=(1.0, 0.33))
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_60_latest_read.png")
    fig.savefig(p)
    return p


def main():
    res = json.load(open(os.path.join(RUN, "wave", "wave_sim.json")))
    sig = {c: load(c) for c, *_ in CORN}
    print("wrote", fig59(sig, res))
    print("wrote", fig60(sig, res))


if __name__ == "__main__":
    main()
