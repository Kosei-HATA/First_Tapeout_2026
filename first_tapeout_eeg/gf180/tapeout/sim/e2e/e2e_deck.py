#!/usr/bin/env python3
"""Short-window transistor E2E deck (tracker D4, L3): electrodes -> eeg_afe (with its
clock driver eeg_afe_clk) -> eeg_adc (with eeg_dac1/eeg_dac2/eeg_quantizer, the OTA1
chopper driver) on the real bias generator (eeg_bias) and reference filter (eeg_ref).
The DWA controller is the XSPICE model of the imported deck, as in adc_deck.py.

Timing (RTL, e_n = MCLK edge n of a frame):
  e0  CMP_STROBE; every 4th frame also a CHOP edge (128 kHz, CHOP_OUT = CHOP)
  CHOP_BLANK from 1 MCLK before to --blank MCLK after every CHOP edge
  e3  SEL1/SEL2 (controller), e4 DAC_CLK, e16 CHOP1 edges (--chop1)
AFE_RST (AFE input reset and ADC integrator reset) is high until --trst.
Electrodes: a sine of --amp V pk at --fsig on --vos V of offset (offset DAC off),
100 ohm per leg, on VCM. Bias codes at their reset values, CPF_TRIM 8.

out.csv columns: sig, outp, outn (AFE output), o1p, o1n, i1p, i1n, o2p, o2n, norm1,
i(avdd), on a --wstep grid (e2e_check.py reads them).

Usage: python3 e2e_deck.py <out_dir> [--tstop 70e-6] [--fsig 16e3] [--amp 0.943e-3]
       [--vos 0] [--chop1 4e3] [--blank 7] [--trst 10e-6] [--corner typical] [--temp 27]
       [--wstep 20e-9] [--tol fast|fine]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "adc_loop"))
import make_deck as md  # noqa: E402
import adc_deck as ad  # noqa: E402

AFE = os.path.join(md.REPO, "gf180", "tapeout", "afe")


def deck(a):
    T, TM, T0 = md.T, md.T / 32, md.T0_LOAD
    e0 = T0 - 3 * TM  # strobe of the frame whose DLOAD is T0
    sel = " ".join(f"SEL{j}" for j in range(31))
    seln = " ".join(f"SELN{j}" for j in range(31))
    s2l = " ".join(f"S2L{j}" for j in range(31))
    s2ln = " ".join(f"S2LN{j}" for j in range(31))
    th = " ".join(f"TH{j}" for j in range(31))
    strobe = f"PULSE(0 3.3 {e0 - 0.25e-9:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})"
    dclk = f"PULSE(0 3.3 {T0 + TM - 0.25e-9:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})"
    # AFE chopper: high (phase A) from 0, edges at e0 of every 4th frame from the first one
    chop = f"PULSE(3.3 0 {e0 - 0.25e-9:.10e} 0.5n 0.5n {4 * T - 0.5e-9:.10e} {8 * T:.10e})"
    blank = f"PULSE(0 3.3 {e0 - TM - 0.25e-9:.10e} 0.5n 0.5n {(1 + a.blank) * TM - 0.5e-9:.10e} {4 * T:.10e})"
    if a.chop1:
        p = 1 / a.chop1
        chop1 = f"PULSE(3.3 0 {T0 + 13 * TM - 0.25e-9:.10e} 0.5n 0.5n {p / 2 - 0.5e-9:.10e} {p:.10e})"
    else:
        chop1 = "3.3"
    poly = " ".join(f"SEL{j} 0" for j in range(31)) + " -.5" + " 0.0097751710654936461" * 31
    nets = [os.path.join(AFE, "eeg_afe.spice"), os.path.join(AFE, "eeg_afe_clk.spice")]
    nets += [os.path.join(ad.ADC, n) for n in ad.NETS]
    incs = "\n".join(f".include {n}" for n in nets)
    vec = ("v(sig) v(outp) v(outn) v(xadc.o1p) v(xadc.o1n) v(xadc.i1p) v(xadc.i1n) v(xadc.o2p) v(xadc.o2n) "
           "v(norm1) i(vavdd)")
    return f"""* E2E: eeg_afe -> eeg_adc, {a.corner} {a.temp:g} C, {a.amp * 1e3:g} mV pk {a.fsig:g} Hz on {a.vos * 1e3:g} mV
.include {md.PDK}/design.ngspice
.lib {md.PDK}/sm141064.ngspice {a.corner}
.lib {md.PDK}/sm141064.ngspice {ad.RES[a.corner]}
.lib {md.PDK}/sm141064.ngspice mimcap_{ad.CAPC[a.corner]}
.lib {md.PDK}/sm141064.ngspice cap_mim
.lib {md.PDK}/sm141064.ngspice moscap_{ad.CAPC[a.corner]}
.include quantizer.spice
{incs}
.include {ad.BIAS}
.temp {a.temp}
.options sparse method=trap maxord=2 {ad.TOLS[a.tol]} bypass=0
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
* references
VEP EP 0 1.9
RBP EP PADP 0.2
VEN EN 0 1.4
RBN EN PADN 0.2
XREF PADP PADN VREFP VREFN 0 eeg_ref
* bias generator at the reset codes (AFE_IBIAS 2, BOOST_TRIM 4 units)
VCIB1 IB1 0 3.3
VCIB0 IB0 0 0
VCBP1 BP1 0 0
VCBP0 BP0 0 3.3
VCBN1 BN1 0 0
VCBN0 BN0 0 3.3
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0
+ AVDD 0 eeg_bias
CVCMPAD VCM 0 100n
VITST ITST 0 1
* electrodes: sine on an offset, 100 ohm per leg, on VCM
VSIG SIG 0 SIN({a.vos:g} {a.amp:g} {a.fsig:g} 1.1u)
ESP SRCP VCM SIG 0 .5
ESN SRCN VCM SIG 0 -.5
RSP SRCP ELP 100
RSN SRCN ELN 100
* RTL-like clocks
VSTB CMP_STROBE 0 {strobe}
VDCLK DAC_CLK 0 {dclk}
VCHOP CHOP 0 {chop}
VBLANK CHOP_BLANK 0 {blank}
VCH1 CHOP1 0 {chop1}
VRST AFE_RST 0 PWL(0 3.3 {a.trst:g} 3.3 {a.trst + 5e-9:g} 0)
ENRST NRST 0 AVDD AFE_RST 1
* AFE clock driver (CHOP_OUT = CHOP, CHOP_EN = 1) and the AFE (offset DAC off, CPF_TRIM 8)
XAC CHOP CHOP CHOP_BLANK AVDD AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RSTA AVDD 0 eeg_afe_clk
XA ELP ELN OUTP OUTN VCM VBN VBCM BLP BLN RSTA CIA NCIA CIB NCIB CDA NCDA CDB NCDB
+ OFPH 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 AVDD AVDD 0 eeg_afe
.nodeset v(xa.inp)=1.65 v(xa.inn)=1.65 v(xa.opi)=1.65 v(xa.oni)=1.65 v(outp)=1.65 v(outn)=1.65
* ADC (integrators reset with AFE_RST)
XADC OUTP OUTN CHOP1 DAC_CLK CMP_STROBE AFE_RST NRST {sel}
+ {s2l}
+ {th}
+ VREFP VREFN VCM VBN1 VNC1 VPC1 VBCM1 VBPC2 VBNC2 IDP IDN IQ AVDD 0 DVDD 0 eeg_adc
XCTRL {th} DLOAD DRESET_EVENT AVDD 0 {sel}
+ {seln}
+ {s2l}
+ {s2ln} adc_ctrl_event
AEVENT [DLOAD DRESET_EVENT] CLOCK_EVENTS
.model CLOCK_EVENTS d_source(input_file="events.txt")
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
    ap.add_argument("--tstop", type=float, default=70e-6)
    ap.add_argument("--fsig", type=float, default=16e3)
    ap.add_argument("--amp", type=float, default=0.943e-3)
    ap.add_argument("--vos", type=float, default=0.0)
    ap.add_argument("--chop1", type=float, default=4e3)
    ap.add_argument("--blank", type=int, default=7)
    ap.add_argument("--trst", type=float, default=10e-6)
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27)
    ap.add_argument("--wstep", type=float, default=20e-9)
    ap.add_argument("--tol", choices=sorted(ad.TOLS), default="fast")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    q = open(os.path.join(md.IMPORT, "quantizer.spice")).read()
    q = md.sub(r"^\.model ADC33 adc_bridge \(in_low=0\.99 in_high=2\.31 ",
               ".model ADC33 adc_bridge (in_low=1.65 in_high=1.65 ", q)
    open(os.path.join(a.out, "quantizer.spice"), "w").write(q)
    open(os.path.join(a.out, "events.txt"), "w").write(md.events(a.tstop))
    open(os.path.join(a.out, "circuit.spice"), "w").write(deck(a))
    print(f"wrote {a.out}/circuit.spice ({a.corner} {a.temp:g} C, tstop {a.tstop:g}, tol {a.tol})")


if __name__ == "__main__":
    main()
