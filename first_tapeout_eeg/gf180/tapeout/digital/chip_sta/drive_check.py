#!/usr/bin/env python3
"""Transistor-level check of the long digital-to-analog nets (tracker C3, chip_nets.py).

1. drive: the output buffer of eeg_digital_top (gf180mcu_fd_sc_mcu9t5v0__buf_1, as in the
   macro now; buf_16 for comparison) driving the extracted net as an RC ladder of 20
   sections (R and the wire capacitance C_iso + C_cpl of build/nets.json) with the
   receiver's gate load at the end. Edge time (30-70 % and 10-90 %) and delay (50 %
   from the buffer input) at the receiver.
2. aclk: the AFE clock driver eeg_afe_clk (gf180/tapeout/afe/eeg_afe_clk.spice) with
   CHOP, CHOP_OUT (= CHOP, CHOP_DLY = 0) and CHOP_BLANK (1 MCLK before to 7 MCLK after
   each edge) each from a buffer of that strength through its own extracted net, on
   its real supply (AVDD_CLK / AVSS_CLK through 100 ohm per side, 150 pF next to the
   driver; the digital buffers on an ideal DVDD) and with the loads of clk_check.py.
   Counted per CHOP edge: crossings of VDD/2 of each output in a window around it
   (exactly one expected: more is a glitch), the dead time of the input chopper and
   the delay from the CHOP buffer input to CIA / CIB.
3. adcclk: the OTA1 chopper driver eeg_adc_clk with the real OTA1 as load
   (gf180/tapeout/sim/adc_loop/aclk_check.py), CHOP1 from a buffer through its
   extracted net: dead time, commutator overlap, the two order margins and the delay
   per edge, as in aclk_check.py, and the VDD/2 crossings of every phase per edge.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/drive_check.py
       [--corners ss:125:3.0 typical:27:3.3 ff:-40:3.6] [--only drive|aclk|adcclk]
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD")
MODELS = os.path.join(PDK, "libs.tech", "ngspice")
CELLS = os.path.join(PDK, "libs.ref", "gf180mcu_fd_sc_mcu9t5v0", "spice", "gf180mcu_fd_sc_mcu9t5v0.spice")
ACLK = os.path.join(REPO, "gf180", "tapeout", "afe", "eeg_afe_clk.spice")
RUNS = os.path.join(HERE, "build", "spice")
NSEG = 20
TM = 1 / 32.768e6
AVDD = 3.3


def ladder(name, a, b, r, c, cend):
    """RC ladder from node a to node b: NSEG sections of r / NSEG and c / NSEG."""
    lines = []
    prev = a
    for k in range(NSEG):
        nxt = b if k == NSEG - 1 else f"{name}_{k}"
        lines.append(f"R{name}{k} {prev} {nxt} {r / NSEG:.4f}")
        lines.append(f"C{name}{k} {nxt} 0 {c / NSEG * 1e-15:.4e}")
        prev = nxt
    lines.append(f"C{name}e {b} 0 {cend * 1e-15:.4e}")
    return lines


def net_rc(nets, n):
    d = nets[n]
    i = max(range(1, len(d["r_typ"])), key=lambda j: d["r_typ"][0][j])
    return d["r_typ"][0][i], d["c_iso_fF"] + d["c_cpl_fF"], sum(d["sink_cap_fF"])


def header(corner, temp):
    return [f".include {MODELS}/design.ngspice", f".lib {MODELS}/sm141064.ngspice {corner}", f".include {CELLS}",
            f".temp {temp}", ".options sparse reltol=1e-4"]


def cross(t, v, level, rising, after, before=np.inf):
    m = (t > after) & (t < before)
    tt, vv = t[m], v[m]
    s = (vv[:-1] < level) & (vv[1:] >= level) if rising else (vv[:-1] > level) & (vv[1:] <= level)
    i = np.flatnonzero(s)
    if not i.size:
        return float("nan")
    i = i[0]
    return tt[i] + (level - vv[i]) * (tt[i + 1] - tt[i]) / (vv[i + 1] - vv[i])


def ncross(t, v, level, after, before):
    m = (t > after) & (t < before)
    vv = v[m] - level
    return int(np.count_nonzero(np.signbit(vv[:-1]) != np.signbit(vv[1:])))


def spice(d, deck, cols):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    return x[:, 0], {n: x[:, 2 * i + 1] for i, n in enumerate(cols)}


def drive(nets, corner, temp, vdd, cell, n):
    r, c, cg = net_rc(nets, n)
    deck = header(corner, temp) + [
        f"VDD VDD 0 {vdd}",
        f"VIN IN 0 PULSE(0 {vdd} 5n 0.3n 0.3n 300n 600n)",
        f"X1 IN Z VDD VDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}"] + ladder("w", "Z", "RX", r, c, cg) + [
        ".control", "set noaskquit", "tran 0.02n 610n 0 0.05n", "wrdata out.csv v(in) v(z) v(rx)", "quit", ".endc", ".end"]
    t, v = spice(os.path.join(RUNS, f"drive_{n}_{cell}_{corner}_{temp}"), "\n".join(deck) + "\n", ["in", "z", "rx"])
    res = {}
    for edge, rising, t0 in (("rise", True, 4e-9), ("fall", False, 304e-9)):
        lv = [cross(t, v["rx"], f * vdd, rising, t0) for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        if not rising:
            lv = [cross(t, v["rx"], f * vdd, False, t0) for f in (0.9, 0.7, 0.5, 0.3, 0.1)]
        tin = cross(t, v["in"], vdd / 2, rising, t0)
        res[edge] = {"t3070": (lv[3] - lv[1]) * 1e9, "t1090": (lv[4] - lv[0]) * 1e9, "delay": (lv[2] - tin) * 1e9}
    return n, cell, corner, temp, res


def aclk(nets, corner, temp, vdd, cell):
    T = 1 / 128e3
    tstop = 50e-9 + T + 400e-9
    edges = [50e-9 + k * T / 2 for k in range(3)]
    chop = f"PULSE(0 {vdd} 50n 0.3n 0.3n {T / 2 - 0.3e-9:.6e} {T:.6e})"
    bl = [(0.0, 0.0)]
    for e in edges:
        bl += [(e - TM, 0.0), (e - TM + 0.3e-9, vdd), (e + 7 * TM, vdd), (e + 7 * TM + 0.3e-9, 0.0)]
    bl = [p for p in bl if p[0] >= 0]
    blank = " ".join(f"{a:.6e} {b:g}" for a, b in bl)
    deck = header(corner, temp) + [
        f"VDDD DVDD 0 {vdd}",
        f"VAV PADD 0 {AVDD}",
        "RCKP PADD AVDD_CLK 100", "RCKN AVSS_CLK 0 100", "CCK AVDD_CLK AVSS_CLK 150p",
        f"VCH CHI 0 {chop}", f"VBL BLI 0 PWL({blank})",
        f"XB1 CHI CHZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}",
        f"XB2 CHI COZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}",
        f"XB3 BLI BLZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}"]
    for nm, z, x in (("CHOP", "CHZ", "CHOP"), ("CHOP_OUT", "COZ", "CHOP_OUT"), ("CHOP_BLANK", "BLZ", "CHOP_BLANK")):
        r, c, cg = net_rc(nets, nm)
        deck += ladder(nm.lower(), z, x, r, c, 0.0)
    deck += [f".include {ACLK}",
             "VEN CHOP_EN 0 3.3", "VRS AFE_RST 0 0",
             "XC CHOP CHOP_OUT CHOP_BLANK CHOP_EN AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RST AVDD_CLK AVSS_CLK eeg_afe_clk",
             "CL1 CIA AVSS_CLK 16.6p", "CL2 NCIA AVSS_CLK 33p", "CL3 CIB AVSS_CLK 16.6p", "CL4 NCIB AVSS_CLK 33p",
             "CL5 CDA AVSS_CLK 0.3p", "CL6 NCDA AVSS_CLK 0.6p", "CL7 CDB AVSS_CLK 0.3p", "CL8 NCDB AVSS_CLK 0.6p",
             "CL9 OFPH AVSS_CLK 0.2p",
             ".control", "set noaskquit", f"tran 0.02n {tstop:.6e} 0 0.1n",
             "wrdata out.csv v(chi) v(chop) v(cia) v(ncia) v(cib) v(ncib) v(cda) v(cdb) v(avdd_clk) v(avss_clk) v(chop_blank) v(xc.chopb)",
             "quit", ".endc", ".end"]
    cols = ["chi", "chop", "cia", "ncia", "cib", "ncib", "cda", "cdb", "avdd", "avss", "blank", "chopb"]
    t, v = spice(os.path.join(RUNS, f"aclk_{cell}_{corner}_{temp}"), "\n".join(deck) + "\n", cols)
    res = {"glitch": {}, "edge": []}
    for k, e in enumerate(edges[1:], 1):
        w0, w1 = e - 0.5 * TM, e + 9 * TM
        g = {n: ncross(t, v[n], AVDD / 2, w0, w1) for n in ("cia", "ncia", "cib", "ncib", "chopb")}
        # output chopper: one fall at the blanking start (1 MCLK before) and one rise at its end
        g["cda+cdb"] = ncross(t, v["cda"], AVDD / 2, e - 1.5 * TM, w1) + ncross(t, v["cdb"], AVDD / 2, e - 1.5 * TM, w1)
        res["glitch"][f"edge{k}"] = g
        rising = (k % 2 == 0)          # edge 1: CHOP falls (A -> B), edge 2: CHOP rises (B -> A)
        on = "cia" if rising else "cib"
        off_n, off_p = ("cib", "ncib") if rising else ("cia", "ncia")
        on_n, on_p = ("cia", "ncia") if rising else ("cib", "ncib")
        t_off = max(cross(t, v[off_n], 0.3, False, e - 2e-9), cross(t, v[off_p], AVDD - 0.3, True, e - 2e-9))
        t_on = min(cross(t, v[on_n], 0.7, True, e - 2e-9), cross(t, v[on_p], AVDD - 0.7, False, e - 2e-9))
        t_in = cross(t, v["chi"], vdd / 2, rising, e - 2e-9)
        sup = (t > e) & (t < e + 60e-9)
        res["edge"].append({"edge": "rise" if rising else "fall", "dead_ns": (t_on - t_off) * 1e9,
                            "delay_ns": (cross(t, v[on], AVDD / 2, True, e - 2e-9) - t_in) * 1e9,
                            "chop_t1090_ns": abs(cross(t, v["chop"], (0.9 if rising else 0.1) * vdd, rising, e - 2e-9)
                                                 - cross(t, v["chop"], (0.1 if rising else 0.9) * vdd, rising, e - 2e-9)) * 1e9,
                            "supply_min_V": float((v["avdd"][sup] - v["avss"][sup]).min())})
    return cell, corner, temp, res


def adcclk(nets, corner, temp, vdd, cell):
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "adc_loop"))
    import aclk_check as ac
    deck = ac.deck(corner, int(temp))
    old = [ln for ln in deck.splitlines() if ln.startswith("VCH CHOP1")][0]
    r, c, cg = net_rc(nets, "CHOP1")
    new = [f".include {CELLS}", f"VDDD DVDD 0 {vdd}", old.replace("VCH CHOP1", "VCH CHI").replace(f"PULSE({ac.VDD} 0", f"PULSE({vdd} 0"),
           f"XB1 CHI CHZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}"] + ladder("ch1", "CHZ", "CHOP1", r, c, 0.0)
    deck = deck.replace(old, "\n".join(new)).replace(f".temp {int(temp)}", f".temp {temp}")
    deck = deck.replace("wrdata out.csv v(chop1)", "wrdata out.csv v(chi) v(chop1)")
    names = ["chi"] + ac.NAMES
    t, v = spice(os.path.join(RUNS, f"adcclk_{cell}_{corner}_{temp}"), deck, names)
    res = {}
    for e, old_, new_, tag in ((ac.E1, "a", "b", "A->B"), (ac.E2, "b", "a", "B->A")):
        a0 = e - 2e-9
        ci_old, nci_old, ci_new, nci_new = v[f"ci{old_}"], v[f"nci{old_}"], v[f"ci{new_}"], v[f"nci{new_}"]
        cd_old, ncd_old, cd_new, ncd_new = v[f"cd{old_}"], v[f"ncd{old_}"], v[f"cd{new_}"], v[f"ncd{new_}"]
        res[tag] = {
            "dead": (ac.tg_on_start(t, ci_new, nci_new, a0) - ac.tg_full_off(t, ci_old, nci_old, a0)) * 1e9,
            "overlap": (cross(t, cd_old, ac.VDD / 2, False, a0) - cross(t, cd_new, ac.VDD / 2, True, a0)) * 1e9,
            "margin1": (ac.tg_off_start(t, ci_old, nci_old, a0) - ac.tg_full_on(t, cd_new, ncd_new, a0)) * 1e9,
            "margin2": (ac.tg_off_start(t, cd_old, ncd_old, a0) - ac.tg_full_on(t, ci_new, nci_new, a0)) * 1e9,
            "delay": (cross(t, cd_new, ac.VDD / 2, True, a0) - cross(t, v["chi"], vdd / 2, tag == "B->A", a0)) * 1e9,
            "crossings": [ncross(t, v[n], ac.VDD / 2, a0, e + 60e-9) for n in ("cia", "ncia", "cib", "ncib", "cda", "ncda", "cdb", "ncdb")]}
    return cell, corner, temp, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", nargs="+", default=["ss:125:3.0", "typical:27:3.3", "ff:-40:3.6"])
    ap.add_argument("--only", choices=["drive", "aclk", "adcclk"])
    a = ap.parse_args()
    nets = json.load(open(os.path.join(HERE, "build", "nets.json")))
    cs = [(c.split(":")[0], float(c.split(":")[1]), float(c.split(":")[2])) for c in a.corners]
    out = {}
    with ThreadPoolExecutor(6) as ex:
        if a.only in (None, "drive"):
            jobs = [ex.submit(drive, nets, c, t, vdd, cell, n) for c, t, vdd in cs for cell in ("buf_1", "buf_16")
                    for n in ("CMP_STROBE", "DAC_CLK", "CHOP", "CHOP_BLANK", "CHOP1")]
            print("| net | cell | corner | rise 30-70 / 10-90 / delay (ns) | fall 30-70 / 10-90 / delay (ns) |")
            print("|---|---|---|---|---|")
            for j in jobs:
                n, cell, c, t, r = j.result()
                out.setdefault("drive", []).append({"net": n, "cell": cell, "corner": f"{c} {t:g} C", **r})
                print(f"| {n} | {cell} | {c} {t:g} C | " + " | ".join(
                    f"{r[e]['t3070']:.2f} / {r[e]['t1090']:.2f} / {r[e]['delay']:.2f}" for e in ("rise", "fall")) + " |",
                    flush=True)
        if a.only in (None, "aclk"):
            jobs = [ex.submit(aclk, nets, c, t, vdd, cell) for c, t, vdd in cs for cell in ("buf_1", "buf_16")]
            print("\n| cell | corner | edge | CHOP 10-90 at the driver (ns) | dead time (ns) | CHOP buffer in -> CIA/CIB (ns) "
                  "| AVDD_CLK - AVSS_CLK min (V) | VDD/2 crossings (CIA NCIA CIB NCIB CHOPB, CDA+CDB) |")
            print("|---|---|---|---|---|---|---|---|")
            for j in jobs:
                cell, c, t, r = j.result()
                out.setdefault("aclk", []).append({"cell": cell, "corner": f"{c} {t:g} C", **r})
                for k, e in enumerate(r["edge"], 1):
                    g = r["glitch"][f"edge{k}"]
                    print(f"| {cell} | {c} {t:g} C | {e['edge']} | {e['chop_t1090_ns']:.1f} | {e['dead_ns']:.2f} | "
                          f"{e['delay_ns']:.2f} | {e['supply_min_V']:.3f} | {g['cia']} {g['ncia']} {g['cib']} {g['ncib']} "
                          f"{g['chopb']}, {g['cda+cdb']} |", flush=True)
        if a.only == "adcclk" or a.only is None:
            jobs = [ex.submit(adcclk, nets, c, t, vdd, cell) for c, t, vdd in cs for cell in ("buf_1", "buf_16")]
            print("\n| cell | corner | edge | dead (ns) | overlap (ns) | margin 1 / 2 (ns) | CHOP1 buffer in -> commutator (ns) "
                  "| VDD/2 crossings (CIA NCIA CIB NCIB CDA NCDA CDB NCDB) |")
            print("|---|---|---|---|---|---|---|---|")
            for j in jobs:
                cell, c, t, r = j.result()
                out.setdefault("adcclk", []).append({"cell": cell, "corner": f"{c} {t:g} C", **r})
                for tag, e in r.items():
                    print(f"| {cell} | {c} {t:g} C | {tag} | {e['dead']:.2f} | {e['overlap']:.2f} | {e['margin1']:.2f} / "
                          f"{e['margin2']:.2f} | {e['delay']:.2f} | {' '.join(map(str, e['crossings']))} |", flush=True)
    with open(os.path.join(HERE, "build", "drive_check.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
