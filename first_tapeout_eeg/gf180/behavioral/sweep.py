#!/usr/bin/env python3
"""Architecture sweep for the GF180 Sigma-Delta ADC (behavioral, sdm.py).

Grid: order {2,3} x quantizer {1,2,4 bit} x dither {none, input sine/PN,
quantizer-subtractive} x fs {256k, 512k} x coefficient sets.
All runs use the GF180-calibrated settling profile (kappa=1e-3 on int1,
gamma=0.086; int2/int3 ideal -- their errors are shaped, verified in
validate.py). Output: ranked CSV + stdout table with the margin breakdown
(quantization ceiling vs settling/limit-cycle contribution vs total).
"""
import numpy as np
import csv
from sdm import simulate, analyze, SettleProfile, IDEAL

GF180_INT1 = SettleProfile(gamma=0.086, kappa=1e-3)

COEFFS = {
    ('L2', 'sdm3'): (2, (2.0, 2.0, 0.5, 1.0)),
    ('L2', 'lowgain'): (2, (1.0, 1.0, 1.0, 1.0)),   # a2d1=1,d2=1: same NTF, smaller int1 steps
    ('L3', 'bw3'): (3, (2.0, 2.0, 0.5, 1.0, 1.0, 1.0)),  # NTF=(1-z^-1)^3, STF(DC)=-1
}

DITHERS = {
    'none': dict(dither_mode='none'),
    'in_sine': dict(dither_mode='input_sine', dither_amp=0.05, dither_freq=2400.0),
    'in_pn': dict(dither_mode='input_pn', dither_amp=0.05),
    'q_sub': dict(dither_mode='quantizer_sub', dither_amp=0.25),
}


def run(order, coeffs, bits, dither, fs, settle_int1):
    kw = dict(fs=fs, order=order, coeffs=coeffs, bits=bits,
              settle=(settle_int1,) + (IDEAL,) * (order - 1), **DITHERS[dither])
    y, xend = simulate(**kw)
    r = analyze(y, fs=fs)
    # quantization ceiling: same config, ideal integrators
    yi, _ = simulate(**{**kw, 'settle': (IDEAL,) * order})
    ri = analyze(yi, fs=fs)
    stable = bool(np.all(np.isfinite(y))) and abs(y.mean()) < 1.0
    p_full = 10 ** (-r['sndr'] / 10)
    p_ideal = 10 ** (-ri['sndr'] / 10)
    p_settle = max(p_full - p_ideal, 1e-30)
    sndr_settle = -10 * np.log10(p_settle)
    return dict(order=order, coeffs=bits and coeffs, bits=bits, dither=dither,
                fs=fs, sndr=r['sndr'], sndr_ideal=ri['sndr'],
                sndr_settle=sndr_settle, top_hz=r['top'][0][0],
                top_dbc=r['top'][0][1], floor=r['floor_sndr'],
                stable=stable)


def main():
    rows = []
    for (lname, cname), (order, coeffs) in COEFFS.items():
        for bits in (1, 2, 4):
            for dither in DITHERS:
                for fs in (256e3, 512e3):
                    r = run(order, coeffs, bits, dither, fs, GF180_INT1)
                    r['arch'] = f"{lname}/{cname}"
                    rows.append(r)
                    print(f"{lname}/{cname} {bits}b {dither:8s} fs={fs/1e3:5.0f}k "
                          f"SNDR={r['sndr']:7.2f} (ideal {r['sndr_ideal']:7.2f}, "
                          f"settle-lim {r['sndr_settle']:7.2f}) "
                          f"top {r['top_hz']:.1f}Hz/{r['top_dbc']:.1f}dBc "
                          f"{'' if r['stable'] else 'UNSTABLE'}", flush=True)
    rows.sort(key=lambda r: -r['sndr'])
    with open('sweep_results.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['arch', 'order', 'bits', 'dither',
                                          'fs', 'sndr', 'sndr_ideal',
                                          'sndr_settle', 'top_hz', 'top_dbc',
                                          'floor', 'stable'])
        w.writeheader()
        for r in rows:
            r2 = dict(r)
            r2['coeffs'] = ''
            w.writerow({k: r2[k] for k in w.fieldnames})
    print("\n=== TOP 15 (GF180 settling, kappa_int1=1e-3) ===")
    for r in rows[:15]:
        print(f"{r['arch']:10s} {r['bits']}b {r['dither']:8s} fs={r['fs']/1e3:5.0f}k "
              f"SNDR={r['sndr']:7.2f} dB (Q-ceiling {r['sndr_ideal']:6.1f}, "
              f"settle-lim {r['sndr_settle']:6.1f})")


if __name__ == '__main__':
    main()
