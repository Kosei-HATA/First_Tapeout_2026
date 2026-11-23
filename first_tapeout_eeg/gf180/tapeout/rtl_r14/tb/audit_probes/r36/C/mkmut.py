#!/usr/bin/env python3
"""Audit 36, auditor C: make a mutant copy. usage: mkmut.py <name>
Copies ../audit36_C/gf180 (without rtl_r14/build) to ../audit36_C_mut/<name>/gf180 and applies MUTANTS[name]
(file relative to rtl_r14, old text occurring exactly once, new text). Prints the edited file names (basename)."""
import os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from muts import MUTANTS
name = sys.argv[1]
src = os.path.normpath(os.path.join(HERE, "..", "audit36_C", "gf180"))
dst_root = os.path.normpath(os.path.join(HERE, "..", "audit36_C_mut", name))
if os.path.exists(dst_root):
    shutil.rmtree(dst_root)
os.makedirs(dst_root)
subprocess.run(["rsync", "-a", "--exclude", "tapeout/rtl_r14/build", src, dst_root + "/"], check=True)
subprocess.run(["rsync", "-a", os.path.join(os.path.dirname(src), "documentation"), dst_root + "/"], check=True)
r14 = os.path.join(dst_root, "gf180", "tapeout", "rtl_r14")
edited = []
texts = {}
for f, old, new in MUTANTS[name]:
    p = os.path.normpath(os.path.join(r14, f))
    t = texts.get(p) or open(p, encoding="utf-8").read()
    n = t.count(old)
    if n != 1:
        sys.exit(f"NOT APPLIED: {f}: the text occurs {n} times")
    texts[p] = t.replace(old, new)
    edited.append(os.path.basename(p))
for p, t in texts.items():
    open(p, "w", encoding="utf-8").write(t)
print(" ".join(sorted(set(edited))))
