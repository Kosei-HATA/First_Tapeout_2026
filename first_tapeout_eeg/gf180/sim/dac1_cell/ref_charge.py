#!/usr/bin/env python3
"""Charge that one DAC1 unit cell (dac1_cell.spice, TG-switched) draws from the
references per toggle, beyond its static current (tracker B6).

The cell is complementary: at every toggle one of its two resistor heads moves from
VRN to VRP and the other from VRP to VRN, so each reference sees one rising and one
falling head per toggle, whichever way D goes. The static current from VRP is
2 x 0.25 V / 300 k = 1.67 uA per cell, independent of D. Per toggle VRP delivers an
extra charge q_t (the rising head's capacitance, the TG channel and overlap charge)
and VRN takes about the same back. With DWA the number of toggles per frame depends
on the code (about 2 min(k, 31 - k) for a steady code k), so the references carry a
code-dependent current q_t N(k) fs on top of the constant one.

Outputs at ideal virtual grounds (VCM), D/DB through 1 kohm with 1 ns edges.

--arch steered: the steered cell (dac1s_cell, resistors tied to the references, NMOS
steer their current between the virtual grounds) for comparison.

Usage: python3 ref_charge.py [--corner typical] [--temp 27] [--arch switched|steered]
"""
import argparse
import importlib.util
import os
import numpy as np

# run_cell.py imports the DAC2 folder's run_cell.py under that name, so load this
# folder's copy under another one
_spec = importlib.util.spec_from_file_location(
    "dac1_run_cell", os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cell.py"))
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

T = rc.T
VCM = rc.VCM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--arch", choices=["switched", "steered"], default="switched")
    a = ap.parse_args()
    a.tol, a.ws, a.tr, a.skew, a.voff, a.rmis = "A", 1.0, 1.0, 0.0, 0.0, 0.0
    bits = [0] * 4 + [0, 1] * 16 + [0] * 4
    t0 = 2e-6
    tstop = t0 + len(bits) * T
    deck = rc.header(a, False, 1) + f"""
VOP OUTP 0 {VCM}
VON OUTN 0 {VCM}
VD DS 0 PWL({rc.dac2.pattern_pwl(bits, t0, a.tr * 1e-9)})
VDB DBS 0 PWL({rc.dac2.pattern_pwl(bits, t0, a.tr * 1e-9, invert=True)})
RD DS D 1k
RDB DBS DB 1k
{rc.cell_lines(a, 195.5e-6, 195.5e-6)}
.control
set noaskquit
tran 0.1n {tstop:.9e} 0 0.5n
wrdata tr.csv i(vrp) i(vrn) i(vdd)
quit
.endc
.end
"""
    d = rc.run(deck, f"refq_{a.arch}_{a.corner}_{a.temp:g}")
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, ip, inn, idd = x[:, 0], -x[:, 1], -x[:, 3], -x[:, 5]  # current out of each source

    def q(i, lo, hi):
        m = (t >= lo) & (t <= hi)
        return np.trapezoid(i[m], t[m])

    # static current: the frames before the toggles start, away from the first edge
    i_vrp = q(ip, t0 + 1.5 * T, t0 + 3.5 * T) / (2 * T)
    i_vrn = q(inn, t0 + 1.5 * T, t0 + 3.5 * T) / (2 * T)
    qp, qn = [], []
    for k in range(5, 4 + 32):
        te = t0 + k * T
        qp.append(q(ip, te - 0.2 * T, te + 0.8 * T) - i_vrp * T)
        qn.append(q(inn, te - 0.2 * T, te + 0.8 * T) - i_vrn * T)
    qp, qn = np.array(qp), np.array(qn)
    print(f"{a.arch}, {a.corner} {a.temp:g} C: static VRP {i_vrp * 1e6:.4f} uA, VRN {i_vrn * 1e6:.4f} uA per cell")
    print(f"  per toggle: VRP delivers {qp[0::2].mean() * 1e15:+.3f} fC (D 0->1) / {qp[1::2].mean() * 1e15:+.3f} fC "
          f"(D 1->0); VRN delivers {qn[0::2].mean() * 1e15:+.3f} / {qn[1::2].mean() * 1e15:+.3f} fC")


if __name__ == "__main__":
    main()
