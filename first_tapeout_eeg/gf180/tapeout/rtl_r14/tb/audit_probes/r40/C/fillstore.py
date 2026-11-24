"""audit40 C: from tb_top_r14's golden log (build/top_r14_cic.log) and sample log (top_r14_samples.log): for every
store, whether it is FILL's store (the third output after a clear) and the flags at the store; then which of those
stored samples were read and compared (the sample log). Reports how many compared samples are FILL stores / RUN
stores, with OVERRUN=1, with ERR(ALERT)=1."""
import sys, os
B = sys.argv[1]
clears, stores = [], {}
for ln in open(os.path.join(B, "top_r14_cic.log")):
    f = ln.split()
    if f[0] == "O" and f[2] == "1":
        clears.append(int(f[1]))
    elif f[0] == "S":
        stores[int(f[1])] = tuple(int(x) for x in f[2:6])
fill = {c + 3 for c in clears}
read = {}
for ln in open(os.path.join(B, "top_r14_samples.log")):
    s, d, st = map(int, ln.split())
    read[s] = st
cnt = {}
for s, (err, mask, dfl, mskd) in stores.items():
    kind = "FILL" if s in fill else "RUN"
    ovr = dfl & 1            # DFLAG.OVERRUN at bit 0 (checked below against the map)
    alert = int(bool((err & mask) | (dfl & mskd)))
    key = (kind, "read" if s in read else "unread", ovr, alert)
    cnt[key] = cnt.get(key, 0) + 1
for k in sorted(cnt):
    print(k, cnt[k])
print("clears", len(clears), "stores", len(stores), "read", len(read))
