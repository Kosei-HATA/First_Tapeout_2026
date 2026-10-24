#!/usr/bin/env python3
"""Data for the Bode plots and Smith charts (tracker D4 / D6): CSV files in runs/viz/, for the
schematic (sch) and the final chip's extraction (pex), typical, 27 C, CPF_TRIM 8, the AFE
loaded by the ADC input RIN 18.75 kohm per side (as pex_afe.py).

  afe_loop  the AFE amplifier with the chopper frozen in phase A or B (an LTI circuit):
            loop gain T(f) of the closed loop (Cin, Cf, the parasitics) by Middlebrook's double
            injection at the break between the summing node INP and the input-pair gates INPG
            (the gates split from INP / INN as for the wiring resistance, pex_afe.py;
            differential probes): a series voltage (run vz) and a current into the gates (run
            iz), Tv = (1 - V1) / V1, Ti = -I2 / (1 + I2), T = (Tv Ti - 1) / (2 + Tv + Ti), exact
            with bilateral paths (Cf, the gate-drain capacitances). Open-loop gain
            A(f) = (OPI - ONI) / (INPG - INNG) with the loop opened there for AC (run ol: the
            gates follow the summing node's operating point through 1e16 H and are driven by
            ideal sources; the gates' load on the summing node is left out, which moves the
            output's load through Cf by < 0.1 % as Cin >> Cf); the gain measured in place agrees
            within 0.01 dB up to 100 MHz. (-T / beta with beta from a current pushed into the
            outputs fails here above ~5 MHz: beta is -51.6 dB, the order of the amplifier's
            reverse transmission.) 1 Hz - 1 GHz.
  ota       ADC OTA1 and OTA2 with their stage loads, the OTA1 chopper frozen: OTA1 with
            RIN (ppolyf, as eeg_adc), the DAC1 resistors (each input sees 31 x 600 kohm to
            the references for every code: 19.35 kohm to VCM), C1 (eeg_c1) cross-coupled,
            R21 to the stage-2 virtual ground (VCM) and the output wiring (2 pF in sch, 2.6 pF
            in pex: adc_top's extraction); OTA2 driven through R21, with C2 (eeg_c2), the
            quantizer's inputs (strobe low) and the wiring (2 pF / 0.8 pF); DAC2 is a cascoded
            current DAC (high impedance) and left out. T by double injection as for the AFE, at the
            break between the summing node and the OTA input pins; open-loop gain with the real
            loads A = -T / beta, beta(f) = (in diff) / (out diff) with a differential current
            pushed into the outputs (run inj; beta ~ C1 / (C1 + C_gate) ~ 1 here, far above the
            OTA's reverse transmission). This is the gain with the loop opened and the summing
            node loaded by RIN, RD1 and the gates (not held at virtual ground: the gain
            measured in place sees C1 / C2 to a virtual ground and levels off at their
            feed-through above the OTA's bandwidth, and its product with beta is not the loop
            gain). A 1e16 H inductor across each C sets the DC operating point (open from
            1 Hz). 1 Hz - 1 GHz.
  ntf       NTF and STF of the CT 2nd-order loop as implemented (time constants of
            gf180/behavioral/ct2_dac2_options.py: C1 halved with the resistors doubled and
            stage 2 scaled by 10 keep them; NRZ DACs, DAC2 updated 3 MCLK and DAC1 4 MCLK after
            the strobe), linear quantizer (gain from the 3.125 mV threshold step and the 2/31
            DAC step), integrator leakage from the OTA DC gains of `ota` (sch). Exact
            discretization (matrix exponential); STF(f) = k H_u(j 2 pi f) NTF(e^{j 2 pi f T}),
            normalized to its DC value. 0.1 Hz - 512 kHz.
  bb        AFE baseband signal transfer with chopping, from the frozen-phase transfer H(f)
            electrode -> OUTP - OUTN (afe_loop's run): the input chopper puts the signal at
            k fch +- f (odd k, weights 2/(j pi k)), the output chopper brings it back:
            G(f) = sum_k odd 4/(pi k)^2 [H(k fch + f) + conj H(k fch - f)]  (at f = 0 the
            in-band gain of afe_noise.py). Phase kept. The period average of the E2E checks
            adds sinc(f Tch) and -180 f Tch degrees (column *_avg). Blanking left out: the
            sum counts the amplifier output's settling after each chopper edge, which the
            7-MCLK blanking hides in the chip, so its level is some % below the transient
            runs of zin (afe_baseband_transient.csv), which are at the frozen-phase level.
  zin_ac    the frozen-phase AC input impedance over the whole sweep (reference only).
  zin       electrode-side input impedance with chopping (transient: a small sine on the
            electrodes, the fundamental of the electrode current over whole signal periods
            after settling; differential: Z = (VELP - VELN) / I, the current into ELP;
            common mode: both electrodes driven together, Z per side), and the frozen-phase AC
            value for reference (method column says which). The differential runs also give
            the chopped transfer source -> OUTP - OUTN with the blanking, for bb's check.

Usage: python3 gf180/tapeout/pex/viz_data.py afe_loop|ota|ntf|bb|zin|zin_ac [--variants sch pex]
       (bb reads afe_loop's runs; ntf reads ota's DC gains)
"""
import argparse
import json
from fractions import Fraction
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import pex_afe as pa  # noqa: E402

OUT = os.path.join(HERE, "runs", "viz")
ADC = os.path.join(REPO, "gf180", "tapeout", "adc")
REF = os.path.join(ADC, "eeg_ref.spice")
PEXR = os.path.join(HERE, "runs")
FCH, TCH = pa.FCH, pa.TCH

BIAS_ADC = """VEP EP 0 1.9
RBP EP PADP 0.2
VEN EN 0 1.4
RBN EN PADN 0.2
XREF PADP PADN VREFP VREFN 0 eeg_ref
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
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
"""


def run(d, deck, name="tb.spice"):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, name), "w").write(deck)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", name], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    if r.returncode:
        raise RuntimeError(f"ngspice failed in {d}")
    return time.time() - t


def read_pairs(path, n):
    """wrdata file of n vectors (x, y pairs) -> x, [y_1 .. y_n]."""
    x = np.loadtxt(path)
    return x[:, 0], [x[:, 2 * k + 1] for k in range(n)]


trapz = getattr(np, "trapezoid", None) or np.trapz


def db(h):
    return 20 * np.log10(np.abs(h))


def deg(h):
    return np.degrees(np.unwrap(np.angle(h)))


def margins(f, t):
    """First 0 dB crossing of |T| going down: (UGF Hz, phase margin deg = 180 + angle T);
    None where |T| does not cross in the sweep."""
    m = np.abs(t)
    ph = deg(t)
    for i in range(1, len(f)):
        if m[i - 1] >= 1 > m[i]:
            a = (np.log(m[i - 1])) / (np.log(m[i - 1]) - np.log(m[i]))
            fu = np.exp(np.log(f[i - 1]) + a * (np.log(f[i]) - np.log(f[i - 1])))
            pu = ph[i - 1] + a * (ph[i] - ph[i - 1])
            return float(fu), float(180 + pu)
    return None, None


def gain_margin(f, t):
    """First crossing of angle T through -180 deg going down: (Hz, gain margin dB = -|T|)."""
    m = db(t)
    ph = deg(t)
    for i in range(1, len(f)):
        if ph[i - 1] > -180 >= ph[i]:
            a = (ph[i - 1] + 180) / (ph[i - 1] - ph[i])
            return (float(np.exp(np.log(f[i - 1]) + a * (np.log(f[i]) - np.log(f[i - 1])))),
                    float(-(m[i - 1] + a * (m[i] - m[i - 1]))))
    return None, None


def unity(f, h):
    m = np.abs(h)
    for i in range(1, len(f)):
        if m[i - 1] >= 1 > m[i]:
            a = np.log(m[i - 1]) / (np.log(m[i - 1]) - np.log(m[i]))
            return float(np.exp(np.log(f[i - 1]) + a * (np.log(f[i]) - np.log(f[i - 1]))))
    return None


def write_csv(path, cols, rows, comment=""):
    """Header and data only (any CSV reader); the conditions go to <name>.txt beside it."""
    if comment:
        open(os.path.splitext(path)[0] + ".txt", "w").write(comment.strip() + "\n")
    with open(path, "w") as fo:
        fo.write(",".join(cols) + "\n")
        for r in rows:
            fo.write(",".join(r if isinstance(r, str) else f"{v:.6g}" if isinstance(v, float) else str(v)
                              for v in r) + "\n")
    print("wrote", os.path.relpath(path, REPO))


# ----------------------------------------------------------------------------------
# AFE, frozen phase
# ----------------------------------------------------------------------------------
def afe_dut(variant, extra, mode="src"):
    if variant == "sch":
        txt = "".join(f".include {f}\n" for f in pa.SCH_FILES)
        wrap = open(os.path.join(pa.LAYOUT, "lvs", "afe_top.spice")).read()
    else:
        txt = ""
        wrap = open(os.path.join(pa.PEXDIR, f"afe_top_{variant}.spice")).read()
    wrap = pa.split_signal_path(wrap, variant)
    # the split joined again through 1 mohm (0 V sources alone here stop the DC operating
    # point); the probe of the double injection sits between that resistor (driver side, the
    # summing node) and the gates
    extra = ("LDCP INP ONI 1e16\nLDCN INN OPI 1e16\nRTP INP INPA 1m\nRTN INN INNA 1m\n"
             + (open_loop("INPA", "INNA", "INPG", "INNG") if mode == "ol" else probe("INPA", "INNA", "INPG", "INNG", mode))
             + "RWP WPT WP 1m\nRWN WNT WN 1m\n") + extra
    return txt + wrap.replace(".ends afe_top", extra + ".ends afe_top")


def probe(ap, an, bp, bn, mode):
    """Differential double-injection probe from the driver side (ap, an) to the load side
    (bp, bn): series sources (+ at the load side) and currents into the load side."""
    vz = {"vz": ("0.5", "-0.5")}.get(mode, ("0", "0"))
    txt = f"VZP {bp} {ap} DC 0 AC {vz[0]}\nVZN {bn} {an} DC 0 AC {vz[1]}\n"
    if mode == "iz":
        txt += f"IZP 0 {bp} AC 0.5\nIZN 0 {bn} AC -0.5\n"
    return txt


def open_loop(ap, an, bp, bn):
    """The loop opened between (ap, an) and the gates (bp, bn) for AC, closed for DC: the gates
    follow the driver side's operating point through 1e16 H and get a differential AC 1 from
    ideal sources; the driver side is left without the gates' load."""
    return (f"LBP {ap} {ap}D 1e16\nLBN {an} {an}D 1e16\nCBP {ap}D 0 1\nCBN {an}D 0 1\n"
            f"VGP {bp} {ap}D DC 0 AC 0.5\nVGN {bn} {an}D DC 0 AC -0.5\n")


def middlebrook(v1, i2):
    """T from the double injection: v1 load-side voltage per unit series voltage (run vz),
    i2 driver-to-load current per unit injected current (run iz)."""
    tv = (1 - v1) / v1
    ti = -i2 / (1 + i2)
    return (tv * ti - 1) / (2 + tv + ti)


def afe_ac_deck(variant, phase, mode, fstart=1.0, fstop=1e9, ppd=40, cm=False):
    """mode src: electrode source AC 1 (differential, or common mode with cm); vz / iz: the
    double-injection runs; ol: the loop opened at the gates, which are driven; source at 0
    but for src."""
    chop, en = ("3.3", "0") if phase == "A" else ("0", "3.3")
    ac = "AC 1" if mode == "src" else "AC 0"
    en_n = "0.5" if cm else "-0.5"
    return f"""* afe_top {variant}: frozen phase {phase}, AC {mode}{' common mode' if cm else ''}
{pa.head()}.include {pa.BIAS}
{afe_dut(variant, "", mode)}
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
{pa.BIAS_LINES}VCHOP CHOP 0 {chop}
VCHOPO CHOP_OUT 0 {chop}
VBLK CHOP_BLANK 0 0
VEN CHOP_EN 0 {en}
VAR AFE_RST 0 0
VSRC SRC 0 DC 0 {ac}
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 {en_n}
RSP SRC_P ELP 100
RSN SRC_N ELN 100
RLOADP OUTP CM {pa.RIN:g}
RLOADN OUTN CM {pa.RIN:g}
{pa.xline()}
.nodeset v(xdut.inp)=1.65 v(xdut.inn)=1.65 v(xdut.opi)=1.65 v(xdut.oni)=1.65 v(outp)=1.65 v(outn)=1.65
.control
set noaskquit
op
ac dec {ppd} {fstart:g} {fstop:g}
let vo = v(xdut.opi) - v(xdut.oni)
let vi = v(xdut.inpg) - v(xdut.inng)
let vout = v(outp) - v(outn)
let ve = v(elp) - v(eln)
let ip = (v(src_p) - v(elp)) / 100
let iq = (v(src_n) - v(eln)) / 100
let vp = v(elp) - v(cm)
let iz = {"0 * vo" if mode == "ol" else "-(i(v.xdut.vzp) - i(v.xdut.vzn))"}
wrdata ac.csv real(vo) imag(vo) real(vi) imag(vi) real(vout) imag(vout) real(ve) imag(ve) real(ip) imag(ip) real(iq) imag(iq) real(vp) imag(vp) real(iz) imag(iz)
quit
.endc
.end
"""


def afe_ac(variant, phase, mode, cm=False):
    d = os.path.join(OUT, "work", f"afe_{variant}_{phase}_{mode}" + ("_cm" if cm else ""))
    run(d, afe_ac_deck(variant, phase, mode, cm=cm))
    f, c = read_pairs(os.path.join(d, "ac.csv"), 16)
    z = [c[2 * k] + 1j * c[2 * k + 1] for k in range(8)]
    return f, dict(vo=z[0], vi=z[1], vout=z[2], ve=z[3], ip=z[4], iq=z[5], vp=z[6], iz=z[7])


def do_afe_loop(variants):
    res = {}
    for v in variants:
        for ph in ("A", "B"):
            with ThreadPoolExecutor(4) as ex:
                (f, s), (_, rv), (_, ri), (_, ro) = ex.map(lambda m: afe_ac(v, ph, m), ("src", "vz", "iz", "ol"))
            t = middlebrook(rv["vi"], ri["iz"])
            a = ro["vo"] / ro["vi"]
            fu, pm = margins(f, t)
            f180, gm = gain_margin(f, t)
            res[f"{v}_{ph}"] = dict(A_dc_db=float(db(a[0])), A_ugf_hz=unity(f, a), T_dc_db=float(db(t[0])),
                                    T_max_db=float(db(t).max()), T_ugf_hz=fu, PM_deg=pm, GM_db=gm, f180_hz=f180)
            write_csv(os.path.join(OUT, f"afe_loop_{v}_{ph}.csv"), ["f_hz", "A_db", "A_deg", "T_db", "T_deg"],
                      [(float(x), float(y), float(z), float(p), float(q))
                       for x, y, z, p, q in zip(f, db(a), deg(a), db(t), deg(t))],
                      f"AFE amplifier, chopper frozen in phase {ph}, {v}, typical 27 C, CPF_TRIM 8, RIN 18.75k load\n"
                      f"T by Middlebrook double injection at the summing node / gate break; A = (OPI-ONI)/(INPG-INNG)\n"
                      f"with the loop opened there for AC (gates driven, DC closed through 1e16 H)\n"
                      + json.dumps(res[f"{v}_{ph}"]))
            # H from the source (100 ohm per leg in front of the electrodes, VSRC AC 1), as afe_noise.py
            np.save(os.path.join(OUT, "work", f"afe_{v}_{ph}_H.npy"), np.vstack([f, s["vout"], s["ve"],
                                                                               s["ip"], s["iq"]]))
            print(v, ph, json.dumps(res[f"{v}_{ph}"]))
    json.dump(res, open(os.path.join(OUT, "afe_loop_summary.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------
# ADC OTAs
# ----------------------------------------------------------------------------------
def ota_deck(which, variant, phase, mode):
    pin = lambda on: "3.3" if on else "0"
    a = phase == "A"
    chop = (f"VCIA CIA 0 {pin(a)}\nVNCIA NCIA 0 {pin(not a)}\nVCIB CIB 0 {pin(not a)}\nVNCIB NCIB 0 {pin(a)}\n"
            f"VCDA CDA 0 {pin(a)}\nVNCDA NCDA 0 {pin(not a)}\nVCDB CDB 0 {pin(not a)}\nVNCDB NCDB 0 {pin(a)}\n")
    ota_sch = os.path.join(ADC, "eeg_adc_otas.spice")
    if which == "ota1":
        ota = ota_sch if variant == "sch" else os.path.join(PEXR, "gf180_inside_cascode_ota_c",
                                                           "gf180_inside_cascode_ota_pex.spice")
        cw = "2p" if variant == "sch" else "2.6p"
        body = f"""{chop}EP INP VCM SIG 0 0.5
EN INN VCM SIG 0 -0.5
XRINP INP I1P 0 ppolyf_u_1k r_length=291.28u r_width=1u m=16
XRINN INN I1N 0 ppolyf_u_1k r_length=291.28u r_width=1u m=16
RD1P I1P VCM 19.355k
RD1N I1N VCM 19.355k
XC1P I1P O1N eeg_c1
XC1N I1N O1P eeg_c1
LF1P I1P O1N 1e16
LF1N I1N O1P 1e16
CW1P O1P 0 {cw}
CW1N O1N 0 {cw}
XR21P O1P VCM 0 ppolyf_u_1k r_length=291.28u r_width=1u m=3
XR21N O1N VCM 0 ppolyf_u_1k r_length=291.28u r_width=1u m=3
RTP I1P IAP 1m
RTN I1N IAN 1m
{probe("IAP", "IAN", "IXP", "IXN", mode)}XOTA1 IXP IXN O1P O1N VCM VBN1 VNC1 VPC1 VBCM1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB AVDD 0 gf180_inside_cascode_ota
"""
        o, i = ("o1p", "o1n"), ("ixp", "ixn")
        incs = [ota]
    else:
        ota = ota_sch if variant == "sch" else os.path.join(PEXR, "gf180_ct_ota_tel16_cmfb_c",
                                                           "gf180_ct_ota_tel16_cmfb_pex.spice")
        q = os.path.join(ADC, "eeg_quantizer.spice") if variant == "sch" else os.path.join(
            PEXR, "eeg_quantizer_c", "eeg_quantizer_pex.spice")
        cw = "2p" if variant == "sch" else "0.8p"
        th = " ".join(f"TH{k}" for k in range(31))
        body = f"""EP S2P VCM SIG 0 0.5
EN S2N VCM SIG 0 -0.5
XR21P S2P I2P 0 ppolyf_u_1k r_length=291.28u r_width=1u m=3
XR21N S2N I2N 0 ppolyf_u_1k r_length=291.28u r_width=1u m=3
XC2P I2P O2N eeg_c2
XC2N I2N O2P eeg_c2
LF2P I2P O2N 1e16
LF2N I2N O2P 1e16
CW2P O2P 0 {cw}
CW2N O2N 0 {cw}
XQ O2P O2N VREFP VREFN 0 {th} IQ AVDD 0 DVDD 0 eeg_quantizer
RTP I2P IAP 1m
RTN I2N IAN 1m
{probe("IAP", "IAN", "IXP", "IXN", mode)}XOTA2 IXP IXN O2P O2N VCM VBN1 VNC1 VPC1 VBCM1 AVDD 0 gf180_ct_ota_tel16_cmfb
"""
        o, i = ("o2p", "o2n"), ("ixp", "ixn")
        incs = [ota, q]
    if mode == "inj":
        body += f"IOP 0 {o[0].upper()} AC 0.5\nION 0 {o[1].upper()} AC -0.5\n"
    ac = "AC 1" if mode == "src" else "AC 0"
    incl = "".join(f".include {f}\n" for f in incs + [os.path.join(ADC, "eeg_adc.spice"), REF, pa.BIAS])
    return f"""* ADC {which} {variant}: phase {phase}, AC {mode}
{pa.head()}{incl}.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=1e-14 bypass=0
{BIAS_ADC}VSIG SIG 0 DC 0 {ac}
{body}.nodeset v({o[0]})=1.65 v({o[1]})=1.65 v({i[0]})=1.65 v({i[1]})=1.65
.control
set noaskquit
op
ac dec 40 1 1e9
let vo = v({o[0]}) - v({o[1]})
let vi = v({i[0]}) - v({i[1]})
let iz = -(i(vzp) - i(vzn))
wrdata ac.csv real(vo) imag(vo) real(vi) imag(vi) real(iz) imag(iz)
quit
.endc
.end
"""


def ota_ac(which, variant, phase, mode):
    d = os.path.join(OUT, "work", f"{which}_{variant}_{phase}_{mode}")
    run(d, ota_deck(which, variant, phase, mode))
    f, c = read_pairs(os.path.join(d, "ac.csv"), 6)
    return f, c[0] + 1j * c[1], c[2] + 1j * c[3], c[4] + 1j * c[5]


def do_ota(variants):
    res = {}
    jobs = [(w, v, ph) for w in ("ota1", "ota2") for v in variants for ph in (("A", "B") if w == "ota1" else ("A",))]

    def one(job):
        w, v, ph = job
        f, _, v1, _ = ota_ac(w, v, ph, "vz")
        _, _, _, i2 = ota_ac(w, v, ph, "iz")
        _, vo_j, vi_j, _ = ota_ac(w, v, ph, "inj")
        t = middlebrook(v1, i2)
        return job, f, -t / (vi_j / vo_j), t

    with ThreadPoolExecutor(4) as ex:
        for (w, v, ph), f, a, t in ex.map(one, jobs):
            fu, pm = margins(f, t)
            f180, gm = gain_margin(f, t)
            key = f"{w}_{v}" + (f"_{ph}" if w == "ota1" else "")
            res[key] = dict(A_dc_db=float(db(a[0])), A_ugf_hz=unity(f, a), T_max_db=float(db(t).max()),
                            T_ugf_hz=fu, PM_deg=pm, GM_db=gm, f180_hz=f180)
            write_csv(os.path.join(OUT, f"{key}.csv"), ["f_hz", "A_db", "A_deg", "T_db", "T_deg"],
                      [(float(x), float(y), float(z), float(p), float(q))
                       for x, y, z, p, q in zip(f, db(a), deg(a), db(t), deg(t))],
                      f"ADC {w.upper()} {v}{' chopper phase ' + ph if w == 'ota1' else ''}, typical 27 C, stage load\n"
                      f"T by double injection at the summing node / OTA input break (integrator loop); A = -T/beta,\n"
                      f"beta = (in diff)/(out diff) by output current injection (loaded open-loop gain)\n"
                      + json.dumps(res[key]))
            print(key, json.dumps(res[key]))
    json.dump(res, open(os.path.join(OUT, "ota_summary.json"), "w"), indent=1)


# ----------------------------------------------------------------------------------
# NTF / STF of the loop
# ----------------------------------------------------------------------------------
def do_ntf(_variants):
    from scipy.linalg import expm
    fs = 1.024e6
    T = 1 / fs
    vref = 0.5
    rin, rd1, c1 = 9375.0, 300e3 / 31, 680.5137683e-12
    r21, rd2, c2 = 1e6, (320e6 / 3) / 31, 1.953125e-12
    tau2, tau1 = 3 / 32 * T, 4 / 32 * T
    kq = (2 / 31) / 3.125e-3                       # DAC level per volt of O2 (diff)
    ota = {}
    p = os.path.join(OUT, "ota_summary.json")
    if os.path.exists(p):
        ota = json.load(open(p))
    a1 = 10 ** (ota.get("ota1_sch_A", {}).get("A_dc_db", np.inf) / 20) if ota else np.inf
    a2 = 10 ** (ota.get("ota2_sch", {}).get("A_dc_db", np.inf) / 20) if ota else np.inf
    rows_all = {}
    for tag, (g1a, g2a) in (("ideal", (np.inf, np.inf)), ("leaky", (a1, a2))):
        g1 = (1 / rin + 1 / rd1) / (g1a * c1)
        g2 = (1 / r21 + 1 / rd2) / (g2a * c2)
        M = np.array([[-g1, 0.0], [1 / (r21 * c2), -g2]])
        bu = np.array([1 / (rin * c1), 0.0])
        b1 = np.array([-vref / (rd1 * c1), 0.0])
        b2 = np.array([0.0, -vref / (rd2 * c2)])

        def seg(h):
            """exp(Mh) and int_0^h exp(M s) ds (via the augmented exponential)."""
            aug = np.zeros((4, 4))
            aug[:2, :2] = M * h
            aug[:2, 2:] = np.eye(2) * h
            e = expm(aug)
            return e[:2, :2], e[:2, 2:]

        # segments: [0,tau2) DACs at y[n-1]; [tau2,tau1) DAC2 at y[n]; [tau1,T) both at y[n]
        E1, I1 = seg(tau2)
        E2, I2 = seg(tau1 - tau2)
        E3, I3 = seg(T - tau1)
        Phi = E3 @ E2 @ E1
        g_old = E3 @ E2 @ I1 @ (b1 + b2) + E3 @ I2 @ b1      # y[n-1]
        g_new = E3 @ I2 @ b2 + I3 @ (b1 + b2)                 # y[n]
        C = np.array([0.0, 1.0])
        f = np.logspace(-1, np.log10(512e3), 1200)
        z = np.exp(1j * 2 * np.pi * f * T)
        L = np.array([C @ np.linalg.solve(zz * np.eye(2) - Phi, g_new + g_old / zz) for zz in z])
        ntf = 1 / (1 - kq * L)
        hu = np.array([C @ np.linalg.solve(1j * 2 * np.pi * ff * np.eye(2) - M, bu) for ff in f])
        stf = kq * hu * ntf
        stf0 = stf[0]
        rows_all[tag] = (f, ntf, stf / stf0, abs(stf0))
    f, ntf, stf, s0 = rows_all["leaky"]
    fi, ntfi, stfi, _ = rows_all["ideal"]
    write_csv(os.path.join(OUT, "adc_ntf_stf.csv"),
              ["f_hz", "ntf_db", "ntf_deg", "stf_db", "stf_deg", "ntf_ideal_db", "ntf_ideal_deg"],
              [(float(a), float(b), float(c), float(d), float(e), float(g), float(h))
               for a, b, c, d, e, g, h in zip(f, db(ntf), deg(ntf), db(stf), deg(stf), db(ntfi), deg(ntfi))],
              "CT 2nd-order 5-bit loop as implemented: fs 1.024 MHz, NRZ DAC2 at 3/32 T and DAC1 at 4/32 T after the\n"
              "strobe, RIN C1 = 6.380 us, RD1 C1 = 6.586 us, R21 C2 = 1.953 us, RD2 C2 = 6.720 us, VREF 0.5 V,\n"
              f"quantizer gain {kq:.2f}/V (linear); leaky integrators from the OTA DC gains A1 {db(a1):.1f} dB,\n"
              f"A2 {db(a2):.1f} dB (ota, sch); ntf_ideal: infinite OTA gain. STF normalized to its DC value\n"
              f"({s0:.4f} DAC level per volt at the ADC input, i.e. DC gain RD1/(RIN VREF) = 2.065).")
    i = np.argmin(np.abs(f - 100))
    print(f"NTF at 100 Hz {db(ntf[i]):.1f} dB (ideal {db(ntfi[i]):.1f}), at fs/2 {db(ntf[-1]):.1f} dB; "
          f"STF at 100 Hz {db(stf[i]):.4f} dB, max |NTF| {db(ntf).max():.1f} dB")


# ----------------------------------------------------------------------------------
# AFE baseband transfer (harmonic sum)
# ----------------------------------------------------------------------------------
def do_bb(variants):
    f_bb = np.logspace(-1, np.log10(64e3), 400)
    for v in variants:
        for ph in ("A", "B"):
            p = os.path.join(OUT, "work", f"afe_{v}_{ph}_H.npy")
            if not os.path.exists(p):
                print("run afe_loop first:", p)
                continue
            dat = np.load(p)
            f, h = dat[0].real, dat[1]
            lf = np.log(f)
            hi = lambda x: np.interp(np.log(x), lf, h.real) + 1j * np.interp(np.log(x), lf, h.imag)
            kmax = int(f[-1] / FCH) - 1
            ks = np.arange(1, kmax + 1, 2)
            g = np.array([np.sum(4 / (np.pi * ks) ** 2 * (hi(ks * FCH + x) + np.conj(hi(ks * FCH - x)))) for x in f_bb])
            avg = g * np.sinc(f_bb * TCH) * np.exp(-1j * np.pi * f_bb * TCH)
            write_csv(os.path.join(OUT, f"afe_baseband_{v}_{ph}.csv"),
                      ["f_hz", "gain_db", "phase_deg", "gain_avg_db", "phase_avg_deg"],
                      [(float(a), float(b), float(c), float(d), float(e))
                       for a, b, c, d, e in zip(f_bb, db(g), deg(g), db(avg), deg(avg))],
                      f"AFE baseband transfer with chopping, electrode source (diff, 100 ohm per leg) -> OUTP-OUTN, {v},\n"
                      f"frozen-phase H of phase {ph}\n"
                      f"harmonic sum over odd k up to {kmax} (fch 128 kHz); *_avg: with the chopper-period average (sinc)\n"
                      f"gain at 0.1 Hz {abs(g[0]):.2f} ({db(g[0]):.2f} dB); frozen-phase in-band |H| {abs(h[0]):.2f}\n"
                      f"blanking not modelled: the sum counts the output's settling after each chopper edge, which the\n"
                      f"7-MCLK blanking hides; afe_baseband_transient.csv has the chopped transient with the blanking")
            print(v, ph, f"gain {abs(g[0]):.2f} at 0.1 Hz, {abs(g[-1]):.2f} at 64 kHz")


# ----------------------------------------------------------------------------------
# electrode input impedance
# ----------------------------------------------------------------------------------
def zin_deck(variant, f_sig, amp, cm, tsettle, tstop):
    """The electrode currents run through 0 V meters into 1 F integrators (q = int i dt, smooth),
    so the spikes at the chopper edges are counted exactly on a coarse output grid."""
    chop = f"PULSE(0 3.3 {TCH / 2:.6e} 0.5n 0.5n {TCH / 2 - 0.5e-9:.6e} {TCH:.6e})"
    bl = f"PULSE(0 3.3 {TCH / 2 - pa.MCLK:.6e} 0.5n 0.5n {pa.MCLK + pa.BLANK - 0.5e-9:.6e} {TCH / 2:.6e})"
    src = (f"SIN(0 {amp:g} {f_sig:g} 50u)" if f_sig > 0 else f"PWL(0 0 50u 0 51u {amp:g})")
    en_n = "0.5" if cm else "-0.5"
    return f"""* afe_top {variant}: input impedance, {'common' if cm else 'differential'} mode, {f_sig:g} Hz
{pa.head()}.include {pa.BIAS}
{pa.dut_text(variant)}
.temp 27
.options sparse reltol=1e-5 vntol=1e-8 abstol=1e-12 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
{pa.BIAS_LINES}VCHOP CHOP 0 {chop}
VCHOPO CHOP_OUT 0 {chop}
VBLK CHOP_BLANK 0 {bl}
VEN CHOP_EN 0 3.3
VAR AFE_RST 0 PWL(0 3.3 10u 3.3 11u 0)
VSRC SRC 0 {src}
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 {en_n}
VMP SRC_P SRC_PM 0
VMN SRC_N SRC_NM 0
RSP SRC_PM ELP 100
RSN SRC_NM ELN 100
FQP 0 QP VMP 1
CQP QP 0 1
RQP QP 0 1e15
FQN 0 QN VMN 1
CQN QN 0 1
RQN QN 0 1e15
GQO 0 QO OUTP OUTN 1
CQO QO 0 1
RQO QO 0 1e15
RLOADP OUTP CM {pa.RIN:g}
RLOADN OUTN CM {pa.RIN:g}
{pa.xline()}
.nodeset v(xdut.inp)=1.65 v(xdut.inn)=1.65 v(xdut.opi)=1.65 v(xdut.oni)=1.65 v(outp)=1.65 v(outn)=1.65
.ic v(qp)=0 v(qn)=0 v(qo)=0
.control
set noaskquit
tran 100n {tstop:.6e} {tsettle:.6e} 4n
linearize
let vp = v(elp) - v(cm)
let vq = v(eln) - v(cm)
wrdata tr.csv v(qp) v(qn) vp vq v(qo) v(src)
quit
.endc
.end
"""


def whole_periods(f_sig, n_min):
    """Number of signal periods >= n_min that is also a whole number of chopper periods, so
    the chopper harmonics and their sidebands k fch +- f leave nothing in the signal's bin."""
    p = (Fraction(f_sig).limit_denominator(10 ** 6) / Fraction(FCH).limit_denominator(10 ** 6)).numerator
    return p * -(-n_min // p)


def zin_one(variant, f_sig, cm, amp=0.2e-3):
    """Fundamental of V and of the electrode current over whole signal periods after tsettle
    (current from the charge integrator by parts: int i e^-jwt = [q e^-jwt] + jw int q e^-jwt;
    the output the same way from its integral); f = 0: a DC step, the mean current over 16
    chopper periods."""
    tsettle = 0.4e-3
    span = whole_periods(f_sig, 1) / f_sig if f_sig > 0 else 16 * TCH
    tag = f"zin_{variant}_{'cm' if cm else 'dm'}_{f_sig:g}Hz"
    d = os.path.join(OUT, "work", tag)
    t0 = time.time()
    run(d, zin_deck(variant, f_sig, amp, cm, tsettle, tsettle + span))
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, qp, qn, vp, vq, qo, vs = x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7], x[:, 9], x[:, 11]
    m = t >= tsettle
    t, qp, qn, vp, vq, qo, vs = t[m], qp[m], qn[m], vp[m], vq[m], qo[m], vs[m]
    tw = t[-1] - t[0]
    if f_sig > 0:
        w = 2 * np.pi * f_sig
        e = np.exp(-1j * w * t)
        vf = lambda y: 2 * trapz(y * e, t) / tw
        jf = lambda q: 2 * ((q[-1] * e[-1] - q[0] * e[0]) + 1j * w * trapz(q * e, t)) / tw
    else:
        vf = lambda y: trapz(y, t) / tw
        jf = lambda q: (q[-1] - q[0]) / tw
    g = None
    if cm:
        z = vf(vp) / jf(qp)          # per side (each electrode to the common mode)
    else:
        z = (vf(vp) - vf(vq)) / jf(qp)
        if f_sig > 0:
            g = complex(jf(qo) / vf(vs))
    return dict(f=f_sig, z=complex(z), g=g, cm=cm, variant=variant, t=time.time() - t0)


def do_zin(variants, points=None, workers=8):
    pts = points or [0.0, 100.0, 1e3, 4e3, 16e3, 50e3]
    jobs = [(v, fz, cm) for v in variants for fz in (pts if v == "sch" else [0.0, 1e3]) for cm in (False, True)]
    # the longest first: pex, then the low frequencies (one period of 100 Hz is 10 ms)
    jobs.sort(key=lambda j: (j[0] == "sch", j[1] == 0, j[1]))
    rows, grows = [], []
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(zin_one, *j) for j in jobs]
        for fu in as_completed(futs):
            r = fu.result()
            rows.append((r["f"], r["z"].real, r["z"].imag, f"transient-chopped-{'cm' if r['cm'] else 'dm'}",
                         r["variant"]))
            if r["g"] is not None:
                grows.append((r["f"], float(db(r["g"])), float(np.degrees(np.angle(r["g"]))),
                              "transient-chopped-blanked", r["variant"]))
            print(r["variant"], "cm" if r["cm"] else "dm", r["f"], f"Z {r['z']:.4g}",
                  f"G {abs(r['g']):.2f}" if r["g"] is not None else "", f"({r['t']:.0f} s)", flush=True)
    grows.sort(key=lambda r: (r[4], r[0]))
    write_csv(os.path.join(OUT, "afe_baseband_transient.csv"), ["f_hz", "gain_db", "phase_deg", "method", "netlist"],
              grows, "AFE chopped transfer source (diff, 100 ohm per leg) -> OUTP-OUTN from the transient runs of zin\n"
              "(0.2 mV sine, choppers at 128 kHz with the 7-MCLK blanking, fundamental over whole signal and chopper\n"
              "periods after 0.4 ms): the check of afe_baseband_*.csv, whose harmonic sum has no blanking")
    # frozen-phase AC reference
    for v in variants:
        for cm in (False, True):
            f, s = afe_ac(v, "A", "src", cm=cm)
            zz = s["vp"] / s["ip"] if cm else s["ve"] / s["ip"]
            for fr in [1.0, 10.0, 100.0, 1e3, 4e3, 16e3, 50e3, 1e5, 1e6]:
                i = np.argmin(np.abs(np.log(f / fr)))
                rows.append((float(f[i]), float(zz[i].real), float(zz[i].imag),
                             f"frozen-phase-AC-{'cm' if cm else 'dm'} (reference only)", v))
    rows.sort(key=lambda r: (r[4], r[3], r[0]))
    write_csv(os.path.join(OUT, "afe_zin.csv"), ["f_hz", "re_ohm", "im_ohm", "method", "netlist"],
              [(float(a), float(b), float(c), m, n) for a, b, c, m, n in rows],
              "Electrode-side input impedance of the AFE, typical 27 C, CPF_TRIM 8, 100 ohm per leg, fch 128 kHz\n"
              "dm: (V_ELP - V_ELN) / I_ELP with a differential drive; cm: V_ELP / I_ELP per side with both driven\n"
              "transient-chopped: fundamental of a 0.2 mV sine after settling (f = 0: DC step, average over\n"
              "chopper periods); frozen-phase AC: chopper stopped in phase A, for reference only")


def do_zin_ac(variants):
    """Frozen-phase AC input impedance (chopper stopped in phase A), the whole sweep."""
    rows = []
    for v in variants:
        for cm in (False, True):
            f, s = afe_ac(v, "A", "src", cm=cm)
            zz = s["vp"] / s["ip"] if cm else s["ve"] / s["ip"]
            rows += [(float(a), float(b.real), float(b.imag), f"frozen-phase-AC-{'cm' if cm else 'dm'} (reference only)", v)
                     for a, b in zip(f, zz)]
    write_csv(os.path.join(OUT, "afe_zin_frozen_ac.csv"), ["f_hz", "re_ohm", "im_ohm", "method", "netlist"], rows,
              "Electrode-side input impedance of the AFE with the chopper stopped in phase A (an LTI circuit; the\n"
              "chopper's switched-capacitor action is missing, so this is a reference only, not the chip's input\n"
              "impedance: see the transient-chopped rows of afe_zin.csv), typical 27 C, CPF_TRIM 8, 100 ohm per leg\n"
              "dm: (V_ELP - V_ELN) / I_ELP with a differential drive; cm: V_ELP / I_ELP per side with both driven")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["afe_loop", "ota", "ntf", "bb", "zin", "zin_ac"])
    ap.add_argument("--variants", nargs="+", default=["sch", "pex"])
    ap.add_argument("--points", nargs="+", type=float)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(os.path.join(OUT, "work"), exist_ok=True)
    if a.what == "zin":
        do_zin(a.variants, a.points, a.workers)
    else:
        {"afe_loop": do_afe_loop, "ota": do_ota, "ntf": do_ntf, "bb": do_bb, "zin_ac": do_zin_ac}[a.what](a.variants)


if __name__ == "__main__":
    main()
