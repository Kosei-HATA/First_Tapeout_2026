"""Spectrum of the 1 kSPS output of the end-to-end test (tb_e2e +out file).

Reads "<seq> <data hex>" lines, takes a coherent record after the settling samples
and prints, for the band 0.5..100 Hz: the tone level and its CIC3 droop against the
theory, the harmonics HD2..HD5, the alias of an out-of-band tone (CIC3 response at
that frequency against the theory) and the SNDR without the alias. The same codes
(+codes) decimated in floating point with a sharp filter (CIC4 R = 256 and a Kaiser
FIR to 400 S/s, as ct2_dac2_options.sndr) give the reference SNDR of the stream, and
the difference to the RTL output is the part of the digital output (CIC3 aliasing
of the shaped quantization noise and the 24-bit rounding).

Units: x = 2c - 31 (code units), DATA = x * 2^18 at DC, full scale x = 31; the ADC
input u (V) gives x = 64 u (RD1 / (RIN VREF) with RIN / RD1 = 31 / 32, VREF 0.5 V).
0.279 V pk at the ADC input is the chip full scale (0.943 mV pk at the electrode).

Usage: e2e_spectrum.py SAMPLES --codes CODES --tone F [--alias F] [--settle N] [--record N]
"""

import argparse
import math

import numpy as np
from scipy.signal import resample_poly

FS_MOD = 1.024e6
R = 1024
FS_OUT = FS_MOD / R          # 1000 S/s
X_PER_V = 64.0               # code units per volt at the ADC input
V_FS = 0.279                 # chip full scale at the ADC input (V pk)
E_FS = 0.943e-3              # the same at the electrode (V pk)


def cic3_gain(f):
    """|H(f)| of the R = 1024 sinc^3 decimator, DC gain normalized to 1."""
    if f == 0:
        return 1.0
    a = math.pi * f / FS_MOD
    return abs(math.sin(R * a) / (R * math.sin(a))) ** 3


def read_samples(path):
    seq, data = [], []
    with open(path) as fh:
        for line in fh:
            s, d = line.split()
            v = int(d, 16)
            if v & 0x800000:
                v -= 1 << 24
            seq.append(int(s))
            data.append(v)
    seq = np.array(seq)
    if np.any(np.diff(seq) != 1) or seq[0] != 0:
        raise SystemExit("SEQ is not 0, 1, 2, ...")
    return np.array(data, dtype=np.float64) / 2.0 ** 18     # code units x


def band_analysis(y, fs, tone, alias=None, lo=0.5, hi=100.0):
    n = y.size
    spec = np.abs(np.fft.rfft(y)) ** 2 / (n / 2.0) ** 2     # amplitude^2 of each bin (pk)
    f = np.arange(spec.size) * fs / n
    band = (f >= lo) & (f <= hi)
    kt = int(round(tone * n / fs))
    res = {"tone_pk": math.sqrt(spec[kt])}
    harm = []
    excl = {kt}
    for h in range(2, 6):
        kh = int(round(h * tone * n / fs))
        if f[kh] <= hi:
            harm.append((h, math.sqrt(spec[kh])))
            excl.add(kh)
    res["harm"] = harm
    if alias is not None:
        fa = abs(alias - fs * round(alias / fs))            # folded frequency
        ka = int(round(fa * n / fs))
        res["alias_f"] = fa
        res["alias_pk"] = math.sqrt(spec[ka])
        excl.add(ka)
    noise = sum(spec[k] for k in np.nonzero(band)[0] if k not in excl) / 2.0   # power (rms^2)
    res["noise_rms"] = math.sqrt(noise)
    res["sndr"] = 10 * math.log10((spec[kt] / 2.0) / (noise + sum(a * a / 2.0 for _, a in harm)))
    res["snr"] = 10 * math.log10((spec[kt] / 2.0) / noise)
    return res


def reference_decimation(codes, settle_s, record_s):
    """Codes -> x in floating point: CIC4 (R = 256), then FIR /10 to 400 S/s."""
    r = 256
    acc = codes.astype(np.int64) * 2 - 31
    for _ in range(4):
        acc = np.cumsum(acc)
    acc = acc[r - 1::r]
    for _ in range(4):
        acc = np.diff(acc, prepend=np.int64(0))
    x = acc / float(r ** 4)
    d = resample_poly(x, 1, 10, window=("kaiser", 12.0))
    fs2 = FS_MOD / r / 10
    i0 = int(round(settle_s * fs2))
    return d[i0:i0 + int(round(record_s * fs2))], fs2


def report(name, res, tone, alias):
    tone_v = res["tone_pk"] / X_PER_V
    print(f"{name}: tone {tone:g} Hz {res['tone_pk']:.6f} x pk ({tone_v * 1e3:.4f} mV at the ADC input), "
          f"SNDR {res['sndr']:.1f} dB, SNR {res['snr']:.1f} dB, noise 0.5..100 Hz {res['noise_rms']:.3e} x rms "
          f"= {res['noise_rms'] / X_PER_V / V_FS * E_FS * 1e9:.4f} nVrms at the electrode")
    print("    " + ", ".join(f"HD{h} {20 * math.log10(a / res['tone_pk'] + 1e-30):.1f} dBc" for h, a in res["harm"]))
    if alias is not None:
        print(f"    alias of {alias:g} Hz at {res['alias_f']:g} Hz: {res['alias_pk']:.4e} x pk")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("samples")
    ap.add_argument("--codes", required=True)
    ap.add_argument("--tone", type=float, required=True)
    ap.add_argument("--tone-v", type=float, help="input amplitude (V pk) of the tone, for the gain check")
    ap.add_argument("--alias", type=float)
    ap.add_argument("--alias-v", type=float, help="input amplitude (V pk) of the out-of-band tone")
    ap.add_argument("--settle", type=int, default=250)
    ap.add_argument("--record", type=int, required=True)
    a = ap.parse_args()

    x = read_samples(a.samples)
    if x.size < a.settle + a.record:
        raise SystemExit(f"only {x.size} samples")
    y = x[a.settle:a.settle + a.record]
    res = band_analysis(y, FS_OUT, a.tone, a.alias)
    print(f"RTL output (CIC3, 1 kSPS): samples {a.settle}..{a.settle + a.record - 1} "
          f"({a.record / FS_OUT:g} s, coherent, rectangular window)")
    report("  RTL", res, a.tone, a.alias)
    if a.tone_v:
        g_meas = res["tone_pk"] / (a.tone_v * X_PER_V)
        print(f"    tone gain {g_meas:.6f} of x = 64 u (CIC3 droop at {a.tone:g} Hz in theory {cic3_gain(a.tone):.6f}; "
              f"the rest is the modulator's STF and finite OTA gain)")
    if a.alias is not None and a.alias_v:
        h_meas = res["alias_pk"] / (a.alias_v * X_PER_V)
        print(f"    CIC3 response at {a.alias:g} Hz: measured {20 * math.log10(h_meas):.2f} dB, "
              f"theory {20 * math.log10(cic3_gain(a.alias)):.2f} dB")

    # the reference record starts 0.1 s into the stream (the FIR edge effects at
    # the end of the stream, about 25 ms, stay outside it)
    codes = np.fromfile(a.codes, dtype=np.uint8)
    d, fs2 = reference_decimation(codes, 0.1, a.record / FS_OUT)
    ref = band_analysis(d, fs2, a.tone, a.alias)
    print(f"Reference (same codes, CIC4 R=256 + FIR to {fs2:g} S/s, floating point):")
    report("  ref", ref, a.tone, a.alias)
    lsb = 1.0 / 2 ** 18
    q = lsb / math.sqrt(12.0) * math.sqrt((100.0 - 0.5) / (FS_OUT / 2.0))
    print(f"Output rounding (1 LSB = 2^-18 x, uniform, 0.5..100 Hz of 0..500 Hz): {q:.3e} x rms = "
          f"{q / X_PER_V / V_FS * E_FS * 1e9:.4f} nVrms at the electrode")


if __name__ == "__main__":
    main()
