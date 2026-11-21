#!/usr/bin/env python3
"""Make one mutant copy: mkmut.py NAME  (edits from mutants.py). Extracts the pristine tree into scratchpad/mut/NAME,
applies the edits (each text must occur exactly once), installs run_first_fail.sh in its rtl_r14."""
import os, sys, shutil, subprocess
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SP, "tools"))
from mutants import MUTANTS
name = sys.argv[1]
desc, edits = MUTANTS[name]
d = os.path.join(SP, "mut", name)
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d)
subprocess.run(["tar", "-xf", os.path.join(SP, "pristine_audit24_C.tar"), "-C", d], check=True)
for f, old, new in edits:
    p = os.path.join(d, f)
    t = open(p, encoding="utf-8").read()
    if t.count(old) != 1:
        sys.exit(f"{name}: text occurs {t.count(old)} times in {f}")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
shutil.copy(os.path.join(SP, "tools", "run_first_fail.sh"), os.path.join(d, "gf180/tapeout/rtl_r14/run_first_fail.sh"))
print(d)
