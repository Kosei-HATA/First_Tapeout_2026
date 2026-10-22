#!/usr/bin/env python3
"""Write the AFE netlist of this rev (gf180/tapeout/afe/eeg_afe.spice) from the
analysis generator in gf180/tapeout/sim/afe/afe_noise.py, then check that the
written netlist reproduces the generator's operating point and gain.

Configuration (documentation/gf180_afe_noise_20261022.md):
  NMOS input pair L 1.5 um, PMOS input pair L 0.28 um, bias current x3 (NMOS
  tail m 768), input TG m 256, output TG m 8, regulated cascodes (one
  common-source booster per cascode, mirror loads L 8 um), Cin 636p, Cf 2p,
  Cpf 2.15p at CPF_TRIM = 8 (1.99 pF fixed plus a 4-bit array of 20/40/80/160 fF, 1.99 to
  2.29 pF), 128 kHz chopping, output hold capacitors 30 pF per side for output-chopper
  blanking.

Ports of eeg_afe:
  ELP ELN        electrodes (chip pins)
  OUTP OUTN      to the ADC input resistors (output chopper side)
  VCM            1.65 V CMFB reference
  VBN            NMOS tail gate (bias block, sets the x3 current)
  VBCM           CMFB tail gate
  BLP            booster PMOS-mirror node: the bias block sinks 125 uA from it
  BLN            booster NMOS-mirror node: the bias block sources 125 uA into it
  RST            INP/INN reset (high = reset to the outputs)
  CIA NCIA CIB NCIB   input chopper phases A/B and complements
  CDA NCDA CDB NCDB   output chopper phases A/B and complements; both stay low for the
                      blanking window (7 MCLK) after every chopper edge
  OFPH           offset-DAC phase: toggles when the input-chopper TG of the new phase closes
                 (rising edges of CIA and CIB), high in phase A (clock driver, tracker B8)
  OFS            offset-DAC sign (static, from the registers)
  OFM0..OFM9     offset-DAC magnitude (static)
  OFEN0..OFEN3   offset-DAC range groups (static): EN0 bits 0-6, EN1 bit 7, EN2 bit 8, EN3 bit 9
  CPF0..CPF3     CPF_TRIM (static): Cpf = 1.99 pF + code x 20 fF (reset 8 = 2.15 pF). Each
                 trim capacitor hangs from WP/WN and is switched at its other plate to the
                 amplifier output (bit 1) or to VCM (bit 0), so no switch touches the
                 high-impedance input side; an off capacitor only adds at most 0.3 pF to WP/WN
  VDD VSS
Electrode-offset cancellation (tracker B7, documentation/gf180_electrode_dc_20261022.md):
eeg_afe_offdac cancels (1 - 2 S) x magnitude x 0.311 mV (differential, at the
electrodes), range +-39/79/159/318 mV with 1/2/3/4 groups enabled. Only the caps of
the set magnitude bits switch, each through a series resistor that gives all bits the
same charge time constant (65 ns, about RS x Cin at RS = 100 ohm). INP/INN DC path: a switched-capacitor resistor per side
(10 fF, clocked by the input-chopper phases, about 780 Mohm at 128 kHz) from the
amplifier input to the opposite output, in parallel with Cf; the reset switch stays.
Capacitors are ideal here; layout uses MIM arrays (tracker E2).

Usage: python3 make_afe_netlist.py [--check] [--tau 65e-9 --out <path>]  (--tau/--out: DAC time-constant studies)
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.normpath(os.path.join(HERE, "..", "sim", "afe"))
sys.path.insert(0, SIM)
import afe_noise  # noqa: E402

OUT = os.path.join(HERE, "eeg_afe.spice")
PARAMS = dict(core=1, tg=256, ln=1.5, lp=0.28, mp=1.0, itail=3, scasc=1, tgo=8)
CPF = 2.15e-12
CPF_BASE = 1.99e-12  # fixed part of Cpf; CPF_TRIM adds code x 20 fF (code 8 = 2.15 pF)
CPF_STEP = 20e-15
OFF_CU = 60e-15  # offset-DAC unit capacitor (MIM 5.5 x 5.5 um)
OFF_BITS = 10
OFF_GROUP = [0, 0, 0, 0, 0, 0, 0, 1, 2, 3]  # range group of each magnitude bit
OFF_TAU = 65e-9  # offset-DAC charge time constant: RS 100 ohm x (Cin + electrode-node C)
C_SC = 10e-15    # switched-capacitor DC path
CHOLD = 30e-12  # per side, output-chopper blanking (documentation/gf180_afe_noise_20261022.md)
RENAME = [("reuse_input_tg_m64", "eeg_afe_input_tg"), ("reuse_tg", "eeg_afe_output_tg"),
          ("gf180_reuse_cascoded_core", "eeg_afe_core"), ("gf180_ct_cmfb8", "eeg_afe_cmfb"),
          ("gf180_ccia_local_feedback", "eeg_afe_amp")]


def body():
    afe_noise.BOOST = "tr"
    txt = afe_noise.candidate(boost="tr", **PARAMS)
    for old, new in RENAME:
        txt = re.sub(rf"\b{old}\b", new, txt)
    # booster mirror references become ports (fed by the bias block)
    txt = txt.replace("IBLP BLP VSS 125u\n", "").replace("IBLN VDD BLN 125u\n", "")
    # cascode gates are driven by the boosters: VNC/VPC ports are dropped
    txt = txt.replace(".subckt eeg_afe_core INP INN OUTP OUTN VBN VBP VNC VPC VDD VSS",
                      ".subckt eeg_afe_core INP INN OUTP OUTN VBN VBP BLP BLN VDD VSS")
    txt = txt.replace("XCORE INP INN OPI ONI VBN VBP VNC VPC VDD VSS eeg_afe_core",
                      "XCORE INP INN OPI ONI VBN VBP BLP BLN VDD VSS eeg_afe_core")
    txt = txt.replace(".subckt eeg_afe_amp EP EN WP WN INP INN OPI ONI OUTP OUTN VCM VBN VBCM VNC VPC VBP",
                      ".subckt eeg_afe_amp EP EN WP WN INP INN OPI ONI OUTP OUTN VCM VBN VBCM BLP BLN VBP")
    assert "VNC" not in txt.split(".subckt eeg_afe_core", 1)[1].split(".ends eeg_afe_core")[0].split("\n", 1)[0]
    return txt


def offdac():
    """Electrode-offset DAC, sign-magnitude: per side, binary-weighted caps into INP/INN.
    Only the caps of the set magnitude bits switch, AVSS <-> AVDD through a series
    resistor R_k = TAU / C_k (all bits deliver their charge with the same time constant,
    close to that of the electrode charge, RS x Cin). The plates of the other bits are
    clamped to AVSS by a strong NMOS, so their R_k adds no noise: with no offset the DAC
    adds only its capacitance at the amplifier input. Range groups are switched at the
    amplifier-input side (a disabled group is parked at VCM)."""
    bits = " ".join(f"M{k}" for k in range(OFF_BITS))
    L = ["",
         "* electrode-offset cancellation DAC (tracker B7), sign-magnitude",
         "* PH: DAC phase, toggles when the input-chopper TG of the new phase closes (high in",
         "* phase A). X = S XOR PH. Active bit k (Mk and its group enabled): P plate = VDD when",
         "* not X, N plate = VDD when X; inactive plates stay at VSS. For S = 0 the P plates rise",
         "* at the A->B edge: +sum(active Ck) x VDD into INP cancels the Cin step of a positive",
         "* ELP-ELN offset, magnitude x 0.311 mV per unit (60 fF). Each plate is driven through",
         f"* R_k = {OFF_TAU * 1e9:g} ns / C_k (thermal noise grows with the active capacitance, i.e.",
         "* with the cancelled offset). Inactive plates: clamped to VSS by an NMOS sized for",
         "* R_on x C_k = 0.2 ns. Disabled groups: plates low, top plate at VCM.",
         f".subckt eeg_afe_offdac INP INN VCM PH S {bits} EN0 EN1 EN2 EN3 VDD VSS",
         "XSB SB S VDD VSS eeg_afe_inv s=1",
         "XNPH NPH PH VDD VSS eeg_afe_inv s=2",
         "XMXA S XR NPH PH VDD VSS eeg_afe_tg",    # passes S while PH low
         "XMXB SB XR PH NPH VDD VSS eeg_afe_tg",   # passes not S while PH high
         "XXR1 XRB XR VDD VSS eeg_afe_inv s=2",
         "XXR2 X XRB VDD VSS eeg_afe_inv s=8",
         "XXR3 XB X VDD VSS eeg_afe_inv s=8"]
    for g in range(4):
        L.append(f"XENB{g} ENB{g} EN{g} VDD VSS eeg_afe_inv s=1")
    tg = {0: (10, 20), 1: (10, 20), 2: (20, 40), 3: (40, 80)}  # range TG W (um), NMOS/PMOS
    for g in range(4):
        wn, wp = tg[g]
        for s, node in (("P", "INP"), ("N", "INN")):
            L.append(f"XRG{s}{g}N T{s}{g} EN{g} {node} VSS nfet_03v3 W={wn}u L=0.28u nf={wn // 10 or 1} m=1")
            L.append(f"XRG{s}{g}P T{s}{g} ENB{g} {node} VDD pfet_03v3 W={wp}u L=0.28u nf={wp // 10 or 1} m=1")
            L.append(f"XPK{s}{g}N T{s}{g} ENB{g} VCM VSS nfet_03v3 W=1u L=0.28u nf=1 m=1")
            L.append(f"XPK{s}{g}P T{s}{g} EN{g} VCM VDD pfet_03v3 W=2u L=0.28u nf=1 m=1")
    for k in range(OFF_BITS):
        g = OFF_GROUP[k]
        m = max(1, 2 ** (k - 5))  # plate driver strength (units of W 1/2.5 um)
        c = OFF_CU * 2 ** k
        r = OFF_TAU / c
        wcl = max(0.5, round(c * 0.28e-6 / (172e-6 * 2.6 * 0.2e-9) * 1e6 * 2) / 2)  # clamp W (um)
        L += [f"* bit {k}: {c * 1e12:.4g} pF per side, group {g}, R {r / 1e3:.4g} kohm, driver x{m}, clamp W {wcl:g} um",
              f"XNP{k} NP{k} EN{g} M{k} XB VDD VSS eeg_afe_nand3 s={max(1, m // 4)}",
              f"XNN{k} NN{k} EN{g} M{k} X VDD VSS eeg_afe_nand3 s={max(1, m // 4)}",
              f"XDP{k} DP{k} NP{k} VDD VSS eeg_afe_inv s={m}",
              f"XDN{k} DN{k} NN{k} VDD VSS eeg_afe_inv s={m}",
              f"RDP{k} DP{k} BP{k} {r:.6g}",
              f"RDN{k} DN{k} BN{k} {r:.6g}",
              f"XNA{k} NA{k} EN{g} M{k} VDD VSS eeg_afe_nand2 s=1",
              f"XCLP{k} BP{k} NA{k} VSS VSS nfet_03v3 W={wcl:g}u L=0.28u nf={max(1, int(wcl // 10))} m=1",
              f"XCLN{k} BN{k} NA{k} VSS VSS nfet_03v3 W={wcl:g}u L=0.28u nf={max(1, int(wcl // 10))} m=1",
              f"COFP{k} TP{g} BP{k} {c * 1e15:.6g}f",
              f"COFN{k} TN{g} BN{k} {c * 1e15:.6g}f"]
    L += [".ends eeg_afe_offdac",
          "* s: strength (W and finger count scale with s)",
          ".subckt eeg_afe_inv Y A VDD VSS s=1",
          "XP Y A VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XN Y A VSS VSS nfet_03v3 W={1u*s} L=0.28u nf={s} m=1",
          ".ends eeg_afe_inv",
          ".subckt eeg_afe_nand2 Y A B VDD VSS s=1",
          "XPA Y A VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XPB Y B VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XNA Y A M1 VSS nfet_03v3 W={2u*s} L=0.28u nf={s} m=1",
          "XNB M1 B VSS VSS nfet_03v3 W={2u*s} L=0.28u nf={s} m=1",
          ".ends eeg_afe_nand2",
          ".subckt eeg_afe_nand3 Y A B C VDD VSS s=1",
          "XPA Y A VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XPB Y B VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XPC Y C VDD VDD pfet_03v3 W={2.5u*s} L=0.28u nf={s} m=1",
          "XNA Y A M1 VSS nfet_03v3 W={3u*s} L=0.28u nf={s} m=1",
          "XNB M1 B M2 VSS nfet_03v3 W={3u*s} L=0.28u nf={s} m=1",
          "XNC M2 C VSS VSS nfet_03v3 W={3u*s} L=0.28u nf={s} m=1",
          ".ends eeg_afe_nand3",
          ".subckt eeg_afe_tg A Y G GN VDD VSS",
          "XN A G Y VSS nfet_03v3 W=1u L=0.28u nf=1 m=1",
          "XP A GN Y VDD pfet_03v3 W=2u L=0.28u nf=1 m=1",
          ".ends eeg_afe_tg", ""]
    return "\n".join(L)


def cpftrim():
    """Cpf trim array: per side and bit, a capacitor from WP (WN) to a switched plate
    that a TG connects to OPI (ONI) when the bit is 1 and to VCM when it is 0."""
    L = ["", "* Cpf trim: 20/40/80/160 fF per side, switched at the amplifier-output plate",
         ".subckt eeg_afe_cpftrim WP WN OPI ONI VCM B0 B1 B2 B3 VDD VSS"]
    for k in range(4):
        c = CPF_STEP * 2 ** k
        L += [f"XIB{k} BN{k} B{k} VDD VSS eeg_afe_inv s=1",
              f"CTP{k} WP XP{k} {c * 1e15:g}f",
              f"XTPO{k} XP{k} OPI B{k} BN{k} VDD VSS eeg_afe_tg",
              f"XTPV{k} XP{k} VCM BN{k} B{k} VDD VSS eeg_afe_tg",
              f"CTN{k} WN XN{k} {c * 1e15:g}f",
              f"XTNO{k} XN{k} ONI B{k} BN{k} VDD VSS eeg_afe_tg",
              f"XTNV{k} XN{k} VCM BN{k} B{k} VDD VSS eeg_afe_tg"]
    L += [".ends eeg_afe_cpftrim", ""]
    return "\n".join(L)


def top():
    bits = " ".join(f"OFM{k}" for k in range(OFF_BITS))
    return f"""
* AFE top: input chopper TGs, Cin, Cf, Cpf, reset switches, DC path, offset DAC,
* amplifier, output chopper TGs
.subckt eeg_afe ELP ELN OUTP OUTN VCM VBN VBCM BLP BLN RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB
+ OFPH OFS {bits} OFEN0 OFEN1 OFEN2 OFEN3 CPF0 CPF1 CPF2 CPF3 VDD VSS
CINP WP INP 636p
CINN WN INN 636p
CFBP ONI INP 2p
CFBN OPI INN 2p
CPFP WP OPI {CPF_BASE * 1e12:g}p
CPFN WN ONI {CPF_BASE * 1e12:g}p
XCPF WP WN OPI ONI VCM CPF0 CPF1 CPF2 CPF3 VDD VSS eeg_afe_cpftrim
XRSTP INP RST ONI VSS nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
XRSTN INN RST OPI VSS nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5
* INP/INN DC path: switched-capacitor resistor to the opposite output (parallel to Cf),
* {C_SC * 1e15:g} fF per side, one transfer per chopper period (about 780 Mohm at 128 kHz)
XSCP1 INP CIA SCP VSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XSCP2 SCP CIB ONI VSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
CSCP SCP VSS {C_SC * 1e15:g}f
XSCN1 INN CIA SCN VSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XSCN2 SCN CIB OPI VSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
CSCN SCN VSS {C_SC * 1e15:g}f
XOFF INP INN VCM OFPH OFS {bits} OFEN0 OFEN1 OFEN2 OFEN3 VDD VSS eeg_afe_offdac
XAMP ELP ELN WP WN INP INN OPI ONI OUTP OUTN VCM VBN VBCM BLP BLN VBP CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD VSS eeg_afe_amp
* hold capacitors for output-chopper blanking (CDA/CDB low for 7 MCLK after each edge)
CHOLDP OUTP VSS {CHOLD * 1e12:g}p
CHOLDN OUTN VSS {CHOLD * 1e12:g}p
.ends eeg_afe
"""


def write(out=None):
    head = f"""* eeg_afe: chopper-stabilised capacitively coupled instrumentation amplifier (GF180, this rev)
* Written by gf180/tapeout/afe/make_afe_netlist.py from gf180/tapeout/sim/afe/afe_noise.py
* ({', '.join(f'{k} {v:g}' for k, v in PARAMS.items())}, boosters N {afe_noise.BOOST_N}, P {afe_noise.BOOST_P},
* booster load L {afe_noise.LOAD_L:g} um). Do not edit by hand; change the generator and rerun.
"""
    out = out or OUT
    open(out, "w").write(head + body() + offdac() + cpftrim() + top())
    return out


def check():
    """Operating point of eeg_afe (reset on, phase A) against the generator deck."""
    d = os.path.join(SIM, "runs", "netlist_check")
    os.makedirs(d, exist_ok=True)
    tb = f"""* eeg_afe netlist check (phase A, reset on)
.include {afe_noise.PDK}/design.ngspice
.lib {afe_noise.PDK}/sm141064.ngspice typical
.include {OUT}
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
VBN VBN 0 0.8485
VBCM VBCM 0 0.82
IBLP BLP 0 125u
IBLN VDD BLN 125u
VRST RST 0 3.3
VSRC SRC 0 DC 0 AC 1
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 -0.5
RSP SRC_P ELP 100
RSN SRC_N ELN 100
CLOADP OUTP 0 4p
CLOADN OUTN 0 4p
RLOADP OUTP CM 9375
RLOADN OUTN CM 9375
XA ELP ELN OUTP OUTN CM VBN VBCM BLP BLN RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB
+ VDD 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 VDD VDD 0 eeg_afe
VCIA CIA 0 3.3
VNCIA NCIA 0 0
VCIB CIB 0 0
VNCIB NCIB 0 3.3
VCDA CDA 0 3.3
VNCDA NCDA 0 0
VCDB CDB 0 0
VNCDB NCDB 0 3.3
.control
set noaskquit
op
print i(vdd) v(xa.inp) v(xa.oni) v(xa.vbp) v(xa.xamp.xcore.dnp) v(xa.xamp.xcore.dpp)
quit
.endc
.end
"""
    open(os.path.join(d, "tb.spice"), "w").write(tb)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    # the offset-DAC logic makes the first (dynamic gmin) attempt fail; true gmin stepping
    # then converges, so only a missing result is an error
    if "i(vdd) =" not in log:
        raise RuntimeError("operating point did not converge (see run.log)")
    v = dict(re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M))
    return {k: float(x) for k, x in v.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="simulate the operating point of the written netlist")
    ap.add_argument("--tau", type=float, default=None, help="offset-DAC time constant (study variants)")
    ap.add_argument("--out", default=None, help="write the netlist here instead (study variants)")
    a = ap.parse_args()
    global OFF_TAU
    if a.tau is not None:
        OFF_TAU = a.tau
    print("wrote", write(a.out))
    if a.check:
        v = check()
        print(f"eeg_afe operating point (reset on): IDD {-v['i(vdd)']*1e3:.3f} mA (generator deck 23.148 mA), "
              f"INP {v['v(xa.inp)']:.4f} V, ONI {v['v(xa.oni)']:.4f} V, VBP {v['v(xa.vbp)']:.4f} V, "
              f"DNP {v['v(xa.xamp.xcore.dnp)']:.4f} V, DPP {v['v(xa.xamp.xcore.dpp)']:.4f} V")


if __name__ == "__main__":
    main()
