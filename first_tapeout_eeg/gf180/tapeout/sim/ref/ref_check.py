#!/usr/bin/env python3
"""Checks of the reference filter eeg_ref (gf180/tapeout/adc/eeg_ref.spice), tracker B6.

Pads driven by an ideal external reference (VCM +- 0.25 V) through 2 nH and 0.2 ohm
per side (bond wire and package; the asig_5p0 pad's own 1.2 ohm in addition). Load:
the constant reference current (30 uA from VREFP into VREFN), plus the DAC1 break of
every frame (all 62 switch nodes rise about 88 mV for 2 ns, the resistor currents
drop by up to 35 %: modelled as a 9 uA, 2 ns dip on each reference at e4).

  dc     VREFP - VREFN at the filter output
  ripple deviation of VREFP - VREFN at the next comparator strobe (e0, 28 MCLK after
         the break) and its peak
  noise  in-band (0.5..100 Hz) differential noise of the filter resistors

Usage: python3 ref_check.py [--corners typical:27 ss:85 ff:-20]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
REF = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
VCM = 1.65
T = 1 / 1.024e6
TM = T / 32
RES = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff"}
CAPS = {"typical": "typical", "ss": "ss", "ff": "ff"}


def deck(corner, temp):
    t4 = 2e-6 + 4 * TM
    dip = f"PULSE(0 9u {t4:.10e} 0.2n 0.2n 1.8n {T:.10e})"
    return f"""* eeg_ref check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.lib {PDK}/sm141064.ngspice {RES[corner]}
.lib {PDK}/sm141064.ngspice mimcap_{CAPS[corner]}
.lib {PDK}/sm141064.ngspice cap_mim
.lib {PDK}/sm141064.ngspice moscap_{CAPS[corner]}
.include {REF}
.temp {temp}
.options sparse reltol=1e-6 abstol=1e-15 vntol=1e-9
VEP EP 0 DC {VCM + 0.25} AC 0.5
VEN EN 0 DC {VCM - 0.25} AC -0.5
LBP EP BP 2n
RBP BP PADP 0.2 noisy=0
LBN EN BN 2n
RBN BN PADN 0.2 noisy=0
XR PADP PADN VREFP VREFN 0 eeg_ref
* constant load 30 uA (VREFP -> VREFN) and the break dips of DAC1
ILOAD VREFP VREFN DC 30u
IDP VREFP 0 {dip}
IDN 0 VREFN {dip}
.control
set noaskquit
op
print v(vrefp)-v(vrefn) v(padp)-v(padn)
tran 0.02n {2e-6 + 3 * T:.6e} 0 0.1n
wrdata tr.csv v(vrefp)-v(vrefn)
noise v(vrefp, vrefn) VEP dec 20 0.1 1e6 1
print onoise_total
setplot noise1
wrdata nz.csv onoise_spectrum
quit
.endc
.end
"""


def run(corner, temp):
    d = os.path.join(HERE, "runs", f"ref_{corner}_{temp}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(corner, temp))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    vdc = float(re.search(r"v\(vrefp\)-v\(vrefn\) = ([-0-9.e+]+)", log).group(1))
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, v = x[:, 0], x[:, 1]
    e4 = 2e-6 + T + 4 * TM  # the second frame's break
    base = np.interp(e4 - 50e-9, t, v)
    m = (t > e4) & (t < e4 + 0.9 * T)
    peak = np.abs(v[m] - base).max()
    at_strobe = np.interp(e4 - 4 * TM + T, t, v) - base
    nz = np.loadtxt(os.path.join(d, "nz.csv"))
    f, s = nz[:, 0], nz[:, 1]
    band = (f >= 0.5) & (f <= 100)
    vn = np.sqrt(np.trapezoid(s[band] ** 2, f[band]))
    return corner, temp, {"VREFP - VREFN (V)": vdc, "break ripple peak (uV)": peak * 1e6,
                          "at the next strobe (uV)": at_strobe * 1e6, "filter noise 0.5-100 Hz (nVrms)": vn * 1e9}


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
        print(f"| {k} | " + " | ".join(f"{r[k]:.4g}" for _, _, r in res) + " |")


if __name__ == "__main__":
    main()
