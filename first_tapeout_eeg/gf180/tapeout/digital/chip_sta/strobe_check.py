#!/usr/bin/env python3
"""TH timing of the quantizer with the strobe as on the chip (tracker C3, chip_sta).

The timing bench of gf180/tapeout/sim/quantizer/quantizer_check.py (eeg_quantizer, 8
strobes with the input stepping between codes), with two changes:
  * CMP_STROBE comes from the output buffer of eeg_digital_top (buf_1 as in run f2, or
    buf_16 as in the candidate d1) through the extracted net (build/nets.json: R and
    C_iso + kc C_cpl as a 20-section ladder, the gate load of the strobe buffer at
    the end); the buffer's input is an ideal 0.3 ns edge, the time reference;
  * each TH carries its extracted load (C_iso + kc C_cpl) instead of 0.3 pF.
Printed per case: the last TH to cross 50 % after the strobe, from the buffer input
(what the chip-level STA adds to the arrival of CMP_STROBE at the macro pin) and from
the strobe at the quantizer input, and the strobe's 10-90 % rise at the quantizer.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/chip_sta/strobe_check.py
       [--cases ss:-20:3.0:buf_1 ss:125:3.0:buf_1 ...] [--kc 2]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "quantizer"))
import quantizer_check as qc  # noqa: E402
from qcmp_check import IQ27  # noqa: E402
import drive_check as dc  # noqa: E402

IQT = {-20: 25.66 / 31.40, 27: 1.0, 85: 38.88 / 31.40, 125: 1.0 + (38.88 / 31.40 - 1.0) * (125 - 27) / (85 - 27)}


def case(nets, corner, temp, vdd, cell, kc):
    n = 8
    levels = [1.6e-3, -1.6e-3, 20e-3, -45e-3, 0.05e-3, 47e-3, -0.05e-3, 3.1e-3]
    pwl = []
    for k, v in enumerate(levels):
        ts = qc.T0 + k * qc.T
        pwl += [(max(ts - qc.T / 2, 0.0), v), (ts + qc.T / 2 - 1e-9, v)]
    src = " ".join(f"{x:.10e} {y:.6e}" for x, y in pwl)
    tstop = qc.T0 + n * qc.T
    d = nets["CMP_STROBE"]
    r, cw, cg = d["r_typ"][0][1], d["c_iso_fF"] + kc * d["c_cpl_fF"], 0.0   # the strobe buffer's gate is in the netlist
    strobe = dc.ladder("stb", "STBZ", "CMP_STROBE", r, cw, cg)
    loads = [f"CTH{k} TH{k} 0 {(nets[f'TH{k}']['c_iso_fF'] + kc * nets[f'TH{k}']['c_cpl_fF']) * 1e-15:.4e}" for k in range(31)]
    iq = IQ27[corner] * IQT[temp]
    th = " ".join(f"TH{k}" for k in range(31))
    text = f"""* eeg_quantizer timing with the chip's strobe ({cell})
.include {qc.PDK}/design.ngspice
.lib {qc.PDK}/sm141064.ngspice {corner}
.lib {qc.PDK}/sm141064.ngspice {qc.RES[corner]}
.lib {qc.PDK}/sm141064.ngspice mimcap_{qc.CAPC.get(corner, 'typical')}
.lib {qc.PDK}/sm141064.ngspice cap_mim
.include {qc.QNET}
.include {dc.CELLS}
.temp {temp}
.options sparse reltol=1e-4 abstol=1e-12 vntol=1e-7
VAVDD AVDD 0 {vdd}
VDVDD DVDD 0 {vdd}
VRP VREFP 0 1.9
VRN VREFN 0 1.4
IQ AVDD IQ {iq}
VSTI STBI 0 PULSE(0 {vdd} {qc.T0:.10e} 0.3n 0.3n {qc.TM - 0.3e-9:.10e} {qc.T:.10e})
XB STBI STBZ DVDD DVDD 0 0 gf180mcu_fd_sc_mcu9t5v0__{cell}
{chr(10).join(strobe)}
VD VD 0 PWL({src})
EINP INPS 0 VALUE={{1.65+V(VD)/2}}
EINN INNS 0 VALUE={{1.65-V(VD)/2}}
VMP INPS INP 0
VMN INNS INN 0
XQ INP INN VREFP VREFN CMP_STROBE {th} IQ AVDD 0 DVDD 0 eeg_quantizer
{chr(10).join(loads)}
.control
tran 0.02n {tstop:.10e} 0 0.5n
wrdata out.csv v(stbi) v(cmp_strobe) {" ".join(f"v(th{k})" for k in range(31))}
quit
.endc
.end
"""
    name = f"chipstrobe_{cell}_{corner}_{temp}_{vdd:g}_kc{kc:g}"
    dd, _ = qc.run(name, text)
    x = np.loadtxt(os.path.join(dd, "out.csv"))
    t, si, sq = x[:, 0], x[:, 1], x[:, 3]
    th_v = x[:, 5::2]
    worst_in = worst_q = 0.0
    rise = []
    codes = []
    for k in range(1, n):
        ts = qc.T0 + k * qc.T
        w = (t > ts - 20e-9) & (t < ts + qc.T - 40e-9)
        tw = t[w]
        t_in = dc.cross(tw, si[w], vdd / 2, True, ts - 5e-9)
        t_q = dc.cross(tw, sq[w], vdd / 2, True, ts - 5e-9)
        rise.append(dc.cross(tw, sq[w], 0.9 * vdd, True, ts - 5e-9) - dc.cross(tw, sq[w], 0.1 * vdd, True, ts - 5e-9))
        last = -1.0
        for j in range(31):
            ch = np.flatnonzero(np.diff((th_v[w, j] > vdd / 2).astype(int)) != 0)
            if ch.size:
                last = max(last, tw[ch[-1] + 1])
        codes.append(int(np.sum(th_v[w][-1] > vdd / 2)))
        if last > 0:
            worst_in = max(worst_in, last - t_in)
            worst_q = max(worst_q, last - t_q)
    return cell, corner, temp, vdd, kc, worst_in * 1e9, worst_q * 1e9, max(rise) * 1e9, codes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["ss:-20:3.0:buf_1", "ss:-20:3.0:buf_16", "ss:85:3.0:buf_1",
                                                    "ss:125:3.0:buf_1", "typical:27:3.3:buf_1", "typical:27:3.3:buf_16"])
    ap.add_argument("--kc", type=float, default=2.0)
    a = ap.parse_args()
    nets = json.load(open(os.path.join(HERE, "build", "nets.json")))
    cs = []
    for c in a.cases:
        corner, temp, vdd, cell = c.split(":")
        cs.append((corner, int(temp), float(vdd), cell))
    print(f"| buffer | corner | AVDD = DVDD | last TH from the buffer input / from the strobe at the quantizer (ns) "
          f"| strobe 10-90 % at the quantizer (ns) | codes |")
    print("|---|---|---|---|---|---|")
    with ThreadPoolExecutor(len(cs)) as ex:
        for r in ex.map(lambda c: case(nets, *c, a.kc), cs):
            cell, corner, temp, vdd, kc, wi, wq, rise, codes = r
            print(f"| {cell} | {corner} {temp} C | {vdd:g} V | {wi:.2f} / {wq:.2f} | {rise:.2f} | {codes} |", flush=True)


if __name__ == "__main__":
    main()
