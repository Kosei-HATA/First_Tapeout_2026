#!/usr/bin/env python3
"""Working ADC-loop deck for this rev, derived from the imported independent-
environment deck (gf180/tapeout/import_20261021/adc_gain10_loop/).

Changes against the import (all needed for long, robust runs):
  * PDK paths -> local ciel install.
  * Stage 2 scaled x10 (C2 19.53p, R21 100k); DAC2 = 31 transistor cells
    (gf180/sim/dac2_cell/dac2_cell.spice) instead of the 106.7 Meg resistor DAC;
    cascode biases through 10k, cell gates through 1k from S2L/S2LN.
  * Quantizer model: the controller's adc_bridge (ADC33) thresholds 0.99/2.31 V
    -> 1.65/1.65 V. The 0.99..2.31 V band returned UNKNOWN while the analog
    TH round-trip ramped; a clock edge there latched X into the DWA pointer and
    opened the loop. With equal thresholds no UNKNOWN band exists; the LUT 'x'
    entries are then unreachable (they only decode UNKNOWN inputs).
  * OTA bias sources (VBN1, VNC1, VPC1, VBCM1) through 1k with 10 pF, like a
    real bias generator; ideal sources made the solver fail at DAC switching.
    VCM goes through 10 ohm + 100 pF for the same reason.
  * Tolerances: trap, reltol 1e-5, vntol 1e-7, abstol 1e-12, chgtol 1e-16.
  * Input: sine (default 0.3 V pk, 1 kHz), DLOAD events for every clock.
  * --quant tr: the transistor quantizer (gf180/tapeout/adc/eeg_quantizer.spice)
    replaces the ideal comparators; the XSPICE controller (DWA, SEL/S2L) stays.
    CMP_STROBE rises 3 MCLK before each DLOAD, as in the RTL (TH captured at
    e2, SEL changes at e3, ELD 91.6 ns); the controller samples TH at DLOAD.
    The ladder runs from VREFP/VREFN = 1.65 V +- VREF/2, IQ is 31.25 uA.
  * --quant ideal: the same, with ideal comparators sampled at the strobe
    (quantizer_ideal.spice), the reference for --quant tr.
  * OTA1 chopper: the import drove it with tanh sources that toggle only four
    times (until 33 us), so OTA1 was in effect unchopped. Here --chop1 0 (default)
    holds phase A for the whole run; --chop1 <fch> chops for the whole run with
    the import's edge order around each nominal edge t_e: drain commutator of the
    new phase on at t_e - ovl/2, input TG of the old phase off at t_e - dead/2,
    input TG of the new phase on at t_e + dead/2, drain commutator of the old
    phase off at t_e + ovl/2 (50 % points, 2 ns edges; import: dead 15 ns,
    ovl 25 ns). The first edge is --chop1-phase frames after a DAC load.
    --chop1-drv drives OTA1 through the transistor driver eeg_adc_clk
    (gf180/tapeout/adc/eeg_adc_clk.spice) from a CHOP1 square wave instead.
  * out.csv holds the waveforms interpolated to --wstep (default 20 ns, linearize):
    writing every solver point made 3 GB per 8 ms (11.6 GB per 32 ms) and filled
    the disk on 10/22. The analyses sample once per frame.
  * --ota1 rev (default) takes the OTAs from gf180/tapeout/adc/eeg_adc_otas.spice
    (OTA1 input pair L 1 um, m 1024, since 10/22); --ota1 import keeps the import's
    otas.spice (L 2 um, m 2048), which all loop runs before that used; --ota1 ideal
    replaces both OTAs with linear behavioral amplifiers (otas_ideal.spice: gain 1e4,
    50 MHz) to separate the OTAs' distortion from the rest of the deck.

Usage: python3 make_deck.py <out_dir> [--tstop 1.25e-3] [--fsig 1e3] [--amp 0.3]
       [--dac2 cells|ideal] [--quant model|tr|ideal]
       [--chop1 0|<fch>] [--chop1-phase 0.5] [--dead 15e-9] [--ovl 25e-9] [--chop1-drv]
       [--ota1 rev|import|ideal] [--wstep 20e-9]
Then: (cd <out_dir> && ngspice -b circuit.spice) -> out.csv
"""
import argparse
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
IMPORT = os.path.join(REPO, "gf180", "tapeout", "import_20261021", "adc_gain10_loop")
CELL = os.path.join(REPO, "gf180", "sim", "dac2_cell", "dac2_cell.spice")
OTAS_REV = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc_otas.spice")
ACLK = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc_clk.spice")
QUANT = {"tr": (os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_quantizer.spice"), "eeg_quantizer"),
         "ideal": (os.path.join(HERE, "quantizer_ideal.spice"), "eeg_quantizer_ideal")}
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
T = 1 / 1.024e6
S = 10.0
T0_LOAD = 2.0784625e-06  # first DLOAD
TM = T / 32  # MCLK period


def events(tstop):
    lines = ["0 0s 1s", "1.054e-06 0s 0s"]
    t0, k = T0_LOAD, 0
    while t0 + k * T < tstop:
        t = t0 + k * T
        lines += [f"{t:.10e} 1s 0s", f"{t + 32e-9:.10e} 0s 0s"]
        k += 1
    return "\n".join(lines) + "\n"


def pulse(v1, v2, t50, w50, per, tr=2e-9):
    """PULSE from v1 to v2 whose first 50 % crossing is at t50, 50 % width w50."""
    return f"PULSE({v1} {v2} {t50 - tr / 2:.10e} {tr:g} {tr:g} {w50 - tr:.10e} {per:.10e})"


def chop1_sources(fch, phase, dead, ovl, drv=False):
    """OTA1 chopper drives (CIA_DRV ... CDB_DRV); phase A = CIA/CDA high."""
    if drv:  # transistor driver from CHOP1; it drives the complements as well
        if fch == 0:
            ch = "3.3"
        else:
            p = 1 / fch
            te = T0_LOAD + (1 + phase) * T
            ch = pulse(3.3, 0, te, p / 2, p, 0.5e-9)
        # the driver's supply through 1 ohm and 200 pF like a real decoupled rail; an
        # ideal source stopped a 4 kHz run at a chopper edge (timestep too small)
        return (f".include {ACLK}\nVCHOP1 CHOP1 0 {ch}\nVACLKS VACLKS 0 3.3\nRACLK VACLKS VACLK 1\n"
                "CACLK VACLK 0 200p\n"
                "XACLK CHOP1 CIA_DRV NCIA_DRV CIB_DRV NCIB_DRV CDA_DRV NCDA_DRV CDB_DRV NCDB_DRV VACLK 0 eeg_adc_clk")
    if fch == 0:
        return "VIA_DRV CIA_DRV 0 3.3\nVIB_DRV CIB_DRV 0 0\nVDA_DRV CDA_DRV 0 3.3\nVDB_DRV CDB_DRV 0 0"
    p = 1 / fch
    if abs(p / 2 / T - round(p / 2 / T)) > 1e-9:
        raise SystemExit("--chop1: the half period must be a whole number of frames")
    te = T0_LOAD + (1 + phase) * T  # first A->B edge
    return "\n".join([
        f"VIA_DRV CIA_DRV 0 {pulse(3.3, 0, te - dead / 2, p / 2 + dead, p)}",
        f"VIB_DRV CIB_DRV 0 {pulse(0, 3.3, te + dead / 2, p / 2 - dead, p)}",
        f"VDA_DRV CDA_DRV 0 {pulse(3.3, 0, te + ovl / 2, p / 2 - ovl, p)}",
        f"VDB_DRV CDB_DRV 0 {pulse(0, 3.3, te - ovl / 2, p / 2 + ovl, p)}"])


def sub(pattern, repl, text, count=1):
    new, n = re.subn(pattern, repl, text, flags=re.M)
    if n < count:
        raise SystemExit(f"pattern not found: {pattern}")
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--tstop", type=float, default=1.25e-3)
    ap.add_argument("--fsig", type=float, default=1e3)
    ap.add_argument("--amp", type=float, default=0.3)
    ap.add_argument("--dac2", choices=["cells", "ideal"], default="cells")
    ap.add_argument("--quant", choices=["model", "tr", "ideal"], default="model")
    ap.add_argument("--chop1", type=float, default=0.0, help="OTA1 chopper frequency (Hz), 0 = phase A")
    ap.add_argument("--chop1-phase", type=float, default=0.5, help="first edge, frames after a DAC load")
    ap.add_argument("--dead", type=float, default=15e-9, help="input-TG dead time (s)")
    ap.add_argument("--ovl", type=float, default=25e-9, help="drain-commutator overlap (s)")
    ap.add_argument("--chop1-drv", action="store_true", help="OTA1 chopper through eeg_adc_clk")
    ap.add_argument("--ota1", choices=["rev", "import", "ideal"], default="rev")
    ap.add_argument("--wstep", type=float, default=20e-9,
                    help="out.csv interval (s); the solver's step is still capped at 1 ns")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    otas = {"rev": OTAS_REV, "import": os.path.join(IMPORT, "otas.spice"),
            "ideal": os.path.join(HERE, "otas_ideal.spice")}[a.ota1]
    shutil.copy(otas, os.path.join(a.out, "otas.spice"))
    q = open(os.path.join(IMPORT, "quantizer.spice")).read()
    q = sub(r"^\.model ADC33 adc_bridge \(in_low=0\.99 in_high=2\.31 ",
            ".model ADC33 adc_bridge (in_low=1.65 in_high=1.65 ", q)
    open(os.path.join(a.out, "quantizer.spice"), "w").write(q)
    open(os.path.join(a.out, "events.txt"), "w").write(events(a.tstop))

    txt = open(os.path.join(IMPORT, "circuit.spice")).read()
    txt = txt.replace("/Volumes/mukiebi/Codex/gf180_ishi_env_20261015/native_runtime/pdk/"
                      "gf180mcuD/libs.tech/ngspice", PDK)
    txt = sub(r"^\.options .*$", ".options sparse method=trap maxord=2 reltol=1e-5 "
              "vntol=1e-7 abstol=1e-12 chgtol=1e-16 bypass=0", txt)
    txt = sub(r"^VSIG .*$", f"VSIG SIG 0 SIN(0 {a.amp} {a.fsig} 1.1u)", txt)
    txt = sub(r"^BIA_DRV .*\n(ENCIA .*\n)BIB_DRV .*\n(ENCIB .*\n)BDA_DRV .*\n(ENCDA .*\n)BDB_DRV .*\n(ENCDB .*)$",
              lambda m: chop1_sources(a.chop1, a.chop1_phase, a.dead, a.ovl, a.chop1_drv) + "\n"
              + ("" if a.chop1_drv else "".join(m.groups())), txt)
    for b, v in (("VBN1", ".85"), ("VNC1", "2"), ("VPC1", "1.7"), ("VBCM1", ".82")):
        txt = sub(rf"^{b} {b} 0 {re.escape(v)}$", f"{b} {b}S 0 {v}\nR{b} {b}S {b} 1k\nC{b} {b} 0 10p", txt)
    # the ideal CM source carries the DAC return currents and stalled the step control
    txt = sub(r"^VCM CM 0 (\S+)$", r"VCM CMS 0 \1\nRVCM CMS CM 10\nCVCM CM 0 100p", txt)
    txt = sub(r"^(R21[PN] \S+ \S+) 1Meg$", rf"\g<1> {1e6 / S:.6g}", txt, 2)
    txt = sub(r"^(C2[PN] \S+ \S+) 1\.953125p$", rf"\g<1> {1.953125 * S:.6g}p", txt, 2)
    if a.dac2 == "ideal":
        txt = sub(r"^(RD2[PN] \S+ \S+) \{320000000/3/31\}$", rf"\g<1> {{320000000/3/31/{S}}}", txt, 2)
    else:
        txt = sub(r"^(RD2[PN] .*)$", r"* \1  (replaced by the transistor DAC2 array)", txt, 2)
        cells = "\n".join(f"RD2D{j} S2L{j} D2D{j} 1k\nRD2B{j} S2LN{j} D2B{j} 1k\n"
                          f"XD2_{j} I2P I2N D2D{j} D2B{j} VBP2 VBPC2 VBN2 VBNC2 VDD 0 dac2_cell"
                          for j in range(31))
        block = (f".include {CELL}\n"
                 "IRP2 XIRP2 0 DC 234.4n\nIRN2 VDD XIRN2 DC 234.4n\n"
                 "VBPC2 VBPC2S 0 1.8\nRBPC2 VBPC2S VBPC2 10k\n"
                 "VBNC2 VBNC2S 0 1.5\nRBNC2 VBNC2S VBNC2 10k\n"
                 "XB2 XIRP2 XIRN2 VBP2 VBPC2 VBN2 VBNC2 VDD 0 dac2_bias\n" + cells + "\n")
        # insert before the final ".end" line (a plain "\n.end" also matches ".ends rst_tg")
        txt = sub(r"^\.end\s*$", lambda m: block + ".end", txt)
    if a.quant != "model":
        m = re.search(r"^XQ O2P O2N DLOAD DRESET_EVENT VDD 0 (.*) ct_quantizer5_event$", txt, re.M)
        if not m:
            raise SystemExit("quantizer instance not found")
        th = " ".join(f"TH{k}" for k in range(31))
        qfile, qname = QUANT[a.quant]
        block = (f".lib {PDK}/sm141064.ngspice res_typical\n.include {qfile}\n"
                 f"XQT O2P O2N VREFPQ VREFNQ CMP_STROBE {th} IQQ VDD 0 VDD 0 {qname}\n"
                 f"XCTRL {th} DLOAD DRESET_EVENT VDD 0 {m.group(1)} adc_ctrl_event\n"
                 "EVRPQ VREFPQ 0 VALUE={1.65+V(VREF)/2}\nEVRNQ VREFNQ 0 VALUE={1.65-V(VREF)/2}\n"
                 "IQQ VDD IQQ 31.25u\n"
                 f"VSTB CMP_STROBE 0 PULSE(0 3.3 {T0_LOAD - 3 * TM - 0.25e-9:.10e} 0.5n 0.5n "
                 f"{TM - 0.5e-9:.10e} {T:.10e})")
        txt = txt[:m.start()] + block + txt[m.end():]
    txt = sub(r"^\.save .*$", "", txt)
    txt = sub(r"^\.tran .*$", "", txt)
    txt = sub(r"^\.end\s*$", "", txt)
    txt += f"""
.control
set noaskquit
save time v(sig) v(o1p) v(o1n) v(i1p) v(i1n) v(o2p) v(o2n) v(i2p) v(i2n) v(norm1) i(vdd_src)
tran {a.wstep:g} {a.tstop} 0 1e-09
linearize
wrdata out.csv v(sig) v(o1p) v(o1n) v(i1p) v(i1n) v(o2p) v(o2n) v(i2p) v(i2n) v(norm1) i(vdd_src)
quit
.endc
.end
"""
    open(os.path.join(a.out, "circuit.spice"), "w").write(txt)
    print(f"wrote {a.out}/circuit.spice (dac2={a.dac2}, quant={a.quant}, tstop={a.tstop}, "
          f"chop1={a.chop1:g}{' driver' if a.chop1_drv else ''}, ota1={a.ota1})")


if __name__ == "__main__":
    main()
