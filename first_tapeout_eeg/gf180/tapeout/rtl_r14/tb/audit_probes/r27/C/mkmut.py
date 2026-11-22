#!/usr/bin/env python3
"""mkmut.py <mutants.py> <name>: copy scratchpad/pristine to scratchpad/mut/<name> and apply the edits of MUTANTS[name]
(each text exactly once, applied in order)."""
import os, shutil, sys, runpy
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(SP, "pristine")
muts = runpy.run_path(sys.argv[1])["MUTANTS"]
name = sys.argv[2]
dst = os.path.join(SP, "mut", name)
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(SRC, dst, symlinks=True)
for f, old, new in muts[name]:
    p = os.path.join(dst, f)
    t = open(p, encoding="utf-8").read()
    if t.count(old) != 1:
        sys.exit(f"{name}: text occurs {t.count(old)} times in {f}: {old[:80]!r}")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
print(dst)
