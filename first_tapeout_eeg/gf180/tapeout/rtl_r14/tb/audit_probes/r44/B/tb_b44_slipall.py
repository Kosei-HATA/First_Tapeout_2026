"""audit round 44, B: the accepted faulted CRC reads of tb_b44_slipall (RTL) against regmap.slip_hazards."""
import sys, os, collections
sys.path.insert(0, sys.argv[1])
import regmap as R
names = {}
for a, n, acc, lock, fl, _ in R.REGS:
    if acc != "WO" and n != "SAMPLE":
        names[a] = n
    if any(f["cls"] == "apply" for f in fl):
        names[a + R.SHADOW_MIRROR] = n + ".ACT"
haz = {}
bad, n_acc, n_wrong, seen = [], 0, 0, collections.Counter()
for line in open(sys.argv[2]):
    if not line.startswith("ACC"):
        continue
    d = dict(kv.split("=") for kv in line.split()[1:])
    a, fault, k = int(d["a"], 16), int(d["fault"]), int(d["k"])
    read, true = int(d["read"], 16), int(d["true"], 16) if d["true"] not in ("xx",) else None
    dec = int(d["dec"], 16) if "x" not in d["dec"] else None
    n_acc += 1
    if read == true:
        continue
    n_wrong += 1
    key = names.get(a)
    h = 0x80 | a
    tag = f"{line.strip()} key={key}"
    if fault == 1:
        seen[("mosi", key, dec)] += 1
        if not (dec == R.smp_hdr() and a in R.WINDOW_NEIGHBOURS_REQUIRED):
            bad.append("MOSI flip accepted outside the window neighbours: " + tag)
        continue
    if key not in haz:
        haz[key] = set(R.slip_hazards(key))
    base = key.split(".")[0]
    if read not in R.reg_values(base):
        seen[("illegal", key, read)] += 1
        continue
    pair = (true, read) if dec == h else (-1, read)
    seen[(key, pair)] += 1
    if pair not in haz[key]:
        bad.append(f"pair {pair} not in slip_hazards({key}) = {sorted(haz[key])[:12]}: " + tag)
print(f"{n_acc} accepted, {n_wrong} with another value; distinct wrong pairs: {dict(seen)}")
for b in bad[:30]:
    print("NOT IN MODEL:", b)
print("PASS" if not bad else f"FAIL: {len(bad)} accepted wrong values the model does not record")
