#!/usr/bin/env python3
"""Make a mutant copy of the audit copy: mkmut.py <name> <file under rtl_r14 or rtl> <old> <new> [<old2> <new2> ...]
(each old text must occur exactly once). The copy is scratchpad/mut/<name>/ (gf180 + documentation, build/ left out)."""
import os, shutil, sys
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(SP, "audit32_C")
name, f = sys.argv[1], sys.argv[2]
pairs = sys.argv[3:]
dst = os.path.join(SP, "mut", name)
if os.path.exists(dst):
    sys.exit(f"{dst} exists")
def ign(d, names):
    return [n for n in names if n == "build" and os.path.basename(d) == "rtl_r14"] + \
           [n for n in names if n == "__pycache__"]
os.makedirs(dst)
for top in ("gf180", "documentation"):
    shutil.copytree(os.path.join(BASE, top), os.path.join(dst, top), symlinks=True, ignore=ign)
# the e2e codes dir under rtl/build is a link folder: keep it (copied above with symlinks); make sure it is there
assert os.path.islink(os.path.join(dst, "gf180/tapeout/rtl/build/e2e/s4.codes"))
p = os.path.join(dst, "gf180/tapeout/rtl_r14", f)
if not os.path.exists(p):
    p = os.path.join(dst, "gf180/tapeout/rtl", f)
t = open(p, encoding="utf-8").read()
for o, n in zip(pairs[0::2], pairs[1::2]):
    if t.count(o) != 1:
        sys.exit(f"'{o}' occurs {t.count(o)} times in {f}")
    t = t.replace(o, n)
open(p, "w", encoding="utf-8").write(t)
print(f"made {dst}: {f} edited")
