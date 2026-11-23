import sys, collections
f = sys.argv[1]
hdr = collections.Counter(); dat = collections.Counter(); other = []
for ln in open(f):
    p = ln.split()
    if not p: continue
    if p[0] in ("HDR", "DAT"):
        kv = dict(x.split("=", 1) for x in p[1:] if "=" in x)
        (hdr if p[0] == "HDR" else dat)[(kv["phase"], kv["status"], kv["pend"], kv["cmd"])] += 1
    else:
        other.append(ln.strip())
print("header STATUS copies in an acknowledge cycle (phase, STATUS, pend, command): count")
for k, v in sorted(hdr.items()): print("  ", k, v)
print("0x03 data loads in an acknowledge cycle:")
for k, v in sorted(dat.items()): print("  ", k, v)
for o in other: print(o[:300])
