#!/usr/bin/env python3
"""Transistor-level ADC loop deck (tracker B2/D2): the ADC block eeg_adc
(gf180/tapeout/adc/eeg_adc.spice) with the real bias generator (eeg_bias), the
reference filter (eeg_ref) and the RTL frame timing; the DWA controller is the
XSPICE model of the imported deck (adc_ctrl_event), as in make_deck.py --quant tr.

Frame timing (e_n = MCLK edge n of a frame, as eeg_digital_top):
  e0  CMP_STROBE rises (one MCLK), the quantizer decides
  e3  DLOAD: the controller takes TH and updates SEL1/SEL2 (DAC2 switches)
  e4  DAC_CLK rises (one MCLK): DAC1 switches (common-break drive)
  e16 CHOP1 edges (--chop1, 0 = phase A all the time)
Supplies AVDD/DVDD ideal 3.3 V. References: ideal 1.9/1.4 V through 0.2 ohm into
eeg_ref. Bias codes at their reset values (AFE_IBIAS 2, BOOST_TRIM 4 units).
Input: ideal differential sine on VCM (from eeg_bias, 100 nF at the VCM pad). With --zero,
the ADC_ZERO test of TEST_CFG[5] instead: the inputs carry only the AFE hold capacitors
(the output chopper is open) and the INP-INN switch of eeg_adc is closed.
The integrators are reset (RST = 1) until 1 us.

out.csv has the columns of make_deck.py (sig, o1p, o1n, i1p, i1n, o2p, o2n, i2p, i2n,
norm1, i(avdd)) on a --wstep grid, so analyze_tone.py and chop1_fold.py apply.

Usage: python3 adc_deck.py <out_dir> [--tstop 1.25e-3] [--fsig 1e3] [--amp 0.3]
       [--chop1 4e3] [--corner typical] [--temp 27] [--wstep 20e-9] [--tol fast|fine] [--zero]
Then: (cd <out_dir> && ngspice -b circuit.spice) -> out.csv
"""
import argparse
import os
import make_deck as md

HERE = os.path.dirname(os.path.abspath(__file__))
ADC = os.path.join(md.REPO, "gf180", "tapeout", "adc")
BIAS = os.path.join(md.REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
NETS = ["eeg_adc_otas.spice", "eeg_adc_clk.spice", "eeg_dac1.spice", "eeg_dac2.spice",
        "eeg_quantizer.spice", "eeg_ref.spice", "eeg_adc.spice"]
RES = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff", "sf": "res_typical", "fs": "res_typical"}
CAPC = {"typical": "typical", "ss": "ss", "ff": "ff", "sf": "typical", "fs": "typical"}
# fine: as make_deck.py (spectra); fast: functional runs of the full transistor ADC
TOLS = {"fine": "reltol=1e-5 vntol=1e-7 abstol=1e-12 chgtol=1e-16",
        "fast": "reltol=1e-4 vntol=1e-6 abstol=1e-11 chgtol=1e-15"}


def deck(a):
    T, TM, T0 = md.T, md.T / 32, md.T0_LOAD
    sel = " ".join(f"SEL{j}" for j in range(31))
    seln = " ".join(f"SELN{j}" for j in range(31))
    s2l = " ".join(f"S2L{j}" for j in range(31))
    s2ln = " ".join(f"S2LN{j}" for j in range(31))
    th = " ".join(f"TH{j}" for j in range(31))
    strobe = f"PULSE(0 3.3 {T0 - 3 * TM - 0.25e-9:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})"
    dclk = f"PULSE(0 3.3 {T0 + TM - 0.25e-9:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})"
    if a.chop1:
        p = 1 / a.chop1
        chop = f"PULSE(3.3 0 {T0 + 13 * TM - 0.25e-9:.10e} 0.5n 0.5n {p / 2 - 0.5e-9:.10e} {p:.10e})"
    else:
        chop = "3.3"
    poly = " ".join(f"SEL{j} 0" for j in range(31)) + " -.5" + " 0.0097751710654936461" * 31
    incs = "\n".join(f".include {os.path.join(ADC, n)}" for n in NETS)
    vec = ("v(sig) v(xadc.o1p) v(xadc.o1n) v(xadc.i1p) v(xadc.i1n) v(xadc.o2p) v(xadc.o2n) "
           "v(xadc.i2p) v(xadc.i2n) v(norm1) i(vavdd)")
    if a.zero:  # ADC_ZERO: AFE output chopper open, only the 30 pF hold capacitors on the
        # inputs (started 20 mV apart), the INP-INN switch closed; v(sig) is then INP - INN
        inp = ("* input: ADC_ZERO test (AFE output chopper open, hold capacitors only)\n"
               "VAZ AZERO 0 3.3\nCHP INP 0 30p\nCHN INN 0 30p\nESIG SIG 0 INP INN 1\n"
               ".ic v(inp)=1.66 v(inn)=1.64\n")
    else:
        inp = (f"* input\nVSIG SIG 0 SIN(0 {a.amp} {a.fsig} 1.1u)\nEINP INP VCM SIG 0 .5\n"
               "EINN INN VCM SIG 0 -.5\nVAZ AZERO 0 0\n")
    return f"""* eeg_adc loop: {a.corner} {a.temp} C, {a.fsig:g} Hz {a.amp:g} V pk, CHOP1 {a.chop1:g} Hz
.include {md.PDK}/design.ngspice
.lib {md.PDK}/sm141064.ngspice {a.corner}
.lib {md.PDK}/sm141064.ngspice {RES[a.corner]}
.lib {md.PDK}/sm141064.ngspice mimcap_{CAPC[a.corner]}
.lib {md.PDK}/sm141064.ngspice cap_mim
.lib {md.PDK}/sm141064.ngspice moscap_{CAPC[a.corner]}
.include quantizer.spice
{incs}
.include {BIAS}
.temp {a.temp}
.options sparse method=trap maxord=2 {TOLS[a.tol]} bypass=0
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
* references (the bond-wire inductance is left out: with the on-chip capacitors it
* rings near 400 MHz at every DAC1 break and slowed the solver ~10x; ref_check.py
* covers it)
VEP EP 0 1.9
RBP EP PADP 0.2
VEN EN 0 1.4
RBN EN PADN 0.2
XREF PADP PADN VREFP VREFN 0 eeg_ref
* bias generator at the reset codes; AFE-side outputs into dummy diodes
VCIB1 IB1 0 3.3
VCIB0 IB0 0 0
VCBP1 BP1 0 0
VCBP0 BP0 0 3.3
VCBN1 BN1 0 0
VCBN0 BN0 0 3.3
XLN BLN BLN 0 0 nfet_03v3 W=20u L=8u nf=1 m=4
XLP BLP BLP AVDD AVDD pfet_03v3 W=20u L=8u nf=1 m=4
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0
+ AVDD 0 eeg_bias
CVCMPAD VCM 0 100n
VITST ITST 0 1
{inp}* frame timing
VSTB CMP_STROBE 0 {strobe}
VDCLK DAC_CLK 0 {dclk}
VCH1 CHOP1 0 {chop}
VRST RST 0 PWL(0 3.3 1u 3.3 1.005u 0)
ENRST NRST 0 AVDD RST 1
XADC INP INN CHOP1 DAC_CLK CMP_STROBE RST NRST AZERO {sel}
+ {s2l}
+ {th}
+ VREFP VREFN VCM VBN1 VNC1 VPC1 VBCM1 VBPC2 VBNC2 IDP IDN IQ AVDD 0 DVDD 0 eeg_adc
XCTRL {th} DLOAD DRESET_EVENT AVDD 0 {sel}
+ {seln}
+ {s2l}
+ {s2ln} adc_ctrl_event
AEVENT [DLOAD DRESET_EVENT] CLOCK_EVENTS
.model CLOCK_EVENTS d_source(input_file="events.txt")
* DAC1 level monitor (as the imported deck's ESUM1): -0.5 + k/31
ESUM1 NORM1 0 POLY(31) {poly}
.control
set noaskquit
save time {vec}
tran {a.wstep:g} {a.tstop} 0 1e-09
linearize
wrdata out.csv {vec}
quit
.endc
.end
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--tstop", type=float, default=1.25e-3)
    ap.add_argument("--fsig", type=float, default=1e3)
    ap.add_argument("--amp", type=float, default=0.3)
    ap.add_argument("--chop1", type=float, default=4e3, help="OTA1 chopper (Hz), 0 = phase A")
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27)
    ap.add_argument("--wstep", type=float, default=20e-9)
    ap.add_argument("--tol", choices=sorted(TOLS), default="fast")
    ap.add_argument("--zero", action="store_true",
                    help="ADC_ZERO test: inputs on the 30 pF hold capacitors only, INP-INN switch closed")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    q = open(os.path.join(md.IMPORT, "quantizer.spice")).read()
    q = md.sub(r"^\.model ADC33 adc_bridge \(in_low=0\.99 in_high=2\.31 ",
               ".model ADC33 adc_bridge (in_low=1.65 in_high=1.65 ", q)
    open(os.path.join(a.out, "quantizer.spice"), "w").write(q)
    open(os.path.join(a.out, "events.txt"), "w").write(md.events(a.tstop))
    open(os.path.join(a.out, "circuit.spice"), "w").write(deck(a))
    print(f"wrote {a.out}/circuit.spice ({a.corner} {a.temp:g} C, tstop {a.tstop:g}, chop1 {a.chop1:g}, "
          f"tol {a.tol})")


if __name__ == "__main__":
    main()
