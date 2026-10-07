#!/usr/bin/env python3
"""Validation of sdm.py against measured SPICE results.

Claims checked (documentation/gf180_feasibility.md §6, enob18_study.md §4):
 1. ideal discrete ceiling:            ~123.3 dB (ENOB18 same-record) 
 2. GF180 CMFB-fixed full run:         69.65 dB  -> kappa_int1 ~ 1e-3
 3. sky130 final full run:             91.68 dB  -> kappa_int1 in 3e-5..1e-4 cloud
 4. comparator hysteresis is benign:   icmp experiment (61.23 dB short = floor
    unmoved by ideal comparator) -> model: threshold hysteresis does NOT
    generate the comb
 5. int2 nonlinearity is shaped (only int1 matters)
 6. constant creep fraction (gamma) alone is a benign coefficient error
"""
from sdm import simulate, analyze, SettleProfile, IDEAL

rows = []
def run(name, **kw):
    y, _ = simulate(**kw)
    r = analyze(y)
    rows.append((name, r))
    print(f"{name:38s} SNDR={r['sndr']:7.2f} dB  top={r['top'][0][0]:6.1f} Hz "
          f"/ {r['top'][0][1]:6.1f} dBc")

run("1. ideal L2 1bit (expect ~123.3)")
k1 = SettleProfile(kappa=1e-3)
run("2. GF180 kappa=1e-3 int1 (expect ~69.7)", settle=(k1, IDEAL))
run("3a. sky130-ish kappa=3e-5 (expect ~92)", settle=(SettleProfile(kappa=3e-5), IDEAL))
run("3b. sky130-ish kappa=1e-4", settle=(SettleProfile(kappa=1e-4), IDEAL))
run("4. comparator hyst=1e-3 (expect benign)", cmp_hyst=1e-3)
run("5. kappa=1e-3 on int2 only (expect benign)", settle=(IDEAL, k1))
run("6. gamma=0.086 only (expect benign)", settle=(SettleProfile(gamma=0.086), IDEAL))
