#!/usr/bin/env python3
"""VER-07 diagnostic (digital-control audit round 34, auditor A): CHOP1's edge, e16 of the frames at 0 mod 32 (the start
of chopper phase A), lies 1 MCLK after the forced 15-MCLK blanking ends, on the ss post-blanking spike of the ADC input
(+632 mV at MCLK 16 after each CHOP_OUT edge, figure 51). OTA1's commutation puts q = beta I + gamma v_o1 into C1 per
side (gf180_ota1_chopper_20261022.md: beta 3.45..3.79 ns at ss 85 C), with I the current OTA1 carries, here the spike's.

Two runs of deck_spike.py's ss deck with CHOP1's first edge moved (--chop1-td): onto the spike after the CHOP_OUT edge at
9.7994 us (+16 MCLK, xrun_A_actual_ss_30u_c1spike) and onto e16 of a frame without a CHOP_OUT edge (12.2408 us,
_c1ctrl), against the deck's own run (its only CHOP1 edge at 2.475 us, in the reset transient; after each moved edge
every run has CHOP1 low, as the reference). At each moved edge, the difference of the run's differential O1 and the
reference run's is fitted by a line before the edge (300 to 5 ns before; the frame's DAC update is 366 ns before) and
after it (30 to 500 ns after; the next update is 580 ns after; the first 20 ns are the commutation's own transient,
which returns), and the step between the two lines at the edge is the charge the commutation left in C1: q per side is
that differential step x C1 / 2 (C1 per side counted from the extracted netlist's MIM capacitors I1N-O1P at 2 fF/um^2,
typical; the ss MIM corner moves it by a few %). OTA1's current per side at the edge is C1 / 2 x dO1/dt of the
reference run (the first integrator's current). The DC error at the ADC input if every CHOP1 edge carried the same
charge (all of them sit on a spike of the same sign): 2 RIN x q x 2 f_ch (RIN 18.75 kOhm per side, the tracker's
note on the ADC of today), input-referred through the AFE's gain with the offset DAC on (286, the tracker's note).

Inputs: runs/ver07_r14/adc_spike/xrun_A_actual_ss_30u{,_c1spike,_c1ctrl}/ (raw.csv, meta.json).
Output: runs/ver07_r14/adc_spike/chop1_spike.json.
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/chop1_spike.py
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")
NAMES = ["sig", "o1p", "o1n", "i1p", "i1n", "o2p", "o2n", "i2p", "i2n", "norm1", "iavdd"]
RIN = 18750.0                     # per side (gf180_tapeout_tracker.md: the ADC of today, RIN 18.75 kOhm per side)
MCLK = 32.768e6
AFE_GAIN = 286.0                  # the AFE's chopper-mean gain with the offset DAC on (blanking 15 MCLK; the tracker)


def c1_from_netlist(run):
    """C1 per side: the MIM capacitors between I1N and O1P in the run's extracted ADC (2 fF/um^2, typical)."""
    import re
    area = 0.0
    for ln in open(os.path.join(OUT, run, "eeg_adc_pex.spice")):
        if " I1N O1P cap_mim_2f0ff " in ln:
            w = float(re.search(r"c_width=([0-9.]+)u", ln).group(1))
            l_ = float(re.search(r"c_length=([0-9.]+)u", ln).group(1))
            area += w * l_
    return area * 2e-15


def load(run):
    x = pd.read_csv(os.path.join(OUT, run, "raw.csv"), sep=r"\s+", header=None, engine="c").to_numpy()
    v = {n: x[:, 2 * i + 1] for i, n in enumerate(NAMES)}
    v["t"] = x[:, 0]
    v["o1"] = v["o1p"] - v["o1n"]
    v["vg1"] = v["i1p"] - v["i1n"]
    return v


def at(v, key, t):
    return np.interp(t, v["t"], v[key])


def main():
    ref = load("xrun_A_actual_ss_30u")
    C1 = c1_from_netlist("xrun_A_actual_ss_30u")
    res = {}
    for tag in ("c1spike", "c1ctrl"):
        run = f"xrun_A_actual_ss_30u_{tag}"
        meta = json.load(open(os.path.join(OUT, run, "meta.json")))
        te = meta["chop1_td"] + 0.25e-9                 # the PULSE midpoint (0.5 ns edges)
        v = load(run)

        def diff(t):
            return at(v, "o1", t) - at(ref, "o1", t)
        tb = te + np.linspace(-300e-9, -5e-9, 60)
        ta = te + np.linspace(30e-9, 500e-9, 95)
        pb = np.polyfit(tb - te, diff(tb), 1)
        pa = np.polyfit(ta - te, diff(ta), 1)
        step = pa[1] - pb[1]                            # V, differential, at the edge
        q_side = step * C1 / 2
        tt = np.linspace(te - 6e-9, te - 1e-9, 11)
        i_side = C1 / 2 * np.polyfit(tt, at(ref, "o1", tt), 1)[0]      # A per side into C1 just before the edge
        res[tag] = dict(edge_us=te * 1e6, sig_mv=at(ref, "sig", te) * 1e3, o1_mv=at(ref, "o1", te) * 1e3,
                        i_c1_ua_per_side=i_side * 1e6, o1_step_mv=step * 1e3,
                        fit_rms_uv=[float(np.std(diff(tb) - np.polyval(pb, tb - te)) * 1e6),
                                    float(np.std(diff(ta) - np.polyval(pa, ta - te)) * 1e6)],
                        slopes_mv_per_us=[pb[0] * 1e-3, pa[0] * 1e-3],
                        q_fc_per_side=q_side * 1e15, beta_eff_ns=-q_side / i_side * 1e9,
                        transient_10ns_mv=(diff(te + 10e-9) - np.polyval(pb, 10e-9)) * 1e3)
    dq = res["c1spike"]["q_fc_per_side"] - res["c1ctrl"]["q_fc_per_side"]
    out = dict(c1_pf_per_side=C1 * 1e12, rin_ohm_per_side=RIN, afe_gain=AFE_GAIN, runs=res, extra_q_fc_per_side=dq)
    for fch in (1e3, 2e3, 4e3, 8e3, 16e3):
        vdc = 2 * RIN * dq * 1e-15 * 2 * fch                        # V at the ADC input, if every edge alike
        out[f"dc_if_same_sign_{fch / 1e3:g}k"] = dict(adc_input_uv=vdc * 1e6, input_referred_nv=vdc / AFE_GAIN * 1e9)
    json.dump(out, open(os.path.join(OUT, "chop1_spike.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
