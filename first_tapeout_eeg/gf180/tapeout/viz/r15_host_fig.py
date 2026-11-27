#!/usr/bin/env python3
"""Figure 62 (chip r15, 11/28): the Python host model of requirement 5.4 driving two r15 chips (VER-06;
gf180/tapeout/rtl_r15/run_host_r15.sh, tb/host_r15.py on the board tb/tb_host_r15.sv), from its event record
(build/host_r15/host_events.json).

  (a) every sample the host used, as the electrode-referred residual (DATA / 4,665 LSB per uV: the board's AFE gain
      287.02 and 0.5 V reference), per chip; OVL samples hollow, CHANGED samples crossed
  (b) the offset DAC M of each probe of the search (coarse, fine, APPLY_NR neighbours) and the nearest M of each
      electrode offset (dashed)
  (c) the procedure's events per chip: RUN, the commands (refusals marked), the faults on the line, SOFT_RESET, and
      the grid comparisons of step 5

usage: r15_host_fig.py [<build/host_r15 folder>]
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import BAD, INK2, LIGHT, MUTED, OK  # noqa: E402

V.CHIP, V.CHIP_DATE = "r15", "20261128"
V.CHIP_LABEL = "Chip r15 (fifteenth assembly rebuilt with macro r15m13, 28 Nov 2026)"
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, "gf180", "tapeout", "rtl_r15", "build", "host_r15")
OUT = os.environ.get("R15_FIG_OUT") or os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
LSB_PER_UV = 31 * 287.02e-6 / 0.5 * 2 ** 18
COL = ["#1d4ed8", "#d97706"]                     # chip 0, chip 1: fixed order
S_OVL, S_CHG = 1 << 5, 1 << 4
FAULT_TXT = {"mosi": "MOSI bit\n(CRC_ERR)", "cut": "read cut\n(FRAME_ERR)", "miso": "MISO bit\n(read again)",
             "extra": "+8 SCLK\n(word dropped)"}


def main():
    j = json.load(open(os.path.join(B, "host_events.json")))
    ev, words, offs = j["events"], j["words"], j["offsets_uv"]
    V.apply()
    fig = V.figure(12.0, 11.6, "r15: the model host procedure (5.4) in Python drives two chips",
                   "Two r15 chips (RTL) sharing MCLK, RESET_N, SCLK, MOSI and the MISO line; the host sees MISO, DRDY_N "
                   "and time only. Bring-up, step 5 grids, the offset search, steady reading, six faults on the line, "
                   "one chip's SOFT_RESET, STOP: 36 checks, all passed",
                   note="Board tb_host_r15.sv: per chip an electrode offset (chip 0 +87.65 mV, chip 1 −45.32 mV) plus a "
                        "common 37 Hz 40 µV signal and 2 µV rms noise, minus the offset DAC of the pins (301 µV a step), "
                        "times the AFE gain 287.02, into a first-order 31-level sigma-delta. Host host_r15.py: rules "
                        "(a), (b), (d), (e), part of (c), steps 2–10; its mutation self-test detects all 7 RTL errors "
                        "tried (SOFT_RESET moving SEQ or the frame grid, a 2-step APPLY_NR, a write CRC not checked, "
                        "CHANGED one short, bits after a whole frame ignored, START taken outside IDLE).")
    gs = fig.add_gridspec(4, 1, height_ratios=[1.2, 0.95, 0.55, 1.05])
    ax = fig.add_subplot(gs[0])
    for c in (0, 1):
        w = np.array(words[str(c)], dtype=float)
        if not len(w):
            continue
        t, d, st = w[:, 0] / 1e6, w[:, 2] / LSB_PER_UV, w[:, 3].astype(int)
        norm = (st & (S_OVL | S_CHG)) == 0
        ax.plot(t[norm], d[norm], "o", ms=2.4, color=COL[c], label=f"chip {c}")
        o = (st & S_OVL) != 0
        ax.plot(t[o], d[o], "o", ms=3.6, mfc="none", mec=COL[c], mew=0.8, label=f"chip {c}: OVL")
        k = (st & S_CHG) != 0
        ax.plot(t[k], d[k], "x", ms=4.0, color=COL[c], mew=0.9, label=f"chip {c}: CHANGED")
    ax.set_ylim(-1950, 1950)
    ax.set_ylabel("residual at the electrode (µV)")
    ax.set_title("(a) every sample the host used: saturated while M is far, then the residual of the chosen M")
    ax.legend(loc="upper right", ncol=3, fontsize=7.8)
    ab = fig.add_subplot(gs[1], sharex=ax)
    for c in (0, 1):
        pr = [e for e in ev if e["kind"] == "probe" and e["chip"] == c]
        if not pr:
            continue
        t = np.array([e["t"] for e in pr]) / 1e6
        m = np.array([e["m"] for e in pr])
        ab.step(t, m, where="post", color=COL[c], lw=1.2, label=f"chip {c}: M of each probe")
        for stage, mk in (("coarse", "o"), ("fine", "s"), ("fine_nr", "D")):
            k = np.array([e["stage"] == stage for e in pr])
            ab.plot(t[k], m[k], mk, ms=3.6, color=COL[c])
        ab.axhline(round(offs[c] / 301.0), color=COL[c], lw=0.9, ls="--")
        done = next((e for e in ev if e["kind"] == "search_done" and e["chip"] == c), None)
        if done:
            ab.annotate(f"M {done['m']:+d}", (done["t"] / 1e6, done["m"]), xytext=(6, 6 if c == 0 else -12),
                        textcoords="offset points", fontsize=8, color=COL[c])
    ab.set_ylabel("offset DAC M (signed)")
    ab.set_title("(b) the search: coarse probes (circles, range 4), fine APPLY (square), APPLY_NR neighbours (diamonds); "
                 "dashed: the nearest M of each offset")
    ab.legend(loc="upper right", ncol=2, fontsize=7.8)
    ae = fig.add_subplot(gs[2], sharex=ax)
    ae.set_ylim(-0.6, 1.6)
    ae.set_yticks([0, 1])
    ae.set_yticklabels(["chip 0", "chip 1"])
    ae.grid(axis="y", visible=False)
    t_f = [f["t"] / 1e6 for f in j["faults"]]
    seq = []                                          # the fault period, listed in (d)
    for e in ev:
        c, t = e["chip"], e["t"] / 1e6
        if e["kind"] == "RUN":
            ae.plot(t, c, "|", ms=11, color=COL[c], mew=1.4)
        elif e["kind"] == "cmd":
            ae.plot(t, c, "|", ms=6, color=LIGHT if e["done"] else BAD, mew=0.9)
        elif e["kind"] == "soft_reset":
            ae.plot(t, c, "*", ms=10, color="#7c3aed")
        elif e["kind"] in ("grid_i", "grid_ii"):
            ae.plot(t, 0.5, "s", ms=5.5, color=OK if e["ok"] else BAD)
    for f in j["faults"]:
        ae.plot(f["t"] / 1e6, f["chip"], "^", ms=6.5, color=BAD)
    if t_f:
        lo = min(t_f) - 1.5
        hi = max(e["t"] for e in ev if e["kind"] == "grid_ii") / 1e6 + 1.5
        ae.axvspan(lo, hi, color="#fee2e2", alpha=0.7, lw=0)
        ae.text((lo + hi) / 2, 1.45, "(d)", ha="center", va="center", fontsize=8, color=BAD)
    g0 = [e for e in ev if e["kind"] in ("grid_i", "grid_ii") and e["t"] / 1e6 < 100]
    if g0:
        gi = next(e for e in g0 if e["kind"] == "grid_i")
        gii = next(e for e in g0 if e["kind"] == "grid_ii")
        ae.text(gi["t"] / 1e6 + 3, 1.45, f"after the bring-up: (i) SEQ {gi['seq_ref']} = {gi['seq_other']}, "
                f"(ii) DRDY_N falls {gii['diff_ns']:+.1f} ns apart", fontsize=7.2, color=OK, va="center")
    ae.set_xlabel("simulated time (ms; RESET_N released at 5 µs)")
    ae.set_title("(c) events: RUN (tall ticks), commands (grey ticks, refused red), faults on the line (red triangles), "
                 "SOFT_RESET (star), step 5 grid comparisons (green squares between the rows)")
    ae.set_xlim(0, j["end_ns"] / 1e6)
    # (d) the fault period and the SOFT_RESET in order (not to scale)
    rows = []
    fault_txt = {"mosi": ("MOSI bit of a write", "CRC_ERR: found by the", "settings check, written again"),
                 "cut": ("read cut at 12 bits", "CRC wrong: read again;", "step 8 clears FRAME_ERR"),
                 "miso": ("MISO bit of a sample", "CRC wrong: 8 more SCLK,", "the same sample again"),
                 "extra": ("+8 SCLK after a sample", "not popped: word dropped", "by the FRAME_ERR rule")}
    for f in j["faults"]:
        rows.append((f["t"], f["chip"], "fault", fault_txt.get(f["kind"], (f["kind"],))))
    for e in ev:
        if not t_f or e["t"] / 1e6 < min(t_f) - 1.5:
            continue
        if e["kind"] == "cmd" and not e["done"]:
            what = {"START": ("START in RUN", "STATE_ERR: refused,", "still RUN"),
                    "APPLY_NR": ("APPLY_NR of 2 steps", "CFG_ERR: refused,", "the active M unchanged")}
            rows.append((e["t"], e["chip"], "refused", what.get(e["name"], (e["name"],))))
        elif e["kind"] == "soft_reset":
            rows.append((e["t"], e["chip"], "soft", ("SOFT_RESET", "confirmed: CRC off,", "RESET_FLAG 1")))
        elif e["kind"] == "cmd" and e["name"] == "START" and e["done"]:
            rows.append((e["t"], e["chip"], "cmd", ("START", "(steps 2-5 again,", "M written first)")))
        elif e["kind"] == "RUN":
            rows.append((e["t"], e["chip"], "run", ("RUN",)))
        elif e["kind"] == "grid_i":
            rows.append((e["t"], 0.5, "grid", ("step 5 (i)", f"SEQ {e['seq_ref']} = {e['seq_other']}")))
        elif e["kind"] == "grid_ii":
            rows.append((e["t"], 0.5, "grid", ("step 5 (ii)", f"falls {e['diff_ns']:+.1f} ns apart")))
    rows.sort(key=lambda r: r[0])
    ad = fig.add_subplot(gs[3])
    ad.set_xlim(-0.6, len(rows) - 0.4)
    ad.set_ylim(-1.25, 2.1)
    ad.set_yticks([0, 1])
    ad.set_yticklabels(["chip 0", "chip 1"])
    ad.set_xticks(range(len(rows)))
    ad.set_xticklabels([f"{r[0] / 1e6:.2f}" for r in rows], fontsize=7.6)
    ad.grid(False)
    style = {"fault": ("^", BAD), "refused": ("v", BAD), "soft": ("*", "#7c3aed"), "cmd": ("|", INK2),
             "run": ("|", INK2), "grid": ("s", OK)}
    for k, (tt, y, kind, txt) in enumerate(rows):
        mk, col = style[kind]
        ad.plot(k, y, mk, ms=9 if mk != "|" else 13, color=col, mew=1.4)
        up = y >= 0.75 or (y == 0.5 and k % 2) or (y == 0 and k % 2)
        ad.text(k, y + (0.22 if up else -0.22), "\n".join(txt), ha="center", va="bottom" if up else "top",
                fontsize=7.0, color=col if kind != "cmd" and kind != "run" else INK2)
    ad.set_xlabel("simulated time of each event (ms), in order, not to scale")
    ad.set_title("(d) the faults on chip 0, chip 1's SOFT_RESET and the grid comparisons after it")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"gf180_viz_{V.CHIP}_62_host_model.png")
    fig.savefig(p)
    print("wrote", p)


if __name__ == "__main__":
    main()
