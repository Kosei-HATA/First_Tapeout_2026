#!/usr/bin/env python3
"""ADC input headroom (tracker B7, 10/24): the exact per-clock loop model of
gf180/tapeout/sim/quantizer/quantizer_spec.py (stage 2 scaled x10, A1 2710, A2 3000,
ELD 3/32, ideal DACs and comparators, quantizer range +-46.875 mV, DAC1 full scale
VREF x RIN/RD1 = 0.484 V) driven by the AFE output as the ADC sees it.

The input is the low-frequency content U(t) (a 32 Hz sine of amplitude ain plus a DC
offset dc, both as per-chopper-period averages, i.e. what the CIC sees) times the
per-ADC-clock shape w[k mod 8] of the AFE output (8 ADC clocks per 128 kHz chopper
period, the first one starting with phase A). The shapes come from the schematic
afe_top transients of gf180/tapeout/pex/afe_dcpath.py (average over each ADC clock /
per-period average):
  flat   1 (the average alone, as the headroom was budgeted so far)
  cur7   DC path as drawn, blanking 7 MCLK (residual, +0.5 mV): phase A carries about
         twice the average, phase B about zero
  cur15  DC path as drawn, offset DAC on (range 1), blanking 15 MCLK (residual, +30.04 mV)
  sym7   DC path with the phase-swapped branch (step, +0.5 mV, settled)

Prints the in-band SNDR (quantization only, 0.5-100 Hz), the peak input, peak |x1|
(stage-1 output) and |x2| (quantizer input), and the share of clocks at code 0 or 31.
Needs numba (as quantizer_spec.py).

Usage: python3 adc_headroom.py ain,dc,shape [...]    (V, V, name; e.g. 0.2786,0,cur7)
"""
import os
import sys

import numpy as np
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "behavioral"))
import ct2_dac2_options as m  # noqa: E402

ELD = 3 / 32
SHAPES = {
    "flat": [1.0] * 8,
    "cur7": [1.5134, 2.0277, 2.0277, 2.0268, 0.4041, 0.0001, 0.0001, 0.0001],
    "cur15": [1.0358, 2.0952, 2.0952, 2.0942, 0.6813, -0.0005, -0.0005, -0.0005],
    "sym7": [0.9587, 1.0139, 1.0139, 1.0134, 0.9588, 1.0139, 1.0139, 1.0134],
}


@njit(cache=True)
def simulate(ad, b, ad0, b0, u, thr):
    """Code c[n] (0..31, -1 after a runaway) and the peak |x1|, |x2|."""
    n = u.shape[0]
    out = np.empty(n, np.int64)
    x1 = 0.0
    x2 = 0.0
    yp = 0.0
    x1max = 0.0
    x2max = 0.0
    for i in range(n):
        mx1 = ad0[0, 0] * x1 + ad0[0, 1] * x2 + b0[0, 0] * u[i] + (b0[0, 1] + b0[0, 2]) * yp
        mx2 = ad0[1, 0] * x1 + ad0[1, 1] * x2 + b0[1, 0] * u[i] + (b0[1, 1] + b0[1, 2]) * yp
        c = 0
        for k in range(31):
            if x2 > thr[k]:
                c += 1
        out[i] = c
        y = (2.0 * c - 31.0) / 31.0
        x1 = ad[0, 0] * mx1 + ad[0, 1] * mx2 + b[0, 0] * u[i] + (b[0, 1] + b[0, 2]) * y
        x2 = ad[1, 0] * mx1 + ad[1, 1] * mx2 + b[1, 0] * u[i] + (b[1, 1] + b[1, 2]) * y
        yp = y
        if i > n // 20:
            x1max = max(x1max, abs(x1))
            x2max = max(x2max, abs(x2))
        if abs(x2) > 10.0:
            out[i:] = -1
            break
    return out, x1max, x2max


def run(ain, dc=0.0, shape="flat"):
    ad0, b0 = m.discretize(10.0, 1.0, 2710, 3000, ELD * m.T)
    ad, b = m.discretize(10.0, 1.0, 2710, 3000, (1 - ELD) * m.T)
    n = int(round((m.T_SETTLE + m.T_REC + m.T_TAIL) * m.FS))
    k = np.arange(n)
    u = (ain * np.sin(2 * np.pi * m.F0 * (k + 0.5) * m.T) + dc) * np.asarray(SHAPES[shape])[k % 8]
    c, x1, x2 = simulate(ad, b, ad0, b0, u, m.THR)
    sat = float(np.mean((c == 0) | (c == 31))) if (c >= 0).all() else float("nan")
    return m.sndr(c), x1, x2, sat, np.abs(u).max()


def main():
    print("| ain (V pk) | DC (mV) | shape | peak input (V) | SNDR (dB) | peak abs(x1) (V) | peak abs(x2) (mV) | codes 0/31 |")
    print("|---|---|---|---|---|---|---|---|")
    for arg in sys.argv[1:]:
        ain, dc, shape = arg.split(",")
        s, x1, x2, sat, up = run(float(ain), float(dc), shape)
        print(f"| {float(ain):.4f} | {float(dc) * 1e3:+.1f} | {shape} | {up:.3f} | {s:.1f} | {x1:.3f} | {x2 * 1e3:.1f} | "
              f"{sat * 100:.3f} % |", flush=True)


if __name__ == "__main__":
    main()
