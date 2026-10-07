#!/usr/bin/env python3
"""Quick health check for sdm3_mb debug runs (small CSVs, in-memory).
Reports per-TH transition counts, per-cycle code range (PH2 plateau
majority vote), and (DWA) PTRS/PTRM coverage.
Usage: check_mb_debug.py <csv> [--dwa] [--fs 512000]"""
import numpy as np, sys

path = sys.argv[1]
dwa = "--dwa" in sys.argv
fs = 512000.0
Ts = 1.0/fs
d = np.loadtxt(path)
t = d[:, 0]
bits = [d[:, 3+2*j] for j in range(15)]
print(f"file={path}  rows={len(t)}  t=[{t[0]:.6f},{t[-1]:.6f}]")
for j, b in enumerate(bits):
    h = b > 0.9
    print(f"  TH{j:2d}: transitions={int(np.sum(h[1:]!=h[:-1])):5d}  "
          f"min={b.min():.2f} max={b.max():.2f}")
# per-cycle code via plateau majority vote (ph in [0.57,0.94])
k = (t/Ts).astype(int)
ph = (t - k*Ts)/Ts
m = (ph >= 0.57) & (ph <= 0.94)
ks = np.unique(k[m])
codes = np.zeros(len(ks))
for j, b in enumerate(bits):
    for i, kk in enumerate(ks):
        sel = m & (k == kk)
        codes[i] += 1.0 if np.mean(b[sel] > 0.9) > 0.5 else 0.0
print(f"  codes: n={len(codes)} min={codes.min():.0f} max={codes.max():.0f} "
      f"mean={codes.mean():.2f}")
csum = d[:, 3+2*15]
print(f"  CSUM: min={csum.min():.3f} max={csum.max():.3f}")
if dwa:
    ptrs = d[:, 3+2*16]
    ptrm = d[:, 3+2*17]
    pu = np.unique(np.round(ptrs, 1))
    print(f"  PTRS: min={ptrs.min():.3f} max={ptrs.max():.3f} "
          f"distinct(0.1)={len(pu)} -> {pu[:20]}")
    print(f"  PTRM: min={ptrm.min():.3f} max={ptrm.max():.3f}")
o2p = d[:, -3]; o2n = d[:, -1]
print(f"  O2D: min={(o2p-o2n).min()*1e3:.1f} mV max={(o2p-o2n).max()*1e3:.1f} mV")
