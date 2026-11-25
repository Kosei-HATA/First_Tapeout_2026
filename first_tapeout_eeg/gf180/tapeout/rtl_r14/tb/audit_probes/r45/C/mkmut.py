#!/usr/bin/env python3
"""Audit 45, auditor C: make one mutant copy of the r14 RTL + tests (from the audit copy audit45_C) and apply edits.
Usage: mkmut.py <tag>   (edits from muts.py MUTS[tag]: list of (file relative to gf180/tapeout, old, new))
The copy: a45C_mut/<tag>/{gf180/tapeout/rtl, gf180/tapeout/rtl_r14 (no build), documentation, inputs linked}."""
import os, shutil, sys
SCR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(SCR, "audit45_C")
REPO = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from muts import MUTS  # noqa: E402

tag = sys.argv[1]
dst = os.path.join(SCR, "a45C_mut", tag)
shutil.rmtree(dst, ignore_errors=True)
os.makedirs(os.path.join(dst, "gf180", "tapeout"))
ign = shutil.ignore_patterns("build", "__pycache__")
shutil.copytree(os.path.join(SRC, "gf180", "tapeout", "rtl"), os.path.join(dst, "gf180", "tapeout", "rtl"), ignore=ign)
shutil.copytree(os.path.join(SRC, "gf180", "tapeout", "rtl_r14"), os.path.join(dst, "gf180", "tapeout", "rtl_r14"),
                ignore=ign)
shutil.copytree(os.path.join(SRC, "documentation"), os.path.join(dst, "documentation"))
e2e = os.path.join(dst, "gf180", "tapeout", "rtl", "build", "e2e")
os.makedirs(e2e)
for f in ("s4.codes", "s20.codes"):
    os.symlink(os.path.join(REPO, "gf180/tapeout/rtl/build/e2e", f), os.path.join(e2e, f))
for r in ("typical_ov2.5V_150u_then_dc-39mV_300u", "typical_ov2.5V_50u_rec60u_f20k_a0.28"):
    d = os.path.join(dst, "gf180/tapeout/pex/runs/adc_overload_r12", r)
    os.makedirs(d)
    os.symlink(os.path.join(REPO, "gf180/tapeout/pex/runs/adc_overload_r12", r, "out.csv"), os.path.join(d, "out.csv"))
for f, old, new in MUTS[tag]:
    p = os.path.join(dst, "gf180", "tapeout", f)
    t = open(p, encoding="utf-8").read()
    n = t.count(old)
    if n != 1:
        sys.exit(f"NOT APPLIED: {f}: the text occurs {n} times")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
print(f"made {dst}")
