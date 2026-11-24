# a40_ovl_onset.py with the RTL's excess loop delay (3/32 of a frame: DAC_LOAD_CYCLE 2) as adc_beh_mc.py applies it
import sys, types, os
stub = types.ModuleType("numba")
stub.njit = lambda *a, **k: a[0] if len(a) == 1 and callable(a[0]) and not k else (lambda f: f)
sys.modules["numba"] = stub
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gf180", "behavioral"))
import numpy as np
import ct2_dac2_options as m
ad0, b0 = m.discretize(tseg=3 / 32 * m.T)
ad, b = m.discretize(tseg=29 / 32 * m.T)

def ovl(c):
    ext = ((c == 0) | (c == 31)).astype(int)
    cs = np.concatenate([[0], np.cumsum(ext)])
    n = np.arange(len(c))
    cnt = cs[n + 1] - cs[np.maximum(n + 1 - 32, 0)]
    now = cnt >= 4
    return now.mean(), ((ext == 1) & now).mean(), ext.mean()

N = 1 << 16
t = np.arange(N) / m.FS
for v in (0.40, 0.42, 0.43, 0.44, 0.45, 0.46):
    c, _, _ = m.simulate(ad, b, np.full(N, v), m.THR, 0.0, 0.0, 0.0, 1, ad0=ad0, b0=b0)
    if (c < 0).any():
        print("DC %.2f V: runaway" % v); continue
    a, h, e = ovl(c[1000:])
    print("ELD 3/32, DC %.2f V: OVL_NOW %5.1f %%, hits %5.1f %%, extreme codes %5.1f %%" % (v, 100 * a, 100 * h, 100 * e))
for off, amp in ((0.28, 0.20), (0.28, 0.15), (0.20, 0.20), (0.0, 0.44)):
    u = off + amp * np.sin(2 * np.pi * 40.0 * t)
    c, _, _ = m.simulate(ad, b, u, m.THR, 0.0, 0.0, 0.0, 1, ad0=ad0, b0=b0)
    if (c < 0).any():
        print("offset %.2f + %.2f V pk: runaway" % (off, amp)); continue
    a, h, e = ovl(c[1000:])
    print("ELD 3/32, offset %.2f + %.2f V pk (peak %.2f V): OVL_NOW %5.1f %%, hits %5.2f %%" % (off, amp, off + amp, 100 * a, 100 * h))
# DATA is still the input there (the mean of the codes as an input voltage), with the RTL's loop delay
fs_in = m.VREF * m.RIN / m.RD1
for v in (0.44, 0.46, 0.48):
    c, _, _ = m.simulate(ad, b, np.full(N, v), m.THR, 0.0, 0.0, 0.0, 1, ad0=ad0, b0=b0)
    ok = c[1000:]
    print("ELD 3/32, DC %.2f V: runaway %s, mean of the codes as an input %.4f V"
          % (v, bool((c < 0).any()), np.mean(2 * ok[ok >= 0] - 31) / 31 * fs_in))
