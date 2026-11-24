import os, sys, importlib.util
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("muts", os.path.join(B, "tools", "muts.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
name, d = sys.argv[1], sys.argv[2]
for rel, old, new in M.MUTS[name]:
    p = os.path.join(d, "gf180", "tapeout", rel)
    t = open(p, encoding="utf-8").read()
    n = t.count(old)
    if n != 1:
        sys.exit(f"NOT APPLIED: {rel}: text occurs {n} times")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
    print("applied", rel)
