#!/usr/bin/env python3
"""Behavioral loop with different excess loop delays for DAC1 and DAC2 (tracker B3).

With the common-break drive DAC1 switches at e4 (DAC_CLK), one MCLK after SEL1/SEL2
change at e3, while DAC2 still switches with SEL2 at e3. Each clock is split into
three segments: [0, e2) old DAC1 and DAC2 levels, [e2, e1) old DAC1 and new DAC2,
[e1, T) both new. Loop as gf180/behavioral/ct2_dac2_options.py (stage 2 x10,
A1 2710, A2 3000, DWA, ideal elements), SNDR in 0.5..100 Hz.

Usage: python3 eld_mixed.py
"""
import os
import sys
import numpy as np
from numba import njit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "behavioral"))
import ct2_dac2_options as m  # noqa: E402


@njit(cache=True)
def sim3(ada, ba, adb, bb, adc, bc, u, thr):
    n = u.shape[0]
    out = np.empty(n, np.int64)
    x1 = 0.0
    x2 = 0.0
    yp = 0.0
    for i in range(n):
        a1 = ada[0, 0] * x1 + ada[0, 1] * x2 + ba[0, 0] * u[i] + (ba[0, 1] + ba[0, 2]) * yp
        a2 = ada[1, 0] * x1 + ada[1, 1] * x2 + ba[1, 0] * u[i] + (ba[1, 1] + ba[1, 2]) * yp
        c = 0
        for k in range(31):
            if x2 > thr[k]:
                c += 1
        out[i] = c
        y = 1.0 - 2.0 * (31 - c) / 31.0
        b1 = adb[0, 0] * a1 + adb[0, 1] * a2 + bb[0, 0] * u[i] + bb[0, 1] * yp + bb[0, 2] * y
        b2 = adb[1, 0] * a1 + adb[1, 1] * a2 + bb[1, 0] * u[i] + bb[1, 1] * yp + bb[1, 2] * y
        x1 = adc[0, 0] * b1 + adc[0, 1] * b2 + bc[0, 0] * u[i] + (bc[0, 1] + bc[0, 2]) * y
        x2 = adc[1, 0] * b1 + adc[1, 1] * b2 + bc[1, 0] * u[i] + (bc[1, 1] + bc[1, 2]) * y
        yp = y
        if abs(x2) > 10.0:
            out[i:] = -1
            break
    return out


def main():
    n = int(round((m.T_SETTLE + m.T_REC + m.T_TAIL) * m.FS))
    u = m.AIN * np.sin(2 * np.pi * m.F0 * (np.arange(n) + 0.5) * m.T)
    print("| DAC2 switches at | DAC1 switches at | SNDR 0.5-100 Hz (dB) |")
    print("|---|---|---|")
    for e2, e1 in ((3, 3), (3, 4), (4, 4), (3, 5)):
        ada, ba = m.discretize(10.0, 1.0, 2710, 3000, e2 / 32 * m.T)
        if e1 == e2:
            adb, bb = np.eye(2), np.zeros((2, 3))
        else:
            adb, bb = m.discretize(10.0, 1.0, 2710, 3000, (e1 - e2) / 32 * m.T)
        adc, bc = m.discretize(10.0, 1.0, 2710, 3000, (32 - e1) / 32 * m.T)
        c = sim3(ada, ba, adb, bb, adc, bc, u, m.THR)
        print(f"| e{e2} | e{e1} | {m.sndr(c):.1f} |")


if __name__ == "__main__":
    main()
