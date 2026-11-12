#!/usr/bin/env python3
"""Flicker (1/f) noise of the ADC's poly resistors (11/12, gf180_realistic_eval_20261028.md): the ppolyf_u_1k units
of RIN and DAC1 (291.28 x 1 um, about 310 kohm) and the reference filter R_f (ppolyf_u 2 x 7 um), in the residual
band 0.5-100 Hz, electrode-referred (AFE gain 297.75).

The PDK's model: the body of each resistor carries KF and AF (ppolyf_u_1k: KF 2.62e-26, AF 1; ppolyf_u: KF 2.4e-23,
AF 1.79) and ngspice gives a shunt noise current S_I = KF |I|^AF / (f L W) (L, W the effective dimensions in m). With
the PDK's own body expression (r= with v()) ngspice makes the body a B source and drops this noise; afe_startup.res_mm
(constant body r, model card kept) restores it. Part 1 checks the closed form against ngspice .noise on res_mm.

How the noise reaches DATA:
- DAC1: each cell has a 600 kohm string (two units) from VREFP and one from VREFN; they never leave their references,
  so each carries a constant DC current I0 = (VREFP - VREFN) / 2 / (2 R_u) whatever the code, and the PDK's noise of
  that DC current is stationary. The steering switch sends it to OUTP or OUTN: cell j adds d_j[n] eta_j(t) to the DAC's
  normalised output, d_j = +-1 its selection, eta_j the relative 1/f fluctuation of its two strings. With the DWA of
  eeg_dwa.sv every cell's selection averages to the code, so only the product with the signal stays in the band;
  Part 2 runs the code streams of the behavioral loop (rtl/model/ct2_codes.py, white input noise added) through the
  DWA and the thermometer (DWA_EN = 0) and integrates e = (1/62) sum_j d_j eta_j.
- RIN: 16 units per side carry the signal current (u/2)/R_u. A resistor's 1/f noise is a fluctuation of its
  resistance, noise current = -I(t) dR/R (Coram, McAndrew, Gullapalli, Kundert, "Flicker noise formulations in
  compact models", IEEE TCAD 2020: AF = 2 has the physical basis, and KF |I|^AF applied to a current that changes
  sign gives a wrong dc-like 1/f component). Model B (used for the budget): dR/R with S = K / (L W f), K taken from
  the PDK at a calibration current I_cal, K = KF I_cal^(AF - 2), so the input-referred noise is u (g_P + g_N) / 2.
  Model A (for reference only): the PDK's KF |I(t)|^AF at the instantaneous current, as a periodic-noise analysis
  with the PDK's model would compute it; it grows as sqrt(level) and is the form the paper shows to be wrong.
  The PDK's AF = 1 makes K depend on the current (K = KF / I): the PDK documents 1/f measurement conditions only for
  MOSFETs, so where its fit holds is not known. I_cal = I0 (the DAC1 strings' current, also the RIN units' current at
  full scale) is the conservative choice; Part 3 sweeps I_cal.

usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_flicker.py [--log2n 22]   (from the repo root)
writes runs/adc_flicker/: adc_flicker.json (all numbers), psd_<case>.npz (spectra for figs_perf.py), ng/ (decks)"""
import argparse
import bisect
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "rtl", "model"))
import afe_startup as S  # noqa: E402  (res_mm model header)
import ct2_codes as C  # noqa: E402  (behavioral CT loop)

OUT = os.path.join(HERE, "runs", "adc_flicker")
ADC = os.path.join(HERE, "..", "adc")
K_B, T_K = 1.380649e-23, 300.15
FS = 1.024e6
G_AFE = 297.75                    # electrode -> ADC input (gf180_input_output_20261112.md)
FS_PK = 0.943e-3                  # full scale of the ENOB budget, electrode pk
BASE_NV = 5.60                    # residual without these terms, code 3 (gf180_realistic_eval_20261028.md, 11/12)
VREF_CHIP = 0.487735              # VREFP - VREFN at the ADC (the r9 chain, typical)
I_RF = 30e-6                      # DC current through each R_f (eeg_ref.spice: DAC1 25.6 + ladder 1.6 + VCM 2.5 uA)
EXT_REF_NV = 375.0                # requirement on the external reference, differential nVrms in the band
BAND = (0.5, 100.0)
LNB = math.log(BAND[1] / BAND[0])
TYPES = {  # kf, af, r_dw, r_dl (PDK sm141064.spice, .lib res)
    "ppolyf_u_1k": (2.62e-26, 1.0, 0.0148e-6, 3.85e-11),
    "ppolyf_u": (2.4e-23, 1.79, 2.55e-8, 2e-11),
}
UNIT = ("ppolyf_u_1k", 291.28, 1.0)


def check_netlists():
    """the geometry this script assumes, from the netlists"""
    adc = open(os.path.join(ADC, "eeg_adc.spice")).read()
    dac = open(os.path.join(ADC, "eeg_dac1.spice")).read()
    ref = open(os.path.join(ADC, "eeg_ref.spice")).read()
    for side in "PN":
        assert re.search(rf"^XRIN{side} \S+ \S+ AVSS ppolyf_u_1k r_length=291.28u r_width=1u m=16$", adc, re.M), side
    cell = dac[dac.index(".subckt eeg_dac1_cell"):]
    cell = cell[:cell.index(".ends")]
    assert len(re.findall(r"ppolyf_u_1k r_length=291.28u r_width=1u$", cell, re.M)) == 4
    assert dac.count("eeg_dac1_cell\n") >= 31
    assert len(re.findall(r"ppolyf_u r_length=2u r_width=7u$", ref, re.M)) == 2


def eff_lw(typ, l_um, w_um):
    kf, af, dw, dl = TYPES[typ]
    return (l_um * 1e-6 - 2 * dl) * (w_um * 1e-6 - 2 * dw)


def header():
    """the Monte Carlo model header (res_mm: the PDK's resistor sections with a constant body expression, so ngspice
    keeps the body's noise) with the global and per-instance variation switched off: typical values"""
    h = S.head("typical", 1, "lin")
    for p in ("sw_stat_global", "sw_stat_mismatch"):
        assert f".param {p}=1\n" in h, p
        h = h.replace(f".param {p}=1\n", f".param {p}=0\n")
    return h


def ngspice_part():
    """.noise at 10 Hz of one device on a DC current, against sqrt(4kTR + KF I^AF R^2 / (f L W))"""
    cases = [(*UNIT, i) for i in (0.03, 0.1, 0.3, 0.4064, 1.0, 3.0)]
    cases += [("ppolyf_u_1k", 582.56, 2.0, 0.4064), ("ppolyf_u", 857.0, 1.0, 0.4064), ("ppolyf_u", 2.0, 7.0, I_RF * 1e6)]
    rows = []
    for typ, l_um, w_um, i_ua in cases:
        d = os.path.join(OUT, "ng", f"{typ}_{l_um:g}x{w_um:g}_{i_ua:g}uA")
        os.makedirs(d, exist_ok=True)
        deck = (f"* poly flicker check (adc_flicker.py)\n{header()}\n.temp 27\n"
                f"XR n 0 0 {typ} r_length={l_um}u r_width={w_um}u\nI1 0 n dc {i_ua}u ac 1\n"
                f".control\nop\nlet rdc = v(n) / {i_ua}u\nprint rdc\nnoise v(n) I1 dec 1 10 10\nsetplot noise1\n"
                f"print onoise_spectrum\n.endc\n.end\n")
        open(os.path.join(d, "tb.spice"), "w").write(deck)
        log = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True).stdout
        open(os.path.join(d, "run.log"), "w").write(log)
        r = float(re.search(r"rdc = ([-0-9.e+]+)", log).group(1))
        sim = float(re.findall(r"onoise_spectrum = ([-0-9.e+]+)", log)[0])
        kf, af = TYPES[typ][:2]
        i = i_ua * 1e-6
        lw = eff_lw(typ, l_um, w_um)
        form = math.sqrt(4 * K_B * T_K * r + kf * i ** af / (10.0 * lw) * r ** 2)
        fl10 = max(sim ** 2 - 4 * K_B * T_K * r, 0.0)          # the flicker part of the simulated V^2/Hz at 10 Hz
        rows.append(dict(type=typ, l_um=l_um, w_um=w_um, i_ua=i_ua, r=r, sim_nv=sim * 1e9, formula_nv=form * 1e9,
                         ratio=sim / form, rel_f=fl10 * 10.0 / (i * r) ** 2,   # S_I / I^2 x f from the simulation
                         rel_f_model=kf * i ** (af - 2) / lw))
        print(f"  {typ:12s} {l_um:7.2f} x {w_um:4.1f} um, {i_ua:7.4f} uA, R {r:10.1f}: {sim * 1e9:9.3f} nV/rtHz at 10 Hz "
              f"(closed form {form * 1e9:9.3f}, ratio {sim / form:.4f}), S_I/I^2 x f {rows[-1]['rel_f']:.4e}", flush=True)
    return rows


def codes_noisy(n, dc, amp, f0, noise_rms, seed):
    """ct2_codes.ct2_codes with white Gaussian input noise (V rms per clock) added to the input"""
    t = C.m.T
    sa = C.segment(C.E_DAC2 / 32 * t)
    sb = C.segment((C.E_DAC1 - C.E_DAC2) / 32 * t)
    sc = C.segment((32 - C.E_DAC1) / 32 * t)
    a00, a01, a10, a11, ba00, ba01, ba02, ba10, ba11, ba12 = sa
    b00, b01, b10, b11, bb00, bb01, bb02, bb10, bb11, bb12 = sb
    c00, c01, c10, c11, bc00, bc01, bc02, bc10, bc11, bc12 = sc
    ka1, ka2, kc1, kc2 = ba01 + ba02, ba11 + ba12, bc01 + bc02, bc11 + bc12
    thr = [float(v) for v in C.m.THR]
    rng = np.random.default_rng(seed)
    out = np.empty(n, np.uint8)
    x1 = x2 = 0.0
    yp = 1.0 - 2.0 * 16 / 31.0
    for start in range(0, n, 1 << 20):
        stop = min(n, start + (1 << 20))
        tt = (np.arange(start, stop, dtype=np.float64) + 0.5) * t
        u_arr = dc + amp * np.sin(2 * math.pi * f0 * tt) + noise_rms * rng.standard_normal(stop - start)
        for i, u in zip(range(start, stop), u_arr.tolist()):
            p1 = a00 * x1 + a01 * x2 + ba00 * u + ka1 * yp
            p2 = a10 * x1 + a11 * x2 + ba10 * u + ka2 * yp
            c = bisect.bisect_left(thr, x2)
            out[i] = c
            y = (2.0 * c - 31.0) / 31.0
            q1 = b00 * p1 + b01 * p2 + bb00 * u + bb01 * yp + bb02 * y
            q2 = b10 * p1 + b11 * p2 + bb10 * u + bb11 * yp + bb12 * y
            x1 = c00 * q1 + c01 * q2 + bc00 * u + kc1 * y
            x2 = c10 * q1 + c11 * q2 + bc10 * u + kc2 * y
            yp = y
            if abs(x2) > 10.0:
                raise SystemExit(f"loop runaway at frame {i}")
    return out


def pink(n, s1, rng):
    """real sequence with one-sided PSD s1 / f (nothing at DC)"""
    w = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    h = np.zeros_like(f)
    h[1:] = np.sqrt(s1 / f[1:] * FS / 2)
    return np.fft.irfft(w * h, n)


def psd(x):
    n = len(x)
    win = np.hanning(n)
    p = 2 * np.abs(np.fft.rfft((x - x.mean()) * win)) ** 2 / (FS * np.sum(win ** 2))
    return np.fft.rfftfreq(n, 1 / FS), p


def band_power(f, p, f0):
    """power in BAND, without |f - f0| < 0.5 Hz around a tone (those bins count as the signal)"""
    keep = (f >= BAND[0]) & (f <= BAND[1])
    if f0 > 0:
        keep &= np.abs(f - f0) >= 0.5
    return float(np.sum(p[keep]) * (f[1] - f[0]))


def selections(c, dwa=True):
    """d_j[n] = +-1, j = 0..30: eeg_dwa.sv (k = 31 - c elements to the positive reference, p <- (p + k) mod 31,
    pointer 0 at reset) or the thermometer (DWA_EN = 0)"""
    k = 31 - c.astype(np.int64)
    p = np.concatenate(([0], np.cumsum(k)[:-1])) % 31
    for j in range(31):
        yield j, np.where((((j - p) % 31) if dwa else j) < k, 1.0, -1.0)


def loop_part(n, s_r, r_u, noise_rms):
    """the DAC1 and RIN noise for a set of inputs (u at the ADC input, V), DWA and thermometer"""
    nset = 1 << 13
    f0 = round(10.0 * n / FS) * FS / n                    # about 10 Hz, an integer number of cycles in the record
    a_fs = FS_PK * G_AFE
    u_fs_model = C.m.VREF * C.m.RIN / C.m.RD1             # ADC input for y = 1 in the behavioral loop
    kf, lw = TYPES["ppolyf_u_1k"][0], eff_lw(*UNIT)
    cases = [("zero", 0.0, 0.0, True), ("dc_res153", 153e-6 * G_AFE, 0.0, True), ("sine_10pct", 0.0, 0.1 * a_fs, True),
             ("sine_fs", 0.0, a_fs, True), ("zero_therm", 0.0, 0.0, False), ("sine_fs_therm", 0.0, a_fs, False)]
    cache, res = {}, {}
    for name, dc, amp, dwa in cases:
        t0 = time.time()
        if (dc, amp) not in cache:
            cache[(dc, amp)] = codes_noisy(n + nset, dc, amp, f0, noise_rms, seed=7)
        c_all = cache[(dc, amp)]
        e, eta_sum, dbar = np.zeros(n), np.zeros(n), np.zeros(n)
        for j, d in selections(c_all, dwa):
            eta = pink(n, s_r, np.random.default_rng(1000 + j))   # the same cell noise in every case
            dj = d[nset:]
            e += dj * eta
            eta_sum += eta
            dbar += dj
        e /= 62.0
        e_gain = dbar / 31.0 * eta_sum / 62.0                     # the part that follows the code (signal x mean fluctuation)
        ft = f0 if amp > 0 else 0.0
        f, p_dac = psd(e)
        tt = (np.arange(nset, nset + n) + 0.5) / FS
        u = dc + amp * np.sin(2 * math.pi * f0 * tt)
        v_a = np.sqrt(kf * np.abs(u) * r_u / (32 * lw)) * (pink(n, 1.0, np.random.default_rng(2001)) -
                                                           pink(n, 1.0, np.random.default_rng(2002)))
        v_b = u / 2 * (pink(n, s_r / 16, np.random.default_rng(2003)) + pink(n, s_r / 16, np.random.default_rng(2004)))
        _, p_a = psd(v_a)
        _, p_b = psd(v_b)
        to_nv = lambda pw, scale=1.0: math.sqrt(pw) * scale / G_AFE * 1e9   # noqa: E731
        u2 = dc ** 2 + amp ** 2 / 2
        mabs = abs(dc) if amp == 0 else 2 / math.pi * amp
        r = dict(dc_v=dc, amp_v=amp, dwa=dwa,
                 dac_nv=to_nv(band_power(f, p_dac, ft), u_fs_model),
                 dac_gain_nv=to_nv(band_power(*psd(e_gain), ft), u_fs_model),
                 dac_rest_nv=to_nv(band_power(*psd(e - e_gain), ft), u_fs_model),
                 dac_cf_nv=math.sqrt(u2 * s_r / 124 * LNB) / G_AFE * 1e9,
                 rin_b_nv=to_nv(band_power(f, p_b, ft)), rin_b_cf_nv=math.sqrt(u2 * s_r / 32 * LNB) / G_AFE * 1e9,
                 rin_a_nv=to_nv(band_power(f, p_a, ft)),
                 rin_a_cf_nv=math.sqrt(kf * mabs * r_u / (16 * lw) * LNB) / G_AFE * 1e9,
                 code_mean=float(c_all[nset:].mean()), code_std=float(c_all[nset:].std()))
        res[name] = r
        print(f"  {name:14s} DAC1 {r['dac_nv']:6.3f} nV (follows the code {r['dac_gain_nv']:6.3f}, rest {r['dac_rest_nv']:6.3f}, "
              f"closed form {r['dac_cf_nv']:6.3f}); RIN B {r['rin_b_nv']:6.3f} (cf {r['rin_b_cf_nv']:6.3f}), "
              f"A {r['rin_a_nv']:6.3f} (cf {r['rin_a_cf_nv']:6.3f}) [{time.time() - t0:.0f} s]", flush=True)
        sel = (f > 0) & (f <= 400)
        np.savez_compressed(os.path.join(OUT, f"psd_{name}.npz"), f=f[sel], f0=ft,
                            dac=p_dac[sel] * (u_fs_model / G_AFE) ** 2, rin_b=p_b[sel] / G_AFE ** 2,
                            rin_a=p_a[sel] / G_AFE ** 2)
    return res, f0


def enob(nv):
    return (20 * math.log10(FS_PK / math.sqrt(2) / (nv * 1e-9)) - 1.76) / 6.02


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log2n", type=int, default=22, help="record of 2^N frames at 1.024 MHz (22: 4.1 s)")
    ap.add_argument("--noise", type=float, default=50e-6, help="white noise at the ADC input, V rms per clock")
    a = ap.parse_args()
    os.chdir(REPO)
    os.makedirs(OUT, exist_ok=True)
    check_netlists()
    print("Part 1: ngspice .noise of the PDK's resistors (res_mm), 10 Hz")
    ng = ngspice_part()
    unit = next(r for r in ng if r["type"] == "ppolyf_u_1k" and r["l_um"] == 291.28 and r["i_ua"] == 0.4064)
    r_u = unit["r"]
    i0 = VREF_CHIP / 2 / (2 * r_u)                      # DAC1 string current
    kf = TYPES["ppolyf_u_1k"][0]
    s_r = kf / (i0 * eff_lw(*UNIT))                     # relative 1/f PSD x f of one unit at I0 (model B at I_cal = I0)
    alt = next(r for r in ng if r["type"] == "ppolyf_u" and r["l_um"] == 857.0)
    big = next(r for r in ng if r["l_um"] == 582.56)
    rf = next(r for r in ng if r["type"] == "ppolyf_u" and r["l_um"] == 2.0)
    # R_f: both references' fluctuations add to VREFP - VREFN; the DAC1 output (and the signal it balances) scales with it
    rf_v2 = 2 * rf["rel_f"] * (I_RF * rf["r"]) ** 2 * LNB
    rf_nv = math.sqrt(rf_v2) * 1e9
    print(f"I0 {i0 * 1e6:.4f} uA, S_R {s_r:.4e}; R_f: {rf_nv:.1f} nVrms on VREFP - VREFN (requirement {EXT_REF_NV:.0f}), "
          f"{0.5 * rf_nv / EXT_REF_NV:.3f} nVrms at full scale")
    print(f"Part 2: behavioral loop, DWA, 2^{a.log2n} frames")
    loop, f0 = loop_part(1 << a.log2n, s_r, r_u, a.noise)
    fs = loop["sine_fs"]
    fs_b = math.hypot(fs["rin_b_nv"], fs["dac_nv"])
    fs_a = math.hypot(fs["rin_a_nv"], fs["dac_nv"])
    base = BASE_NV
    room = math.sqrt((FS_PK / math.sqrt(2) / 10 ** ((16.5 * 6.02 + 1.76) / 20) * 1e9) ** 2 - base ** 2)
    # Part 3: where the PDK's level is taken (model B scales as sqrt(I0 / I_cal))
    ical = np.logspace(-7, -4, 121)
    sweep = [dict(i_cal=float(ic), fs_nv=fs_b * math.sqrt(i0 / ic), enob=enob(math.hypot(base, fs_b * math.sqrt(i0 / ic))))
             for ic in ical]
    i_cross = i0 * (fs_b / room) ** 2
    alt_ratio = math.sqrt(alt["rel_f"] / unit["rel_f"])
    big_ratio = math.sqrt(big["rel_f"] / unit["rel_f"])
    summ = dict(base_nv=base, base_enob=enob(base), fs_b_nv=fs_b, fs_a_nv=fs_a, enob_b=enob(math.hypot(base, fs_b)),
                enob_a=enob(math.hypot(base, fs_a)), room_nv=room, i_cross=i_cross, rf_nv=rf_nv,
                rf_fs_nv=0.5 * rf_nv / EXT_REF_NV, alt_ratio=alt_ratio, enob_alt=enob(math.hypot(base, fs_b * alt_ratio)),
                big_ratio=big_ratio, enob_big=enob(math.hypot(base, fs_b * big_ratio)))
    print(f"full scale, model B at I0: RIN {fs['rin_b_nv']:.2f} + DAC1 {fs['dac_nv']:.2f} -> {fs_b:.2f} nVrms, "
          f"{summ['enob_b']:.2f} bit (without: {summ['base_enob']:.2f}); model A {fs_a:.2f} nVrms, {summ['enob_a']:.2f} bit")
    print(f"room for 16.5 bit at full scale {room:.2f} nVrms: the PDK's level must hold only above {i_cross * 1e6:.2f} uA; "
          f"ppolyf_u units x{alt_ratio:.4f} -> {summ['enob_alt']:.2f} bit; 4x area x{big_ratio:.3f} -> {summ['enob_big']:.2f} bit")
    json.dump(dict(ngspice=ng, loop=loop, f0=f0, n=1 << a.log2n, i0=i0, s_r=s_r, r_u=r_u, kf=kf, lw=eff_lw(*UNIT),
                   g_afe=G_AFE, band=BAND, noise=a.noise, sweep=sweep, summary=summ, vref=VREF_CHIP, i_rf=I_RF),
              open(os.path.join(OUT, "adc_flicker.json"), "w"), indent=1)
    print("wrote", os.path.join(OUT, "adc_flicker.json"))


if __name__ == "__main__":
    main()
