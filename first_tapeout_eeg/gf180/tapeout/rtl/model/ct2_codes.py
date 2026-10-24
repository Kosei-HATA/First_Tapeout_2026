"""Code streams from the CT 2nd-order 5-bit sigma-delta behavioral loop, for the
end-to-end digital test (tb/tb_e2e.sv, run_e2e.sh).

The loop is the one of gf180/behavioral/ct2_dac2_options.py with the DAC timing of
gf180/tapeout/sim/dac1/eld_mixed.py: stage 2 scaled x10 (s = 10), finite OTA gains
A1 = 2710 and A2 = 3000, DAC2 switching at e3 (SEL2 update) and DAC1 at e4
(DAC_CLK, common-break drive), 31 thresholds of 3.125 mV on O2, VREF 0.5 V,
fs = 1.024 MHz. Each clock is solved exactly in three segments with the matrix
exponential of ct2_dac2_options.discretize(): [0, e3) old DAC levels, [e3, e4) new
DAC2 and old DAC1, [e4, T) both new; the decision is taken from O2 at the start of
the clock (the comparator strobe e0). The DAC elements are ideal and there is no
device noise (quantization only), so the stream is a stimulus for the digital
block, not a performance prediction.

The input is the differential ADC input in volts: a DC offset plus tones, held over
each clock (sampled at the clock centre, as in ct2_dac2_options.run_case).
0.279 V pk is the full scale of the chip (electrode 0.943 mV pk, tracker A1).

Usage:
  ct2_codes.py OUT.codes --seconds S [--dc V] [--tone F:A[:PHASE]] ... [--gold OUT.gold]
Writes one byte per frame (c = 0..31). With --gold, also writes the valid outputs of
the bit-exact CIC model (cic_golden.cic3_run on the stream from index 0), one 24-bit
hex value per line, as tb_e2e expects.
"""

import argparse
import bisect
import math
import os
import sys
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "behavioral"))

try:  # numba is only an accelerator of ct2_dac2_options.simulate (not used here)
    import numba  # noqa: F401
except ImportError:  # pragma: no cover
    def _njit(*args, **kw):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f
    sys.modules["numba"] = types.SimpleNamespace(njit=_njit)

import ct2_dac2_options as m  # noqa: E402

sys.path.insert(0, HERE)
import cic_golden as g  # noqa: E402

S_STAGE2 = 10.0          # stage 2 x10 (C2 19.5 pF, R21 100 k)
A1, A2 = 2710.0, 3000.0  # OTA DC gains (A1 includes the R21 load)
E_DAC2, E_DAC1 = 3, 4    # MCLK edges (of 32 per clock) where DAC2 / DAC1 switch


def segment(t):
    ad, b = m.discretize(S_STAGE2, 1.0, A1, A2, t)
    return [float(v) for v in ad.ravel()] + [float(v) for v in b.ravel()]


def ct2_codes(n, dc=0.0, tones=(), progress=True):
    """Return n codes (bytearray, 0..31) and the peak |O1|, |O2| (V)."""
    t = m.T
    sa = segment(E_DAC2 / 32 * t)
    sb = segment((E_DAC1 - E_DAC2) / 32 * t)
    sc = segment((32 - E_DAC1) / 32 * t)
    # ad = [a00 a01 a10 a11], b = [b00 b01 b02 b10 b11 b12] (columns u, y1 = DAC1, y2 = DAC2)
    a00, a01, a10, a11, ba00, ba01, ba02, ba10, ba11, ba12 = sa
    b00, b01, b10, b11, bb00, bb01, bb02, bb10, bb11, bb12 = sb
    c00, c01, c10, c11, bc00, bc01, bc02, bc10, bc11, bc12 = sc
    ka1 = ba01 + ba02            # segment a: both DACs at the old level
    ka2 = ba11 + ba12
    kc1 = bc01 + bc02            # segment c: both at the new level
    kc2 = bc11 + bc12
    thr = [float(v) for v in m.THR]

    codes = bytearray(n)
    x1 = x2 = 0.0
    yp = 1.0 - 2.0 * 16 / 31.0   # reset state of SEL: k = 16 elements at VP
    x1max = x2max = 0.0
    chunk = 1 << 20
    t0 = time.time()
    for start in range(0, n, chunk):
        stop = min(n, start + chunk)
        tt = (np.arange(start, stop, dtype=np.float64) + 0.5) * t
        u_arr = np.full(stop - start, float(dc))
        for f, a, ph in tones:
            u_arr += a * np.sin(2.0 * math.pi * f * tt + ph)
        for i, u in zip(range(start, stop), u_arr.tolist()):
            p1 = a00 * x1 + a01 * x2 + ba00 * u + ka1 * yp
            p2 = a10 * x1 + a11 * x2 + ba10 * u + ka2 * yp
            c = bisect.bisect_left(thr, x2)      # number of thresholds below O2
            codes[i] = c
            y = (2.0 * c - 31.0) / 31.0          # 1 - 2 k / 31 with k = 31 - c
            q1 = b00 * p1 + b01 * p2 + bb00 * u + bb01 * yp + bb02 * y
            q2 = b10 * p1 + b11 * p2 + bb10 * u + bb11 * yp + bb12 * y
            x1 = c00 * q1 + c01 * q2 + bc00 * u + kc1 * y
            x2 = c10 * q1 + c11 * q2 + bc10 * u + kc2 * y
            yp = y
            if abs(x2) > x2max:
                x2max = abs(x2)
                if x2max > 10.0:
                    raise SystemExit(f"loop runaway at frame {i}")
            if abs(x1) > x1max:
                x1max = abs(x1)
        if progress:
            print(f"  {stop}/{n} frames, {time.time() - t0:.0f} s", file=sys.stderr, flush=True)
    return codes, x1max, x2max


def parse_tone(s):
    parts = [float(v) for v in s.split(":")]
    if len(parts) == 2:
        parts.append(0.0)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("tone is F:A[:PHASE]")
    return tuple(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, required=True)
    ap.add_argument("--dc", type=float, default=0.0)
    ap.add_argument("--tone", type=parse_tone, action="append", default=[])
    ap.add_argument("--gold")
    a = ap.parse_args()

    n = int(round(a.seconds * m.FS))
    codes, x1max, x2max = ct2_codes(n, a.dc, a.tone)
    with open(a.out, "wb") as f:
        f.write(codes)
    arr = np.frombuffer(bytes(codes), dtype=np.uint8)
    hist = np.bincount(arr, minlength=32)
    print(f"{a.out}: {n} frames ({a.seconds} s), dc {a.dc} V, tones "
          f"{', '.join(f'{f:g} Hz {amp:g} V' for f, amp, _ in a.tone) or 'none'}; "
          f"codes {arr.min()}..{arr.max()}, mean x {2.0 * arr.mean() - 31.0:+.4f}, "
          f"codes 0/31 used {hist[0]}/{hist[31]} times, peak |O1| {x1max:.4f} V, |O2| {x2max:.4f} V")
    if a.gold:
        outs, st = g.cic3_run(bytes(codes))
        valid = [d for d, v in outs if v]
        with open(a.gold, "w") as f:
            for d in valid:
                f.write(f"{d & 0xFFFFFF:06x}\n")
        print(f"{a.gold}: {len(valid)} valid outputs of {len(outs)} strobes, wraps i2/i3 "
              f"{st['wrap_i2']}/{st['wrap_i3']}, combs {st['wrap_c1']}/{st['wrap_c2']}/{st['wrap_c3']}, "
              f"ties even/odd {st['tie_even']}/{st['tie_odd']}, saturated {st['saturated']}")


if __name__ == "__main__":
    main()
