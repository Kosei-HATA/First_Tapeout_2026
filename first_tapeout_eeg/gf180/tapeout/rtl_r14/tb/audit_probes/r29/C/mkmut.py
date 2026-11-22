#!/usr/bin/env python3
"""mkmut.py <mutants.py> <name>: a fresh copy of the pristine 85a64db3 sources (git archive) in ../mut/<name>/ with
the external inputs linked, and the edits of MUTANTS[name] applied (each old text exactly once, in order)."""
import os, runpy, shutil, subprocess, sys
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg"
muts = runpy.run_path(sys.argv[1])["MUTANTS"]
name = sys.argv[2]
dst = os.path.join(SP, "mut", name)
if os.path.exists(dst):
    shutil.rmtree(dst)
os.makedirs(dst)
a = subprocess.run(["git", "-C", REPO, "archive", "85a64db3", "gf180/tapeout/rtl", "gf180/tapeout/rtl_r14",
                    "documentation/gf180_digital_control_requirements_20261119.md",
                    "documentation/gf180_digital_control_spec_20261119.md"], capture_output=True, check=True)
subprocess.run(["tar", "-x"], input=a.stdout, cwd=dst, check=True)
os.makedirs(os.path.join(dst, "gf180/tapeout/rtl/build/e2e"))
for f in ("s4.codes", "s20.codes"):
    os.symlink(f"{REPO}/gf180/tapeout/rtl/build/e2e/{f}", os.path.join(dst, "gf180/tapeout/rtl/build/e2e", f))
for R in ("typical_ov2.5V_150u_then_dc-39mV_300u", "typical_ov2.5V_50u_rec60u_f20k_a0.28"):
    d = os.path.join(dst, "gf180/tapeout/pex/runs/adc_overload_r12", R)
    os.makedirs(d)
    os.symlink(f"{REPO}/gf180/tapeout/pex/runs/adc_overload_r12/{R}/out.csv", os.path.join(d, "out.csv"))
for f, old, new in muts[name]:
    p = os.path.join(dst, f)
    t = open(p, encoding="utf-8").read()
    if t.count(old) != 1:
        sys.exit(f"{name}: the text occurs {t.count(old)} times in {f}: {old[:80]!r}")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
print(dst)
