#!/usr/bin/env python3
"""Distortion of the AFE in chopped operation (transient), compared with the
frozen-phase prediction of afe_distortion.py.

A sine of FSIG = fch/64 is applied through RS per leg with both choppers
running (deck of afe_chop_gain.py). The demodulated output is integrated over
every chopper period (exact for the piecewise-linear transient output), which
removes the periodic switching spikes and leaves one sample per chopper period;
the harmonics come from an FFT over 4 signal periods (256 chopper periods)
after 0.5 ms of start-up.

Usage: python3 afe_chop_distortion.py [--scale 1 2] [--reltol 1e-5 1e-6] [design knobs]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_noise
import afe_chop_gain

HERE = os.path.dirname(os.path.abspath(__file__))
FS_AMP = 0.943396e-3
T_START, NSIG = 0.5e-3, 4


def deck(a, amp, reltol):
    fch = a.fch
    fsig = fch / 64
    tstop = T_START + NSIG / fsig
    t = afe_chop_gain.deck(a.core, a.tg, a.rs, 0.0, fch, a.vpc, a.cpf, a.blank)
    t = t.replace("VSRC SRC 0 DC 0", f"VSRC SRC 0 DC 0 SIN(0 {amp:.9e} {fsig:g})")
    t = t.replace("reltol=1e-5 vntol=1e-8 abstol=1e-12", f"reltol={reltol:g} vntol=1e-8 abstol=1e-12")
    t = re.sub(r"^tran .*$", f"tran 4n {tstop:.6e} 0 4n", t, flags=re.M)
    if a.cload is not None:
        t = re.sub(r"^(CLOAD[PN] \S+ \S+) 4p$", rf"\g<1> {a.cload:g}p", t, flags=re.M)
    if a.chold:  # differential hold capacitor on the AFE output (output-chopper blanking)
        t = t.replace("CLOADN OUTN 0 4p", f"CLOADN OUTN 0 4p\nCHOLD OUTP OUTN {a.chold:g}p", 1)
    assert "SIN(" in t and f"reltol={reltol:g}" in t
    return t


def ideal_switches(cand, which):
    """Diagnostic: replace chopper TGs by linear voltage-controlled switches (no charge)."""
    cand = ".model SWOUT sw vt=1.65 vh=0.2 ron=100 roff=1e12\n.model SWIN sw vt=1.65 vh=0.2 ron=3 roff=1e12\n" + cand
    if which in ("out", "both"):
        for inst, a_, b_, g in (("XOP_A", "OPI", "OUTP", "CDA"), ("XON_A", "ONI", "OUTN", "CDA"),
                                ("XOP_B", "OPI", "OUTN", "CDB"), ("XON_B", "ONI", "OUTP", "CDB")):
            cand = re.sub(rf"^{inst} .*$", f"S{inst[1:]} {a_} {b_} {g} VSS SWOUT", cand, flags=re.M)
    if which in ("in", "both"):
        for inst, a_, b_, g in (("XIP_A", "EP", "WP", "CIA"), ("XIN_A", "EN", "WN", "CIA"),
                                ("XIP_B", "EP", "WN", "CIB"), ("XIN_B", "EN", "WP", "CIB")):
            cand = re.sub(rf"^{inst} .*$", f"S{inst[1:]} {a_} {b_} {g} VSS SWIN", cand, flags=re.M)
    return cand


def run(a, scale, reltol):
    amp = scale * FS_AMP
    name = (f"chopdist_core{a.core:g}_tg{a.tg}_ln{a.ln:g}_lp{a.lp:g}_it{a.itail:g}_sc{a.scasc:g}"
            f"_cpf{a.cpf:g}_b{afe_noise.BOOST}_bp{a.boost_pole:g}_f{a.fch/1e3:g}k_tgo{a.tgo}_cl{a.cload}_sw{a.ideal_sw}"
            f"_bl{a.blank:g}_ch{a.chold:g}"
            f"_x{scale:g}_rt{reltol:g}")
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    cand = afe_noise.candidate(a.core, a.tg, a.ln, a.lp, 1.0, a.itail, a.scasc, a.tgo)
    if a.ideal_sw:
        cand = ideal_switches(cand, a.ideal_sw)
    open(os.path.join(d, "cand.spice"), "w").write(cand)
    open(os.path.join(d, "tb.spice"), "w").write(deck(a, amp, reltol))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    t, v = np.loadtxt(os.path.join(d, "tr.csv"), unpack=True)
    os.remove(os.path.join(d, "tr.csv"))
    tch = 1 / a.fch
    q = np.concatenate([[0.0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))])
    edges = T_START + tch * np.arange(64 * NSIG + 1)
    avg = np.diff(np.interp(edges, t, q)) / tch
    spec = np.abs(np.fft.rfft(avg)) / (len(avg) / 2)
    h = [spec[k * NSIG] for k in range(1, 6)]
    return scale, reltol, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, nargs="+", default=[1.0, 2.0], help="amplitude / 0.943 mVpk")
    ap.add_argument("--reltol", type=float, nargs="+", default=[1e-5, 1e-6])
    ap.add_argument("--core", type=float, default=1.0)
    ap.add_argument("--tg", type=int, default=64)
    ap.add_argument("--ln", type=float, default=0.28)
    ap.add_argument("--lp", type=float, default=0.28)
    ap.add_argument("--itail", type=float, default=1.0)
    ap.add_argument("--scasc", type=float, default=None)
    ap.add_argument("--vpc", type=float, default=1.1)
    ap.add_argument("--cpf", type=float, default=2.10)
    ap.add_argument("--fch", type=float, default=afe_noise.FCH)
    ap.add_argument("--rs", type=float, default=afe_noise.RS)
    ap.add_argument("--boost", default="0", help="cascode boosting: 0, tr, or a behavioural gain")
    ap.add_argument("--tgo", type=int, default=8, help="output chopper TG multiplicity")
    ap.add_argument("--boost-pole", type=float, default=100e3, help="behavioural booster pole (Hz)")
    ap.add_argument("--blank", type=float, default=0.0, help="output-chopper blanking after each edge (s)")
    ap.add_argument("--chold", type=float, default=0.0, help="differential hold capacitor OUTP-OUTN (pF)")
    ap.add_argument("--cload", type=float, default=None, help="load capacitance per side (pF), default 4")
    ap.add_argument("--ideal-sw", choices=["in", "out", "both"], default=None,
                    help="diagnostic: linear switches instead of chopper TGs")
    a = ap.parse_args()
    a.scasc = a.itail if a.scasc is None else a.scasc
    afe_noise.set_boost(a.boost)
    afe_noise.BOOST_POLE = a.boost_pole
    jobs = [(s, rt) for s in a.scale for rt in a.reltol]
    with ThreadPoolExecutor(len(jobs)) as ex:
        res = list(ex.map(lambda j: run(a, *j), jobs))
    for scale, reltol, h in res:
        rel = [20 * np.log10(x / h[0]) for x in h[1:]]
        print(f"x{scale:g} FS ({scale * FS_AMP * 1e3:.3f} mVpk), reltol {reltol:g}: fundamental {h[0]*1e3:.2f} mVpk "
              f"(gain {h[0] / (scale * FS_AMP):.2f}); HD2 {rel[0]:.1f}, HD3 {rel[1]:.1f}, HD4 {rel[2]:.1f}, "
              f"HD5 {rel[3]:.1f} dBc", flush=True)


if __name__ == "__main__":
    main()
