#!/usr/bin/env python3
"""The ADC's in-band SNDR with manufacturing variation (tracker D3 / D7): the exact per-clock loop
model of gf180/behavioral/ct2_dac2_options.py (5 bits, DWA on both DACs, stage 2 scaled x10, NRZ
DACs, the excess loop delay of the RTL, 3 of 32 MCLK) run for all dies at once (numpy over the dies;
numba is not needed). Each Monte Carlo die takes, from the block Monte Carlo of the extracted ADC
(adc_block_mc.py, runs/adc_mc/adc_block_mc.json, the same seed):

  - the 31 quantizer thresholds (eeg_quantizer);
  - DAC1 (adc_rdac): the 31 element charges (the DWA mismatch), the full scale against RIN
    (31 i_e RIN), RIN itself, the even-order charge per toggled element (the all-31 measurement, the
    mean over the elements that DWA does not shape, on every element, plus a random part per element
    with zero mean over the 31, its sigma the spread of one cell about the all-31 value over the
    seeds) and the odd-order charge per toggle (+ on, - off);
  - the OTA1 / OTA2 DC gains with the integrator loads (OTA1: the mean of its two chopper phases);
  - the loop's time constants: RIN as measured, R21 and the DAC2 current (from eeg_bias, set by a
    ppolyf_u_1k resistor) with the PDK's global sheet-resistance draw of the seed
    (1 + 3 mc_rsh_ppolyf_u_1k / 1000, res_mc_skew 3), C1 and C2 with its global MIM draw
    (1 + mc_c_cox_2p0ff).

What the block Monte Carlo does not cover keeps the model's assumptions: DAC2 element mismatch
2 % (sigma, DWA), no DAC2 even / odd charge, no OTA offsets (OTA1 is chopped; OTA2's offset, sigma
0.33 mV at the second integrator, is shaped by the first), no noise, OTAs linear. The input is a
0.3 V pk differential 32 Hz sine at the ADC input (4 s coherent record, CIC4 / 256 and FIR / 10 as
the RTL, SNDR over 0.5-100 Hz, ct2_dac2_options.sndr).

Cases:
  --mc                the Monte Carlo dies (seeds with a quantizer result; DAC1 from typical where a
                      seed has none yet, reported);
  --corners           the blocks' corners (typical, ss, ff, fs, sf; ss / ff with res_ss / res_ff and
                      mimcap_ss / mimcap_ff as the block benches take them, fs / sf with typical R
                      and MIM) and the resistor / MIM corners with typical blocks (the four combinations,
                      and res_ff or mimcap_ff alone)
                      (ppolyf_u_1k x 1.2 / 0.8, MIM 2 fF x 1.1 / 0.9);
  --base              the model as the D3 tables used it (ideal blocks, A1 2710, A2 3000, DAC1 0.5 %,
                      DAC2 2 %, DAC1 even -1.67e-6) for reference;
  --sweep-even        typical blocks with DAC1's even charge per toggle swept, the same on every
                      element (-0.016 .. +0.016 fC; the requirement is 0.008 fC per cell);
  --check N          the vectorized loop against ct2_dac2_options.simulate (pure Python) over N
                      clocks for a few random dies: the codes must agree exactly.

Usage: python3 adc_beh_mc.py [--mc] [--corners] [--base] [--sweep-even] [--check 20000] [--ain 0.3] [--eld 0.09375]
"""
import argparse
import json
import os
import sys
import time
import types

import numpy as np
from scipy.linalg import expm
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
try:
    import numba  # noqa: F401
except ImportError:                                  # ct2_dac2_options only needs njit to import
    stub = types.ModuleType("numba")
    stub.njit = lambda *a, **k: a[0] if len(a) == 1 and callable(a[0]) and not k else (lambda f: f)
    sys.modules["numba"] = stub
sys.path.insert(0, os.path.join(REPO, "gf180", "behavioral"))
import ct2_dac2_options as m  # noqa: E402

BLOCK = os.path.join(HERE, "runs", "adc_mc", "adc_block_mc.json")
_REV = os.environ.get("EEG_PEX_REV", "")              # pex.py: the runs of a changed layout (r7: runs/adc_beh_mc_r7)
OUT = os.path.join(HERE, "runs", "adc_beh_mc" + (f"_{_REV}" if _REV else ""))
# C1 and C2 as drawn against the model's (ct2_dac2_options: C1 halved with RIN doubled, stage 2 x10):
# x1.25 since 10/29 (r7; the r6 results in runs/adc_beh_mc/ are with 1)
DRAWN_C12 = 1.25
S2 = 10.0                                            # stage 2 scaled x10 (R21 100k, C2 19.5 pF)
ELD = 3 / 32                                         # CMP_STROBE -> new DAC levels (RTL DAC_LOAD_CYCLE)
SIGMA2 = 0.02                                        # DAC2 element mismatch (assumed, as D3)
RSH_1K = 1000.0                                      # ppolyf_u_1k sheet (typical), res_mc_skew 3
CORNER_R = {"res_ss": 1.2, "res_ff": 0.8}            # ppolyf_u_1k 1000 +- 200
CORNER_C = {"mimcap_ss": 1.1, "mimcap_ff": 0.9}      # mim_corner_2p0ff


def discretize(rin, c1, vfs, r21, rd2, c2, a1, a2, tseg):
    """ct2_dac2_options.discretize with every element given: x(t + tseg) = Ad x + b [u, y1, y2].
    vfs is DAC1's full scale at the input (VREF RIN / RD1)."""
    rd1 = m.VREF * rin / vfs
    g1 = (1 / rin + 1 / rd1) / (a1 * c1)
    g2 = (1 / r21 + 1 / rd2) / (a2 * c2)
    mm = np.zeros((5, 5))
    mm[:2, :2] = [[-g1, 0.0], [1 / (r21 * c2), -g2]]
    mm[:2, 2:] = [[1 / (rin * c1), -m.VREF / (rd1 * c1), 0.0], [0.0, 0.0, -m.VREF / (rd2 * c2)]]
    e = expm(mm * tseg)
    return e[:2, :2].copy(), e[:2, 2:].copy()


def prefix(w):
    """cs[s, p, k]: the sum of w[s] over the k elements from p on (mod 31), added in that order as the
    model's DWA loop adds them."""
    S = w.shape[0]
    idx = (np.arange(31)[:, None] + np.arange(31)[None, :]) % 31          # [p, j] -> element
    cs = np.zeros((S, 31, 32))
    cs[:, :, 1:] = np.cumsum(w[:, idx], axis=2)
    return cs


def simulate(ad, b, ad0, b0, u, thr, w1, w2, e1, o1, eps2, o2):
    """ct2_dac2_options.simulate for S dies at once. Per die (first axis): ad, b over the clock after
    the DAC update and ad0, b0 before it (the excess loop delay), the 31 thresholds thr, the DAC
    element weights w1 / w2 (sum 31), DAC1's even charge per toggled element e1 and odd charge o1
    (+ when it turns on, - off), DAC2's even charge per toggle eps2 (one value) and odd charge o2,
    all in units of one element's charge per clock. Returns the codes (n, S) int8 (-1 from a loop
    runaway on) and the peak |x1|, |x2| after the first 5 %."""
    S, n = thr.shape[0], u.shape[0]
    a00, a01, a10, a11 = ad[:, 0, 0], ad[:, 0, 1], ad[:, 1, 0], ad[:, 1, 1]
    b00, b01, b02, b10, b11, b12 = b[:, 0, 0], b[:, 0, 1], b[:, 0, 2], b[:, 1, 0], b[:, 1, 1], b[:, 1, 2]
    z00, z01, z10, z11 = ad0[:, 0, 0], ad0[:, 0, 1], ad0[:, 1, 0], ad0[:, 1, 1]
    c00, c01, c02, c10, c11, c12 = b0[:, 0, 0], b0[:, 0, 1], b0[:, 0, 2], b0[:, 1, 0], b0[:, 1, 1], b0[:, 1, 2]
    cs1, cs2 = prefix(w1), prefix(w2)
    die = np.arange(S)
    J = np.arange(31)
    odd1, odd2 = bool(np.any(o1)), bool(np.any(o2))
    x1, x2, y1p, y2p = np.zeros(S), np.zeros(S), np.zeros(S), np.zeros(S)
    p = np.zeros(S, np.int64)
    prev = np.zeros((S, 31), bool)
    out = np.empty((n, S), np.int8)
    x1max, x2max = np.zeros(S), np.zeros(S)
    dead = np.full(S, n)
    i5 = n // 20
    for i in range(n):
        ui = u[i]
        mx1 = z00 * x1 + z01 * x2 + c00 * ui + c01 * y1p + c02 * y2p
        mx2 = z10 * x1 + z11 * x2 + c10 * ui + c11 * y1p + c12 * y2p
        c = (x2[:, None] > thr).sum(1)
        out[i] = c
        k = 31 - c
        sel = (J - p[:, None]) % 31 < k[:, None]
        tog = sel != prev
        s1 = cs1[die, p, k]
        s2 = cs2[die, p, k]
        t1 = np.cumsum(e1 * tog, axis=1)[:, -1]
        nt = tog.sum(1)
        t2 = eps2 * nt
        if odd1:
            t1 = np.cumsum(np.where(tog, np.where(sel, o1, -o1), 0.0) + e1 * tog, axis=1)[:, -1]
        if odd2:
            t2 = t2 + np.cumsum(np.where(tog, np.where(sel, o2, -o2), 0.0), axis=1)[:, -1]
        prev = sel
        p = (p + k) % 31
        y1 = 1.0 - 2.0 * s1 / 31.0 + t1 / 31.0
        y2 = 1.0 - 2.0 * s2 / 31.0 + t2 / 31.0
        x1 = a00 * mx1 + a01 * mx2 + b00 * ui + b01 * y1 + b02 * y2
        x2 = a10 * mx1 + a11 * mx2 + b10 * ui + b11 * y1 + b12 * y2
        y1p, y2p = y1, y2
        if i > i5:
            np.maximum(x1max, np.abs(x1), out=x1max)
            np.maximum(x2max, np.abs(x2), out=x2max)
        bad = np.abs(x2) > 10.0
        if bad.any():
            dead[bad & (dead == n)] = i
            x1[bad], x2[bad], y1p[bad], y2p[bad] = 0.0, 0.0, 0.0, 0.0
    for s in range(S):
        out[dead[s]:, s] = -1
    return out, x1max, x2max


class Die:
    """One die: its label and physical loop parameters (relative to the model's typical values where
    noted)."""

    def __init__(self, label, thr_err=None, w1=None, e1=None, o1=None, vfs=None, k_rin=1.0, k_r=1.0, k_c=1.0,
                 a1=2710.0, a2=3000.0, sigma1=0.0, seed=1, note="", k_c1=DRAWN_C12, k_c2=DRAWN_C12):
        self.label, self.note = label, note
        self.thr = m.THR + (np.zeros(31) if thr_err is None else np.asarray(thr_err))
        rng = np.random.RandomState(seed)                      # DAC2 mismatch (and DAC1 if not given)
        w = 1.0 + (sigma1 * rng.randn(31) if w1 is None else np.asarray(w1) - 1.0)
        self.w1 = w * (31.0 / w.sum())
        w = 1.0 + SIGMA2 * rng.randn(31)
        self.w2 = w * (31.0 / w.sum())
        self.e1 = np.zeros(31) if e1 is None else np.broadcast_to(np.asarray(e1, float), (31,)).copy()
        self.o1 = np.zeros(31) if o1 is None else np.broadcast_to(np.asarray(o1, float), (31,)).copy()
        self.vfs = m.VREF * m.RIN / m.RD1 if vfs is None else vfs
        self.k_rin, self.k_r, self.k_c, self.a1, self.a2 = k_rin, k_r, k_c, a1, a2
        self.k_c1, self.k_c2 = k_c1, k_c2                    # C1 / C2 against the model's (DRAWN_C12: as drawn)

    def coeffs(self, eld):
        el = dict(rin=m.RIN * self.k_rin, c1=m.C1 * self.k_c * self.k_c1, vfs=self.vfs, r21=m.R21_0 / S2 * self.k_r,
                  rd2=m.RD2_0 / S2 * self.k_r, c2=m.C2_0 * S2 * self.k_c * self.k_c2, a1=self.a1, a2=self.a2)
        if eld > 0:
            ad0, b0 = discretize(**el, tseg=eld * m.T)
            ad, b = discretize(**el, tseg=(1 - eld) * m.T)
        else:
            ad, b = discretize(**el, tseg=m.T)
            ad0, b0 = np.eye(2), np.zeros((2, 3))
        return ad, b, ad0, b0


def spectrum(c):
    """ct2_dac2_options.sndr's spectrum (CIC4 / 256 as the RTL, FIR / 10, the 4 s coherent window,
    0.5-100 Hz): the SNDR, the SNR without the in-band harmonics of the 32 Hz input (64 and 96 Hz),
    and HD2 / HD3 (dBc); NaN after a runaway."""
    if (c < 0).any():
        return (np.nan,) * 4
    r = 256
    acc = c.astype(np.int64)
    for _ in range(4):
        acc = np.cumsum(acc)
    acc = acc[r - 1::r]
    for _ in range(4):
        acc = np.diff(acc, prepend=np.int64(0))
    y = 1.0 - 2.0 * (acc / float(r ** 4)) / 31.0
    d = resample_poly(y, 1, 10, window=("kaiser", 12.0))
    fs2 = m.FS / r / 10
    nrec, i0 = int(round(m.T_REC * fs2)), int(round(m.T_SETTLE * fs2))
    spec = np.abs(np.fft.rfft(d[i0:i0 + nrec])) ** 2
    f = np.arange(spec.size) * fs2 / nrec
    ks = int(round(m.F0 * nrec / fs2))
    band = (f >= 0.5) & (f <= 100.0)
    band[ks] = False
    noise = band.copy()
    noise[[2 * ks, 3 * ks]] = False
    db = lambda x: 10 * np.log10(x)
    return (db(spec[ks] / spec[band].sum()), db(spec[ks] / spec[noise].sum()),
            db(spec[2 * ks] / spec[ks]), db(spec[3 * ks] / spec[ks]))


def run(dies, ain, eld, f0=m.F0):
    """Per die: SNDR, SNR without the in-band harmonics, HD2, HD3 (dB) and the peak |x1|, |x2|."""
    co = [d.coeffs(eld) for d in dies]
    ad, b, ad0, b0 = (np.array([c[i] for c in co]) for i in range(4))
    n = int(round((m.T_SETTLE + m.T_REC + m.T_TAIL) * m.FS))
    u = ain * np.sin(2 * np.pi * f0 * (np.arange(n) + 0.5) * m.T)
    st = lambda a: np.array([getattr(d, a) for d in dies])
    codes, x1m, x2m = simulate(ad, b, ad0, b0, u, st("thr"), st("w1"), st("w2"), st("e1"), st("o1"),
                               np.zeros(len(dies)), np.zeros((len(dies), 31)))
    sp = np.array([spectrum(codes[:, s]) for s in range(len(dies))])
    return dict(sndr=sp[:, 0], snr=sp[:, 1], hd2=sp[:, 2], hd3=sp[:, 3], x1m=x1m, x2m=x2m)


def check(nclk, eld):
    """The vectorized loop against ct2_dac2_options.simulate (pure Python) on random dies."""
    cases = [dict(sigma1=0.005, sigma2=0.02, seed=1, eps1=-1.67e-6),
             dict(sigma1=0.003, sigma2=0.03, seed=7, eps1=2e-5, eps1_sigma=1e-5),
             dict(sigma1=0.01, sigma2=0.01, seed=3, eps1=0.0, thr_sd=1.7e-3)]
    n = nclk
    u = m.AIN * np.sin(2 * np.pi * m.F0 * (np.arange(n) + 0.5) * m.T)
    kw = dict(s=S2, k2=1.0, a1=2710.0, a2=3000.0)
    if eld > 0:
        ad0, b0 = m.discretize(**kw, tseg=eld * m.T)
        ad, b = m.discretize(**kw, tseg=(1 - eld) * m.T)
    else:
        ad, b = m.discretize(**kw)
        ad0, b0 = np.eye(2), np.zeros((2, 3))
    # the per-die discretization of this script must equal the model's
    d0 = Die("x", a1=2710.0, a2=3000.0).coeffs(eld)
    for x, y in zip(d0, (ad, b, ad0, b0)):
        assert np.allclose(x, y, rtol=1e-12, atol=0), "discretize differs"
    rows, W1, W2, E1, THRS = [], [], [], [], []
    for c in cases:
        thr = m.THR + (np.random.RandomState(99).randn(31) * c.get("thr_sd", 0.0))
        t = time.time()
        ref, x1r, x2r = m.simulate(ad, b, u, thr, 0.0, c["sigma1"], c["sigma2"], c["seed"], c["eps1"], 0.0, 0.0,
                                   ad0, b0, c.get("eps1_sigma", 0.0))
        tref = time.time() - t
        np.random.seed(c["seed"])                              # the model's draws, in its order
        w1 = 1.0 + c["sigma1"] * np.random.randn(31)
        w2 = 1.0 + c["sigma2"] * np.random.randn(31)
        np.random.randn(31)                                    # e_odd (zero here)
        e1 = c["eps1"] + c.get("eps1_sigma", 0.0) * np.random.randn(31)
        W1.append(w1 * (31.0 / w1.sum()))
        W2.append(w2 * (31.0 / w2.sum()))
        E1.append(e1)
        THRS.append(thr)
        rows.append((ref, x1r, x2r, tref))
    S = len(cases)
    t = time.time()
    out, x1m, x2m = simulate(np.repeat(ad[None], S, 0), np.repeat(b[None], S, 0), np.repeat(ad0[None], S, 0),
                             np.repeat(b0[None], S, 0), u, np.array(THRS), np.array(W1), np.array(W2), np.array(E1),
                             np.zeros((S, 31)), np.zeros(S), np.zeros((S, 31)))
    tvec = time.time() - t
    ok = True
    for s, (ref, x1r, x2r, tref) in enumerate(rows):
        diff = np.nonzero(out[:, s] != ref)[0]
        same = not len(diff) and x1m[s] == x1r and x2m[s] == x2r
        ok &= same
        print(f"die {s}: {n} clocks, codes {'identical' if not len(diff) else f'differ from clock {diff[0]} ({len(diff)})'}, "
              f"peak |x1| {x1m[s]:.6g} / {x1r:.6g}, |x2| {x2m[s]:.6g} / {x2r:.6g} (model {tref:.1f} s)")
    print(f"vectorized: {S} dies in {tvec:.1f} s; {'PASS' if ok else 'FAIL'}")
    return ok


def load_block():
    with open(BLOCK, encoding="utf-8") as f:
        return json.load(f)


def ota_gains(o1, o2):
    a1 = 10 ** (np.mean([o1["A"]["A_dc_db"], o1["B"]["A_dc_db"]]) / 20)
    return a1, 10 ** (o2["-"]["A_dc_db"] / 20)


def dac1_die(d, typ, rng, even_sd):
    """DAC1's element weights, even and odd charge per toggle (units of the element charge per clock,
    u = i_e T = 2 Iu T), full scale at the input (31 i_e RIN, as measured: 0.6 % below the model's
    VREF RIN / RD1 at typical) and RIN factor. The even charge is the all-31 measurement (the mean
    over the elements: the part DWA does not shape) on every element plus a random part per element
    with zero mean over the 31; typical where the seed has no result yet. The odd charge is measured
    at typical only (adc_block_mc: element 30 turned on alone against on with 29 turned off).
    Returns the parameters and which parts are the seed's own ('static', 'even')."""
    st = d is not None and d.get("elem_err") is not None
    ev = st and d.get("even_all_fc") is not None
    src = d if st else typ
    u = src["u_mean_fc"]
    e1 = np.full(31, (d if ev else typ)["even_all_fc"] / u)
    if ev:
        r = rng.randn(31)
        e1 = e1 + (r - r.mean()) * even_sd / u
    o1 = (src.get("odd_per_toggle_fc") or typ.get("odd_per_toggle_fc") or 0.0) / u
    rin = 0.5 * (src["rin_p_ohm"] + src["rin_n_ohm"])
    rin0 = 0.5 * (typ["rin_p_ohm"] + typ["rin_n_ohm"])
    return (dict(w1=1.0 + np.asarray(src["elem_err"]), e1=e1, o1=o1, vfs=src["vfs_v"], k_rin=rin / rin0),
            {k for k, v in (("static", st), ("even", ev)) if v})


def mc_dies(j):
    typ = j["corners"]["typical"]
    seeds = sorted(int(s) for s, d in j["per_seed"].items() if d.get("quant_threshold_error_mv"))
    # the random part of DAC1's even charge per element: one cell about the common part, over the seeds
    dev = [d["even_one_fc"] - d["even_all_fc"] for d in j["per_seed"].values()
           if d.get("even_one_fc") is not None and d.get("even_all_fc") is not None]
    even_sd = float(np.std(dev, ddof=1)) if len(dev) > 2 else abs(typ["dac1"]["even_one_fc"] - typ["dac1"]["even_all_fc"])
    dies, nod = [], []
    for s in seeds:
        d = j["per_seed"][str(s)]
        g = d.get("globals") or {}
        a1, a2 = ota_gains(d["ota1"], d["ota2"]) if "ota1" in d and "ota2" in d else ota_gains(typ["ota1"], typ["ota2"])
        dac, own = dac1_die(d, typ["dac1"], np.random.RandomState(1000 + s), even_sd)
        note = "" if own == {"static", "even"} else "DAC1 even charge typical" if own else "DAC1 typical"
        if note:
            nod.append(s)
        dies.append(Die(f"mc{s}", thr_err=np.asarray(d["quant_threshold_error_mv"]) * 1e-3, a1=a1, a2=a2,
                        k_r=1.0 + 3 * g.get("mc_rsh_ppolyf_u_1k", 0.0) / RSH_1K, k_c=1.0 + g.get("mc_c_cox_2p0ff", 0.0),
                        seed=s, note=note, **dac))
    return dies, nod, even_sd


def corner_dies(j):
    typ = j["corners"]["typical"]
    dies = []
    for c in ("typical", "ss", "ff", "fs", "sf"):
        d = j["corners"].get(c) or {}
        if not d.get("quant"):
            continue
        a1, a2 = ota_gains(d["ota1"], d["ota2"]) if d.get("ota1") and d.get("ota2") else ota_gains(typ["ota1"], typ["ota2"])
        dac, have = dac1_die(d.get("dac1"), typ["dac1"], np.random.RandomState(0), 0.0)
        # the block benches take res_ss / mimcap_ss with MOS ss (ff with ff; fs / sf typical R and MIM)
        kr, kc = CORNER_R.get(f"res_{c}", 1.0), CORNER_C.get(f"mimcap_{c}", 1.0)
        if not have:                                     # DAC1 of typical: RIN with the corner's sheet
            dac["k_rin"] *= kr
        dies.append(Die(f"MOS {c}" + (f" (res_{c}, mimcap_{c})" if c in ("ss", "ff") else ""),
                        thr_err=np.asarray(d["quant"]["err_mv"]) * 1e-3, a1=a1, a2=a2, k_r=kr, k_c=kc, seed=1,
                        note="" if have else "DAC1 typical", **dac))
    a1, a2 = ota_gains(typ["ota1"], typ["ota2"])
    dac, _ = dac1_die(typ["dac1"], typ["dac1"], np.random.RandomState(0), 0.0)
    combos = [(rc, kr, cc, kc) for rc, kr in CORNER_R.items() for cc, kc in CORNER_C.items()]
    combos += [("res_ff", CORNER_R["res_ff"], "mimcap_typical", 1.0), ("res_typical", 1.0, "mimcap_ff", CORNER_C["mimcap_ff"])]
    for rc, kr, cc, kc in combos:
        d = dict(dac, k_rin=dac["k_rin"] * kr)
        dies.append(Die(f"{rc} {cc}", thr_err=np.asarray(typ["quant"]["err_mv"]) * 1e-3, a1=a1, a2=a2, k_r=kr,
                        k_c=kc, seed=1, **d))
    return dies


EVEN_SWEEP_FC = [-0.016, -0.008, -0.004, -0.002, -0.001, -0.0005, 0.0, 0.0005, 0.001, 0.002, 0.004, 0.008, 0.016]


def even_dies(j):
    """Typical blocks with DAC1's even-order charge per toggle swept (the same on every element)."""
    typ = j["corners"]["typical"]
    a1, a2 = ota_gains(typ["ota1"], typ["ota2"])
    dac, _ = dac1_die(typ["dac1"], typ["dac1"], np.random.RandomState(0), 0.0)
    u = typ["dac1"]["u_mean_fc"]
    return [Die(f"DAC1 even {q:+.4f} fC", thr_err=np.asarray(typ["quant"]["err_mv"]) * 1e-3, a1=a1, a2=a2, seed=1,
                **dict(dac, e1=np.full(31, q / u))) for q in EVEN_SWEEP_FC]


def base_dies():
    return [Die(f"D3 base, seed {s}", a1=2710.0, a2=3000.0, sigma1=0.005, e1=-1.67e-6, seed=s) for s in (1, 2, 3)]


def report(title, dies, r, dt):
    print(f"\n### {title} ({len(dies)} dies, {dt:.0f} s)\n")
    print("| die | SNDR (dB) | SNR without HD2/3 (dB) | HD2 / HD3 (dBc) | peak abs x1 (V) | peak abs x2 (mV) | A1 / A2 (dB) | "
          "R / C / RIN factor | DAC1 full scale (mV) | note |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for k, d in enumerate(dies):
        print(f"| {d.label} | {r['sndr'][k]:.1f} | {r['snr'][k]:.1f} | {r['hd2'][k]:.1f} / {r['hd3'][k]:.1f} | {r['x1m'][k]:.3f} | "
              f"{r['x2m'][k] * 1e3:.1f} | {20 * np.log10(d.a1):.2f} / {20 * np.log10(d.a2):.2f} | "
              f"{d.k_r:.4f} / {d.k_c:.4f} / {d.k_rin:.4f} | {d.vfs * 1e3:.2f} | {d.note} |")
    ok = np.isfinite(r["sndr"])
    if ok.sum() > 1:
        print(f"\nSNDR mean {r['sndr'][ok].mean():.1f} dB, sigma {r['sndr'][ok].std(ddof=1):.1f} dB, worst {r['sndr'][ok].min():.1f} dB; "
              f"SNR worst {r['snr'][ok].min():.1f} dB; HD2 / HD3 worst {r['hd2'][ok].max():.1f} / {r['hd3'][ok].max():.1f} dBc; "
              f"runaways {(~ok).sum()}; peak |x2| up to {r['x2m'].max() * 1e3:.1f} mV (quantizer range +-46.9 mV)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", action="store_true")
    ap.add_argument("--corners", action="store_true")
    ap.add_argument("--base", action="store_true")
    ap.add_argument("--sweep-even", action="store_true", help="typical blocks, DAC1's even charge per toggle swept")
    ap.add_argument("--check", type=int, default=0, metavar="N")
    ap.add_argument("--ain", type=float, default=m.AIN, help="differential sine at the ADC input (V pk)")
    ap.add_argument("--eld", type=float, default=ELD, help="excess loop delay (fraction of the clock)")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check(a.check, a.eld) else 1)
    os.makedirs(OUT, exist_ok=True)
    j = load_block() if (a.mc or a.corners or a.sweep_even) else None
    res = {}
    for flag, title, make in ((a.base, "the D3 model's own assumptions", base_dies),
                              (a.sweep_even, "DAC1 even charge swept", lambda: even_dies(j)),
                              (a.corners, "corners", lambda: corner_dies(j)), (a.mc, "Monte Carlo", None)):
        if not flag:
            continue
        if make is None:
            dies, nod, even_sd = mc_dies(j)
            print(f"Monte Carlo: {len(dies)} seeds; DAC1 from typical for {len(nod)} ({nod}); "
                  f"DAC1 even, random part per element sigma {even_sd:.5f} fC/toggle")
        else:
            dies = make()
        t = time.time()
        r = run(dies, a.ain, a.eld)
        report(f"{title}: ain {a.ain:g} V pk, ELD {a.eld:.4f}", dies, r, time.time() - t)
        res[title] = [dict(label=d.label, sndr_db=float(r["sndr"][k]), snr_db=float(r["snr"][k]), hd2_dbc=float(r["hd2"][k]),
                           hd3_dbc=float(r["hd3"][k]), x1max=float(r["x1m"][k]), x2max=float(r["x2m"][k]), k_r=d.k_r,
                           k_c=d.k_c, k_rin=d.k_rin, a1=d.a1, a2=d.a2, vfs=d.vfs, e1_mean=float(d.e1.mean()),
                           e1_sd=float(d.e1.std()), o1_mean=float(d.o1.mean()),
                           thr_sd_mv=float((d.thr - m.THR).std() * 1e3), note=d.note)
                      for k, d in enumerate(dies)]
    if res:
        tag = "_".join(k for k, f in (("base", a.base), ("even", a.sweep_even), ("corners", a.corners), ("mc", a.mc))
                       if f)
        path = os.path.join(OUT, f"{tag}_ain{a.ain:g}_eld{a.eld:.4f}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(ain=a.ain, eld=a.eld, block=BLOCK, results=res), f, indent=1)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
