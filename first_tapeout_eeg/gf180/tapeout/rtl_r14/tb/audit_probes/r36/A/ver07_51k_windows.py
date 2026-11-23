"""Audit 36 A: what the first stored samples read on the VER-07 51k||47n deck (M 100, the correct code) if the coarse
search of requirements 5.4 step 7 runs with T_ELEC = 0. The ADC input (OUTP - OUTN) of the deck, after the last release
(AFE_RST falls 6.1221 ms), averaged with the sinc^3 weights of a stored window that starts at the ALIGN clear
(release + T_REC 0.25 ms + 0..1 ms), linear (no ADC compression), and clipped at +-0.484 V per sample (a crude bound of
the overload's compression), for the 1st, 2nd and 3rd stored samples (windows starting at clear, clear + 1, clear + 2 ms)."""
import json, os, sys
import numpy as np
import pandas as pd
d = sys.argv[1]
meta = json.load(open(os.path.join(d, "meta.json")))
cols = ["qo", "outp_adc", "outn_adc"]
keep = [0] + [2 * meta["vectors"].index(c) + 1 for c in cols]
x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)[keep].to_numpy()
t = x[:, 0]; vo = x[:, 2] - x[:, 3]; qo = x[:, 1]
t_rel = meta["afe_rst_again"][1]
FS_ = 0.484
FR = 1 / 1.024e6                                   # one modulator frame
R = 1024
# sinc^3 weights over 3R - 2 frames
b = np.ones(R); w = np.convolve(np.convolve(b, b), b); w = w / w.sum()
# per-frame mean of the ADC input from the exact integral qo (charge-like: mean = d qo / dt)
t_end = t[-1]
def frame_means(t0, n):
    e = t0 + FR * np.arange(n + 1)
    q = np.interp(e, t, qo)
    return np.diff(q) / FR
def frame_clip(t0, n):
    # crude: clip the instantaneous input at +-FS, then average per frame
    e = t0 + FR * np.arange(n + 1)
    out = np.empty(n)
    for i in range(n):
        a, b_ = np.searchsorted(t, [e[i], e[i + 1]])
        seg = np.clip(vo[a:b_ + 1], -FS_, FS_)
        out[i] = seg.mean() if len(seg) else np.nan
    return out
print(f"release {t_rel*1e3:.4f} ms, deck end {t_end*1e3:.3f} ms ({(t_end - t_rel)*1e3:.2f} ms after the release)")
# chopper-period means at a few points
for s in (0.25e-3, 0.5e-3, 1.0e-3, 1.5e-3, 2.0e-3, 2.5e-3, 3.0e-3, 4.0e-3, 6.0e-3, 7.5e-3):
    if t_rel + s + 64 * FR < t_end:
        m = frame_means(t_rel + s, 64).mean()
        print(f"  mean of the 64 frames from {s*1e3:.2f} ms after the release: {m*1e3:+8.1f} mV")
for clear_ms in (0.25, 0.5, 0.75, 1.0, 1.25):
    row = []
    for k in range(3):
        t0 = t_rel + clear_ms * 1e-3 + k * 1e-3
        n = 3 * R - 2
        if t0 + n * FR > t_end:
            row.append("   (deck ends)"); continue
        lin = (frame_means(t0, n) * w).sum()
        cl = (frame_clip(t0, n) * w).sum()
        row.append(f"{lin*1e3:+7.1f}/{cl*1e3:+7.1f}")
    print(f"clear {clear_ms:4.2f} ms after the release: samples 1..3 (linear / clipped, mV at the ADC input): " + "  ".join(row))
print("--- T_ELEC = 3 ms (SEQ-03's example) and later clears")
for clear_ms in (3.25, 3.75, 4.25, 5.25, 7.25, 9.25, 10.75):
    row = []
    for k in range(3):
        t0 = t_rel + clear_ms * 1e-3 + k * 1e-3
        n = 3 * R - 2
        if t0 + n * FR > t_end:
            row.append("   (deck ends)"); continue
        lin = (frame_means(t0, n) * w).sum()
        row.append(f"{lin*1e3:+7.1f}")
    print(f"clear {clear_ms:5.2f} ms after the release: samples 1..3 (linear, mV at the ADC input): " + "  ".join(row))
for s in (8e-3, 9e-3, 10e-3, 11e-3, 12e-3, 13e-3, 13.8e-3):
    if t_rel + s + 64 * FR < t_end:
        print(f"  mean of the 64 frames from {s*1e3:.2f} ms: {frame_means(t_rel + s, 64).mean()*1e3:+8.1f} mV")
