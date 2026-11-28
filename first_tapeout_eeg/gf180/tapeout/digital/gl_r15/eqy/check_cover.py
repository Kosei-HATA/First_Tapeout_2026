#!/usr/bin/env python3
"""11/28: every match point of the eqy run (run_eqy_r15.sh) is compared: each bit of each matched name other than an
input port is a partition output ("Adding output bit" in eqy's partition.log), so no port or register is left out
silently (insbuf off dropped 16 of the 25 output ports, 11/28).
usage: check_cover.py <gold.json> <match.txt> <eqy work dir>"""
import json
import re
import sys

gold = json.load(open(sys.argv[1]))
(m,) = [v for v in gold["modules"].values() if v.get("attributes", {}).get("top")]
inputs = {n for n, p in m["ports"].items() if p["direction"] == "input"}
outputs = {n: len(p["bits"]) for n, p in m["ports"].items() if p["direction"] == "output"}
added = set(re.findall(r"^Adding output bit \\(\S+)(?: \[(\d+)\])?(?: to partition)", open(sys.argv[3] + "/partition.log").read(), re.M))
added = {(n, int(i) if i else None) for n, i in added}
want, missing = 0, []
for ln in open(sys.argv[2]):
    n = ln.split()[1]
    if n in inputs:
        continue
    w = outputs.get(n, 1)
    for i in range(w):
        want += 1
        key = (n, i if n in outputs and w > 1 else None)
        if key not in added and not (w == 1 and (n, 0) in added):
            missing.append(f"{n}[{i}]" if w > 1 else n)
nout = sum(outputs.values())
cov_out = [n for n in outputs if all(((n, i if outputs[n] > 1 else None) in added or (n, 0) in added) for i in range(outputs[n]))]
print(f"compare points: {want - len(missing)} of {want} matched bits are partition outputs; "
      f"output ports compared: {len(cov_out)} of {len(outputs)} ({nout} bits)")
for x in missing[:40]:
    print("  not compared:", x)
sys.exit(1 if missing or len(cov_out) != len(outputs) else 0)
