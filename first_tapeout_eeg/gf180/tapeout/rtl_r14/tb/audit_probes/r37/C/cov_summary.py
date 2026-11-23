import sys, collections
f = sys.argv[1]
ST = {0: "IDLE", 1: "WARMUP", 2: "RECOVER", 3: "WAIT_E", 4: "ALIGN", 5: "FILL", 6: "RUN", 7: "PRE", 8: "PULSE"}
CMD = {0x11: "START", 0x22: "STOP", 0x33: "APPLY", 0x44: "APPLY_NR", 0x55: "FLUSH"}
FIELDS = ["m", "sign", "range", "ibias", "cpf", "bp", "bn", "fast", "dwa", "c1", "blank", "atpen", "atpsel", "cstop", "azero"]
app = collections.defaultdict(lambda: collections.Counter())
napp = collections.Counter()
wr = collections.defaultdict(collections.Counter)
ack = collections.Counter()
for ln in open(f):
    p = ln.split()
    if not p:
        continue
    kv = dict(x.split("=", 1) for x in p[1:] if "=" in x)
    if p[0] == "APPLY" and "azero" not in kv: continue
    if p[0] in ("WRITE", "ACK") and len(kv) < 8: continue
    if p[0] == "APPLY":
        key = (CMD.get(int(kv["cmd"], 16), kv["cmd"]), ST.get(int(kv["st"]), kv["st"]))
        napp[key] += 1
        for fl in FIELDS:
            if kv[fl] == "1":
                app[key][fl] += 1
    elif p[0] == "WRITE":
        if kv["ok"] == "1":
            wr[int(kv["a"], 16)][ST.get(int(kv["st"]), kv["st"])] += 1
    elif p[0] == "ACK":
        out = "apply" if kv["apply"] == "1" else "serr" if kv["serr"] == "1" else "cerr" if kv["cerr"] == "1" else ("flush" if kv["flush"] == "1" else "none")
        ack[(CMD.get(int(kv["cmd"], 16), kv["cmd"]), ST.get(int(kv["st"]), kv["st"]), out)] += 1
print("== applies: (command, state): count; fields that differed (shadow != active) at least once [and never]")
for key in sorted(napp):
    seen = app[key]
    print(f"{key}: {napp[key]}; differed: " + ", ".join(f"{k}:{seen[k]}" for k in FIELDS if seen[k]) + "  | never: " + ",".join(k for k in FIELDS if not seen[k]))
print("== accepted writes to timers by state")
for a in (0x50, 0x51, 0x52, 0x53, 0x54):
    print(hex(a), dict(wr[a]))
print("== accepted writes to shadows by state (0x20-0x28, 0x60, 0x61)")
for a in list(range(0x20, 0x29)) + [0x60, 0x61, 0x62]:
    print(hex(a), dict(wr[a]))
print("== acknowledged commands")
for k in sorted(ack):
    print(k, ack[k])
