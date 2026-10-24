#!/usr/bin/env python3
"""E2E with parasitics (tracker D4 / D6): the short-window transistor E2E of
gf180/tapeout/sim/e2e/e2e_deck.py (electrodes -> AFE with its clock driver -> ADC, on the
real bias generator and reference filter; the DWA controller as the XSPICE model) with the
AFE and the ADC in three versions:

  d4   the deck as it is: eeg_afe and eeg_afe_clk from their netlists, AFE and driver on
       AVDD directly (the D4 runs of 10/22)
  sch  afe_top's schematic wrapper (gf180/tapeout/layout/lvs/afe_top.spice: the AFE, its
       clock driver on AVDD_CLK through 100 ohm with its decoupling, the offset DAC halves)
       and eeg_adc's schematic netlist: the same block boundaries as the extraction
  pex  the extracted blocks of the final chip (pex.py: runs/afe_top_c/afe_top_pex.spice,
       runs/adc_top_c/eeg_adc_pex.spice; the devices with the layout's geometry and the
       parasitic capacitances, MIM top-plate coupling moved to the bottom plates)
  pexchip  pex with the chip-level wiring of OUTP / OUTN across Ch-A: the Metal4 route's
       resistance (0.38 um wide, 150.4 um between the blocks, 90 mohm/sq: 35.6 ohm per side,
       in series at the AFE output) and its capacitances in Ch-A (pex_chipwin.py, window
       x 1582-1732.4, y 1395-1995 um: the route and the branches to the test multiplexer;
       nets the deck does not have, such as the test multiplexer's, are static and go to 0)

The afe_top instance joins the clock driver's outputs and their output-section copies
(RST2, CIA2, ... as in pex_afe.py), CPF_TRIM 8, offset DAC off, CHOP_OUT = CHOP,
CHOP_EN = 1. Stimulus, timing and the saved vector are those of e2e_deck.py, so
tr_window.py --kind e2e reads out.csv; check() adds the AFE output's held-level ripple, its
largest instantaneous value at the ADC input and the O2 swing.

Usage: python3 gf180/tapeout/pex/pex_e2e.py run <variant> [--tstop 70e-6 ...]   (writes and runs)
       python3 gf180/tapeout/pex/pex_e2e.py check <variant> [--t0 20e-6]
"""
import argparse
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "e2e"))
sys.path.insert(0, HERE)
import e2e_deck as ed  # noqa: E402
import tr_window as tw  # noqa: E402
import pex_afe as pa  # noqa: E402

ADC_SCH = os.path.join(ed.ad.ADC, "eeg_adc.spice")
ADC_PEX = os.path.join(HERE, "runs", "adc_top_c", "eeg_adc_pex.spice")
AFE_PEX = os.path.join(pa.PEXDIR, "afe_top_pex.spice")
RUNS = os.path.join(HERE, "runs", "e2e")
CHIPWIN = os.path.join(HERE, "runs", "chipwin_outpn_cha", "outpn_cha_cw.spice")
R_ROUTE = 0.090 * 150.4 / 0.38          # Metal4 route of OUTP / OUTN across Ch-A (ohm)
DECK_NETS = {"OUTP", "OUTN", "AVDD", "DVDD", "VCM", "ITST", "VBN", "VBCM", "BLP", "BLN", "VBN1", "VBCM1",
             "VNC1", "VPC1", "VBPC2", "VBNC2", "IDP", "IDN", "IQ", "VREFP", "VREFN", "O2P", "O2N"}


def chip_wiring():
    """Series resistors and the window's capacitors for OUTP / OUTN (pexchip)."""
    out = [f"RCWP OUTPA OUTP {R_ROUTE:.4g}", f"RCWN OUTNA OUTN {R_ROUTE:.4g}"]
    for ln in open(CHIPWIN):
        t = ln.split()
        if not t or ln.startswith("*"):
            continue
        a, b = (n if n in DECK_NETS else "0" for n in t[1:3])
        if a != b:
            out.append(f"{t[0]} {a} {b} {t[3]}")
    return "\n".join(out) + "\n"


def afe_line():
    """afe_top instance on the E2E deck's nets."""
    conn = {"VCM_N": "VCM", "VCM_P": "VCM", "AVSS": "0", "RST": "RSTA", "RST2": "RSTA",
            "CIA2": "CIA", "CIB2": "CIB", "CDA2": "CDA", "NCDA2": "NCDA", "CDB2": "CDB", "NCDB2": "NCDB",
            "OFPH_N": "OFPH", "OFPH_P": "OFPH", "CHOP_OUT": "CHOP", "CHOP_EN": "AVDD"}
    for k in range(4):
        conn[f"CPF{k}"] = "AVDD" if (8 >> k) & 1 else "0"
    out = []
    for p in pa.ports():
        if p in conn:
            out.append(conn[p])
        elif re.match(r"OF(S|M\d|EN\d)_[NP]$", p):
            out.append("0")
        else:
            out.append(p)
    return "XA " + " ".join(out) + " afe_top"


def deck_text(variant, a):
    txt = ed.deck(a)
    if variant == "d4":
        return txt
    inc = lambda f: f".include {f}\n"
    for f in (os.path.join(ed.AFE, "eeg_afe.spice"), os.path.join(ed.AFE, "eeg_afe_clk.spice")):
        assert txt.count(inc(f)) == 1, f
        txt = txt.replace(inc(f), "")
    files = (pa.SCH_FILES + [os.path.join(pa.LAYOUT, "lvs", "afe_top.spice")]) if variant == "sch" else [AFE_PEX]
    assert txt.count(inc(ADC_SCH)) == 1
    adc = ADC_SCH if variant == "sch" else ADC_PEX
    txt = txt.replace(inc(ADC_SCH), "".join(inc(f) for f in files) + inc(adc))
    i0 = txt.index("XAC CHOP CHOP")
    i1 = txt.index(" eeg_afe\n", i0) + len(" eeg_afe\n")
    xa = afe_line() + "\n"
    if variant == "pexchip":
        xa = xa.replace(" OUTP OUTN ", " OUTPA OUTNA ", 1) + chip_wiring()
    return txt[:i0] + xa + txt[i1:]


def run(variant, a):
    d = os.path.join(RUNS, variant + (f"_{a.tag}" if a.tag else ""))
    os.makedirs(d, exist_ok=True)
    q = open(os.path.join(ed.md.IMPORT, "quantizer.spice")).read()
    q = ed.md.sub(r"^\.model ADC33 adc_bridge \(in_low=0\.99 in_high=2\.31 ",
                  ".model ADC33 adc_bridge (in_low=1.65 in_high=1.65 ", q)
    open(os.path.join(d, "quantizer.spice"), "w").write(q)
    open(os.path.join(d, "events.txt"), "w").write(ed.md.events(a.tstop))
    open(os.path.join(d, "circuit.spice"), "w").write(deck_text(variant, a))
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "circuit.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    print(f"{variant}: {d} ({time.time() - t:.0f} s, exit {r.returncode})", flush=True)
    return d


def check(d, fsig=16e3, t0=20e-6):
    """tr_window's E2E fits, then the AFE output's held levels (ripple: per chopper half
    period the spread of the held value about the period average), its largest
    instantaneous value (the ADC input range) and the O2 swing."""
    sys.argv = ["tr_window.py", d, "--kind", "e2e", "--fsig", f"{fsig:g}", "--t0", f"{t0:g}"]
    tw.main()
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    col = lambda k: x[:, 2 * k + 1]
    m = t >= t0
    vo = col(1) - col(2)
    o2 = col(7) - col(8)
    print(f"  AFE output (ADC input) instantaneous {vo[m].min() * 1e3:.1f}..{vo[m].max() * 1e3:.1f} mV, "
          f"O2 {o2[m].min() * 1e3:.1f}..{o2[m].max() * 1e3:.1f} mV")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "check"])
    ap.add_argument("variant", choices=["d4", "sch", "pex", "pexchip"])
    ap.add_argument("--tag", default="")
    ap.add_argument("--tstop", type=float, default=70e-6)
    ap.add_argument("--fsig", type=float, default=16e3)
    ap.add_argument("--amp", type=float, default=0.943e-3)
    ap.add_argument("--vos", type=float, default=0.0)
    ap.add_argument("--chop1", type=float, default=4e3)
    ap.add_argument("--blank", type=int, default=7)
    ap.add_argument("--trst", type=float, default=10e-6)
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27)
    ap.add_argument("--wstep", type=float, default=20e-9)
    ap.add_argument("--tol", choices=sorted(ed.ad.TOLS), default="fast")
    ap.add_argument("--t0", type=float, default=20e-6)
    a = ap.parse_args()
    if a.what == "run":
        d = run(a.variant, a)
    else:
        d = os.path.join(RUNS, a.variant + (f"_{a.tag}" if a.tag else ""))
    check(d, a.fsig, a.t0)


if __name__ == "__main__":
    main()
