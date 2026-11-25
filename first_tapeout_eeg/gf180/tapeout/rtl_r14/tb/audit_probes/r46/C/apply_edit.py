# usage: python3 apply_edit.py <copy dir> <edit file (python: EDITS = [(relpath under gf180/tapeout, old, new), ...])>
import sys, os
d, ef = sys.argv[1], sys.argv[2]
ns = {}
exec(open(ef).read(), ns)
for rel, old, new in ns["EDITS"]:
    p = os.path.join(d, "gf180", "tapeout", rel)
    t = open(p).read()
    n = t.count(old)
    if n != 1:
        sys.exit(f"edit not applied: {rel}: the text occurs {n} times")
    open(p, "w").write(t.replace(old, new))
    print(f"applied to {rel}")
