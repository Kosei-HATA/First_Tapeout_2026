#!/usr/bin/env python3
"""Streaming multi-bit thermometer bitstream SNDR for very large wrdata CSVs.

Memory-lean version of sdm_mb_bitstream.py: reads line by line, keeps only
the PH2 plateau samples per thermometer line, majority-votes, sums to code.

Usage: sdm_mb_bitstream_stream.py <csv> [--ncols 15] [--fs 512000] [--fsig 32]
       [--band 0.5 100] [--skip-ms 2]
CSV: wrdata (scale,value) pairs; bit lines at columns 3+2*j, j=0..ncols-1.
"""
import numpy as np, sys, gzip

def main():
    path = sys.argv[1]
    def opt(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            return float(sys.argv[i+1])
        return default
    ncols = int(opt("--ncols", 15))
    fsig = opt("--fsig", 32)
    fs = opt("--fs", 512000)
    blo, bhi = 0.5, 100.0
    if "--band" in sys.argv:
        i = sys.argv.index("--band")
        blo, bhi = float(sys.argv[i+1]), float(sys.argv[i+2])
    skip_ms = opt("--skip-ms", 2)
    Ts = 1.0/fs
    bitcols = [3 + 2*j for j in range(ncols)]

    # pass 1: collect plateau votes per line per sample index
    votes = {}   # (sample_idx, line) -> [count_high, count_total]
    t0 = None; tlast = None
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            p = line.split()
            t = float(p[0])
            if t0 is None: t0 = t
            tlast = t
            k = int(t/Ts)
            ph = (t - k*Ts)/Ts
            if 0.57 <= ph <= 0.94:
                for j, c in enumerate(bitcols):
                    key = (k, j)
                    v = votes.get(key)
                    h = 1 if float(p[c]) > 0.9 else 0
                    votes[key] = (v[0]+h, v[1]+1) if v else (h, 1)
    kmin = int(np.ceil((t0 + skip_ms*1e-3)/Ts))
    spc = int(round(fs/fsig))
    kmax_avail = max(k for (k, j) in votes)
    ncyc = (kmax_avail - kmin)//spc
    kmax = kmin + ncyc*spc
    print(f"# t=[{t0:.4f},{tlast:.4f}] samples {kmin}..{kmax} ({ncyc} coherent cycles of {fsig} Hz)")
    codes = np.zeros(kmax-kmin)
    for j in range(ncols):
        for i, k in enumerate(range(kmin, kmax)):
            v = votes.get((k, j))
            if v and v[0]*2 > v[1]:
                codes[i] += 1.0
    n = len(codes)
    b = 2.0*codes/ncols - 1.0
    B = np.fft.rfft(b)
    f = np.fft.rfftfreq(n, Ts)
    mag = np.abs(B)/(n/2)
    isig = int(round(fsig*n*Ts))
    band = (f >= blo) & (f <= bhi)
    sig = mag[isig]
    nb = band.copy(); nb[isig] = False
    pnoise = np.sum((mag[nb]/np.sqrt(2))**2)
    sndr = 20*np.log10((sig/np.sqrt(2))/np.sqrt(pnoise))
    print(f"file={path}")
    print(f"  samples={n}, mean code={codes.mean()/ncols:.4f}")
    print(f"  signal @{fsig} Hz: amplitude={sig:.4f}")
    print(f"  SNDR({blo}-{bhi} Hz) = {sndr:.2f} dB")
    fb = f[nb]; mb = mag[nb]
    top = np.argsort(mb)[-5:][::-1]
    print(f"  top in-band lines: {[(round(fb[j],1), round(mb[j],5)) for j in top]}")

if __name__ == "__main__":
    main()
