#!/usr/bin/env python3
"""Timing of the OTA1 chopper driver eeg_adc_clk (gf180/tapeout/adc/eeg_adc_clk.spice)
with the real OTA1 (eeg_adc_otas.spice, inputs at CM, outputs 680.5 + 4 pF) as load.

CHOP1 falls at 100 ns (A -> B) and rises at 300 ns (B -> A). Per edge, with "new"/"old"
the phase being entered/left:
  dead      input TG of the old phase fully off (NMOS gate < 0.3 V and PMOS gate
            > VDD - 0.3 V) until the new one starts to conduct (NMOS gate > 0.7 V or
            PMOS gate < VDD - 0.7 V)
  overlap   new commutator gate 50 % up until old commutator gate 50 % down
  margin 1  new commutator fully on (gate > VDD - 0.3 V, complement < 0.3 V) until the
            old input TG starts to turn off (gate < VDD - 0.3 V or complement > 0.3 V)
  margin 2  new input TG fully on until the old commutator starts to turn off
  delay     CHOP1 edge to the new commutator gate at 50 %
  edges     10-90 % of CIA and NCIA, CDA and NCDA (the edge at B -> A)
A negative margin means the input TGs start to swap before the commutators of both
phases conduct (margin 1) or a commutator opens before the new input TG has closed
(margin 2).

Usage: python3 aclk_check.py [--corners typical:27 ss:85 ff:-20 sf:27 fs:27]
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CLK = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc_clk.spice")
OTAS = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc_otas.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
VDD = 3.3
E1, E2 = 100e-9, 300e-9
CAPC = {"ss": "ss", "ff": "ff"}  # MIM corner (the OTA compensation caps)
NAMES = ["chop1", "cia", "ncia", "cib", "ncib", "cda", "ncda", "cdb", "ncdb", "idd"]


def deck(corner, temp):
    return f"""* eeg_adc_clk timing with OTA1 as load
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.lib {PDK}/sm141064.ngspice mimcap_{CAPC.get(corner, 'typical')}
.lib {PDK}/sm141064.ngspice cap_mim
.include {OTAS}
.include {CLK}
.temp {temp}
.options sparse reltol=1e-4
VDD VDD 0 {VDD}
VCM CM 0 1.65
VBN1 VBN1 0 .85
VNC1 VNC1 0 2
VPC1 VPC1 0 1.7
VBCM1 VBCM1 0 .82
VCH CHOP1 0 PULSE({VDD} 0 {E1 - 0.25e-9:.6e} 0.5n 0.5n {E2 - E1 - 0.5e-9:.6e} 1u)
VCLK VCLK 0 {VDD}
XC CHOP1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VCLK 0 eeg_adc_clk
XOTA1 CM CM O1P O1N CM VBN1 VNC1 VPC1 VBCM1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD 0 gf180_inside_cascode_ota
C1P O1P 0 684.5p
C1N O1N 0 684.5p
.control
set noaskquit
tran 0.01n 500n 0 0.05n
wrdata out.csv v(chop1) v(cia) v(ncia) v(cib) v(ncib) v(cda) v(ncda) v(cdb) v(ncdb) i(vclk)
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


def tg_on_start(t, g, gb, after):
    """first time a TG (gate g, complement gb) starts to conduct"""
    return min(cross(t, g, 0.7, True, after), cross(t, gb, VDD - 0.7, False, after))


def tg_full_on(t, g, gb, after):
    return max(cross(t, g, VDD - 0.3, True, after), cross(t, gb, 0.3, False, after))


def tg_off_start(t, g, gb, after):
    return min(cross(t, g, VDD - 0.3, False, after), cross(t, gb, 0.3, True, after))


def tg_full_off(t, g, gb, after):
    return max(cross(t, g, 0.3, False, after), cross(t, gb, VDD - 0.3, True, after))


def run(corner, temp):
    d = os.path.join(HERE, "runs", f"aclk_{corner}_{temp}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(corner, temp))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    res = {}
    for e, old, new, tag in ((E1, "a", "b", "A->B"), (E2, "b", "a", "B->A")):
        a0 = e - 2e-9
        ci_old, nci_old = v[f"ci{old}"], v[f"nci{old}"]
        ci_new, nci_new = v[f"ci{new}"], v[f"nci{new}"]
        cd_old, ncd_old = v[f"cd{old}"], v[f"ncd{old}"]
        cd_new, ncd_new = v[f"cd{new}"], v[f"ncd{new}"]
        res[f"dead {tag} (ns)"] = (tg_on_start(t, ci_new, nci_new, a0) - tg_full_off(t, ci_old, nci_old, a0)) * 1e9
        res[f"overlap {tag} (ns)"] = (cross(t, cd_old, VDD / 2, False, a0) - cross(t, cd_new, VDD / 2, True, a0)) * 1e9
        res[f"margin 1 {tag} (ns)"] = (tg_off_start(t, ci_old, nci_old, a0) - tg_full_on(t, cd_new, ncd_new, a0)) * 1e9
        res[f"margin 2 {tag} (ns)"] = (tg_off_start(t, cd_old, ncd_old, a0) - tg_full_on(t, ci_new, nci_new, a0)) * 1e9
        res[f"delay {tag} (ns)"] = (cross(t, cd_new, VDD / 2, True, a0) - e) * 1e9
    a0 = E2 - 2e-9
    res["CIA rise 10-90 (ns)"] = (cross(t, v["cia"], 0.9 * VDD, True, a0) - cross(t, v["cia"], 0.1 * VDD, True, a0)) * 1e9
    res["NCIA fall 90-10 (ns)"] = (cross(t, v["ncia"], 0.1 * VDD, False, a0)
                                   - cross(t, v["ncia"], 0.9 * VDD, False, a0)) * 1e9
    res["CDA rise 10-90 (ns)"] = (cross(t, v["cda"], 0.9 * VDD, True, a0) - cross(t, v["cda"], 0.1 * VDD, True, a0)) * 1e9
    res["NCDA fall 90-10 (ns)"] = (cross(t, v["ncda"], 0.1 * VDD, False, a0)
                                   - cross(t, v["ncda"], 0.9 * VDD, False, a0)) * 1e9
    m = t > 50e-9
    res["supply charge per edge (pC)"] = -np.trapezoid(v["idd"][m], t[m]) / 2 * 1e12
    return corner, temp, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", nargs="+", default=["typical:27", "ss:85", "ff:-20", "sf:27", "fs:27"])
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
