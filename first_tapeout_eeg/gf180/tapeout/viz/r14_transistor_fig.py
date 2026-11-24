#!/usr/bin/env python3
"""Figure 56 (r14, 11/24): the transistor-level checks of the long digital-to-analog lines on the 14th chip against
the 13th (VER-08): each chip's own extracted wiring (chip_nets.py), its macro's output buffer (r13 buf_1, r14 clkbuf_2;
buf_16 as the reference of a strong driver), ngspice (gf180/tapeout/digital/chip_sta/run_checks.sh):
  (a) the edges at the receivers (10-90 %, rising, ss 125 C) of CMP_STROBE, DAC_CLK, CHOP, CHOP_BLANK, CHOP1
      (drive_check.py, 20-segment RC lines with coupling once and the receivers' gates)
  (b) the AFE clock driver (eeg_afe_clk with its real supplies): CHOP's buffer input to CIA / CIB, falling and rising
  (c) OTA1's chopper driver (eeg_adc_clk on the real OTA1): CHOP1's buffer input to the new commutator phase
  (d) the quantizer: the last TH settled, from the strobe buffer's input (strobe_check.py, the strobe through its
      line, the TH loads extracted, coupling twice)
  (e) DAC1's common break (dac1_brk_check.py): DAC_CLK's buffer input to BRK at 50 %
  (f) the coupling disturbances at the quiet receivers (xtalk_check.py), the largest of the three corners
Results: chip_sta/build/r13/ (the 13th chip's own wiring) and chip_sta/build/r14/.
Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_transistor_fig.py
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import MUTED, plt  # noqa: E402

V.CHIP, V.CHIP_DATE = "r14", "20261124"
V.CHIP_LABEL = "Chip r14 (fourteenth assembly, 24 Nov 2026)"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
B = os.path.join(REPO, "gf180", "tapeout", "digital", "chip_sta", "build")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
CELL = {"r13": "buf_1", "r14": "clkbuf_2"}
COL = {"r13": "#94a3b8", "r14": "#0d9488", "ref": "#cbd5e1"}
LAB = {"r13": "13th chip, buf_1 (r13 macro)", "r14": "14th chip, clkbuf_2 (r14 macro)",
       "ref": "buf_16 on the 14th chip's lines (reference)"}
CORNERS = ("ss 125 C", "typical 27 C", "ff -40 C")
CLAB = {"ss 125 C": "ss 125 °C", "typical 27 C": "typ 27 °C", "ff -40 C": "ff −40 °C"}


def load(ver):
    d = json.load(open(os.path.join(B, ver, "drive_check.json")))
    x = json.load(open(os.path.join(B, ver, "xtalk_check.json")))
    st = {}
    for line in open(os.path.join(B, ver, "strobe_check.log")):
        m = re.match(r"\| (\w+) \| ([^|]+?) \| [^|]+ \| ([\d.]+) / ([\d.]+) \| ([\d.]+) \|", line)
        if m:
            st[(m.group(1), m.group(2))] = (float(m.group(3)), float(m.group(4)), float(m.group(5)))
    db = {}
    head = None
    for line in open(os.path.join(B, ver, "dac1_brk_check.log")):
        c = [s.strip() for s in line.strip().strip("|").split("|")]
        if c[0] == "quantity":
            head = c[1:]
        elif head and c[0].startswith("DAC_CLK to BRK"):
            db = dict(zip(head, map(float, c[1:])))
    return d, x, st, db


def main():
    V.apply()
    D = {v: load(v) for v in ("r13", "r14")}
    fig = V.figure(13.4, 9.4, "Transistor-level checks of the long control lines: the 14th chip against the 13th",
                   "Each chip's own extracted lines driven by its macro's output buffer, the real receivers in "
                   "ngspice: r14's clkbuf_2 halves the edges, every receiver switches once per edge with the same "
                   "dead times and orders, the quantizer settles TH 2.5 ns earlier, and the coupling disturbances "
                   "stay at or below half the logic threshold (largest 0.62 V on r14, 0.77 V on r13).",
                   note="Lines from each chip's core LVS (chip_nets.py), 20 RC segments, coupling once (twice for the "
                        "strobe and TH loads), the receivers' gates. ss 125 °C 3.0 V, typical 27 °C 3.3 V, ff −40 °C "
                        "3.6 V; the quantizer also at ss −20 °C (its slowest) with AVDD = DVDD = 3.0 V. buf_16 drives the "
                        "14th chip's lines as the reference of a strong buffer (the r13 runs drove r13's lines with it: "
                        "the same values within 0.01 ns). r13: the 13th chip's own wiring (11/24 extraction), "
                        "not the 10/24 wiring of section 5 of the verification document.")
    gs = fig.add_gridspec(2, 3)
    # (a) edges
    ax = fig.add_subplot(gs[0, 0])
    nets = ["CMP_STROBE", "DAC_CLK", "CHOP", "CHOP_BLANK", "CHOP1"]

    def edge(ver, cell, net, corner="ss 125 C"):
        for r in D[ver][0]["drive"]:
            if r["net"] == net and r["cell"] == cell and r["corner"] == corner:
                return r["rise"]["t1090"]
    x = np.arange(len(nets))
    w = 0.27
    for i, (ver, cell, key) in enumerate((("r13", "buf_1", "r13"), ("r14", "clkbuf_2", "r14"), ("r14", "buf_16", "ref"))):
        vals = [edge(ver, cell, n) for n in nets]
        ax.bar(x + (i - 1) * w, vals, w, color=COL[key], label=LAB[key])
        if key != "ref":
            for xi, v in zip(x, vals):
                ax.text(xi + (i - 1) * w, v + 0.4, f"{v:.1f}", ha="center", fontsize=6.6,
                        color=MUTED if key == "r13" else COL["r14"])
    ax.set_xticks(x)
    ax.set_xticklabels(nets, fontsize=7.6)
    ax.set_ylabel("rising edge 10–90 % at the receiver (ns)")
    ax.set_title("(a) Edges at the receivers, ss 125 °C")
    ax.legend(loc="upper left", fontsize=6.9)
    # (b) AFE clock driver
    ax = fig.add_subplot(gs[0, 1])
    xs = np.arange(len(CORNERS))
    for i, ver in enumerate(("r13", "r14")):
        for j, e in enumerate(("fall", "rise")):
            vals = []
            for c in CORNERS:
                r = [a for a in D[ver][0]["aclk"] if a["cell"] == CELL[ver] and a["corner"] == c][0]
                vals.append([q for q in r["edge"] if q["edge"] == e][0]["delay_ns"])
            ax.bar(xs + (2 * i + j - 1.5) * 0.2, vals, 0.19, color=COL[ver], alpha=1.0 if e == "rise" else 0.55,
                   label=f"{ver}, CHOP {'rising' if e == 'rise' else 'falling'}")
    for i, ver in enumerate(("r13", "r14")):
        r = [a for a in D[ver][0]["aclk"] if a["cell"] == CELL[ver] and a["corner"] == "ss 125 C"][0]
        f_, r_ = [q["delay_ns"] for q in r["edge"]]
        ax.annotate(f"{ver}: rise − fall {r_ - f_:.1f} ns\n= {abs(r_ - f_) / 3906.25 * 100:.2f} % of a half period",
                    (xs[0] + (2 * i + 0.5 - 1.5) * 0.2, max(f_, r_)), xytext=(0.55 + 0.0 * i, 21.5 - 4.2 * i),
                    textcoords="data", fontsize=6.8, color=MUTED if ver == "r13" else COL["r14"],
                    arrowprops=dict(arrowstyle="->", color=MUTED if ver == "r13" else COL["r14"], lw=0.8))
    ax.set_xticks(xs)
    ax.set_xticklabels([CLAB[c] for c in CORNERS])
    ax.set_ylim(0, 27)
    ax.set_ylabel("CHOP buffer input to CIA / CIB (ns)")
    ax.set_title("(b) AFE clock driver (dead time the same: 7.63 / 4.93 / 3.27 ns)")
    ax.legend(loc="upper right", fontsize=6.8, ncol=2)
    # (c) OTA1 chopper driver
    ax = fig.add_subplot(gs[0, 2])
    for i, ver in enumerate(("r13", "r14")):
        for j, e in enumerate(("A->B", "B->A")):
            vals = [[a for a in D[ver][0]["adcclk"] if a["cell"] == CELL[ver] and a["corner"] == c][0][e]["delay"]
                    for c in CORNERS]
            ax.bar(xs + (2 * i + j - 1.5) * 0.2, vals, 0.19, color=COL[ver], alpha=1.0 if j else 0.55,
                   label=f"{ver}, {e.replace('->', ' to ')}")
    ax.set_xticks(xs)
    ax.set_xticklabels([CLAB[c] for c in CORNERS])
    ax.set_ylabel("CHOP1 buffer input to commutator (ns)")
    ax.set_title("(c) OTA1 chopper driver (dead, overlap, order: same\nwithin 0.03 ns)")
    ax.legend(loc="upper right", fontsize=6.8, ncol=2)
    # (d) quantizer
    ax = fig.add_subplot(gs[1, 0])
    qc = ["ss -20 C", "ss 85 C", "ss 125 C", "typical 27 C"]
    xq = np.arange(len(qc))
    for i, (ver, cell, key) in enumerate((("r13", "buf_1", "r13"), ("r14", "clkbuf_2", "r14"))):
        vals = [D[ver][2][(cell, c)][0] for c in qc]
        ax.bar(xq + (i - 0.5) * 0.36, vals, 0.36, color=COL[key], label=LAB[key])
        for xi, v, c in zip(xq, vals, qc):
            ax.text(xi + (i - 0.5) * 0.36, v + 0.15, f"{v:.2f}", ha="center", fontsize=6.6,
                    color=MUTED if key == "r13" else COL["r14"])
    ref = [D["r14"][2].get(("buf_16", c), (np.nan,))[0] for c in qc]
    ax.plot(xq, ref, "_", ms=26, mew=1.6, color="#475569", label="buf_16 (reference)")
    ax.set_xticks(xq)
    ax.set_xticklabels(["ss −20 °C\n3.0 V", "ss 85 °C\n3.0 V", "ss 125 °C\n3.0 V", "typ 27 °C\n3.3 V"], fontsize=7.6)
    ax.set_ylabel("last TH settled, from the strobe buffer's input (ns)")
    ax.set_ylim(0, 15.5)
    ax.set_title("(d) Quantizer: the strobe through its line, TH settled")
    ax.legend(loc="upper right", fontsize=6.8, markerscale=0.3)
    # (e) DAC1 break
    ax = fig.add_subplot(gs[1, 1])
    for i, (ver, key) in enumerate((("r13", "r13"), ("r14", "r14"))):
        vals = [D[ver][3][f"{CELL[ver]} {c}"] for c in CORNERS]
        ax.bar(xs + (i - 0.5) * 0.36, vals, 0.36, color=COL[key], label=LAB[key])
        for xi, v in zip(xs, vals):
            ax.text(xi + (i - 0.5) * 0.36, v + 0.05, f"{v:.2f}", ha="center", fontsize=6.6,
                    color=MUTED if key == "r13" else COL["r14"])
    ref = [D["r14"][3][f"buf_16 {c}"] for c in CORNERS]
    ax.plot(xs, ref, "_", ms=40, mew=1.6, color="#475569", label="buf_16 (reference)")
    ax.set_xticks(xs)
    ax.set_xticklabels([CLAB[c] for c in CORNERS])
    ax.set_ylabel("DAC_CLK buffer input to BRK at 50 % (ns)")
    ax.set_title("(e) DAC1's common break (width and latch order:\nthe same, 2.35 / 1.56 / 1.08 ns wide)")
    ax.legend(loc="upper right", fontsize=6.8, markerscale=0.3)
    # (f) crosstalk
    ax = fig.add_subplot(gs[1, 2])
    items = [("CHOP_EN", "afe", "CHOP_EN"), ("CHOP_BLANK (high)", "afe", "CHOP_BLANK (high)"),
             ("CPF3 (trim 1)", "afe1", "CPF3"), ("AFE_RST", "afe", "AFE_RST"), ("ADC_ZERO", "adc", "ADC_ZERO"),
             ("TC3 by CMP_STROBE", "adc", "TC3 (by CMP_STROBE)"), ("TC3 by CHOP1", "adc", "TC3 (by CHOP1)"),
             ("TC2 by CHOP1", "adc", "TC2 (by CHOP1)")]

    def dist(ver, kind, name):
        x = D[ver][1]
        tag = "f2" if ver == "r13" else "r14"
        vals = []
        for k, v in x.items():
            if kind.startswith("afe") and k.startswith(f"xtalk_afe_{tag}_") and "_d0_" in k:
                if (kind == "afe1") == k.endswith("_c1"):
                    vals.append(v["dist"][name])
            elif kind == "adc" and k.startswith(f"xtalk_adc_{tag}_"):
                vals.append(v[name])
        return max(vals)
    y = np.arange(len(items))
    for i, ver in enumerate(("r13", "r14")):
        vals = [dist(ver, k, n) for _, k, n in items]
        ax.barh(y + (i - 0.5) * 0.36, vals, 0.36, color=COL[ver], label=LAB[ver])
        for yi, v in zip(y, vals):
            ax.text(v + 0.01, yi + (i - 0.5) * 0.36, f"{v:.2f}", va="center", fontsize=6.4,
                    color=MUTED if ver == "r13" else COL["r14"])
    ax.axvline(1.5, color="#b91c1c", lw=0.9, ls="--")
    ax.text(1.48, len(items) - 0.4, "logic threshold ≈ 1.5 V", ha="right", fontsize=6.8, color="#b91c1c")
    ax.set_yticks(y)
    ax.set_yticklabels([lab for lab, _, _ in items], fontsize=7.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.6)
    ax.set_xlabel("largest disturbance at the receiver, 3 corners (V)")
    ax.set_title("(f) Coupling at the quiet receivers (CHOP_DLY 0)")
    ax.legend(loc="upper right", bbox_to_anchor=(0.9, 1.0), fontsize=6.8)
    ax.grid(axis="y", visible=False)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_56_transistor_checks.png")
    fig.savefig(p)
    print("wrote", p)


if __name__ == "__main__":
    main()
