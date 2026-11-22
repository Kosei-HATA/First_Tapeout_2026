import re, sys
# usage: dgrep.py PATTERN WIDTH FILE...
pat, w = sys.argv[1], int(sys.argv[2])
for p in sys.argv[3:]:
    txt = open(p, encoding="utf-8").read()
    lines = txt.split("\n")
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(pat, ln):
            a, b = max(0, m.start() - w), min(len(ln), m.end() + w)
            print(f"{p.split('/')[-1]}:{i}: ...{ln[a:b]}...")
