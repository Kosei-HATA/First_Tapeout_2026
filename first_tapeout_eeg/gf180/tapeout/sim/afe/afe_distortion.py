#!/usr/bin/env python3
"""Static distortion of the AFE (CCIA) in one frozen chopper phase.

The amplifier sees the chopped signal, but its output settles within a few
tens of ns after each chopper edge (closed-loop bandwidth about 5.6 MHz, slew
rate about 500 V/us against a 0.25 V step), so the in-band distortion is the
static nonlinearity of each phase. A frozen-phase transient with a 1 kHz sine
(well below fch, well above the DC path's corner) measures it. Demodulation
averages phase A and phase B, which are mirror images, so the odd orders are
what matters; the even orders are reported for the symmetry check.

The run is repeated at 1/10 amplitude: a real cubic term drops by 20 dB,
numerical noise does not.

Usage: python3 afe_distortion.py [--amp 0.943396e-3] [design knobs of afe_noise.py]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_noise

HERE = os.path.dirname(os.path.abspath(__file__))
F0 = 1e3
NPER, NSKIP = 8, 2
TSIG = 20e-6  # signal starts after the reset release


def deck(a, amp):
    t = afe_noise.deck(a.core, a.tg, "A", a.rs, a.vpc, a.cpf, a.vnc)
    t = t.replace("* AFE frozen-phase noise", "* AFE frozen-phase distortion", 1)
    t = t.replace("VSRC SRC 0 DC 0 AC 1", f"VSRC SRC 0 DC 0 SIN(0 {amp:.9e} {F0:g} {TSIG:g})")
    # the 1e16 H DC path is numerically fragile in .tran: reset INP/INN with NMOS
    # switches until 10 us, then hold (as afe_chop_gain.py)
    t = t.replace("LDCP INP ONI 1e16\nLDCN INN OPI 1e16", """XRSTP INP RST ONI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
XRSTN INN RST OPI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
VRST RST_D 0 PWL(0 3.3 10u 3.3 11u 0)
RGRST RST_D RST 10""")
    assert "XRSTP" in t
    t = t.replace("RLOADP OUTP CM 9375", f"RLOADP OUTP CM {a.rload:g}").replace(
        "RLOADN OUTN CM 9375", f"RLOADN OUTN CM {a.rload:g}")
    if a.freeze_cmfb:  # diagnostic: hold VBP at its operating point (CMFB inactive at 1 kHz)
        t = t.replace("XDUT ", "CVBPHOLD VBP 0 1\nXDUT ", 1)
    tstop = TSIG + (NSKIP + NPER) / F0
    return re.sub(r"\.control.*", f""".control
set noaskquit
tran 0.2u {tstop:.6e} 0 0.2u
let vo = v(outp) - v(outn)
let vc = v(opi) - v(oni)
let vi = v(inp) - v(inn)
let vw = v(wp) - v(wn)
let vdn = v(xdut.xcore.dnp) - v(xdut.xcore.dnn)
let vdp = v(xdut.xcore.dpp) - v(xdut.xcore.dpn)
linearize vo vc vi vw vdn vdp
wrdata tr.csv vo vc vi vw vdn vdp
quit
.endc
.end
""", t, flags=re.S)


def run(a, amp):
    name = (f"dist_core{a.core:g}_tg{a.tg}_ln{a.ln:g}_lp{a.lp:g}_mp{a.mp:g}_it{a.itail:g}_sc{a.scasc:g}"
            f"_vpc{a.vpc:g}_vnc{a.vnc:g}_lnc{a.lnc:g}_lpc{a.lpc:g}_cpf{a.cpf:g}_tgo{a.tgo}_rl{a.rload:g}"
            f"_rs{a.rs:g}_amp{amp:g}_b{afe_noise.BOOST}"
            f"{'_cmfbhold' if a.freeze_cmfb else ''}{'_idealsw-' + a.ideal_sw if a.ideal_sw else ''}")
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    cand = afe_noise.candidate(a.core, a.tg, a.ln, a.lp, a.mp, a.itail, a.scasc, a.tgo, a.lnc, a.lpc,
                               None, a.dnref, a.dpref)
    if a.ideal_sw in ("in", "both"):  # diagnostic: phase-A input TGs -> 3 ohm, phase B removed
        cand = re.sub(r"^XIP_A EP WP .*$", "RIP_A EP WP 3", cand, flags=re.M)
        cand = re.sub(r"^XIN_A EN WN .*$", "RIN_A EN WN 3", cand, flags=re.M)
        cand = re.sub(r"^XI[PN]_B .*$\n", "", cand, flags=re.M)
    if a.ideal_sw in ("out", "both"):  # diagnostic: phase-A output TGs -> 10 ohm, phase B removed
        cand = re.sub(r"^XOP_A OPI OUTP .*$", "ROP_A OPI OUTP 10", cand, flags=re.M)
        cand = re.sub(r"^XON_A ONI OUTN .*$", "RON_A ONI OUTN 10", cand, flags=re.M)
        cand = re.sub(r"^XO[PN]_B .*$\n", "", cand, flags=re.M)
    open(os.path.join(d, "cand.spice"), "w").write(cand)
    open(os.path.join(d, "tb.spice"), "w").write(deck(a, amp))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    data = np.loadtxt(os.path.join(d, "tr.csv"))
    os.remove(os.path.join(d, "tr.csv"))
    t = data[:, 0]
    m = t >= TSIG + NSKIP / F0 - 1e-12
    n = int(round(NPER / F0 / (t[1] - t[0])))
    out = []
    for col in (1, 3, 5, 7, 9, 11):  # AFE output, core output, amp input, Cin plate, pair drains
        spec = np.abs(np.fft.rfft(data[m, col][:n])) / (n / 2)
        out.append([spec[k * NPER] for k in range(1, 6)])
    return amp, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amp", type=float, default=0.943396e-3, help="differential peak at the electrode (V)")
    ap.add_argument("--core", type=float, default=1.0)
    ap.add_argument("--tg", type=int, default=64)
    ap.add_argument("--ln", type=float, default=0.28)
    ap.add_argument("--lp", type=float, default=0.28)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--itail", type=float, default=1.0)
    ap.add_argument("--scasc", type=float, default=None)
    ap.add_argument("--vpc", type=float, default=1.1)
    ap.add_argument("--cpf", type=float, default=2.10)
    ap.add_argument("--rs", type=float, default=afe_noise.RS)
    ap.add_argument("--freeze-cmfb", action="store_true", help="diagnostic: hold VBP with 1 F")
    ap.add_argument("--tgo", type=int, default=8, help="output chopper TG multiplicity")
    ap.add_argument("--rload", type=float, default=9375.0, help="ADC input resistor per side (ohm)")
    ap.add_argument("--vnc", type=float, default=2.2, help="NMOS cascode gate bias (V)")
    ap.add_argument("--lnc", type=float, default=1.0, help="NMOS cascode L (um)")
    ap.add_argument("--lpc", type=float, default=1.0, help="PMOS cascode L (um)")
    ap.add_argument("--fs-only", action="store_true", help="skip the 1/10 amplitude run")
    ap.add_argument("--boost", default="0", help="cascode boosting: 0, tr, or a behavioural gain")
    ap.add_argument("--dnref", type=float, default=1.0535, help="boost reference for the NMOS pair drains")
    ap.add_argument("--dpref", type=float, default=2.2582, help="boost reference for the PMOS pair drains")
    ap.add_argument("--ideal-sw", choices=["in", "out", "both"], default=None,
                    help="diagnostic: replace the phase-A TGs by resistors")
    a = ap.parse_args()
    a.scasc = a.itail if a.scasc is None else a.scasc
    afe_noise.set_boost(a.boost)
    amps = (a.amp,) if a.fs_only else (a.amp, a.amp / 10)
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(lambda amp: run(a, amp), amps))
    for amp, hs in res:
        for label, h in zip(("OUTP-OUTN", "OPI-ONI  ", "INP-INN  ", "WP-WN    ", "DNP-DNN  ", "DPP-DPN  "), hs):
            rel = [20 * np.log10(x / h[0]) for x in h[1:]]
            print(f"electrode {amp*1e3:.4f} mVpk, {label}: fundamental {h[0]*1e3:.2f} mVpk (gain {h[0]/amp:.2f}); "
                  f"HD2 {rel[0]:.1f}, HD3 {rel[1]:.1f}, HD4 {rel[2]:.1f}, HD5 {rel[3]:.1f} dBc")


if __name__ == "__main__":
    main()
