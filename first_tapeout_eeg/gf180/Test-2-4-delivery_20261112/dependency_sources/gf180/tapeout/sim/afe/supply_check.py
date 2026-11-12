#!/usr/bin/env python3
"""Supply of the AFE clock driver (tracker A5/C1, documentation/gf180_test_decap_20261022.md):
chopped transient of eeg_afe with its clock driver eeg_afe_clk (the --clkdrv deck of
afe_offset.py, blanking 7 MCLK) on a model of the supply network.

Network: ideal 3.3 V at the package; AVDD and AVSS each through --npad bond wires of
--lpad and --rpad in parallel to the pad nodes PADD/PADS; between the pad nodes the pad
and ESD capacitance --cpad, the decoupling of the rest of the chip --cother and its load
--iother; on-chip rails of --rrail per side to the amplifier, which has --camp of local
decoupling between its VDD and VSS. The bias inputs of the amplifier (VBN, VBCM, the
booster bias currents) are referred to its own VSS; VCM, the electrodes and the ADC load
are referred to the board ground. The driver supply is one of
  ideal      the driver and the amplifier on ideal 3.3 V (the reference)
  shared     the driver on the amplifier rails
  sep:R[:C]  AVDD_CLK/AVSS_CLK from the pad nodes through R ohm on each side, with
             C (default --cclk) between them next to the driver

The electrode input is 0 until --tstep and --vin after it, so one run gives the output
offset (average over chopper periods 8..12) and the gain (periods 16..25).
Printed per configuration: offset and gain against the ideal run, the largest
deviation of the amplifier supply (VDD - VSS) at a chopper edge and the time until it
stays within 1 mV, the droop of the driver supply, the dead time of the input chopper
(the TG of one phase stops conducting, NMOS gate below 2.35 V and PMOS gate above
0.95 V, i.e. 1.65 V +- 0.7 V, until one of the other phase starts), and the peak
current in the bond wires.

The defaults reproduce the table of the document (adopted: sep:100:150e-12, 100 ohm per
side and 150 pF). --tg-bulk ideal puts the wells and substrate of the input-chopper TGs
on ideal supplies; it showed that the 25 mV left on the amplifier supply with the
driver separated comes through them.

Usage: python3 supply_check.py [--configs ideal shared sep:2 sep:100:150e-12 ...]
       [--cclk 300e-12] [--camp 200e-12] [--lpad 2e-9] [--npad 3] [--tstop 200e-6]
       [--tg-bulk amp|ideal]
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_offset

HERE = os.path.dirname(os.path.abspath(__file__))
TCH = afe_offset.TCH
VTN, VTP = 2.35, 0.95  # conduction thresholds of the input TG gates (signal 1.65 V)


def deck(cfg, o, afe=afe_offset.AFE):
    d = afe_offset.deck(0.0, 0, 0, o.rs, o.tstop, 7 / 32.768e6, afe=afe, clkdrv=True)

    def sub(old, new):
        nonlocal d
        assert d.count(old) == 1, old
        d = d.replace(old, new)

    if cfg == "ideal":
        net = "VSUP VDD 0 3.3\nVSSA0 VSSA 0 0"
        dv, ds = "VDD", "VSSA"
    else:
        net = "\n".join([
            "VSUP SUPP 0 3.3",
            f"LPD SUPP PDL {o.lpad / o.npad:.4g}", f"RPD PDL PADD {o.rpad / o.npad:.4g}",
            f"LPS 0 PSL {o.lpad / o.npad:.4g}", f"RPS PSL PADS {o.rpad / o.npad:.4g}",
            f"CPAD PADD PADS {o.cpad * o.npad:.4g}", f"COTH PADD PADS {o.cother:.4g}",
            f"IOTH PADD PADS {o.iother:.4g}",
            f"RRD PADD VDD {o.rrail:.4g}", f"RRS PADS VSSA {o.rrail:.4g}",
            f"CAMP VDD VSSA {o.camp:.4g}"])
        if cfg == "shared":
            dv, ds = "VDD", "VSSA"
        else:
            f = cfg.split(":")
            r, c = float(f[1]), float(f[2]) if len(f) > 2 else o.cclk
            net += f"\nRCD PADD VDDC {r:g}\nRCS PADS VSSC {r:g}\nCCLK VDDC VSSC {c:.4g}"
            dv, ds = "VDDC", "VSSC"
    if o.tg_bulk == "ideal":
        net += "\n.global VDDI\nVDDI VDDI 0 3.3"
    sub("VDD VDD 0 3.3\n", net + "\n")
    sub("VBN VBN 0 ", "VBN VBN VSSA ")
    sub("VBCM VBCM 0 ", "VBCM VBCM VSSA ")
    sub("IBLP BLP 0 ", "IBLP BLP VSSA ")
    sub("VSRC SRC 0 DC 0\n", f"VSRC SRC 0 PWL(0 0 {o.tstep:.6e} 0 {o.tstep + 10e-9:.6e} {o.vin:.6e})\n")
    i0 = d.index("+ OFPH ")
    i1 = d.index("\n", i0)
    sub(d[i0:i1], "+ OFPH" + " VSSA" * 18 + " VDD VDD VSSA eeg_afe")  # offset DAC off, CPF_TRIM 8
    sub("XCLK CHOP_S CHOP_S BLANK_S VDD 0 CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RSTX VDD 0 eeg_afe_clk",
        f"XCLK CHOP_S CHOP_S BLANK_S {dv} {ds} CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RSTX {dv} {ds} eeg_afe_clk")
    sub("wrdata tr.csv vo va v(cda) v(cdb)",
        f"let vsa = v(vdd) - v(vssa)\nlet vsc = v({dv}) - v({ds})\n"
        "wrdata tr.csv vo vsa vsc v(cia) v(ncia) v(cib) v(ncib) i(vsup)")
    return d


def cross(t, v, level, rising, after):
    m = t > after
    tt, vv = t[m], v[m]
    s = (vv[:-1] < level) & (vv[1:] >= level) if rising else (vv[:-1] > level) & (vv[1:] <= level)
    i = np.flatnonzero(s)
    if not i.size:
        return float("nan")
    i = i[0]
    return tt[i] + (level - vv[i]) * (tt[i + 1] - tt[i]) / (vv[i + 1] - vv[i])


def run(cfg, o):
    f = cfg.split(":")
    c = float(f[2]) if len(f) > 2 else o.cclk
    tag = "_tgideal" if o.tg_bulk == "ideal" else ""
    d = os.path.join(HERE, "runs", f"supply_{f[0]}{''.join(f[1:2])}_c{c * 1e12:g}p_l{o.lpad * 1e9:g}n{tag}")
    os.makedirs(d, exist_ok=True)
    afe = afe_offset.AFE
    if o.tg_bulk == "ideal":  # input-chopper TG wells and substrate on ideal supplies (diagnostic)
        txt = open(afe).read()
        assert txt.count("VDD VSS eeg_afe_input_tg") == 4
        afe = os.path.join(d, "eeg_afe_tgideal.spice")
        open(afe, "w").write(txt.replace("VDD VSS eeg_afe_input_tg", "VDDI 0 eeg_afe_input_tg"))
    open(os.path.join(d, "tb.spice"), "w").write(deck(cfg, o, afe))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    os.remove(os.path.join(d, "tr.csv"))
    t = x[:, 0]
    vo, vsa, vsc, cia, ncia, cib, ncib, isup = (x[:, 2 * k + 1] for k in range(8))
    q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
    avg = lambda k0, k1: (np.interp(k1 * TCH, t, q) - np.interp(k0 * TCH, t, q)) / ((k1 - k0) * TCH)
    res = {"off": avg(8, 12), "sig": avg(16, 25)}
    # supply deviations at the chopper edges (every TCH / 2) in periods 16..25
    dev, settle, droop = [], [], []
    for e in np.arange(32, 50) * TCH / 2:
        pre = (t >= e - 400e-9) & (t <= e - 100e-9)
        w = (t >= e - 50e-9) & (t <= e + 2e-6)
        a0 = np.trapezoid(vsa[pre], t[pre]) / (t[pre][-1] - t[pre][0])
        c0 = np.trapezoid(vsc[pre], t[pre]) / (t[pre][-1] - t[pre][0])
        da = vsa[w] - a0
        dev.append(da[np.argmax(np.abs(da))])
        out = np.flatnonzero(np.abs(da) > 1e-3)
        settle.append(t[w][out[-1]] - e if out.size else 0.0)
        droop.append((vsc[w] - c0).min())
    k = np.argmax(np.abs(dev))
    res["dev"], res["settle"], res["droop"] = dev[k], max(settle), min(droop)
    # dead times at the last edges: A -> B at 25 TCH, B -> A at 25.5 TCH
    e1, e2 = 25 * TCH, 25.5 * TCH
    a_off = max(cross(t, cia, VTN, False, e1 - 5e-9), cross(t, ncia, VTP, True, e1 - 5e-9))
    b_on = min(cross(t, cib, VTN, True, e1 - 5e-9), cross(t, ncib, VTP, False, e1 - 5e-9))
    b_off = max(cross(t, cib, VTN, False, e2 - 5e-9), cross(t, ncib, VTP, True, e2 - 5e-9))
    a_on = min(cross(t, cia, VTN, True, e2 - 5e-9), cross(t, ncia, VTP, False, e2 - 5e-9))
    res["dead"] = (min(b_on - a_off, a_on - b_off))
    w = (t >= 16 * TCH) & (t <= 25 * TCH)
    res["ipk"] = np.abs(isup[w]).max()
    return cfg, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["ideal", "shared", "sep:2", "sep:50", "sep:100", "sep:100:150e-12",
                                                     "sep:100:100e-12", "sep:200", "sep:1000"])
    ap.add_argument("--cclk", type=float, default=300e-12)
    ap.add_argument("--camp", type=float, default=200e-12)
    ap.add_argument("--lpad", type=float, default=2e-9)
    ap.add_argument("--rpad", type=float, default=0.1)
    ap.add_argument("--npad", type=int, default=3)
    ap.add_argument("--cpad", type=float, default=3e-12, help="per pad, with the ESD")
    ap.add_argument("--cother", type=float, default=100e-12, help="decoupling of the rest of the chip (ADC)")
    ap.add_argument("--iother", type=float, default=5e-3, help="DC load of the rest of the chip")
    ap.add_argument("--rrail", type=float, default=0.3)
    ap.add_argument("--rs", type=float, default=100.0)
    ap.add_argument("--tg-bulk", choices=["amp", "ideal"], default="amp",
                    help="bulks of the input-chopper TGs: the amplifier rails, or ideal supplies (diagnostic)")
    ap.add_argument("--vin", type=float, default=1e-3)
    ap.add_argument("--tstep", type=float, default=96e-6)
    ap.add_argument("--tstop", type=float, default=200e-6)
    o = ap.parse_args()
    with ThreadPoolExecutor(len(o.configs)) as ex:
        res = dict(ex.map(lambda c: run(c, o), o.configs))
    ref = res.get("ideal")
    print(f"bond wires {o.npad} x {o.lpad * 1e9:g} nH per side, amplifier decap {o.camp * 1e12:g} pF, "
          f"driver decap {o.cclk * 1e12:g} pF; input {o.vin * 1e3:g} mV after {o.tstep * 1e6:g} us")
    print("| supply of the driver | output offset (mV) | gain | gain change (ppm) | amplifier supply at the "
          "edges, largest deviation (mV) | within 1 mV after (ns) | driver supply droop (V) | dead time (ns) "
          "| peak bond-wire current (mA) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for c, r in res.items():
        g = (r["sig"] - r["off"]) / o.vin
        dg = (g / ((ref["sig"] - ref["off"]) / o.vin) - 1) * 1e6 if ref else float("nan")
        print(f"| {c} | {r['off'] * 1e3:+.3f} | {g:.2f} | {dg:+.0f} | {r['dev'] * 1e3:+.1f} | "
              f"{r['settle'] * 1e9:.0f} | {r['droop']:+.3f} | {r['dead'] * 1e9:.2f} | {r['ipk'] * 1e3:.1f} |")


if __name__ == "__main__":
    main()
