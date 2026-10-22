#!/usr/bin/env python3
"""Charge error of one OTA1 chopper edge in the first integrator.

In the loop the OTA1 output current carries the integrator current I = v_in/(2 RIN) -
v_dac/(2 RD1) per side (the quantization error of the last DAC1 level) and the R21 load
current v_o1/(2 R21); the virtual ground sits at v_vd = 2 I / gm + v_o1 / A. A chopper
edge moves charge in proportion to these: the OTA1 gates (about 70 pF) are swapped
between the two virtual-ground nodes, and the OTA output current is interrupted while
the drain commutators of both phases conduct. That charge is an input error. In the
loop it is taken once per chopper edge, far below fs, so the shaped quantization noise
near fs/2 folds into the band (chop1_fold.py applies the result to loop waveforms).

Bench: the first stage of make_deck.py (OTA1 with its bias sources through 1k/10p,
RIN 9375, RD1 300k/31, C1 680.5 pF, CL 4 pF, R21 100k into an ideal virtual ground at
CM), the DAC at mid-scale. The operating point is taken with the input at CM; the input
steps to the value for I at 0.5 us. The O1 difference can be preset instead (with
I = 0), so that the edges see only the R21 load current. One run holds chopper phase A,
the other chops with edges every 2 us (alternating A->B and B->A). The difference of
the differential O1 voltages steps by 2 q / C1 at each edge (q per side). Per edge type
a least-squares fit q = beta I + gamma v_o1 + q0 (v_o1 the differential O1 voltage
before the edge) gives the coefficients.

Usage: python3 ota1_edge.py [--i -4e-6 -2e-6 2e-6 4e-6] [--vo -0.2 0.2] [--dead 15e-9]
       [--ovl 25e-9] [--tr 2e-9] [--cl 4e-12] [--corner typical] [--temp 27]
       [--lin 2] [--mscale 1] [--drv]

--drv drives the chopper through the transistor driver eeg_adc_clk (gf180/tapeout/adc/)
instead of ideal sources with the given dead time, overlap and edge time.
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import ota1_noise

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CLK = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc_clk.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
RIN = 9375.0
RD1 = 300e3 / 31
C1 = 680.51376829979684e-12
T0 = 4e-6  # first edge
DT = 2e-6  # edge spacing
NEDGE = 6
TS = 0.5e-6  # input step (the operating point is taken with the input at CM)


def pulse(v1, v2, t50, w50, per, tr):
    return f"PULSE({v1} {v2} {t50 - tr / 2:.10e} {tr:g} {tr:g} {w50 - tr:.10e} {per:.10e})"


def deck(i_err, vo0, chop, dead, ovl, tr, cl, corner, temp, otas, drv=False):
    vin = 2 * RIN * i_err  # differential input for I per side with the DAC at mid-scale
    per = 2 * DT
    if drv:  # the transistor driver eeg_adc_clk from a CHOP1 square wave (falls at T0)
        ch = f"PULSE(3.3 0 {T0 - 0.25e-9:.10e} 0.5n 0.5n {DT - 0.5e-9:.10e} {per:.10e})" if chop else "3.3"
        clk = (f".include {CLK}\nVCH CHOP1 0 {ch}\nVCLK VCLK 0 3.3\n"
               "XCLK CHOP1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VCLK 0 eeg_adc_clk")
    elif chop:
        clk = "\n".join([
            f"VIA CIA 0 {pulse(3.3, 0, T0 - dead / 2, DT + dead, per, tr)}",
            f"VIB CIB 0 {pulse(0, 3.3, T0 + dead / 2, DT - dead, per, tr)}",
            f"VDA CDA 0 {pulse(3.3, 0, T0 + ovl / 2, DT - ovl, per, tr)}",
            f"VDB CDB 0 {pulse(0, 3.3, T0 - ovl / 2, DT + ovl, per, tr)}"])
    else:
        clk = "VIA CIA 0 3.3\nVIB CIB 0 0\nVDA CDA 0 3.3\nVDB CDB 0 0"
    return f"""* OTA1 chopper edge charge, I = {i_err:g} A, chop {chop}
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.include {otas}
.temp {temp}
.options sparse method=trap maxord=2 reltol=1e-5 vntol=1e-7 abstol=1e-12 chgtol=1e-16 bypass=0
VDD VDD 0 3.3
VCMS CMS 0 1.65
RVCM CMS CM 10
CVCM CM 0 100p
VBN1S VBN1S 0 .85
RVBN1 VBN1S VBN1 1k
CVBN1 VBN1 0 10p
VNC1S VNC1S 0 2
RVNC1 VNC1S VNC1 1k
CVNC1 VNC1 0 10p
VPC1S VPC1S 0 1.7
RVPC1 VPC1S VPC1 1k
CVPC1 VPC1 0 10p
VBCM1S VBCM1S 0 .82
RVBCM1 VBCM1S VBCM1 1k
CVBCM1 VBCM1 0 10p
VINP VINP 0 PWL(0 1.65 {TS:g} 1.65 {TS + 10e-9:g} {1.65 + vin / 2:.9f})
VINN VINN 0 PWL(0 1.65 {TS:g} 1.65 {TS + 10e-9:g} {1.65 - vin / 2:.9f})
VG2 G2 0 1.65
{clk}
{"" if drv else "ENCIA NCIA 0 VDD CIA 1\nENCIB NCIB 0 VDD CIB 1\nENCDA NCDA 0 VDD CDA 1\nENCDB NCDB 0 VDD CDB 1"}
XOTA1 I1P I1N O1P O1N CM VBN1 VNC1 VPC1 VBCM1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD 0 gf180_inside_cascode_ota
RINP VINP I1P {RIN}
RINN VINN I1N {RIN}
RD1P CM I1P {RD1:.6f}
RD1N CM I1N {RD1:.6f}
C1P O1N I1P {C1:.6e}
C1N O1P I1N {C1:.6e}
RF1P O1N I1P 1T
RF1N O1P I1N 1T
CL1P O1P 0 {cl:g}
CL1N O1N 0 {cl:g}
R21P O1P G2 100k
R21N O1N G2 100k
.ic v(o1p)={1.65 + vo0 / 2:.6f} v(o1n)={1.65 - vo0 / 2:.6f}
.control
set noaskquit
tran 0.2n {T0 + NEDGE * DT - 0.2e-6:.6e} 0 0.5n
wrdata out.csv v(o1p) v(o1n) v(i1p) v(i1n)
quit
.endc
.end
"""


def run(args):
    name, i_err, vo0, chop, o = args
    d = os.path.join(HERE, "runs", "ota1_edge", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(i_err, vo0, chop, o.dead, o.ovl, o.tr, o.cl, o.corner,
                                                      o.temp, o.otas, o.drv))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    return x[:, 0], x[:, 1] - x[:, 3], x[:, 5] - x[:, 7]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i", type=float, nargs="+", default=[-4e-6, -2e-6, 2e-6, 4e-6])
    ap.add_argument("--vo", type=float, nargs="+", default=[-0.2, 0.2],
                    help="O1 differential presets (V) run with I = 0")
    ap.add_argument("--dead", type=float, default=15e-9)
    ap.add_argument("--ovl", type=float, default=25e-9)
    ap.add_argument("--tr", type=float, default=2e-9)
    ap.add_argument("--cl", type=float, default=4e-12)
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=int, default=27)
    ap.add_argument("--lin", type=float, default=2.0, help="OTA1 input-pair L (um), import 2")
    ap.add_argument("--mscale", type=float, default=1.0, help="input-pair multiplicity scale (import 2048)")
    ap.add_argument("--drv", action="store_true", help="drive the chopper with eeg_adc_clk (ignores dead/ovl/tr)")
    o = ap.parse_args()
    tm = "drv" if o.drv else f"d{o.dead * 1e9:g}_o{o.ovl * 1e9:g}_tr{o.tr * 1e9:g}"
    tag = f"{tm}_cl{o.cl * 1e12:g}_l{o.lin:g}_m{o.mscale:g}_{o.corner}{o.temp}"
    os.makedirs(os.path.join(HERE, "runs", "ota1_edge"), exist_ok=True)
    o.otas = os.path.join(HERE, "runs", "ota1_edge", f"otas_l{o.lin:g}_m{o.mscale:g}.spice")
    open(o.otas, "w").write(ota1_noise.otas_variant(o.lin, o.mscale))
    cases = [(i, 0.0) for i in o.i] + [(0.0, v) for v in o.vo]
    jobs = [(f"{tag}_i{i * 1e6:g}_v{v:g}_{c}", i, v, c, o) for i, v in cases for c in (False, True)]
    with ThreadPoolExecutor(min(len(jobs), 6)) as ex:
        res = list(ex.map(run, jobs))
    clk = "driver eeg_adc_clk" if o.drv else f"dead {o.dead * 1e9:g} ns, overlap {o.ovl * 1e9:g} ns, edges {o.tr * 1e9:g} ns"
    print(f"{clk}, CL {o.cl * 1e12:g} pF, "
          f"pair L {o.lin:g} um m {2048 * o.mscale:g}, {o.corner} {o.temp} C")
    rows = []  # (edge type, I, v_vd, v_o1, q)
    for k, (i, v) in enumerate(cases):
        t0, o0, v0 = res[2 * k]
        t1, o1, v1 = res[2 * k + 1]
        diff = lambda tt: np.interp(tt, t1, o1) - np.interp(tt, t0, o0)
        for e in range(NEDGE):
            te = T0 + e * DT
            step = diff(te + 1.0e-6) - diff(te - 0.2e-6)
            # the chopped run's own state just before the edge (phase B before B->A edges)
            vb = np.interp(te - 0.2e-6, t1, v1) * (1 if e % 2 == 0 else -1)
            ob = np.interp(te - 0.2e-6, t1, o1)
            rows.append((e % 2, i, vb, ob, step * C1 / 2))
    r = np.array(rows)
    print("| edge | I per side (uA) | v_vd (uV) | v_o1 (mV) | q per side (fC) |")
    print("|---|---|---|---|---|")
    for e, i, vb, ob, q in r:
        print(f"| {'A->B' if e == 0 else 'B->A'} | {i * 1e6:g} | {vb * 1e6:.1f} | {ob * 1e3:.1f} | {q * 1e15:.2f} |")
    for e in (0, 1):
        m = r[:, 0] == e
        A = np.vstack([r[m, 1], r[m, 3], np.ones(m.sum())]).T
        c, *_ = np.linalg.lstsq(A, r[m, 4], rcond=None)
        res_ = r[m, 4] - A @ c
        print(f"{'A->B' if e == 0 else 'B->A'}: q = {c[0] * 1e9:.2f} ns * I + {c[1] * 1e12:.4f} pC/V * v_o1 "
              f"+ {c[2] * 1e15:.3f} fC (residual {res_.std() * 1e15:.3f} fC)")


if __name__ == "__main__":
    main()
