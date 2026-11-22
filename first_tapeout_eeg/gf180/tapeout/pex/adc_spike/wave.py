#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 2: the start deck's ADC input as a continuous waveform for the ADC models.

The deck wrote its signals linearized on a 100 ns grid, too coarse for the ~90 ns spike after each blanking window.
Its qo (integ of OUTP_ADC - OUTN_ADC on the raw time points) gives every interval's charge exactly, except at the grid
point next to each CHOP_OUT edge, where it is off by up to +-24 mV us (an interpolation artifact that cancels over the
next bin; check() shows it), so averaging boundaries are put at mid-phase. The chopper edges come every 3.90625 us
(128 MCLK), not a multiple of 100 ns, so the 100 ns samples fall on 16 phases (6.25 ns apart) relative to the edges:
overlaying the segments of one chopper phase (equivalent-time sampling) gives that phase's waveform at ~6 ns. The
window's waveform is then, per edge-centred segment k ([te_k - TE/2, te_k + TE/2)),

    u(t) = template_{k mod 2}(t - te_k) + off_k,

off_k such that the segment's integral equals qo's (keeps the slow drift and the exact mean). The step at the end of
blanking (CHOP_BLANK falls 457.76..458.26 ns after the CHOP_OUT PULSE start) is put at 458.3 -> 460.3 ns, the shape
after it from both phases' samples (sharper than the samples show: conservative for the transistor-level check).
The template is a PWL simplified to TOL, so the same corners drive ngspice (deck_spike.py).

Window: the last 1 ms of the runs, 1024 modulator clocks from strobe 1862 after t_reset (strobes at t_reset + n T,
every 4th on a CHOP_OUT edge, as eeg_clkgen: CMP_STROBE at frame cycle 0, chop_out edges at cycle 0 of every 4th
frame), = 128 chopper periods, so the window repeats seamlessly.
Variants: actual; clip (u limited to +-0.484 V, DAC1's full scale at the ADC input); dc (the window mean, constant).

Inputs: runs/ver07_r14/adc_spike/data/<tag>.npz, <tag>_meta.json (extract.py).
Outputs (run as a script): runs/ver07_r14/adc_spike/wave.json (the reconstruction's residuals against the deck's
samples and qo, the window means, the spike's numbers per phase), wave_templates.npz (per run and phase: the
overlaid samples and the template, for the figure).

Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/wave.py
       (as a module: Wave(tag).u(t, variant), Wave(tag).pwl(a, b, variant))
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")
T = 1 / 1.024e6                 # modulator clock (MCLK / 32)
TE = 4 * T                      # half chopper period (128 MCLK): CHOP_OUT edge spacing
MCLK = T / 32
VCLIP = 0.484                   # DAC1 full scale referred to the ADC input (V, differential)
TOL = 0.25e-3                   # PWL simplification tolerance (V)
N_START = 1862                  # window start: strobe index from t_reset, half a segment before the CHOP_OUT edge of
                                # strobe 1864 (= 4 * 466)
N_CLK = 1024                    # 1 ms = 1024 clocks = 256 segments = 128 chopper periods
TB0, TB1 = 458.3e-9, 460.3e-9   # the blanking window's end (after the CHOP_OUT PULSE start): the step, 2 ns
TB_SHAPE = 470e-9               # the step's shape from both phases' samples up to here


def load(tag):
    d = np.load(os.path.join(OUT, "data", f"{tag}.npz"))
    meta = json.load(open(os.path.join(OUT, "data", f"{tag}_meta.json")))
    return dict(t=d["t"], u=d["outp_adc"] - d["outn_adc"], qo=d["qo"]), meta


def simplify(x, y, tol):
    """Douglas-Peucker on a PWL: indices of the points kept (first and last always)."""
    keep = np.zeros(len(x), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(x) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        xi, yi = x[a + 1:b], y[a + 1:b]
        yl = y[a] + (y[b] - y[a]) * (xi - x[a]) / (x[b] - x[a])
        k = int(np.argmax(np.abs(yi - yl)))
        if abs(yi[k] - yl[k]) > tol:
            c = a + 1 + k
            keep[c] = True
            stack += [(a, c), (c, b)]
    return np.nonzero(keep)[0]


def pwl_mean(x, y, a, b):
    """mean of the PWL (x, y) over [a, b] (x covers it)"""
    xs = np.concatenate(([a], x[(x > a) & (x < b)], [b]))
    ys = np.interp(xs, x, y)
    return float(np.sum(0.5 * (ys[1:] + ys[:-1]) * np.diff(xs)) / (b - a))


class Wave:
    def __init__(self, tag, n_start=N_START, n_clk=N_CLK, tol=TOL):
        d, meta = load(tag)
        self.tag, self.meta = tag, meta
        self.tr = meta["t_reset"]
        self.t0 = self.tr + n_start * T                      # window start (2 clocks before a CHOP_OUT edge)
        self.t1 = self.t0 + n_clk * T
        assert self.t1 <= meta["tstop"] - 0.2e-6, "window beyond the run"
        assert self.t0 >= meta["afe_rst_again"][1] + 0.1e-3, "window starts before the last release"
        t, u, qo = d["t"], d["u"], d["qo"]
        self.k0 = int(round((self.t0 + TE / 2 - self.tr) / TE))   # first edge (segment centre)
        self.nk = int(round((self.t1 - self.t0) / TE))
        ks = self.k0 + np.arange(self.nk)
        te = self.tr + ks * TE
        assert abs(te[0] - TE / 2 - self.t0) < 1e-12
        Q = lambda x: np.interp(x, t, qo)                   # noqa: E731
        # segment means between mid-phase points (qo is clean there; next to an edge it is not, see check())
        self.mk = (Q(te + TE / 2) - Q(te - TE / 2)) / TE
        self.mean_qo = float((Q(self.t1) - Q(self.t0)) / (self.t1 - self.t0))
        self.tmpl, self.raw = {}, {}
        for p in (0, 1):
            tau, val = [], []
            sel = (ks % 2) == p
            ref = self.mk[sel].mean()
            for k, a, mk in zip(ks[sel], te[sel], self.mk[sel]):
                w = (t >= a - TE / 2) & (t < a + TE / 2)
                tau.append(t[w] - a)
                val.append(u[w] - mk + ref)                   # take the drift out
            tau, val = np.concatenate(tau), np.concatenate(val)
            o = np.argsort(tau, kind="stable")
            tau, val = tau[o], val[o]
            key = np.round(tau / 0.05e-9).astype(np.int64)     # merge samples at the same offset (0.05 ns)
            uk, inv = np.unique(key, return_inverse=True)
            x = np.bincount(inv, tau) / np.bincount(inv)
            y = np.bincount(inv, val) / np.bincount(inv)
            x = np.concatenate(([-TE / 2], x, [TE / 2]))       # flat to the segment's ends (mid-phase)
            y = np.concatenate(([y[0]], y, [y[-1]]))
            self.raw[p] = (x, y)
        self.samples = {p: self.raw[p] for p in (0, 1)}      # the overlaid samples, before the step is sharpened
        # the step at the end of the blanking window: each phase's samples are 12.5 ns apart, so the step would be
        # spread over 12.5 ns. Put it at TB0 -> TB1 (2 ns) instead, the shape just after it from both phases' samples
        # (6.25 ns apart), extrapolated back to TB1
        ox, oy = [], []
        for p in (0, 1):
            x, y = self.raw[p]
            s = (x > TB0) & (x < TB_SHAPE)
            ox += list(x[s])
            oy += list(y[s])
        o = np.argsort(ox)
        ox, oy = np.array(ox)[o], np.array(oy)[o]
        v1 = oy[0] - (ox[0] - TB1) * (oy[1] - oy[0]) / (ox[1] - ox[0])
        self.step = (float(TB0), float(TB1), float(v1), ox.tolist(), oy.tolist())
        for p in (0, 1):
            x, y = self.raw[p]
            pre = x <= TB0 - 1e-12
            post = x >= TB_SHAPE
            x = np.concatenate((x[pre], [TB0, TB1], ox, x[post]))
            y = np.concatenate((y[pre], [y[pre][-1], v1], oy, y[post]))
            self.raw[p] = (x, y)
            i = simplify(x, y, tol)
            xs, ys = x[i], y[i]
            self.tmpl[p] = (xs, ys, pwl_mean(xs, ys, -TE / 2, TE / 2))
        # per segment: offset so that the template's mean is the exact one
        self.off = np.array([self.mk[i] - self.tmpl[(k % 2)][2] for i, k in enumerate(ks)])
        self.ks, self.te = ks, te
        self.data = d

    def u(self, tq, variant="actual"):
        """the reconstructed ADC input at times tq (inside the window; outside, the window is repeated)"""
        tq = np.asarray(tq, float)
        L = self.t1 - self.t0
        tw = self.t0 + np.mod(tq - self.t0, L)               # periodic extension (1 ms = 128 chopper periods)
        i = np.clip(np.floor((tw - self.t0) / TE).astype(np.int64), 0, self.nk - 1)
        tau = tw - self.te[i]                                # in [-TE/2, TE/2)
        out = np.empty_like(tw)
        for p in (0, 1):
            w = (self.ks[i] % 2) == p
            xs, ys, _ = self.tmpl[p]
            out[w] = np.interp(tau[w], xs, ys) + self.off[i[w]]
        if variant == "clip":
            out = np.clip(out, -VCLIP, VCLIP)
        elif variant == "dc":
            out = np.full_like(out, self.mean_qo)
        elif variant != "actual":
            raise ValueError(variant)
        return out

    def pwl(self, a, b, variant="actual"):
        """(times, values) of the reconstructed waveform's PWL corners in [a, b] (exact for 'actual' and 'clip'
        up to the clip crossings, which are added)"""
        pts = []
        n0 = int(np.floor((a - self.t0) / TE)) - 1
        n1 = int(np.ceil((b - self.t0) / TE)) + 1
        for n in range(n0, n1 + 1):
            i = n % self.nk
            base = self.t0 + n * TE + TE / 2                 # the segment's edge
            xs, ys, _ = self.tmpl[self.ks[i] % 2]
            pts.append(np.stack([base + xs, ys + self.off[i]], 1))
        p = np.concatenate(pts)
        p = p[(p[:, 0] >= a) & (p[:, 0] <= b)]
        # the segments' end and start points coincide in time: keep the later (start of the next) only
        keep = np.ones(len(p), bool)
        keep[:-1] = np.diff(p[:, 0]) > 1e-15
        p = p[keep]
        if variant == "clip":
            x, y = p[:, 0], p[:, 1]
            xs, ys = [x[0]], [y[0]]
            for j in range(1, len(x)):
                for lim in (VCLIP, -VCLIP):
                    if (y[j - 1] - lim) * (y[j] - lim) < 0:      # crossing: add the crossing point
                        f = (lim - y[j - 1]) / (y[j] - y[j - 1])
                        xs.append(x[j - 1] + f * (x[j] - x[j - 1]))
                        ys.append(lim)
                xs.append(x[j])
                ys.append(y[j])
            p = np.stack([xs, np.clip(ys, -VCLIP, VCLIP)], 1)
        elif variant == "dc":
            p = np.array([[a, self.mean_qo], [b, self.mean_qo]])
        return p[:, 0], p[:, 1]

    def check(self):
        """residuals of the reconstruction against the deck's samples and qo's 100 ns charges, inside the window"""
        t, u, qo = self.data["t"], self.data["u"], self.data["qo"]
        w = (t >= self.t0) & (t <= self.t1 - 100e-9)
        ur = self.u(t[w])
        # 100 ns bins: exact integral of the reconstruction (fine sampling) against qo
        tb = t[w]
        fine = np.linspace(0, 100e-9, 201)
        mids = 0.5 * (fine[1:] + fine[:-1])
        ub = self.u(tb[:, None] + mids[None, :]).mean(1)
        qb = (qo[np.nonzero(w)[0] + 1] - qo[w]) / 100e-9
        k = np.floor((tb - self.tr) / TE + 0.5).astype(np.int64)
        tau = tb - (self.tr + k * TE)                        # bin start against the nearest edge
        clean = (~((tau > -100e-9) & (tau < 0.0)) & ~((tau >= 0.0) & (tau < 100e-9))
                 & ~((tau > -200e-9) & (tau <= -100e-9)))
        Q = lambda x: np.interp(x, t, qo)                   # noqa: E731
        f2 = np.linspace(-200e-9, 200e-9, 801)
        m2 = 0.5 * (f2[1:] + f2[:-1])
        te = self.tr + self.ks[1:-1] * TE
        rec2 = self.u(te[:, None] + m2[None, :]).mean(1) * 400e-9
        q2 = Q(te + 200e-9) - Q(te - 200e-9)
        return dict(samples_rms_mv=float(np.sqrt(np.mean((ur - u[w]) ** 2)) * 1e3),
                    samples_max_mv=float(np.abs(ur - u[w]).max() * 1e3),
                    bins_rms_mv=float(np.sqrt(np.mean((ub - qb)[clean] ** 2)) * 1e3),
                    bins_max_mv=float(np.abs(ub - qb)[clean].max() * 1e3),
                    bins_next_to_edges_max_mv=float(np.abs(ub - qb)[~clean].max() * 1e3),
                    edge400ns_rms_mvus=float(np.sqrt(np.mean((rec2 - q2) ** 2)) * 1e9),
                    edge400ns_max_mvus=float(np.abs(rec2 - q2).max() * 1e9),
                    n_points=(len(self.tmpl[0][0]), len(self.tmpl[1][0])),
                    mean_qo_mv=self.mean_qo * 1e3, off_sd_mv=float(self.off.std() * 1e3),
                    off_span_mv=float(np.ptp(self.off) * 1e3))

    def spike(self):
        """per chopper phase: the level before the step, the peak, the time above +VCLIP, the area above the
        pre-step level from the step to 900 ns, the area above +VCLIP (template, drift taken out)"""
        out = []
        f = np.linspace(-TE / 2, TE / 2, 400001)
        for p in (0, 1):
            xs, ys, _ = self.tmpl[p]
            u = np.interp(f, xs, ys)
            pre = float(np.interp(TB0 - 1e-9, xs, ys))
            sp = (f >= TB0) & (f <= 900e-9)
            out.append(dict(phase=p, pre_step_mv=pre * 1e3, peak_mv=float(u.max() * 1e3),
                            above_fs_ns=float((u > VCLIP).sum() * (f[1] - f[0]) * 1e9),
                            area_above_pre_mvus=float(np.trapz(u[sp] - pre, f[sp]) * 1e9),
                            area_above_fs_mvus=float(np.trapz(np.clip(u - VCLIP, 0, None), f) * 1e9)))
        return out


def main():
    res, arrays = {}, {}
    for tag in "AB":
        w = Wave(tag)
        c = w.check()
        tq = np.linspace(w.t0, w.t1, 2_000_001)[:-1] + 0.25e-9
        ua, uc = w.u(tq), w.u(tq, "clip")
        mk = w.mk.reshape(-1, 2).mean(1)                    # chopper-period means (two segments)
        res[tag] = dict(run=w.meta.get("corner"), window_ms=(w.t0 * 1e3, w.t1 * 1e3), check=c,
                        mean_actual_mv=float(ua.mean() * 1e3), mean_qo_mv=w.mean_qo * 1e3,
                        mean_clip_mv=float(uc.mean() * 1e3), max_mv=float(ua.max() * 1e3), min_mv=float(ua.min() * 1e3),
                        chopper_means_mv=dict(first=float(mk[0] * 1e3), last=float(mk[-1] * 1e3),
                                              min=float(mk.min() * 1e3), max=float(mk.max() * 1e3)),
                        above_fs_ns_per_segment=float((ua > VCLIP).mean() * TE * 1e9),
                        above_fs_mvus_per_segment=float(np.clip(ua - VCLIP, 0, None).mean() * TE * 1e9),
                        step=dict(t0_ns=w.step[0] * 1e9, t1_ns=w.step[1] * 1e9, value_mv=w.step[2] * 1e3),
                        spike=w.spike())
        for p in (0, 1):
            arrays[f"{tag}{p}_samples_t"], arrays[f"{tag}{p}_samples_u"] = w.samples[p]
            arrays[f"{tag}{p}_tmpl_t"], arrays[f"{tag}{p}_tmpl_u"] = w.tmpl[p][0], w.tmpl[p][1]
        r = res[tag]
        print(f"{tag} ({r['run']}): window {r['window_ms'][0]:.6f}..{r['window_ms'][1]:.6f} ms, mean {r['mean_actual_mv']:.3f} "
              f"mV (qo {r['mean_qo_mv']:.3f}), clip {r['mean_clip_mv']:.3f} mV, {r['min_mv']:.1f}..{r['max_mv']:.1f} mV; "
              f"chopper-period means {r['chopper_means_mv']['first']:.2f} .. {r['chopper_means_mv']['last']:.2f} mV; "
              f"above +{VCLIP} V {r['above_fs_ns_per_segment']:.1f} ns, {r['above_fs_mvus_per_segment']:.2f} mV us per segment")
        print("   check:", json.dumps(c))
        for s in r["spike"]:
            print(f"   phase {s['phase']}: before the step {s['pre_step_mv']:.1f} mV, peak {s['peak_mv']:.1f} mV, above FS "
                  f"{s['above_fs_ns']:.1f} ns; area above the pre-step level {s['area_above_pre_mvus']:.1f} mV us, above FS "
                  f"{s['area_above_fs_mvus']:.2f} mV us")
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "wave.json"), "w"), indent=1)
    np.savez(os.path.join(OUT, "wave_templates.npz"), **arrays)
    print("wrote", os.path.join(OUT, "wave.json"), "and wave_templates.npz")


if __name__ == "__main__":
    main()
