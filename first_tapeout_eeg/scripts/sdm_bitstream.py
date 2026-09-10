#!/usr/bin/env python3
"""Bitstream SNDR for the CT 1st-order SDM bench (fs=16 kHz, 32 Hz input).

Reads a wrdata CSV (time,value column pairs), samples the BIT node at 16 kHz
just before each clock cycle ends, takes an integer number of 32 Hz cycles
(500 samples/cycle), and does a coherent FFT: signal bin at 32 Hz vs the rest
of the 0.5-100 Hz band.

Usage: sdm_bitstream.py <csv> [--bitcol N] [--fsig 32] [--fs 16000]
                        [--band 0.5 100] [--skip-ms 10]
--bitcol: value-column index (0-based, counting value columns only, time pairs
          ignored). sdm1ct.csv: 0=vin, 1=oint, 2=bit (default 2).
"""
import numpy as np, sys

def main():
    path = sys.argv[1]
    def opt(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            return float(sys.argv[i+1])
        return default
    bitcol = int(opt("--bitcol", 2))
    fsig = opt("--fsig", 32)
    fs = opt("--fs", 16000)
    blo, bhi = 0.5, 100.0
    if "--band" in sys.argv:
        i = sys.argv.index("--band")
        blo, bhi = float(sys.argv[i+1]), float(sys.argv[i+2])
    skip_ms = opt("--skip-ms", 10)

    d = np.loadtxt(path)
    t = d[:, 0]
    bit = d[:, 3 + 2*bitcol]

    Ts = 1.0/fs
    spc = int(round(fs/fsig))          # samples per signal cycle (500)
    tstart = t[0] + skip_ms*1e-3
    k0 = int(np.ceil(tstart/Ts))
    nsamp = int((t[-1]-k0*Ts)/Ts)
    ncyc = nsamp//spc
    nsamp = ncyc*spc
    # sample BIT 1 us before cycle end (decision settled, latch holding)
    tsamp = (k0 + np.arange(nsamp))*Ts - 1e-6
    idx = np.searchsorted(t, tsamp)
    idx = np.clip(idx, 0, len(t)-1)
    b = (bit[idx] > 0.9).astype(float)*2 - 1     # +/-1

    n = len(b)
    B = np.fft.rfft(b)                 # coherent: integer cycles, no window
    f = np.fft.rfftfreq(n, Ts)
    mag = np.abs(B)/(n/2)
    isig = int(round(fsig*n*Ts))
    band = (f >= blo) & (f <= bhi)
    sig = mag[isig]
    noise_bins = band.copy(); noise_bins[isig] = False
    # also drop DC bin neighbourhood handled by blo=0.5
    pnoise = np.sum((mag[noise_bins]/np.sqrt(2))**2)
    sndr = 20*np.log10((sig/np.sqrt(2))/np.sqrt(pnoise))
    duty = (b+1)/2
    print(f"file={path}")
    print(f"  samples={n} ({ncyc} cycles of {fsig} Hz), duty={duty.mean():.4f}")
    print(f"  signal @{fsig} Hz: bitstream amplitude={sig:.4f}")
    print(f"  SNDR({blo}-{bhi} Hz) = {sndr:.2f} dB")
    # top in-band spurs excluding signal
    top = np.argsort(mag[noise_bins])[-5:][::-1]
    fb = f[noise_bins]; mb = mag[noise_bins]
    print(f"  top in-band lines: {[(round(fb[j],1), round(mb[j],4)) for j in top]}")

if __name__ == "__main__":
    main()
