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
--avdd sets the board AVDD alone (11/16: the raised AVDD proposed for the AFE's headroom; DVDD and the trim lines
stay at 3.3 V); --boost sets BOOST_TRIM (BTRIM_P = BP1:BP0, BTRIM_N = BN1:BN0, codes 0..3 = 2 / 4 / 6 / 8 units;
1 1 = 4 / 4, the reset value; BTRIM_P sets the BLN leg, the PMOS-cascode boosters' loads, which is the margin map's
NBLN, and BTRIM_N the BLP leg (NBLP), so the 3.40 V trim ff 8/2 is --boost 3 0, as afe_trim_start.py --bp 3 --bn 0);
--corner sets the MOS / resistor / MIM / diode corner (afe_startup.head; typical by default, Monte Carlo seeds ignore
it). Runs off the defaults get _<corner> / _avdd<v> / _bt<P>-<N> in their folder names.

Variants: chip (chipnets of the filled chip; --chip nofill / highr: before the fill, high-corner metal
resistance), ideal (the same nets with the wiring ideal:
afe_startup.chip_model's R x 1e-4 and no C, no rails inside afe_top; the blocks on one supply
and ground as in pex_afe.py, which it should reproduce).

Usage: python3 gf180/tapeout/pex/afe_chip_noise.py [--variants chip ideal] [--phase A B] [--ibias 2 3] [--mc 1 2 ...]
           [--avdd 3.40 3.43 ...] [--boost 0 0] [--corner typical ss ff sf fs]
"""
import argparse
import json
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

RUNS = os.path.join(HERE, "runs", "chip_noise" + (f"_{S._REV}" if S._REV else ""))   # EEG_PEX_REV: the chip wiring of that chip
VDD, VREFP, VREFN, CVCM, R_BW = 3.3, 1.9, 1.4, 10e-9, 0.1
UNITS = (2, 4, 6, 8)                                  # BOOST_TRIM codes 0..3 (afe_trim_start.py)
OP = ("i(vavdd) v(avdd_afei) v(avss_afei) v(avdd_bias) v(avss_bias) v(vbn_afe) v(vbn_bias) v(vcm_afe) "
      "v(vrefp_adc) v(vrefn_adc) v(xdut.opi) v(xdut.oni) v(xdut.inp) v(xdut.inn) @rafevss[i]")


def deck(variant, phase, code, seed, kind="fill", avdd=VDD, boost=(1, 1), corner="typical"):
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
    return f"""* afe_top on the chip's operating point ({variant}): frozen phase {phase}, AFE_IBIAS code {code}, {'mc' + str(seed) if mc else corner}, noise
{S.head(corner, seed, "lin")}.include {S.REF_PEX}
.include {chip}
{bias}
{afe}
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VAVDD AVDD_BRD 0 {avdd:g}
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
BBP1 BP1 0 {lvl(boost[0] >> 1 & 1)}
BBP0 BP0 0 {lvl(boost[0] & 1)}
BBN1 BN1 0 {lvl(boost[1] >> 1 & 1)}
BBN0 BN0 0 {lvl(boost[1] & 1)}
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


def run_dir(variant, phase, code, seed, kind="fill", avdd=VDD, boost=(1, 1), corner="typical"):
    corner = "typical" if seed is not None else corner
    return os.path.join(RUNS, f"{variant}_{phase}_ib{code}" + (f"_mc{seed}" if seed is not None else "") +
                        (f"_{corner}" if corner != "typical" else "") +
                        (f"_{kind}" if kind != "fill" else "") + (f"_avdd{avdd:g}" if avdd != VDD else "") +
                        (f"_bt{UNITS[boost[0]]}-{UNITS[boost[1]]}" if tuple(boost) != (1, 1) else ""))


def analyze(d):
    """a finished run's folder: chopped gain, supply currents and voltages, and the chopped in-band noise at the input"""
    log = open(os.path.join(d, "run.log")).read()
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
    return dict(gain=g, idd=-v.get("i(vavdd)", np.nan) * 1e3, iafe=v.get("@rafevss[i]", np.nan) * 1e3,
                vafe=v.get("v(avdd_afei)", np.nan) - v.get("v(avss_afei)", np.nan),
                vbn=v.get("v(vbn_afe)", np.nan) - v.get("v(avss_afei)", np.nan),
                vbnb=v.get("v(vbn_bias)", np.nan) - v.get("v(avss_bias)", np.nan),
                total=ntot * 1e9, flicker=nfl * 1e9, thermal=np.sqrt(max(ntot ** 2 - nfl ** 2, 0)) * 1e9)


# the AFE core's devices in the extracted afe_top (r6 on): the input pairs, their cascodes and the cascode boosters
CORE_DEVS = {"x424": "pmos_pair", "x425": "pmos_pair", "x417": "pmos_casc", "x418": "pmos_casc", "x427": "nmos_pair",
             "x428": "nmos_pair", "x415": "nmos_casc", "x416": "nmos_casc", "x429": "pmos_booster", "x430": "pmos_booster",
             "x421": "nmos_booster", "x422": "nmos_booster"}


def op_margins(d):
    """the operating point of a run's deck (op only, in <d>/op/): per group of CORE_DEVS the smallest |VDS| - |VDSAT| (V),
    the input pairs' gm and the boosters' currents; cached in <d>/op_margins.json"""
    fj = os.path.join(d, "op_margins.json")
    if os.path.exists(fj):
        return json.load(open(fj))
    t = open(os.path.join(d, "tb.spice")).read()
    c0, c1 = t.index(".control"), t.index(".endc")
    vec = " ".join(f"@m.xdut.{x}.m0[{q}]" for x in CORE_DEVS for q in ("vds", "vdsat", "id", "gm"))
    t = t[:c0] + f".control\nset noaskquit\nsave all {vec}\nop\nprint {vec}\nquit\n" + t[c1:]
    o = os.path.join(d, "op")
    os.makedirs(o, exist_ok=True)
    open(os.path.join(o, "tb.spice"), "w").write(t)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=o, capture_output=True, text=True)
    open(os.path.join(o, "run.log"), "w").write(r.stdout + r.stderr)
    v = {k: float(x) for k, x in re.findall(r"^(\S+) = ([-0-9.e+]+)", r.stdout, re.M)}
    q = lambda x, k: v[f"@m.xdut.{x}.m0[{k}]"]   # noqa: E731
    out = {}
    for x, grp in CORE_DEVS.items():
        m = abs(q(x, "vds")) - abs(q(x, "vdsat"))
        out[grp] = min(out.get(grp, m), m)
    out.update(pmos_pair_gm=q("x424", "gm"), nmos_pair_gm=q("x427", "gm"), i_pmos_booster=abs(q("x429", "id")),
               i_nmos_booster=abs(q("x421", "id")))
    json.dump(out, open(fj, "w"), indent=1)
    return out


def one(variant, phase, code, seed, kind="fill", avdd=VDD, boost=(1, 1), corner="typical"):
    corner = "typical" if seed is not None else corner
    d = run_dir(variant, phase, code, seed, kind, avdd, boost, corner)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(variant, phase, code, seed, kind, avdd, boost, corner))
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    opts = ([corner] if corner != "typical" else []) + ([kind] if kind != "fill" else []) + \
           ([f"AVDD {avdd:g} V"] if avdd != VDD else []) + \
           ([f"boost {UNITS[boost[0]]}/{UNITS[boost[1]]}"] if tuple(boost) != (1, 1) else [])
    return dict(variant=variant + (f" ({', '.join(opts)})" if opts else ""), phase=phase, code=code, seed=seed,
                t=time.time() - t, **analyze(d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="+", default=["chip", "ideal"], choices=["chip", "ideal"])
    ap.add_argument("--phase", nargs="+", default=["A", "B"])
    ap.add_argument("--ibias", nargs="+", type=int, default=[2], help="AFE_IBIAS code (2: reset value)")
    ap.add_argument("--mc", nargs="+", type=int, default=None, help="Monte Carlo seeds (afe_startup.head)")
    ap.add_argument("--chip", default="fill", choices=["fill", "nofill", "highr"],
                    help="chip wiring: filled chip, before the fill, high-corner metal resistance")
    ap.add_argument("--avdd", nargs="+", type=float, default=[VDD], help="board AVDD (V); DVDD and the trim lines stay at 3.3 V")
    ap.add_argument("--corner", nargs="+", default=["typical"], choices=list(S.MOSF))
    ap.add_argument("--boost", nargs=2, type=int, default=[1, 1], metavar=("BTRIM_P", "BTRIM_N"),
                    help="BOOST_TRIM codes 0..3 (2 / 4 / 6 / 8 units; 1 1 = 4 / 4, the reset value)")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    jobs = [(v, p, c, s, a.chip, av, tuple(a.boost), k) for k in a.corner for av in a.avdd for v in a.variants for c in a.ibias for s in (a.mc or [None]) for p in a.phase]
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
