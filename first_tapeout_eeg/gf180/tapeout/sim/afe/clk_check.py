#!/usr/bin/env python3
"""Clock-driver check of eeg_afe_clk (gf180/tapeout/afe/eeg_afe_clk.spice, tracker B8)
with lumped gate loads equal to the eeg_afe switches:
  CIA/CIB 16.6 pF (NMOS gates of two m = 256 input TGs), NCIA/NCIB 33 pF (PMOS gates),
  CDA/CDB 0.3 pF, NCDA/NCDB 0.6 pF (output TGs), OFPH 0.2 pF (offset-DAC logic).
CHOP at 128 kHz (0.5 ns edges), CHOP_OUT = CHOP, CHOP_BLANK from 1 MCLK before to
7 MCLK after each edge.

Printed per corner: dead time between the input-chopper phases (the TG of one phase
fully off, NMOS gate < 0.3 V and PMOS gate > VDD - 0.3 V, until the other one starts
to conduct, NMOS gate > 0.7 V or PMOS gate < VDD - 0.7 V), the CIA/NCIA skew at 50 %,
the 10-90 % edge times, OFPH against the 50 % rise of CIA/CIB, and the output-chopper
phases against the blanking.

Usage: python3 clk_check.py [--corners typical:27 ss:85 ff:-20]
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_noise

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CLK = os.path.join(REPO, "gf180", "tapeout", "afe", "eeg_afe_clk.spice")
T = 1 / 128e3
TM = 1 / 32.768e6
VDD = 3.3


def deck(corner, temp):
    tstop = 2 * T
    # CHOP: high in phase A from 0; the first edge at T/2 (falling), the second at T (rising)
    chop = f"PULSE(0 {VDD} 50n 0.5n 0.5n {T / 2 - 0.5e-9:.6e} {T:.6e})"
    edges = [50e-9 + k * T / 2 for k in range(5)]
    bl = []
    for e in edges:
        bl += [(e - TM, 0), (e - TM + 0.5e-9, VDD), (e + 7 * TM, VDD), (e + 7 * TM + 0.5e-9, 0)]
    bl = [(0.0, 0)] + [p for p in bl if p[0] > 0]
    blank = " ".join(f"{a:.6e} {b:g}" for a, b in bl)
    return f"""* eeg_afe_clk check
.include {afe_noise.PDK}/design.ngspice
.lib {afe_noise.PDK}/sm141064.ngspice {corner}
.include {CLK}
.temp {temp}
.options sparse reltol=1e-4
VDD VDD 0 {VDD}
VCHOP CHOP 0 {chop}
VCO CHOP_OUT 0 {chop}
VBL CHOP_BLANK 0 PWL({blank})
VEN CHOP_EN 0 {VDD}
VRS AFE_RST 0 0
XC CHOP CHOP_OUT CHOP_BLANK CHOP_EN AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RST VDD 0 eeg_afe_clk
CL1 CIA 0 16.6p
CL2 NCIA 0 33p
CL3 CIB 0 16.6p
CL4 NCIB 0 33p
CL5 CDA 0 0.3p
CL6 NCDA 0 0.6p
CL7 CDB 0 0.3p
CL8 NCDB 0 0.6p
CL9 OFPH 0 0.2p
.control
set noaskquit
tran 0.02n {tstop:.6e} 0 0.1n
wrdata out.csv v(chop) v(cia) v(ncia) v(cib) v(ncib) v(ofph) v(cda) v(cdb) v(chop_blank) i(vdd)
quit
.endc
.end
"""


def cross(t, v, level, rising, after):
    m = t > after
    tt, vv = t[m], v[m]
    s = (vv[:-1] < level) & (vv[1:] >= level) if rising else (vv[:-1] > level) & (vv[1:] <= level)
    i = np.flatnonzero(s)
    if not i.size:
        return float("nan")
    i = i[0]
    return tt[i] + (level - vv[i]) * (tt[i + 1] - tt[i]) / (vv[i + 1] - vv[i])


def run(corner, temp):
    d = os.path.join(HERE, "runs", f"clk_{corner}_{temp}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(corner, temp))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(
        ["chop", "cia", "ncia", "cib", "ncib", "ofph", "cda", "cdb", "blank", "idd"])}
    e1 = 50e-9 + T / 2  # A -> B
    e2 = 50e-9 + T      # B -> A
    res = {}
    # A off, B on (after e1)
    a_off = max(cross(t, v["cia"], 0.3, False, e1 - 5e-9), cross(t, v["ncia"], VDD - 0.3, True, e1 - 5e-9))
    b_on = min(cross(t, v["cib"], 0.7, True, e1 - 5e-9), cross(t, v["ncib"], VDD - 0.7, False, e1 - 5e-9))
    res["dead A->B (ns)"] = (b_on - a_off) * 1e9
    b_off = max(cross(t, v["cib"], 0.3, False, e2 - 5e-9), cross(t, v["ncib"], VDD - 0.3, True, e2 - 5e-9))
    a_on = min(cross(t, v["cia"], 0.7, True, e2 - 5e-9), cross(t, v["ncia"], VDD - 0.7, False, e2 - 5e-9))
    res["dead B->A (ns)"] = (a_on - b_off) * 1e9
    res["CIA/NCIA skew at rise (ns)"] = (cross(t, v["ncia"], VDD / 2, False, e2 - 5e-9)
                                         - cross(t, v["cia"], VDD / 2, True, e2 - 5e-9)) * 1e9
    c10 = cross(t, v["cia"], 0.33, True, e2 - 5e-9)
    c90 = cross(t, v["cia"], 2.97, True, e2 - 5e-9)
    n90 = cross(t, v["ncia"], 2.97, False, e2 - 5e-9)
    n10 = cross(t, v["ncia"], 0.33, False, e2 - 5e-9)
    res["CIA rise 10-90 (ns)"] = (c90 - c10) * 1e9
    res["NCIA fall 90-10 (ns)"] = (n10 - n90) * 1e9
    res["CHOP edge -> CIA 50 % (ns)"] = (cross(t, v["cia"], VDD / 2, True, e2 - 5e-9) - e2) * 1e9
    res["OFPH rise - CIA 50 % (ns)"] = (cross(t, v["ofph"], VDD / 2, True, e2 - 5e-9)
                                        - cross(t, v["cia"], VDD / 2, True, e2 - 5e-9)) * 1e9
    res["OFPH fall - CIB 50 % (ns)"] = (cross(t, v["ofph"], VDD / 2, False, e1 - 5e-9)
                                        - cross(t, v["cib"], VDD / 2, True, e1 - 5e-9)) * 1e9
    # output chopper: low through the blanking window, then high
    res["CDB rise - blank end (ns)"] = (cross(t, v["cdb"], VDD / 2, True, e1 - 5e-9)
                                        - cross(t, v["blank"], VDD / 2, False, e1 - 5e-9)) * 1e9
    w = (t > e1 - TM + 5e-9) & (t < e1 + 7 * TM - 1e-9)  # after the gates have turned off
    res["CDA/CDB max in blanking (V)"] = max(v["cda"][w].max(), v["cdb"][w].max())
    m = t > 50e-9 + 1e-9
    res["supply charge per edge (pC)"] = -np.trapezoid(v["idd"][m], t[m]) / 4 * 1e12
    return corner, temp, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", nargs="+", default=["typical:27", "ss:85", "ff:-20"])
    a = ap.parse_args()
    cases = [(c.split(":")[0], int(c.split(":")[1])) for c in a.corners]
    with ThreadPoolExecutor(len(cases)) as ex:
        res = list(ex.map(lambda c: run(*c), cases))
    keys = list(res[0][2])
    print("| quantity | " + " | ".join(f"{c} {t} C" for c, t, _ in res) + " |")
    print("|---|" + "---|" * len(res))
    for k in keys:
        print(f"| {k} | " + " | ".join(f"{r[k]:.2f}" for _, _, r in res) + " |")


if __name__ == "__main__":
    main()
