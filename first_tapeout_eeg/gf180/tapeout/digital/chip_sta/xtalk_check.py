#!/usr/bin/env python3
"""Crosstalk between the digital control lines on the chip (tracker C3, chip_sta).

The routed bus from the digital block to the analog blocks puts static or quiet lines
next to switching ones (build/xtalk.json, xtalk.py). Two coupled-bus benches, each
line an RC ladder of 20 sections (R and its capacitance to everything outside the
bench from chip_nets.py / xtalk.py) with the extracted coupling to its neighbours
spread along the ladders, every line driven by its output buffer of eeg_digital_top
as in run f2 (all buf_1) or in the candidate d1 (buf_16 / clkbuf_16 on the long
nets, buf_1 on the static trims):

  afe  CPF3 | CHOP | CHOP_OUT | CHOP_BLANK | CHOP_EN | AFE_RST, in this order on the
       chip, into the AFE clock driver eeg_afe_clk on its own supply (as drive_check.py
       aclk) and, for CPF3, the input of the Cpf trim (inverter and switch gates).
       CHOP_DLY 0 (CHOP_OUT with CHOP) or 90 MCLK; CHOP_BLANK from 1 MCLK before to
       7 MCLK after each CHOP_OUT edge; CHOP_EN = 1, AFE_RST = 0, CPF3 = 0 or 1.
  adc  ADC_ZERO | CMP_STROBE | TC3 (CMP_STROBE pulses every frame) and TC2 | CHOP1 | TC3:
       ADC_ZERO = 0 drives the gate of the ADC input-short NMOS (W 10 um) directly; 0.3 V
       across it, the net charge it passes is printed.

Printed: the largest disturbance of each quiet line at its receiver (V, from its
level), and for the AFE clock driver the VDD/2 crossings of its outputs per CHOP edge
(one per phase expected, CDA + CDB two per blanking window).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/xtalk_check.py
       [--corners ss:125:3.0 typical:27:3.3 ff:-40:3.6] [--only afe|adc]
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import drive_check as dc

HERE = os.path.dirname(os.path.abspath(__file__))
NETS = json.load(open(os.path.join(HERE, "build", "nets.json")))
XT = json.load(open(os.path.join(HERE, "build", "xtalk.json")))
TM = dc.TM
NSEG = 20
CELL = {"f2": {}, "d1": {n: "buf_16" for n in ("CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST", "CHOP1",
                                                "ADC_ZERO")} | {"CMP_STROBE": "clkbuf_16"}}


def r_of(n):
    d = NETS.get(n)
    if d:
        return max(d["r_typ"][0][1:])
    # nets not in chip_nets.py (the static trims): R from the length, 0.237 ohm/um
    a = XT[n]["c_iso_fF"]
    return a / 0.065 * 0.237


def bus(lines, version):
    """Coupled ladders for the given line order; returns netlist lines and the driver
    input / far-end node names."""
    out = []
    inner = set(lines)
    for i, n in enumerate(lines):
        cg = XT[n]["c_iso_fF"] + sum(v for k, v in XT[n]["cpl_fF"].items() if k not in inner)
        r = r_of(n)
        cell = CELL[version].get(n, "buf_1")
        out.append(f"XB_{n} IN_{n} Z_{n} DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}")
        prev = f"Z_{n}"
        for k in range(NSEG):
            nxt = n if k == NSEG - 1 else f"{n}_{k}"
            out.append(f"R_{n}_{k} {prev} {nxt} {r / NSEG:.4f}")
            out.append(f"C_{n}_{k} {nxt} 0 {cg / NSEG * 1e-15:.4e}")
            prev = nxt
    for a, b in zip(lines, lines[1:]):
        c = XT[a]["cpl_fF"].get(b, 0.0)
        for k in range(NSEG):
            na = a if k == NSEG - 1 else f"{a}_{k}"
            nb = b if k == NSEG - 1 else f"{b}_{k}"
            out.append(f"CC_{a}_{b}_{k} {na} {nb} {c / NSEG * 1e-15:.4e}")
    return out


def pwl(points):
    return "PWL(" + " ".join(f"{t:.6e} {v:g}" for t, v in points) + ")"


def afe(corner, temp, vdd, version, dly, cpf):
    tr = 0.3e-9
    e = [50e-9, 50e-9 + 3.9e-6]            # CHOP edges: rise, fall
    eo = [x + dly * TM for x in e]         # CHOP_OUT edges
    tstop = eo[1] + 400e-9
    ch = [(0, 0), (e[0], 0), (e[0] + tr, vdd), (e[1], vdd), (e[1] + tr, 0)]
    co = [(0, 0), (eo[0], 0), (eo[0] + tr, vdd), (eo[1], vdd), (eo[1] + tr, 0)]
    bl = [(0, 0)]
    for x in eo:
        bl += [(x - TM, 0), (x - TM + tr, vdd), (x + 7 * TM, vdd), (x + 7 * TM + tr, 0)]
    lines = ["CPF3", "CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "AFE_RST"]
    deck = dc.header(corner, temp) + [
        f"VDDD DVDD 0 {vdd}", f"VAV PADD 0 {vdd}", "RCKP PADD AVDD_CLK 100", "RCKN AVSS_CLK 0 100",
        "CCK AVDD_CLK AVSS_CLK 150p", f"VAVDD AVDD 0 {vdd}",
        f"VCH IN_CHOP 0 {pwl(ch)}", f"VCO IN_CHOP_OUT 0 {pwl(co)}", f"VBL IN_CHOP_BLANK 0 {pwl(bl)}",
        f"VEN IN_CHOP_EN 0 {vdd}", "VRS IN_AFE_RST 0 0", f"VCP IN_CPF3 0 {vdd * cpf}"] + bus(lines, version) + [
        f".include {dc.ACLK}",
        "XC CHOP CHOP_OUT CHOP_BLANK CHOP_EN AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RST AVDD_CLK AVSS_CLK eeg_afe_clk",
        "CL1 CIA AVSS_CLK 16.6p", "CL2 NCIA AVSS_CLK 33p", "CL3 CIB AVSS_CLK 16.6p", "CL4 NCIB AVSS_CLK 33p",
        "CL5 CDA AVSS_CLK 0.3p", "CL6 NCDA AVSS_CLK 0.6p", "CL7 CDB AVSS_CLK 0.3p", "CL8 NCDB AVSS_CLK 0.6p",
        "CL9 OFPH AVSS_CLK 0.2p",
        # Cpf trim input: inverter IB3 (as eeg_afe) and the gates of the trim switches
        "XIP CPF3B CPF3 AVDD AVDD pfet_03v3 W=2.5u L=0.28u nf=1 m=1",
        "XIN CPF3B CPF3 0 0 nfet_03v3 W=1u L=0.28u nf=1 m=1", "CCPF CPF3 0 6f",
        ".control", "set noaskquit", f"tran 0.02n {tstop:.6e} 0 0.1n",
        "wrdata out.csv v(chop) v(chop_out) v(chop_blank) v(chop_en) v(afe_rst) v(cpf3) v(cpf3b) "
        "v(cia) v(ncia) v(cib) v(ncib) v(cda) v(cdb) v(xc.chopb)",
        "quit", ".endc", ".end"]
    cols = ["chop", "chop_out", "chop_blank", "chop_en", "afe_rst", "cpf3", "cpf3b", "cia", "ncia", "cib", "ncib",
            "cda", "cdb", "chopb"]
    name = f"xtalk_afe_{version}_{corner}_{temp:g}_d{dly}_c{cpf}"
    t, v = dc.spice(os.path.join(dc.RUNS, name), "\n".join(deck) + "\n", cols)
    res = {"dist": {}, "cross": []}

    def dist(n, level, windows):
        m = np.zeros_like(t, dtype=bool)
        for a, b in windows:
            m |= (t > a) & (t < b)
        return float(np.max(np.abs(v[n][m] - level))) if m.any() else 0.0
    wch = [(x - 2e-9, x + 60e-9) for x in e]
    wco = [(x - 2e-9, x + 60e-9) for x in eo]
    wbl = [(x - TM - 2e-9, x - TM + 60e-9) for x in eo] + [(x + 7 * TM - 2e-9, x + 7 * TM + 60e-9) for x in eo]
    res["dist"]["CHOP_EN"] = dist("chop_en", vdd, wch + wco + wbl)
    res["dist"]["AFE_RST"] = dist("afe_rst", 0.0, wch + wco + wbl)
    res["dist"]["CPF3"] = dist("cpf3", vdd * cpf, wch + wco + wbl)
    res["dist"]["CPF3B"] = dist("cpf3b", vdd * (1 - cpf), wch + wco + wbl)
    # CHOP_BLANK while high: at the CHOP_OUT (and, with a delay, CHOP) edges
    res["dist"]["CHOP_BLANK (high)"] = dist("chop_blank", vdd, wco + ([] if dly == 0 else []))
    if dly:
        # quiet CHOP at the CHOP_OUT / CHOP_BLANK edges, quiet CHOP_OUT at the CHOP edges
        lv_ch = [vdd if e[0] < x < e[1] else 0.0 for x in eo]
        res["dist"]["CHOP (quiet)"] = max(dist("chop", lv, [(x - 2e-9, x + 60e-9)]) for lv, x in zip(lv_ch, eo))
        lv_co = [0.0, vdd]
        res["dist"]["CHOP_OUT (quiet)"] = max(dist("chop_out", lv, [(x - 2e-9, x + 60e-9)]) for lv, x in zip(lv_co, e))
    for k, x in enumerate(eo):
        w0, w1 = min(x, e[k]) - 1.5 * TM, max(x, e[k]) + 9 * TM
        res["cross"].append([dc.ncross(t, v[n], 3.3 / 2, w0, w1) for n in ("cia", "ncia", "cib", "ncib", "chopb")]
                            + [dc.ncross(t, v["cda"], 3.3 / 2, w0, w1) + dc.ncross(t, v["cdb"], 3.3 / 2, w0, w1)])
    return name, res


def adc(corner, temp, vdd, version):
    tr = 0.3e-9
    T = 1 / 1.024e6
    stb = [(0, 0)]
    for k in range(3):
        a = 100e-9 + k * T
        stb += [(a, 0), (a + tr, vdd), (a + TM, vdd), (a + TM + tr, 0)]
    c1 = [(0, 0), (100e-9 + 16 * TM, 0), (100e-9 + 16 * TM + tr, vdd), (100e-9 + T + 16 * TM, vdd),
          (100e-9 + T + 16 * TM + tr, 0)]
    tstop = 100e-9 + 2.5 * T
    deck = dc.header(corner, temp) + [
        f"VDDD DVDD 0 {vdd}", f"VAVDD AVDD 0 {vdd}",
        f"VST IN_CMP_STROBE 0 {pwl(stb)}", "VZ IN_ADC_ZERO 0 0", "VT3 IN_TC3 0 0", "VT2 IN_TC2 0 0",
        f"VC1 IN_CHOP1 0 {pwl(c1)}"] + bus(["ADC_ZERO", "CMP_STROBE", "TC3"], version) + \
        [ln.replace("XB_TC3", "XB2_TC3").replace("IN_TC3", "IN2_TC3").replace("Z_TC3", "Z2_TC3")
         .replace(" TC3_", " T3B_").replace(" TC3 ", " T3B ").replace("_TC3_", "_T3B_")
         for ln in bus(["TC2", "CHOP1", "TC3"], version)] + [
        "VT3B IN2_TC3 0 0",
        # ADC_ZERO receivers: the input-short NMOS (W 10 um) between two quiet nodes, its inverter
        "XZN ZA ADC_ZERO ZB 0 nfet_03v3 W=10u L=0.28u nf=2 m=1", "VZA ZA 0 1.80", "VZB ZB 0 1.50",
        "XZIP ZIB ADC_ZERO AVDD AVDD pfet_03v3 W=2u L=0.28u nf=1 m=1",
        "XZIN ZIB ADC_ZERO 0 0 nfet_03v3 W=1u L=0.28u nf=1 m=1",
        "CSTB CMP_STROBE 0 12f", "CTC3 TC3 0 40f", "CT3B T3B 0 40f", "CTC2 TC2 0 40f", "CCH1 CHOP1 0 7f",
        ".control", "set noaskquit", f"tran 0.02n {tstop:.6e} 0 0.1n",
        "wrdata out.csv v(adc_zero) v(tc3) v(t3b) v(tc2) v(cmp_strobe) v(chop1) i(vza)", "quit", ".endc", ".end"]
    cols = ["adc_zero", "tc3", "t3b", "tc2", "cmp_strobe", "chop1", "iza"]
    name = f"xtalk_adc_{version}_{corner}_{temp:g}"
    t, v = dc.spice(os.path.join(dc.RUNS, name), "\n".join(deck) + "\n", cols)
    m = t > 90e-9
    q = float(np.trapz(v["iza"][m], t[m])) * 1e15         # net charge through the switch (0.3 V across it)
    return name, {"ADC_ZERO": float(np.max(np.abs(v["adc_zero"][m]))), "TC3 (by CMP_STROBE)": float(np.max(np.abs(v["tc3"][m]))),
                  "TC3 (by CHOP1)": float(np.max(np.abs(v["t3b"][m]))), "TC2 (by CHOP1)": float(np.max(np.abs(v["tc2"][m]))),
                  "short-switch net charge, 3 frames, 0.3 V across (fC)": q}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", nargs="+", default=["ss:125:3.0", "typical:27:3.3", "ff:-40:3.6"])
    ap.add_argument("--only", choices=["afe", "adc"])
    a = ap.parse_args()
    cs = [(c.split(":")[0], float(c.split(":")[1]), float(c.split(":")[2])) for c in a.corners]
    jobs = []
    with ThreadPoolExecutor(6) as ex:
        if a.only in (None, "afe"):
            for c in cs:
                for ver in ("f2", "d1"):
                    for dly in (0, 90):
                        for cpf in (0, 1):
                            jobs.append(("afe", (c, ver, dly, cpf), ex.submit(afe, *c, ver, dly, cpf)))
        if a.only in (None, "adc"):
            for c in cs:
                for ver in ("f2", "d1"):
                    jobs.append(("adc", (c, ver), ex.submit(adc, *c, ver)))
        out = {}
        for kind, key, j in jobs:
            name, r = j.result()
            out[name] = r
            if kind == "afe":
                (corner, temp, vdd), ver, dly, cpf = key
                d = r["dist"]
                print(f"afe {ver} {corner} {temp:g} C CHOP_DLY {dly} CPF3={cpf}: " +
                      ", ".join(f"{k} {x:.3f} V" for k, x in d.items()) + f"; crossings per edge {r['cross']}", flush=True)
            else:
                (corner, temp, vdd), ver = key
                print(f"adc {ver} {corner} {temp:g} C: " + ", ".join(f"{k} {x:.3f}" for k, x in r.items()), flush=True)
    with open(os.path.join(HERE, "build", "xtalk_check.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
