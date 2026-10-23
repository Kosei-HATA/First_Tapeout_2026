#!/usr/bin/env python3
"""AFE with and without parasitics (tracker D6): the same testbenches on three versions
of the AFE layout block afe_top (input chopper afe_tgin, core eeg_afe_core, Cin arrays,
output section, offset-DAC halves, clock driver eeg_afe_clk with its 100 ohm supply):

  sch  the schematic: the LVS wrapper gf180/tapeout/layout/lvs/afe_top.spice on the
       simulation netlists (eeg_afe.spice, eeg_afe_clk.spice, the wrappers of afe_tgin
       and the offset-DAC halves);
  dev  the devices that magic extracts from the layout, no parasitic capacitances (finger
       widths and junction areas of the layout);
  pex  dev with every extracted parasitic capacitance (pex.py, runs/afe_top_c).

Testbenches (typical, 27 C, CPF_TRIM 8, offset DAC off, RS 100 ohm per leg, the ADC
input as the load: RIN 18.75 kohm per side to VCM, noiseless):
  noise  one chopper phase frozen (CHOP_EN low = phase A, or CHOP_EN high with CHOP low
         = phase B), the real bias block eeg_bias, and the method of afe_noise.py: .ac
         for the electrode-to-output transfer H(f), .noise for the output density, the
         chopped estimate sqrt(sum_k 8/(pi k)^2 S(k fch) x BW) / sum_k 8/(pi k)^2 Re H(k fch)
         over 0.5-100 Hz. The INP/INN DC path is the noiseless 1e16 H of afe_noise.py
         (INP-ONI, INN-OPI), added inside the DUT. Electrode and load resistors noiseless.
  tran   both choppers at 128 kHz from the block's own clock driver (CHOP, CHOP_OUT =
         CHOP, CHOP_BLANK 1 MCLK before to 7 MCLK after each edge), ideal bias (as
         afe_offset.py), INP/INN reset until 10 us, a DC input: the output OUTP - OUTN is
         averaged over 100-200 us (offset: 0 mV in; gain: +-0.5 mV), and its
         peak-to-peak outside the blanking windows is the ripple.

  sine   the same with a full-scale sine (0.943 mV pk) at fch/64 from 20 us: gain and
         HD2..HD5 of the output averaged over each chopper period, FFT from 2 ms.
  --rwire (noise): the extracted wiring resistance of the signal path (pex_rin.py) in
         series: E with the source resistors, W between the chopper and Cin, T between
         INP / INN and the input-pair gates.

Usage: python3 gf180/tapeout/pex/pex_afe.py noise [--variants sch dev pex] [--phase A B] [--rwire]
       python3 gf180/tapeout/pex/pex_afe.py tran [--variants ...] [--vin 0 0.5 -0.5]
       python3 gf180/tapeout/pex/pex_afe.py sine [--variants ...]
"""
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

trapz = getattr(np, "trapezoid", None) or np.trapz

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "afe"))
import afe_noise  # noqa: E402  (PDK path, raw reader, harmonic sums)

LAYOUT = os.path.join(REPO, "gf180", "tapeout", "layout")
AFE = os.path.join(REPO, "gf180", "tapeout", "afe")
BIAS = os.path.join(REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
MOSLIN = os.path.join(REPO, "gf180", "tapeout", "sim", "moscap_lin.spice")
PEXDIR = os.path.join(HERE, "runs", "afe_top_c")
RUNS = os.path.join(HERE, "runs", "afe")
PDK = afe_noise.PDK
FCH = 128e3
TCH = 1 / FCH
MCLK = 1 / 32.768e6
BLANK = 7 * MCLK
RIN = 18750.0
BAND = (0.5, 100.0)
SCH_FILES = [os.path.join(AFE, "eeg_afe.spice"), os.path.join(AFE, "eeg_afe_clk.spice"),
             os.path.join(LAYOUT, "lvs", "afe_tgin.spice"), os.path.join(LAYOUT, "lvs", "offdac_n.spice"),
             os.path.join(LAYOUT, "lvs", "offdac_p.spice")]


def ports():
    txt = re.sub(r"\n\+", " ", open(os.path.join(LAYOUT, "lvs", "afe_top.spice")).read())
    return re.search(r"^\.subckt afe_top (.*)$", txt, re.M).group(1).split()


# wiring resistance of the signal path per side (pex_rin.py, typical, ohm): electrode
# side E (in series with the source), Cin bottom-plate side W (chopper to Cin), top-plate
# side T (Cin to the input-pair gates)
RIN_EXTRACTED = {"E": (0.350, 0.346), "W": (3.970, 3.935), "T": (71.60, 114.59)}


def split_signal_path(text, variant):
    """Separate the input-pair gates (INPG / INNG) from INP / INN and the chopper's W
    terminals (WPT / WNT) from WP / WN, so that the wiring resistance can sit between."""
    if variant == "sch":
        a = "XTG ELP ELN WP WN CIA NCIA CIB NCIB AVDD AVSS afe_tgin"
        b = "XCORE INP INN OPI ONI VBN VBP BLP BLN AVDD AVSS eeg_afe_core"
        assert text.count(a) == 1 and text.count(b) == 1
        return text.replace(a, a.replace(" WP WN ", " WPT WNT ")).replace(b, b.replace(" INP INN ", " INPG INNG "))
    out = []
    n = {"g": 0, "w": 0}
    for ln in text.splitlines(keepends=True):
        t = ln.split()
        if t and t[0].startswith("X") and t[-1] != "afe_top" and len(t) > 5:
            if t[5] in ("nfet_03v3", "pfet_03v3") and t[2] in ("INP", "INN") and \
                    ("l=1.5u" in t and "w=20u" in t and t[5] == "nfet_03v3" or
                     "l=0.28u" in t and "w=20u" in t and t[5] == "pfet_03v3"):
                t[2] = t[2] + "G"          # input-pair gate
                n["g"] += 1
                ln = " ".join(t) + "\n"
            elif t[5] in ("nfet_03v3", "pfet_03v3") and {t[1], t[3]} & {"WP", "WN"} and {t[1], t[3]} & {"ELP", "ELN"}:
                t = [x + "T" if i in (1, 3) and x in ("WP", "WN") else x for i, x in enumerate(t)]
                n["w"] += 1
                ln = " ".join(t) + "\n"
        out.append(ln)
    assert n["g"] == 4 and n["w"] == 8, n
    return "".join(out)


def dut_text(variant, extra="", rin=None):
    """afe_top subcircuit text for a variant, with `extra` lines inserted before .ends;
    rin = {"W": (P, N), "T": (P, N)} puts the wiring resistance in series (E goes into the
    testbench's source resistors)."""
    if variant == "sch":
        txt = "".join(f".include {f}\n" for f in SCH_FILES)
        wrap = open(os.path.join(LAYOUT, "lvs", "afe_top.spice")).read()
    else:
        txt = ""
        wrap = open(os.path.join(PEXDIR, f"afe_top_{variant}.spice")).read()
    assert wrap.count(".ends afe_top") == 1
    if rin:
        wrap = split_signal_path(wrap, variant)
        extra += (f"RWIRE_WP WPT WP {rin['W'][0]:g}\nRWIRE_WN WNT WN {rin['W'][1]:g}\n"
                  f"RWIRE_TP INP INPG {rin['T'][0]:g}\nRWIRE_TN INN INNG {rin['T'][1]:g}\n")
    return txt + wrap.replace(".ends afe_top", extra + ".ends afe_top")


UNIT_MV = 60e-15 * 3.3 / 636e-12 * 1e3   # offset-DAC step, electrode-referred (afe_offset.py)
NBITS = {1: 7, 2: 8, 3: 9, 4: 10}


def xline(cpf=8, dac=None):
    """DUT instance: driver outputs and their output-section copies joined; offset DAC off,
    or dac = (offset mV, range 1..4): both halves set for that offset (afe_offset.py)."""
    conn = {"VCM": "CM", "VCM_N": "CM", "VCM_P": "CM", "AVDD": "VDD", "AVSS": "0",
            "RST2": "RST", "CIA2": "CIA", "CIB2": "CIB", "CDA2": "CDA", "NCDA2": "NCDA", "CDB2": "CDB",
            "NCDB2": "NCDB", "OFPH_N": "OFPH", "OFPH_P": "OFPH"}
    for k in range(4):
        conn[f"CPF{k}"] = "VDD" if (cpf >> k) & 1 else "0"
    if dac:
        vos, rng = dac
        mag = min(int(round(abs(vos) / UNIT_MV)), 2 ** NBITS[rng] - 1)
        for h in ("N", "P"):
            conn[f"OFS_{h}"] = "VDD" if vos < 0 else "0"
            for k in range(10):
                conn[f"OFM{k}_{h}"] = "VDD" if (mag >> k) & 1 else "0"
            for g in range(4):
                conn[f"OFEN{g}_{h}"] = "VDD" if g < rng else "0"
    out = []
    for p in ports():
        if p in conn:
            out.append(conn[p])
        elif re.match(r"OF(S|M\d|EN\d)_[NP]$", p):
            out.append("0")
        else:
            out.append(p)
    return "XDUT " + " ".join(out) + " afe_top"


def head(corner="typical"):
    return (f".include {PDK}/design.ngspice\n.lib {PDK}/sm141064.ngspice {corner}\n"
            f".lib {PDK}/sm141064.ngspice res_typical\n.lib {PDK}/sm141064.ngspice mimcap_typical\n"
            f".lib {PDK}/sm141064.ngspice cap_mim\n.param moscap_corner=1\n.include {MOSLIN}\n")


BIAS_LINES = """VRP VREFP 0 1.9
VRN VREFN 0 1.4
VITST ITST 0 1
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCMX VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0 VDD 0 eeg_bias
XDQ IQ IQ 0 0 nfet_03v3 W=4u L=2u nf=1 m=8
VIB1 IB1 0 3.3
VIB0 IB0 0 0
VBP1 BP1 0 0
VBP0 BP0 0 3.3
VBN1 BN1 0 0
VBN0 BN0 0 3.3
.nodeset v(xb.g1)=0.85 v(xb.gp)=2.2 v(vbn)=0.84 v(vbcm)=0.81 v(xb.nt)=0.84
+ v(xb.nc)=0.81 v(xb.nd)=0.8 v(xb.sb)=0 v(bln)=1.1 v(blp)=1.5 v(xb.s2)=0.05
"""


def noise_deck(variant, phase, rs=100.0, rin=None):
    chop, en = ("3.3", "0") if phase == "A" else ("0", "3.3")
    dut = dut_text(variant, "LDCP INP ONI 1e16\nLDCN INN OPI 1e16\n", rin)
    rwe = f"RWIRE_EP SRC_P ELPX {rin['E'][0]:g}\nRWIRE_EN SRC_N ELNX {rin['E'][1]:g}\n" if rin else ""
    sp, sn = ("ELPX", "ELNX") if rin else ("SRC_P", "SRC_N")
    return f"""* afe_top {variant}: frozen phase {phase}, noise
{head()}.include {BIAS}
{dut}
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
{BIAS_LINES}VCHOP CHOP 0 {chop}
VCHOPO CHOP_OUT 0 {chop}
VBLK CHOP_BLANK 0 0
VEN CHOP_EN 0 {en}
VAR AFE_RST 0 0
VSRC SRC 0 DC 0 AC 1
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 -0.5
{rwe}RSP {sp} ELP {rs:g} noisy=0
RSN {sn} ELN {rs:g} noisy=0
RLOADP OUTP CM {RIN:g} noisy=0
RLOADN OUTN CM {RIN:g} noisy=0
{xline()}
.nodeset v(xdut.inp)=1.65 v(xdut.inn)=1.65 v(xdut.opi)=1.65 v(xdut.oni)=1.65 v(outp)=1.65 v(outn)=1.65
.control
set noaskquit
op
print i(vdd) v(xdut.opi) v(xdut.oni) v(xdut.inp) v(xdut.inn) v(vbn) v(xdut.vbp) v(cia) v(cib) v(cda) v(cdb)
ac dec 20 0.1 1e7
let hr = real(v(outp) - v(outn))
let hi = imag(v(outp) - v(outn))
wrdata ac.csv hr hi
noise v(outp, outn) VSRC dec 20 0.1 1e7 1
setplot noise1
set filetype=ascii
write noise.raw
quit
.endc
.end
"""


def tran_deck(variant, vin_mv, rs=100.0, tstop=200e-6, blank=BLANK, sine_mv=0.0, dac=None):
    chop = f"PULSE(0 3.3 {TCH / 2:.6e} 0.5n 0.5n {TCH / 2 - 0.5e-9:.6e} {TCH:.6e})"
    bl = f"PULSE(0 3.3 {TCH / 2 - MCLK:.6e} 0.5n 0.5n {MCLK + blank - 0.5e-9:.6e} {TCH / 2:.6e})"
    return f"""* afe_top {variant}: chopped transient, {vin_mv:+g} mV
{head()}{dut_text(variant)}
.temp 27
.options sparse reltol=1e-5 vntol=1e-8 abstol=1e-12 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
VBN VBN 0 0.8485
VBCM VBCM 0 0.82
IBLP BLP 0 125u
IBLN VDD BLN 125u
VCHOP CHOP 0 {chop}
VCHOPO CHOP_OUT 0 {chop}
VBLK CHOP_BLANK 0 {bl}
VEN CHOP_EN 0 3.3
VAR AFE_RST 0 PWL(0 3.3 10u 3.3 11u 0)
VSRC SRC 0 DC {vin_mv * 1e-3:.6g}{f' SIN({vin_mv * 1e-3:.6g} {sine_mv * 1e-3:.9e} {FCH / 64:g} {SINE_T0:g})' if sine_mv else ''}
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 -0.5
RSP SRC_P ELP {rs:g}
RSN SRC_N ELN {rs:g}
RLOADP OUTP CM {RIN:g}
RLOADN OUTN CM {RIN:g}
{xline(dac=dac)}
.nodeset v(xdut.inp)=1.65 v(xdut.inn)=1.65 v(xdut.opi)=1.65 v(xdut.oni)=1.65 v(outp)=1.65 v(outn)=1.65
.control
set noaskquit
tran 4n {tstop:.6e} 0 4n
let vo = v(outp) - v(outn)
let va = v(xdut.opi) - v(xdut.oni)
let vw = v(xdut.wp) - v(xdut.wn)
wrdata tr.csv vo va v(cda) v(cdb) vw i(vdd)
quit
.endc
.end
"""


def run(d, deck):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    return log, time.time() - t


def noise_one(variant, phase, rin=None):
    d = os.path.join(RUNS, f"noise_{variant}_{phase}" + ("_rwire" if rin else ""))
    log, dt = run(d, noise_deck(variant, phase, rin=rin))
    v = {k: float(x) for k, x in re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}
    ac = np.loadtxt(os.path.join(d, "ac.csv"))
    f, h = ac[:, 0], ac[:, 1] + 1j * ac[:, 3]
    nz = afe_noise.read_raw(os.path.join(d, "noise.raw"))
    fn = nz["frequency"]
    tot = nz["onoise_spectrum"] ** 2
    fl = sum((s ** 2 for n, s in nz.items() if n.endswith("1overf")), np.zeros_like(fn))
    kmax = int(fn[-1] / FCH) - 1
    g = abs(afe_noise.chop_sum(f, h.real, kmax, FCH))
    bw = BAND[1] - BAND[0]
    ntot = np.sqrt(afe_noise.chop_sum(fn, tot, kmax, FCH) * bw) / g
    nfl = np.sqrt(afe_noise.chop_sum(fn, fl, kmax, FCH) * bw) / g
    sel = (fn >= 10) & (fn <= 100)
    habs2 = np.abs(np.interp(fn, f, h.real) + 1j * np.interp(fn, f, h.imag)) ** 2
    frozen = np.sqrt(np.mean(tot[sel] / habs2[sel]) * bw)
    return dict(variant=variant + ("+R" if rin else ""), phase=phase, t=dt, idd=-v.get("i(vdd)", np.nan) * 1e3, gain=g,
                gain10=np.sqrt(np.interp(10, fn, habs2)), total=ntot * 1e9, flicker=nfl * 1e9,
                thermal=np.sqrt(max(ntot ** 2 - nfl ** 2, 0)) * 1e9, frozen=frozen * 1e9,
                vinp=v.get("v(xdut.inp)", np.nan), vopi=v.get("v(xdut.opi)", np.nan))


SINE_T0 = 20e-6       # the sine starts after the reset (released at 11 us) with zero input
SINE_FFT0 = 2.0e-3    # FFT window start: 7 x the DC path's 286 us after the start


def sine_one(variant, sine_mv=0.943):
    """Full-scale sine at fch/64 (2 kHz), starting at 20 us (after the INP/INN reset, so
    that Cin keeps no input charge: the start-up effect of the AFE document); the output
    integrated over every chopper period, HD2..HD5 from an FFT over 4 signal periods from
    2 ms (coherent, rectangular window). (afe_offset.py --sine starts the FFT at 0.5 ms; in
    this bench the DC path (286 us) still settles there, after the reset and, in pex, from
    the offset of the DC-path switch coupling, and its leakage covered the harmonics at
    -89 to -93 dBc.)"""
    d = os.path.join(RUNS, f"sine_{variant}_{sine_mv:g}mV")
    tstop = SINE_FFT0 + 4 * 64 * TCH
    log, dt = run(d, tran_deck(variant, 0.0, tstop=tstop, sine_mv=sine_mv))
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, vo = x[:, 0], x[:, 1]
    q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
    edges = SINE_FFT0 + TCH * np.arange(64 * 4 + 1)
    per = np.diff(np.interp(edges, t, q)) / TCH
    spec = np.abs(np.fft.rfft(per - per.mean())) / (len(per) / 2)
    h = [spec[4 * k] for k in range(1, 6)]
    return dict(variant=variant, t=dt, gain=h[0] / (sine_mv * 1e-3), hd=[20 * np.log10(v / h[0]) for v in h[1:]])


def tran_one(variant, vin_mv, tstop=200e-6, dac_range=0, blank_mclk=7):
    dac = (vin_mv, dac_range) if dac_range else None
    d = os.path.join(RUNS, f"tran_{variant}_{vin_mv:+g}mV" + (f"_r{dac_range}_bl{blank_mclk}" if dac else ""))
    log, dt = run(d, tran_deck(variant, vin_mv, tstop=tstop, blank=blank_mclk * MCLK, dac=dac))
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, vo, va, cda, cdb, vw, idd = x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7], x[:, 9], x[:, 11]
    m = (t >= 100e-6) & (t <= tstop)
    avg = trapz(vo[m], t[m]) / (t[m][-1] - t[m][0])
    held = m & ((cda > 1.65) | (cdb > 1.65))
    pp = vo[held].max() - vo[held].min()
    return dict(variant=variant, vin=vin_mv, t=dt, avg=avg, pp=pp, vamax=np.abs(va[m]).max(),
                idd=-trapz(idd[m], t[m]) / (t[m][-1] - t[m][0]) * 1e3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["noise", "tran", "sine"])
    ap.add_argument("--variants", nargs="+", default=["sch", "dev", "pex"])
    ap.add_argument("--phase", nargs="+", default=["A", "B"])
    ap.add_argument("--vin", nargs="+", type=float, default=[0.0, 0.5, -0.5])
    ap.add_argument("--tstop", type=float, default=200e-6)
    ap.add_argument("--rwire", action="store_true", help="noise: the extracted wiring resistance in series (RIN_EXTRACTED)")
    ap.add_argument("--dac", type=int, default=0, help="tran: offset-DAC range 1..4 set for the input (0: off)")
    ap.add_argument("--blank", type=int, default=7, help="tran: output-chopper blanking in MCLK")
    a = ap.parse_args()
    if a.what == "noise":
        jobs = [(v, p, RIN_EXTRACTED if a.rwire else None) for v in a.variants for p in a.phase]
        print("| DUT | phase | IDD (mA) | gain 10 Hz (frozen) | chopped gain | chopped total (nVrms) | thermal | 1/f "
              "| run (s) |")
        print("|---|---|---|---|---|---|---|---|---|")
        with ThreadPoolExecutor(len(jobs)) as ex:
            for r in ex.map(lambda j: noise_one(*j), jobs):
                print(f"| {r['variant']} | {r['phase']} | {r['idd']:.3f} | {r['gain10']:.2f} | {r['gain']:.2f} | "
                      f"{r['total']:.3f} | {r['thermal']:.3f} | {r['flicker']:.3f} | {r['t']:.0f} |",
                      flush=True)
    elif a.what == "sine":
        print("| DUT | gain at 2 kHz | HD2 (dBc) | HD3 (dBc) | HD4 (dBc) | HD5 (dBc) | run (s) |")
        print("|---|---|---|---|---|---|---|")
        with ThreadPoolExecutor(len(a.variants)) as ex:
            for r in ex.map(sine_one, a.variants):
                print(f"| {r['variant']} | {r['gain']:.2f} | " + " | ".join(f"{h:.1f}" for h in r["hd"]) + f" | {r['t']:.0f} |",
                      flush=True)
    else:
        jobs = [(v, x) for v in a.variants for x in a.vin]
        res = {}
        with ThreadPoolExecutor(len(jobs)) as ex:
            for r in ex.map(lambda j: tran_one(*j, a.tstop, a.dac, a.blank), jobs):
                res[(r["variant"], r["vin"])] = r
                print(f"{r['variant']} {r['vin']:+g} mV: avg {r['avg'] * 1e3:+.4f} mV, p-p outside blanking "
                      f"{r['pp'] * 1e3:.2f} mV, max |OPI-ONI| {r['vamax']:.3f} V, IDD {r['idd']:.3f} mA ({r['t']:.0f} s)",
                      flush=True)
        print("| DUT | gain (+-0.5 mV) | output offset (mV) | input-referred offset (uV) | ripple p-p (mV) |")
        print("|---|---|---|---|---|")
        for v in a.variants:
            if (v, 0.5) in res and (v, -0.5) in res:
                g = (res[(v, 0.5)]["avg"] - res[(v, -0.5)]["avg"]) / 1e-3
                z = res.get((v, 0.0))
                print(f"| {v} | {g:.2f} | {z['avg'] * 1e3:+.3f} | {z['avg'] / g * 1e6:+.3f} | {z['pp'] * 1e3:.2f} |"
                      if z else f"| {v} | {g:.2f} | | | |")


if __name__ == "__main__":
    main()
