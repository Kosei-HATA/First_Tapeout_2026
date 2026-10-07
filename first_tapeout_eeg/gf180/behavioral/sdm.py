#!/usr/bin/env python3
"""Discrete-time behavioral model of the sdm3-family SC Sigma-Delta modulator
(GF180 port study), including the analog state-dependent mechanisms that
produce the measured deterministic limit-cycle comb:

  - exact loop timing of the alternating-phase (Boser-Wooley) chain:
        x1[n] = x1[n-1] + a1*u[n]   + d1*y[n-1]
        x2[n] = x2[n-1] + a2*x1[n]  + d2*y[n-1]      (non-delaying cascade)
        x3[n] = x3[n-1] + a3*x2[n]  + d3*y[n-1]      (order-3 option)
        y[n]  = Q(x_L[n])           (same-cycle decision, sdm3 direct DAC)
    General CIFB chain of order L with per-integrator (a_i, d_i).
    For L=2, (2,2,0.5,1): NTF=(1-z^-1)^2 exactly, STF(DC)=-1.
    For L=3, (2,2,0.5,1,1,1): NTF=(1-z^-1)^3 exactly, STF(DC)=-1.

  - integrator incomplete-settling nonlinearity (per integrator):
        dx_actual = dx_ideal * (1 + gamma_i + kappa_i * x_i[n-1])
                                     + eta_i * dx_ideal^2
    gamma_i : state-independent settling/creep fraction (plateau creep;
              a pure coefficient error -- benign by itself, kept for
              completeness). GF180 measured: creep/step = 0.086 (CMFB-fixed
              RSET=40k), 0.066 (RSET=25k); sky130: 0.0066.
    kappa_i : state-dependent gain (per unit integrator state; slewing /
              GM compression). Measured increment amplitude dependence
              -79.45..-79.52 mV over the +/-0.6 V swing -> ~1e-3 /V state.
    eta_i   : quadratic-in-step term (slew asymmetry; even-order nonlinearity).

  - quantizer: 1/2/4 bit mid-tread, y = -Q(x_L) (sdm3 sign convention),
    optional quantizer dither (subtractive: added before Q, subtracted from
    the output bitstream digitally) or non-subtractive.
  - optional input dither: out-of-band sine or PN sequence.
  - optional deterministic comparator threshold hysteresis (decision depends
    on previous decision), for A/B against the measured exoneration of the
    strong-arm port.

Normalization: input u=1.0 corresponds to full-scale amplitude
(duty = 0.5 - u/2, y in {-1,+1} for 1-bit), i.e. 1.0 = 50 mV diff at the
modulator input. Integrator states carry the same normalized charge units;
kappa is per unit state, eta per unit step.
"""

import numpy as np


def quantize(v, bits, rng=None, dither=0.0):
    """Mid-tread quantizer, y = -Q(v + dither), levels in [-1, 1)."""
    vd = v + dither
    if bits == 1:
        return -1.0 if vd >= 0 else 1.0
    # B-bit mid-tread: step = 2/2^B, symmetric clipping
    nlev = 1 << bits
    step = 2.0 / nlev
    q = np.clip(np.round(vd / step - 0.5) + 0.5, -(nlev // 2 - 0.5),
                nlev / 2 - 0.5) * step
    return -q


class SettleProfile:
    """Per-integrator settling parameters (gamma, kappa, eta)."""
    def __init__(self, gamma=0.0, kappa=0.0, eta=0.0):
        self.gamma = gamma
        self.kappa = kappa
        self.eta = eta


# Measured profiles (documentation/gf180_feasibility.md §6, enob18_study.md §4)
IDEAL = SettleProfile(0.0, 0.0, 0.0)
SKY130 = SettleProfile(gamma=0.0066, kappa=2e-4, eta=2e-4)   # 0.53 mV / 80 mV step
GF180 = SettleProfile(gamma=0.086, kappa=1e-3, eta=1e-3)     # -6.9 mV / 80 mV step
GF180_R25K = SettleProfile(gamma=0.066, kappa=8e-4, eta=8e-4)


def simulate(fs=256e3, fsig=32.0, amp=0.6, ncyc=10, skip_ms=10.0,
             order=2, coeffs=None, bits=1,
             settle=(IDEAL, IDEAL, IDEAL),
             dither_mode='none', dither_amp=0.0, dither_freq=2400.0,
             cmp_hyst=0.0, dac_mismatch=0.0, dwa=False, seed=1, u_override=None):
    """Run the modulator. Returns (y, d_sub, t_axis_info):
    y       : bitstream (normalized, mean tracks -u), length ncyc*spc after skip
    d_sub   : subtractive dither sequence (zeros unless quantizer-sub)
    dac_mismatch: std of per-level feedback DAC error, as a fraction of one
    quantizer step (multibit element mismatch; 0 for ideal DAC).
    """
    if coeffs is None:
        coeffs = {2: (2.0, 2.0, 0.5, 1.0),
                  3: (2.0, 2.0, 0.5, 1.0, 1.0, 1.0)}[order]
    a = coeffs[0::2][:order]
    d = coeffs[1::2][:order]
    rng = np.random.default_rng(seed)
    spc = int(round(fs / fsig))
    nskip = int(round(skip_ms * 1e-3 * fs))
    n = nskip + ncyc * spc
    if u_override is not None:
        u = u_override
    else:
        u = amp * np.sin(2 * np.pi * fsig * np.arange(n) / fs)
    if dither_mode == 'input_sine':
        u = u + dither_amp * np.sin(2 * np.pi * dither_freq * np.arange(n) / fs)
    elif dither_mode == 'input_pn':
        u = u + dither_amp * (2.0 * rng.integers(0, 2, n) - 1.0)
    x = np.zeros(order)
    y = np.zeros(n)
    dsub = np.zeros(n)
    yprev = 1.0  # BIT starts high (nodeset v(BIT)=VDD)
    prev_dec = 1.0
    step = 2.0 / (1 << bits)
    dac_err = {}
    # DWA: thermometer unit elements (2^B - 1 units) with static errors,
    # selected by a rotating pointer (data-weighted averaging, 1st-order
    # mismatch shaping)
    n_unit = (1 << bits) - 1
    unit_err = rng.standard_normal(n_unit) * dac_mismatch * step if dwa else None
    dwa_ptr = 0
    for k in range(n):
        # non-delaying cascade: integrator i integrates the FRESH x[i-1]
        # (int2 samples int1's settled output within the same cycle), and
        # every DAC applies y from the previous cycle's latched decision.
        for i in range(order):
            uprev = x[i - 1] if i > 0 else u[k]
            if dwa and bits > 1:
                c = int(round(yprev / step + (n_unit - 1) / 2))
                c = max(0, min(n_unit, c))
                err = 0.0
                for j in range(c):
                    err += unit_err[(dwa_ptr + j) % n_unit]
                dwa_ptr = (dwa_ptr + c) % n_unit
                yfb = yprev + err
            elif dac_mismatch > 0.0 and bits > 1:
                yv = dac_err.get(yprev)
                if yv is None:
                    yv = yprev + dac_mismatch * step * rng.standard_normal()
                    dac_err[yprev] = yv
                yfb = yv
            else:
                yfb = yprev
            dx = a[i] * uprev + d[i] * yfb
            s = settle[i] if i < len(settle) else IDEAL
            x[i] += dx * (1.0 + s.gamma + s.kappa * x[i]) \
                + s.eta * dx * abs(dx)
        vin = x[order - 1]
        if cmp_hyst != 0.0:
            vin = vin + cmp_hyst * prev_dec
        if dither_mode == 'quantizer_sub':
            dv = dither_amp * (2.0 * rng.integers(0, 2, size=1)[0] - 1.0)
        elif dither_mode == 'quantizer_nonsub':
            dv = dither_amp * (2.0 * rng.integers(0, 2, size=1)[0] - 1.0)
        else:
            dv = 0.0
        yk = quantize(vin, bits, dither=dv)
        prev_dec = -yk
        y[k] = yk
        if dither_mode == 'quantizer_sub':
            dsub[k] = dv  # subtract digitally (same sign as added to input)
        yprev = yk
    sl = slice(nskip, n)
    out = y[sl] + (dsub[sl] if dither_mode == 'quantizer_sub' else 0.0)
    return out, x.copy()


def analyze(y, fs=256e3, fsig=32.0, blo=0.5, bhi=100.0):
    """Same math as gf180/results/analyze_sndr_fast.py: coherent FFT,
    SNDR over [blo, bhi], top in-band lines, k*3.2 Hz skirt fraction,
    floor-only SNDR. Returns dict."""
    n = len(y)
    Ts = 1.0 / fs
    B = np.fft.rfft(y)
    f = np.fft.rfftfreq(n, Ts)
    mag = np.abs(B) / (n / 2)
    isig = int(round(fsig * n * Ts))
    band = (f >= blo) & (f <= bhi)
    sig = mag[isig]
    noise_bins = band.copy()
    noise_bins[isig] = False
    pnoise = np.sum((mag[noise_bins] / np.sqrt(2)) ** 2)
    sndr = 20 * np.log10((sig / np.sqrt(2)) / np.sqrt(pnoise))
    fb, mb = f[noise_bins], mag[noise_bins]
    order_ = np.argsort(mb)[::-1]
    top = [(fb[j], 20 * np.log10(mb[j] / sig)) for j in order_[:10]]
    excl = mb.copy()
    excl[order_[:40]] = 0
    pw = np.sum((excl / np.sqrt(2)) ** 2)
    floor_sndr = 20 * np.log10((sig / np.sqrt(2)) / np.sqrt(pw)) if pw > 0 else np.inf
    skirt = np.zeros_like(band)
    df = 1.0 / (n * Ts)
    # skirt at k * (1/T_record) offsets from carrier (comb spacing = 1/Trec)
    comb = np.zeros_like(band)
    for kk in range(1, 32):
        for s in (+1, -1):
            idx = int(round((fsig + s * kk * df) * n * Ts))
            if 0 <= idx < len(mag) and band[idx]:
                comb[idx] = True
    pcomb = np.sum((mag[comb & noise_bins] / np.sqrt(2)) ** 2)
    return dict(sndr=sndr, sig=sig, floor_sndr=floor_sndr,
                comb_frac=pcomb / pnoise if pnoise > 0 else 0.0,
                top=top, ncyc=int(n * Ts * fsig))


def sqnr_ideal_1bit(L, OSR):
    """Ideal 1-bit peak SQNR formula from enob18_study.md §1."""
    return 6.02 + 1.76 - 10 * np.log10(np.pi ** (2 * L) / (2 * L + 1)) \
        + (20 * L + 10) * np.log10(OSR)
