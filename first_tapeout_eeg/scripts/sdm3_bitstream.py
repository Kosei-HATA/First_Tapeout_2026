#!/usr/bin/env python3
"""Bitstream SNDR for the sdm3 SC SDM benches (fs=256 kHz, 32 Hz input).

Like sdm_bitstream.py, but samples BIT by majority vote over the PH2 plateau
of each cycle instead of a single point 1 us before cycle end. ngspice saves
at internal (non-uniform) time steps with multi-us gaps in smooth regions;
single-point sampling can land inside the latch's CMPCK transition and read a
mid-rail value - ~1 such bad read in 80000 cycles raises the apparent in-band
floor from ~5e-7 to ~5e-5/bin (66.8 dB vs 100.9 dB on the same data).

Usage: sdm3_bitstream.py <csv> [--fs 256000] [--fsig 32] [--band 0.5 100]
                        [--skip-ms 10] [--bitcol 0]
CSV format: wrdata (scale,value) pairs; bit value at column 3+2*bitcol.
"""
import numpy as np, sys

def main():
    path = sys.argv[1]
    def opt(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            return float(sys.argv[i+1])
        return default
    bitcol = int(opt("--bitcol", 0))
    fsig = opt("--fsig", 32)
    fs = opt("--fs", 256000)
    blo, bhi = 0.5, 100.0
    if "--band" in sys.argv:
        i = sys.argv.index("--band")
        blo, bhi = float(sys.argv[i+1]), float(sys.argv[i+2])
    skip_ms = opt("--skip-ms", 10)

    d = np.loadtxt(path)
    t = d[:, 0]
    bit = d[:, 3 + 2*bitcol]
    Ts = 1.0/fs
    spc = int(round(fs/fsig))
    k0 = int(np.ceil((t[0] + skip_ms*1e-3)/Ts))
    nsamp = int((t[-1]-k0*Ts)/Ts)
    ncyc = nsamp//spc
    nsamp = ncyc*spc
    ks = k0 + np.arange(nsamp)
    # majority vote over the PH2 plateau (BIT decided during PH1, static
    # through PH2 = 53%-95% of the cycle for the sdm3 clocking)
    lo = np.searchsorted(t, ks*Ts + 0.57*Ts)
    hi = np.searchsorted(t, ks*Ts + 0.94*Ts)
    b = np.empty(nsamp)
    for i, (a, c) in enumerate(zip(lo, hi)):
        a = min(a, len(bit)-1); c = min(max(c, a+1), len(bit))
        b[i] = 1.0 if np.mean(bit[a:c] > 0.9) > 0.5 else -1.0

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
    duty = (b+1)/2
    print(f"file={path}")
    print(f"  samples={n} ({ncyc} cycles of {fsig} Hz), duty={duty.mean():.4f}")
    print(f"  signal @{fsig} Hz: bitstream amplitude={sig:.4f}")
    print(f"  SNDR({blo}-{bhi} Hz) = {sndr:.2f} dB")
    top = np.argsort(mag[noise_bins])[-5:][::-1]
    fb = f[noise_bins]; mb = mag[noise_bins]
    print(f"  top in-band lines: {[(round(fb[j],1), round(mb[j],5)) for j in top]}")

if __name__ == "__main__":
    main()
