#!/usr/bin/env python3
"""Bitstream SNDR for multi-bit ΣΔ benches (e.g. 2-bit flash quantizer output).

Like sdm3_bitstream.py but for N parallel threshold outputs (thermometer code)
or a single multi-level signal. Samples by majority vote over the PH2 plateau
per line, then sums/averages the levels to form the output code.

Usage: sdm_mb_bitstream.py <csv> --ncols M [--fs 256000] [--fsig 32]
       [--band 0.5 100] [--skip-ms 10]
CSV: wrdata (scale,value) pairs; the M bit lines' values at columns 3+2*(bitcol+j)
for j=0..M-1 (default bitcol 0). Thermometer code assumed: output code =
sum of the M lines (each 0/1 after vote), scaled to ±1 by code = 2*sum/M - 1.
"""
import numpy as np, sys

def main():
    path = sys.argv[1]
    def opt(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            return float(sys.argv[i+1])
        return default
    ncols = int(opt("--ncols", 1))
    fsig = opt("--fsig", 32)
    fs = opt("--fs", 256000)
    blo, bhi = 0.5, 100.0
    if "--band" in sys.argv:
        i = sys.argv.index("--band")
        blo, bhi = float(sys.argv[i+1]), float(sys.argv[i+2])
    skip_ms = opt("--skip-ms", 10)

    d = np.loadtxt(path)
    t = d[:, 0]
    Ts = 1.0/fs
    spc = int(round(fs/fsig))
    k0 = int(np.ceil((t[0] + skip_ms*1e-3)/Ts))
    nsamp = int((t[-1]-k0*Ts)/Ts)
    ncyc = nsamp//spc
    nsamp = ncyc*spc
    ks = k0 + np.arange(nsamp)
    lo = np.searchsorted(t, ks*Ts + 0.57*Ts)
    hi = np.searchsorted(t, ks*Ts + 0.94*Ts)

    codes = np.zeros(nsamp)
    for j in range(ncols):
        bit = d[:, 3 + 2*j]
        for i, (a, c) in enumerate(zip(lo, hi)):
            a = min(a, len(bit)-1); c = min(max(c, a+1), len(bit))
            codes[i] += 1.0 if np.mean(bit[a:c] > 0.9) > 0.5 else 0.0
    b = 2.0*codes/max(ncols,1) - 1.0   # thermometer -> ±1

    n = len(b)
    B = np.fft.rfft(b)
    f = np.fft.rfftfreq(n, Ts)
    mag = np.abs(B)/(n/2)
    isig = int(round(fsig*n*Ts))
    band = (f >= blo) & (f <= bhi)
    sig = mag[isig]
    noise_bins = band.copy(); noise_bins[isig] = False
    pnoise = np.sum((mag[noise_bins]/np.sqrt(2))**2)
    sndr = 20*np.log10((sig/np.sqrt(2))/np.sqrt(pnoise))
    duty = (codes/max(ncols,1)).mean()
    print(f"file={path}")
    print(f"  samples={n} ({ncyc} cycles of {fsig} Hz), mean code={duty:.4f}")
    print(f"  signal @{fsig} Hz: bitstream amplitude={sig:.4f}")
    print(f"  SNDR({blo}-{bhi} Hz) = {sndr:.2f} dB")
    top = np.argsort(mag[noise_bins])[-5:][::-1]
    fb = f[noise_bins]; mb = mag[noise_bins]
    print(f"  top in-band lines: {[(round(fb[j],1), round(mb[j],5)) for j in top]}")

if __name__ == "__main__":
    main()
