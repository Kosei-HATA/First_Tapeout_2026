#!/usr/bin/env python3
"""mk.py <name> : make the mutant copy <name> from MUTANTS (muts.py) of the clean audit copy (scratchpad/audit34_C) in
scratchpad/mut34C/<name>/ (rtl_r14/build left out, the external inputs kept as symlinks); each old text must occur
exactly once when its turn comes. Prints the copy's rtl_r14 path."""
import os, shutil, sys
SP = "/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad"
sys.path.insert(0, os.path.join(SP, "a34C_tools"))
from muts import MUTANTS
BASE = os.path.join(SP, "audit34_C")
name = sys.argv[1]
edits = MUTANTS[name]
dst = os.path.join(SP, "mut34C", name)
if os.path.exists(dst):
    shutil.rmtree(dst)
def ign(d, names):
    return [n for n in names if (n == "build" and os.path.basename(d) == "rtl_r14") or n == "__pycache__"]
os.makedirs(dst)
for top in ("gf180", "documentation"):
    shutil.copytree(os.path.join(BASE, top), os.path.join(dst, top), symlinks=True, ignore=ign)
assert os.path.islink(os.path.join(dst, "gf180/tapeout/rtl/build/e2e/s4.codes"))
for f, o, n in edits:
    p = os.path.join(dst, "gf180/tapeout/rtl_r14", f)
    if not os.path.exists(p):
        p = os.path.join(dst, "gf180/tapeout/rtl", f)
    t = open(p, encoding="utf-8").read()
    if t.count(o) != 1:
        shutil.rmtree(dst)
        sys.exit(f"NOT APPLIED: '{o[:80]}' occurs {t.count(o)} times in {f}")
    open(p, "w", encoding="utf-8").write(t.replace(o, n))
print(os.path.join(dst, "gf180/tapeout/rtl_r14"))
