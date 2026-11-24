# Audit 40 A: what the ADC's DATA says about an input beyond its range (step 7's coarse sign rule, criterion "a
# reading beyond about one M step"; one 51-kOhm step is 0.86-0.88 V at the ADC input, the range +-0.484 V).
# The behavioral loop of gf180/behavioral/ct2_dac2_options.py (linear integrators, no rails; the RTL's excess loop
# delay 3/32 is left out here: zero ELD): a DC input held for 3,072 frames (three CIC windows); per input the mean
# code, the share of extreme codes (0 or 31) and the frame at which the linear loop runs away (|x2| > 10 V: the real
# integrators would sit at their rails, the codes at the extremes).
import sys, types, os
stub = types.ModuleType("numba")
stub.njit = lambda *a, **k: a[0] if len(a) == 1 and callable(a[0]) and not k else (lambda f: f)
sys.modules["numba"] = stub
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gf180", "behavioral"))
import numpy as np
import ct2_dac2_options as m
ad, b = m.discretize()
fs_in = m.VREF * m.RIN / m.RD1
print("DAC1 full scale at the ADC input: %.4f V" % fs_in)
for v in (0.30, 0.45, 0.48, 0.49, 0.51, 0.52, 0.86, 1.20):
    u = np.full(3072, v)
    c, x1m, x2m = m.simulate(ad, b, u, m.THR, 0.0, 0.0, 0.0, 1)
    ok = c[c >= 0]
    run = int(np.argmax(c < 0)) if (c < 0).any() else None
    ext = np.mean((ok == 31) | (ok == 0)) if len(ok) else float("nan")
    mean_y = np.mean(2 * ok - 31) / 31 * fs_in if len(ok) else float("nan")
    print("DC %.2f V: frames before runaway %s, extreme codes %.1f %%, mean of the codes as an input %.4f V"
          % (v, run if run is not None else "none (3072)", 100 * ext, mean_y))
# the same with the RTL's excess loop delay (3/32 of a frame)
ad0, b0 = m.discretize(tseg=3 / 32 * m.T)
ad2, b2 = m.discretize(tseg=29 / 32 * m.T)
for v in (0.49, 0.51, 0.52, 0.86, 1.20):
    c, _, _ = m.simulate(ad2, b2, np.full(3072, v), m.THR, 0.0, 0.0, 0.0, 1, ad0=ad0, b0=b0)
    ok = c[c >= 0]
    run = int(np.argmax(c < 0)) if (c < 0).any() else None
    print("ELD 3/32, DC %.2f V: frames before runaway %s, extreme codes %.1f %%"
          % (v, run if run is not None else "none (3072)", 100 * np.mean((ok == 31) | (ok == 0))))
