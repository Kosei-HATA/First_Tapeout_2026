#!/usr/bin/env python3
"""ENOB in its proper sense (11/14): a full-scale sine at the electrodes through the whole chain to DATA,
the SINAD over 0.5-100 Hz from the FFT of DATA, ENOB = (SINAD - 1.76) / 6.02.

The bits quoted so far (figure 07, budget.csv) are an SNR from a sum of input-referred noise,
16.5 - log2(N / 5.88 nVrms), with the ADC side still the 10/22 allocation (2.93 nVrms). Here the sine itself
goes through the chain. A transistor-level run cannot give it: the band starts at 0.5 Hz, so the record must be
seconds long, and the chip's power-on-to-CIC chain covers 10 ms in about 2.5 days. The chain is put together
from the extracted blocks instead:

  electrodes  x(t) = A sin(2 pi f0 t), A = 0.943 mV pk (the budget's full scale), f0 = 83 cycles in 8192 DATA
              samples (10.13 Hz: coherent, the cycle count prime, harmonics 2 to 9 in the band). The source's own
              thermal noise is left out, as in the target (16.5 bit with 100 ohm per leg; the electrodes are
              evaluated apart).
  AFE         the r12 AFE's static transfer (afe_dcpath.py static: the chopped AFE's averaged output at
              +-0.236 .. +-0.943 mV, runs/final_static_pex_r12.log; 5th-order fit, offset dropped) scaled to the
              chain's slope 297.75 (gf180_input_output_20261112.md). Its noise as white noise at the input with
              the in-band level of the Monte Carlo on the chip (r12 wiring, AFE_IBIAS 3, runs/chip_noise_r12/
              mc_ib3.log, per die; typical 5.327 nVrms) and the output chopper's blanking fold (0.681 nVrms) as
              the budget books it. A die's gain follows its chopped gain in that run.
  ADC         the per-clock loop model of adc_beh_mc.py with the dies of the extracted ADC's block Monte Carlo
              (r11's, the same blocks as r12: thresholds, DAC1 elements and their even / odd charge, OTA gains,
              the loop's R and C) and ELD 0.22 of a clock (reproduces the transistor-level loop). Its thermal
              noise at the input: resistors 1.17, OTA1 0.27, OTA1's chopper fold 0.17 nVrms at the electrodes
              (the tracker's 11/12 values). The 1/f fluctuation of the RIN and DAC1 poly resistors as a gain
              noise of one-sided density s_r (1/32 + 1/124) / f (adc_flicker.py model B, I_cal = I0,
              runs/adc_flicker_r11; RIN and DAC1 together).
  digital     eeg_cic3 bit-exact (rtl/model/cic_golden.py: x = 2c - 31, sinc^3, R 1024, round half even by 2^12,
              24 bit), vectorized here and checked against the golden model on every run; DATA at 1 kS/s.

The SINAD counts every bin of 0.5-100 Hz except the tone's (rectangular window on the coherent record). The
chain's noise sources go in at their extracted levels, so what the sine test adds to the budget's sum is the
loop itself at full scale (quantization, DAC1 mismatch and charges, ELD, OTA gains), the distortion of AFE and
loop together, the gain noise around the tone, and the RTL's decimator (sinc^3 droop: -0.43 dB at 100 Hz).
Not in it by default: the OTAs' static nonlinearity (--ota-nl adds it; 11/15: the ENOB moves by 0.45 mbit at most,
figure 36), the poly resistors' voltage coefficient (the PDK's terms are 0), the external reference (its requirement:
0.5 nVrms at full scale), clock jitter (DAC1's edge: ota_distortion.py).

One record's noise estimate scatters by about 1 / sqrt(815 bins), 3.5 % in power or 0.025 bit (1 sigma), as
much as the dies differ: typical is run again with its own noise (--repeat) and quoted as the mean. The SINAD is
also given with the decimator's droop equalized (each bin divided by |sinc^3|^2), the flat band the budget's
0.5-100 Hz assumes; the sinc^3 alone takes about 3 % of the in-band white noise.

Columns, all in one vectorized loop run: typical and its repeats, typical without input (the in-band noise of
DATA, to the electrodes by typical's slope), the Monte Carlo dies (ADC seed k with AFE seed k), the block corners
(AFE typical), an amplitude sweep on typical, and typical without noise (with and without the AFE's transfer).

--ota-nl (11/15): the same columns with the OTAs' static nonlinearity in the loop (ota_static.py: the extracted
OTA1 and OTA2 on their stage loads, per die where the die has a bench, typical otherwise); the same noise draws, so
the change against the run without it is the OTAs' (and the loop's chaotic code sequence; see ota_distortion.py for
the OTAs' error term alone).

usage: [EEG_PEX_REV=r12] gf180/tools/venv310/bin/python gf180/tapeout/pex/enob_sine.py [--nrec 8192 --cycles 83] [--quick]
           [--ota-nl]
writes runs/enob_sine_<rev>/: enob_sine.json (every column), spectra.npz (typical's DATA spectra for the figure);
with --ota-nl enob_sine_otanl.json and spectra_otanl.npz
"""
import argparse
import json
import math
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("EEG_PEX_REV", "r12")
sys.path.insert(0, HERE)
import adc_beh_mc as B  # noqa: E402  (the loop model and the dies of the block Monte Carlo)
import ota_static as O  # noqa: E402  (the OTAs' static nonlinearity, --ota-nl)
sys.path.insert(0, os.path.join(HERE, "..", "rtl", "model"))
import cic_golden as G  # noqa: E402  (eeg_cic3, bit-exact)

m = B.m
REV = B._REV
OUT = os.path.join(HERE, "runs", "enob_sine" + (f"_{REV}" if REV else ""))
FS_PK = 0.943e-3                    # V pk at the electrodes: the budget's full scale (tracker A1)
G_AFE = 297.75                      # ADC input / electrodes: the chain's slope without the AFE offset
BAND = (0.5, 100.0)
FS_DATA = m.FS / G.R                # 1 kS/s
ELD = 0.22                          # of a clock (figs_perf BEH_ELD)
N_BLANK = 0.681                     # nVrms: the output chopper's blanking fold (budget.csv)
N_ADC = dict(resistors=1.17, ota1=0.27, ota1_chop=0.17)   # nVrms at the electrodes (tracker, 11/12)
DEC_G = 256                         # the gain noise is made at 4 kHz and held
SETTLE = 20                         # DATA samples dropped after the CIC's invalid ones
STATIC_LOG = os.path.join(HERE, "runs", f"final_static_pex_{REV}.log")
NOISE = os.path.join(HERE, "runs", f"chip_noise_{REV}")
FLICKER = os.path.join(HERE, "runs", "adc_flicker_r11", "adc_flicker.json")
SWEEP_DB = [-100, -80, -60, -40, -20, -10, -6, -3, -1]


def afe_transfer():
    """The AFE's static transfer, normalized: P(xn) = xn + a2 xn^2 + ... + a5 xn^5, xn = x / FS_PK (5th-order
    least squares through the 8 points, offset dropped). Returns [a2..a5], the static gain, the fit residual (V)."""
    pts = []
    for ln in open(STATIC_LOG, encoding="utf-8"):
        mm = re.match(r"\s*pex ([+-]?\d+\.\d+) mV: average ([+-]?\d+\.\d+) mV", ln)
        if mm:
            pts.append((float(mm.group(1)), float(mm.group(2))))
    if len(pts) != 8:
        raise SystemExit(f"{STATIC_LOG}: {len(pts)} static points, 8 expected")
    x, y = np.array(pts).T
    xn = x / (FS_PK * 1e3)
    b = np.polynomial.polynomial.polyfit(xn, y, 5)
    resid = y - np.polynomial.polynomial.polyval(xn, b)
    return b[2:] / b[1], b[1] / (FS_PK * 1e3), float(np.abs(resid).max()) * 1e-3


def harmonics(a, n=4096):
    """HD2..HD5 (dBc) of P at full scale."""
    xn = np.sin(2 * np.pi * np.arange(n) / n)
    s = np.abs(np.fft.rfft(xn + sum(a[k] * xn ** (k + 2) for k in range(4))))
    return [20 * math.log10(s[h] / s[1]) for h in (2, 3, 4, 5)]


def afe_noise():
    """The AFE's in-band noise (nVrms) and chopped gain on the chip, AFE_IBIAS 3: typical and per seed."""
    def table(path):
        rows = {}
        for ln in open(path, encoding="utf-8"):
            p = [s.strip() for s in ln.strip().strip("|").split("|")]
            if len(p) == 13 and p[:3] == ["chip", "A", "3"]:
                rows[p[3]] = dict(gain=float(p[8]), nv=float(p[9]))
        return rows
    typ = table(os.path.join(NOISE, "typical_ib3.log"))["-"]
    mc = {int(s): v for s, v in table(os.path.join(NOISE, "mc_ib3.log")).items()}
    return typ, mc


def pink(n, s1, fs, rng):
    """A real sequence with one-sided density s1 / f (nothing at DC), as adc_flicker.pink."""
    w = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    h = np.zeros_like(f)
    h[1:] = np.sqrt(s1 / f[1:] * fs / 2)
    return np.fft.irfft(w * h, n)


class Stim:
    """u[i] for adc_beh_mc.simulate: the ADC input (V, differential) of every column at clock i, made block by
    block: (gain FS_PK P(x / FS_PK) + white noise) (1 + gain noise held over DEC_G clocks)."""

    def __init__(self, n, f0, amp, gain, apoly, sig, gnoise, seed, blk=1 << 16):
        self.shape = (n, len(amp))
        self.f0, self.amp, self.gain, self.apoly, self.sig, self.g = f0, amp, gain, apoly, sig, gnoise
        self.rng = np.random.default_rng(seed)
        self.blk, self.i0, self.buf = blk, -(1 << 62), None

    def _fill(self, i0):
        i1 = min(i0 + self.blk, self.shape[0])
        t = (np.arange(i0, i1) + 0.5) / m.FS
        xn = np.sin(2 * np.pi * self.f0 * t)[:, None] * (self.amp / FS_PK)[None, :]
        p = xn + sum(self.apoly[None, :, k] * xn ** (k + 2) for k in range(4))
        u = self.gain[None, :] * FS_PK * p + self.sig[None, :] * self.rng.standard_normal((i1 - i0, self.shape[1]))
        u *= 1.0 + self.g[np.arange(i0, i1) // DEC_G]
        self.buf, self.i0 = u, i0

    def __getitem__(self, i):
        k = i - self.i0
        if not 0 <= k < self.blk:
            self._fill(i - i % self.blk)
            k = i - self.i0
        return self.buf[k]


def cic_data(c):
    """eeg_cic3 on a code stream from its clear: every strobe's DATA (the first G.NSKIP invalid), int64."""
    x = 2 * c.astype(np.int64) - 31
    i1 = np.cumsum(x)                                        # i1 += x
    i2 = np.concatenate(([0], np.cumsum(i1)[:-1]))           # i2 += old i1 (wraps modulo 2^64; the result fits)
    i3 = np.concatenate(([0], np.cumsum(i2)[:-1]))           # i3 += old i2
    y = i3[G.R - 1::G.R]                                     # combs on the updated i3 at the R-th input
    for _ in range(3):
        y = np.diff(y, prepend=np.int64(0))
    q, r = y >> G.SH, y & ((1 << G.SH) - 1)
    half = 1 << (G.SH - 1)
    q = q + ((r > half) | ((r == half) & ((q & 1) == 1)))
    return np.clip(q, -(1 << (G.WO - 1)), (1 << (G.WO - 1)) - 1)


def check_cic(n=300_000, seed=5):
    rng = np.random.default_rng(seed)
    c = np.clip(np.round(15.5 + 14 * np.sin(np.arange(n) * 3e-4) + 2 * rng.standard_normal(n)), 0, 31).astype(np.int8)
    gold, _ = G.cic3_run(bytes(c.astype(np.uint8)))
    mine = cic_data(c)
    ok = len(gold) == len(mine) and all(int(d) == int(v) for (d, _), v in zip(gold, mine))
    print(f"CIC: vectorized against cic_golden on {n} codes, {len(gold)} strobes: {'identical' if ok else 'DIFFER'}")
    return ok


def sinc3(f):
    """|eeg_cic3| at f (Hz): sinc^3, R 1024 at the modulator's clock."""
    f = np.asarray(f, float)
    out = np.ones_like(f)
    nz = f > 0
    out[nz] = np.abs(np.sin(np.pi * f[nz] * G.R / m.FS) / (G.R * np.sin(np.pi * f[nz] / m.FS))) ** 3
    return out


def spectrum(data, nrec, k0):
    """SINAD etc. over BAND from the record after the invalid and settling strobes (rectangular window); also
    the SINAD with the decimator's droop equalized (every bin divided by |sinc^3|^2: a flat band, as the budget's
    0.5-100 Hz assumes) and the in-band noise and distortion in DATA counts rms (for a record without input)."""
    x = data[G.NSKIP + SETTLE:G.NSKIP + SETTLE + nrec].astype(float)
    p = np.abs(np.fft.rfft(x)) ** 2
    f = np.arange(p.size) * FS_DATA / nrec
    band = (f >= BAND[0]) & (f <= BAND[1])
    nb = band.copy()
    nb[k0] = False
    harm = [h * k0 for h in range(2, 10) if h * k0 < p.size and band[h * k0]]
    nh = nb.copy()
    nh[harm] = False
    db = lambda v: 10 * math.log10(v)  # noqa: E731
    ps = p[k0]
    peq = p / sinc3(f) ** 2
    return dict(sinad=db(ps / p[nb].sum()), sinad_eq=db(peq[k0] / peq[nb].sum()), snr=db(ps / p[nh].sum()),
                thd=db(p[harm].sum() / ps), hd=[db(p[h] / ps) for h in harm], amp_counts=2 * math.sqrt(ps) / nrec,
                nad_counts=math.sqrt(2 * p[nb].sum()) / nrec, dc_counts=float(x.mean())), p / ps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nrec", type=int, default=8192, help="DATA samples in the record (1 kS/s)")
    ap.add_argument("--cycles", type=int, default=83, help="sine cycles in the record (prime)")
    ap.add_argument("--quick", action="store_true", help="typical, its repeats, no input and the noiseless columns only")
    ap.add_argument("--repeat", type=int, default=8, help="typical again with its own noise, N more records")
    ap.add_argument("--ota-nl", action="store_true", help="the OTAs' static nonlinearity in the loop (ota_static.py)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if not check_cic():
        raise SystemExit("the vectorized CIC differs from cic_golden")
    f0 = a.cycles * FS_DATA / a.nrec
    apoly, g_static, resid = afe_transfer()
    hds = harmonics(apoly)
    print(f"AFE static transfer ({os.path.relpath(STATIC_LOG, HERE)}): gain {g_static:.3f}, fit residual "
          f"{resid * 1e6:.2f} uV, a2..a5 {', '.join(f'{v:+.3e}' for v in apoly)}; at full scale HD2..HD5 "
          f"{' / '.join(f'{v:.1f}' for v in hds)} dBc")
    typ_afe, mc_afe = afe_noise()
    fl = json.load(open(FLICKER, encoding="utf-8"))
    s_g = fl["s_r"] * (1 / 32 + 1 / 124)
    j = B.load_block()
    corners = B.corner_dies(j)
    typ = corners[0]
    mcd, nod, _ = B.mc_dies(j)
    cols = []

    def col(label, group, die, amp_db=0.0, afe=None, noise=True, poly=True, flick=True):
        afe = afe or typ_afe
        cols.append(dict(label=label, group=group, die=die, amp_db=amp_db,
                         amp=FS_PK * 10 ** (amp_db / 20) if amp_db is not None else 0.0,
                         gain=G_AFE * afe["gain"] / typ_afe["gain"], afe_nv=afe["nv"], noise=noise, poly=poly,
                         flick=flick))

    col("typical", "typical", typ)
    for k in range(a.repeat):
        col(f"typical, record {k + 2}", "repeat", typ)
    col("typical, no input", "noinput", typ, amp_db=None)
    if not a.quick:
        for d in mcd:
            col(d.label, "mc", d, afe=mc_afe.get(int(d.label[2:])))
        for d in corners[1:]:
            col(d.label, "corner", d)
        for db in SWEEP_DB:
            col(f"typical, {db:+d} dBFS", "sweep", typ, amp_db=db)
    col("typical, no noise", "noiseless", typ, noise=False, flick=False)
    col("typical, no noise, AFE linear", "noiseless", typ, noise=False, poly=False, flick=False)
    S = len(cols)
    n = (G.NSKIP + SETTLE + a.nrec + 1) * G.R
    adc2 = sum(v * v for v in N_ADC.values())
    for c in cols:
        c["inj_nv"] = math.sqrt(c["afe_nv"] ** 2 + N_BLANK ** 2 + adc2) if c["noise"] else 0.0
        var_u = ((c["afe_nv"] ** 2 + N_BLANK ** 2) * c["gain"] ** 2 + adc2 * G_AFE ** 2) * 1e-18
        c["sig_u"] = math.sqrt(var_u / (BAND[1] - BAND[0]) * m.FS / 2) if c["noise"] else 0.0
    ng = n // DEC_G + 2
    gnoise = np.zeros((ng, S))
    for s, c in enumerate(cols):
        if c["flick"]:
            gnoise[:, s] = pink(ng, s_g, m.FS / DEC_G, np.random.default_rng(3000 + s))
    dies = [c["die"] for c in cols]
    co = [d.coeffs(ELD) for d in dies]
    ad, b, ad0, b0 = (np.array([cc[i] for cc in co]) for i in range(4))
    st = lambda at: np.array([getattr(d, at) for d in dies])  # noqa: E731
    u = Stim(n, f0, np.array([c["amp"] for c in cols]), np.array([c["gain"] for c in cols]),
             np.array([apoly if c["poly"] else np.zeros(4) for c in cols]), np.array([c["sig_u"] for c in cols]),
             gnoise, seed=11)
    print(f"{S} columns, {n} clocks ({n / m.FS:.2f} s), f0 {f0:.6f} Hz, record {a.nrec} DATA samples; "
          f"ADC dies from {os.path.relpath(B.BLOCK, HERE)}; DAC1 typical for MC seeds {nod}", flush=True)
    t = time.time()
    nl1 = nl2 = None
    if a.ota_nl:
        nl1, nl2, used = O.loop_nl(dies, m)
        for c, cs in zip(cols, used):
            c["ota_bench"] = cs
        print("OTA nonlinearity in the loop: benches " + ", ".join(sorted(set(used))), flush=True)
    codes, x1m, x2m = B.simulate(ad, b, ad0, b0, u, st("thr"), st("w1"), st("w2"), st("e1"), st("o1"),
                                 np.zeros(S), np.zeros((S, 31)), nl1=nl1, nl2=nl2)
    dt = time.time() - t
    print(f"loop: {dt:.0f} s", flush=True)
    rows, spec = [], {}
    for s, c in enumerate(cols):
        r = dict(label=c["label"], group=c["group"], amp_db=c["amp_db"], amp_mv=c["amp"] * 1e3, gain=c["gain"],
                 afe_nv=c["afe_nv"], inj_nv=c["inj_nv"], noise=c["noise"], afe_poly=c["poly"], flicker=c["flick"],
                 x1max=float(x1m[s]), x2max=float(x2m[s]))
        if a.ota_nl:
            r["ota_bench"] = c["ota_bench"]
        if (codes[:, s] < 0).any():
            r.update(sinad=float("nan"), note="runaway")
        else:
            res, p = spectrum(cic_data(codes[:, s]), a.nrec, a.cycles)
            r.update(res)
            if c["amp"] > 0:
                r["enob"] = (r["sinad"] - 1.76) / 6.02
                r["enob_eq"] = (r["sinad_eq"] - 1.76) / 6.02
                r["enob_fs"] = (r["sinad"] + 20 * math.log10(FS_PK / c["amp"]) - 1.76) / 6.02
                r["nad_nv"] = c["amp"] / math.sqrt(2) * 10 ** (-r["sinad"] / 20) * 1e9
                r["counts_per_uv"] = r["amp_counts"] / (c["amp"] * 1e6)
            else:                                           # no tone: only the in-band noise counts
                for k in ("sinad", "sinad_eq", "snr", "thd", "hd", "amp_counts"):
                    r.pop(k)
            if c["group"] in ("typical", "noiseless"):
                spec[c["label"]] = p
        rows.append(r)
    for r in rows:                                          # no input: DATA counts to the electrodes by typical's slope
        if r["group"] == "noinput" and "nad_counts" in r:
            r["noise_nv"] = r["nad_counts"] / rows[0]["counts_per_uv"] * 1e3
    f = np.arange(a.nrec // 2 + 1) * FS_DATA / a.nrec
    sfx = "_otanl" if a.ota_nl else ""
    np.savez_compressed(os.path.join(OUT, f"spectra{sfx}.npz"), f=f, k0=a.cycles,
                        **{k.replace(", ", "_").replace(" ", "_"): v for k, v in spec.items()})
    meta = dict(rev=REV, fs_pk_v=FS_PK, f0_hz=f0, nrec=a.nrec, cycles=a.cycles, band_hz=BAND, g_afe=G_AFE, eld=ELD,
                n_blank_nv=N_BLANK, n_adc_nv=N_ADC, gain_noise_s1=s_g, afe_static=dict(a2_a5=list(map(float, apoly)),
                gain=g_static, resid_v=resid, hd2_hd5_dbc=hds), afe_typical=typ_afe, block=B.BLOCK, loop_s=dt,
                dac1_typical_seeds=nod, ota_nl=a.ota_nl)
    with open(os.path.join(OUT, f"enob_sine{sfx}.json"), "w", encoding="utf-8") as fo:
        json.dump(dict(meta=meta, rows=rows), fo, indent=1)
    print("\n| column | input (dBFS) | SINAD (dB) | ENOB (bit) | ENOB, droop equalized (bit) | SNR (dB) | THD (dBc) "
          "| HD2 / HD3 (dBc) | NAD (nVrms) | injected noise (nVrms) | peak abs x2 (mV) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lvl = "none" if r["amp_db"] is None else f"{r['amp_db']:+.0f}"
        if r.get("note") == "runaway":
            print(f"| {r['label']} | {lvl} | runaway | | | | | | | | |")
        elif r["group"] == "noinput":
            print(f"| {r['label']} | {lvl} | | | | | | | {r['noise_nv']:.3f} (noise alone) | {r['inj_nv']:.3f} "
                  f"| {r['x2max'] * 1e3:.1f} |")
        else:
            print(f"| {r['label']} | {lvl} | {r['sinad']:.2f} | {r['enob']:.3f} | {r['enob_eq']:.3f} | {r['snr']:.2f} "
                  f"| {r['thd']:.1f} | {r['hd'][0]:.1f} / {r['hd'][1]:.1f} | {r['nad_nv']:.3f} | {r['inj_nv']:.3f} "
                  f"| {r['x2max'] * 1e3:.1f} |")
    for name, gs in (("typical, every record", ("typical", "repeat")), ("Monte Carlo", ("mc",)), ("corners", ("corner",))):
        ok = [r for r in rows if r["group"] in gs and "enob" in r]
        if len(ok) > 1:
            e, q = np.array([r["enob"] for r in ok]), np.array([r["enob_eq"] for r in ok])
            print(f"\n{name}: {len(ok)} records, ENOB mean {e.mean():.3f}, sigma {e.std(ddof=1):.3f}, worst {e.min():.3f}, "
                  f"best {e.max():.3f} bit; droop equalized mean {q.mean():.3f}, worst {q.min():.3f} bit")
    print(f"\nwrote {os.path.join(OUT, f'enob_sine{sfx}.json')}")


if __name__ == "__main__":
    main()
