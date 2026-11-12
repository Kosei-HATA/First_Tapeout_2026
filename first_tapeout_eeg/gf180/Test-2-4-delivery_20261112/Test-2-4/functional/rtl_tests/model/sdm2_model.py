"""Behavioral 2nd-order, 5-bit (31 comparators) sigma-delta modulator.

Stimulus generator for the digital testbenches: it produces the quantizer code
stream c[n] (0..31) that the digital block would see on TH[30:0].

Model (discrete time, CIFB with delaying integrators, NTF = (1 - z^-1)^2):
    v[n]    = Q(x2[n])                       (31 comparators)
    x1[n+1] = x1[n] + u[n] - v[n]
    x2[n+1] = x2[n] + x1[n] - 2 v[n]
Units: everything is in units of the CIC input x = 2c - 31, i.e. the quantizer
output levels are -31, -29, ..., 31 and comparator i (TH[i]) switches at
x = -30 + 2 i, so c = number of thresholds below x2 = popcount(TH).
The input u is a sine with a DC offset and a little Gaussian noise
(deterministic seed). The loop is stable without overload while |u| < 29.

This is only a code-stream generator. It is not a model of the CT loop.
"""

import argparse
import math

import numpy as np

FS_HZ = 1.024e6          # modulator rate
NCOMP = 31               # comparators (5-bit flash)


def _loop_py(u, codes, x1, x2):
    """Run the modulator over u; write codes; return the final state."""
    for i in range(u.shape[0]):
        # c = #{j in 0..30 : x2 > -30 + 2 j}
        c = math.ceil((x2 + 30.0) * 0.5)
        if c < 0:
            c = 0
        elif c > NCOMP:
            c = NCOMP
        v = 2.0 * c - 31.0
        codes[i] = c
        x1_new = x1 + u[i] - v
        x2 = x2 + x1 - 2.0 * v
        x1 = x1_new
    return x1, x2


try:  # numba is only an accelerator; the result does not depend on it
    from numba import njit
    _loop = njit(cache=False)(_loop_py)
except Exception:  # pragma: no cover
    _loop = _loop_py


def sdm2_codes(n, amp=0.85, freq_hz=37.0, dc=0.05, noise_rms=1e-3,
               phase=0.3, seed=20261022, chunk=1 << 20):
    """Return n codes (uint8, 0..31).

    amp, dc and noise_rms are relative to full scale (31 in x units).
    """
    rng = np.random.default_rng(seed)
    codes = np.empty(n, dtype=np.uint8)
    x1 = 0.0
    x2 = 0.0
    w = 2.0 * math.pi * freq_hz / FS_HZ
    for start in range(0, n, chunk):
        stop = min(n, start + chunk)
        t = np.arange(start, stop, dtype=np.float64)
        u = NCOMP * (amp * np.sin(w * t + phase) + dc)
        u += NCOMP * noise_rms * rng.standard_normal(stop - start)
        x1, x2 = _loop(u, codes[start:stop], x1, x2)
    return codes


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="output file (one byte per code)")
    ap.add_argument("-n", type=int, default=100000)
    ap.add_argument("--amp", type=float, default=0.85)
    ap.add_argument("--freq", type=float, default=37.0)
    ap.add_argument("--dc", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=20261022)
    a = ap.parse_args()
    codes = sdm2_codes(a.n, amp=a.amp, freq_hz=a.freq, dc=a.dc, seed=a.seed)
    codes.tofile(a.out)
    print(f"{a.out}: {a.n} codes, min {codes.min()}, max {codes.max()}, "
          f"mean x {2.0 * codes.mean() - 31.0:+.4f}")


if __name__ == "__main__":
    main()
