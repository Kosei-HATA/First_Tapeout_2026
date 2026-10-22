#!/usr/bin/env python3
"""Chopped-transient gain of the AFE (CCIA cpf210 candidate) against the
frozen-phase LPTV prediction of afe_noise.py.

Both choppers run at fch (ideal drive through 10 ohm, 2 ns edges, 5 ns dead
time after each phase). INP/INN are reset to ONI/OPI by NMOS switches until 10 us, then held.
A DC differential input of +-VIN is applied from t=0 through RS per leg; the
in-band gain is the difference of the demodulated output averages over
62.5-218.75 us (10 periods at 64 kHz, 20 at 128 kHz), divided by 2 VIN. The load is RIN 9375 ohm to
an ideal virtual ground, as in afe_noise.py.

The frozen-phase output noise of afe_noise.py, summed over the chopper
harmonics, is referred to the electrode with this transient gain.

Usage: python3 afe_chop_gain.py [--rs 50e3 ...] [--vin 0.5e-3] [design knobs of afe_noise.py]
"""
import argparse
import os
import subprocess
import numpy as np
import afe_noise

HERE = os.path.dirname(os.path.abspath(__file__))
TR, TN = 2e-9, 5e-9
T0, TAVG = 62.5e-6, 156.25e-6  # averaging window: 10 periods at 64 kHz, 20 at 128 kHz


def clocks(tch, blank=0.0):
    """PWL (repeating) for phase A (high at t=0) and phase B. With blank > 0 the
    phases rise blank seconds after the nominal edge (output-chopper blanking:
    both output switches stay open while the amplifier output settles)."""
    if blank <= 0:
        a = f"0 3.3 {tch/2-TN-TR:.6e} 3.3 {tch/2-TN:.6e} 0 {tch-TR:.6e} 0 {tch:.6e} 3.3"
        b = f"0 0 {tch/2:.6e} 0 {tch/2+TR:.6e} 3.3 {tch-TN-TR:.6e} 3.3 {tch-TN:.6e} 0 {tch:.6e} 0"
        return a, b
    a = (f"0 0 {blank:.6e} 0 {blank+TR:.6e} 3.3 {tch/2-TN-TR:.6e} 3.3 {tch/2-TN:.6e} 0 {tch:.6e} 0")
    b = (f"0 0 {tch/2+blank:.6e} 0 {tch/2+blank+TR:.6e} 3.3 {tch-TN-TR:.6e} 3.3 {tch-TN:.6e} 0 "
         f"{tch:.6e} 0")
    return a, b


def deck(core, tg, rs, vin, fch, vpc, cpf=2.10, blank=0.0):
    a, b = clocks(1 / fch)
    ao, bo = clocks(1 / fch, blank)
    noise_deck = afe_noise.deck(core, tg, "A", rs, vpc, cpf)
    # reuse the passive network and DUT lines of the noise deck
    body = noise_deck.split("VDD VDD 0 3.3\n", 1)[1].split("XDUT", 1)[0]
    body = body.replace("VSRC SRC 0 DC 0 AC 1", f"VSRC SRC 0 DC {vin}")
    body = body.replace(" noisy=0", "")
    body = body.split("* DC path", 1)[0]
    head = noise_deck.split("VDD VDD 0 3.3\n", 1)[0]
    nodeset = ".nodeset" + noise_deck.split(".nodeset", 1)[1].split(".control", 1)[0]
    head = head.replace("* AFE frozen-phase noise", "* AFE chopped transient", 1)
    # the averaged gain does not need the .noise tolerances; the large input TGs
    # stall the step control at the chopper edges with reltol 1e-6
    head = head.replace("reltol=1e-6 vntol=1e-10 abstol=3e-13", "reltol=1e-5 vntol=1e-8 abstol=1e-12")
    return f"""{head}VDD VDD 0 3.3
{body}XRSTP INP RST ONI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
XRSTN INN RST OPI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
VRST RST_D 0 PWL(0 3.3 10u 3.3 11u 0)
RGRST RST_D RST 10
XDUT VINP VINN WP WN INP INN OPI ONI OUTP OUTN CM VBN VBCM VNC VPC VBP CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD 0 gf180_ccia_local_feedback
* clock drivers: ideal waveforms through 10 ohm
VCIA CIA_D 0 PWL({a}) r=0
ENCIA NCIA_D 0 VDD CIA_D 1
VCIB CIB_D 0 PWL({b}) r=0
ENCIB NCIB_D 0 VDD CIB_D 1
VCDA CDA_D 0 PWL({ao}) r=0
ENCDA NCDA_D 0 VDD CDA_D 1
VCDB CDB_D 0 PWL({bo}) r=0
ENCDB NCDB_D 0 VDD CDB_D 1
RGCIA CIA_D CIA 10
RGNCIA NCIA_D NCIA 10
RGCIB CIB_D CIB 10
RGNCIB NCIB_D NCIB 10
RGCDA CDA_D CDA 10
RGNCDA NCDA_D NCDA 10
RGCDB CDB_D CDB 10
RGNCDB NCDB_D NCDB 10
{nodeset}.control
set noaskquit
tran 4n {T0 + TAVG:.6e} 0 4n
let vo = v(outp) - v(outn)
wrdata tr.csv vo
quit
.endc
.end
"""


def run_tran(rs, vin, a):
    name = (f"chop_core{a.core:g}_tg{a.tg}_ln{a.ln:g}_lp{a.lp:g}_mp{a.mp:g}_it{a.itail:g}_sc{a.scasc:g}"
            f"_vpc{a.vpc:g}_cpf{a.cpf:g}_b{afe_noise.BOOST}_f{a.fch/1e3:g}k_rs{rs:g}_vin{vin:+g}")
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "cand.spice"), "w").write(
        afe_noise.candidate(a.core, a.tg, a.ln, a.lp, a.mp, a.itail, a.scasc))
    open(os.path.join(d, "tb.spice"), "w").write(deck(a.core, a.tg, rs, vin, a.fch, a.vpc, a.cpf))
    return d, subprocess.Popen(["ngspice", "-b", "tb.spice"], cwd=d,
                               stdout=open(os.path.join(d, "run.log"), "w"), stderr=subprocess.STDOUT)


def average(d):
    t, v = np.loadtxt(os.path.join(d, "tr.csv"), unpack=True)
    os.remove(os.path.join(d, "tr.csv"))
    m = t >= T0
    return np.trapezoid(v[m], t[m]) / (t[m][-1] - t[m][0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=float, default=1.0)
    ap.add_argument("--tg", type=int, default=64)
    ap.add_argument("--rs", type=float, nargs="+", default=[50e3])
    ap.add_argument("--vin", type=float, default=0.5e-3)
    ap.add_argument("--ln", type=float, default=0.28)
    ap.add_argument("--lp", type=float, default=0.28)
    ap.add_argument("--mp", type=float, default=1.0)
    ap.add_argument("--itail", type=float, default=1.0)
    ap.add_argument("--scasc", type=float, default=None)
    ap.add_argument("--vpc", type=float, default=1.1)
    ap.add_argument("--fch", type=float, default=afe_noise.FCH)
    ap.add_argument("--cpf", type=float, default=2.10, help="impedance-boost capacitor (pF)")
    ap.add_argument("--tran-only", action="store_true", help="skip the LPTV noise run")
    ap.add_argument("--boost", default="0", help="cascode boosting: 0, tr, or a behavioural gain")
    a = ap.parse_args()
    afe_noise.set_boost(a.boost)
    a.scasc = a.itail if a.scasc is None else a.scasc
    jobs = {rs: [run_tran(rs, s * a.vin, a) for s in (1, -1)] for rs in a.rs}
    print(f"core x{a.core:g}, TG m={a.tg}, L N/P {a.ln:g}/{a.lp:g} um, mp {a.mp:g}, itail {a.itail:g}, "
          f"scasc {a.scasc:g}, VPC {a.vpc:g}, fch {a.fch/1e3:g} kHz; "
          f"electrode-referred noise uses the transient gain")
    print("| RS per leg (ohm) | frozen gain | LPTV gain | transient gain | chopped thermal (nVrms) | chopped 1/f (nVrms) | total (nVrms) |")
    print("|---|---|---|---|---|---|---|")
    for rs, pair in jobs.items():
        for _, p in pair:
            p.wait()
        vp, vn = (average(d) for d, _ in pair)
        g = (vp - vn) / (2 * a.vin)
        if a.tran_only:
            print(f"| {rs:g} | - | - | {g:.1f} | - | - | - |  (Cpf {a.cpf:g} pF, offset {(vp + vn) / 2 * 1e3:+.3f} mV)",
                  flush=True)
            continue
        lptv = afe_noise.run(a.core, a.tg, "A", rs=rs, ln=a.ln, lp=a.lp, fch=a.fch, mp=a.mp,
                             itail=a.itail, scasc=a.scasc, vpc=a.vpc, cpf=a.cpf)
        th, fl = (x * lptv["gain_chop"] / g for x in lptv["total"][1:])
        print(f"| {rs:g} | {lptv['gain10']:.1f} | {lptv['gain_chop']:.1f} | {g:.1f} | {th:.2f} | {fl:.2f} | "
              f"{np.hypot(th, fl):.2f} |", flush=True)


if __name__ == "__main__":
    main()
