#!/usr/bin/env python3
"""AFE start-up from power-on, as the chip sequences it: the realistic counterpart of the
pex_afe.py transients, which start from a solved operating point with ideal bias.

  - Supplies: AVDD and DVDD each from a regulator that ramps 0 -> --vdd in --tramp, behind
    BOARD (output resistance, 10 uF bulk and 100 nF next to the chip, with ESR / ESL) and the
    chip-on-board bond wires (R, L each, L damped by r_damp), one per bonded pad. Every node
    starts at 0 V (uic). The chip's AVSS and DVSS are their own nodes, not the simulator's
    ground.
  - The chip-level wiring: chipnets (pex_chipnets.py, runs/chipnets/README.md: the filled chip,
    typical metal resistance). It has the 13 bonded analog pads (AVDD x3, AVSS x3, ELP x2, ELN x2,
    VCM, VREFP, VREFN: the pad cell's metal, 1.27 ohm, its ESD diodes and bar capacitance), the
    AVDD / AVSS grid with the 75 decoupling units, and the routes between the blocks (bias lines,
    VCM, the electrode straps, OUTP / OUTN, the references) with their capacitance and their
    couplings to the switching nets. Each block sits on its own pins: afe_top on AVDD_AFE /
    AVSS_AFE behind --rafe (its own rails to the tails, pex_chipnets' estimate), eeg_bias on
    AVDD_BIAS / AVSS_BIAS, so the AFE's tails see VBN against the bias block's AVSS.
  - Pads: besides, every asig_5p0 cell of the ring (47) from the PDK's IO netlist
    (gf180mcu_fd_io.spice) with its pad open, for its share of the ring (clamp diode, 17.6 pF
    ring capacitor), 8 dvdd and 8 dvss cells (the ring's ESD clamps) and 4 corners, on the
    ring nets DVDDC / DVSSC (the cells' core pins VDD / VSS on the same ring: the chip has no
    separate core-supply pads) with chip_lay.decaps()' 48 units DVDD-DVSS. The 9 digital
    bi_24t pads are left out.
  - The external reference (VREFP 1.9 V, VREFN 1.4 V, assumed to power up with AVDD) on the
    board with 1 uF each, through its bond wire and pad into eeg_ref (extracted); the ADC's
    reference load (DAC1 and the quantizer ladder, 27.2 uA) is a resistor between its VREFP /
    VREFN pins.
  - The bias block eeg_bias extracted (beta multiplier with its start-up branch, MOS-capacitor
    filters), its trims at their register reset values (AFE_IBIAS code 2 = 8 units, boosters 4
    units) until the firmware writes AFE_IBIAS (--ibias, --t-write after RESET_N; code 3 = 10
    units makes up for the AFE's ground sitting above the bias block's). Its VCM divider (2 x 100 kohm from VREFP / VREFN) charges the off-chip capacitor
    --cvcm on the board through the VCM pad.
  - afe_top extracted (pex: the layout's devices and every extracted capacitance) with the
    signal path's wiring resistance (pex_afe.RIN_EXTRACTED: W and T inside; of E, the chopper's
    part between the chip wiring's electrode pins and the AFE) and the chip wiring's couplings
    to its inner nets.
  - The RTL's sequence (gf180/tapeout/rtl/README.md), its outputs swinging between DVSS and
    DVDD on the chip: while RESET_N is low the choppers are idle (CHOP = CHOP_OUT =
    CHOP_BLANK = 0) and AFE_RST = CHOP_EN = 1. RESET_N is released at --t-reset: CHOP and
    CHOP_OUT start at 128 kHz at that edge (CHOP_DLY 0), CHOP_BLANK covers 1 MCLK before to
    7 MCLK after each later CHOP_OUT edge (15 MCLK with the offset DAC on). Software clears
    AFE_RST at --t-afe (a Monte Carlo run adds a random fraction of a chopper period, so the
    release falls at any phase).
  - The ADC as its input resistors (18.75 kohm per side) into a virtual ground that follows
    its VCM pin (the ADC integrator's common-mode loop) and its supply current (--iadc,
    between its AVDD and AVSS pins, ramping with the supplies); noiseless.
  - The electrodes: a differential source (0, or --vin mV with the offset DAC set for it,
    pex_afe.xline) on the board's VCM (the body on the reference electrode) through 100 ohm
    per leg and one bond wire per electrode pad.
Output (tr.csv, on a 100 ns grid by linearize): qo and qa, the running integrals of OUTP - OUTN
and of the amplifier output OPI - ONI (chopper-period means are exact differences of
them), and the saved node voltages and supply currents; run.log prints vamax, the largest
|OPI - ONI|.
Remaining simplifications: the board values are assumptions (no board yet); afe_top's own
supply rails are a lumped estimate (--rafe) and the blocks' extractions have no resistance
inside them (runs/chipnets/README.md, "Left out"); the ADC is its input resistors, reference
load and supply current only; the test multiplexer is not modeled (its pins of the chip
wiring are left open); the digital block draws no supply current and its pads are missing;
the MOS capacitors are the linear stand-ins of moscap_lin.spice unless --moscap pdk (a run
with them at 0.3 x moved no bias settling time with the 1 ms ramp); the MIM and
poly-resistor mismatch coefficients are stand-ins (the PDK has no local model for them:
--mim-a, --res-a); no noise.

Variation: --corner typical | ss | ff | fs | sf (MOS, with the matching resistor, MIM, diode
and MOS-capacitor corners), --vdd, --mc SEED: the PDK's statistical section (global process
and per-device mismatch: sw_stat_global = sw_stat_mismatch = 1, .options seed = SEED,
reproducible). The PDK's mismatch wrappers (fets_mm) scale the mismatch with par, not with
the multiplier M, so every transistor with M = k gets par = k.

Modes:
  power  the AFE held in reset with the choppers idle (RESET_N low) from power-on to --tstop:
         the bias start-up and the VCM charging, with the AFE as their load
  start  the full sequence: RESET_N at --t-reset (default --t-afe - 0.2 ms), AFE_RST released
         at --t-afe, to --tstop (default --t-afe + 3 ms)

--variant sch runs the schematics instead (pre-layout: afe_top, eeg_bias and eeg_ref as drawn,
without afe_top's signal-path and rail resistances) on the same chip wiring, so that the two
differ only in the blocks' extraction (the ideal wiring of chip_model's sch, resistances x 1e-4
and no capacitance, left the bond wires undamped by the chip: the run stopped on a 1e-19 s step
62.5 us after the choppers started). On the extracted wiring the sch deck stops on a 1e-19 s
step at the end of the supply ramp; 1 fF from every node to ground (.options cshunt; the
extraction's parasitics give the pex netlists theirs), the gear integration and reltol 1e-4 (1e-5
for pex) get it past the ramp (all three are needed), but it still stops at 1.33 ms (brst#branch,
10/28): the sch variant does not run through on this bench. --sine A adds a sine of A mV pk at
--fsig from 20 us after the AFE release.

Usage: python3 afe_startup.py power --cvcm 100n [--tstop 0.1]
       python3 afe_startup.py start --cvcm 10n --t-afe 5e-3 [--vdd 3.3] [--corner ss] [--mc 1]
       python3 afe_startup.py start --cvcm 10n --sine 0.943 [--variant sch]
       (several --cvcm / --mc values run in parallel)
"""
import argparse
import copy
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pex_afe as P  # noqa: E402  (DUT text, offset-DAC instance line, PDK path)

REF = os.path.join(P.REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")
REF_PEX = os.path.join(HERE, "runs", "eeg_ref_c", "eeg_ref_pex.spice")          # pex_chipnets.py blocks
BIAS_PEX = os.path.join(HERE, "runs", "eeg_bias_c", "eeg_bias_pex.spice")
_REV = os.environ.get("EEG_PEX_REV", "")              # pex.py: the extraction of a changed layout
CHIPNETS = os.path.join(HERE, "runs", "chipnets" + (f"_{_REV}" if _REV else ""))
IO = os.path.normpath(os.path.join(P.PDK, "..", "..", "libs.ref", "gf180mcu_fd_io", "spice", "gf180mcu_fd_io.spice"))
RUNS = os.path.join(HERE, "runs", "startup")
MOSF = {"typical": 1.0, "ff": 0.9, "ss": 1.1, "fs": 1.0, "sf": 1.0}
FETS = {"nfet_03v3", "pfet_03v3", "nfet_05v0", "pfet_05v0", "nfet_06v0", "pfet_06v0", "nfet_06v0_nvt"}
# board and package, assumed (no board yet): regulator output resistance, bulk and local
# decoupling per supply with their ESR / ESL, one chip-on-board bond wire (R, L, and r_damp across
# L: its high-frequency loss. Undamped, or with 500 ohm or more, ngspice aborts at a chopper edge
# ("timestep too small" at the wire's node); 20 and 100 ohm give the same chopper-period means
# to 0.002 uV)
BOARD = dict(r_ldo=0.05, c_bulk=10e-6, esr_bulk=0.02, c_hf=100e-9, esr_hf=0.01, esl_hf=0.5e-9,
             c_ref=1e-6, r_bw=0.1, l_bw=2e-9, r_damp=20.0)
PADS = {"AVDD": (0, 7, 12), "AVSS": (1, 6, 13), "ELP": (2, 3), "ELN": (4, 5)}         # bonded pads (chipnets' _P<k>)
N_ASIG, N_DVDD, N_DVSS, N_COR = 47, 8, 8, 4                                           # the ring (pad_geometry.json)
DECAP_D = 48                                                                            # chip_lay.decaps() units, DVDD
STRAP_RIN = (0.039, 0.059)    # the pad straps' share of RIN_EXTRACTED's E (pex_chipnets.STRAP_RIN): chipnets has them
RAFE = (0.746, 0.123)         # afe_top's own AVSS / AVDD rails, east pins -> tails (pex_chipnets afegrid, lumped)
IADC = 4.7e-3                 # ADC supply current (pex_chipnets smoke)
# afe_top's ports on the chip wiring's pins (the rest as pex_afe.xline joins them)
CHIP_PORT = {"VCM": "VCM_AFE", "VCM_N": "VCMN_AFE", "VCM_P": "VCMP_AFE", "AVDD": "AVDD_AFEI", "AVSS": "AVSS_AFEI",
             "OUTP": "OUTP_AFE", "OUTN": "OUTN_AFE", "VBN": "VBN_AFE", "VBCM": "VBCM_AFE", "BLP": "BLP_AFE",
             "BLN": "BLN_AFE"}
SAVE = ("v(avdd_afei) v(avss_afei) v(avdd_bias) v(avss_bias) v(dvddc) v(dvssc) v(vcm_afe) v(vcm_p9) v(vrefp_adc) "
        "v(vrefn_adc) v(vbn_bias) v(vbn_afe) v(vbcm_afe) v(bln_afe) v(blp_afe) v(xb.gp) v(afe_rst) v(outp_adc) "
        "v(outn_adc) v(xdut.opi) v(xdut.oni) v(xdut.inp) v(xdut.inn) v(elp) v(eln) i(vavdd) i(vdvdd)")
CAP06 = """.subckt cap_nmos_06v0 1 2 c_length=1e-6 c_width=1e-6
C1 1 2 {moscap_corner*c_length*c_width*2.177e-3}
.ends cap_nmos_06v0
"""


def par_m(text):
    """par = M on every multiplied transistor: fets_mm scales the mismatch with par."""
    out = []
    for ln in text.splitlines(keepends=True):
        t = ln.split()
        if t and t[0][:1] in "Xx" and FETS & set(t) and not any(x.lower().startswith("par=") for x in t):
            m = next((x.split("=", 1)[1] for x in t if x.lower().startswith("m=")), "1")
            if m != "1":
                ln = ln.rstrip("\n") + f" par={m}\n"
        out.append(ln)
    return "".join(out)


MIM_MM = os.path.join(P.REPO, "gf180", "tapeout", "sim", "mim_mm.spice")
RES_MM = os.path.join(RUNS, "res_mm.spice")
MM_POLY = ("ppolyf_u", "ppolyf_u_1k")       # the resistor types of these netlists


def res_mm():
    """The PDK's statistical resistor section with per-instance mismatch added to MM_POLY: the
    parameters of `.lib res_statistical` (global variation), then a copy of `.lib res` in which
    each MM_POLY subcircuit draws mis_rr = agauss(0, 0.7071 res_mm_a / sqrt(par W L), 1) and
    scales its body resistance by (1 + mis_rr sw_stat_mismatch). The PDK draws no resistor
    mismatch (ppolyf_u's mis_r defaults to 0, ppolyf_u_1k has none); res_mm_a is a stand-in,
    the pair coefficient of a 180 nm poly resistor (3 %·um, Pelgrom / Boser). The body's r is
    written as a parameter expression (temper replaced by res_mm_temp, the deck's temperature;
    the voltage terms dropped, r_vc1 = r_vc2 = 0 for these types): with temper or v() in it,
    ngspice evaluates r at run time and the subcircuit's agauss draw never reached the instance
    (40 equal resistors under one seed came out identical). The body keeps its model card (its
    flicker noise). Written once into RUNS from the PDK file."""
    if os.path.exists(RES_MM) and "res_mm_temp" in open(RES_MM).read():
        return RES_MM
    lines = open(os.path.join(P.PDK, "sm141064.ngspice")).read().splitlines()
    a = lines.index(".lib res_statistical")
    b = next(i for i in range(a, len(lines)) if lines[i].startswith(".lib 'sm141064.spice' res"))
    out = ["* generated by afe_startup.res_mm() from the PDK's sm141064.ngspice (see its docstring)",
           ".param res_mm_a=0.03", ".param res_mm_temp=27"] + lines[a + 1:b]
    src = open(os.path.join(P.PDK, "sm141064.spice")).read().splitlines()
    r0, r1 = src.index(".lib res"), src.index(".endl res")
    cur = None
    for ln in src[r0 + 1:r1]:
        if ln.startswith(".subckt "):
            cur = ln.split()[1]
            if cur in MM_POLY:
                assert "r_vc1=0 " in ln + " " or "r_vc1" not in ln, ln
                ln = ln.replace("temper", "res_mm_temp")
            out.append(ln)
            if cur in MM_POLY:
                out.append(".param mis_rr='agauss(0,0.7071*res_mm_a*1e-6/sqrt(par*r_length*r_width),1)'")
            continue
        if cur in MM_POLY and ln.startswith(".param r_vc"):
            assert ln.split("=")[1].strip() == "0", ln
        if cur in MM_POLY and ln.startswith(".param r_temp="):
            ln = ln.replace("temper", "res_mm_temp")
        if cur in MM_POLY and ln.startswith("rb "):
            k = ln.index("r='") + 3
            e = ln.index("'", k)
            ln = ln[:k] + "r_temp*r_n*r_rsh0*(1+mis_rr*sw_stat_mismatch)" + ln[e:]
        out.append(ln)
    out.append(f".lib {P.PDK}/sm141064.spice efuse")
    os.makedirs(RUNS, exist_ok=True)
    open(RES_MM, "w").write("\n".join(out) + "\n")
    return RES_MM


def head(corner, seed, moscap, mim_a=1.41, res_a=3.0, temp=27.0):
    """Model libraries. A Monte Carlo run (seed) takes the PDK's statistical sections for the
    MOSFETs, resistors (res_mm: with mismatch) and MIM capacitors (global), and mim_mm.spice for
    the MIM capacitors' per-instance mismatch (pair coefficient mim_a %·um, a stand-in: the PDK
    has none); res_a is the resistors' pair coefficient (%·um), temp the deck's temperature (the
    resistors' temperature coefficient in res_mm)."""
    res = {"ss": "res_ss", "ff": "res_ff"}.get(corner, "res_typical")
    mim = {"ss": "mimcap_ss", "ff": "mimcap_ff"}.get(corner, "mimcap_typical")
    dio = {"ss": "diode_ss", "ff": "diode_ff"}.get(corner, "diode_typical")
    h = f".include {P.PDK}/design.ngspice\n"
    if seed is not None:
        h += (f".param sw_stat_global=1\n.param sw_stat_mismatch=1\n.options seed={seed}\n"
              f".lib {P.PDK}/sm141064.ngspice statistical\n.include {res_mm()}\n"
              f".lib {P.PDK}/sm141064.ngspice mimcap_statistical\n.include {MIM_MM}\n"
              f".param mim_mm_a2p0={mim_a / 100:g}\n.param res_mm_a={res_a / 100:g}\n.param res_mm_temp={temp:g}\n"
              f".lib {P.PDK}/sm141064.ngspice {dio}\n")
    else:
        h += (f".lib {P.PDK}/sm141064.ngspice {corner}\n"
              f".lib {P.PDK}/sm141064.ngspice {res}\n.lib {P.PDK}/sm141064.ngspice {mim}\n"
              f".lib {P.PDK}/sm141064.ngspice cap_mim\n.lib {P.PDK}/sm141064.ngspice {dio}\n")
    if moscap == "pdk":
        mc = {"ss": "moscap_ss", "ff": "moscap_ff"}.get(corner, "moscap_typical")
        return h + f".lib {P.PDK}/sm141064.ngspice {mc}\n"
    return h + f".param moscap_corner={MOSF[corner]}\n.include {P.MOSLIN}\n" + CAP06


def dut(variant, mc, chip):
    """afe_top: pex with the signal path's wiring resistance and the chip wiring's couplings to
    its inner nets, or the schematic (sch) with its files inlined, so that par = M reaches their
    transistors."""
    if variant == "pex":
        extra = os.path.join(CHIPNETS, os.path.basename(chip).replace(".spice", "_afe_extra.spice"))
        text = P.dut_text("pex", extra=open(extra).read(), rin=P.RIN_EXTRACTED)
    else:
        text = P.dut_text("sch")
        for f in P.SCH_FILES:
            text = text.replace(f".include {f}\n", open(f).read() + "\n")
    return par_m(text) if mc else text


def chip_model(variant, kind):
    """The chip wiring: chipnets (kind: fill, nofill, highr) for pex; for sch the same nets made
    ideal (resistances x 1e-4, capacitors removed: the pads' ESD diodes and the decoupling stay),
    the common-ground reference of afe_chip_noise.py (deck() puts both of its variants on pex's)."""
    src = os.path.join(CHIPNETS, "chipnets.spice" if kind == "fill" else f"chipnets_{kind}.spice")
    if variant == "pex":
        return src
    dst = os.path.join(RUNS, "chipnets_ideal.spice")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        out = [f"* generated by afe_startup.chip_model() from {os.path.basename(src)}: R x 1e-4, no C"]
        for ln in open(src).read().splitlines():
            t = ln.split()
            if t and t[0][:1] in "Cc":
                continue
            if t and t[0][:1] in "Rr" and len(t) == 4:
                ln = f"{t[0]} {t[1]} {t[2]} {float(t[3]) * 1e-4:.6g}"
            out.append(ln)
        os.makedirs(RUNS, exist_ok=True)
        open(dst, "w").write("\n".join(out) + "\n")
    return dst


def chip_line(model):
    """XCHIP on the deck's nodes: the ports keep their names, the pad ring is DVDDC / DVSSC."""
    txt = open(model).read()
    head_ = txt[txt.index(".subckt chipnets "):]
    ports = []
    for k, ln in enumerate(head_.splitlines()):
        if k and not ln.startswith("+"):
            break
        ports += ln.lstrip("+").split()[2 if k == 0 else 0:]
    return "XCHIP " + " ".join({"DVDD": "DVDDC", "DVSS": "DVSSC"}.get(p, p) for p in ports) + " chipnets\n"


def dut_line(dac):
    """pex_afe.xline on the chip wiring's afe_top pins (CHIP_PORT), the register-driven controls
    (CPF_TRIM, the offset DAC's sign, magnitude and range) between DVSSC and DVDDC."""
    toks = P.xline(dac=dac).split()
    out = [toks[0]]
    for port, tok in zip(P.ports(), toks[1:-1]):
        if port in CHIP_PORT:
            tok = CHIP_PORT[port]
        elif port.startswith(("CPF", "OFS_", "OFM", "OFEN")):
            tok = {"VDD": "DVDDC", "0": "DVSSC"}[tok]
        out.append(tok)
    return " ".join(out + [toks[-1]])


def supply(name, reg, brd, a):
    """regulator -> board decoupling for one supply"""
    b = BOARD
    return (f"V{name} {reg} 0 PWL(0 0 {a.tramp:.6e} {a.vdd})\nRLDO{name} {reg} {brd} {b['r_ldo']:g}\n"
            f"CBK{name} {brd} {brd}_bk {b['c_bulk']:g}\nRBK{name} {brd}_bk 0 {b['esr_bulk']:g}\n"
            f"CHF{name} {brd} {brd}_hf {b['c_hf']:g}\nRHF{name} {brd}_hf {brd}_hl {b['esr_hf']:g}\n"
            f"LHF{name} {brd}_hl 0 {b['esl_hf']:g}\n")


def wire(name, a_, b_, n=1):
    """n bond wires in parallel"""
    return (f"LBW{name} {a_} {name}_w {BOARD['l_bw'] / n:g}\nRDBW{name} {a_} {name}_w {BOARD['r_damp'] / n:g}\n"
            f"RBW{name} {name}_w {b_} {BOARD['r_bw'] / n:g}\n")


def board_and_pads(a, chip):
    """The board, one bond wire per bonded pad onto the chip wiring's bond pads, the chip wiring,
    and the pad ring."""
    L = [supply("AVDD", "AVDD_REG", "AVDD_BRD", a), supply("DVDD", "DVDD_REG", "DVDD_BRD", a)]
    L += [wire(f"AVDD{k}", "AVDD_BRD", f"AVDD_P{k}") for k in PADS["AVDD"]]
    L += [wire(f"AVSS{k}", "0", f"AVSS_P{k}") for k in PADS["AVSS"]]
    L.append(wire("DVDD", "DVDD_BRD", "DVDDC", N_DVDD) + wire("DVSS", "0", "DVSSC", N_DVSS))
    L.append(chip_line(chip))
    L.append(f"XDECD DVDDC DVSSC cap_nmos_03v3 c_length=28.6u c_width=44u m={DECAP_D}\n")
    # the ring: every asig_5p0 cell for its clamp and ring capacitor, its pad open (the bonded
    # pads' own paths are in the chip wiring)
    L.append("".join(f"XASIG{k} NC_PAD{k} DVDDC DVSSC DVDDC DVSSC gf180mcu_fd_io__asig_5p0\n" for k in range(1, N_ASIG + 1)))
    L.append("".join(f"XDVDD{k} DVDDC DVSSC DVSSC gf180mcu_fd_io__dvdd\n" for k in range(1, N_DVDD + 1)))
    L.append("".join(f"XDVSS{k} DVDDC DVSSC DVDDC gf180mcu_fd_io__dvss\n" for k in range(1, N_DVSS + 1)))
    L.append("".join(f"XCOR{k} DVDDC DVSSC DVDDC DVSSC gf180mcu_fd_io__cor\n" for k in range(1, N_COR + 1)))
    # the external reference and the VCM capacitor on the board, their wires to the pads
    L.append(f"VREFPX VREFP_EXT 0 PWL(0 0 {a.tramp:.6e} 1.9)\nVREFNX VREFN_EXT 0 PWL(0 0 {a.tramp:.6e} 1.4)\n"
             f"CREFP VREFP_EXT 0 {BOARD['c_ref']:g}\nCREFN VREFN_EXT 0 {BOARD['c_ref']:g}\n"
             + wire("VREFP", "VREFP_EXT", "VREFP_PAD_P10") + wire("VREFN", "VREFN_EXT", "VREFN_PAD_P11")
             + f"CVCM VCM_BRD 0 {a.cvcm:g}\n" + wire("VCM", "VCM_BRD", "VCM_P9"))
    return "".join(L)


def digital(name, node, unit):
    """a register / RTL output between the chip's DVSS and DVDD: unit is a 0..1 source node"""
    return f"B{name} {node} 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v({unit})\n"


def deck(a, mode, seed):
    mc = seed is not None
    pex = a.variant == "pex"
    chip = chip_model("pex", a.chip)       # both variants on the chip's extracted wiring (see the docstring)
    afe = dut(a.variant, mc, chip)
    bias = open(BIAS_PEX if pex else P.BIAS).read()
    bias = par_m(bias) if mc else bias
    rng = next((r for r, full in ((1, 39), (2, 79), (3, 159), (4, 318)) if abs(a.vin) <= full), 4) if a.vin else 0
    vos = a.vin if a.dac_mag is None else (1 if a.vin >= 0 else -1) * a.dac_mag * P.UNIT_MV
    blank = (15 if rng else 7) * P.MCLK
    e = [P.RIN_EXTRACTED["E"][k] - STRAP_RIN[k] for k in range(2)] if pex else (0.0, 0.0)   # the chopper's part
    rafe = a.rafe if pex else (0.0, 0.0)
    sine = f" SIN({a.vin * 1e-3:.6g} {a.sine * 1e-3:.9e} {a.fsig:g} {a.t_afe + 20e-6:.9e})" if a.sine else ""
    # AFE_IBIAS: its reset value (code 2) until the firmware writes --ibias, --t-write after RESET_N
    tw = a.t_reset + a.t_write
    trim = ""
    for b in (1, 0):
        r, n = (2 >> b) & 1, (a.ibias >> b) & 1
        if mode == "start" and r != n:
            trim += f"VUIB{b} UIB{b} 0 PWL(0 {r} {tw:.9e} {r} {tw + 2e-9:.9e} {n})\n"
    ib = {b: f"UIB{b}" if f"VUIB{b} " in trim else ("ONE" if (2 >> b) & 1 else "ZERO") for b in (1, 0)}
    if mode == "power":
        units = "VUCHOP UCHOP 0 0\nVUCHOPO UCHOPO 0 0\nVUBLK UBLK 0 0\nVURST URST 0 1\n"
        tmax = min(10e-6, a.tstop / 5000)
        tstep = tmax
    else:
        tr, tch = a.t_reset, P.TCH
        units = (f"VUCHOP UCHOP 0 PULSE(0 1 {tr:.9e} 0.5n 0.5n {tch / 2 - 0.5e-9:.9e} {tch:.9e})\n"
                 f"VUCHOPO UCHOPO 0 PULSE(0 1 {tr:.9e} 0.5n 0.5n {tch / 2 - 0.5e-9:.9e} {tch:.9e})\n"
                 f"VUBLK UBLK 0 PULSE(0 1 {tr + tch / 2 - P.MCLK:.9e} 0.5n 0.5n {P.MCLK + blank - 0.5e-9:.9e} {tch / 2:.9e})\n"
                 f"VURST URST 0 PWL(0 1 {a.t_afe:.9e} 1 {a.t_afe + 2e-9:.9e} 0)\n")
        tmax = a.tmax
        tstep = 100e-9                     # output grid; the integrals keep the chopper-period means exact
    tag = "typical" if not mc else f"mc{seed}"
    return f"""* afe_top {a.variant} from power-on: {mode}, C_VCM {a.cvcm:g} F, AVDD {a.vdd} V, {a.corner if not mc else tag}, {a.vin:+g} mV
{head(a.corner, seed, a.moscap, a.mim_a, a.res_a)}.include {REF_PEX if pex else REF}
.include {IO}
.include {chip}
{bias}
{afe}
.temp {a.temp}
.options sparse reltol={1e-5 if pex else 1e-4:g} vntol=1e-8 abstol=1e-12 bypass=0{"" if pex else " cshunt=1e-15 method=gear"}
{board_and_pads(a, chip)}RAFEVDD AVDD_AFE AVDD_AFEI {max(rafe[1], 1e-6):g}
RAFEVSS AVSS_AFEI AVSS_AFE {max(rafe[0], 1e-6):g}
XREF VREFP_PAD_REF VREFN_PAD_REF VREFP_REF VREFN_REF AVSS_REF eeg_ref
RADC VREFP_ADC VREFN_ADC 18.4k
IADC AVDD_ADC AVSS_ADC PWL(0 0 {a.tramp:.6e} {a.iadc:g})
XB VBN_BIAS VBCM_BIAS BLP_BIAS BLN_BIAS VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM_BIAS VREFP_BIAS VREFN_BIAS
+ IB1 IB0 BP1 BP0 BN1 BN0 AVDD_BIAS AVSS_BIAS eeg_bias
XDQ IQ IQ AVSS_ADC AVSS_ADC nfet_03v3 W=4u L=2u nf=1 m=8{' par=8' if mc else ''}
VITST ITST AVSS_TM 0
VONE ONE 0 1
VZERO ZERO 0 0
{trim}{digital('IB1', 'IB1', ib[1])}{digital('IB0', 'IB0', ib[0])}\
{digital('BP1', 'BP1', 'ZERO')}{digital('BP0', 'BP0', 'ONE')}\
{digital('BN1', 'BN1', 'ZERO')}{digital('BN0', 'BN0', 'ONE')}{digital('CHEN', 'CHOP_EN', 'ONE')}\
{units}{digital('CHOP', 'CHOP', 'UCHOP')}{digital('CHOPO', 'CHOP_OUT', 'UCHOPO')}{digital('BLK', 'CHOP_BLANK', 'UBLK')}\
{digital('RST', 'AFE_RST', 'URST')}VSRC SRC 0 DC {a.vin * 1e-3:.6g}{sine}
EP SRC_P VCM_BRD SRC 0 0.5
EN SRC_N VCM_BRD SRC 0 -0.5
RSP SRC_P ELP_BRD 100
RSN SRC_N ELN_BRD 100
{''.join(wire(f'{n}{k}', f'{n}_BRD', f'{n}_P{k}') for n in ('ELP', 'ELN') for k in PADS[n])}\
RECHP ELP_AFE ELP {max(e[0], 1e-3):g}
RECHN ELN_AFE ELN {max(e[1], 1e-3):g}
EVG VG AVSS_ADC VCM_ADC AVSS_ADC 1
RLOADP OUTP_ADC VG {P.RIN:g}
RLOADN OUTN_ADC VG {P.RIN:g}
{dut_line((vos, rng) if rng else None)}
.control
set noaskquit
save {SAVE}
tran {tstep:.3e} {a.tstop:.6e} 0 {tmax:.3e} uic
let qo = integ(v(outp_adc) - v(outn_adc))
let qa = integ(v(xdut.opi) - v(xdut.oni))
let vamax = vecmax(abs(v(xdut.opi) - v(xdut.oni)))
print vamax
linearize qo qa {SAVE}
wrdata tr.csv qo qa {SAVE}
quit
.endc
.end
"""


def vec_name(v):
    """the column name of a saved vector in meta.json: v(xdut.opi) -> opi, i(vavdd) -> iavdd"""
    return v[2:-1].split(".")[-1] if v.startswith("v(") else "i" + v[3:-1]


def run(a, mode, cvcm, seed):
    a = copy.copy(a)
    a.cvcm = cvcm
    if seed is not None and mode == "start":          # release at a random phase of the chopper
        a.t_afe += random.Random(seed).random() * P.TCH
    name = (("sch_" if a.variant == "sch" else "") + f"{mode}_c{cvcm:g}_v{a.vdd:g}_{a.corner if seed is None else f'mc{seed}'}"
            f"_{a.vin:+g}mV" + (f"_m{a.dac_mag}" if a.dac_mag is not None else "") +
            (f"_sine{a.sine:g}mV{a.fsig:g}Hz" if a.sine else "") +
            (f"_afe{a.t_afe0 * 1e3:g}ms" if mode == "start" else "") + ("_pdkcap" if a.moscap == "pdk" else "") +
            (f"_chip{a.chip}" if a.chip != "fill" else "") + (f"_ib{a.ibias}" if a.ibias != 2 else "") + a.tag)
    d = os.path.join(RUNS, name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(a, mode, seed))
    json.dump({k: getattr(a, k) for k in ("cvcm", "vdd", "corner", "temp", "vin", "variant", "sine", "fsig", "tramp",
                                          "t_afe", "t_reset", "tstop", "tmax", "moscap", "chip", "rafe", "iadc", "ibias",
                                          "t_write", "mim_a", "res_a", "dac_mag")}
              | {"mode": mode, "seed": seed, "vectors": ["qo", "qa"] + [vec_name(v) for v in SAVE.split()]},
              open(os.path.join(d, "meta.json"), "w"), indent=1)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    ok = os.path.exists(os.path.join(d, "tr.csv")) and "timestep too small" not in (r.stdout + r.stderr).lower()
    return name, ok, time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["power", "start"])
    ap.add_argument("--cvcm", nargs="+", default=["100n"], help="off-chip capacitance on the VCM pad")
    ap.add_argument("--vdd", type=float, default=3.3)
    ap.add_argument("--corner", default="typical", choices=list(MOSF))
    ap.add_argument("--mc", nargs="+", type=int, default=None, help="Monte Carlo seeds (process + mismatch)")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--vin", type=float, default=0.0, help="electrode DC offset (mV); the offset DAC is set for it")
    ap.add_argument("--dac-mag", type=int, default=None,
                    help="offset-DAC magnitude M instead of round(|vin| / step): the code the firmware's search settles on "
                         "when the step differs from the nominal (on-chip AVDD, extracted capacitance)")
    ap.add_argument("--variant", choices=["pex", "sch"], default="pex", help="afe_top extracted or the schematic")
    ap.add_argument("--sine", type=float, default=0.0, help="sine amplitude (mV pk) from 20 us after the AFE release")
    ap.add_argument("--fsig", type=float, default=P.FCH / 64, help="sine frequency (Hz)")
    ap.add_argument("--tramp", type=float, default=1e-3, help="supply ramp time (s)")
    ap.add_argument("--t-afe", type=float, default=5e-3, help="AFE_RST released (s)")
    ap.add_argument("--t-reset", type=float, default=None, help="RESET_N released (s); default t-afe - 0.2 ms")
    ap.add_argument("--tstop", type=float, default=None)
    ap.add_argument("--tmax", type=float, default=100e-9,
                    help="start: largest time step (10 ns moved the chopper-period means by 0.003 uV)")
    ap.add_argument("--chip", choices=["fill", "nofill", "highr"], default="fill",
                    help="chip wiring: chipnets of the filled chip, before the fill, or with high-corner metal resistance")
    ap.add_argument("--rafe", type=float, nargs=2, default=list(RAFE), metavar=("AVSS", "AVDD"),
                    help="afe_top's own rails from its pins to the tails (ohm; pex_chipnets' estimate)")
    ap.add_argument("--iadc", type=float, default=IADC, help="ADC supply current (A)")
    ap.add_argument("--ibias", type=int, default=2, choices=range(4),
                    help="AFE_IBIAS code the firmware writes after RESET_N (2: the register's reset value, no write)")
    ap.add_argument("--t-write", type=float, default=20e-6, help="start: the firmware's register write, after RESET_N (s)")
    ap.add_argument("--moscap", choices=["lin", "pdk"], default="lin")
    ap.add_argument("--mim-a", type=float, default=1.41, help="Monte Carlo: MIM mismatch, pair coefficient (%%·um; a stand-in)")
    ap.add_argument("--res-a", type=float, default=3.0, help="Monte Carlo: poly-resistor mismatch, pair coefficient (%%·um; a stand-in)")
    ap.add_argument("--tag", default="", help="suffix of the run folder")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    a.t_reset = a.t_afe - 0.2e-3 if a.t_reset is None else a.t_reset
    a.t_afe0 = a.t_afe
    if a.tstop is None:
        a.tstop = a.t_afe + 3e-3 if a.mode == "start" else 0.05
    vals = {"p": 1e-12, "n": 1e-9, "u": 1e-6}
    cv = [float(c[:-1]) * vals[c[-1]] if c[-1] in vals else float(c) for c in a.cvcm]
    jobs = [(c, s) for c in cv for s in (a.mc if a.mc else [None])]
    with ThreadPoolExecutor(min(a.jobs, len(jobs))) as ex:
        for name, ok, dt in ex.map(lambda j: run(a, a.mode, *j), jobs):
            print(f"{name}: {'ok' if ok else 'FAILED (see run.log)'} ({dt:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
