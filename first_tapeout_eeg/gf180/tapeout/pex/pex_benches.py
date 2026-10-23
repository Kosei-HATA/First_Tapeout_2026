#!/usr/bin/env python3
"""Bench checks of DAC1 and the OTA1 chopper with and without parasitics (tracker D6):
the existing benches on the schematic (sch), the extracted devices (dev) and the
devices with the extracted capacitances (pex) of the layout blocks:

  dac1  gf180/tapeout/sim/dac1/dac1_check.py, tests 'even' (charge error per toggle that
        does not depend on its direction, one cell and all 31) and 'ref' (reference
        charge per frame, extra charge per toggle), on the block adc_rdac (RIN and DAC1,
        pex.py adc_rdac): eeg_dac1 is the block with RIN shorted end to end (INP = I1P,
        INN = I1N), so that RIN carries no current and only its parasitics stay;
  ota1  gf180/tapeout/sim/adc_loop/ota1_edge.py with the chopper driver eeg_adc_clk
        (--drv): the charge one OTA1 chopper edge leaves in the first integrator,
        q = beta I + gamma v_o1, on the block gf180_inside_cascode_ota (pex.py
        gf180_inside_cascode_ota) in place of the subcircuit of eeg_adc_otas.spice.
        (The bench keeps its own values: RIN 9375, C1 680.5 pF, CL 4 pF; the comparison
        is between the three versions.)

Usage: python3 gf180/tapeout/pex/pex_benches.py dac1|ota1 [--variants sch dev pex] [--even-only]
       (dac1 runs the variants one after another: start one process per variant to have them in parallel;
       variant pexnox = pex without the couplings of the steering nodes XP / XN to the switching nets)
"""
import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
ADC = os.path.join(REPO, "gf180", "tapeout", "adc")
LVS = os.path.join(REPO, "gf180", "tapeout", "layout", "lvs")
RUNS = os.path.join(HERE, "runs", "benches")


def dac1_wrapper(variant):
    """A file that defines eeg_dac1 (the ports of eeg_dac1.spice) on the block adc_rdac."""
    os.makedirs(RUNS, exist_ok=True)
    path = os.path.join(RUNS, f"eeg_dac1_{variant}.spice")
    sel = " ".join(f"SEL{i}" for i in range(31))
    if variant == "sch":
        # the schematic DAC1 under another name, called by the block's LVS wrapper
        src = open(os.path.join(ADC, "eeg_dac1.spice")).read()
        src = src.replace(".subckt eeg_dac1 ", ".subckt eeg_dac1_sch ").replace(".ends eeg_dac1\n", ".ends eeg_dac1_sch\n")
        blk = open(os.path.join(LVS, "adc_rdac.spice")).read().replace(" eeg_dac1\n", " eeg_dac1_sch\n")
        inc = src + "\n" + blk
    elif variant == "pexnox":
        # pex without the couplings between the steering nodes XP / XN and the switching
        # nets (SEL, the cells' latch and drive nodes, the break lines): the test of the
        # mechanism of the even error
        sw = re.compile(r"^(SEL1_\d+|DAC_CLK|DAC1\.BRK\w*|DAC1\.C\d+\.(D|DB|Q|QB|N1)|DAC1\.\w+\.M\d)$")
        xn = re.compile(r"^DAC1\.C\d+\.X[PN]$")
        lines = []
        for ln in open(os.path.join(HERE, "runs", "adc_rdac_c", "adc_rdac_pex.spice")):
            t = ln.split()
            if ln.startswith("CP") and ((xn.match(t[1]) and sw.match(t[2])) or (xn.match(t[2]) and sw.match(t[1]))):
                continue
            lines.append(ln)
        inc = "".join(lines)
    else:
        inc = open(os.path.join(HERE, "runs", "adc_rdac_c", f"adc_rdac_{variant}.spice")).read()
    txt = (inc + f"\n.subckt eeg_dac1 OUTP OUTN VRP VRN {sel} DAC_CLK VDD VSS\n"
           f"XBLK OUTP OUTN OUTP OUTN VRP VRN {sel} DAC_CLK VDD VSS adc_rdac\n.ends eeg_dac1\n")
    open(path, "w").write(txt)
    return path


def otas_file(variant):
    """eeg_adc_otas.spice with gf180_inside_cascode_ota from the block extraction (sch: as
    it is), headed by the MIM model sections that the bench of ota1_edge.py does not load
    (its deck predates the MIM compensation capacitors of 10/23)."""
    src = open(os.path.join(ADC, "eeg_adc_otas.spice")).read()
    if variant != "sch":
        m = re.search(r"^\.subckt gf180_inside_cascode_ota .*?^\.ends gf180_inside_cascode_ota\s*$", src, re.M | re.S)
        blk = open(os.path.join(HERE, "runs", "gf180_inside_cascode_ota_c",
                                f"gf180_inside_cascode_ota_{variant}.spice")).read()
        src = src[:m.start()] + blk + src[m.end():]
    pdk = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                             "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
    head = f".lib {pdk}/sm141064.ngspice mimcap_typical\n.lib {pdk}/sm141064.ngspice cap_mim\n"
    path = os.path.join(RUNS, f"otas_{variant}.spice")
    os.makedirs(RUNS, exist_ok=True)
    open(path, "w").write(head + src)
    return path


def dac1(variants, even_only=False):
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "dac1"))
    import dac1_check as dc
    o = argparse.Namespace(corner="typical", temp=27.0, voff=0.0, mc=0, tol="A")
    print("| DUT | even, one cell (fC/toggle) | even, all 31 (fC/toggle) | VRP k=0 (uA) | VRP k=15 (uA) "
          "| VRP k=31 (uA) | extra VRP charge per toggle (fC) |")
    print("|---|---|---|---|---|---|---|")

    # one variant at a time: dac1_check keeps the netlist and the run folder in module
    # globals (run the variants as separate processes to have them in parallel)
    for v in variants:
        dc.DAC1 = dac1_wrapper(v)
        dc.HERE = os.path.join(RUNS, f"dac1_{v}")
        e = dc.even(o)
        if even_only:
            print(f"| {v} | {e['one'] * 1e15:+.5f} | {e['all'] * 1e15:+.5f} | | | | |", flush=True)
            continue
        r = dc.ref(o)
        print(f"| {v} | {e['one'] * 1e15:+.5f} | {e['all'] * 1e15:+.5f} | {r['VRP current, steady k = 0 (uA)']:.4f} | "
              f"{r['VRP current, steady k = 15 (uA)']:.4f} | {r['VRP current, steady k = 31 (uA)']:.4f} | "
              f"{r['extra VRP charge per toggle (fC)']:+.4f} |", flush=True)


def ota1(variants):
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "adc_loop"))
    import ota1_edge as oe
    for v in variants:
        o = argparse.Namespace(dead=15e-9, ovl=25e-9, tr=2e-9, cl=4e-12, corner="typical", temp=27,
                               otas=otas_file(v), drv=True)
        oe.HERE = os.path.join(RUNS, f"ota1_{v}")
        cases = [(i, 0.0) for i in (-4e-6, -2e-6, 2e-6, 4e-6)] + [(0.0, x) for x in (-0.2, 0.2)]
        jobs = [(f"{v}_i{i * 1e6:g}_v{x:g}_{c}", i, x, c, o) for i, x in cases for c in (False, True)]
        with ThreadPoolExecutor(6) as ex:
            res = list(ex.map(oe.run, jobs))
        rows = []
        for k, (i, x) in enumerate(cases):
            t0, o0, v0 = res[2 * k]
            t1, o1, v1 = res[2 * k + 1]
            diff = lambda tt: np.interp(tt, t1, o1) - np.interp(tt, t0, o0)
            for e in range(oe.NEDGE):
                te = oe.T0 + e * oe.DT
                step = diff(te + 1.0e-6) - diff(te - 0.2e-6)
                ob = np.interp(te - 0.2e-6, t1, o1)
                rows.append((e % 2, i, ob, step * oe.C1 / 2))
        r = np.array(rows)
        for e in (0, 1):
            m = r[:, 0] == e
            A = np.vstack([r[m, 1], r[m, 2], np.ones(m.sum())]).T
            c, *_ = np.linalg.lstsq(A, r[m, 3], rcond=None)
            res_ = r[m, 3] - A @ c
            print(f"{v} {'A->B' if e == 0 else 'B->A'}: q = {c[0] * 1e9:.3f} ns * I + {c[1] * 1e12:.4f} pC/V * v_o1 "
                  f"+ {c[2] * 1e15:.3f} fC (residual {res_.std() * 1e15:.3f} fC)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["dac1", "ota1"])
    ap.add_argument("--variants", nargs="+", default=["sch", "dev", "pex"])
    ap.add_argument("--even-only", action="store_true", help="dac1: the even test only")
    a = ap.parse_args()
    if a.what == "dac1":
        dac1(a.variants, a.even_only)
    else:
        ota1(a.variants)


if __name__ == "__main__":
    main()
