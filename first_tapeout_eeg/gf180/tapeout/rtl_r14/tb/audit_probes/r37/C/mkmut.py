#!/usr/bin/env python3
"""audit37 C: make a mutant copy under mut/<name> from the pristine tree and apply its edits (each text exactly once)."""
import os, shutil, sys, importlib.util
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("muts", os.path.join(BASE, "tools", "muts.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
name = sys.argv[1]
edits = M.MUTS[name]
d = os.path.join(BASE, "mut", name)
shutil.rmtree(d, ignore_errors=True)
os.makedirs(os.path.join(d, "gf180"))
shutil.copytree(os.path.join(BASE, "gf180", "tapeout_pristine_ref"), os.path.join(d, "gf180", "tapeout"), symlinks=True)
shutil.copytree(os.path.join(BASE, "documentation"), os.path.join(d, "documentation"))
for rel, old, new in edits:
    p = os.path.join(d, "gf180", "tapeout", rel)
    t = open(p, encoding="utf-8").read()
    n = t.count(old)
    if n != 1:
        sys.exit(f"NOT APPLIED: {rel}: text occurs {n} times")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
shutil.copy(os.path.join(BASE, "tools", "screen.sh"), os.path.join(d, "gf180", "tapeout", "rtl_r14", "screen.sh"))
print(d)
