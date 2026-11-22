#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 3 (behavioral): does the ADC loop tolerate the start deck's ADC input (run A, ss:
a +0.64 V spike for ~90 ns after every output-chopper blanking window; run B, typical, as the control)?

The loop is adc_beh_mc.py's exact per-clock model (imported from gf180/tapeout/pex: DWA on both DACs, the dies of the
extracted ADC's block Monte Carlo and corners from runs/adc_mc_r11/adc_block_mc.json, ELD 0.22 of a clock, which
reproduces the transistor-level loop) with the integrator outputs clipped at the extracted OTA rails of
adc_overload_beh.py (O1 +-2.27 V, O2 +-3.25 V, figure 40). Only the input term changes: adc_beh_mc holds the input
constant over a clock; here the reconstructed waveform (wave.py) is integrated exactly through the loop filter on NF
sub-steps per clock, in the clock's two parts (before and after the DAC update), so a spike inside a clock acts with
its real timing. The 1 ms window is repeated NT times (1 ms = 128 chopper periods; the slow drift inside the window
jumps back at the seams, < 2 mV) so that the RTL's CIC (sinc^3, R 1024, bit-exact against cic_golden.py) gives valid
DATA. The OTAs' static nonlinearity (ota_static.py, figure 36) is left out: |O1| stays below 40 mV here.

Per variant (A actual, A clipped to +-0.484 V, A at its DC mean, B actual, B DC) and die (5 block corners, 6 resistor /
MIM corners, 30 Monte Carlo): peak |O1|, |O2| at the strobes and between them, the quantizer (clocks with O2 beyond
the outermost thresholds +-46.875 mV, codes 0 or 31), figure 40's 1-bit test (|O1| > 0.5 V), clip activity, DATA's
mean (input-referred with the die's own DAC1 full scale) against the input's mean, and the 1 ms boxcar means.
Also the trajectories of the ss die between the strobes (A actual and A dc, 24 clocks) for the figure.

Inputs: runs/ver07_r14/adc_spike/data/ (extract.py), runs/adc_mc_r11/adc_block_mc.json.
Outputs: runs/ver07_r14/adc_spike/beh_spike.json, beh_traj.npz.
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/beh_spike.py [--tiles 10] [--nf 1000]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from scipy.linalg import expm

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
PEX = os.path.join(REPO, "gf180", "tapeout", "pex")
OUT = os.path.join(PEX, "runs", "ver07_r14", "adc_spike")
os.environ["EEG_PEX_REV"] = "r12"          # the ADC of r13 is r12's (r13 changed only afe_top); blocks from adc_mc_r11
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "rtl", "model"))
sys.path.insert(0, PEX)
sys.path.insert(0, HERE)
import adc_beh_mc as B  # noqa: E402  (the loop model, the dies; it imports gf180/behavioral/ct2_dac2_options.py)
import cic_golden as G  # noqa: E402  (eeg_cic3, bit-exact)
from adc_overload_beh import X1MAX, X2MAX  # noqa: E402  (the extracted OTA rails, figure 40)
import wave as W  # noqa: E402  (this folder's wave.py, ahead of the standard library's module on sys.path)

assert hasattr(W, "Wave"), "adc_spike/wave.py expected"
m = B.m
T = m.T
ELD = 0.22
QTOP = float(m.THR[-1])                    # 46.875 mV: the outermost thresholds
SCALE = 31.0 * (1 << 18)                   # DATA at full scale (x = 2c - 31, sinc^3 gain 2^30, >> 12)
TRAJ = (600, 24)                           # the figure's trajectories: clocks 600..623 of the window, the ss die


def ct_matrix(d):
    """the continuous-time matrix [A | B] (states x1, x2; inputs u, y1, y2) of die d, as adc_beh_mc.discretize, and
    the first integrator's RIN C1"""
    rin, c1, vfs = m.RIN * d.k_rin, m.C1 * d.k_c * d.k_c1, d.vfs
    r21, rd2, c2 = m.R21_0 / B.S2 * d.k_r, m.RD2_0 / B.S2 * d.k_rd2, m.C2_0 * B.S2 * d.k_c * d.k_c2
    rd1 = m.VREF * rin / vfs
    g1 = (1 / rin + 1 / rd1) / (d.a1 * c1)
    g2 = (1 / r21 + 1 / rd2) / (d.a2 * c2)
    mm = np.zeros((5, 5))
    mm[:2, :2] = [[-g1, 0.0], [1 / (r21 * c2), -g2]]
    mm[:2, 2:] = [[1 / (rin * c1), -m.VREF / (rd1 * c1), 0.0], [0.0, 0.0, -m.VREF / (rd2 * c2)]]
    return mm, rin * c1


def kernels(d, nf, j0):
    """the sub-step matrices of die d and the kernels that turn nf sub-step inputs into the state change over the two
    parts of a clock (exact for an input constant on each sub-step)"""
    mm, _ = ct_matrix(d)
    E = expm(mm * T / nf)
    Ah, Bh = E[:2, :2], E[:2, 2:]
    P = [np.eye(2)]
    for _ in range(nf):
        P.append(Ah @ P[-1])
    K0 = np.array([P[j0 - 1 - j] @ Bh[:, 0] for j in range(j0)])          # (j0, 2)
    K1 = np.array([P[nf - 1 - j] @ Bh[:, 0] for j in range(j0, nf)])      # (nf - j0, 2)
    return Ah, Bh, K0, K1


def cic_data(c):
    """eeg_cic3 on a code stream from its clear (as enob_sine.cic_data)"""
    x = 2 * c.astype(np.int64) - 31
    i1 = np.cumsum(x)
    i2 = np.concatenate(([0], np.cumsum(i1)[:-1]))
    i3 = np.concatenate(([0], np.cumsum(i2)[:-1]))
    y = i3[G.R - 1::G.R]
    for _ in range(3):
        y = np.diff(y, prepend=np.int64(0))
    q, r = y >> G.SH, y & ((1 << G.SH) - 1)
    half = 1 << (G.SH - 1)
    q = q + ((r > half) | ((r == half) & ((q & 1) == 1)))
    return np.clip(q, -(1 << (G.WO - 1)), (1 << (G.WO - 1)) - 1)


def check_cic(n=100_000):
    rng = np.random.default_rng(5)
    c = np.clip(np.round(15.5 + 14 * np.sin(np.arange(n) * 3e-4) + 2 * rng.standard_normal(n)), 0, 31).astype(np.int8)
    gold, _ = G.cic3_run(bytes(c.astype(np.uint8)))
    mine = cic_data(c)
    return len(gold) == len(mine) and all(int(d) == int(v) for (d, _), v in zip(gold, mine))


def loop(dies, v0, v1, clip=True, x_init=None, y_init=None):
    """adc_beh_mc.simulate with the input term replaced by the exact per-part contributions v0 (before the DAC
    update) and v1 (after it), shape (n, S, 2). Returns codes c (n, S), the state at every strobe X (n + 1, S, 2:
    X[0] is the start, 0 unless x_init = (x1, x2) is given; y_init: the DAC level held from before), the DAC levels
    during each clock (n, S, 4: y1, y2 before the update, y1, y2 after it), clip counts."""
    S, n = len(dies), v0.shape[0]
    co = [d.coeffs(ELD) for d in dies]
    ad, b, ad0, b0 = (np.array([c[i] for c in co]) for i in range(4))
    thr = np.array([d.thr for d in dies])
    w1, w2 = np.array([d.w1 for d in dies]), np.array([d.w2 for d in dies])
    e1, o1 = np.array([d.e1 for d in dies]), np.array([d.o1 for d in dies])
    cs1, cs2 = B.prefix(w1), B.prefix(w2)
    die = np.arange(S)
    J = np.arange(31)
    odd1 = bool(np.any(o1))
    x1, x2, y1p, y2p = np.zeros(S), np.zeros(S), np.zeros(S), np.zeros(S)
    if x_init is not None:
        x1[:], x2[:] = x_init[0], x_init[1]
    if y_init is not None:
        y1p[:], y2p[:] = y_init, y_init
    p = np.zeros(S, np.int64)
    prev = np.zeros((S, 31), bool)
    C = np.empty((n, S), np.int8)
    X = np.zeros((n + 1, S, 2))
    X[0, :, 0], X[0, :, 1] = x1, x2
    Y = np.zeros((n, S, 4))
    nclip = np.zeros(S, np.int64)
    for i in range(n):
        mx1 = ad0[:, 0, 0] * x1 + ad0[:, 0, 1] * x2 + v0[i, :, 0] + b0[:, 0, 1] * y1p + b0[:, 0, 2] * y2p
        mx2 = ad0[:, 1, 0] * x1 + ad0[:, 1, 1] * x2 + v0[i, :, 1] + b0[:, 1, 1] * y1p + b0[:, 1, 2] * y2p
        c = (x2[:, None] > thr).sum(1)
        C[i] = c
        k = 31 - c
        sel = (J - p[:, None]) % 31 < k[:, None]
        tog = sel != prev
        s1 = cs1[die, p, k]
        s2 = cs2[die, p, k]
        t1 = (e1 * tog).sum(1)
        if odd1:
            t1 = (np.where(tog, np.where(sel, o1, -o1), 0.0) + e1 * tog).sum(1)
        prev = sel
        p = (p + k) % 31
        y1 = 1.0 - 2.0 * s1 / 31.0 + t1 / 31.0
        y2 = 1.0 - 2.0 * s2 / 31.0
        x1 = ad[:, 0, 0] * mx1 + ad[:, 0, 1] * mx2 + v1[i, :, 0] + b[:, 0, 1] * y1 + b[:, 0, 2] * y2
        x2 = ad[:, 1, 0] * mx1 + ad[:, 1, 1] * mx2 + v1[i, :, 1] + b[:, 1, 1] * y1 + b[:, 1, 2] * y2
        if clip:
            hit = (np.abs(x1) > X1MAX) | (np.abs(x2) > X2MAX)
            nclip += hit
            np.clip(x1, -X1MAX, X1MAX, out=x1)
            np.clip(x2, -X2MAX, X2MAX, out=x2)
        Y[i, :, 0], Y[i, :, 1], Y[i, :, 2], Y[i, :, 3] = y1p, y2p, y1, y2
        X[i + 1, :, 0], X[i + 1, :, 1] = x1, x2
        y1p, y2p = y1, y2
    return C, X, Y, nclip


def run(w, tag, variant, dies, ntiles, nf, j0):
    n = ntiles * W.N_CLK
    h = T / nf
    s = w.t0 + np.arange(n) * T                                      # strobes (every 4th: a CHOP_OUT edge + 2 T)
    U = w.u(s[:, None] + (np.arange(nf)[None, :] + 0.5) * h, variant)  # (n, nf), periodic beyond the window
    u_mean = float(U[:W.N_CLK].mean())
    S = len(dies)
    v0, v1 = np.empty((n, S, 2)), np.empty((n, S, 2))
    fine = []
    for si, d in enumerate(dies):
        mm, _ = ct_matrix(d)
        ad, b, ad0, b0 = d.coeffs(ELD)
        e0 = expm(mm * j0 * h)
        assert np.allclose(e0[:2, :2], ad0, rtol=1e-9, atol=1e-12) and np.allclose(e0[:2, 2:], b0, rtol=1e-9, atol=1e-15)
        Ah, Bh, K0, K1 = kernels(d, nf, j0)
        v0[:, si, :] = U[:, :j0] @ K0
        v1[:, si, :] = U[:, j0:] @ K1
        fine.append((Ah, Bh))
    C, X, Y, nclip = loop(dies, v0, v1)
    # between the strobes: the trajectory on the nf sub-steps, all clocks and dies at once
    Ah = np.array([f[0] for f in fine])                                # (S, 2, 2)
    Bh = np.array([f[1] for f in fine])                                # (S, 2, 3)
    Z = X[:-1].copy()                                                  # (n, S, 2) at each clock's strobe
    zmax = np.abs(Z).copy()
    for j in range(nf):
        ya = Y[:, :, 0:2] if j < j0 else Y[:, :, 2:4]
        Z = (np.einsum("sij,nsj->nsi", Ah, Z) + U[:, j, None, None] * Bh[None, :, :, 0]
             + ya[:, :, 0, None] * Bh[None, :, :, 1] + ya[:, :, 1, None] * Bh[None, :, :, 2])
        np.maximum(zmax, np.abs(Z), out=zmax)
    cons = float(np.abs(Z - X[1:]).max())                              # the sub-steps end where the loop is
    a = W.N_CLK                                                        # statistics after the first window (from rest)
    vfs = np.array([d.vfs for d in dies])
    x1s, x2s = np.abs(X[a + 1:, :, 0]).max(0), np.abs(X[a + 1:, :, 1]).max(0)
    x1f, x2f = zmax[a:, :, 0].max(0), zmax[a:, :, 1].max(0)
    rail = ((C[a:] == 0) | (C[a:] == 31)).sum(0)
    over = (np.abs(X[a + 1:, :, 1]) > QTOP).sum(0)
    data = np.array([cic_data(C[:, k]) for k in range(S)])            # (S, ntiles)
    dv = data[:, 3:] * vfs[:, None] / SCALE                            # valid from the 3rd window's end on
    box = ((2.0 * C[a:].astype(float) - 31.0) / 31.0).reshape(ntiles - 1, W.N_CLK, S).mean(1) * vfs[None, :]
    out = []
    for k, d in enumerate(dies):
        out.append(dict(die=d.label, vfs_mv=float(vfs[k] * 1e3), tau1_us=float(ct_matrix(d)[1] * 1e6),
                        o1_peak_strobe_mv=float(x1s[k] * 1e3), o1_peak_mv=float(x1f[k] * 1e3),
                        o2_peak_strobe_mv=float(x2s[k] * 1e3), o2_peak_mv=float(x2f[k] * 1e3),
                        code_min=int(C[a:, k].min()), code_max=int(C[a:, k].max()), rail_codes=int(rail[k]),
                        o2_beyond_thresholds=int(over[k]), onebit=bool(x1f[k] > 0.5), clip_clocks=int(nclip[k]),
                        data_mean_mv=float(dv[k].mean() * 1e3), data_sd_uv=float(dv[k].std() * 1e6),
                        data_minus_input_uv=float((dv[k].mean() - u_mean) * 1e6),
                        box_mean_mv=float(box[:, k].mean() * 1e3), box_sd_uv=float(box[:, k].std() * 1e6)))
    return dict(tag=tag, variant=variant, input_mean_mv=u_mean * 1e3, input_max_mv=float(U.max() * 1e3),
                input_min_mv=float(U.min() * 1e3), substep_consistency_v=cons, ntiles=ntiles, nf=nf, eld=ELD,
                dies=out)


def traj(w, die, variant, n0, n, nf, j0):
    """O1, O2 of one die every 10 sub-steps for clocks n0..n0+n-1 of the window (the loop from rest at its start)"""
    s = w.t0 + np.arange(n0 + n) * T
    U = w.u(s[:, None] + (np.arange(nf)[None, :] + 0.5) * T / nf, variant)
    Ah, Bh, K0, K1 = kernels(die, nf, j0)
    C, X, Y, _ = loop([die], (U[:, :j0] @ K0)[:, None, :], (U[:, j0:] @ K1)[:, None, :])
    tt, z1, z2 = [], [], []
    for i in range(n0, n0 + n):
        Z = X[i, 0].copy()
        for q in range(nf):
            ya = Y[i, 0, 0:2] if q < j0 else Y[i, 0, 2:4]
            Z = Ah @ Z + U[i, q] * Bh[:, 0] + ya[0] * Bh[:, 1] + ya[1] * Bh[:, 2]
            if q % 10 == 9:
                tt.append((i - n0) * T + (q + 1) * T / nf)
                z1.append(Z[0])
                z2.append(Z[1])
    return np.array(tt), np.array(z1), np.array(z2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", type=int, default=10)
    ap.add_argument("--nf", type=int, default=1000)
    a = ap.parse_args()
    j0 = int(round(ELD * a.nf))
    assert abs(j0 - ELD * a.nf) < 1e-9
    assert check_cic(), "the vectorized CIC differs from cic_golden"
    waves = {tag: W.Wave(tag) for tag in "AB"}
    j = B.load_block()
    corners = B.corner_dies(j)
    mcd, _, _ = B.mc_dies(j)
    dies = corners + mcd
    print(f"{len(dies)} dies: {', '.join(d.label for d in dies[:len(corners)])}, {mcd[0].label}..{mcd[-1].label}")
    res = []
    for tag, variants in (("A", ("actual", "clip", "dc")), ("B", ("actual", "dc"))):
        for v in variants:
            t = time.time()
            r = run(waves[tag], tag, v, dies, a.tiles, a.nf, j0)
            res.append(r)
            print(f"\n{tag} {v}: input mean {r['input_mean_mv']:.4f} mV ({r['input_min_mv']:.1f} .. {r['input_max_mv']:.1f}), "
                  f"sub-step consistency {r['substep_consistency_v']:.2e} V ({time.time() - t:.0f} s)")
            for k in (0, 1):
                q = r["dies"][k]
                print(f"  {q['die'][:30]:30s} O1 {q['o1_peak_mv']:.1f} (strobes {q['o1_peak_strobe_mv']:.1f}) mV, O2 "
                      f"{q['o2_peak_mv']:.1f} (strobes {q['o2_peak_strobe_mv']:.1f}) mV, codes {q['code_min']}..{q['code_max']}, "
                      f"rail {q['rail_codes']}, clip {q['clip_clocks']}; DATA {q['data_mean_mv']:.4f} mV, DATA - input "
                      f"{q['data_minus_input_uv']:+.2f} uV")
            dd = r["dies"]
            print(f"  all {len(dd)} dies: O1 <= {max(q['o1_peak_mv'] for q in dd):.1f} mV, O2 <= "
                  f"{max(q['o2_peak_mv'] for q in dd):.1f} mV (strobes {max(q['o2_peak_strobe_mv'] for q in dd):.1f}), codes "
                  f"{min(q['code_min'] for q in dd)}..{max(q['code_max'] for q in dd)}, rail codes {sum(q['rail_codes'] for q in dd)}, "
                  f"beyond {sum(q['o2_beyond_thresholds'] for q in dd)}, clip {sum(q['clip_clocks'] for q in dd)}, 1-bit "
                  f"{sum(q['onebit'] for q in dd)}; DATA - input {min(q['data_minus_input_uv'] for q in dd):+.2f} .. "
                  f"{max(q['data_minus_input_uv'] for q in dd):+.2f} uV")
    os.makedirs(OUT, exist_ok=True)
    json.dump(dict(eld=ELD, x1max=X1MAX, x2max=X2MAX, qtop=QTOP, block=os.path.relpath(B.BLOCK, REPO), tiles=a.tiles,
                   nf=a.nf, results=res), open(os.path.join(OUT, "beh_spike.json"), "w"), indent=1)
    arrays = dict(n0=TRAJ[0], T=T, die=corners[1].label)
    for v in ("actual", "dc"):
        tt, z1, z2 = traj(waves["A"], corners[1], v, TRAJ[0], TRAJ[1], a.nf, j0)
        arrays.update({"t": tt, f"o1_{v}": z1, f"o2_{v}": z2})
    arrays["edges"] = np.array([(k - TRAJ[0]) * T for k in range(TRAJ[0], TRAJ[0] + TRAJ[1] + 1)
                                if (W.N_START + k) % 4 == 0])               # the CHOP_OUT edges (every 4th strobe)
    np.savez(os.path.join(OUT, "beh_traj.npz"), **arrays)
    print("\nwrote", os.path.join(OUT, "beh_spike.json"), "and beh_traj.npz")


if __name__ == "__main__":
    main()
