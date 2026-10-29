#!/usr/bin/env python3
"""End-to-end power-on transient of the chip (first milestone of the full E2E): electrodes ->
extracted AFE -> extracted ADC -> codes, from 0 V, with the RTL's reset sequence.

The deck is afe_startup.py's power-on bench (its board, bond wires, pad ring, chip wiring,
extracted eeg_bias / eeg_ref and afe_top, the RTL's AFE controls), with the real ADC in place
of its resistor load, so that the two benches stay consistent:
  - Board and package (afe_startup.board_and_pads): AVDD and DVDD from regulators that ramp
    0 -> --vdd in --tramp behind the board decoupling, one damped bond wire per bonded pad;
    the external reference (1.9 / 1.4 V, ramping with AVDD) and the VCM capacitor --cvcm on
    the board. Every node starts at 0 V (uic): no operating point is solved.
  - The chip wiring (afe_startup.chip_model, pex_chipnets: runs/chipnets/README.md): the 13
    bonded analog pads, the AVDD / AVSS grid with the 75 decoupling units, the routes between
    the blocks (bias lines, VCM, electrode straps, OUTP / OUTN, references) with their
    capacitance and their couplings to the switching nets; each block on its own pins
    (afe_top behind --rafe, eeg_bias, eeg_ref, the ADC on AVDD_ADC / AVSS_ADC, VCM_ADC,
    OUTP_ADC / OUTN_ADC, VREFP_ADC / VREFN_ADC); the pad ring DVDDC / DVSSC (all asig_5p0,
    dvdd, dvss and corner cells of the PDK's IO netlist, 48 DVDD decoupling units) is also
    the chip's digital supply.
  - eeg_ref and eeg_bias extracted (sch: schematics), trims at their reset values; afe_top
    extracted with the signal path's wiring resistance and the chip wiring's couplings to its
    inner nets (afe_startup.dut / dut_line); its clock driver is inside afe_top.
  - eeg_adc extracted (pex_e2e.ADC_PEX: OTAs, DAC1 with its latches and break pulse, DAC2,
    the 31-comparator quantizer, the OTA1 chopper driver, the reset switches) on its pins of
    the chip wiring, the quantizer latches on DVDDC / DVSSC; its bias lines (VBN1, VNC1, VPC1,
    VBCM1, VBPC2, VBNC2, IDP, IDN, IQ) straight from eeg_bias (not in the chip wiring).
  - The digital block as the RTL times it (gf180/tapeout/rtl/README.md), its outputs swinging
    between DVSSC and DVDDC (afe_startup.digital()), MCLK edges 0.5 ns:
      RESET_N low from power-on: CHOP = CHOP_OUT = CHOP_BLANK = CMP_STROBE = DAC_CLK = 0,
        CHOP1 = 1, AFE_RST = CHOP_EN = 1 (AFE input and both ADC integrators in reset),
        eeg_adc_dig in reset (SEL1 = SEL2 = elements 0..15), DAC1's latches undefined.
      RESET_N released at --t-reset: the 2-FF synchronizer releases ADC_RST_N two MCLK
        later and frame 0 starts at the next edge (e0): CMP_STROBE every frame at e0,
        CHOP / CHOP_OUT rise at e0 of frame 0 and toggle every 4 frames (128 kHz),
        CHOP_BLANK from 1 MCLK before to 7 MCLK after every later CHOP_OUT edge (15 with
        the offset DAC on), eeg_adc_dig leaves reset at e1, takes the code at e2 and moves
        SEL1 / SEL2 at e3 (DWA on both, the same pointer, so SEL2 = SEL1; --dac2-sel therm
        drives DAC2 with the straight code as the older E2E decks did), DAC_CLK at e4 (the
        first one defines DAC1's latches), CHOP1 at 4 kHz with its first edge at e16 of
        frame 128. RESET_N is placed 2.5 MCLK before e0 and moved later by up to 4 frames so
        that frame 0 falls on the frame and chopper grid of e2e_deck.py (e0 = T0_LOAD - 3
        MCLK + 4 k T): tr_window.py and plot_e2e.py then read out.csv as they read the E2E's.
      AFE_RST (software, CONTROL.AFE_RST) falls at the first MCLK edge from --t-afe: the
        AFE input reset and both ADC integrator resets release together; the ADC converts.
    eeg_adc_dig is the XSPICE controller of the E2E decks (quantizer.spice adc_ctrl_event:
    TH taken at DLOAD = e3 instead of e2, the same code since the comparators hold TH from
    e0 to the next strobe; popcount, DWA rotation, reset state code 15 / k 16 / pointer 0
    as the RTL); its 0 / 3.3 V outputs are scaled onto DVSSC..DVDDC.
  - Electrodes: a differential source (--vin mV DC with the offset DAC set for it, plus a
    sine of --amp mV pk at --fsig from --t-sig, default the AFE release, where the sine is
    0) on the board's VCM through 100 ohm per leg and one bond wire per electrode pad.

Solver and stages. Sparse 1.3 (--solver sparse, the default): with KLU, Newton needs 15-40
iterations per point on this deck (the board, pads and chip wiring next to the extracted
blocks; KLU refactors with its first pivot order), the power-on took hours and the first
comparator strobe stopped with "timestep too small"; with Sparse 1.3 the power-on to RESET_N
takes about a minute. One run from power-on is the default. --t-handoff T splits it: a
power-on stage (ramp/, --tol-ramp, --solver-ramp) up to T (after the supply ramp, before
frame 0, while the controller model is still in reset), then the main run from its last point
(every node voltage and inductor current, uic with .ic; the nodes held only by ideal sources
are left to them). A continued run matches an uninterrupted one to a few uV (median over the
nodes; mV only on logic nodes still switching at VDD = 0.4 V); --reuse-ramp starts again from
an earlier run's power-on stage. ngspice's .options interp is not used: in these decks it
wrote spurious values (-5e4 V on a bridge output, 350 A in the reference source).

Idealized or missing: the digital block is timed sources and the XSPICE controller (no
gate-level logic, no DVDD current of the logic, no MCLK or SPI activity, no digital pads);
the board / package values are assumptions; the chip wiring's limits (runs/chipnets/README.md:
afe_top's own rails lumped as --rafe, no resistance inside the block extractions); the ADC's
bias lines are ideal wires; the test multiplexer is absent (its pins of the chip wiring
open); the MOS capacitors are linear stand-ins (moscap_lin.spice) unless --moscap pdk; no
noise; no mismatch unless --mc.

Phases and their cost: static (power-on to RESET_N), clocked reset (RESET_N to AFE_RST: all
clocks run, integrators in reset) and converting (from the AFE release). progress.csv holds
ngspice's progress lines with the wall clock and the sampled CPU time; the summary gives CPU
s per simulated us and accepted points per us for each phase.

Outputs (runs/e2e_startup/<name>/): tb.spice, events.txt, quantizer.spice, meta.json,
run.log, progress.csv, tr.raw (binary, all accepted points of the saved vectors; a
two-stage run's from the handoff time), ramp/ (the power-on stage of a two-stage run: its
deck, log and ramp.raw with every node), out.csv (the E2E columns of e2e_deck.py on a --wstep
grid from 2 us before frame 0: sig, outp, outn (at the ADC), o1p, o1n, i1p, i1n, o2p, o2n,
norm1, i(vavdd)), frames.csv (per frame: code, DWA pointer, DAC1 level, DAC1 latches against
SEL1, O1 / O2 / AFE output at the strobe), summary.json, overview.png. --save lean keeps 25
vectors (the E2E columns, the controller's code and pointer, supplies, VCM and LATMIS, the
number of DAC1 latches that differ from SEL1, a B-source monitor) for ms-long runs: about
0.2 kB per accepted point, 1.8 GB for 5 ms of conversion, against 1 kB with the full set.

The decimator (cic): the codes from the first frame after the AFE release (the firmware's
CONTROL write clears AFE_RST and sets RUN | FILTER_CLEAR in one commit, as tb_e2e.sv does),
through the bit-exact model of eeg_cic3 (rtl/model/cic_golden.py) and through the RTL itself
(tb_e2e.sv on Icarus: TH from the codes, the samples read over SPI and checked bit-exact). The
first valid output is the third strobe, 3072 frames (3.0 ms) after the clear.

Chained runs (chain): the same deck in chunks, each an ngspice -b -r run that streams every
node to chunk.raw and restarts from the previous chunk's end state: every node voltage and
inductor current (.ic, uic), the XSPICE controller's flip-flops (code register, DWA pointer,
SEL1: their FF0 / FF1 models in the chunk's quantizer.spice), the sources seen from the chunk's
start (PULSE / SIN with the phase as a negative delay, the supplies' ramps, the reset release
and the AFE_IBIAS write as DC once they are past), the events file from the chunk's start.
Boundaries at e20 (no clock edge near) every --chunk-frames frames from --chunk-first. Each
chunk keeps chunk.json, state.json (the end state), frames.csv and lean.npz (the lean vectors);
the raw is deleted (--keep-raw keeps it). The driver logs to progress.log (a line per chunk and
every 30 min), records a failure in failure.json and stops; the same command resumes from the
last finished chunk. At the end: frames.csv of the whole run, cic and expect into cic.log.

Usage: python3 gf180/tapeout/pex/e2e_startup.py run [--cvcm 10n] [--t-reset 4.8e-3]
           [--t-afe 5e-3] [--tstop 5.05e-3] [--amp 0.943 --fsig 16e3] [--vin 0]
           [--variant pex|sch] [--chip fill] [--corner ss] [--mc 1 2] [--save lean] [--tag x]
           [--t-handoff T [--reuse-ramp]]
       python3 gf180/tapeout/pex/e2e_startup.py chain ... [--chunk-frames 100] [--bounds T1 T2 ..]
       python3 gf180/tapeout/pex/e2e_startup.py check|plot|cic|expect|status <run folder>
       python3 gf180/tapeout/pex/e2e_startup.py compare <chained run> <continuous run> --from-t T
       python3 gf180/tapeout/pex/e2e_startup.py deck ...              (write the decks only)
"""
import argparse
import copy
import json
import math
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "adc_loop"))
sys.path.insert(0, HERE)
import make_deck as md  # noqa: E402  (frame constants, quantizer.spice of the import)
import adc_deck as ad  # noqa: E402  (ADC netlists, tolerance sets)
import pex_afe as P  # noqa: E402
import pex_e2e as PE  # noqa: E402  (ADC_PEX: the extracted eeg_adc)
import afe_startup as S  # noqa: E402  (board, pads, PDK head, AFE, digital outputs)

RUNS = os.path.join(HERE, "runs", "e2e_startup")
TM = P.MCLK                      # MCLK period, 30.52 ns
T = 32 * TM                      # frame, 976.6 ns
E0_REF = md.T0_LOAD - 3 * TM     # e0 of e2e_deck.py's first frame: its frame and chopper grid
EDGE = 0.5e-9                    # digital edges
ADC_SCH = [os.path.join(ad.ADC, n) for n in ad.NETS if n != "eeg_ref.spice"]
NSEL = 31
TOLS = dict(ad.TOLS, loose="reltol=1e-3 vntol=1e-5 abstol=1e-10 chgtol=1e-14")
ONE_LSB = 1 / (NSEL * 3.3)       # NORM1 = -0.5 + k / 31 from the 0 / 3.3 V controller outputs
# the ADC's pins of the chip wiring (afe_startup / pex_chipnets node names)
E2E_VEC = ["v(sig)", "v(outp_adc)", "v(outn_adc)", "v(xadc.o1p)", "v(xadc.o1n)", "v(xadc.i1p)", "v(xadc.i1n)",
           "v(o2p)", "v(o2n)", "v(norm1)", "i(vavdd)"]
MON_VEC = ["v(avdd_adc)", "v(avss_adc)", "v(avdd_afei)", "v(avss_afei)", "v(avdd_bias)", "v(avss_bias)", "v(dvddc)",
           "v(dvssc)", "v(vcm_adc)", "v(vcm_afe)", "v(vcm_bias)", "v(vcm_brd)", "v(vrefp_adc)", "v(vrefn_adc)",
           "v(vrefp_ref)", "v(vrefn_ref)", "v(vbn_afe)", "v(vbn_bias)", "v(vbcm_afe)", "v(bln_afe)", "v(blp_afe)",
           "v(vbn1)", "v(vnc1)", "v(vpc1)", "v(vbcm1)", "v(vbpc2)", "v(vbnc2)", "v(iq)", "v(xb.gp)", "v(afe_rst)",
           "v(chop)", "v(chop_blank)", "v(cmp_strobe)", "v(dac_clk)", "v(chop1)", "v(xdut.opi)", "v(xdut.oni)",
           "v(xdut.inp)", "v(xdut.inn)", "v(elp)", "v(eln)", "v(outp_afe)", "v(outn_afe)", "v(xadc.i2p)",
           "v(xadc.i2n)", "i(vdvdd)", "i(vrefpx)", "i(vrefnx)"]
AVDD, AVSS, VCM = "v(avdd_adc)", "v(avss_adc)", "v(vcm_adc)"     # the ADC's view
VOP, VON = "v(outp_adc)", "v(outn_adc)"                           # the AFE output at the ADC input
CTRL_VEC = [f"v(xctrl.{p}{k})" for p in ("ca", "pa") for k in range(5)]


def lat_node(variant, j):
    """DAC1 element j's latch output Q (follows SEL1_j while the break pulse is high)"""
    return f"v(xadc.dac1.c{j}.q)" if variant == "pex" else f"v(xadc.xdac1.xc{j}.q)"


def vectors(a):
    """saved vectors: full (122, for short runs) or lean (25, for ms-long runs: the E2E columns, the
    controller's code and pointer, the DAC1 latch check as one monitor, supplies and VCM)"""
    if getattr(a, "save", "full") == "lean":
        v = E2E_VEC + CTRL_VEC + ["v(latmis)", AVDD, AVSS, "v(dvddc)", "v(dvssc)", VCM, "v(afe_rst)"]
        return v + ([f"v(th{j})" for j in range(NSEL)] if a.save_th else [])
    v = E2E_VEC + MON_VEC + CTRL_VEC + ["v(latmis)"] + [lat_node(a.variant, j) for j in range(NSEL)]
    v += [f"v(selx{j})" for j in range(NSEL)]
    if a.dac2_sel == "therm":
        v += ["v(norm2)"]
    if a.save_th:
        v += [f"v(th{j})" for j in range(NSEL)]
    return v


def timeline(a):
    """MCLK edges at E0_REF + n TM. RESET_N rises 2.5 MCLK before e0 of frame 0 (the third
    edge after it: two synchronizer flip-flops, then the clock generator's first count)."""
    k = math.ceil((a.t_reset + 2.5 * TM - E0_REF) / (4 * T) - 1e-9) * 4
    e0 = E0_REF + k * T
    n = math.ceil((a.t_afe - E0_REF) / TM - 1e-6)
    t_afe = E0_REF + n * TM
    if t_afe < e0 + T:
        raise SystemExit(f"--t-afe must be at least one frame after frame 0 (e0 = {e0:.6e} s)")
    half1 = round(1.024e6 / (2 * a.chop1)) if a.chop1 else 0
    t_rn = e0 - 2.5 * TM
    ibias = getattr(a, "ibias", 2)
    t_write = None
    if ibias != 2:      # the firmware's AFE_IBIAS write, committed at an MCLK edge
        t_write = E0_REF + math.ceil((t_rn + a.t_write - E0_REF) / TM - 1e-6) * TM
        if not t_rn < t_write < t_afe:
            raise SystemExit("--t-write must put the AFE_IBIAS write between RESET_N and the AFE release")
    tl = dict(t_reset=t_rn, e0=e0, t_rstloc=e0 + TM, t_afe=t_afe, ibias=ibias, t_write=t_write,
              afe_frame=int((t_afe - e0) // T), afe_cycle=int(round((t_afe - e0) % T / TM)) % 32,
              chop1_half=half1, t_sig=a.t_sig if a.t_sig is not None else t_afe, tstop=a.tstop)
    return tl


def events(tl, t0=0.0):
    """DLOAD (e3 of every frame from frame 0) and the controller's reset (until e1 of frame
    0, eeg_adc_dig's local reset); times from t0 (the start of a continued run)"""
    rst = tl["t_rstloc"] - t0
    out = ["0 0s 1s", f"{rst:.12e} 0s 0s"] if rst > 0 else ["0 0s 0s"]
    k = 0
    while tl["e0"] + 3 * TM + k * T < tl["tstop"]:
        t = tl["e0"] + 3 * TM + k * T - t0
        if t + 32e-9 > 0:
            if t <= 0:
                raise SystemExit("a continued run must not start inside a DLOAD pulse")
            out += [f"{t:.12e} 1s 0s", f"{t + 32e-9:.12e} 0s 0s"]
        k += 1
    return "\n".join(out) + "\n"


def pulse(t_edge, high, period, v1=0, v2=1):
    """unit PULSE whose first edge is centred on t_edge, high for `high` (50 % points)"""
    return f"PULSE({v1} {v2} {t_edge - EDGE / 2:.12e} {EDGE:g} {EDGE:g} {high - EDGE:.12e} {period:.12e})"


def adc_text(variant, mc):
    if variant == "pex":
        txt = open(PE.ADC_PEX).read()
    else:
        txt = "".join(open(f).read() + "\n" for f in ADC_SCH)
    return S.par_m(txt) if mc else txt


def shift_pwl(text, t0):
    """the supply / reference ramps PWL(0 0 tramp V) of board_and_pads() seen from t0"""
    def f(m):
        tr, v = float(m.group(1)), float(m.group(2))
        if t0 >= tr:
            return f"DC {v:g}"
        return f"PWL(0 {v * t0 / tr:.9g} {tr - t0:.9e} {v:g})"
    return re.sub(r"PWL\(0 0 ([0-9.eE+-]+) ([0-9.eE+-]+)\)", f, text) if t0 > 0 else text


def driven_nodes(text):
    """top-level nodes with nothing but ideal sources and control inputs on them (the unit
    sources, the electrode source, the POLY monitors, the XSPICE bridge outputs): KLU refuses
    an .ic on a node without a diagonal matrix entry, and their values follow from the sources"""
    lines, depth = [], 0
    for ln in text.splitlines():
        if ln.startswith("+") and lines:
            lines[-1] += " " + ln[1:]
        else:
            lines.append(ln)
    real, seen = set(), set()
    for ln in lines:
        tk = ln.split()
        if not tk:
            continue
        w = tk[0].lower()
        if w == ".subckt":
            depth += 1
            continue
        if w == ".ends":
            depth -= 1
            continue
        if depth or w[0] in "*.":
            continue
        nodes = [x.lower() for x in tk[1:] if "=" not in x and "(" not in x and "[" not in x and "]" not in x]
        if w[0] in "rcld":
            real |= set(nodes[:2])
        elif w[0] == "m":
            real |= set(nodes[:4])
        elif w[0] == "x":
            real |= set(nodes[:-1])
        elif w[0] in "vbegfhi":
            seen |= set(nodes[:2])
    return seen - real


def ic_lines(ic, skip=()):
    """.ic for every node of the previous stage's last point except the driven ones"""
    v = [(k[2:-1], x) for k, x in ic.items() if k.startswith("v(") and k[2:-1] not in skip
         and not re.match(r"(selx|selnx|s2lx|s2lnx)\d+$|xctrl\.", k[2:-1])]
    return "".join(".ic " + " ".join(f"v({n})={x:.12g}" for n, x in v[i:i + 8]) + "\n" for i in range(0, len(v), 8))


def inductor_ic(text, ic):
    """L lines of the deck (board, bond wires) with the previous stage's currents"""
    def f(m):
        k = f"i({m.group(1).lower()})"
        return m.group(0) + (f" ic={ic[k]:.12g}" if k in ic else "")
    return re.sub(r"^(L\S+) \S+ \S+ \S+$", f, text, flags=re.M)


def deck(a, seed, tl, st=None):
    """the deck; st (a staged run): t0 (start, s; every source and event seen from it), tend
    (end, s), tol, ic (node voltages and inductor currents to start from, uic), save_all,
    solver, raw (output file)"""
    st = st or {}
    t0, tend = st.get("t0", 0.0), st.get("tend", a.tstop)
    tol, raw, solver = st.get("tol", a.tol), st.get("raw", "tr.raw"), st.get("solver", a.solver)
    mc = seed is not None
    pex = a.variant == "pex"
    chip = S.chip_model(a.variant, a.chip)
    rng = next((r for r, full in ((1, 39), (2, 79), (3, 159), (4, 318)) if abs(a.vin) <= full), 4) if a.vin else 0
    blank = 15 if rng else 7
    e = [P.RIN_EXTRACTED["E"][k] - S.STRAP_RIN[k] for k in range(2)] if pex else (0.0, 0.0)   # the chopper's part
    rafe = a.rafe if pex else (0.0, 0.0)
    bias = open(S.BIAS_PEX if pex else P.BIAS).read()
    bias = S.par_m(bias) if mc else bias
    e0, dg = tl["e0"] - t0, S.digital
    vdc = (a.vin + getattr(a, "dc", 0.0)) * 1e-3          # electrode DC: the offset (DAC set for it) + --dc
    sine = f" SIN({vdc:.6g} {a.amp * 1e-3:.9e} {a.fsig:g} {tl['t_sig'] - t0:.12e})" if a.amp else ""
    # AFE_IBIAS: the reset value (code 2: IB1 = 1, IB0 = 0) until the firmware's write (afe_startup's
    # trim lines), a 2 ns edge at an MCLK edge; seen from t0 in a continued run
    trim, ib = "", {1: "ONE", 0: "ZERO"}
    for b in (1, 0):
        r_, n_ = (2 >> b) & 1, (tl.get("ibias", 2) >> b) & 1
        if r_ != n_:
            tw = tl["t_write"] - t0
            trim += (f"VUIB{b} UIB{b} 0 PWL(0 {r_} {tw - 1e-9:.12e} {r_} {tw + 1e-9:.12e} {n_})\n" if tw - 1e-9 > 0
                     else f"VUIB{b} UIB{b} 0 {n_}\n")
            ib[b] = f"UIB{b}"
    ch1 = (pulse(e0 + tl["chop1_half"] * T + 16 * TM, tl["chop1_half"] * T, 2 * tl["chop1_half"] * T, 1, 0)
           if a.chop1 else "1")
    ta = tl["t_afe"] - t0
    urst = f"PWL(0 1 {ta - 1e-9:.12e} 1 {ta + 1e-9:.12e} 0)" if ta - 1e-9 > 0 else "0"
    units = (f"VONE ONE 0 1\nVZERO ZERO 0 0\n"
             f"VUCMP UCMP 0 {pulse(e0, TM, T)}\n"
             f"VUDCK UDCK 0 {pulse(e0 + 4 * TM, TM, T)}\n"
             f"VUCHOP UCHOP 0 {pulse(e0, 4 * T, 8 * T)}\n"
             f"VUBLK UBLK 0 {pulse(e0 + 4 * T - TM, (1 + blank) * TM, 4 * T)}\n"
             f"VUCH1 UCH1 0 {ch1}\n"
             f"VURST URST 0 {urst}\n" + trim)
    digital = (dg("IB1", "IB1", ib[1]) + dg("IB0", "IB0", ib[0]) + dg("BP1", "BP1", "ZERO") + dg("BP0", "BP0", "ONE")
               + dg("BN1", "BN1", "ZERO") + dg("BN0", "BN0", "ONE") + dg("CHEN", "CHOP_EN", "ONE")
               + dg("AZ", "ADC_ZERO", "ZERO") + dg("CMP", "CMP_STROBE", "UCMP") + dg("DCK", "DAC_CLK", "UDCK")
               + dg("CHOP", "CHOP", "UCHOP") + dg("CHOPO", "CHOP_OUT", "UCHOP") + dg("BLK", "CHOP_BLANK", "UBLK")
               + dg("CH1", "CHOP1", "UCH1") + dg("RST", "AFE_RST", "URST"))
    sel = " ".join(f"SEL{j}" for j in range(NSEL))
    sel2 = " ".join(f"S2L{j}" for j in range(NSEL)) if a.dac2_sel == "therm" else sel
    th = " ".join(f"TH{j}" for j in range(NSEL))
    ctrl_out = " ".join(f"{p}{j}" for p in ("SELX", "SELNX", "S2LX", "S2LNX") for j in range(NSEL))
    scale = "".join(f"BSEL{j} SEL{j} 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(SELX{j})/3.3\n" for j in range(NSEL))
    if a.dac2_sel == "therm":
        scale += "".join(f"BS2L{j} S2L{j} 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(S2LX{j})/3.3\n" for j in range(NSEL))
    poly = lambda p: " ".join(f"{p}{j} 0" for j in range(NSEL)) + " -.5" + f" {ONE_LSB:.17g}" * NSEL
    norm = f"ESUM1 NORM1 0 POLY({NSEL}) {poly('SELX')}\n"
    # DAC1 latches against SEL1: the number of elements whose latch Q differs from SEL1 (glitches
    # while DAC_CLK reloads them; 0 between the reloads)
    norm += "BLATMIS LATMIS 0 V=" + "+".join(
        f"abs(u(v({lat_node(a.variant, j)[2:-1]})-v(AVDD_ADC,AVSS_ADC)/2)-u(v(SELX{j})-1.65))" for j in range(NSEL)) + "\n"
    if a.dac2_sel == "therm":
        norm += f"ESUM2 NORM2 0 POLY({NSEL}) {poly('S2LX')}\n"
    opts = f".options {solver} method=trap maxord=2 {TOLS[tol]} bypass=0\n"
    if a.xtrtol:
        opts += f".options xtrtol={a.xtrtol}\n"
    tstep = a.tstep
    tag = "typical" if not mc else f"mc{seed}"
    save = "save all" if st.get("save_all") else f"save time {' '.join(vectors(a))}"
    if st.get("batch"):     # ngspice -b -r: every node streamed to the raw file (a chunk of a chained run)
        control = f".options acct\n.save all\n.tran {tstep:g} {tend - t0:.12e} 0 {a.tmax:g} uic\n"
    else:
        control = (f".control\nset noaskquit\nset filetype=binary\n{save}\n"
                   f"tran {tstep:g} {tend - t0:.12e} 0 {a.tmax:g} uic\nwrite {raw}\nrusage all\nquit\n.endc\n")
    ic = st.get("ic")
    txt = f"""* E2E from power-on: afe_top {a.variant} -> eeg_adc {a.variant}, chip wiring {a.chip if pex else 'ideal'}, C_VCM {a.cvcm:g} F, AVDD {a.vdd} V, {a.corner if not mc else tag}
* RESET_N {tl['t_reset']:.9e} s, frame 0 at {tl['e0']:.9e} s, AFE_RST released {tl['t_afe']:.9e} s (frame {tl['afe_frame']} cycle {tl['afe_cycle']}), stop {a.tstop:.6e} s
* this deck: {t0:.9e} .. {tend:.9e} s (its time 0 is {t0:.9e} s{', every node from the previous stage' if ic else ', every node at 0 V'}), tolerances {tol}
{S.head(a.corner, seed, a.moscap, a.mim_a, a.res_a)}.include {S.REF_PEX if pex else S.REF}
.include {S.IO}
.include {chip}
.include quantizer.spice
{bias}
{S.dut(a.variant, mc, chip)}
{adc_text(a.variant, mc)}
.temp {a.temp}
{opts}{shift_pwl(S.board_and_pads(a, chip), t0)}RAFEVDD AVDD_AFE AVDD_AFEI {max(rafe[1], 1e-6):g}
RAFEVSS AVSS_AFEI AVSS_AFE {max(rafe[0], 1e-6):g}
XREF VREFP_PAD_REF VREFN_PAD_REF VREFP_REF VREFN_REF AVSS_REF eeg_ref
XB VBN_BIAS VBCM_BIAS BLP_BIAS BLN_BIAS VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM_BIAS VREFP_BIAS VREFN_BIAS
+ IB1 IB0 BP1 BP0 BN1 BN0 AVDD_BIAS AVSS_BIAS eeg_bias
VITST ITST AVSS_TM 0
* digital block: RTL timing as 0..1 sources, outputs between DVSSC and DVDDC
{units}{digital}* electrodes
VSIG SIG 0 DC {vdc:.6g}{sine}
EP SRC_P VCM_BRD SIG 0 0.5
EN SRC_N VCM_BRD SIG 0 -0.5
RSP SRC_P ELP_BRD 100
RSN SRC_N ELN_BRD 100
{''.join(S.wire(f'{n}{k}', f'{n}_BRD', f'{n}_P{k}') for n in ('ELP', 'ELN') for k in S.PADS[n])}\
RECHP ELP_AFE ELP {max(e[0], 1e-3):g}
RECHN ELN_AFE ELN {max(e[1], 1e-3):g}
* AFE (its clock driver inside) on its chip-wiring pins, the ADC on its pins (OUTP / OUTN route in the chip wiring)
{S.dut_line((a.vin, rng) if rng else None)}
XADC OUTP_ADC OUTN_ADC CHOP1 DAC_CLK CMP_STROBE AFE_RST ADC_ZERO {sel}
+ {sel2}
+ {th}
+ VREFP_ADC VREFN_ADC VCM_ADC VBN1 VNC1 VPC1 VBCM1 VBPC2 VBNC2 IDP IDN IQ O2P O2N AVDD_ADC AVSS_ADC DVDDC DVSSC eeg_adc
* eeg_adc_dig: the XSPICE controller, its outputs scaled onto DVSSC..DVDDC
XCTRL {th} DLOAD DRESET_EVENT DVDDC DVSSC {ctrl_out} adc_ctrl_event
AEVENT [DLOAD DRESET_EVENT] CLOCK_EVENTS
.model CLOCK_EVENTS d_source(input_file="events.txt")
{scale}{norm}@@IC@@{control}.end
"""
    if not ic:
        return txt.replace("@@IC@@", "")
    return inductor_ic(txt.replace("@@IC@@", ic_lines(ic, driven_nodes(txt) | {"0"})), ic)


# ---------------------------------------------------------------- running

def cpu_of(pid):
    """CPU time (s) of a running process, from ps"""
    try:
        s = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        parts = [float(x) for x in s.replace("-", ":").split(":")]
        return sum(v * 60 ** k for k, v in enumerate(reversed(parts)))
    except (ValueError, OSError):
        return float("nan")


def run_ngspice(d, deck_name="tb.spice", cpu_every=5.0, extra=(), beat=None, beat_every=1800.0):
    """ngspice -b in d; run.log, and progress.csv: wall clock (s), simulated time and the
    process's CPU time (s, sampled every cpu_every s of wall clock, else nan) of every progress
    line. ngspice prints a progress line at an accepted point at most every 0.25 s of CPU, so
    where points are expensive the lines thin out: the CPU column is the measure. beat(wall,
    simulated time) is called every beat_every s of wall clock. ngspice is killed if this
    process is interrupted."""
    p = subprocess.Popen(["ngspice", "-b", *extra, deck_name], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t0 = time.time()
    last, last_beat = -1e9, 0.0
    pat = re.compile(rb"Reference value :\s*([-+0-9.eE]+)")
    buf = b""
    try:
        with open(os.path.join(d, "run.log"), "wb") as log, open(os.path.join(d, "progress.csv"), "w") as prog:
            while True:
                ch = p.stdout.read1(65536)
                if not ch:
                    break
                log.write(ch)
                buf += ch
                parts = re.split(rb"[\r\n]", buf)
                buf = parts[-1]
                for ln in parts[:-1]:
                    m = pat.search(ln)
                    if m:
                        w = time.time() - t0
                        cpu = float("nan")
                        if w - last >= cpu_every:
                            cpu, last = cpu_of(p.pid), w
                        prog.write(f"{w:.2f} {float(m.group(1)):.9e} {cpu:.2f}\n")
                        if beat and w - last_beat >= beat_every:
                            last_beat = w
                            beat(w, float(m.group(1)))
                prog.flush()
    except BaseException:
        p.kill()
        p.wait()
        raise
    _, status, ru = os.wait4(p.pid, 0)
    p.returncode = os.waitstatus_to_exitcode(status)
    return p.returncode, time.time() - t0, ru.ru_utime + ru.ru_stime


def run_name(a, seed):
    return (("sch_" if a.variant == "sch" else "") + f"c{a.cvcm:g}_v{a.vdd:g}_{a.corner if seed is None else f'mc{seed}'}"
            f"_{a.vin:+g}mV" + (f"_dc{a.dc:+g}mV" if getattr(a, "dc", 0) else "")
            + (f"_ib{a.ibias}" if getattr(a, "ibias", 2) != 2 else "") + (f"_sine{a.amp:g}mV{a.fsig:g}Hz" if a.amp else "")
            + f"_rst{a.t_reset * 1e3:g}_afe{a.t_afe * 1e3:g}_to{a.tstop * 1e3:g}ms" + a.tag)


def write_quantizer(d):
    q = open(os.path.join(md.IMPORT, "quantizer.spice")).read()
    q = md.sub(r"^\.model ADC33 adc_bridge \(in_low=0\.99 in_high=2\.31 ",
               ".model ADC33 adc_bridge (in_low=1.65 in_high=1.65 ", q)
    open(os.path.join(d, "quantizer.spice"), "w").write(q)


def last_point(path):
    """node voltages and inductor currents of the last point of a raw file"""
    r = read_raw(path)
    return {k: float(v[-1]) for k, v in r.items() if k.startswith("v(") or k.startswith("i(l")}


def prepare(a, seed):
    """the run folder; a two-stage run (--t-handoff) gets ramp/ with the power-on deck"""
    tl = timeline(a)
    d = os.path.join(RUNS, run_name(a, seed))
    os.makedirs(d, exist_ok=True)
    write_quantizer(d)
    th = a.t_handoff
    if th:
        if not a.tramp < th < tl["e0"] - 1e-9:
            raise SystemExit("--t-handoff must lie between the end of the supply ramp and frame 0 "
                             f"(e0 = {tl['e0']:.9e} s): the controller model's state is not handed over")
        dr = os.path.join(d, "ramp")
        os.makedirs(dr, exist_ok=True)
        write_quantizer(dr)
        open(os.path.join(dr, "events.txt"), "w").write(events(tl))
        open(os.path.join(dr, "tb.spice"), "w").write(
            deck(a, seed, tl, dict(tend=th, tol=a.tol_ramp, solver=a.solver_ramp, save_all=True, raw="ramp.raw")))
    else:
        open(os.path.join(d, "events.txt"), "w").write(events(tl))
        open(os.path.join(d, "tb.spice"), "w").write(deck(a, seed, tl))
    meta = {k: getattr(a, k) for k in ("cvcm", "vdd", "tramp", "corner", "temp", "moscap", "variant",
                                       "chip", "rafe", "mim_a", "res_a", "vin", "dc", "ibias", "t_write", "amp", "fsig", "chop1", "dac2_sel", "tstop", "tstep",
                                       "tmax", "tol", "tol_ramp", "t_handoff", "solver", "solver_ramp", "xtrtol",
                                       "wstep", "save")}
    meta |= {"seed": seed, "timeline": tl, "requested": {"t_reset": a.t_reset, "t_afe": a.t_afe}, "t0": th or 0.0}
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
    return d, tl


def run(a, seed):
    d0 = os.path.join(RUNS, run_name(a, seed))
    old = json.load(open(os.path.join(d0, "meta.json"))) if os.path.exists(os.path.join(d0, "meta.json")) else {}
    reuse = (a.reuse_ramp and old.get("ramp", {}).get("exit") == 0
             and os.path.exists(os.path.join(d0, "ramp", "ramp.raw")))
    if reuse:   # the power-on stage of an earlier run of the same name
        tl = timeline(a)
        d, meta = d0, old
    else:
        d, tl = prepare(a, seed)
        meta = json.load(open(os.path.join(d, "meta.json")))
    if a.t_handoff:
        dr = os.path.join(d, "ramp")
        if not reuse:
            rc, wall, cpu = run_ngspice(dr)
            meta["ramp"] = {"exit": rc, "wall_s": wall, "cpu_s": cpu}
            json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
        else:
            rc, wall = 0, meta["ramp"]["wall_s"]
        log1 = open(os.path.join(dr, "run.log"), errors="replace").read()
        if (rc != 0 or not os.path.exists(os.path.join(dr, "ramp.raw")) or "timestep too small" in log1.lower()
                or "simulation(s) aborted" in log1):
            return d, False, wall
        ic = last_point(os.path.join(dr, "ramp.raw"))
        open(os.path.join(d, "events.txt"), "w").write(events(tl, a.t_handoff))
        open(os.path.join(d, "tb.spice"), "w").write(
            deck(a, seed, tl, dict(t0=a.t_handoff, tend=a.tstop, tol=a.tol, ic=ic)))
    rc, wall, cpu = run_ngspice(d)
    meta |= {"exit": rc, "wall_s": wall, "cpu_s": cpu}
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
    log = open(os.path.join(d, "run.log"), errors="replace").read()
    ok = rc == 0 and os.path.exists(os.path.join(d, "tr.raw")) and "timestep too small" not in log.lower() \
        and "simulation(s) aborted" not in log
    if ok:
        check(d)
        plot(d)
    return d, ok, wall


# ---------------------------------------------------------------- chained runs (checkpoints)

FF_LINE = re.compile(r"^(A(PTR|SEL|CODE)(\d+) .* )(FF[01])$", re.M)


def ctrl_state(last):
    """the XSPICE controller's flip-flops from a last point: DWA pointer (pa), code register (ca),
    SEL1 (the bridge outputs SELX)"""
    bit = lambda k: int(last[k] > 1.65)
    return {"PTR": [bit(f"v(xctrl.pa{b})") for b in range(5)], "CODE": [bit(f"v(xctrl.ca{b})") for b in range(5)],
            "SEL": [bit(f"v(selx{j})") for j in range(NSEL)]}


def write_quantizer_state(d, st):
    """quantizer.spice with every controller flip-flop starting from its saved state (FF0 / FF1:
    the import's models with ic = 0 / 1; set / reset stay idle in a continued run)"""
    write_quantizer(d)
    q = open(os.path.join(d, "quantizer.spice")).read()
    n = {"n": 0}

    def f(m):
        n["n"] += 1
        return m.group(1) + f"FF{st[m.group(2)][int(m.group(3))]}"
    q = FF_LINE.sub(f, q)
    assert n["n"] == 41, n
    open(os.path.join(d, "quantizer.spice"), "w").write(q)


def chunk_state(raw):
    """end state of a chunk: every node voltage and inductor current at its last point, and the
    controller's flip-flops"""
    names, mm = raw_mm(raw)
    row = np.array(mm[-1])
    last = {n: float(row[j]) for j, n in enumerate(names)}
    ic = {k: v for k, v in last.items() if k.startswith("v(") or k.startswith("i(l")}
    return {"time": last["time"], "ic": ic, "ctrl": ctrl_state(last)}


def raw_columns(raw, names_wanted, t0):
    """selected columns of a chunk's raw (absolute time)"""
    names, mm = raw_mm(raw)
    idx = {n: j for j, n in enumerate(names)}
    r = {"time": np.array(mm[:, idx["time"]]) + t0}
    for n in names_wanted:
        if n in idx:
            r[n] = np.array(mm[:, idx[n]])
    return r


def frames_between(r, tl, variant, t_lo, t_hi):
    """frames whose strobe (e0) and mid-frame (e16) both lie inside [t_lo, t_hi]"""
    fr = frames(r, tl, variant)
    return [x for x in fr if x["t_e0"] >= t_lo and x["t_e0"] + 16 * TM <= t_hi]


def chain_bounds(tl, first, every, tstop):
    """chunk boundaries: mid-frame (e20, away from every clock edge of the frame) from `first` on,
    every `every` frames"""
    k0 = math.ceil((first - tl["e0"]) / T)
    out = []
    k = k0
    while tl["e0"] + k * T + 20 * TM < tstop - T:
        out.append(tl["e0"] + k * T + 20 * TM)
        k += every
    return out


FRAME_KEYS = ["frame", "t_e0", "code", "ptr", "k_sel", "norm1", "lat_mismatch", "lat_min_margin", "o1", "o2", "vo", "rst"]


def write_frames(path, fr, append=False):
    with open(path, "a" if append else "w") as f:
        if not append:
            f.write(" ".join(FRAME_KEYS) + "\n")
        for x in fr:
            f.write(" ".join(str(int(x[k])) if isinstance(x[k], bool) else (f"{x[k]:.9g}" if isinstance(x[k], float)
                                                                              else str(x[k])) for k in FRAME_KEYS) + "\n")


def read_frames(path):
    rows = open(path).read().split("\n")
    keys = rows[0].split()
    out = []
    for ln in rows[1:]:
        if ln.strip():
            x = dict(zip(keys, ln.split()))
            out.append({k: (int(v) if k in ("frame", "code", "ptr", "k_sel", "lat_mismatch", "rst") else float(v))
                        for k, v in x.items()})
    return out


LEAN_KEEP = E2E_VEC + CTRL_VEC + ["v(latmis)", AVDD, AVSS, "v(dvddc)", "v(dvssc)", VCM, "v(afe_rst)", "v(vbn_afe)",
                                  "v(vbn_bias)", "i(vdvdd)", "v(vrefp_adc)", "v(vrefn_adc)", "v(vrefp_ref)",
                                  "v(vrefn_ref)", "i(vrefpx)", "i(vrefnx)"]


def run_chunk(a, seed, tl, d, k, t0, t1, prev):
    """chunk k of a chained run in folder d/chunk_kkk: from power-on (k = 0) or from the previous
    chunk's end state, to t1; every node streamed to chunk.raw (ngspice -b -r), then the end state,
    the frames and the lean vectors kept and the raw deleted"""
    dk = os.path.join(d, f"chunk_{k:03d}")
    os.makedirs(dk, exist_ok=True)
    st = dict(t0=t0, tend=t1, tol=a.tol, batch=True)
    if prev is None:
        write_quantizer(dk)
    else:
        st["ic"] = prev["ic"]
        write_quantizer_state(dk, prev["ctrl"])
    open(os.path.join(dk, "events.txt"), "w").write(events(tl, t0))
    open(os.path.join(dk, "tb.spice"), "w").write(deck(a, seed, tl, st))
    raw = os.path.join(dk, "chunk.raw")

    def beat(w, ts):    # a line in progress.log every 30 min of a chunk
        with open(os.path.join(d, "progress.log"), "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}   chunk {k} at {(t0 + ts) * 1e3:.6f} ms "
                    f"({ts / (t1 - t0) * 100:.0f} % of it), {w / 3600:.2f} h in it\n")
    rc, wall, cpu = run_ngspice(dk, extra=("-r", "chunk.raw"), beat=beat)
    log = open(os.path.join(dk, "run.log"), errors="replace").read()
    info = dict(k=k, t0=t0, t1=t1, exit=rc, wall_s=wall, cpu_s=cpu, tol=a.tol)
    bad = rc != 0 or not os.path.exists(raw) or "timestep too small" in log.lower() or "simulation(s) aborted" in log
    if not bad:
        stt = chunk_state(raw)
        bad = abs(stt["time"] + t0 - t1) > 1e-12
    if bad:
        info["status"] = "failed"
        json.dump(info, open(os.path.join(dk, "chunk.json"), "w"), indent=1)
        return info, None
    keep = LEAN_KEEP + [lat_node(a.variant, j) for j in range(NSEL)] + [f"v(selx{j})" for j in range(NSEL)]
    r = raw_columns(raw, keep, t0)
    fr = frames_between(r, tl, a.variant, t0, t1)
    write_frames(os.path.join(dk, "frames.csv"), fr)
    np.savez_compressed(os.path.join(dk, "lean.npz"), **{n: r[n] for n in ["time"] + LEAN_KEEP if n in r})
    info |= dict(status="done", points=int(len(r["time"])), frames=len(fr), codes=[x["code"] for x in fr],
                 o1_mV=[float(min(x["o1"] for x in fr) * 1e3), float(max(x["o1"] for x in fr) * 1e3)] if fr else None,
                 o2_mV=[float(min(x["o2"] for x in fr) * 1e3), float(max(x["o2"] for x in fr) * 1e3)] if fr else None,
                 lat_mismatch=int(sum(x["lat_mismatch"] for x in fr)))
    json.dump(stt, open(os.path.join(dk, "state.json"), "w"))
    json.dump(info, open(os.path.join(dk, "chunk.json"), "w"), indent=1)
    if not a.keep_raw:
        os.remove(raw)
    return info, stt


def driver_alive(lock):
    """the pid in a chain's driver.pid if that process is alive and runs e2e_startup.py, else None"""
    try:
        pid = int(open(lock).read().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    cmd = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True).stdout
    return pid if "e2e_startup.py" in cmd else None


def chain(a, seed):
    """a run in chunks that restart from each other's end state; resumable: completed chunks
    (chunk.json status done, state.json) are skipped, the next one starts from the last state"""
    tl = timeline(a)
    d = os.path.join(RUNS, run_name(a, seed) + "_chain")
    os.makedirs(d, exist_ok=True)
    bounds = a.bounds if a.bounds else chain_bounds(tl, a.chunk_first, a.chunk_frames, a.tstop)
    edges = [0.0] + list(bounds) + [a.tstop]
    meta = {k: getattr(a, k) for k in ("cvcm", "vdd", "tramp", "corner", "temp", "moscap", "variant", "chip", "rafe",
                                       "mim_a", "res_a", "vin", "dc", "ibias", "t_write", "amp", "fsig", "chop1",
                                       "dac2_sel", "tstop", "tstep", "tmax", "tol", "solver", "xtrtol", "wstep")}
    meta |= {"seed": seed, "timeline": tl, "edges": edges, "requested": {"t_reset": a.t_reset, "t_afe": a.t_afe}}
    mp = os.path.join(d, "meta.json")
    if os.path.exists(mp):
        old = json.load(open(mp))
        if old.get("edges") != edges or old.get("timeline") != tl:
            raise SystemExit(f"{d}: an earlier chain with other chunk edges or timing; use another --tag")
    logp = os.path.join(d, "progress.log")
    # one driver per chain: driver.pid names the running one
    lock = os.path.join(d, "driver.pid")
    pid = driver_alive(lock)
    if pid and pid != os.getpid():
        raise SystemExit(f"{d}: driver {pid} is still running (driver.pid); stop it first")
    open(lock, "w").write(f"{os.getpid()}\n")
    json.dump(meta, open(mp, "w"), indent=1)
    import signal

    def stop(signum, frame):
        raise SystemExit(f"signal {signum}")
    signal.signal(signal.SIGTERM, stop)
    if signal.getsignal(signal.SIGHUP) != signal.SIG_IGN:     # under nohup SIGHUP stays ignored
        signal.signal(signal.SIGHUP, stop)
    prev = None
    t_start = time.time()
    for k in range(len(edges) - 1):
        dk = os.path.join(d, f"chunk_{k:03d}")
        cj = os.path.join(dk, "chunk.json")
        if os.path.exists(cj) and json.load(open(cj)).get("status") == "done" and os.path.exists(os.path.join(dk, "state.json")):
            prev = json.load(open(os.path.join(dk, "state.json")))
            continue
        with open(logp, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} chunk {k}/{len(edges) - 2}: {edges[k] * 1e3:.6f} -> "
                    f"{edges[k + 1] * 1e3:.6f} ms started\n")
        try:
            info, stt = run_chunk(a, seed, tl, d, k, edges[k], edges[k + 1], prev)
            if info["status"] != "done" and a.tol != "fine":
                # one retry of a chunk that ngspice failed on, with the fine tolerances
                os.replace(os.path.join(dk, "run.log"), os.path.join(dk, f"run_failed_{a.tol}.log"))
                with open(logp, "a") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} chunk {k} failed with the {a.tol} tolerances (exit "
                            f"{info['exit']}, {dk}/run_failed_{a.tol}.log); retrying it with the fine ones\n")
                b = copy.copy(a)
                b.tol = "fine"
                info, stt = run_chunk(b, seed, tl, d, k, edges[k], edges[k + 1], prev)
                info["tol"] = "fine (retry)"
                json.dump(info, open(cj, "w"), indent=1)
        except BaseException as ex:     # an error in the driver, or stopped (SIGTERM / SIGHUP / ^C)
            import traceback
            info = dict(k=k, t0=edges[k], t1=edges[k + 1], status="interrupted" if isinstance(
                ex, (SystemExit, KeyboardInterrupt)) else "error", error=repr(ex), traceback=traceback.format_exc())
            json.dump(info, open(os.path.join(d, "failure.json"), "w"), indent=1)
            with open(logp, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} chunk {k} {info['status'].upper()}: {ex!r}; resume with "
                        f"the same command\n")
            os.path.exists(lock) and os.remove(lock)
            if isinstance(ex, Exception):
                return False
            raise
        with open(logp, "a") as f:
            if info["status"] != "done":
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} chunk {k} FAILED (exit {info['exit']}, see "
                        f"{dk}/run.log); resume with the same command\n")
                json.dump(info, open(os.path.join(d, "failure.json"), "w"), indent=1)
                os.path.exists(lock) and os.remove(lock)
                return False
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} chunk {k} done: {info['wall_s'] / 3600:.2f} h wall, "
                    f"{info['cpu_s'] / 3600:.2f} h CPU, {info['points']} points, {info['frames']} frames, codes "
                    f"{min(info['codes']) if info['codes'] else '-'}..{max(info['codes']) if info['codes'] else '-'}, "
                    f"O1 {info['o1_mV']} mV, O2 {info['o2_mV']} mV, latch mismatches {info['lat_mismatch']}; "
                    f"last codes {' '.join(map(str, info['codes'][-12:]))}\n")
        prev = stt
    # merged frames, summary
    fr = []
    for k in range(len(edges) - 1):
        fr += read_frames(os.path.join(d, f"chunk_{k:03d}", "frames.csv"))
    write_frames(os.path.join(d, "frames.csv"), fr)
    with open(logp, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} all {len(edges) - 1} chunks done, {len(fr)} frames; "
                f"{(time.time() - t_start) / 3600:.2f} h in this session\n")
    if os.path.exists(os.path.join(d, "failure.json")):
        os.remove(os.path.join(d, "failure.json"))
    # the RTL's decimator on the codes (bit-exact model and tb_e2e.sv), into cic.log
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        for fn in (cic, expect):
            try:
                fn(d)
            except Exception as ex:     # the analysis must not turn a finished run into a failed one
                print(f"{fn.__name__}() failed: {ex!r}; run: e2e_startup.py {fn.__name__} {d}")
    open(os.path.join(d, "cic.log"), "w").write(buf.getvalue())
    with open(logp, "a") as f:
        f.write(buf.getvalue())
    os.path.exists(lock) and os.remove(lock)
    return True


def status(d):
    """progress of a chained run: chunks done, the running chunk's simulated time, codes so far,
    wall time per chunk and an estimate of the end"""
    meta = json.load(open(os.path.join(d, "meta.json")))
    edges = meta["edges"]
    n = len(edges) - 1
    done, walls, codes = [], [], []
    for k in range(n):
        cj = os.path.join(d, f"chunk_{k:03d}", "chunk.json")
        if os.path.exists(cj):
            info = json.load(open(cj))
            if info.get("status") == "done":
                done.append(k)
                walls.append(info["wall_s"])
                codes += info.get("codes", [])
            elif info.get("status") == "failed":
                print(f"chunk {k} FAILED (exit {info.get('exit')}): see {os.path.dirname(cj)}/run.log")
    running = next((k for k in range(n) if k not in done), None)
    print(f"{d}: {len(done)} of {n} chunks done ({edges[len(done)] * 1e3 if done else 0:.4f} of {edges[-1] * 1e3:.4f} ms)")
    pid = driver_alive(os.path.join(d, "driver.pid"))
    print(f"  driver: {f'running (pid {pid})' if pid else 'not running'}")
    if os.path.exists(os.path.join(d, "failure.json")):
        fj = json.load(open(os.path.join(d, "failure.json")))
        print(f"  failure.json: chunk {fj.get('k')} {fj.get('status')} {fj.get('error', '')} (exit {fj.get('exit')})")
    if running is not None:
        pp = os.path.join(d, f"chunk_{running:03d}", "progress.csv")
        if os.path.exists(pp) and os.path.getsize(pp):
            x = np.loadtxt(pp, ndmin=2)
            print(f"  chunk {running} running: at {(edges[running] + x[-1, 1]) * 1e3:.6f} ms "
                  f"(chunk {edges[running] * 1e3:.4f} -> {edges[running + 1] * 1e3:.4f} ms), {x[-1, 0] / 3600:.2f} h in it")
    if walls:
        per = np.mean(walls[1:]) if len(walls) > 1 else walls[0]
        left = n - len(done)
        print(f"  {np.mean(walls) / 3600:.2f} h per chunk so far; about {left * per / 3600:.1f} h left "
              f"(end about {time.strftime('%Y-%m-%d %H:%M', time.localtime(time.time() + left * per))})")
    if codes:
        print(f"  {len(codes)} frames so far, codes {min(codes)}..{max(codes)}, last: {' '.join(map(str, codes[-20:]))}")


def compare(da, db, t_from):
    """frames of two runs (frames.csv, e.g. a chained and a continuous one) from t_from: codes,
    pointer, O1 / O2 / AFE output at the strobe"""
    fa = {x["frame"]: x for x in read_frames(os.path.join(da, "frames.csv"))}
    fb = {x["frame"]: x for x in read_frames(os.path.join(db, "frames.csv"))}
    ks = sorted(k for k in fa if k in fb and fa[k]["t_e0"] >= t_from)
    same = [fa[k]["code"] == fb[k]["code"] for k in ks]
    dmax = {q: max(abs(fa[k][q] - fb[k][q]) for k in ks) * 1e6 for q in ("o1", "o2", "vo")} if ks else {}
    print(f"{len(ks)} frames from {t_from * 1e3:.6f} ms (frames {ks[0] if ks else '-'}..{ks[-1] if ks else '-'}): codes "
          f"identical in {sum(same)}, pointer identical in {sum(fa[k]['ptr'] == fb[k]['ptr'] for k in ks)}; largest "
          f"difference at the strobe O1 {dmax.get('o1', 0):.2f} uV, O2 {dmax.get('o2', 0):.2f} uV, AFE out "
          f"{dmax.get('vo', 0):.2f} uV")
    for k in ks:
        print(f"  frame {k}: code {fa[k]['code']:2d} / {fb[k]['code']:2d}, O1 {fa[k]['o1'] * 1e3:+9.4f} / "
              f"{fb[k]['o1'] * 1e3:+9.4f} mV, O2 {fa[k]['o2'] * 1e3:+8.4f} / {fb[k]['o2'] * 1e3:+8.4f} mV")
    return ks, same, dmax


# ---------------------------------------------------------------- reading and checks

def read_raw(path):
    """ngspice binary raw file (real) -> dict name -> array"""
    blob = open(path, "rb").read()
    i = blob.index(b"Binary:\n")
    head = blob[:i].decode().splitlines()
    nv = int(next(h for h in head if h.startswith("No. Variables:")).split(":")[1])
    npt = int(next(h for h in head if h.startswith("No. Points:")).split(":")[1])
    k = head.index("Variables:")
    names = [h.split()[1].lower() for h in head[k + 1:k + 1 + nv]]
    data = np.frombuffer(blob[i + 8:], dtype="<f8")
    npt = min(npt, data.size // nv)
    data = data[:npt * nv].reshape(npt, nv)
    return {n: data[:, j] for j, n in enumerate(names)}


def raw_mm(path):
    """a (possibly huge) ngspice binary raw file as (names, memmap of points x variables)"""
    with open(path, "rb") as f:
        head = b""
        while b"Binary:\n" not in head:
            ch = f.read(1 << 16)
            if not ch:
                raise ValueError(f"{path}: no binary section")
            head += ch
    i = head.index(b"Binary:\n")
    lines = head[:i].decode().splitlines()
    nv = int(next(h for h in lines if h.startswith("No. Variables:")).split(":")[1])
    k = lines.index("Variables:")
    names = [h.split()[1].lower() for h in lines[k + 1:k + 1 + nv]]
    size = os.path.getsize(path) - (i + 8)
    npt = size // (8 * nv)
    return names, np.memmap(path, dtype="<f8", mode="r", offset=i + 8, shape=(npt, nv))


def rusage(log):
    keys = ("Transient timepoints", "Accepted timepoints", "Rejected timepoints", "Transient iterations",
            "Circuit Equations", "Transient analysis time", "Transient load time", "Transient factor time",
            "Transient solve time", "Transient trunc time", "Matrix reorder time")
    out = {}
    for k in keys:
        m = re.search(rf"^{k}\s*=\s*([-+0-9.eE]+)", log, re.M)
        if m:
            out[k] = float(m.group(1))
    return out


def phase_cost(d, t, bounds, cpu_total=None):
    """per phase: CPU s (the sampled CPU column of progress.csv against simulated time; the
    last phase ends at the run's total), wall s, accepted points"""
    pr = np.loadtxt(os.path.join(d, "progress.csv"), ndmin=2)
    w, s = pr[:, 0], pr[:, 1]
    c = pr[:, 2] if pr.shape[1] > 2 else np.full_like(w, np.nan)
    ok = np.isfinite(c)
    sc, cc = np.concatenate([[0.0], s[ok]]), np.concatenate([[0.0], c[ok]])
    if cpu_total and s.size:
        sc, cc = np.concatenate([sc, [s[-1] + 1e-15]]), np.concatenate([cc, [cpu_total]])
    out = []
    for name, a0, a1 in bounds:
        a1 = min(a1, t[-1])
        n = int(((t >= a0) & (t < a1)).sum())
        cpu = float(np.interp(a1, sc, cc) - np.interp(a0, sc, cc)) if ok.any() else float("nan")
        wall = float(np.interp(a1, s, w) - np.interp(a0, s, w)) if s.size else float("nan")
        us = (a1 - a0) * 1e6
        out.append(dict(phase=name, t0=a0, t1=a1, sim_us=us, cpu_s=cpu, wall_s=wall, points=n,
                        cpu_s_per_us=cpu / us if us > 0 else float("nan"),
                        wall_s_per_us=wall / us if us > 0 else float("nan"),
                        points_per_us=n / us if us > 0 else float("nan")))
    return out


def at(t, y, tq):
    return np.interp(tq, t, y)


def frames(r, tl, variant):
    """per frame k from frame 0: code c[k] (the controller's register after e3), DAC1 level
    popcount(SEL1) = 31 - c[k], DAC1 latches against SEL1 after DAC_CLK (mid-frame), O1, O2 and
    the AFE output at the strobe (e0, just before the quantizer decides)"""
    t = r["time"]
    vdd = r["v(dvddc)"] - r["v(dvssc)"]
    out = []
    k = max(0, math.ceil((t[0] - tl["e0"]) / T - 1e-9))     # the first frame whose strobe is in the data
    while tl["e0"] + k * T + 16 * TM <= t[-1]:     # every frame whose mid-frame sample is in the data
        te0 = tl["e0"] + k * T
        tmid = te0 + 16 * TM                     # after e3 (SEL), e4/e5 (DAC_CLK)
        code = sum(int(at(t, r[f"v(xctrl.ca{b})"], tmid) > 1.65) << b for b in range(5))
        ptr = sum(int(at(t, r[f"v(xctrl.pa{b})"], tmid) > 1.65) << b for b in range(5))
        n1 = float(at(t, r["v(norm1)"], tmid))
        if lat_node(variant, 0) in r:
            sel = np.array([at(t, r[f"v(selx{j})"], tmid) > 1.65 for j in range(NSEL)])
            q = np.array([at(t, r[lat_node(variant, j)], tmid) for j in range(NSEL)])
            vd = at(t, vdd, tmid)
            qh = q > at(t, r["v(dvssc)"], tmid) + vd / 2
            ksel, mis, margin = int(sel.sum()), int((qh != sel).sum()), float((np.abs(q - vd / 2) / vd).min())
        else:   # lean: popcount(SEL1) from the DAC1 level monitor, the latches from LATMIS
            ksel, mis, margin = int(round((n1 + 0.5) * NSEL)), int(round(at(t, r["v(latmis)"], tmid))), float("nan")
        out.append(dict(frame=k, t_e0=te0, code=int(code), ptr=int(ptr), k_sel=ksel, norm1=n1,
                        lat_mismatch=mis, lat_min_margin=margin,
                        o1=float(at(t, r["v(xadc.o1p)"] - r["v(xadc.o1n)"], te0)),
                        o2=float(at(t, r["v(o2p)"] - r["v(o2n)"], te0)),
                        vo=float(at(t, r[VOP] - r[VON], te0)),
                        rst=bool(te0 < tl["t_afe"])))
        k += 1
    return out


def write_out_csv(d, r, t0, wstep):
    """the E2E columns on a uniform grid (pairs of time / value columns, as wrdata writes)"""
    t = r["time"]
    g = np.arange(t0, t[-1], wstep)
    cols = []
    for v in E2E_VEC:
        cols += [g, np.interp(g, t, r[v])]
    np.savetxt(os.path.join(d, "out.csv"), np.vstack(cols).T, fmt="%.9e")


def load(d):
    """the run's raw data on the absolute time axis (a two-stage run: tr.raw from t0)"""
    meta = json.load(open(os.path.join(d, "meta.json")))
    r = read_raw(os.path.join(d, "tr.raw"))
    r["time"] = r["time"] + meta.get("t0", 0.0)
    return meta, r


def check(d):
    meta, r = load(d)
    tl, variant = meta["timeline"], meta["variant"]
    t = r["time"]
    log = open(os.path.join(d, "run.log"), errors="replace").read()
    write_out_csv(d, r, max(tl["e0"] - 2e-6, 0.0), meta["wstep"])
    fr = frames(r, tl, variant)
    if fr:
        keys = list(fr[0])
        with open(os.path.join(d, "frames.csv"), "w") as f:
            f.write(" ".join(keys) + "\n")
            for x in fr:
                f.write(" ".join(str(int(v)) if isinstance(v, bool) else (f"{v:.6g}" if isinstance(v, float) else str(v))
                                 for v in x.values()) + "\n")
    bounds = [("static", 0.0, tl["t_reset"]), ("clocked reset", tl["t_reset"], tl["t_afe"]),
              ("converting", tl["t_afe"], tl["tstop"] + 1e-12)]
    t0 = meta.get("t0", 0.0)
    cost = phase_cost(d, t - t0, [(n, max(b0 - t0, 0.0), b1 - t0) for n, b0, b1 in bounds], meta.get("cpu_s"))
    for c, (n, b0, b1) in zip(cost, bounds):
        c["t0"], c["t1"] = b0, min(b1, float(t[-1]))
    st1 = None
    if meta.get("ramp"):
        # the power-on stage (ramp/): its cost belongs to the static phase
        dr = os.path.join(d, "ramp")
        r1 = read_raw(os.path.join(dr, "ramp.raw"))
        st1 = dict(meta["ramp"], t_end=t0, tol=meta.get("tol_ramp"),
                   rusage=rusage(open(os.path.join(dr, "run.log"), errors="replace").read()),
                   at_end={v: float(r1[v][-1]) for v in (AVDD, "v(dvddc)", VCM, "v(vbn_afe)", "v(vbn1)", "v(xb.gp)")
                           if v in r1})
        c = cost[0]
        c["cpu_s_main"], c["wall_s_main"] = c["cpu_s"], c["wall_s"]
        c["t0"], c["sim_us"] = 0.0, c["t1"] * 1e6
        c["cpu_s"] = (c["cpu_s"] if c["cpu_s"] == c["cpu_s"] else 0.0) + st1["cpu_s"]
        c["wall_s"] = (c["wall_s"] if c["wall_s"] == c["wall_s"] else 0.0) + st1["wall_s"]
        c["cpu_s_per_us"], c["wall_s_per_us"] = c["cpu_s"] / c["sim_us"], c["wall_s"] / c["sim_us"]
        c["points"], c["points_per_us"] = None, float("nan")
    s = dict(run=os.path.basename(d), sim_end=float(t[-1]), complete=bool(t[-1] >= tl["tstop"] * (1 - 1e-6)),
             exit=meta.get("exit"), wall_s=meta.get("wall_s"), cpu_s=meta.get("cpu_s"), rusage=rusage(log), phases=cost,
             power_on_stage=st1)
    # static phase: the state at the RESET_N release
    tr = tl["t_reset"]
    for v in (AVDD, AVSS, "v(avdd_afei)", "v(avss_afei)", "v(avdd_bias)", "v(avss_bias)", "v(dvddc)", VCM,
              "v(vcm_afe)", "v(vrefp_adc)", "v(vrefn_adc)", "v(vbn_afe)", "v(vbn_bias)", "v(vbcm_afe)", "v(bln_afe)",
              "v(blp_afe)", "v(vbn1)", "v(vnc1)", "v(vpc1)", "v(vbcm1)", "v(vbpc2)", "v(vbnc2)", "v(xb.gp)"):
        s.setdefault("at_reset", {})[v] = float(at(t, r[v], tr)) if v in r else float("nan")
    s["at_reset"]["vcm_drift_last_100us_uV"] = float((at(t, r[VCM], tr) - at(t, r[VCM], tr - 1e-4)) * 1e6)
    s["at_reset"]["i_avdd_mA"] = float(-at(t, r["i(vavdd)"], tr) * 1e3)
    s["at_reset"]["i_dvdd_mA"] = float(-at(t, r["i(vdvdd)"], tr) * 1e3) if "i(vdvdd)" in r else float("nan")
    vo = r[VOP] - r[VON]
    s["at_reset"]["afe_out_mV"] = float(at(t, vo, tr) * 1e3)
    s["at_reset"]["o1_mV"] = float(at(t, r["v(xadc.o1p)"] - r["v(xadc.o1n)"], tr) * 1e3)
    s["at_reset"]["o2_mV"] = float(at(t, r["v(o2p)"] - r["v(o2n)"], tr) * 1e3)
    # DAC1 latches before the first DAC_CLK (powered up undefined)
    tq = tl["e0"] + 3.5 * TM
    if lat_node(variant, 0) in r:
        vdd = at(t, r["v(dvddc)"] - r["v(dvssc)"], tq)
        q = np.array([at(t, r[lat_node(variant, j)], tq) for j in range(NSEL)])
        s["dac1_before_first_dac_clk"] = dict(high=int((q > vdd / 2).sum()),
                                              min_margin=float(np.abs(q - vdd / 2).min() / vdd),
                                              differ_from_sel=int(round(at(t, r["v(latmis)"], tq))) if "v(latmis)" in r else None)
    else:
        s["dac1_before_first_dac_clk"] = dict(high=None, min_margin=None, differ_from_sel=int(round(at(t, r["v(latmis)"], tq))))
    for name, sel in (("clocked reset", [x for x in fr if x["rst"]]), ("converting", [x for x in fr if not x["rst"]])):
        if not sel:
            continue
        c = np.array([x["code"] for x in sel])
        o2s = np.array([x["o2"] for x in sel])
        # the quantizer: the code against O2 at the strobe (slope in codes per mV, correlation)
        fit = (np.polyfit(o2s * 1e3, c, 1)[0], float(np.corrcoef(o2s, c)[0, 1])) if c.std() > 0 and o2s.std() > 0 \
            else (None, None)        # one code throughout (the integrators in reset): nothing to fit
        s.setdefault("frames", {})[name] = dict(
            n=len(sel), codes=c.tolist(), code_min=int(c.min()), code_max=int(c.max()),
            code_per_mV_o2=None if fit[0] is None else float(fit[0]), code_o2_corr=fit[1],
            k_sel_plus_code_ok=all(x["k_sel"] + x["code"] == 31 for x in sel),
            lat_mismatch_frames=sum(x["lat_mismatch"] > 0 for x in sel),
            lat_min_margin=min(x["lat_min_margin"] for x in sel),
            o1_mV=[min(x["o1"] for x in sel) * 1e3, max(x["o1"] for x in sel) * 1e3],
            o2_mV=[min(x["o2"] for x in sel) * 1e3, max(x["o2"] for x in sel) * 1e3],
            afe_out_mV=[min(x["vo"] for x in sel) * 1e3, max(x["vo"] for x in sel) * 1e3])
    # extremes over the converting phase (all points)
    m = t >= tl["t_afe"]
    if m.sum() > 2:
        o1 = r["v(xadc.o1p)"] - r["v(xadc.o1n)"]
        o2 = r["v(o2p)"] - r["v(o2n)"]
        s["converting_extremes_mV"] = dict(afe_out=[float(vo[m].min() * 1e3), float(vo[m].max() * 1e3)],
                                           o1=[float(o1[m].min() * 1e3), float(o1[m].max() * 1e3)],
                                           o2=[float(o2[m].min() * 1e3), float(o2[m].max() * 1e3)],
                                           o1_cm=[float(((r["v(xadc.o1p)"] + r["v(xadc.o1n)"]) / 2)[m].min()),
                                                  float(((r["v(xadc.o1p)"] + r["v(xadc.o1n)"]) / 2)[m].max())],
                                           o2_cm=[float(((r["v(o2p)"] + r["v(o2n)"]) / 2)[m].min()),
                                                  float(((r["v(o2p)"] + r["v(o2n)"]) / 2)[m].max())])
    # the E2E readout of tr_window.py (sine fits from 10 us after the AFE release)
    t0 = tl["t_afe"] + 10e-6
    if meta.get("amp") and t[-1] - t0 > 0.5 / meta["fsig"]:
        tw = os.path.join(REPO, "gf180", "tapeout", "sim", "e2e", "tr_window.py")
        # -W: numpy 2.0 on Apple's Accelerate flags divide-by-zero / overflow in tr_window's matmul
        # although every result is finite and equal to the plain sum (checked on this deck's runs)
        p = subprocess.run([sys.executable, "-W", "ignore::RuntimeWarning", tw, d, "--kind", "e2e", "--fsig",
                            f"{meta['fsig']:g}", "--t0", f"{t0:.9e}"], capture_output=True, text=True)
        s["tr_window"] = (p.stdout + p.stderr).strip()
    json.dump(s, open(os.path.join(d, "summary.json"), "w"), indent=1)
    report(s)
    return s


def report(s):
    print(f"{s['run']}: simulated to {s['sim_end'] * 1e3:.4f} ms ({'complete' if s['complete'] else 'INCOMPLETE'}), "
          f"wall {s['wall_s'] or 0:.0f} s, CPU {s['cpu_s'] or 0:.0f} s")
    ru = s["rusage"]
    if ru:
        print(f"  ngspice: {ru.get('Circuit Equations', 0):.0f} equations, {ru.get('Accepted timepoints', 0):.0f} accepted / "
              f"{ru.get('Rejected timepoints', 0):.0f} rejected points, {ru.get('Transient iterations', 0):.0f} iterations; "
              f"load {ru.get('Transient load time', 0):.0f} s, factor {ru.get('Transient factor time', 0):.0f} s, "
              f"solve {ru.get('Transient solve time', 0):.0f} s, trunc {ru.get('Transient trunc time', 0):.0f} s")
    st1 = s.get("power_on_stage")
    if st1:
        ru1 = st1["rusage"]
        print(f"  power-on stage to {st1['t_end'] * 1e3:.3f} ms ({st1['tol']} tolerances): CPU {st1['cpu_s']:.0f} s, wall "
              f"{st1['wall_s']:.0f} s, {ru1.get('Accepted timepoints', 0):.0f} accepted / {ru1.get('Rejected timepoints', 0):.0f} "
              f"rejected points, {ru1.get('Transient iterations', 0):.0f} iterations; then every node voltage and inductor "
              f"current handed to the main run")
    for p in s["phases"]:
        pts = f"{p['points']:7d} points ({p['points_per_us']:8.2f}/us)" if p["points"] is not None else "(two stages)"
        print(f"  {p['phase']:14s} {p['t0'] * 1e3:8.4f}..{p['t1'] * 1e3:8.4f} ms: {pts}, CPU {p['cpu_s']:7.0f} s "
              f"({p['cpu_s_per_us']:7.2f} s/us), wall {p['wall_s']:7.0f} s ({p['wall_s_per_us']:7.2f} s/us)")
    z = s["at_reset"]
    print(f"  at RESET_N: AVDD at the ADC / AFE / bias {z[AVDD] - z[AVSS]:.4f} / {z['v(avdd_afei)'] - z['v(avss_afei)']:.4f} / "
          f"{z['v(avdd_bias)'] - z['v(avss_bias)']:.4f} V, DVDD {z['v(dvddc)']:.4f} V, VCM at the ADC {z[VCM]:.5f} V "
          f"(drift {z['vcm_drift_last_100us_uV']:+.1f} uV / 100 us), VREFP / VREFN at the ADC {z['v(vrefp_adc)']:.4f} / "
          f"{z['v(vrefn_adc)']:.4f} V, I(AVDD) {z['i_avdd_mA']:.3f} mA, I(DVDD) {z['i_dvdd_mA']:.3f} mA")
    print(f"             bias VBN {z['v(vbn_afe)']:.4f} VBCM {z['v(vbcm_afe)']:.4f} BLN {z['v(bln_afe)']:.4f} BLP {z['v(blp_afe)']:.4f} "
          f"VBN1 {z['v(vbn1)']:.4f} VNC1 {z['v(vnc1)']:.4f} VPC1 {z['v(vpc1)']:.4f} VBCM1 {z['v(vbcm1)']:.4f} "
          f"VBPC2 {z['v(vbpc2)']:.4f} VBNC2 {z['v(vbnc2)']:.4f} V; AFE out {z['afe_out_mV']:+.2f} mV, O1 {z['o1_mV']:+.2f} mV, "
          f"O2 {z['o2_mV']:+.2f} mV")
    b = s["dac1_before_first_dac_clk"]
    if b["high"] is not None:
        print(f"  DAC1 latches before the first DAC_CLK: {b['high']} of 31 high, smallest distance from mid-rail "
              f"{b['min_margin'] * 100:.1f} % of DVDD" + (f", {b['differ_from_sel']} differ from SEL1" if b.get("differ_from_sel") is not None else ""))
    else:
        print(f"  DAC1 latches before the first DAC_CLK: {b['differ_from_sel']} differ from SEL1")
    for name, f in s.get("frames", {}).items():
        print(f"  {name}: {f['n']} frames, codes {f['code_min']}..{f['code_max']}, popcount(SEL1) = 31 - code "
              f"{'in every frame' if f['k_sel_plus_code_ok'] else 'NOT always'}, DAC1 latches != SEL1 in "
              f"{f['lat_mismatch_frames']} frames (smallest latch margin {f['lat_min_margin'] * 100:.0f} %), at the strobe O1 "
              f"{f['o1_mV'][0]:+.1f}..{f['o1_mV'][1]:+.1f} mV, O2 {f['o2_mV'][0]:+.1f}..{f['o2_mV'][1]:+.1f} mV, AFE out "
              f"{f['afe_out_mV'][0]:+.1f}..{f['afe_out_mV'][1]:+.1f} mV")
        c = f["codes"]
        print(f"    codes: {' '.join(map(str, c[:40]))}{' ...' if len(c) > 40 else ''}")
        if f["code_per_mV_o2"] is None:
            print(f"    code against O2 at the strobe: one code throughout (O2 held at {f['o2_mV'][0]:+.2f} mV), no fit")
        else:
            print(f"    code against O2 at the strobe: {f['code_per_mV_o2']:.3f} codes / mV, correlation {f['code_o2_corr']:.4f}")
    x = s.get("converting_extremes_mV")
    if x:
        print(f"  converting, all points: AFE out {x['afe_out'][0]:+.1f}..{x['afe_out'][1]:+.1f} mV, O1 {x['o1'][0]:+.1f}.."
              f"{x['o1'][1]:+.1f} mV (CM {x['o1_cm'][0]:.4f}..{x['o1_cm'][1]:.4f} V), O2 {x['o2'][0]:+.1f}..{x['o2'][1]:+.1f} mV "
              f"(CM {x['o2_cm'][0]:.4f}..{x['o2_cm'][1]:.4f} V)")
    if s.get("tr_window"):
        print("  tr_window.py --kind e2e:\n    " + s["tr_window"].replace("\n", "\n    "))


def plot(d):
    """overview.png in the run folder: the static phase (supplies, VCM, references, bias,
    supply currents) and the clocked window (AFE output, O1, O2, DAC1 level, controls)"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    meta, r = load(d)
    tl = meta["timeline"]
    if meta.get("ramp"):
        r1 = read_raw(os.path.join(d, "ramp", "ramp.raw"))
        r = {k: np.concatenate([r1[k][r1["time"] < r["time"][0]], v]) for k, v in r.items() if k in r1}
    t = r["time"]
    fig, ax = plt.subplots(4, 2, figsize=(15, 13))
    ms = t * 1e3
    a = ax[0, 0]
    for v in (AVDD, "v(avdd_afei)", "v(dvddc)", VCM, "v(vrefp_adc)", "v(vrefn_adc)"):
        if v in r:
            a.plot(ms, r[v], label=v)
    a.set_title("supplies, VCM, references (V)")
    a = ax[1, 0]
    for v in ("v(vbn_afe)", "v(vbcm_afe)", "v(bln_afe)", "v(blp_afe)", "v(vbn1)", "v(vnc1)", "v(vpc1)", "v(vbcm1)",
              "v(xb.gp)"):
        if v in r:
            a.plot(ms, r[v], label=v)
    a.set_title("bias (V)")
    a = ax[2, 0]
    a.plot(ms, -r["i(vavdd)"] * 1e3, label="I(AVDD regulator)")
    if "i(vdvdd)" in r:
        a.plot(ms, -r["i(vdvdd)"] * 1e3, label="I(DVDD regulator)")
    a.set_title("supply currents (mA)")
    a = ax[3, 0]
    a.plot(ms, (r[VCM] - 1.65) * 1e3, label="VCM at the ADC - 1.65 V (mV)")
    a.plot(ms, (r[VOP] + r[VON]) / 2 * 1e3 - 1650, label="AFE output CM - 1.65 V (mV)")
    a.set_ylim(-50, 50)
    a.set_title("VCM settling")
    m = t >= tl["e0"] - 2e-6
    us = (t[m] - tl["t_afe"]) * 1e6
    a = ax[0, 1]
    a.plot(us, (r[VOP] - r[VON])[m] * 1e3, lw=0.6)
    a.set_title("AFE output OUTP - OUTN (mV) vs time from the AFE release (us)")
    a = ax[1, 1]
    a.plot(us, (r["v(xadc.o1p)"] - r["v(xadc.o1n)"])[m] * 1e3, lw=0.6, label="O1")
    a.plot(us, (r["v(o2p)"] - r["v(o2n)"])[m] * 1e3, lw=0.6, label="O2")
    a.set_title("integrator outputs (mV)")
    a = ax[2, 1]
    a.plot(us, (r["v(norm1)"][m] + 0.5) * 31, lw=0.8, label="popcount(SEL1)")
    if lat_node(meta["variant"], 0) in r:
        q = sum((r[lat_node(meta["variant"], j)] > (r["v(dvddc)"] + r["v(dvssc)"]) / 2).astype(float) for j in range(NSEL))
        a.plot(us, q[m], lw=0.8, ls="--", label="DAC1 latches high")
    if "v(latmis)" in r:
        a.plot(us, r["v(latmis)"][m], lw=0.6, color="k", label="DAC1 latches != SEL1")
    if meta.get("amp"):
        a2 = a.twinx()
        a2.plot(us, r["v(sig)"][m] * 1e3, color="0.6", lw=0.6)
    a.set_title("DAC1: selected elements and latch states")
    a = ax[3, 1]
    for k, v in enumerate(("v(afe_rst)", "v(chop)", "v(chop_blank)", "v(cmp_strobe)", "v(dac_clk)", "v(chop1)")):
        if v in r:
            a.plot(us, r[v][m] / 3.3 + 1.2 * k, lw=0.6, label=v)
    a.set_title("controls (offset per trace)")
    for a in ax.flat:
        a.grid(alpha=0.3)
        if a.get_legend_handles_labels()[0]:
            a.legend(fontsize=7, loc="best")
    fig.tight_layout()
    fig.savefig(os.path.join(d, "overview.png"), dpi=90)
    print(os.path.join(d, "overview.png"))


def cic(d):
    """The RTL's decimator on the run's codes: the stream from the first frame after the AFE
    release (the firmware's CONTROL write clears AFE_RST and sets RUN | FILTER_CLEAR in one
    commit, so the clear lands in the release frame, as in tb_e2e.sv), through the bit-exact
    model of eeg_cic3 (gf180/tapeout/rtl/model/cic_golden.py: R = 1024, sinc^3, 37 bit, round
    half even by 2^12, the first two strobes after the clear invalid). Writes e2e.codes (one
    byte per frame) and e2e.gold (the valid outputs, 24-bit hex), the inputs of the RTL's own
    end-to-end test (tb_e2e.sv: TH from the codes, SPI reads checked bit-exact against the
    golden file), and prints the strobes and the command for that test."""
    rtl = os.path.join(REPO, "gf180", "tapeout", "rtl")
    sys.path.insert(0, os.path.join(rtl, "model"))
    import cic_golden as g
    meta = json.load(open(os.path.join(d, "meta.json")))
    rows = open(os.path.join(d, "frames.csv")).read().split("\n")
    keys = rows[0].split()
    fr = [dict(zip(keys, ln.split())) for ln in rows[1:] if ln.strip()]
    k0 = meta["timeline"]["afe_frame"] + 1
    ks = [int(x["frame"]) for x in fr if int(x["frame"]) >= k0]
    if ks != list(range(k0, k0 + len(ks))):
        gaps = sorted(set(range(k0, k0 + len(ks))) ^ set(ks))
        print(f"  WARNING: the frames from {k0} are not contiguous (missing or repeated: {gaps[:10]}); the stream below "
              f"is misaligned")
    codes = bytes(int(x["code"]) for x in fr if int(x["frame"]) >= k0)
    open(os.path.join(d, "e2e.codes"), "wb").write(codes)
    outs, st = g.cic3_run(codes)
    valid = [x for x, v in outs if v]
    open(os.path.join(d, "e2e.gold"), "w").write("".join(f"{x & 0xFFFFFF:06x}\n" for x in valid))
    print(f"{d}: {len(codes)} frames from frame {k0} (the first after the AFE release), {len(outs)} CIC strobes, "
          f"{len(valid)} valid (the first valid one needs {g.R * (g.NSKIP + 1)} frames)")
    for k, (x, v) in enumerate(outs):
        print(f"  strobe {k}: DATA {x:+9d} ({x / (31 * 2 ** 18):+.6f} of full scale){'' if v else '  (invalid: partial window)'}")
    if valid:
        # the RTL itself (run_e2e.sh's compile and tb_e2e): TH from the codes, the samples read over SPI
        files = ("eeg_clkgen.sv eeg_chop1.sv eeg_therm2bin.sv eeg_dwa.sv eeg_rnd_sat.sv eeg_cic3.sv eeg_fifo.sv eeg_regs.sv "
                 "eeg_spi_slave.sv eeg_raw.sv eeg_digital_top.sv eeg_adc_dig.sv eeg_digital_sys.sv tb/tb_e2e.sv").split()
        vvp = os.path.join(d, "tb_e2e.vvp")
        p = subprocess.run(["iverilog", "-g2012", "-Wall", "-I", "tb", "-o", vvp, "-s", "tb_e2e"] + files, cwd=rtl,
                           capture_output=True, text=True)
        if p.returncode:
            print("  RTL compile failed:\n" + p.stdout + p.stderr)
            return
        p = subprocess.run(["vvp", "-n", vvp, f"+codes={d}/e2e.codes", f"+gold={d}/e2e.gold", f"+nsamp={len(valid)}",
                            f"+out={d}/e2e.samples"], cwd=rtl, capture_output=True, text=True)
        res = [ln for ln in (p.stdout + p.stderr).splitlines() if ln.startswith(("PASS", "FAIL"))]
        print("  RTL (tb_e2e.sv, Icarus): " + (res[0] if res else "no PASS/FAIL line, see the vvp output"))


def lean_series(d, names):
    """a chained run's lean vectors (chunk_*/lean.npz) on one time axis (absolute time; the
    point repeated at each chunk boundary dropped)"""
    out = {k: [] for k in ["time"] + list(names)}
    tlast = -1.0
    for p in sorted(os.listdir(d)):
        f = os.path.join(d, p, "lean.npz")
        if not (p.startswith("chunk_") and os.path.exists(f)):
            continue
        z = np.load(f)
        m = z["time"] > tlast
        for q in out:       # a vector a chunk did not keep (added to LEAN_KEEP later): nan
            out[q].append(z[q][m] if q in z.files else np.full(int(m.sum()), np.nan))
        tlast = float(z["time"][-1])
    return {q: np.concatenate(v) for q, v in out.items()}


def cic_weights():
    """eeg_cic3 as an FIR filter: the output at the n-th accepted input (n = R (j + 1) - 1 for
    strobe j) is sum_k h[n - k] x[k] / 2^12 (before rounding) with h = z^-2 (box_R)^3; the
    pipelined integrators add the delay of 2 inputs. sum h = R^3 = 2^30."""
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "rtl", "model"))
    import cic_golden as g
    b = np.ones(g.R)
    return np.concatenate([[0.0, 0.0], np.convolve(np.convolve(b, b), b)])


def ct2_frames(u):
    """codes of the behavioral loop of the RTL's end-to-end test (rtl/model/ct2_codes.py: ideal
    DAC elements, finite OTA gains, no noise) for the per-frame ADC input u (V, held over each
    frame), from both integrators at 0 and the controller's reset state (code 15, 16 elements)"""
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "rtl", "model"))
    import ct2_codes as c2
    t = c2.m.T
    sa = c2.segment(c2.E_DAC2 / 32 * t)
    sb = c2.segment((c2.E_DAC1 - c2.E_DAC2) / 32 * t)
    sc = c2.segment((32 - c2.E_DAC1) / 32 * t)
    a00, a01, a10, a11, ba00, ba01, ba02, ba10, ba11, ba12 = sa
    b00, b01, b10, b11, bb00, bb01, bb02, bb10, bb11, bb12 = sb
    c00, c01, c10, c11, bc00, bc01, bc02, bc10, bc11, bc12 = sc
    ka1, ka2, kc1, kc2 = ba01 + ba02, ba11 + ba12, bc01 + bc02, bc11 + bc12
    thr = [float(v) for v in c2.m.THR]
    import bisect
    codes, x1 = [], 0.0
    x2, yp, x1max, x2max = 0.0, 1.0 - 2.0 * 16 / 31.0, 0.0, 0.0
    for uu in map(float, u):
        p1 = a00 * x1 + a01 * x2 + ba00 * uu + ka1 * yp
        p2 = a10 * x1 + a11 * x2 + ba10 * uu + ka2 * yp
        c = bisect.bisect_left(thr, x2)
        codes.append(c)
        y = (2.0 * c - 31.0) / 31.0
        q1 = b00 * p1 + b01 * p2 + bb00 * uu + bb01 * yp + bb02 * y
        q2 = b10 * p1 + b11 * p2 + bb10 * uu + bb11 * yp + bb12 * y
        x1 = c00 * q1 + c01 * q2 + bc00 * uu + kc1 * y
        x2 = c10 * q1 + c11 * q2 + bc10 * uu + kc2 * y
        yp = y
        x1max, x2max = max(x1max, abs(x1)), max(x2max, abs(x2))
    return codes, x1max, x2max


def expect(d):
    """The run's CIC samples against what its own ADC input predicts, and the codes and integrator
    ranges of the converting phase. Per frame from the clear (the first frame after the AFE
    release): u = the ADC input OUTP_ADC - OUTN_ADC averaged over the frame (e0 to e0), s = the
    electrode signal averaged the same way. Per strobe: the sinc^3-weighted means of u and s (the
    weights of eeg_cic3, cic_weights()), and three expectations of DATA: 2^24 u (a unity-gain
    ADC: NORM1 x 0.96875 V = input, DATA = 2^18 mean(2c - 31)), the bit-exact CIC on the codes of
    the behavioral loop (ct2_frames) driven by the same u, and 2^24 x 0.3 mV-style electrode
    value x the run's own gain. A chained run reads its chunks' lean vectors."""
    sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "rtl", "model"))
    import cic_golden as g
    meta = json.load(open(os.path.join(d, "meta.json")))
    tl = meta["timeline"]
    k0 = tl["afe_frame"] + 1
    fr = [x for x in read_frames(os.path.join(d, "frames.csv")) if x["frame"] >= k0]
    if [x["frame"] for x in fr] != list(range(k0, k0 + len(fr))):
        print(f"  WARNING: the frames from {k0} are not contiguous; only the contiguous start is used")
        fr = fr[:next((i for i, x in enumerate(fr) if x["frame"] != k0 + i), len(fr))]
    codes = [x["code"] for x in fr]
    names = ["v(sig)", VOP, VON, "v(xadc.o1p)", "v(xadc.o1n)", "v(o2p)", "v(o2n)"]
    if os.path.exists(os.path.join(d, "tr.raw")):
        _, r = load(d)
    else:
        r = lean_series(d, names)
    t = r["time"]
    cum = lambda y: np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])
    e = tl["e0"] + (k0 + np.arange(len(codes) + 1)) * T
    e = e[e <= t[-1]]
    n = len(e) - 1
    u = np.diff(np.interp(e, t, cum(r[VOP] - r[VON]))) / T
    s = np.diff(np.interp(e, t, cum(r["v(sig)"]))) / T
    codes = codes[:n]
    ci, x1max, x2max = ct2_frames(u)
    outs_a, st_a = g.cic3_run(bytes(codes))
    outs_i, _ = g.cic3_run(bytes(ci))
    h = cic_weights()
    xs = 2.0 * np.array(codes) - 31.0
    print(f"{d}: {n} frames from frame {k0} (the first after the AFE release at {tl['t_afe'] * 1e3:.6f} ms), "
          f"{len(outs_a)} CIC strobes")
    print("  strobe  frames weighted (strobe)  DATA (RTL model)   2^24 u_w   ideal loop   DATA/2^24u_w-1  u_w (mV)  "
          "s_w (mV)  gain u_w/s_w  DATA/(2^24 s_w)")
    for j, ((da, va), (di, _)) in enumerate(zip(outs_a, outs_i)):
        nn = g.R * (j + 1) - 1
        lo = max(0, nn - len(h) + 1)
        w = h[nn - np.arange(lo, nn + 1)]
        fir = float(np.dot(w, xs[lo:nn + 1]) / 2 ** g.SH)
        uw, sw = float(np.dot(w, u[lo:nn + 1]) / w.sum()), float(np.dot(w, s[lo:nn + 1]) / w.sum())
        ok = abs(fir - da) <= 0.5 + 1e-9 if va else True
        print(f"  {j:2d}{'  ' if va else ' *'}  {k0 + lo:5d}..{k0 + nn - 2:5d} ({k0 + nn:5d})  {da:+10d}{'' if ok else ' (FIR!)'}  "
              f"{2 ** 24 * uw:+11.0f}  {di:+11d}  {da / (2 ** 24 * uw) - 1:+.3e}  {uw * 1e3:+9.4f} {sw * 1e3:+9.5f}  "
              f"{uw / sw if sw else float('nan'):10.3f}  {da / (2 ** 24 * sw) if sw else float('nan'):10.3f}")
    print("  (* invalid: the first two strobes after the clear; 2^24 u_w: a unity-gain ADC on the weighted ADC input; "
          "ideal loop: rtl/model/ct2_codes.py's loop on u)")
    print(f"  CIC registers (model): wraps i1/i2/i3 {st_a['wrap_i1']}/{st_a['wrap_i2']}/{st_a['wrap_i3']}, combs "
          f"{st_a['wrap_c1']}/{st_a['wrap_c2']}/{st_a['wrap_c3']}, saturated {st_a['saturated']}")
    c = np.array(codes)
    hist = np.bincount(c, minlength=32)
    print(f"  codes: {c.min()}..{c.max()} (0 / 31: {hist[0]} / {hist[31]} frames), mean 2c-31 {xs.mean():+.4f}; "
          f"by ms: " + ", ".join(f"{xs[i:i + 1024].mean():+.3f} [{c[i:i + 1024].min()}..{c[i:i + 1024].max()}]"
                                 for i in range(0, n, 1024)))
    print(f"  ideal loop codes {min(ci)}..{max(ci)}, peak |O1| {x1max * 1e3:.1f} mV, |O2| {x2max * 1e3:.1f} mV; "
          f"codes equal to the run's in {sum(a == b for a, b in zip(codes, ci))} of {n} frames")
    m = t >= tl["t_afe"]
    o1 = r["v(xadc.o1p)"] - r["v(xadc.o1n)"]
    o2 = r["v(o2p)"] - r["v(o2n)"]
    vin = r[VOP] - r[VON]
    f1 = np.array([x["o1"] for x in fr[:n]])
    f2 = np.array([x["o2"] for x in fr[:n]])
    print(f"  converting, all points: ADC input {vin[m].min() * 1e3:+.1f}..{vin[m].max() * 1e3:+.1f} mV, O1 "
          f"{o1[m].min() * 1e3:+.1f}..{o1[m].max() * 1e3:+.1f} mV (CM {((r['v(xadc.o1p)'] + r['v(xadc.o1n)']) / 2)[m].min():.4f}.."
          f"{((r['v(xadc.o1p)'] + r['v(xadc.o1n)']) / 2)[m].max():.4f} V), O2 {o2[m].min() * 1e3:+.1f}..{o2[m].max() * 1e3:+.1f} mV "
          f"(CM {((r['v(o2p)'] + r['v(o2n)']) / 2)[m].min():.4f}..{((r['v(o2p)'] + r['v(o2n)']) / 2)[m].max():.4f} V)")
    print(f"  at the strobe: O1 {f1.min() * 1e3:+.1f}..{f1.max() * 1e3:+.1f} mV, O2 {f2.min() * 1e3:+.2f}..{f2.max() * 1e3:+.2f} mV "
          f"(thresholds -46.875..+46.875 mV), DAC1 latches != SEL1 in {sum(x['lat_mismatch'] > 0 for x in fr[:n])} frames")
    return dict(codes=codes, u=u, s=s, outs=outs_a, outs_ideal=outs_i)


def parse_cap(c):
    vals = {"p": 1e-12, "n": 1e-9, "u": 1e-6}
    return float(c[:-1]) * vals[c[-1]] if c[-1] in vals else float(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["run", "chain", "deck", "check", "plot", "cic", "expect", "compare", "status"])
    ap.add_argument("folder", nargs="?", help="check / plot / cic / compare: the run folder")
    ap.add_argument("folder2", nargs="?", help="compare: the other run folder")
    ap.add_argument("--from-t", type=float, default=0.0, help="compare: frames from this time (s)")
    ap.add_argument("--cvcm", nargs="+", default=["10n"], help="off-chip capacitance on the VCM pad")
    ap.add_argument("--vdd", type=float, default=3.3)
    ap.add_argument("--tramp", type=float, default=1e-3, help="supply ramp time (s)")
    ap.add_argument("--corner", default="typical", choices=list(S.MOSF))
    ap.add_argument("--mc", nargs="+", type=int, default=None, help="Monte Carlo seeds (process + mismatch)")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--moscap", choices=["lin", "pdk"], default="lin")
    ap.add_argument("--variant", choices=["pex", "sch"], default="pex", help="afe_top and eeg_adc extracted or schematics")
    ap.add_argument("--chip", choices=["fill", "nofill", "highr"], default="fill",
                    help="chip wiring (afe_startup.chip_model: pex_chipnets' models); sch: ideal")
    ap.add_argument("--rafe", type=float, nargs=2, default=list(S.RAFE),
                    help="afe_top's own AVSS / AVDD rails (ohm, afe_startup.RAFE)")
    ap.add_argument("--mim-a", type=float, default=1.41, help="Monte Carlo: MIM mismatch (%%·um, afe_startup)")
    ap.add_argument("--res-a", type=float, default=3.0, help="Monte Carlo: poly-resistor mismatch (%%·um, afe_startup)")
    ap.add_argument("--vin", type=float, default=0.0, help="electrode DC offset (mV); the offset DAC is set for it")
    ap.add_argument("--dc", type=float, default=0.0, help="electrode DC signal (mV), the offset DAC off")
    ap.add_argument("--amp", type=float, default=0.0, help="electrode sine amplitude (mV pk)")
    ap.add_argument("--fsig", type=float, default=16e3, help="sine frequency (Hz)")
    ap.add_argument("--t-sig", type=float, default=None, help="sine start (s); default the AFE release")
    ap.add_argument("--chop1", type=float, default=4e3, help="OTA1 chopper (Hz, CHOP1 register), 0 = off")
    ap.add_argument("--dac2-sel", choices=["dwa", "therm"], default="dwa",
                    help="DAC2 selection: dwa (RTL: SEL2 = SEL1) or therm (the older E2E decks)")
    ap.add_argument("--t-reset", type=float, default=None, help="RESET_N released (s); default t-afe - 0.2 ms")
    ap.add_argument("--t-afe", type=float, default=5e-3, help="AFE_RST cleared (s): the CONTROL write")
    ap.add_argument("--ibias", type=int, default=2, choices=range(4),
                    help="AFE_IBIAS code the firmware writes after RESET_N (2: the reset value, no write)")
    ap.add_argument("--t-write", type=float, default=20e-6, help="the AFE_IBIAS write, after RESET_N (s)")
    ap.add_argument("--tstop", type=float, default=None, help="default t-afe + 50 us")
    ap.add_argument("--tstep", type=float, default=10e-9)
    ap.add_argument("--tmax", type=float, default=10e-6, help="largest time step (the clocks' edges set it while they run)")
    ap.add_argument("--tol", choices=sorted(TOLS), default="fast")
    ap.add_argument("--t-handoff", type=float, default=0.0,
                    help="two stages: power-on to this time (s, before frame 0), then the main run from its last point "
                         "(every node voltage and inductor current); 0 (default) = one run from power-on")
    ap.add_argument("--tol-ramp", choices=sorted(TOLS), default="fast", help="tolerances of the power-on stage")
    ap.add_argument("--solver-ramp", choices=["klu", "sparse"], default="sparse", help="solver of the power-on stage")
    ap.add_argument("--reuse-ramp", action="store_true",
                    help="start from the power-on stage of an earlier run of the same name (ramp/ramp.raw)")
    ap.add_argument("--solver", choices=["klu", "sparse"], default="sparse",
                    help="sparse (Sparse 1.3, pivots at every factorization): KLU's refactorization keeps the first "
                         "pivot order, and on this deck (pads, board, chip wiring next to the extracted blocks) Newton "
                         "then needs 15-40 iterations per point instead of 3, 10-50x slower")
    ap.add_argument("--xtrtol", type=int, default=7, help="trtol with the XSPICE devices (ngspice would use 1); 0 = ngspice's")
    ap.add_argument("--wstep", type=float, default=20e-9, help="out.csv grid")
    ap.add_argument("--save", choices=["full", "lean"], default="full",
                    help="saved vectors: full (122, short runs) or lean (25, ms-long runs; DAC1 latches as LATMIS)")
    ap.add_argument("--save-th", action="store_true", help="also save TH0..30")
    ap.add_argument("--tag", default="")
    ap.add_argument("--jobs", type=int, default=1, help="parallel runs (at most 2)")
    ap.add_argument("--chunk-first", type=float, default=None,
                    help="chain: the first chunk boundary (s, moved to e20 of its frame); default 0.1 ms after RESET_N")
    ap.add_argument("--chunk-frames", type=int, default=100, help="chain: frames per chunk after the first")
    ap.add_argument("--bounds", type=float, nargs="+", default=None, help="chain: explicit chunk boundaries (s)")
    ap.add_argument("--keep-raw", action="store_true", help="chain: keep each chunk's raw file (every node, ~62 MB/us)")
    a = ap.parse_args()
    if a.what in ("check", "plot", "cic", "expect", "status"):
        {"check": check, "plot": plot, "cic": cic, "expect": expect, "status": status}[a.what](a.folder)
        return
    if a.what == "compare":
        compare(a.folder, a.folder2, a.from_t)
        return
    a.t_reset = a.t_afe - 0.2e-3 if a.t_reset is None else a.t_reset
    a.tstop = a.t_afe + 50e-6 if a.tstop is None else a.tstop
    jobs = []
    for c in a.cvcm:
        for seed in (a.mc if a.mc else [None]):
            b = copy.copy(a)
            b.cvcm = parse_cap(c)
            jobs.append((b, seed))
    if a.what == "deck":
        for b, seed in jobs:
            print(prepare(b, seed)[0])
        return
    if a.what == "chain":
        for b, seed in jobs:
            if b.chunk_first is None:
                b.chunk_first = timeline(b)["t_reset"] + 0.1e-3
            ok = chain(b, seed)
            print(f"{run_name(b, seed)}_chain: {'done' if ok else 'stopped (see progress.log, failure.json)'}", flush=True)
        return
    with ThreadPoolExecutor(min(max(a.jobs, 1), 2, len(jobs))) as ex:
        for d, ok, dt in ex.map(lambda j: run(*j), jobs):
            print(f"{d}: {'ok' if ok else 'FAILED (see run.log)'} ({dt:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
