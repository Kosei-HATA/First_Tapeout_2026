#!/usr/bin/env python3
"""The chip's supply rejection (11/18, r12): afe_startup.py's start deck (power-on; the extracted afe_top, eeg_bias and
eeg_ref on the chip wiring with the pads, bond wires and the board; AFE_IBIAS 3; the AFE released at 5 ms) with ripple
tones on one regulator's output (--rip AVDD | DVDD: 10 mV pk each at the regulator, ahead of its 0.05 ohm and the
board's 10 uF + 100 nF; from 2.5 ms under a 2 ms raised-cosine envelope) and the legs' impedances set by --zp / --zn
(100 ohm each, or ELP 100 ohm + 51 kohm || 47 nF, the ECG standards' electrode imbalance).

The tones: 1 kHz, and 128 kHz x k + (1 + k / 4) kHz for k = 1, 2, 3. Ripple that enters between the AFE's two
choppers comes out of the output chopper shifted by its harmonics, so the tone next to harmonic k lands on (1 + k / 4)
kHz: each tone has its own frequency at the output, and every tone is a whole number of periods in the window.

Each ripple run is compared with its baseline, the common-mode baseline of cmrr.py (--cm 0, the same legs): the ripple
deck is that deck plus the ripple's B source (and two saved board nodes), so the start-up's own drift drops out (a
polynomial of order 2 takes the rest; a run without a finished baseline is fitted alone, order 4). In the window
T0-T1 (6-10 ms):
  - the ripple at each tone on the board next to the chip (v(AVDD_BRD), v(DVDD_BRD): what a regulator's noise and
    ripple specifications refer to, with the board's decoupling) and on the chip (the AFE's AVDD - AVSS; the pad
    ring's DVDD - DVSS), fitted on the raw 100 ns grid (the chopper's harmonics are whole numbers of periods in the
    window, orthogonal to the tones);
  - OUTP - OUTN at the ADC's input, in band: three boxcars of 62.5 us (8 chopper periods: zeros at every multiple of
    16 kHz, so at every chopper harmonic and every tone's direct component next to one) on the 100 ns grid from the
    exact running integral qo, then the tones' output frequencies fitted, the boxcars' sinc^3 and delay taken out.
    The chip's CIC (sinc^3, R = 1024 at 1.024 MHz, zeros at every 1 kHz) rejects those direct components as well;
    chopper-period means would alias them onto the folded frequencies instead. Referred to the electrodes by the
    AFE's gain on this deck (figure 38's typical run, cmrr.gain());
  - for the 1 kHz tone also the pins' differential, the legs' currents (each leg's admittance to the supply, Y = I / V
    against the board's ripple: conductance and capacitance) and the electrodes' share of the output, the legs'
    currents through their own impedances, -(Ip Zp - In Zn), as in cmrr.py; and the body's and the board VCM's
    movement;
  - the supply rejection, 20 log10(ripple / output at the electrodes), against the board's ripple and the chip's;
  - the output's spread over variants of the fit (the polynomial one order lower and higher; the RC time constants
    x 0.9 and x 1.1) and the same tones fitted on the baseline alone (the method's floor without ripple);
  - the 1 kHz tone's conversion between the choppers, which the output chopper turns into a square wave at the ADC's
    input (fc -+ 1 kHz, 3 fc -+ 1 kHz on the raw grid): out of band, but it takes the ADC's range;
  - for every tone the conversion between the choppers itself: the amplifier's own OPI - ONI (before the output
    chopper) at the tone's frequency per V of the board's ripple; the output chopper's odd harmonic k brings (2 / pi) / k
    of it into band (fold_pred_uv), which is how the tones next to 128 and 384 kHz come back;
  - for the 1 kHz tone on AVDD, each leg's capacitance to AVDD split: the input switches' PMOS wells (switches_supply(),
    AVDD against the pins), through Cin (CIN_PF, the amplifier's input common mode against the pins) and the rest;
  - in band (BAND) from the typical runs: the 1 kHz transfer carried down (band_transfer()), and the flat regulator
    noise that adds 5 % to the AFE's own NOISE_NV, in band and next to each chopper harmonic (both sides fold).
Checked on cmrr.py's runs (11/18): the three boxcars give cmrr.py's numbers wherever the in-band part dominates (51 kohm
|| 47 nF: 286.20 against 285.84 uV at 1 kHz, 194.15 against 193.97 uV at 50 Hz, the harmonics 2f and 3f fitted too),
but the balanced 1 kHz run's 0.52 uV was the chopped conversion (fc -+ 1 kHz, 66.7 mV each at the output) that
chopper-period means alias onto 1 kHz (x 0.0078): in band it is 0.0038 uV.

Results (11/19, typical, figure 46): legs of 100 ohm, AVDD 139 dB at 1 kHz but 52.4 dB next to 128 kHz (the
amplifier's OPI - ONI carries 1.10 V/V of the ripple between the choppers; (2 / pi) of it predicts 20.70 uV against
21.08 uV in band) and 61.2 dB next to 384 kHz; DVDD 197 / 114 dB. ELP 51 kohm || 47 nF: AVDD 62.5 dB in band at 50 Hz
(each leg's 59.0 pF to AVDD = the switches' wells 23.7 + through Cin 23.9 + 11.4 not split). The Monte Carlo dies and
corners have no baselines and are fitted alone: on the typical runs the folded tones agree to 1e-5, but the 1 kHz and
257.5 kHz tones sit near the method's floor (legs of 100 ohm, 1 kHz: 142.9 against 139.1 dB) and the legs' admittances
keep only their sum (the split between P and N takes +-3 pF, +-7 nS of the start-up's drift); the split of the
capacitance is done on the typical runs only. Monte Carlo dies 1-8 (11/19): 52.1-52.8 dB next to 128 kHz (sd 0.24 dB)
and 60.9-61.6 dB next to 384 kHz, the conversion between the choppers 1.05-1.13 V/V, each die's fold the same multiple
of its (2 / pi) / k prediction (1.02 for k = 1, 1.11-1.12 for k = 3): not mismatch; the legs' mean 58.6-59.4 pF.
MOS corners (11/19): ff 51.5 dB (1.23 V/V), ss 53.2 dB (0.99 V/V), sf and fs as typical; the 1 kHz conversion moves by
the same ratio. The lowest (ff) allows 43 nV/rtHz next to 128 and 384 kHz together (41 with the odd harmonics above 3).

r13 (11/19 evening, the first four runs; afe_top's summing nodes interdigitated, SYM_GATES; no baselines, each fitted
alone): next to 128 kHz typical 68.7 dB, ff 67.7, ss 69.3, ELP 51 kohm || 47 nF 64.4 dB (r12: 52.4, 51.5, 53.2, 47.5);
next to 384 kHz typical 77.5 dB; the conversion between the choppers 0.169 V/V (ff 0.189, ss 0.156; r12 1.10), as
expected from the remaining 256 fF of difference plus diagnostics B / D's 0.058 V/V. The noise allowed next to 128 and
384 kHz together with the odd harmonics above 3: ff 264 nV/rtHz (r12 41); in band (51 kohm || 47 nF) unchanged,
62.4 dB at 50 Hz, 232 nV/rtHz.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr.py      (every ripple run of r12; runs/psrr_r12/results.json)
       EEG_PEX_REV=r13 gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr.py     (the runs tagged _chip_r13; runs/psrr_r13)
"""
import glob
import json
import os
import re
import subprocess

import numpy as np

import cmrr as C

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs", "startup")
REV = os.environ.get("EEG_PEX_REV") or "r12"      # the chip of the runs (tag _chip_<REV>); r13: EEG_PEX_REV=r13
OUT = os.path.join(HERE, "runs", f"psrr_{REV}")
T0, T1 = 6e-3, 10e-3
FCH = 1 / C.TCH                       # 128 kHz
LBOX = 8 * C.TCH                      # 62.5 us
DEC = 10                              # the filtered output is fitted every 1 us
SUPPLY = {"AVDD": ("avdd_brd", ("avdd_afei", "avss_afei")), "DVDD": ("dvdd_brd", ("dvddc", "dvssc"))}
NAMES = ["qo", "qip", "qin", "outp_adc", "outn_adc", "elp", "eln", "avdd_afei", "avss_afei", "dvddc", "dvssc",
         "avdd_brd", "dvdd_brd", "body", "vcm_p9", "opi", "oni", "inp", "inn"]
CIN_PF = 636.0                        # each side's input capacitor (the 11/17 split of the legs' 138.5 pF common mode)


def out_freq(f):
    """the tone's frequency after the chopper: next to harmonic k, f - k x 128 kHz"""
    k = int(round(f / FCH))
    return k, abs(f - k * FCH)


def fit_tones(t, y, freqs, poly=2, taus=(), t0=None):
    """least squares: a polynomial (order poly, on the window scaled to -1..1), for each time constant tau exp(-x)
    and x exp(-x) with x = (t - t0) / tau, and cos / sin of each frequency. Returns the complex amplitudes (a - j b
    for a cos + b sin, against the absolute time) and the residual rms."""
    u = (t - 0.5 * (t[0] + t[-1])) / (0.5 * (t[-1] - t[0]))
    cols = [u ** p for p in range(poly + 1)]
    for tau in taus:
        x = (t - (t[0] if t0 is None else t0)) / tau
        cols += [np.exp(-x), x * np.exp(-x)]
    nb = len(cols)
    for f in freqs:
        w = 2 * np.pi * f * t
        cols += [np.cos(w), np.sin(w)]
    A = np.column_stack(cols)
    c, *_ = np.linalg.lstsq(A, y, rcond=None)
    ph = np.array([c[nb + 2 * k] - 1j * c[nb + 2 * k + 1] for k in range(len(freqs))])
    return ph, float(np.std(y - A @ c))


def boxcar3(t, q):
    """three boxcars of LBOX on the uniform grid t, from the running integral q (exact differences for the first):
    the filtered signal and its times"""
    dt = (t[-1] - t[0]) / (len(t) - 1)
    n = int(round(LBOX / dt))
    assert abs(n * dt - LBOX) < 1e-12 and np.max(np.abs(np.diff(t) - dt)) < 1e-12, "the grid is not uniform"
    m = (q[n:] - q[:-n]) / LBOX
    tt = t[n:]
    for _ in range(2):
        Q = C.integral(tt, m)
        m = (Q[n:] - Q[:-n]) / LBOX
        tt = tt[n:]
    return tt, m


def hbox(f):
    """the three boxcars' response at f"""
    return np.sinc(f * LBOX) ** 3 * np.exp(-2j * np.pi * f * 1.5 * LBOX)


def inband(t, q, fo, taus, poly, t0=T0, t1=T1):
    """in-band amplitudes at the output frequencies fo from a running integral q, the boxcars taken out"""
    tt, m = boxcar3(t, q)
    a = (tt >= t0) & (tt < t1)
    tt, m = tt[a][::DEC], m[a][::DEC]
    ph, r = fit_tones(tt, m, fo, poly=poly, taus=taus, t0=t0)
    return ph / hbox(np.asarray(fo)), r


def window(v):
    a = (v["t"] >= T0) & (v["t"] < T1)
    return a


def baseline_of(m, runs):
    """the --cm 0 run without ripple on the same deck otherwise"""
    keys = [k for k in C.MATCH if k != "rip"]
    for d, mb in runs:
        if mb.get("cm") == 0 and not mb.get("rip") and all(mb.get(k) == m.get(k) for k in keys):
            return d, mb
    return None, None


def analyse(d, m, base, g):
    v, _ = C.load(d, NAMES)
    if v["t"][-1] < T1 - 1e-9:
        return None
    n = np.searchsorted(v["t"], T1 + 2 * LBOX)
    t = v["t"][:n]
    vb = None
    if base is not None:
        vb, _ = C.load(base, NAMES)
        if vb["t"][-1] >= t[-1] - 1e-12:
            assert np.allclose(vb["t"][:n], t, rtol=0, atol=1e-12)
        else:
            vb = None

    def diff(k):                                        # run - baseline (or the run alone)
        return v[k][:n] - (vb[k][:n] if vb is not None and k in vb else 0)

    freqs = list(m["rip_f"])
    ks, fo = zip(*(out_freq(f) for f in freqs))
    fo = list(fo)
    taus = C.taus_of(m)
    poly = 2 if vb is not None else 4
    sup = m["rip"]
    brd, (hi, lo) = SUPPLY[sup]
    w = (t >= T0) & (t < T1)
    tw = t[w]
    # the ripple: on the board (the run alone: the baseline has no board nodes) and on the chip (against the baseline)
    pb, rb = fit_tones(tw, v[brd][:n][w], freqs, poly=2)
    chip = diff(hi) - diff(lo)
    pc, rc = fit_tones(tw, chip[w], freqs, poly=2)
    # the output in band, at the electrodes
    po, ro = inband(t, diff("qo"), fo, taus, poly)
    vdm = po / g
    span = [np.abs(vdm)]
    for pv, tv in ((poly - 1, taus), (poly + 1, taus), (poly, tuple(x * 0.9 for x in taus)), (poly, tuple(x * 1.1 for x in taus))):
        span.append(np.abs(inband(t, diff("qo"), fo, tv, pv)[0] / g))
    span = np.array(span)
    # the baseline alone: the method's floor without ripple
    floor = None
    if vb is not None:
        pf, _ = inband(t, vb["qo"][:n], fo, taus, 4)
        floor = np.abs(pf / g)
    # the direct components at the output (raw grid, against the baseline), for the ADC's sampling
    pd_, _ = fit_tones(tw, (diff("outp_adc") - diff("outn_adc"))[w], freqs, poly=2)
    # between the choppers: the amplifier's differential output OPI - ONI at each tone's own frequency (the output
    # chopper's harmonic k, (4 / pi) / k for odd k, brings it to f_out: (2 / pi) / k of it in band)
    pa, _ = fit_tones(tw, (diff("opi") - diff("oni"))[w], freqs, poly=2)
    tones = []
    for i, f in enumerate(freqs):
        ripple_b, ripple_c = abs(pb[i]), abs(pc[i])
        x = abs(vdm[i])
        tones.append(dict(f=f, harmonic=ks[i], f_out=fo[i], board_mv=ripple_b * 1e3, chip_mv=ripple_c * 1e3,
                          chip_over_board=ripple_c / ripple_b, out_uv=abs(po[i]) * 1e6, vdm_uv=x * 1e6,
                          vdm_span_uv=[float(span[:, i].min() * 1e6), float(span[:, i].max() * 1e6)],
                          psrr_board_db=float(20 * np.log10(ripple_b / x)), psrr_chip_db=float(20 * np.log10(ripple_c / x)),
                          floor_uv=float(floor[i] * 1e6) if floor is not None else None,
                          direct_out_uv=float(abs(pd_[i]) * 1e6), between_vv=float(abs(pa[i]) / ripple_b),
                          fold_pred_uv=(float(2 / np.pi / ks[i] * abs(pa[i]) / abs(g) * 1e6) if ks[i] % 2 else None)))
    r = dict(run=os.path.basename(d), base=os.path.basename(base) if vb is not None else None, supply=sup, zp=m["zp"],
             zn=m["zn"], corner=m["corner"], seed=m["seed"], rip_mv=m["rip_mv"], window=[T0, T1], poly=poly, gain=g,
             taus_ms=[x * 1e3 for x in taus], board_resid_uv=rb * 1e6, chip_resid_uv=rc * 1e6, out_resid_uv=ro * 1e6,
             tones=tones, done=bool(v["done"]))
    # the 1 kHz tone (harmonic 0): the pins, the legs, the electrodes' share, the body and the board VCM
    i0 = next((i for i, k in enumerate(ks) if k == 0), None)
    if i0 is not None:
        f = freqs[i0]
        vr = pb[i0]                                         # the board's ripple, the reference
        pins, _ = inband(t, C.integral(t, diff("elp") - diff("eln")), [f], taus, poly)
        ip, _ = inband(t, diff("qip"), [f], (), poly)
        im, _ = inband(t, diff("qin"), [f], (), poly)
        yp, yn = ip[0] / vr, im[0] / vr
        wf = 2 * np.pi * f
        el = -(ip[0] * C.zleg(m["zp"], f) - im[0] * C.zleg(m["zn"], f))
        icm, _ = inband(t, C.integral(t, 0.5 * (diff("inp") + diff("inn"))), [f], (), poly)
        pcm, _ = inband(t, C.integral(t, 0.5 * (diff("elp") + diff("eln"))), [f], (), poly)
        body, _ = inband(t, C.integral(t, diff("body")), [f], (), poly)
        vcm, _ = inband(t, C.integral(t, diff("vcm_p9")), [f], (), poly)
        # its conversion between the choppers: the output chopper's square wave, at fc -+ f and 3 fc -+ f (out of band,
        # the CIC takes it out; it takes the ADC's range), its amplitude from the fundamental pair (pi / 2 x each)
        pq, _ = fit_tones(tw, (diff("outp_adc") - diff("outn_adc"))[w], [FCH - f, FCH + f, 3 * FCH - f, 3 * FCH + f], poly=2)
        sq = np.pi / 2 * 0.5 * (abs(pq[0]) + abs(pq[1]))
        r["direct"] = dict(f=f, out_phase=float(np.degrees(np.angle(vdm[i0] / vr))), pins_uv=float(abs(pins[0]) * 1e6),
                           chopped_mv=float(sq * 1e3), chopped_ratio=float(sq / abs(vr)),
                           chopped_sidebands_mv=[float(abs(x) * 1e3) for x in pq],
                           gain_f=float(abs(po[i0] / pins[0])) if abs(pins[0]) > 0 else None,
                           gp_ns=float(yp.real * 1e9), cp_pf=float(yp.imag / wf * 1e12),
                           gn_ns=float(yn.real * 1e9), cn_pf=float(yn.imag / wf * 1e12),
                           elec_uv=float(abs(el) * 1e6), own_uv=float(abs(vdm[i0] - el) * 1e6),
                           body_uv=float(abs(body[0]) * 1e6), vcm_uv=float(abs(vcm[0]) * 1e6),
                           icm_re=float((icm[0] / vr).real), icm_im=float((icm[0] / vr).imag),
                           pcm_re=float((pcm[0] / vr).real), pcm_im=float((pcm[0] / vr).imag))
    return r


def switches_supply(deck, vcm=1.648, f=1e3):
    """the input chopper's switches alone (cmrr.switches()' small AC deck, the run's extracted devices, every source and
    drain on one node at vcm, the gates as in one phase) with the AC source on AVDD (the PMOS wells) instead: each
    leg's admittance to AVDD through them, with ngspice's default gmin (1 pS x M across every junction, as in the start
    deck) and with 1e-15 (silicon). Returns C (F) and G (S) per leg for both."""
    txt = open(deck, encoding="utf-8").read()
    head = [ln for ln in txt.splitlines()[:12] if ln.startswith((".include", ".lib")) and ("design.ngspice" in ln or "typical" in ln)]
    sub = txt[txt.index(".subckt afe_top"):]
    sub = sub[:sub.index("\n.ends")]
    pins = {"ELP", "ELN", "WPT", "WNT"}
    dev = []
    for ln in sub.splitlines():
        t = ln.split()
        if len(t) > 5 and t[0].startswith("X") and t[5] in ("pfet_03v3", "nfet_03v3") and {t[1], t[3]} <= pins:
            dev.append(" ".join([t[0], "N", t[2], "N", "0" if t[4] == "AVSS" else t[4]] + t[5:]))
    assert len(dev) == 8, dev
    d = os.path.join(OUT, "switches")
    os.makedirs(d, exist_ok=True)
    out = {}
    for tag, opt in (("default", ""), ("gmin1e-15", ".options gmin=1e-15")):
        deckf = os.path.join(d, f"sw_avdd_{tag}.cir")
        open(deckf, "w").write("\n".join(
            ["* the input chopper's switches, AVDD moving (psrr.py switches_supply)"] + head
            + ["VAVDD AVDD 0 DC 3.3 AC 1", "VCIA CIA 0 3.3", "VNCIA NCIA 0 0", "VCIB CIB 0 0", "VNCIB NCIB 0 3.3",
               f"VCM N 0 DC {vcm}"] + dev + [opt, ".temp 27", ".control", f"ac lin 1 {f:g} {f:g}",
                                              "let y = i(vcm)", "print real(y) imag(y)", ".endc", ".end", ""]))
        # i(vcm): the current that AVDD drives into the node (it enters the source at its + end)
        log = subprocess.run(["ngspice", "-b", deckf], capture_output=True, text=True, cwd=d).stdout
        re_ = float(re.search(r"real\(y\)\s*=\s*(\S+)", log).group(1))
        im_ = float(re.search(r"imag\(y\)\s*=\s*(\S+)", log).group(1))
        out[tag] = (re_ / 2, im_ / (2 * np.pi * f) / 2)              # per leg
    return dict(f=f, vcm=vcm, c_pf_leg=out["gmin1e-15"][1] * 1e12, g_ns_leg=out["gmin1e-15"][0] * 1e9,
                g_gmin_ns_leg=(out["default"][0] - out["gmin1e-15"][0]) * 1e9)


BAND = (0.5, 100.0)                  # the EEG band, Hz
NOISE_NV = 5.341                     # the AFE's own noise at the electrodes in BAND, nVrms (chip wiring, AFE_IBIAS 3)


def band_transfer(r, sw):
    """the 1 kHz tone's transfer carried into BAND (V at the electrodes per V of the board's ripple), per Hz on a log
    grid: the legs' currents through their own impedances, from each leg's admittance to the supply at 1 kHz (G + j w
    C; for AVDD without the gmin that the switches' PMOS wells carry in the deck, switches_supply()), plus the chip's
    own conversion from the balanced run at 1 kHz, taken as flat and added in magnitude (no phase assumed)"""
    x = r["direct"]
    # the legs' currents count toward the chip, so the supply's passive paths come out negative (cp_pf < 0); the gmin
    # across the switches' junctions is one of them: -g_gmin per leg, taken out
    gfix = -sw["g_gmin_ns_leg"] if r["supply"] == "AVDD" else 0.0
    f = np.logspace(np.log10(BAND[0]), np.log10(BAND[1]), 400)
    w = 2 * np.pi * f
    yp = (x["gp_ns"] - gfix) * 1e-9 + 1j * w * x["cp_pf"] * 1e-12
    yn = (x["gn_ns"] - gfix) * 1e-9 + 1j * w * x["cn_pf"] * 1e-12
    el = np.abs(yp * np.array([C.zleg(r["zp"], v) for v in f]) - yn * np.array([C.zleg(r["zn"], v) for v in f]))
    return f, el


def main():
    runs = []
    for d in sorted(glob.glob(os.path.join(RUNS, f"start_*_cm0mV*Hz*_chip_{REV}"))):
        if os.path.exists(os.path.join(d, "tr.csv")):
            runs.append((d, json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))))
    g = C.gain()

    def typical(r):
        return r["corner"] == "typical" and r["seed"] is None

    # the switches' small deck takes its models from the typical deck (the Monte Carlo and corner decks load others)
    sw = switches_supply(os.path.join(next(d for d, m in runs if typical(m)), "tb.spice"))
    print(f"the input chopper's switches alone, AVDD moving (their PMOS wells): {sw['c_pf_leg']:.2f} pF and "
          f"{sw['g_ns_leg']:.4f} nS per leg; ngspice's default gmin adds {sw['g_gmin_ns_leg']:.3f} nS per leg")
    res = []
    for d, m in runs:
        if not m.get("rip"):
            continue
        b, _ = baseline_of(m, runs)
        r = analyse(d, m, b, g)
        if r is None:
            print(f"{os.path.basename(d)}: not yet at {T1 * 1e3:g} ms")
            continue
        res.append(r)
        print(f"{r['run']}\n  {r['supply']} ripple, legs {r['zp']} / {r['zn']}, "
              f"{'minus ' + r['base'] if r['base'] else 'fitted alone'} (polynomial {r['poly']}); residuals: board "
              f"{r['board_resid_uv']:.2f} uV, chip {r['chip_resid_uv']:.2f} uV, output {r['out_resid_uv']:.3f} uV")
        for x in r["tones"]:
            print(f"  {x['f'] / 1e3:8.2f} kHz (harmonic {x['harmonic']}, out at {x['f_out'] / 1e3:.2f} kHz): board "
                  f"{x['board_mv']:.3f} mV, chip {x['chip_mv']:.3f} mV; at the electrodes {x['vdm_uv']:.4f} uV pk "
                  f"({x['vdm_span_uv'][0]:.4f}-{x['vdm_span_uv'][1]:.4f}; floor "
                  + (f"{x['floor_uv']:.4f}" if x["floor_uv"] is not None else "-") +
                  f"); PSRR {x['psrr_board_db']:.1f} dB (board), {x['psrr_chip_db']:.1f} dB (chip); direct at the output "
                  f"{x['direct_out_uv']:.2f} uV; between the choppers OPI - ONI {x['between_vv']:.4g} V/V"
                  + (f" (folded by the chopper: {x['fold_pred_uv']:.4f} uV)" if x["fold_pred_uv"] is not None else ""))
        if "direct" in r:
            x = r["direct"]
            print(f"  1 kHz: output phase against the board's ripple {x['out_phase']:+.1f} deg; pins {x['pins_uv']:.4f} uV"
                  f" (output / pins {x['gain_f'] if x['gain_f'] is None else round(x['gain_f'], 2)}); legs to the supply: P "
                  f"{x['gp_ns']:.3f} nS + {x['cp_pf']:.3f} pF, N {x['gn_ns']:.3f} nS + {x['cn_pf']:.3f} pF; the legs' drops "
                  f"{x['elec_uv']:.4f} uV, the rest {x['own_uv']:.4f} uV; body {x['body_uv']:.3f} uV, board VCM "
                  f"{x['vcm_uv']:.3f} uV; between the choppers: a square wave of {x['chopped_mv']:.3f} mV pk at the "
                  f"ADC's input ({x['chopped_ratio']:.4f} x the board's ripple)")
    # in band (0.5-100 Hz): the legs' share from their 1 kHz admittances, plus the balanced run's own conversion
    def h0(r):                                          # the 1 kHz tone's transfer, V at the electrodes per V
        x = next(x for x in r["tones"] if x["harmonic"] == 0)
        return x["vdm_uv"] / x["board_mv"] * 1e-3

    for r in res:                                       # each leg's capacitance to AVDD at 1 kHz, split (typical:
        x = r.get("direct")                             # the switches' wells come from the typical deck)
        if x and r["supply"] == "AVDD" and typical(r):
            a, p = complex(x["icm_re"], x["icm_im"]), complex(x["pcm_re"], x["pcm_im"])
            c_sw = sw["c_pf_leg"] * (1 - p).real        # the switches' PMOS wells: AVDD against the pin
            c_cin = CIN_PF * (a - p).real               # Cin: the amplifier's input common mode against the pin
            x["split"] = dict(c_sw_pf=float(c_sw), c_cin_pf=float(c_cin),
                              c_rest_pf=float(-0.5 * (x["cp_pf"] + x["cn_pf"]) - c_sw - c_cin))
            print(f"  {r['run']}: legs to AVDD at 1 kHz {-0.5 * (x['cp_pf'] + x['cn_pf']):.2f} pF = the switches' wells "
                  f"{c_sw:.2f} + through Cin {c_cin:.2f} (the input common mode {abs(a):.4f} x the ripple, the pins "
                  f"{abs(p):.4f}) + the rest {x['split']['c_rest_pf']:.2f}")
    own = {r["supply"]: h0(r) for r in res if r["zp"] == r["zn"] and "direct" in r and typical(r)}
    for r in res:                                       # the folded tones: the flat noise next to k fc (both sides)
        for x in r["tones"]:                            # that adds 5 % to the AFE's own noise
            if x["harmonic"] > 0 and x["vdm_uv"] > 0:
                h = x["vdm_uv"] / x["board_mv"] * 1e-3
                x["allowed_nv_rthz"] = float(NOISE_NV * np.sqrt(1.05 ** 2 - 1) / (h * np.sqrt(2 * (BAND[1] - BAND[0]))))
    for r in res:
        if "direct" not in r or not typical(r):
            continue
        f, el = band_transfer(r, sw)
        tot = el + own.get(r["supply"], 0.0) if r["zp"] != r["zn"] else np.full_like(f, own.get(r["supply"], 0.0))
        rms = float(np.sqrt(np.trapz(tot ** 2, f) / (f[-1] - f[0])))
        # a flat regulator noise S (V / sqrt Hz) gives S x sqrt(int T^2 df) at the electrodes: the S that adds 5 %
        # to the AFE's own noise (sqrt(1.05^2 - 1) = 0.32 of it)
        allow = NOISE_NV * 1e-9 * np.sqrt(1.05 ** 2 - 1) / np.sqrt(np.trapz(tot ** 2, f)) if rms > 0 else None
        k50 = int(np.argmin(abs(f - 50)))
        sel = np.unique(np.r_[np.arange(0, len(f), 8), len(f) - 1])     # every 8th point and the band's top
        r["band"] = dict(f_hz=[float(v) for v in f[sel]], transfer=[float(v) for v in tot[sel]], legs_max=float(el.max()),
                         at50=float(tot[k50]), rms=rms, psrr50_db=float(-20 * np.log10(tot[k50])) if tot[k50] > 0 else None,
                         allowed_nv_rthz=float(allow * 1e9) if allow else None)
        print(f"{r['supply']}, legs {r['zp']}: in band (0.5-100 Hz) {tot[k50]:.3e} V/V at 50 Hz ("
              f"{r['band']['psrr50_db']:.1f} dB), rms over the band {rms:.3e}; a flat regulator noise of "
              f"{r['band']['allowed_nv_rthz']:.0f} nV/rtHz adds 5 % to the AFE's {NOISE_NV} nVrms")
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(gain=g, switches_avdd=sw, runs=res), open(os.path.join(OUT, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
