#!/usr/bin/env python3
"""The digital side of the chip in the E2E deck: the nine digital pads and the two digital
macros' supply current, and what they do to the AFE and the ADC (written 11/8).

The E2E chain (e2e_startup.py) has the analog pads, the pad ring and the board, but the
digital block draws no supply current, the nine bi_24t pads are missing, and every digital
signal is an ideal source between the ring's DVDDC and DVSSC. This adds, to a copy of one of
the chain's chunk decks:

  - Chip-level DVDD / DVSS from the ring to the blocks, as a star (supply_check.py, r8/r9:
    pads -> digital block 0.19 / 1.12 ohm, -> the DVDD-DVSS decoupling 0.67 / 1.50 ohm, -> the
    ADC's DVDD / DVSS 4.32 / 1.41 ohm). The 48 decoupling units (XDECD) move onto their own
    node.
  - Each macro's own VDD-VSS capacitance: its cells from the PDK netlists in ngspice AC
    (digital/power/cell_decap: eeg_digital_top 92 pF, of it 35 pF fillcap; eeg_adc_dig 26 pF)
    plus an estimate of the n-well junction (MACRO_C), with a series resistance.
  - Each macro's supply current: the charge per MCLK edge from the gate-level power run
    (digital/power/current_profile.py: OpenSTA with the VCD activity, the liberty's split of
    the flip-flops' clock energy between the edges, the clock tree's polarity, the data nets'
    switched capacitance by frame cycle), each charge a triangle of --tw (default 2 ns)
    starting --lead (2 ns) before the deck's output edges, repeated every frame.
  - The nine bi_24t pads (the PDK's transistor netlist, the chip's tie-offs from chip_lay.DPAD)
    on the ring, each through a bond wire (2 nH, 0.1 ohm, 20 ohm damping) to the board: MCLK
    from a 3.3 V oscillator (1.5 ns edges, 33 ohm, 3 pF of trace) whose edge is 4 ns ahead of the
    outputs; RESET_N, CS_N high and SCLK, MOSI low from the host (33 ohm); MISO, DRDY_N,
    RAW_DATA, RAW_CLK into 8 pF of board load each.
  - Every signal the macros drive (the AFE's and the bias block's controls and register bits,
    the ADC's strobes and its DAC selections, the XSPICE controller) swings between its own
    macro's rails, and the ADC block's DVDD / DVSS are its own node.

Cases (each a folder in runs/digital_noise/):
  b1     the normal measurement: MCLK running, the host idle, RAW off (RAW_EN = 0)
  b1iso  the same sources and pads on a separate copy of the ring (its own supply, nothing in
         common with the chip): the same events for the simulator, no coupling. b1 - b1iso is
         the coupling; b1iso - the chain's own chunk is the numerical noise of the extra events
  b2     b1 with the host reading a sample over SPI (2 MHz, 48 bits, 8..34 us into the window)
  b3     b1 with the raw debug stream on (RAW_CLK = MCLK / 4, RAW_DATA random)
  A      (--adc only) the base deck itself over the window: the reference in place of the chain's own chunk

Not in it: the substrate between DVSS and AVSS (the chip joins them through it), resistance
inside the blocks, the chip-level wiring of the control lines (the deck's sources stay ideal
edges at the block pins), glitches (zero-delay activity).

usage:
  /usr/bin/python3 gf180/tapeout/pex/digital_noise.py small [--tw 2e-9]   ring bounce, small deck
  /usr/bin/python3 gf180/tapeout/pex/digital_noise.py make [cases]        write the decks
  /usr/bin/python3 gf180/tapeout/pex/digital_noise.py run [cases]         start them (background)
  /usr/bin/python3 gf180/tapeout/pex/digital_noise.py compare [cases]     against the chain's chunk ('A'): the AFE
        output per chopper period, split into offset + the electrode's 16 kHz tone + rest; the ADC's codes; the
        rails; the AFE input's p-p (runs/digital_noise/compare.json)
  --adc r10 (base / make / run / compare): the same decks with the 10th chip's eeg_adc extraction
        (runs/adc_top_c_r10) in place of the chain's (r7's), in runs/digital_noise_r10/. 'base' writes its
        base_chunk014 (the chain's chunk 14 deck with that eeg_adc), and its 'A' is a run of that deck over the
        window (make / run A ... b3), not the chain's own chunk
  --chain r12 (base / make / run / compare, 11/16): the 12th chip's own chain (afe_top and eeg_adc of r12's
        extraction on chipnets_r12) in place of r9's, in runs/digital_noise_r12/. 'base' copies its chunk 14 deck
        (the same window, 6.1735 ms on, and the same element names as r9's); 'A' is that chain's own chunk, as for
        r9. The chip-level DVDD / DVSS (R_DIST) are r12's too: its supply check gives r9's values to the mΩ
  --nice n (run): below the chain's priority
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RUNS = os.path.join(HERE, "runs", "digital_noise")
BASE = os.path.join(RUNS, "base_chunk014")
PROFILE = os.path.join(REPO, "gf180", "tapeout", "digital", "power", "build", "current_profile.json")
CHAIN = os.path.join(HERE, "runs", "e2e_startup",
                     "c1e-08_v3.3_typical_+0mV_dc+0.3mV_ib3_sine0.5mV16000Hz_rst4.8_afe5_to10.002ms_r9_chain")
NGSPICE = "/opt/homebrew/bin/ngspice"
VDD = 3.3
T = 1.0 / 32.768e6                  # MCLK
TF = 32 * T                         # modulator frame
TCH = 8 * TF                        # chopper period (128 kHz)
# chip-level DVDD / DVSS, ring -> block (supply_check.py, documentation/gf180_chip_assembly_20261023.md)
R_DIST = {"DIG": (0.19, 1.12), "DEC": (0.67, 1.50), "ADD": (4.32, 1.41)}
# the macros' own VDD-VSS capacitance (F) and its series resistance (ohm): the cells (cell_decap,
# inputs low / high averaged) plus the n-well junction (rows' n-well strips, nw2ps_06v0 at 3.3 V)
MACRO_C = {"DIG": (92.4e-12 + 25e-12, 0.5), "ADD": (25.6e-12 + 8e-12, 1.5)}
MACRO_OF = {"DIG": "eeg_digital_top", "ADD": "eeg_adc_dig"}
# the chip's digital pads (chip_lay.DPAD): name, tie-offs (1 = DVDD, 0 = DVSS, else a signal)
DPAD = [("MCLK", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=0)),
        ("RESET_N", dict(A=0, OE=0, IE=1, CS=1, SL=0, PU=1, PD=0)),
        ("SCLK", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=1)),
        ("CS_N", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=1, PD=0)),
        ("MOSI", dict(A=0, OE=0, IE=1, CS=0, SL=0, PU=0, PD=1)),
        ("MISO", dict(A="U_MISO", OE="U_MISO_OE", IE=0, CS=0, SL=1, PU=0, PD=0)),
        ("DRDY_N", dict(A="U_DRDY_N", OE=1, IE=0, CS=0, SL=1, PU=0, PD=0)),
        ("RAW_DATA", dict(A="U_RAW_DATA", OE=1, IE=0, CS=0, SL=1, PU=0, PD=0)),
        ("RAW_CLK", dict(A="U_RAW_CLK", OE=1, IE=0, CS=0, SL=1, PU=0, PD=0))]
BI_PORTS = "A CS DVDD DVSS IE OE PAD PD PU SL VDD VSS Y".split()
HOST_LEVEL = {"RESET_N": 1, "CS_N": 1, "SCLK": 0, "MOSI": 0}
C_BOARD_OUT = 8e-12
PAD_SKEW = 0.125e-9                 # b2, b3: the core's drive of the output pads (A, OE) after the chip's clock grid (s)
# the deck's digital-sourced lines: by the B source's name, which macro drives it
FROM_DIG = {"BIB1", "BIB0", "BBP1", "BBP0", "BBN1", "BBN0", "BCHEN", "BAZ", "BCMP", "BDCK", "BCHOP",
            "BCHOPO", "BBLK", "BCH1", "BRST"}
CASES = ("b1", "b1iso", "b2", "b3")
# --adc: the decks with another extraction of eeg_adc (use_adc). "" = the chain's own, runs/adc_top_c_r7 (adc_top last
# changed in r7: pex_e2e._ADC_REV)
ADC_REV = ""
ADC_PEX = {"r10": os.path.join(HERE, "runs", "adc_top_c_r10", "eeg_adc_pex.spice")}
BASE0 = BASE                            # the chain's chunk deck, copied (r7's eeg_adc)
SMALL = os.path.join(RUNS, "small")     # the pads' operating point (op_pads.json): the same for every eeg_adc
# --chain: another chip's own chain ("" = r9's, CHAIN above)
CHAINS = {"r12": os.path.join(HERE, "runs", "e2e_startup",
                              "c1e-08_v3.3_typical_+0mV_dc+0.3mV_ib3_sine0.5mV16000Hz_rst4.8_afe5_to10.002ms_r12_chain")}
CHAIN_REV = ""


def use_chain(rev):
    """the decks on chip <rev>'s own chain (its chunk 14), in runs/digital_noise_<rev>/ (CHAIN, RUNS, BASE)"""
    global CHAIN_REV, CHAIN, RUNS, BASE, BASE0
    if not rev:
        return
    CHAIN_REV, CHAIN = rev, CHAINS[rev]
    RUNS = os.path.join(HERE, "runs", f"digital_noise_{rev}")
    BASE = BASE0 = os.path.join(RUNS, "base_chunk014")


def copy_chain_base():
    """BASE of use_chain(rev): the chain's chunk 14 deck, quantizer and events as they are"""
    src = os.path.join(CHAIN, "chunk_014")
    os.makedirs(BASE, exist_ok=True)
    for f in ("tb.spice", "quantizer.spice", "events.txt"):
        open(os.path.join(BASE, f), "w").write(open(os.path.join(src, f)).read())
    return BASE


def use_adc(rev):
    """the decks with eeg_adc from ADC_PEX[rev], in runs/digital_noise_<rev>/ (BASE, RUNS); "" = the chain's own"""
    global ADC_REV, RUNS, BASE
    ADC_REV = rev or ""
    RUNS = os.path.join(HERE, "runs", "digital_noise" + (f"_{rev}" if rev else ""))
    BASE = os.path.join(RUNS, "base_chunk014")


def element_nodes(block):
    """{element: its nodes} of a flat subckt body (X: the nodes before the model; R, C, L: two)"""
    out = {}
    for ln in block.splitlines():
        if not ln or ln[0] in "*.+":
            continue
        t = ln.split()
        k = t[0][0].upper()
        if k == "X":
            out[t[0]] = [x.lower() for x in t[1:] if "=" not in x][:-1]
        elif k in "CRL":
            out[t[0]] = [x.lower() for x in t[1:3]]
    return out


def make_base():
    """BASE of use_adc(rev): the chain's chunk deck (BASE0) with eeg_adc from ADC_PEX[rev]. An inner node that the
    new extraction names differently (the same elements on it) keeps its .ic under the new name; any other node
    missing from the new one stops it."""
    text = open(os.path.join(BASE0, "tb.spice")).read()
    i = text.index("* eeg_adc: magic flat extraction")
    j = text.index(".ends eeg_adc", i) + len(".ends eeg_adc")
    old, new = text[i:j], open(ADC_PEX[ADC_REV]).read().rstrip("\n")
    assert new.startswith("* eeg_adc: magic flat extraction") and new.endswith(".ends eeg_adc")
    eo, en = element_nodes(old), element_nodes(new)
    no, nn = {n for v in eo.values() for n in v}, {n for v in en.values() for n in v}
    on = lambda E, n: {e for e, v in E.items() if n in v}  # noqa: E731
    ren = {}
    for g in sorted(no - nn):
        m = [x for x in sorted(nn - no) if on(en, x) == on(eo, g)]
        if len(m) != 1:
            raise SystemExit(f"eeg_adc node {g} is not in {ADC_PEX[ADC_REV]}, and no single node there has its elements")
        ren[g] = m[0]
    deck = text[:i] + new + text[j:]
    for g, x in ren.items():
        deck, k = re.subn(rf"\bv\(xadc\.{re.escape(g)}\)=", f"v(xadc.{x})=", deck)
        print(f"  .ic xadc.{g} -> xadc.{x} ({k})")
    left = [g for g in no - nn if f"v(xadc.{g})=" in deck]
    assert not left, left
    note = (f"* digital_noise.py base --adc {ADC_REV}: eeg_adc from {os.path.relpath(ADC_PEX[ADC_REV], REPO)} in place "
            f"of the chain's (r7's)" + "".join(f"; .ic xadc.{g} -> xadc.{x}" for g, x in ren.items()) + "\n")
    deck = deck.replace("* this deck:", note + "* this deck:", 1)
    os.makedirs(BASE, exist_ok=True)
    open(os.path.join(BASE, "tb.spice"), "w").write(deck)
    for f in ("quantizer.spice", "events.txt"):
        open(os.path.join(BASE, f), "w").write(open(os.path.join(BASE0, f)).read())
    return BASE


def frame_e0(text):
    """the deck's first frame start (e0, local time >= 0) from its CMP_STROBE source"""
    m = re.search(r"^VUCMP UCMP 0 PULSE\(0 1 (\S+) 5e-10", text, re.M)
    e0 = float(m.group(1)) + 0.25e-9            # the 50 % point of the 0.5 ns edge
    k = math.ceil(-e0 / TF) if e0 < 0 else 0
    return e0 + k * TF


def tstop_of(text):
    return float(re.search(r"^\.tran \S+ (\S+)", text, re.M).group(1))


def profile():
    return json.load(open(PROFILE))


def current_pwl(q_rise, q_fall, tw):
    """one frame of triangles (charge in pC per edge) as PWL points from t = 0 (the first one
    starts at 0); repeats every frame"""
    pts = [(0.0, 0.0)]
    for c in range(32):
        for t0, q in ((c * T, q_rise[c]), (c * T + T / 2, q_fall)):
            pk = 2 * q * 1e-12 / tw
            if t0 > pts[-1][0]:
                pts.append((t0, 0.0))
            pts += [(t0 + tw / 2, pk), (t0 + tw, 0.0)]
    pts.append((TF, 0.0))
    return " ".join(f"{t:.6e} {v:.6e}" for t, v in pts)


def pulse01(name, t_on, width, period, td=0.0):
    return f"V{name} {name} 0 PULSE(0 1 {td + t_on - 0.25e-9:.9e} 5e-10 5e-10 {width - 5e-10:.9e} {period:.9e})\n"


def pwl01(name, edges, v0=0):
    """a 0..1 source with 0.5 ns edges at the given times (each edge toggles)"""
    pts, v = [(0.0, v0)], v0
    for t in sorted(edges):
        pts += [(t - 0.25e-9, v), (t + 0.25e-9, 1 - v)]
        v = 1 - v
    return f"V{name} {name} 0 PWL(" + " ".join(f"{t:.9e} {x}" for t, x in pts) + ")\n"


def scaled(name, node, rail):
    """B source: a 0..1 control U<node> onto a macro's rails"""
    return f"B{name} {node} 0 V=v(DVSS_{rail})+v(DVDD_{rail},DVSS_{rail})*v({name})\n"


def digital_model(case, e0, tstop, tw=2e-9, lead=2e-9, ring=("DVDDC", "DVSSC"), sfx=""):
    """the model text; ring = the pad ring's nodes it hangs on (b1iso: a copy of its own)"""
    P = profile()
    rv, rs = ring
    s = sfx
    L = [f"* ---- digital side (digital_noise.py, case {case}) ----\n"]
    for blk, (ru, rl) in R_DIST.items():
        L.append(f"RDV{blk}{s} {rv} DVDD_{blk}{s} {ru}\nRDS{blk}{s} DVSS_{blk}{s} {rs} {rl}\n")
    for blk, (c, esr) in MACRO_C.items():
        L.append(f"CMAC{blk}{s} DVDD_{blk}{s} MACC_{blk}{s} {c:.4e}\nRMAC{blk}{s} MACC_{blk}{s} DVSS_{blk}{s} {esr}\n")
    td = e0 - lead
    for blk, macro in MACRO_OF.items():       # (ngspice's PWL repeats only in a V source: a 1 S VCCS)
        p = P[macro]
        L.append(f"VW{blk}{s} W_{blk}{s} 0 PWL({current_pwl(p['q_rise_pC'], p['q_fall_pC'], tw)}) "
                 f"r=0 td={td:.9e}\nG{blk}{s} DVDD_{blk}{s} DVSS_{blk}{s} W_{blk}{s} 0 1\n")
    # the board: oscillator, host, loads (board ground is node 0)
    t_m = e0 - 4e-9 - 0.75e-9                           # the pad edge 4 ns ahead of the outputs
    t_m -= math.floor(t_m / T) * T
    L.append(f"VMCLKO{s} MCLK_OSC{s} 0 PULSE(0 {VDD} {t_m:.9e} 1.5e-9 1.5e-9 {T / 2 - 1.5e-9:.9e} {T:.9e})\n"
             f"RMCLKS{s} MCLK_OSC{s} MCLK_BRD{s} 33\nCMCLKT{s} MCLK_BRD{s} 0 3e-12\n")
    for nm, lv in HOST_LEVEL.items():
        if case == "b2" and nm in ("CS_N", "SCLK", "MOSI"):
            continue
        L.append(f"VH{nm}{s} {nm}_HOST{s} 0 {VDD * lv}\nRH{nm}{s} {nm}_HOST{s} {nm}_BRD{s} 33\n")
    for nm in ("MISO", "DRDY_N", "RAW_DATA", "RAW_CLK"):
        L.append(f"CL{nm}{s} {nm}_BRD{s} 0 {C_BOARD_OUT:g}\nRL{nm}{s} {nm}_BRD{s} 0 1e6\n")
    for k, (nm, ties) in enumerate(DPAD):
        L.append(f"LBW{nm}{s} {nm}_BRD{s} {nm}_w{s} 2e-09\nRDBW{nm}{s} {nm}_BRD{s} {nm}_w{s} 20\n"
                 f"RBW{nm}{s} {nm}_w{s} {nm}_P{s} 0.1\n")
        conn = []
        for p in BI_PORTS:
            if p in ("DVDD", "VDD"):
                conn.append(rv)
            elif p in ("DVSS", "VSS"):
                conn.append(rs)
            elif p == "PAD":
                conn.append(f"{nm}_P{s}")
            elif p == "Y":
                conn.append(f"{nm}_Y{s}")
            else:
                v = ties[p]
                conn.append({0: rs, 1: rv}[v] if v in (0, 1) else f"{v[2:]}_C{s}")
        L.append(f"XDP{k}{s} {' '.join(conn)} gf180mcu_fd_io__bi_24t\nCY{nm}{s} {nm}_Y{s} {rs} 1e-13\n")
    # the core's drive of the output pads (A, OE) on the digital block's rails
    rail = "DIG" + s
    ctl = {"MISO": [], "MISO_OE": [], "DRDY_N": [], "RAW_DATA": [], "RAW_CLK": None}
    v0 = {"MISO": 0, "MISO_OE": 0, "DRDY_N": 0, "RAW_DATA": 0, "RAW_CLK": 0}
    if case == "b2":
        L += spi_host(e0, ctl, s)
    if case == "b3":
        # RAW_CLK = MCLK/4 and RAW_DATA (changes on its falling edges) as PWLs from one formula, so that
        # their shared corners are the same numbers, PAD_SKEW off the chip's own clock grid (e0 + kT
        # +- 0.25 ns: CMP, DCK, CHOP, BLK). A PULSE RAW_CLK left corners 3 fs from RAW_DATA's printed
        # ones, and the 1st b3 stopped there (12.573 us, timestep 1.25e-17).
        g = lambda k: e0 + k * T + PAD_SKEW
        n = int((tstop - e0) / (4 * T))
        ctl["RAW_CLK"] = [g(2 * j) for j in range(1, 2 * n + 1)]
        rng = np.random.default_rng(1)
        bits = rng.integers(0, 2, n + 1)
        ctl["RAW_DATA"] = [g(4 * (i + 1)) for i in range(n) if bits[i + 1] != bits[i]]
    for nm, ed in ctl.items():
        if ed is None:
            continue
        L.append(pwl01(f"U_{nm}{s}", ed, v0[nm]) if ed else f"VU_{nm}{s} U_{nm}{s} 0 {v0[nm]}\n")
    if case != "b3":
        L.append(f"VU_RAW_CLK{s} U_RAW_CLK{s} 0 0\n")
    for nm in ("MISO", "MISO_OE", "DRDY_N", "RAW_DATA", "RAW_CLK"):
        L.append(f"BU_{nm}{s} {nm}_C{s} 0 V=v(DVSS_{rail})+v(DVDD_{rail},DVSS_{rail})*v(U_{nm}{s})\n")
    return "".join(L)


def spi_host(e0, ctl, s):
    """b2: the host reads one sample. SCLK 2 MHz (mode 0), CS_N low 8.0 .. 34.0 us into the
    window, 48 bits (a read command, then status, 24-bit sample, CRC); the slave answers on MCLK
    edges: MISO_OE 3 edges after CS_N falls / rises (2-FF synchronizer), each MISO bit 3 edges
    after the SCLK falling edge that shifts it; DRDY_N rises when the FIFO empties (the last bit).
    These pad inputs come PAD_SKEW after their MCLK edge. On the edge itself, their printed PWL
    corners fell 3 fs from the strobe's (VUCMP) PULSE corners: r7's b2 got through, r10's stopped
    at 22.827 us (timestep 1.25e-17, 11/11)."""
    L = []
    t_cs0, t_cs1, tsck = 8.0e-6 + 7.3e-9, 34.0e-6 + 7.3e-9, 500e-9
    t_first = t_cs0 + 1.0e-6
    sck = []
    for i in range(48):
        sck += [t_first + i * tsck, t_first + i * tsck + tsck / 2]        # rising, falling
    cmd = [1, 0, 0, 0, 0, 0, 0, 1] + [0] * 40
    mosi_edges, v = [], 0
    for i, b in enumerate(cmd):
        if b != v:
            mosi_edges.append(t_first + i * tsck - tsck / 2 + 5e-9)
            v = b
    rng = np.random.default_rng(2)
    data = [0] * 8 + list(rng.integers(0, 2, 40))
    nxt = lambda t, k: e0 + (math.floor((t - e0) / T) + k) * T + PAD_SKEW       # k-th MCLK edge after t, + skew
    miso, v = [], 0
    for i in range(8, 48):
        t = nxt(t_first + (i - 1) * tsck + tsck / 2, 3)
        if data[i] != v:
            miso.append(t)
            v = data[i]
    if v:
        miso.append(nxt(t_cs1, 3))
    ctl["MISO"] = miso
    ctl["MISO_OE"] = [nxt(t_cs0, 3), nxt(t_cs1, 3)]
    ctl["DRDY_N"] = [nxt(t_first + 47 * tsck + tsck / 2, 3)]
    for nm, edges, lv in (("CS_N", [t_cs0, t_cs1], 1), ("SCLK", sck, 0), ("MOSI", mosi_edges, 0)):
        pts, x = [(0.0, lv * VDD)], lv
        for t in edges:
            pts += [(t - 1e-9, x * VDD), (t + 1e-9, (1 - x) * VDD)]
            x = 1 - x
        L.append(f"VH{nm}{s} {nm}_HOST{s} 0 PWL(" + " ".join(f"{t:.9e} {u:.4g}" for t, u in pts) + ")\n"
                 f"RH{nm}{s} {nm}_HOST{s} {nm}_BRD{s} 33\n")
    return L


def iso_ring(s):
    """b1iso: a copy of the pad ring (its cells, decoupling, bond wires, board) with its own
    regulator, for the same sources without the chip"""
    base = open(os.path.join(BASE, "tb.spice")).read()
    L = [f"* the separate copy of the ring for b1iso\n"]
    for ln in base.splitlines():
        if re.match(r"^(VDVDD|RLDODVDD|CBKDVDD|RBKDVDD|CHFDVDD|RHFDVDD|LHFDVDD|LBWDVDD|RDBWDVDD|RBWDVDD|"
                    r"LBWDVSS|RDBWDVSS|RBWDVSS|XASIG\d+|XDVDD\d+|XDVSS\d+|XCOR\d+|XDECD) ", ln):
            t = ln.split()
            t[0] += s
            t = [x + s if re.match(r"^(DVDD_REG|DVDD_BRD\w*|DVDD_w|DVSS_w|DVDDC|DVSSC|NC_PAD\d+)$", x) else x
                 for x in t]
            L.append(" ".join(t) + "\n")
    return "".join(L)


def patch(case, tw=2e-9, lead=2e-9, twin=None):
    """the B deck: the base chunk deck with the digital side, over its first twin seconds"""
    text = open(os.path.join(BASE, "tb.spice")).read()
    e0, tstop = frame_e0(text), tstop_of(text)
    if twin:
        tstop = min(tstop, twin)
        text = re.sub(r"^(\.tran \S+) \S+ ", lambda m: f"{m.group(1)} {tstop:.9e} ", text, count=1, flags=re.M)
    P = profile()
    out = []
    lines = text.split("\n")
    i = 0
    iso = case == "b1iso"
    while i < len(lines):
        ln = lines[i]
        name = ln.split(" ", 1)[0] if ln else ""
        # an element with its continuation lines
        j = i + 1
        while j < len(lines) and lines[j].startswith("+"):
            j += 1
        blk = lines[i:j]
        if not iso:
            if name in FROM_DIG or name in ("XDUT",):
                blk = [re.sub(r"\bDVSSC\b", "DVSS_DIG", re.sub(r"\bDVDDC\b", "DVDD_DIG", x)) for x in blk]
            elif re.match(r"^BSEL\d+$", name) or name in ("XADC", "XCTRL"):
                blk = [re.sub(r"\bDVSSC\b", "DVSS_ADD", re.sub(r"\bDVDDC\b", "DVDD_ADD", x)) for x in blk]
            elif name == "XDECD":
                blk = [re.sub(r"\bDVSSC\b", "DVSS_DEC", re.sub(r"\bDVDDC\b", "DVDD_DEC", x)) for x in blk]
        if name == ".options" and "acct" in ln:
            if iso:
                out.append(iso_ring("_X"))
                out.append(digital_model(case, e0, tstop, tw, lead, ring=("DVDDC_X", "DVSSC_X"), sfx="_X"))
            else:
                out.append(digital_model(case, e0, tstop, tw, lead))
        if name == ".save":
            blk = [save_line(iso)]
        out += blk
        i = j
    deck = "\n".join(out)
    # initial values of the new nodes (the base's .ic has every old node): the rails with the
    # macros' mean IR drop, the rest from the small deck's operating point
    ic = ics(text, P, iso)
    deck = deck.replace("\n.options acct", "\n" + ic + ".options acct", 1)
    deck = deck.replace("* this deck:", f"* digital_noise.py case {case} (tw {tw:g}, lead {lead:g})\n* this deck:", 1)
    return deck


def plain(twin):
    """'A' of use_adc(rev): the base deck itself over the window, with the B decks' .save"""
    text = open(os.path.join(BASE, "tb.spice")).read()
    tstop = min(tstop_of(text), twin)
    text = re.sub(r"^(\.tran \S+) \S+ ", lambda m: f"{m.group(1)} {tstop:.9e} ", text, count=1, flags=re.M)
    text, k = re.subn(r"^\.save .*$", lambda m: ".save " + " ".join(SAVE), text, count=1, flags=re.M)
    assert k == 1
    return text.replace("* this deck:", "* digital_noise.py case A (the base deck over the window)\n* this deck:", 1)


def ics(text, P, iso):
    """.ic lines for the new nodes"""
    get = lambda n: float(re.search(rf"v\({n}\)=([-+0-9.eE]+)", text).group(1))
    vd, vs = get("dvddc"), get("dvssc")
    I = {"DIG": P["eeg_digital_top"]["I_avg_mA"] * 1e-3, "ADD": P["eeg_adc_dig"]["I_avg_mA"] * 1e-3, "DEC": 0.0}
    s = "_X" if iso else ""
    v = {}
    for blk, (ru, rl) in R_DIST.items():
        v[f"dvdd_{blk}{s}"] = vd - I[blk] * ru
        v[f"dvss_{blk}{s}"] = vs + I[blk] * rl
        if blk in MACRO_C:
            v[f"macc_{blk}{s}"] = v[f"dvss_{blk}{s}"]
    if iso:            # the ring's copy starts where the ring is (its cells' inner nodes too)
        for n, x in re.findall(r"v\(([^)]+)\)=([-+0-9.eE]+)", text):
            if re.match(r"^(dvdd_reg|dvdd_brd\w*|dvdd_w|dvss_w|dvddc|dvssc|nc_pad\d+)$", n):
                v[n + "_x"] = float(x)
            elif re.match(r"^(xasig\d+|xdvdd\d+|xdvss\d+|xcor\d+|xdecd)\.", n):
                inst, rest = n.split(".", 1)
                v[f"{inst}_x.{rest}"] = float(x)
    opf = os.path.join(SMALL, "op_pads.json")
    if os.path.exists(opf):
        for n, x in json.load(open(opf)).items():
            if "." in n:
                inst, rest = n.split(".", 1)
                v[f"{inst}{s.lower()}.{rest}"] = x
            else:
                v[n + s.lower()] = x
    items = [f"v({n.lower()})={x:.12g}" for n, x in v.items()]
    return "".join(".ic " + " ".join(items[k:k + 8]) + "\n" for k in range(0, len(items), 8))


SAVE = ["v(sig)", "v(outp_adc)", "v(outn_adc)", "v(outp_afe)", "v(outn_afe)", "v(xadc.o1p)", "v(xadc.o1n)",
        "v(o2p)", "v(o2n)", "v(xadc.i1p)", "v(xadc.i1n)", "v(avdd_adc)", "v(avss_adc)", "v(dvddc)", "v(dvssc)",
        "v(vcm_adc)", "v(vrefp_adc)", "v(vrefn_adc)", "v(elp)", "v(eln)", "v(elp_p2)", "v(eln_p4)",
        "v(xchip.xpad2.m)", "v(xchip.xpad4.m)", "v(xchip.xpad0.m)", "v(xchip.xpad1.m)", "v(chop)", "v(chop_out)",
        "v(cmp_strobe)", "v(dac_clk)", "v(latmis)", "i(vdvdd)", "i(vavdd)"] + \
       [f"v(xctrl.{p}{k})" for p in ("ca", "pa") for k in range(5)]
SAVE_NEW = ["v(dvdd_dig)", "v(dvss_dig)", "v(dvdd_add)", "v(dvss_add)", "v(dvdd_dec)", "v(dvss_dec)",
            "v(mclk_p)", "v(mclk_y)", "v(miso_p)", "v(raw_clk_p)", "v(drdy_n_p)"]


def save_line(iso):
    new = SAVE_NEW if not iso else [x.replace(")", "_x)") for x in SAVE_NEW] + ["v(dvddc_x)", "v(dvssc_x)"]
    return ".save " + " ".join(SAVE + new)


# ---------------------------------------------------------------- the small deck (ring bounce)
def small(tw=2e-9, tstop=3 * TF, case="b1", tag=""):
    """the ring, the board, the digital side and the 13 analog pads with simple core-side loads:
    how far the rails and the analog pads move (a diagnostic, not the evaluation)"""
    base = open(os.path.join(BASE, "tb.spice")).read()
    head = []
    for ln in base.splitlines():
        if ln.startswith((".include", ".lib", ".param", ".subckt cap_nmos_06v0", "C1 1 2 {moscap", ".ends cap_nmos")):
            if "chipnets.spice" in ln or "eeg_ref_pex" in ln or "quantizer" in ln:
                continue
            head.append(ln)
    chip = open(os.path.join(HERE, "runs", "chipnets_r9", "chipnets.spice")).read()
    padsub = re.search(r"\.subckt pad_asig5p0.*?\.ends pad_asig5p0", chip, re.S).group(0)
    keep = re.compile(r"^(VAVDD|RLDOAVDD|CBKAVDD|RBKAVDD|CHFAVDD|RHFAVDD|LHFAVDD|VDVDD|RLDODVDD|CBKDVDD|RBKDVDD|"
                      r"CHFDVDD|RHFDVDD|LHFDVDD|LBWAVDD\d+|RDBWAVDD\d+|RBWAVDD\d+|LBWAVSS\d+|RDBWAVSS\d+|RBWAVSS\d+|"
                      r"LBWDVDD|RDBWDVDD|RBWDVDD|LBWDVSS|RDBWDVSS|RBWDVSS|XASIG\d+|XDVDD\d+|XDVSS\d+|XCOR\d+|XDECD|"
                      r"VREFPX|VREFNX|CREFP|CREFN|LBWVREF[PN]|RDBWVREF[PN]|RBWVREF[PN]|LBWVCM|RDBWVCM|RBWVCM|CVCM|"
                      r"VSIG|EP|EN|RSP|RSN|LBWEL[PN]\d|RDBWEL[PN]\d|RBWEL[PN]\d) ")
    board = [ln for ln in base.splitlines() if keep.match(ln)]
    board = [re.sub(r"PWL\(0 0 1\.0+e-03 ([0-9.]+)\)", r"DC \1", x) for x in board]
    board = [re.sub(r"\bDVSSC\b", "DVSS_DEC", re.sub(r"\bDVDDC\b", "DVDD_DEC", x)) if x.startswith("XDECD") else x
             for x in board]
    pads = []
    for k, net in ((0, "AVDD"), (7, "AVDD"), (12, "AVDD"), (1, "AVSS"), (6, "AVSS"), (13, "AVSS"), (2, "ELP"),
                   (3, "ELP"), (4, "ELN"), (5, "ELN"), (9, "VCM"), (10, "VREFP_PAD"), (11, "VREFN_PAD")):
        pads.append(f"XPAD{k} {net}_P{k} {net}_E{k} DVDDC DVSSC pad_asig5p0\nRE{k} {net}_E{k} {net}_CORE 1\n")
    core = ("CAVC AVDD_CORE AVSS_CORE 3.76e-10\nIAVC AVDD_CORE AVSS_CORE 5e-3\n"
            "CELP ELP_CORE AVSS_CORE 3e-12\nCELN ELN_CORE AVSS_CORE 3e-12\nRELP ELP_CORE VCM_CORE 1e8\n"
            "RELN ELN_CORE VCM_CORE 1e8\nCVCMC VCM_CORE AVSS_CORE 1e-11\nRVCMDIV VCM_CORE AVSS_CORE 1e5\n"
            "RVCMUP AVDD_CORE VCM_CORE 1e5\nCVRP VREFP_PAD_CORE AVSS_CORE 1e-10\nCVRN VREFN_PAD_CORE AVSS_CORE 1e-10\n")
    # the electrodes ride on the board's VCM (here held by the on-chip divider through the pad)
    e0 = 0.0 + 2e-9
    model = digital_model(case, e0 + 4 * T, tstop, tw)
    L = ["* digital_noise.py small: the ring, the board and the digital side, analog pads with simple loads",
         *head, padsub, *board, *pads, core, model,
         ".options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-11 chgtol=1e-15",
         ".save " + " ".join(["v(dvddc)", "v(dvssc)", "v(dvdd_dig)", "v(dvss_dig)", "v(dvdd_add)", "v(dvss_add)",
                              "v(dvdd_dec)", "v(dvss_dec)", "v(xpad2.m)", "v(xpad4.m)", "v(elp_p2)", "v(eln_p4)",
                              "v(elp_core)", "v(eln_core)", "v(avdd_core)", "v(avss_core)", "v(vcm_core)",
                              "v(xpad0.m)", "v(xpad1.m)", "v(mclk_p)", "v(mclk_y)", "i(vdvdd)", "i(vavdd)"]),
         f".tran 2e-11 {tstop:.6e} 0 5e-11", ".end"]
    return "\n".join(L) + "\n"


def small_op():
    """the pads' operating point (static inputs, no core current, MCLK low): .ic for the B decks"""
    d = SMALL
    os.makedirs(d, exist_ok=True)
    txt = small(case="b1")
    txt = re.sub(r"^(VW(DIG|ADD)) (\S+) 0 PWL\(.*$", r"\1 \3 0 0", txt, flags=re.M)
    txt = re.sub(r"^VMCLKO (\S+) 0 PULSE\(.*$", r"VMCLKO \1 0 0", txt, flags=re.M)
    txt = re.sub(r"^\.save .*$", "", txt, flags=re.M)
    txt = txt.replace(re.search(r"^\.tran .*$", txt, re.M).group(0),
                      ".control\nop\nprint all > op_all.txt\n.endc")
    open(os.path.join(d, "op.spice"), "w").write(txt)
    subprocess.run([NGSPICE, "-b", "op.spice"], cwd=d, stdout=open(os.path.join(d, "op.log"), "w"),
                   stderr=subprocess.STDOUT)
    vals = {}
    for ln in open(os.path.join(d, "op_all.txt"), errors="replace"):
        m = re.match(r"\s*([\w.#\[\]]+)\s*=\s*([-+0-9.eE]+)", ln)
        if m and not m.group(1).endswith("#branch"):
            vals[m.group(1).lower()] = float(m.group(2))
    keep = {n: x for n, x in vals.items() if n.startswith("xdp") or re.match(
        r"^(mclk|reset_n|sclk|cs_n|mosi|miso|drdy_n|raw_data|raw_clk)_(p|w|brd|y|c|host|osc)$", n)}
    json.dump(keep, open(os.path.join(d, "op_pads.json"), "w"), indent=0)
    return keep


def run_bg(d, deck_name="tb.spice", raw="out.raw", nice=0):
    """ngspice in its own session (survives this process and its process group), log to run.log"""
    log = open(os.path.join(d, "run.log"), "w")
    pre = ["nice", "-n", str(nice)] if nice else []
    p = subprocess.Popen(pre + ["caffeinate", "-i", "-s", NGSPICE, "-b", "-r", raw, deck_name], cwd=d, stdout=log,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    return str(p.pid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("small", "op", "base", "make", "run", "compare"))
    ap.add_argument("cases", nargs="*")
    ap.add_argument("--tw", type=float, default=2e-9, help="width of each edge's current triangle (s)")
    ap.add_argument("--lead", type=float, default=2e-9, help="how far it starts before the output edges (s)")
    ap.add_argument("--tstop", type=float, default=3 * TF, help="small: its length (s)")
    ap.add_argument("--twin", type=float, default=47.3e-6,
                    help="make / run: the window of the chunk to run (s): 6 chopper periods after its first edge")
    ap.add_argument("--adc", default="", choices=("", *ADC_PEX), help="the decks with this extraction of eeg_adc")
    ap.add_argument("--chain", default="", choices=("", *CHAINS), help="the decks on this chip's own chain")
    ap.add_argument("--nice", type=int, default=0, help="run: nice level of the runs")
    a = ap.parse_args()
    if a.adc and a.chain:
        raise SystemExit("--adc or --chain, not both")
    use_adc(a.adc)
    use_chain(a.chain)
    if a.mode == "base":
        if CHAIN_REV:
            print(copy_chain_base())
        elif not ADC_REV:
            raise SystemExit("base: with --adc or --chain (r9's own deck is runs/digital_noise/base_chunk014)")
        else:
            print(make_base())
    elif a.mode == "op":
        print(len(small_op()), "pad nodes")
    elif a.mode == "small":
        tag = a.cases[0] if a.cases else "b1"
        d = os.path.join(RUNS, "small", f"{tag}_tw{a.tw * 1e9:g}ns")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "tb.spice"), "w").write(small(a.tw, a.tstop, case=tag))
        print(d, run_bg(d))
    elif a.mode in ("make", "run"):
        for c in a.cases or ((("A",) if ADC_REV else ()) + CASES):
            if c == "A" and not ADC_REV:
                raise SystemExit("A without --adc is the chain's own chunk (nothing to run)")
            d = os.path.join(RUNS, c)
            os.makedirs(d, exist_ok=True)
            for f in ("quantizer.spice", "events.txt"):
                src = os.path.join(BASE, f)
                if not os.path.exists(os.path.join(d, f)):
                    open(os.path.join(d, f), "w").write(open(src).read())
            open(os.path.join(d, "tb.spice"), "w").write(plain(a.twin) if c == "A" else patch(c, a.tw, a.lead, a.twin))
            if a.mode == "run":
                print(c, run_bg(d, nice=a.nice))
            else:
                print(c, os.path.join(d, "tb.spice"))
    elif a.mode == "compare":
        compare(a.cases or None)


# ---------------------------------------------------------------- comparison
GAIN = 298.94           # electrode -> AFE output at the ADC pins, DAC off (7 MCLK blanking; figs_perf.su_gain)


def read_raw(path):
    """ngspice binary raw (real) -> {name: array}, a partial file up to its last full point"""
    blob = open(path, "rb").read()
    i = blob.index(b"Binary:\n")
    head = blob[:i].decode().splitlines()
    nv = int(next(h for h in head if h.startswith("No. Variables:")).split(":")[1])
    k = head.index("Variables:")
    names = [h.split()[1].lower() for h in head[k + 1:k + 1 + nv]]
    data = np.frombuffer(blob[i + 8:], dtype="<f8")
    n = data.size // nv
    data = data[:n * nv].reshape(n, nv)
    return {nm: data[:, j] for j, nm in enumerate(names)}


def chunk_t0():
    m = re.search(r"this deck: (\S+) \.\.", open(os.path.join(BASE, "tb.spice")).read())
    return float(m.group(1))


def load_case(c):
    """a case's vectors on the chunk's local time; 'A' = the chain's own chunk (lean vectors), or with use_adc(rev)
    the run of the base deck"""
    if c == "A" and not ADC_REV:
        f = os.path.join(CHAIN, "chunk_014", "lean.npz")
        if not os.path.exists(f):
            return None
        z = np.load(f)
        r = {k: np.array(z[k]) for k in z.files}
        r["time"] = r["time"] - chunk_t0()
        return r
    f = os.path.join(RUNS, c, "out.raw")
    return read_raw(f) if os.path.exists(f) else None


def integ(t, y, a, b):
    """exact integral of the piecewise-linear y(t) over [a, b]"""
    m = (t > a) & (t < b)
    tt = np.concatenate(([a], t[m], [b]))
    yy = np.concatenate(([np.interp(a, t, y)], y[m], [np.interp(b, t, y)]))
    return float(np.sum((tt[1:] - tt[:-1]) * (yy[1:] + yy[:-1]) / 2))


def chop_edges(text):
    """CHOP's falling edges (local time) from its PULSE: rises at td + m*TCH, falls TCH/2 later"""
    m = re.search(r"^VUCHOP UCHOP 0 PULSE\(0 1 (\S+) 5e-10", text, re.M)
    rise = float(m.group(1)) + 0.25e-9
    fall = rise + TCH / 2
    k = math.ceil(-fall / TCH)
    return fall + k * TCH


def periods(tend):
    """chopper periods from a quarter period after each CHOP falling edge (whole ones in the data)"""
    f0 = chop_edges(open(os.path.join(BASE, "tb.spice")).read())
    out, k = [], 0
    while f0 + TCH / 4 + (k + 1) * TCH <= tend + 1e-12:
        out.append((f0 + TCH / 4 + k * TCH, f0 + TCH / 4 + (k + 1) * TCH))
        k += 1
    return out


def codes(r, e0, tend):
    """the controller's code per frame (its register at mid-frame)"""
    t, out = r["time"], []
    k = 0
    while e0 + k * TF + 16 * T <= tend:
        tm = e0 + k * TF + 16 * T
        out.append(sum(int(np.interp(tm, t, r[f"v(xctrl.ca{b})"]) > 1.65) << b for b in range(5)))
        k += 1
    return out


def tone_basis(P, f, td):
    """per-period means of 1 and of the input tone's sine and cosine (exact): the columns of the offset + tone fit"""
    w = 2 * np.pi * f
    S = [(np.cos(w * (a - td)) - np.cos(w * (b - td))) / w / (b - a) for a, b in P]
    C = [(np.sin(w * (b - td)) - np.sin(w * (a - td))) / w / (b - a) for a, b in P]
    return np.c_[np.ones(len(P)), S, C]


def input_pp(ra, rb, text, after=50e-9, before=5e-9):
    """p-p of a - b at the AFE's input after the first 2 us, on a's points: the common mode, and the differential away
    from the CHOP edges (from `before` ahead of each edge to `after` past it, where the two runs' points sit
    differently on the switching transient), and the differential with them"""
    t = ra["time"]
    m = t > 2e-6
    f0 = chop_edges(text)
    ed = f0 + np.arange(-2, int(t[-1] / (TCH / 2)) + 3) * TCH / 2
    dt = t[:, None] - ed[None, :]
    away = m & ~np.any((dt > -before) & (dt < after), axis=1)
    on_a = lambda r, n: r[n] if r is ra else np.interp(t, r["time"], r[n])  # noqa: E731
    cm = (on_a(ra, "v(elp)") + on_a(ra, "v(eln)") - on_a(rb, "v(elp)") - on_a(rb, "v(eln)")) / 2
    df = on_a(ra, "v(elp)") - on_a(ra, "v(eln)") - on_a(rb, "v(elp)") + on_a(rb, "v(eln)")
    return {"cm_pp_mV": float(np.ptp(cm[m]) * 1e3), "diff_pp_uV": float(np.ptp(df[away]) * 1e6),
            "diff_pp_all_uV": float(np.ptp(df[m]) * 1e6)}


def compare(cases=None):
    text = open(os.path.join(BASE, "tb.spice")).read()
    e0 = frame_e0(text)
    cases = cases or ["A"] + list(CASES)
    R = {c: load_case(c) for c in cases}
    R = {c: r for c, r in R.items() if r is not None}
    tend = min(r["time"][-1] for c, r in R.items() if c != "A")
    if "A" in R:
        tend = min(tend, R["A"]["time"][-1])
    P = periods(tend)
    res = {"adc": ADC_REV or (f"{CHAIN_REV} (the chain's)" if CHAIN_REV else "r7 (the chain's)"), "tend_us": tend * 1e6,
           "periods_us": [[a * 1e6, b * 1e6] for a, b in P], "cases": {}}
    # the electrode's 16 kHz tone: its per-period means are exact, so a difference splits into offset + tone + rest
    m = re.search(r"^VSIG SIG 0 DC \S+ SIN\((\S+) (\S+) (\S+) (\S+)\)", text, re.M)
    fsig, td = float(m.group(3)), float(m.group(4))
    X = tone_basis(P, fsig, td)
    for c, r in R.items():
        t = r["time"]
        vo = r["v(outp_adc)"] - r["v(outn_adc)"]
        o1 = r["v(xadc.o1p)"] - r["v(xadc.o1n)"]
        o2 = r["v(o2p)"] - r["v(o2n)"]
        x = {"vo_uV": [integ(t, vo, a, b) / (b - a) * 1e6 for a, b in P],
             "o1_uV": [integ(t, o1, a, b) / (b - a) * 1e6 for a, b in P],
             "o2_uV": [integ(t, o2, a, b) / (b - a) * 1e6 for a, b in P],
             "codes": codes(r, e0, tend)}
        m = t > 2e-6
        for nm, v in (("ring_vdd", r["v(dvddc)"]), ("ring_vss", r["v(dvssc)"]),
                      ("dig", r.get("v(dvdd_dig)", np.nan) - r.get("v(dvss_dig)", np.nan)),
                      ("add", r.get("v(dvdd_add)", np.nan) - r.get("v(dvss_add)", np.nan))):
            v = np.asarray(v)
            if v.shape == t.shape:
                x[nm + "_pp_mV"] = float(np.ptp(v[m]) * 1e3)
                x[nm + "_mean_mV"] = float(integ(t, v, 2e-6, tend) / (tend - 2e-6) * 1e3)
        if "v(elp)" in r:
            vin = r["v(elp)"] - r["v(eln)"]
            chop = r["v(chop)"]
            s = np.where(chop > 1.65, 1.0, -1.0)
            x["vin_demod_uV"] = [integ(t, vin * s, a, b) / (b - a) * 1e6 for a, b in P]
            x["vin_mean_uV"] = [integ(t, vin, a, b) / (b - a) * 1e6 for a, b in P]
            cm = (r["v(elp)"] + r["v(eln)"]) / 2
            x["cm_pp_mV"] = float(np.ptp(cm[m]) * 1e3)
        res["cases"][c] = x
    ref = res["cases"]["A" if "A" in res["cases"] else next(iter(res["cases"]))]["vo_uV"]
    k = np.linalg.lstsq(X, np.array(ref), rcond=None)[0]
    tone = float(np.hypot(k[1], k[2]))                   # the tone at the AFE output, per-period means (uV)
    res["tone"] = {"f_Hz": fsig, "td_s": td, "out_uV": tone}
    pairs = [("b1iso", "A"), ("b1", "b1iso"), ("b1", "A"), ("b2", "b1"), ("b3", "b1")]
    res["diff"] = {}
    print(f"window {tend * 1e6:.2f} us, {len(P)} chopper periods from "
          + ", ".join(f"{a * 1e6:.2f}" for a, _ in P) + f" us; the tone at the AFE output {tone / 1e3:.1f} mV")
    for p, q in pairs:
        if p in res["cases"] and q in res["cases"]:
            Xc, Yc = res["cases"][p], res["cases"][q]
            dv = [u - v for u, v in zip(Xc["vo_uV"], Yc["vo_uV"])]
            do1 = [u - v for u, v in zip(Xc["o1_uV"], Yc["o1_uV"])]
            n = min(len(Xc["codes"]), len(Yc["codes"]))
            dc = sum(a != b for a, b in zip(Xc["codes"][:n], Yc["codes"][:n]))
            k = np.linalg.lstsq(X, np.array(dv), rcond=None)[0]
            rest = np.array(dv) - X @ k
            fit = {"offset_nV": k[0] / GAIN * 1e3, "tone_ppm": float(np.hypot(k[1], k[2])) / tone * 1e6,
                   "tone_uV": [k[1], k[2]], "rest_nV_rms": float(np.sqrt(np.mean(rest ** 2))) / GAIN * 1e3}
            d = {"vo_uV": dv, "electrode_uV": [v / GAIN for v in dv], "o1_uV": do1, "codes_differ": dc, "frames": n,
                 "fit": fit}
            if "v(elp)" in R[p] and "v(elp)" in R[q]:
                d["input"] = input_pp(R[p], R[q], text)
            res["diff"][f"{p}-{q}"] = d
            print(f"{p:5s} - {q:5s}: AFE out per period (uV) " + " ".join(f"{v:+8.2f}" for v in dv)
                  + "   electrode (nV) " + " ".join(f"{v / GAIN * 1e3:+7.1f}" for v in dv)
                  + f"   codes differ {dc}/{n}")
            print(f"{'':15s}offset {fit['offset_nV']:+.3f} nV, tone {fit['tone_ppm']:.2f} ppm, "
                  f"rest {fit['rest_nV_rms']:.3f} nV rms"
                  + ("; AFE input: CM {cm_pp_mV:.2f} mV p-p, differential {diff_pp_uV:.2f} uV p-p away from the CHOP "
                     "edges ({diff_pp_all_uV:.2f} with them)".format(**d["input"]) if "input" in d else ""))
    for c, x in res["cases"].items():
        extra = " ".join(f"{k} {v:.2f}" for k, v in x.items() if k.endswith("_pp_mV") or k.endswith("_mean_mV"))
        dm = (" vin demod (uV) " + " ".join(f"{v:+.3f}" for v in x["vin_demod_uV"])) if "vin_demod_uV" in x else ""
        print(f"{c:5s}: {extra}{dm}")
    json.dump(res, open(os.path.join(RUNS, "compare.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    main()
