#!/usr/bin/env python3
"""Figure 61 (chip r15, 11/28): the r15 RTL with the two whole code streams of the CT loop model (VER-04;
gf180/tapeout/rtl_r15/run_e2e_r15.sh, tb/tb_e2e_r15.sv, tb/check_e2e_r15.py), every sample read over SPI like the host
and compared bit for bit with the golden CIC (rtl/model/cic_golden.py) run on the stream from ALIGN's clear.

  (a) s20: the 20,250 samples at the ADC input (x / 64 V, x = DATA / 2^18), the chip's samples and the golden
  (b) s20 zoomed to 60 ms: the chip's samples on the golden line, sample by sample
  (c) s4 zoomed to 100 ms (the whole record: 4,250 samples, 32 Hz at the chip full scale, 44.5 mV DC)
  (d) the chip's sample minus the golden output for every sample of both streams (LSB of DATA)

usage: r15_e2e_fig.py [<build/e2e_r15 folder>]
"""
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import INK2, LIGHT, MUTED  # noqa: E402

V.CHIP, V.CHIP_DATE = "r15", "20261128"
V.CHIP_LABEL = "Chip r15 (fifteenth assembly rebuilt with macro r15m13, 28 Nov 2026)"
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "rtl", "model"))
import cic_golden as G  # noqa: E402

B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "gf180", "tapeout", "rtl_r15", "build", "e2e_r15")
CODES = os.path.join(REPO, "gf180", "tapeout", "rtl", "build", "e2e")
OUT = os.environ.get("R15_FIG_OUT") or os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
R = 1024
CHIP_C, GOLD_C = "#1d4ed8", "#94a3b8"


def load(case, tag):
    """(seq, chip data, golden data, golden valid, bench summary line) of one run."""
    stream = open(os.path.join(CODES, f"{case}.codes"), "rb").read()
    n = len(stream)
    start, clr, smp = 0, None, []
    for line in open(os.path.join(B, f"{tag}.log")):
        f = line.split()
        if f and f[0] == "#":
            start = int(f[f.index("start") + 1])
        elif f and f[0] == "C":
            clr = int(f[1])
        elif f and f[0] == "S":
            d = int(f[2], 16)
            smp.append((int(f[1]), d - (1 << 24) if d & (1 << 23) else d))
    seq = np.array([s for s, _ in smp])
    data = np.array([d for _, d in smp], dtype=np.int64)
    ninp = (seq.max() - clr) * R
    pos0 = start + (clr + 1) * R
    codes = [stream[(pos0 + j) % n] for j in range(ninp)]
    out, _st = G.cic3_run(codes)
    gd = np.array([out[s - clr - 1][0] for s in seq], dtype=np.int64)
    gv = np.array([out[s - clr - 1][1] for s in seq])
    summ = next((ln.strip() for ln in open(os.path.join(B, f"{tag}.run.out")) if ln.startswith("tb_e2e_r15:")), "")
    return seq, data, gd, gv, summ


def volts(d):
    return d / 2.0 ** 18 / 64.0


def main():
    runs = {}
    for case, tag in (("s20", "s20_full"), ("s4", "s4_full")):
        lp = os.path.join(B, f"{tag}.log")
        if os.path.exists(lp) and any(ln.startswith("E ") for ln in open(lp)):     # finished runs only
            runs[case] = load(case, tag)
    if "s4" not in runs:
        raise SystemExit("no s4 run")
    V.apply()
    n20 = len(runs["s20"][0]) if "s20" in runs else 0
    n4 = len(runs["s4"][0])
    fig = V.figure(12.0, 8.6, "r15 RTL: whole code streams read like the host, bit-exact with the golden CIC",
                   "The CT loop model's streams s20 (20.26 s) and s4 (4.26 s) at the CODE input from the RESET_N release; "
                   "START with the default timers, every sample read over SPI with CRC (level, then pulse mode of DRDY_N), "
                   "compared with the golden CIC run on the stream from ALIGN's clear",
                   note="tb_e2e_r15.sv: ID, VERSION, CAPS, CRC on, START, STATE polled to RUN; every 97 samples 1 .. 6 "
                        "outputs left unread and the queue read in a row (FIFO_LEVEL checked), every 64 a LATEST read "
                        "(the last stored output, nothing popped); at the end STOP, DFLAG, ERR, DROP_CNT 0, CFG_GEN 1. "
                        "check_e2e_r15.py: SEQ s closes the inputs [s R, (s + 1) R), R = 1024; its self-test detects 7 "
                        "errors written into a log. Volts at the ADC input: x / 64 with x = DATA / 2^18 (2c − 31 units).")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.6, 1.0], height_ratios=[1.0, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    if "s20" in runs:
        seq, d, g, gv, summ = runs["s20"]
        t = (seq - seq[0]) * 1e-3
        ax.plot(t, volts(g) * 1e3, color=GOLD_C, lw=2.4, label="golden CIC", solid_capstyle="round")
        ax.plot(t, volts(d) * 1e3, color=CHIP_C, lw=0.7, label="chip (RTL) over SPI")
        z0 = 5.0
        ax.axvspan(z0, z0 + 0.06, color="#fde68a", alpha=0.6, lw=0)
        ax.set_title(f"(a) s20, all {n20:,} samples")
        ax.set_xlabel("time from the first stored sample (s)   [stream: 0.5 Hz at full scale − 44.5 mV DC, 900 Hz at 27.9 mV]")
        ax.set_ylabel("ADC input (mV)")
        ax.legend(loc="upper right", ncol=2, bbox_to_anchor=(1.0, 1.13))
        az = fig.add_subplot(gs[0, 1])
        k = (t >= z0) & (t < z0 + 0.06)
        az.plot((t[k] - z0) * 1e3, volts(g[k]) * 1e3, color=GOLD_C, lw=2.4, label="golden CIC")
        az.plot((t[k] - z0) * 1e3, volts(d[k]) * 1e3, "o", color=CHIP_C, ms=3.2, label="chip sample")
        az.set_title("(b) s20, 60 ms from 5.0 s, sample by sample")
        az.set_xlabel("time (ms)")
        az.set_ylabel("ADC input (mV)")
    else:
        ax.text(0.5, 0.5, "s20 still running", ha="center", va="center", color=MUTED, transform=ax.transAxes)
    a4 = fig.add_subplot(gs[1, 0])
    seq, d, g, gv, summ4 = runs["s4"]
    t = (seq - seq[0]) * 1e-3
    z4 = 2.0
    k = (t >= z4) & (t < z4 + 0.1)
    a4.plot((t[k] - z4) * 1e3, volts(g[k]) * 1e3, color=GOLD_C, lw=2.4, label="golden CIC")
    a4.plot((t[k] - z4) * 1e3, volts(d[k]) * 1e3, "o", color=CHIP_C, ms=2.6, label="chip (RTL) over SPI")
    a4.set_title("(c) s4, 100 ms from 2.0 s")
    a4.set_xlabel(f"time (ms)   [stream: 32 Hz at full scale + 44.5 mV DC + 128 kHz ripple; {n4:,} samples in all]")
    a4.set_ylabel("ADC input (mV)")
    a4.legend(loc="upper right", ncol=2, bbox_to_anchor=(1.0, 1.13))
    ad = fig.add_subplot(gs[1, 1])
    rows = []
    for i, (case, col) in enumerate((("s20", CHIP_C), ("s4", "#0d9488"))):
        if case not in runs:
            continue
        seq, d, g, gv, summ = runs[case]
        diff = d - g
        nbad = int(np.count_nonzero(diff)) + int(np.count_nonzero(~gv))
        ad.plot(np.arange(len(diff)), diff + 0.0, "o" if case == "s4" else "-", color=col, ms=1.5, lw=1.2,
                label=f"{case}: {nbad} of {len(diff):,} differ")
        m = re.search(r"\((\d+) backlogs, queue up to (\d+), (\d+) LATEST reads", summ)
        rows.append((case, len(diff), nbad, m.groups() if m else ("?", "?", "?")))
    ad.set_ylim(-4, 4)
    ad.set_title("(d) chip sample − golden output (DATA LSB)")
    ad.set_xlabel("sample")
    ad.set_ylabel("difference (LSB)")
    ad.legend(loc="upper right")
    y = 0.08
    for case, n, nbad, (bl, q, lat) in rows:
        ad.text(0.02, y, f"{case}: {bl} backlogs (queue ≤ {q}), {lat} LATEST reads", transform=ad.transAxes,
                fontsize=8, color=INK2)
        y += 0.08
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_61_e2e_streams.png")
    fig.savefig(p)
    print("wrote", p)


if __name__ == "__main__":
    main()
