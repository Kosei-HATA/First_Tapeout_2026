#!/usr/bin/env python3
"""AFE output by chopper phase and the INP/INN DC path (tracker B7, 10/24): the testbenches
of pex_afe.py (afe_top, typical, 27 C, CPF_TRIM 8, the ADC input RIN 18.75 kohm per side as
the load) looked at phase by phase.

The DC path is a switched capacitor per side: CSCP charges from INP in phase A (CIA2) and
dumps into ONI in phase B (CIB2), so its charge balances when ONI(phase B) = INP(phase A).
It holds the amplifier output of phase B, not its average: for anything slower than the DC
path (Rsc x Cf = 287 us, 555 Hz) - the EEG band, the offset-DAC residual - the output of
phase B goes to zero and phase A carries about twice the average. The per-period average
(what the CIC sees) is unchanged; the ADC input and the amplifier swing in phase A double.

  --dc cur  the DC path as drawn
       sym  plus a second branch per side with the phases swapped (CIB2: INP, CIA2: ONI;
            54.52 fF, the same NMOS), so that the charge balances on the average of both
            phases (the candidate fix)

Measurements (outputs averaged over whole chopper periods; the 100-200 us window of
pex_afe.py tran holds 12.8 periods and reads about 1.6 % low with the uneven phases):
  residual  offset DAC on (range 1, blanking 15 MCLK, magnitude = round(vin / 0.311 mV)),
            DC inputs (default both ends of the M = 96 window, 29.735 and 30.04 mV), 200 us:
            per-period average, held level of phase A / B, and the average over each of
            the 8 ADC clocks of a chopper period (the shape the ADC sees)
  step      input 0 -> +0.5 mV at 50 us (in phase B, after the reset at 11 us), 1.5 ms:
            the held levels of both phases as the DC path settles
  static    DC inputs (cur: from t = 0, the reset in phase B leaves the held state at once;
            sym: a step at 50 us, both phases start equal), 200 us; a polynomial through
            the points (offset and even terms included; put 0 in --levels for the extracted
            layout) gives HD2..HD5 of a full-scale sine (0.943 mV pk) well below the DC-path
            corner (static = in-band)
  sine      full-scale sine at fch / --div (256: 500 Hz, the DC path follows 74 %), FFT of
            the per-period average over 4 signal periods from --fft0; --fast k multiplies
            the DC-path capacitors by k (16: corner 8.9 kHz, so that 2 kHz with --div 64
            behaves like an in-band signal; with sym the swapped branch then adds a large
            positive feedback, gain about 375, so only cur is meaningful there)

Usage: python3 gf180/tapeout/pex/afe_dcpath.py residual [--variant sch|pex] [--vin 29.735 30.04]
       python3 gf180/tapeout/pex/afe_dcpath.py step [--dc cur sym]
       python3 gf180/tapeout/pex/afe_dcpath.py static [--dc cur sym] [--levels ...]
       python3 gf180/tapeout/pex/afe_dcpath.py sine [--dc cur sym] [--div 256] [--fast 1]
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
SYM = """XSCP3 INP CIB2 SCP2 AVSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XSCP4 SCP2 CIA2 ONI AVSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XCSCP2 SCP2 AVSS cap_mim_2f0ff c_length=5u c_width=5u
XSCN3 INN CIB2 SCN2 AVSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XSCN4 SCN2 CIA2 OPI AVSS nfet_03v3 W=0.5u L=0.28u nf=1 m=1
XCSCN2 SCN2 AVSS cap_mim_2f0ff c_length=5u c_width=5u
"""
C_SC = 54.52e-15


def first_edge(t0):
    """First CHOP rising edge (start of phase A in the bench) at or after t0."""
    return TCH / 2 + TCH * np.ceil((t0 - TCH / 2) / TCH - 1e-9)


def dut_extra(dc, fast=1.0):
    extra = SYM if dc == "sym" else ""
    if fast != 1.0:
        c = f"{(fast - 1) * C_SC:.4g}"
        extra += f"CSCPX SCP AVSS {c}\nCSCNX SCN AVSS {c}\n"
        extra += f"CSCPX2 SCP2 AVSS {c}\nCSCNX2 SCN2 AVSS {c}\n" if dc == "sym" else ""
    return extra


def deck(variant, dc, vin_mv=0.0, step_mv=None, tstop=200e-6, blank=p.BLANK, sine_mv=0.0, div=64, dac=None,
         fast=1.0):
    txt = p.tran_deck(variant, vin_mv, tstop=tstop, blank=blank, sine_mv=sine_mv, dac=dac)
    if step_mv is not None:
        txt, n = re.subn(r"^VSRC SRC 0 DC 0$", f"VSRC SRC 0 PWL(0 0 50u 0 50.1u {step_mv * 1e-3:.6g})", txt,
                         count=1, flags=re.M)
        assert n == 1
    if sine_mv and div != 64:
        txt, n = re.subn(r"SIN\((\S+) (\S+) 2000 ", rf"SIN(\1 \2 {p.FCH / div:g} ", txt)
        assert n == 1
    extra = dut_extra(dc, fast)
    assert txt.count(".ends afe_top") == 1
    return txt.replace(".ends afe_top", extra + ".ends afe_top")


def load(d):
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    return x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7]     # t, OUTP-OUTN, OPI-ONI, CDA, CDB


def periods(t, vo, cda, cdb, t0, t1):
    """Per chopper period from the first phase-A edge at or after t0: held level in phase A
    and phase B, the period average, and the average over each of the 8 ADC clocks."""
    q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
    e0 = first_edge(t0)
    rows, clk = [], []
    for k in range(int((t1 - e0) / TCH + 1e-9)):
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
    p.run(d, deck(variant, "cur", vin, blank=15 * p.MCLK, dac=(vin, 1)))
    t, vo, va, cda, cdb = load(d)
    r, clk = periods(t, vo, cda, cdb, 100e-6, 200e-6)
    return vin, r[:, 3].mean(), r[:, 1].mean(), r[:, 2].mean(), clk.mean(0), np.abs(va[t >= 100e-6]).max()


def static_one(variant, dc, v):
    d = job_dir(f"static_{variant}_{dc}_{v:+g}mV")
    p.run(d, deck(variant, dc, v if dc == "cur" else 0.0, step_mv=v if dc == "sym" else None))
    t, vo, va, cda, cdb = load(d)
    r, _ = periods(t, vo, cda, cdb, 100e-6, 200e-6)
    return dc, v, r[:, 3].mean(), r[:, 1].mean(), r[:, 2].mean()


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
    ap.add_argument("--dc", nargs="+", default=["cur", "sym"], choices=["cur", "sym"])
    ap.add_argument("--vin", nargs="+", type=float, default=[29.735, 30.04])
    ap.add_argument("--levels", nargs="+", type=float,
                    default=[-0.943, -0.707, -0.471, -0.236, 0.236, 0.471, 0.707, 0.943])
    ap.add_argument("--div", type=int, default=256)
    ap.add_argument("--fft0", type=float, default=2e-3)
    ap.add_argument("--fast", type=float, default=1.0)
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
        def one(dc):
            d = job_dir(f"step_{v}_{dc}")
            p.run(d, deck(v, dc, step_mv=0.5, tstop=1.5e-3))
            t, vo, va, cda, cdb = load(d)
            return dc, periods(t, vo, cda, cdb, 50e-6, 1.5e-3)[0]
        with ThreadPoolExecutor(len(a.dc)) as ex:
            for dc, r in ex.map(one, a.dc):
                print(f"## step {v} {dc}: t (us), phase A / B held (mV), period average (mV)")
                for k in list(range(0, 12, 2)) + list(range(12, len(r), 16)) + [len(r) - 1]:
                    print(f"{r[k, 0] * 1e6:7.1f}  {r[k, 1] * 1e3:8.2f}  {r[k, 2] * 1e3:8.2f}  {r[k, 3] * 1e3:9.3f}")
    elif a.what == "static":
        jobs = [(dc, x) for dc in a.dc for x in a.levels]
        with ThreadPoolExecutor(min(len(jobs), 8)) as ex:
            rows = list(ex.map(lambda j: static_one(v, *j), jobs))
        for dc in a.dc:
            rs = [r for r in rows if r[0] == dc]
            for r in rs:
                print(f"{v} {dc} {r[1]:+.3f} mV: average {r[2] * 1e3:+.5f} mV, phase A {r[3] * 1e3:+.3f}, "
                      f"phase B {r[4] * 1e3:+.3f} mV")
            g, hd, res = fit_hd([r[1] for r in rs], [r[2] for r in rs])
            print(f"{v} {dc}: gain {g:.3f}, full-scale HD2..HD5 " + " / ".join(f"{h:.1f}" for h in hd)
                  + f" dBc (fit residual {res * 1e6:.2f} uV)", flush=True)
    else:
        def one(dc):
            n, nper = a.div, 4
            tstop = a.fft0 + nper * n * TCH
            d = job_dir(f"sine_{v}_{dc}_{p.FCH / n:g}Hz" + (f"_fast{a.fast:g}" if a.fast != 1 else ""))
            p.run(d, deck(v, dc, tstop=tstop, sine_mv=FS_MV, div=n, fast=a.fast))
            t, vo, va, cda, cdb = load(d)
            r, _ = periods(t, vo, cda, cdb, a.fft0, tstop)
            per = r[:, 3]
            spec = np.abs(np.fft.rfft(per - per.mean())) / (len(per) / 2)
            h = [spec[nper * k] for k in range(1, 6)]
            return (f"| {v} {dc} | {p.FCH / n:g} | {a.fast:g} | {h[0] / (FS_MV * 1e-3):.2f} | "
                    + " | ".join(f"{20 * np.log10(x / h[0]):.1f}" for x in h[1:])
                    + f" | {np.abs(r[:, 1]).max() * 1e3:.1f} / {np.abs(r[:, 2]).max() * 1e3:.1f} | "
                    f"{np.abs(va[t >= a.fft0]).max() * 1e3:.1f} |")
        print("| DUT | f (Hz) | DC-path C x | gain | HD2 | HD3 | HD4 | HD5 (dBc) | phase A / B max (mV) | "
              "max abs(OPI-ONI) (mV) |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        with ThreadPoolExecutor(len(a.dc)) as ex:
            for s in ex.map(one, a.dc):
                print(s, flush=True)


if __name__ == "__main__":
    main()
