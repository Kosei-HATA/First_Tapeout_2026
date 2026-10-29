#!/usr/bin/env python3
"""AFE noise on the chip's own operating point: pex_afe.py's noise method (one chopper phase
frozen, .ac for the electrode-to-output transfer, .noise for the output density, the chopped
estimate over 0.5-100 Hz from the harmonic sums of afe_noise.py) with the blocks wired as on
the chip instead of on one ideal supply and ground:

  - afe_top extracted with the signal path's wiring resistance (pex_afe.RIN_EXTRACTED W and T
    inside, the chopper's part of E at its electrode pins), the chip wiring's couplings to its
    inner nets, and its own supply rails (afe_startup.RAFE, lumped);
  - eeg_bias and eeg_ref extracted, each on its own pins of the chip wiring (chipnets: pad
    cells, AVDD / AVSS grid, decoupling, bias lines, VCM, electrode straps, OUTP / OUTN to the
    ADC, the references), so the AFE's tails see VBN against the bias block's AVSS;
  - the ADC's supply current (afe_startup.IADC) on its pins, its input resistors into a virtual
    ground that follows its VCM pin, its reference load;
  - supplies, references and the electrodes' source at the board through one bond wire (0.1 ohm)
    per bonded pad; the VCM capacitor 10 nF on the board.

Noise counted: every device and resistor of the chip, the chip wiring's included (the pad cells
and straps in series with the electrodes, the grid, the bias lines). Not counted, as in
pex_afe.py: the electrodes' 100 ohm per leg, the ADC's input resistors; nor the bond wires (the
package, with the electrodes). The AFE_IBIAS trim is --ibias (2: the register's reset value).

Variants: chip (chipnets of the filled chip; --chip nofill / highr: before the fill, high-corner metal
resistance), ideal (the same nets with the wiring ideal:
afe_startup.chip_model's R x 1e-4 and no C, no rails inside afe_top; the blocks on one supply
and ground as in pex_afe.py, which it should reproduce).

Usage: python3 gf180/tapeout/pex/afe_chip_noise.py [--variants chip ideal] [--phase A B] [--ibias 2 3] [--mc 1 2 ...]
"""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import afe_startup as S  # noqa: E402  (chip wiring, extracted blocks, model libraries)
import pex_afe as P  # noqa: E402
import afe_noise  # noqa: E402  (raw reader, harmonic sums; on pex_afe's path)

RUNS = os.path.join(HERE, "runs", "chip_noise")
VDD, VREFP, VREFN, CVCM, R_BW = 3.3, 1.9, 1.4, 10e-9, 0.1
OP = ("i(vavdd) v(avdd_afei) v(avss_afei) v(avdd_bias) v(avss_bias) v(vbn_afe) v(vbn_bias) v(vcm_afe) "
      "v(vrefp_adc) v(vrefn_adc) v(xdut.opi) v(xdut.oni) v(xdut.inp) v(xdut.inn) @rafevss[i]")


def deck(variant, phase, code, seed, kind="fill"):
    mc = seed is not None
    chip = S.chip_model("pex" if variant == "chip" else "sch", kind)
    extra = (open(os.path.join(S.CHIPNETS, os.path.basename(chip).replace(".spice", "_afe_extra.spice"))).read()
             if variant == "chip" else "")
    afe = P.dut_text("pex", extra + "LDCP INP ONI 1e16\nLDCN INN OPI 1e16\n", P.RIN_EXTRACTED)
    bias = open(S.BIAS_PEX).read()
    if mc:
        afe, bias = S.par_m(afe), S.par_m(bias)
    e = [P.RIN_EXTRACTED["E"][k] - S.STRAP_RIN[k] for k in range(2)]
    rafe = S.RAFE if variant == "chip" else (0.0, 0.0)
    chop, en = ("DVDDC", "0") if phase == "A" else ("0", "DVDDC")
    lvl = lambda b: f"V={VDD:g}" if b else "V=0"   # noqa: E731  (trim lines at DVDD / DVSS, both ideal here)
    wires = "".join(f"RBWAVDD{k} AVDD_BRD AVDD_P{k} {R_BW:g} noisy=0\n" for k in S.PADS["AVDD"])
    wires += "".join(f"RBWAVSS{k} 0 AVSS_P{k} {R_BW:g} noisy=0\n" for k in S.PADS["AVSS"])
    wires += "".join(f"RBW{n}{k} {n}_BRD {n}_P{k} {R_BW:g} noisy=0\n" for n in ("ELP", "ELN") for k in S.PADS[n])
    return f"""* afe_top on the chip's operating point ({variant}): frozen phase {phase}, AFE_IBIAS code {code}, {'mc' + str(seed) if mc else 'typical'}, noise
{S.head("typical", seed, "lin")}.include {S.REF_PEX}
.include {chip}
{bias}
{afe}
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VAVDD AVDD_BRD 0 {VDD:g}
VDVDD DVDDC 0 {VDD:g}
VDVSS DVSSC 0 0
{wires}{S.chip_line(chip)}RAFEVDD AVDD_AFE AVDD_AFEI {max(rafe[1], 1e-6):g}
RAFEVSS AVSS_AFEI AVSS_AFE {max(rafe[0], 1e-6):g}
VREFPX VREFP_EXT 0 {VREFP:g}
VREFNX VREFN_EXT 0 {VREFN:g}
RBWVREFP VREFP_EXT VREFP_PAD_P10 {R_BW:g} noisy=0
RBWVREFN VREFN_EXT VREFN_PAD_P11 {R_BW:g} noisy=0
CVCM VCM_BRD 0 {CVCM:g}
RBWVCM VCM_BRD VCM_P9 {R_BW:g} noisy=0
XREF VREFP_PAD_REF VREFN_PAD_REF VREFP_REF VREFN_REF AVSS_REF eeg_ref
RADC VREFP_ADC VREFN_ADC 18.4k noisy=0
IADC AVDD_ADC AVSS_ADC {S.IADC:g}
XB VBN_BIAS VBCM_BIAS BLP_BIAS BLN_BIAS VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM_BIAS VREFP_BIAS VREFN_BIAS
+ IB1 IB0 BP1 BP0 BN1 BN0 AVDD_BIAS AVSS_BIAS eeg_bias
XDQ IQ IQ AVSS_ADC AVSS_ADC nfet_03v3 W=4u L=2u nf=1 m=8{' par=8' if mc else ''}
VITST ITST AVSS_TM 0
BIB1 IB1 0 {lvl(code >> 1 & 1)}
BIB0 IB0 0 {lvl(code & 1)}
BBP1 BP1 0 V=0
BBP0 BP0 0 V={VDD:g}
BBN1 BN1 0 V=0
BBN0 BN0 0 V={VDD:g}
ECHOP CHOP 0 {chop} 0 1
ECHOPO CHOP_OUT 0 {chop} 0 1
VBLK CHOP_BLANK 0 0
ECHEN CHOP_EN 0 {en} 0 1
VAR AFE_RST 0 0
VSRC SRC 0 DC 0 AC 1
EP SRC_P VCM_BRD SRC 0 0.5
EN SRC_N VCM_BRD SRC 0 -0.5
RSP SRC_P ELP_BRD 100 noisy=0
RSN SRC_N ELN_BRD 100 noisy=0
RECHP ELP_AFE ELP {e[0]:g}
RECHN ELN_AFE ELN {e[1]:g}
EVG VG AVSS_ADC VCM_ADC AVSS_ADC 1
RLOADP OUTP_ADC VG {P.RIN:g} noisy=0
RLOADN OUTN_ADC VG {P.RIN:g} noisy=0
{S.dut_line(None)}
.nodeset v(xdut.inp)=1.65 v(xdut.inn)=1.65 v(xdut.opi)=1.65 v(xdut.oni)=1.65 v(outp_adc)=1.65 v(outn_adc)=1.65
+ v(xb.g1)=0.85 v(xb.gp)=2.2 v(vbn_bias)=0.84 v(vbcm_bias)=0.81 v(bln_bias)=1.1 v(blp_bias)=1.5
.control
set noaskquit
op
print {OP}
ac dec 20 0.1 1e7
let hr = real(v(outp_adc) - v(outn_adc))
let hi = imag(v(outp_adc) - v(outn_adc))
wrdata ac.csv hr hi
noise v(outp_adc, outn_adc) VSRC dec 20 0.1 1e7 1
setplot noise1
set filetype=ascii
write noise.raw
quit
.endc
.end
"""


def one(variant, phase, code, seed, kind="fill"):
    d = os.path.join(RUNS, f"{variant}_{phase}_ib{code}" + (f"_mc{seed}" if seed is not None else "") +
                     (f"_{kind}" if kind != "fill" else ""))
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(variant, phase, code, seed, kind))
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    v = {k.lower(): float(x) for k, x in re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}
    ac = np.loadtxt(os.path.join(d, "ac.csv"))
    f, h = ac[:, 0], ac[:, 1] + 1j * ac[:, 3]
    nz = afe_noise.read_raw(os.path.join(d, "noise.raw"))
    fn = nz["frequency"]
    tot = nz["onoise_spectrum"] ** 2
    fl = sum((s ** 2 for n, s in nz.items() if n.endswith("1overf")), np.zeros_like(fn))
    kmax = int(fn[-1] / P.FCH) - 1
    g = abs(afe_noise.chop_sum(f, h.real, kmax, P.FCH))
    bw = P.BAND[1] - P.BAND[0]
    ntot = np.sqrt(afe_noise.chop_sum(fn, tot, kmax, P.FCH) * bw) / g
    nfl = np.sqrt(afe_noise.chop_sum(fn, fl, kmax, P.FCH) * bw) / g
    return dict(variant=variant + (f" ({kind})" if kind != "fill" else ""), phase=phase, code=code, seed=seed, t=time.time() - t, gain=g,
                idd=-v.get("i(vavdd)", np.nan) * 1e3, iafe=v.get("@rafevss[i]", np.nan) * 1e3,
                vafe=v.get("v(avdd_afei)", np.nan) - v.get("v(avss_afei)", np.nan),
                vbn=v.get("v(vbn_afe)", np.nan) - v.get("v(avss_afei)", np.nan),
                vbnb=v.get("v(vbn_bias)", np.nan) - v.get("v(avss_bias)", np.nan),
                total=ntot * 1e9, flicker=nfl * 1e9, thermal=np.sqrt(max(ntot ** 2 - nfl ** 2, 0)) * 1e9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["chip", "ideal"], choices=["chip", "ideal"])
    ap.add_argument("--phase", nargs="+", default=["A", "B"])
    ap.add_argument("--ibias", nargs="+", type=int, default=[2], help="AFE_IBIAS code (2: reset value)")
    ap.add_argument("--mc", nargs="+", type=int, default=None, help="Monte Carlo seeds (afe_startup.head)")
    ap.add_argument("--chip", default="fill", choices=["fill", "nofill", "highr"],
                    help="chip wiring: filled chip, before the fill, high-corner metal resistance")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    jobs = [(v, p, c, s, a.chip) for v in a.variants for c in a.ibias for s in (a.mc or [None]) for p in a.phase]
    print("| wiring | phase | AFE_IBIAS | seed | AVDD current (mA) | AFE current (mA) | AFE supply (V) | VBN at the AFE / "
          "at the bias (V) | chopped gain | total (nVrms) | thermal | 1/f | run (s) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    with ThreadPoolExecutor(min(a.jobs, len(jobs))) as ex:
        for r in ex.map(lambda j: one(*j), jobs):
            print(f"| {r['variant']} | {r['phase']} | {r['code']} | {r['seed'] if r['seed'] is not None else '-'} | "
                  f"{r['idd']:.3f} | {r['iafe']:.3f} | {r['vafe']:.4f} | {r['vbn']:.4f} / {r['vbnb']:.4f} | {r['gain']:.2f} | "
                  f"{r['total']:.3f} | {r['thermal']:.3f} | {r['flicker']:.3f} | {r['t']:.0f} |", flush=True)


if __name__ == "__main__":
    main()
