#!/usr/bin/env python3
"""DC check of the analog test multiplexer eeg_testmux (gf180/tapeout/test/eeg_testmux.spice),
tracker A5.

Every source node is an ideal voltage with its own value; ITST is an ideal 31.4 uA
current source (the eeg_bias mirror). For each TEST_CFG[4:0] code the ATP voltage is
read with a 1 Mohm load (voltage codes), or the current into ATP held at 1 V (code 11).
With TC4 = 0 every switch must be open: ATP then follows only its load, and with ATP
driven to 3.3 V the current into the dynamic nodes (AFE outputs, O2) stays at leakage.

Usage: python3 testmux_check.py [--corner typical] [--temp 27]
"""
import argparse
import os
import re
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
MUX = os.path.join(REPO, "gf180", "tapeout", "test", "eeg_testmux.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
SRC = {"VCM": 1.65, "VREFP": 1.9, "VREFN": 1.4, "VBN": 0.85, "VBCM": 0.82, "VBN1": 0.851, "VNC1": 2.0,
       "VPC1": 1.7, "VBPC2": 1.8, "VBNC2": 1.5, "AOP": 1.61, "AON": 1.69, "O2P": 1.63, "O2N": 1.67}
ORDER = ["AVSS", "VCM", "VREFP", "VREFN", "VBN", "VBCM", "VBN1", "VNC1", "VPC1", "VBPC2", "VBNC2",
         "ITST", "AOP", "AON", "O2P", "O2N"]


def deck(code, en, atp, corner, temp):
    tc = [(code >> i) & 1 for i in range(4)] + [en]
    srcs = "\n".join(f"V{n} {n} 0 {v}" for n, v in SRC.items())
    nodes = " ".join(n for n in ORDER if n != "AVSS")
    atp_line = {"load": "RATP ATP 0 1Meg", "hold1": "VATP ATP 0 1", "drive": "VATP ATP 0 3.3"}[atp]
    return f"""* eeg_testmux check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.include {MUX}
.temp {temp}
VDD AVDD 0 3.3
{srcs}
IITST AVDD ITST 31.4u
* the mirror cannot pull above about 3 V; keeps ITST defined if both TGs were off
DITST ITST AVDD dclamp
.model dclamp d is=1e-15
{chr(10).join(f"VTC{i} TC{i} 0 {3.3 * b}" for i, b in enumerate(tc))}
{atp_line}
XM ATP TC0 TC1 TC2 TC3 TC4 {nodes} AVDD 0 eeg_testmux
.control
set noaskquit
op
print v(atp) {' '.join(f'i(v{n.lower()})' for n in SRC)} {'i(vatp)' if atp != 'load' else ''}
quit
.endc
.end
"""


def run(code, en, atp, o):
    d = os.path.join(HERE, "runs", f"tm_{o.corner}_{o.temp}_{code}_{en}_{atp}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(code, en, atp, o.corner, o.temp))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=int, default=27)
    o = ap.parse_args()
    print(f"{o.corner} {o.temp} C")
    print("| code | node | expected | ATP | error |")
    print("|---|---|---|---|---|")
    worst = 0.0
    for code, node in enumerate(ORDER):
        if node == "ITST":
            v = run(code, 1, "hold1", o)
            i = v["i(vatp)"]  # current from the ATP node into the 1 V source
            print(f"| {code} | ITST | 31.4 uA into ATP | {i * 1e6:.2f} uA | {(i - 31.4e-6) * 1e9:+.1f} nA |")
            continue
        v = run(code, 1, "load", o)
        exp = 0.0 if node == "AVSS" else SRC[node]
        err = v["v(atp)"] - exp
        worst = max(worst, abs(err))
        print(f"| {code} | {node} | {exp:.3f} | {v['v(atp)']:.4f} | {err * 1e3:+.3f} mV |")
    off = run(5, 0, "load", o)
    drv = run(12, 0, "drive", o)
    leak = max(abs(drv[f"i(v{n})"]) for n in ("aop", "aon", "o2p", "o2n"))
    leak_bias = max(abs(drv[f"i(v{n.lower()})"]) for n in SRC if n not in ("AOP", "AON", "O2P", "O2N"))
    print(f"TC4 = 0: ATP {off['v(atp)'] * 1e3:.3f} mV with 1 Mohm to ground; ATP driven to 3.3 V: "
          f"largest current into AOP/AON/O2P/O2N {leak * 1e12:.2f} pA, into the bias/reference nodes "
          f"{leak_bias * 1e12:.2f} pA; worst selected-voltage error {worst * 1e3:.3f} mV")


if __name__ == "__main__":
    main()
