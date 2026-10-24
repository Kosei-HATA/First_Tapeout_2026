#!/usr/bin/env python3
"""AFE output by chopper phase and the INP/INN DC path (tracker B7, 10/24): the testbenches
of pex_afe.py (afe_top, typical, 27 C, CPF_TRIM 8, the ADC input RIN 18.75 kohm per side as
the load) looked at phase by phase.

The DC path is a switched capacitor per side. With one branch (CSCP charged from INP in
phase A, dumped into ONI in phase B) its charge balances when ONI(phase B) = INP(phase A): it
holds the amplifier output of phase B, not its average, so anything slower than the DC path
(the EEG band, the offset-DAC residual) leaves phase B at zero and phase A at about twice the
average. Since 0cb0fff4 (B7 fix (d)) each side has a second branch with the phases swapped
and all eight switches are gated by the output-chopper phases CDA2 / CDB2, so the charge
balances on the average of both phases. This script measures the DC path as drawn; the
one-branch results of the B7 document (10/24) were taken with it at b64899c3 (--dc cur, and
--dc sym for the fix added as ideal devices).

Measurements (outputs averaged over whole chopper periods; the 100-200 us window of
pex_afe.py tran holds 12.8 periods and read about 1.6 % low with the one-branch DC path):
  residual  offset DAC on (range 1, blanking 15 MCLK, magnitude = round(vin / 0.311 mV)),
            DC inputs (default both ends of the M = 96 window, 29.735 and 30.04 mV), 1 ms,
            averaged over 0.8-1.0 ms (the reset in phase B leaves the phases unequal, which
            the DC path removes with 138 us): per-period average, held level of phase A / B,
            and the average over each of the 8 ADC clocks of a chopper period (the shape the
            ADC sees)
  step      input 0 -> +0.5 mV at 50 us (in phase B, after the reset at 11 us), 1.5 ms:
            the held levels of both phases as the DC path settles
  static    DC inputs as a step at 50 us (both phases start equal; applied from t = 0 the
            imbalance the reset leaves in phase B decays with 138 us inside the window),
            200 us; a polynomial through the points (offset and even terms included; put 0
            in --levels for the extracted layout) gives HD2..HD5 of a full-scale sine
            (0.943 mV pk) well below the DC-path corner (static = in-band)
  sine      full-scale sine at fch / --div (256: 500 Hz), FFT of the per-period average over
            4 signal periods from the last phase-A edge at or before --fft0

Usage: python3 gf180/tapeout/pex/afe_dcpath.py residual [--variant sch|pex] [--vin 29.735 30.04]
       python3 gf180/tapeout/pex/afe_dcpath.py step [--variant ...]
       python3 gf180/tapeout/pex/afe_dcpath.py static [--variant ...] [--levels ...]
       python3 gf180/tapeout/pex/afe_dcpath.py sine [--variant ...] [--div 256]
"""
import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pex_afe as p  # noqa: E402

TCH = p.TCH
TADC = 32 * p.MCLK                     # ADC clock, 8 per chopper period
RUNS = os.path.join(p.HERE, "runs", "afe_dcpath")
FS_MV = 0.943


def first_edge(t0):
    """First CHOP rising edge (start of phase A in the bench) at or after t0."""
    return TCH / 2 + TCH * np.ceil((t0 - TCH / 2) / TCH - 1e-9)


def deck(variant, vin_mv=0.0, step_mv=None, tstop=200e-6, blank=p.BLANK, sine_mv=0.0, div=64, dac=None):
    txt = p.tran_deck(variant, vin_mv, tstop=tstop, blank=blank, sine_mv=sine_mv, dac=dac)
    if step_mv is not None:
        txt, n = re.subn(r"^VSRC SRC 0 DC 0$", f"VSRC SRC 0 PWL(0 0 50u 0 50.1u {step_mv * 1e-3:.6g})", txt,
                         count=1, flags=re.M)
        assert n == 1
    if sine_mv and div != 64:
        txt, n = re.subn(r"SIN\((\S+) (\S+) 2000 ", rf"SIN(\1 \2 {p.FCH / div:g} ", txt)
        assert n == 1
    return txt


def load(d):
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    return x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7]     # t, OUTP-OUTN, OPI-ONI, CDA, CDB


def periods(t, vo, cda, cdb, t0, t1, n=None):
    """Per chopper period from the first phase-A edge at or after t0 (n periods, or as many
    as end before t1): held level in phase A and phase B, the period average, and the
    average over each of the 8 ADC clocks."""
    q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
    e0 = first_edge(t0)
    rows, clk = [], []
    for k in range(n if n is not None else int((t1 - e0) / TCH + 1e-9)):
        a, b = e0 + k * TCH, e0 + (k + 1) * TCH
        s = (t >= a) & (t < b)
        qe = np.interp(a + TADC * np.arange(9), t, q)
        clk.append(np.diff(qe) / TADC)
        rows.append((a, vo[s & (cda > 1.65)].mean(), vo[s & (cdb > 1.65)].mean(), (qe[-1] - qe[0]) / TCH))
    return np.array(rows), np.array(clk)


def job_dir(name):
    return os.path.join(RUNS, name)


def residual_one(variant, vin):
    d = job_dir(f"residual_{variant}_{vin:+g}mV")
    p.run(d, deck(variant, vin, tstop=1e-3, blank=15 * p.MCLK, dac=(vin, 1)))
    t, vo, va, cda, cdb = load(d)
    r, clk = periods(t, vo, cda, cdb, 0.8e-3, 1e-3)
    return vin, r[:, 3].mean(), r[:, 1].mean(), r[:, 2].mean(), clk.mean(0), np.abs(va[t >= 0.8e-3]).max()


def static_one(variant, v):
    d = job_dir(f"static_{variant}_{v:+g}mV")
    p.run(d, deck(variant, step_mv=v))
    t, vo, va, cda, cdb = load(d)
    r, _ = periods(t, vo, cda, cdb, 100e-6, 200e-6)
    return v, r[:, 3].mean(), r[:, 1].mean(), r[:, 2].mean()


def fit_hd(v_mv, y, deg=6):
    """Polynomial of degree deg in v / FS_MV through the static points (an offset and the
    even terms included, for the extracted layout); the gain at zero and HD2..HD5 (dBc) of
    a full-scale sine through it, and the largest fit residual (V)."""
    x = np.asarray(v_mv) / FS_MV
    m = np.vstack([x ** k for k in range(deg + 1)]).T
    c, *_ = np.linalg.lstsq(m, np.asarray(y), rcond=None)
    s = np.sin(np.linspace(0, 2 * np.pi, 4096, endpoint=False))
    spec = np.abs(np.fft.rfft(sum(ck * s ** k for k, ck in enumerate(c))))
    hd = [20 * np.log10(spec[k] / spec[1] + 1e-30) for k in range(2, 6)]
    return c[1] / (FS_MV * 1e-3), hd, np.abs(np.asarray(y) - m @ c).max()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["residual", "step", "static", "sine"])
    ap.add_argument("--variant", default="sch", choices=["sch", "dev", "pex"])
    ap.add_argument("--vin", nargs="+", type=float, default=[29.735, 30.04])
    ap.add_argument("--levels", nargs="+", type=float,
                    default=[-0.943, -0.707, -0.471, -0.236, 0.236, 0.471, 0.707, 0.943])
    ap.add_argument("--div", type=int, default=256)
    ap.add_argument("--fft0", type=float, default=2e-3)
    a = ap.parse_args()
    v = a.variant
    if a.what == "residual":
        with ThreadPoolExecutor(len(a.vin)) as ex:
            res = list(ex.map(lambda x: residual_one(v, x), a.vin))
        print("| vin (mV) | M | per-period average (mV) | phase A held (mV) | phase B held (mV) | max abs(OPI-ONI) (V) | "
              "per-ADC-clock / average |")
        print("|---|---|---|---|---|---|---|")
        for vin, avg, la, lb, shp, vamax in res:
            print(f"| {vin:+g} | {round(abs(vin) / p.UNIT_MV)} | {avg * 1e3:+.3f} | {la * 1e3:+.2f} | {lb * 1e3:+.2f} | "
                  f"{vamax:.3f} | " + " ".join(f"{s / avg:.3f}" for s in shp) + " |")
        if len(res) == 2:
            (v1, y1, *_), (v2, y2, *_) = res
            g = (y2 - y1) / ((v2 - v1) * 1e-3)
            print(f"gain (offset DAC on, range 1, 15 MCLK) {g:.2f}; input-referred residuals "
                  + ", ".join(f"{y / g * 1e3:+.4f} mV" for _, y, *__ in res)
                  + f"; zero at {v1 - y1 / g * 1e3:.4f} mV (M x unit {round(abs(v1) / p.UNIT_MV) * p.UNIT_MV:.4f} mV)")
    elif a.what == "step":
        d = job_dir(f"step_{v}")
        p.run(d, deck(v, step_mv=0.5, tstop=1.5e-3))
        t, vo, va, cda, cdb = load(d)
        r = periods(t, vo, cda, cdb, 50e-6, 1.5e-3)[0]
        print(f"## step {v}: t (us), phase A / B held (mV), period average (mV)")
        for k in list(range(0, 12, 2)) + list(range(12, len(r), 16)) + [len(r) - 1]:
            print(f"{r[k, 0] * 1e6:7.1f}  {r[k, 1] * 1e3:8.2f}  {r[k, 2] * 1e3:8.2f}  {r[k, 3] * 1e3:9.3f}")
    elif a.what == "static":
        with ThreadPoolExecutor(min(len(a.levels), 8)) as ex:
            rows = list(ex.map(lambda x: static_one(v, x), a.levels))
        for r in rows:
            print(f"{v} {r[0]:+.3f} mV: average {r[1] * 1e3:+.5f} mV, phase A {r[2] * 1e3:+.3f}, "
                  f"phase B {r[3] * 1e3:+.3f} mV")
        g, hd, res = fit_hd([r[0] for r in rows], [r[1] for r in rows])
        print(f"{v}: gain {g:.3f}, full-scale HD2..HD5 " + " / ".join(f"{h:.1f}" for h in hd)
              + f" dBc (fit residual {res * 1e6:.2f} uV)", flush=True)
    else:
        n, nper = a.div, 4
        tstop = a.fft0 + nper * n * TCH
        d = job_dir(f"sine_{v}_{p.FCH / n:g}Hz")
        p.run(d, deck(v, tstop=tstop, sine_mv=FS_MV, div=n))
        t, vo, va, cda, cdb = load(d)
        # exactly nper x n periods (coherent FFT), from the last phase-A edge at or before
        # fft0; from the first edge after it only nper x n - 1 periods end before tstop
        r, _ = periods(t, vo, cda, cdb, a.fft0 - TCH, tstop, n=nper * n)
        per = r[:, 3]
        spec = np.abs(np.fft.rfft(per - per.mean())) / (len(per) / 2)
        h = [spec[nper * k] for k in range(1, 6)]
        print("| DUT | f (Hz) | gain | HD2 | HD3 | HD4 | HD5 (dBc) | phase A / B max (mV) | max abs(OPI-ONI) (mV) |")
        print("|---|---|---|---|---|---|---|---|---|")
        print(f"| {v} | {p.FCH / n:g} | {h[0] / (FS_MV * 1e-3):.2f} | " + " | ".join(f"{20 * np.log10(x / h[0]):.1f}"
                                                                         for x in h[1:])
              + f" | {np.abs(r[:, 1]).max() * 1e3:.1f} / {np.abs(r[:, 2]).max() * 1e3:.1f} | "
              f"{np.abs(va[t >= a.fft0]).max() * 1e3:.1f} |")


if __name__ == "__main__":
    main()
