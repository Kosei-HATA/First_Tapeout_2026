#!/usr/bin/env python3
"""LS-fit gain measurement for chopped-PGA transient runs.

Windowed FFTs on non-integer-cycle runs lie; this measures amplitude by
least-squares projection onto sin/cos at the known input frequency, plus DC.
Usage: lsfit_gain.py <csv> <freq_hz> [--skip S]  (csv: time,<voutd> pairs from wrdata)
"""
import numpy as np, sys

def main():
    path = sys.argv[1]; f0 = float(sys.argv[2])
    skip = 0.0
    if "--skip" in sys.argv:
        skip = float(sys.argv[sys.argv.index("--skip")+1])
    d = np.loadtxt(path)
    t = d[:,0]
    # wrdata under `save` zeroes inline expressions, so decks now write
    # v(OUTP) v(OUTN) separately: 6 cols = t,t, t,outp, t,outn -> diff here.
    # Legacy 4-col files hold the differential value in col 3 directly.
    v = d[:,3]-d[:,5] if d.shape[1] >= 6 else d[:,3]
    sel = t >= skip
    t = t[sel]; v = v[sel]
    A = np.column_stack([np.sin(2*np.pi*f0*t), np.cos(2*np.pi*f0*t), np.ones(len(t))])
    coef, res, _, _ = np.linalg.lstsq(A, v, rcond=None)
    amp = np.hypot(coef[0], coef[1])
    resid = v - A@coef
    # residual slow content: decimate to 1 ms bins then look at < 5 Hz
    ns = []
    tb = []
    t0 = t[0]
    nb = int((t[-1]-t0)/1e-3)
    for k in range(nb):
        s = (t>=t0+k*1e-3)&(t<t0+(k+1)*1e-3)
        if s.any():
            ns.append(resid[s].mean()); tb.append(t0+k*1e-3)
    ns = np.array(ns)
    ns = ns - ns.mean()
    fr = np.fft.rfftfreq(len(ns), 1e-3)
    sp = np.abs(np.fft.rfft(ns*np.hanning(len(ns))))*2/np.sum(np.hanning(len(ns)))
    ib = fr <= 100
    # exclude the immediate signal peak neighbourhood is unnecessary: resid has no signal
    print(f"file={path}")
    print(f"  signal {f0} Hz: amplitude={amp*1e3:.4f} mV  DC={coef[2]*1e3:+.4f} mV")
    print(f"  residual: rms={np.std(resid)*1e3:.4f} mV, slow max={np.abs(ns).max()*1e3:.4f} mV")
    top = np.argsort(sp[ib])[-4:][::-1]
    print(f"  residual top in-band lines: {[(round(fr[j],2), round(sp[j]*1e3,4)) for j in top]}")

if __name__ == "__main__":
    main()
