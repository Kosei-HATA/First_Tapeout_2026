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
    input (fc -+ 1 kHz, 3 fc -+ 1 kHz on the raw grid): out of band, but it takes the ADC's range.
Checked on cmrr.py's runs (11/18): the three boxcars give cmrr.py's numbers wherever the in-band part dominates (51 kohm
|| 47 nF: 286.20 against 285.84 uV at 1 kHz, 194.15 against 193.97 uV at 50 Hz, the harmonics 2f and 3f fitted too),
but the balanced 1 kHz run's 0.52 uV was the chopped conversion (fc -+ 1 kHz, 66.7 mV each at the output) that
chopper-period means alias onto 1 kHz (x 0.0078): in band it is 0.0038 uV.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr.py      (every ripple run of r12; runs/psrr_r12/results.json)
"""
import glob
import json
import os

import numpy as np

import cmrr as C

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs", "startup")
OUT = os.path.join(HERE, "runs", "psrr_r12")
REV = "r12"
T0, T1 = 6e-3, 10e-3
FCH = 1 / C.TCH                       # 128 kHz
LBOX = 8 * C.TCH                      # 62.5 us
DEC = 10                              # the filtered output is fitted every 1 us
SUPPLY = {"AVDD": ("avdd_brd", ("avdd_afei", "avss_afei")), "DVDD": ("dvdd_brd", ("dvddc", "dvssc"))}
NAMES = ["qo", "qip", "qin", "outp_adc", "outn_adc", "elp", "eln", "avdd_afei", "avss_afei", "dvddc", "dvssc",
         "avdd_brd", "dvdd_brd", "body", "vcm_p9"]


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
    tones = []
    for i, f in enumerate(freqs):
        ripple_b, ripple_c = abs(pb[i]), abs(pc[i])
        x = abs(vdm[i])
        tones.append(dict(f=f, harmonic=ks[i], f_out=fo[i], board_mv=ripple_b * 1e3, chip_mv=ripple_c * 1e3,
                          chip_over_board=ripple_c / ripple_b, out_uv=abs(po[i]) * 1e6, vdm_uv=x * 1e6,
                          vdm_span_uv=[float(span[:, i].min() * 1e6), float(span[:, i].max() * 1e6)],
                          psrr_board_db=float(20 * np.log10(ripple_b / x)), psrr_chip_db=float(20 * np.log10(ripple_c / x)),
                          floor_uv=float(floor[i] * 1e6) if floor is not None else None,
                          direct_out_uv=float(abs(pd_[i]) * 1e6)))
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
                           body_uv=float(abs(body[0]) * 1e6), vcm_uv=float(abs(vcm[0]) * 1e6))
    return r


def main():
    runs = []
    for d in sorted(glob.glob(os.path.join(RUNS, f"start_*_cm0mV*Hz*_chip_{REV}"))):
        if os.path.exists(os.path.join(d, "tr.csv")):
            runs.append((d, json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))))
    g = C.gain()
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
                  f"{x['direct_out_uv']:.2f} uV")
        if "direct" in r:
            x = r["direct"]
            print(f"  1 kHz: output phase against the board's ripple {x['out_phase']:+.1f} deg; pins {x['pins_uv']:.4f} uV"
                  f" (output / pins {x['gain_f'] if x['gain_f'] is None else round(x['gain_f'], 2)}); legs to the supply: P "
                  f"{x['gp_ns']:.3f} nS + {x['cp_pf']:.3f} pF, N {x['gn_ns']:.3f} nS + {x['cn_pf']:.3f} pF; the legs' drops "
                  f"{x['elec_uv']:.4f} uV, the rest {x['own_uv']:.4f} uV; body {x['body_uv']:.3f} uV, board VCM "
                  f"{x['vcm_uv']:.3f} uV; between the choppers: a square wave of {x['chopped_mv']:.3f} mV pk at the "
                  f"ADC's input ({x['chopped_ratio']:.4f} x the board's ripple)")
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(gain=g, runs=res), open(os.path.join(OUT, "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
