#!/usr/bin/env python3
"""The ADC's distortion from its OTAs at full scale (11/15): the static nonlinearity of the extracted OTA1 and OTA2
on their stage loads (ota_static.py) applied to the integrator outputs of the loop model at full scale, as an
error term on its own.

The loop model (adc_beh_mc.py) has the OTAs linear. A static nonlinearity f(vo) of an OTA's virtual-ground voltage
(beyond its offset and the finite gain the model has) is an error at its stage's input. OTA1's, times 1 + RIN / RD1
(the virtual ground drives RIN and the steered DAC1 resistors), is at the ADC input, and the loop passes it to DATA
as it passes the signal (STF 1 in the band). OTA2's is in series with the first integrator's output at R21; at the
ADC input it is RIN C1 times its derivative. Both are small against the signal, so the loop's response to them is
linear and they are computed from the integrator outputs of a run without them (feed-forward): per clock the mean
of f over the clock (trapezoids over the excess-delay segment and the rest of the clock), eeg_cic3's sinc^3 / 1024
in floating point, and the FFT of the 1 kS/s record, each bin divided by the sinc^3 droop. Out: the harmonics
against the tone and the rest of the band (the intermodulation with the quantization ripple), in nVrms at the
electrodes (/ 297.75). enob_sine.py --ota-nl puts the same nonlinearity into the loop with figure 35's noise.

Columns: typical, the block corners (ss, ff, fs, sf: their own benches), Monte Carlo dies 1-10 (their own benches);
noiseless, full scale at the electrodes through the AFE's static transfer (enob_sine.py), coherent record.

Check of the method: typical's OTA1 curve scaled up to -100 dBc of HD3 in the loop (noiseless, the AFE linear)
against the feed-forward value scaled the same.

Also from the same run, DAC1's sensitivity to the jitter of its update edge (NRZ: per clock an error
vfs (y1[n] - y1[n-1]) dt / T at the input, white for white jitter; DAC2's is shaped by the first integrator): the
in-band noise at the electrodes per 10 ps rms and the jitter that gives 0.5 nVrms.

usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/ota_distortion.py [--nrec 2048 --cycles 23]
writes runs/ota_static_r12/ota_distortion.json and ota_distortion_typical.npz (typical's error spectra)
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import enob_sine as E  # noqa: E402  (sets EEG_PEX_REV r12; the stimulus, the AFE transfer, eeg_cic3's constants)

B, G, O, m = E.B, E.G, E.O, E.m
P = np.polynomial.polynomial


def cic3f(x, r):
    """sinc^3 / r in floating point: three causal moving averages of r from a zero state, the output at the end
    of every block of r (n // r samples, as eeg_cic3 gives them)"""
    y = x
    for _ in range(3):
        c = np.cumsum(y)
        y = (c - np.concatenate([np.zeros(r), c[:-r]])) / r
    return y[r - 1::r]


def per_clock(f, prev, mid, end, eld):
    """the mean of f over the clock: trapezoids from the clock's start to the DAC update and from there to its end"""
    fm = f(mid)
    return eld * 0.5 * (f(prev) + fm) + (1.0 - eld) * 0.5 * (fm + f(end))


def bins(err, nrec, k0, u_amp, skip):
    """the error's 1 kS/s record -> per band bin its amplitude at the ADC input (droop divided out), the harmonics
    2..9 in dBc against u_amp, the rest of the band (no DC, tone, harmonics) and all of it except the tone (V rms)"""
    x = err[skip:skip + nrec]
    a = 2 * np.abs(np.fft.rfft(x)) / nrec
    f = np.arange(a.size) * E.FS_DATA / nrec
    band = (f >= E.BAND[0]) & (f <= E.BAND[1])
    a = np.where(band, a / np.maximum(E.sinc3(f), 1e-12), 0.0)
    harm = [h * k0 for h in range(2, 10) if h * k0 < a.size and band[h * k0]]
    rest = band.copy()
    rest[[k0] + harm] = False
    allb = band.copy()
    allb[k0] = False
    rms = lambda s: float(math.sqrt(np.sum(a[s] ** 2) / 2))  # noqa: E731
    hd = [20 * math.log10(max(a[h], 1e-30) / u_amp) for h in harm]
    return dict(hd_dbc=hd, rest_v=rms(rest), total_v=rms(allb)), f, a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nrec", type=int, default=2048)
    ap.add_argument("--cycles", type=int, default=23)
    a = ap.parse_args()
    f0 = a.cycles * E.FS_DATA / a.nrec
    apoly, _, _ = E.afe_transfer()
    j = B.load_block()
    corners = B.corner_dies(j)
    mcd, _, _ = B.mc_dies(j)
    dies = corners[:5] + [d for d in mcd if int(d.label[2:]) <= 10]
    S = len(dies)
    nl1, _, used = O.loop_nl(dies, m)              # nl1 at the ADC input (x k1); the benches 'ota1 / ota2'
    vx2 = [O.die_nl("ota2", d.label)[0] for d in dies]   # OTA2's nonlinear part in volts (series with x1 at R21)
    n = (G.NSKIP + E.SETTLE + a.nrec + 1) * G.R
    co = [d.coeffs(E.ELD) for d in dies]
    ad, b, ad0, b0 = (np.array([cc[i] for cc in co]) for i in range(4))
    st = lambda at: np.array([getattr(d, at) for d in dies])  # noqa: E731
    u_amp = E.G_AFE * E.FS_PK
    u = E.Stim(n, f0, np.full(S, E.FS_PK), np.full(S, E.G_AFE), np.array([apoly] * S), np.zeros(S),
               np.zeros((n // E.DEC_G + 2, S)), seed=11)
    rec = {k: np.zeros((n, S), np.float32) for k in ("x1", "mx1", "x2")}
    print(f"{S} dies, {n} clocks ({n / m.FS:.2f} s), f0 {f0:.4f} Hz, full scale {u_amp * 1e3:.1f} mV pk at the ADC "
          f"input; benches {', '.join(sorted(set(used)))}", flush=True)
    t = time.time()
    codes, x1m, x2m = B.simulate(ad, b, ad0, b0, u, st("thr"), st("w1"), st("w2"), st("e1"), st("o1"),
                                 np.zeros(S), np.zeros((S, 31)), rec=rec)
    print(f"loop: {time.time() - t:.0f} s", flush=True)
    skip = G.NSKIP + E.SETTLE
    rows, keep = [], {}
    for s, d in enumerate(dies):
        x1 = rec["x1"][:, s].astype(float)
        mx1 = rec["mx1"][:, s].astype(float)
        x2 = rec["x2"][:, s].astype(float)
        x1p, x2p = np.concatenate([[0.0], x1[:-1]]), np.concatenate([[0.0], x2[:-1]])
        e1 = per_clock(lambda v: P.polyval(v, nl1[s]), x1p, mx1, x1, E.ELD)
        d2 = 0.5 * (P.polyval(x2p, vx2[s]) + P.polyval(x2, vx2[s]))
        r1, f, a1 = bins(cic3f(e1, G.R), a.nrec, a.cycles, u_amp, skip)
        rc = m.RIN * d.k_rin * m.C1 * d.k_c * d.k_c1
        dd = cic3f(d2, G.R)[skip:skip + a.nrec]
        dd = np.fft.irfft(np.fft.rfft(dd) * 2j * np.pi * np.arange(a.nrec // 2 + 1) * E.FS_DATA / a.nrec * rc, a.nrec)
        r2, _, a2 = bins(dd, a.nrec, a.cycles, u_amp, 0)
        sel = slice(int(0.05 * n), n)
        # DAC1's update edge with white timing jitter sigma_t: per clock an error vfs (y1[n] - y1[n-1]) sigma_t / T at
        # the input (NRZ), white; y1 = (2c - 31) / 31; in the band BW / (FS / 2) of it
        dy = np.diff(2.0 * codes[sel, s].astype(float) / 31.0)
        jit = d.vfs * dy.std() * math.sqrt((E.BAND[1] - E.BAND[0]) / (m.FS / 2)) / m.T / E.G_AFE   # V per s of jitter
        row = dict(die=d.label, bench=used[s], a1=float(d.a1), k1=float(1 + d.vfs / m.VREF),
                   dac1_step_rms_codes=float(dy.std() * 31 / 2), jitter_nv_per_10ps=jit * 10e-12 * 1e9,
                   jitter_ps_for_0p5nv=0.5e-9 / jit * 1e12,
                   x1_range_mv=[float(x1[sel].min() * 1e3), float(x1[sel].max() * 1e3)],
                   x2_range_mv=[float(x2[sel].min() * 1e3), float(x2[sel].max() * 1e3)],
                   ota1_hd_dbc=r1["hd_dbc"], ota1_rest_nv=r1["rest_v"] / E.G_AFE * 1e9,
                   ota1_total_nv=r1["total_v"] / E.G_AFE * 1e9,
                   ota1_total_dbc=20 * math.log10(r1["total_v"] * math.sqrt(2) / u_amp),
                   ota2_hd_dbc=r2["hd_dbc"], ota2_total_nv=r2["total_v"] / E.G_AFE * 1e9,
                   ota2_total_dbc=20 * math.log10(max(r2["total_v"], 1e-30) * math.sqrt(2) / u_amp))
        rows.append(row)
        if s == 0:
            keep = dict(f=f, ota1=a1, ota2=a2, k0=a.cycles)
        print(f"{d.label[:28]:28s} bench {used[s]:16s} x1 {row['x1_range_mv'][0]:+6.1f}..{row['x1_range_mv'][1]:+6.1f} mV  "
              f"x2 {row['x2_range_mv'][0]:+5.1f}..{row['x2_range_mv'][1]:+5.1f} mV  OTA1: HD2 {r1['hd_dbc'][0]:6.1f} "
              f"HD3 {r1['hd_dbc'][1]:6.1f} dBc, all {row['ota1_total_dbc']:6.1f} dBc ({row['ota1_total_nv'] * 1e3:.3f} pVrms "
              f"at the electrodes)  OTA2: all {row['ota2_total_dbc']:6.1f} dBc  DAC1 step {row['dac1_step_rms_codes']:.2f} "
              f"codes rms: jitter {row['jitter_nv_per_10ps']:.4f} nVrms per 10 ps", flush=True)
    # check of the method: typical's OTA1 curve scaled up to an HD3 of -100 dBc goes into the loop (noiseless, the AFE
    # linear, so that nothing else is near that level); its HD3 in DATA against the feed-forward value times the scale
    scale = 10 ** ((-100.0 - rows[0]["ota1_hd_dbc"][1]) / 20)
    u2 = E.Stim(n, f0, np.full(2, E.FS_PK), np.full(2, E.G_AFE), np.zeros((2, 4)), np.zeros(2),
                np.zeros((n // E.DEC_G + 2, 2)), seed=11)
    pick = lambda v: np.array([v[0], v[0]])  # noqa: E731
    c2, _, _ = B.simulate(pick(ad), pick(b), pick(ad0), pick(b0), u2, pick(st("thr")), pick(st("w1")),
                          pick(st("w2")), pick(st("e1")), pick(st("o1")), np.zeros(2), np.zeros((2, 31)),
                          nl1=np.array([np.zeros_like(nl1[0]), scale * nl1[0]]))
    chk = [E.spectrum(E.cic_data(c2[:, s]), a.nrec, a.cycles)[0]["hd"] for s in range(2)]
    check = dict(scale=scale, predicted_hd3_dbc=rows[0]["ota1_hd_dbc"][1] + 20 * math.log10(scale),
                 in_loop_hd3_dbc=chk[1][1], in_loop_hd3_without_dbc=chk[0][1],
                 predicted_hd2_dbc=rows[0]["ota1_hd_dbc"][0] + 20 * math.log10(scale), in_loop_hd2_dbc=chk[1][0])
    print(f"check: OTA1 x {scale:.3g} in the loop: HD3 {check['in_loop_hd3_dbc']:.2f} dBc (without it "
          f"{check['in_loop_hd3_without_dbc']:.1f}), feed-forward {check['predicted_hd3_dbc']:.2f} dBc", flush=True)
    meta = dict(f0_hz=f0, nrec=a.nrec, cycles=a.cycles, u_amp_v=u_amp, eld=E.ELD, g_afe=E.G_AFE,
                fit=dict(span_v=O.SPAN, deg=O.DEG), benches=O.OUT, check=check)
    json.dump(dict(meta=meta, rows=rows), open(os.path.join(O.OUT, "ota_distortion.json"), "w"), indent=1)
    np.savez_compressed(os.path.join(O.OUT, "ota_distortion_typical.npz"), **keep)
    w1 = max(rows, key=lambda r: r["ota1_total_dbc"])
    w2 = max(rows, key=lambda r: r["ota2_total_dbc"])
    wj = max(rows, key=lambda r: r["jitter_nv_per_10ps"])
    print(f"\nworst OTA1 term: {w1['die']} {w1['ota1_total_dbc']:.1f} dBc; worst OTA2 term: {w2['die']} "
          f"{w2['ota2_total_dbc']:.1f} dBc (ENOB margin of figure 35's worst die: -113.7 dBc); DAC1 edge jitter: "
          f"{wj['jitter_nv_per_10ps']:.4f} nVrms per 10 ps at the electrodes ({wj['die']}), 0.5 nVrms at "
          f"{wj['jitter_ps_for_0p5nv']:.0f} ps rms")


if __name__ == "__main__":
    main()
