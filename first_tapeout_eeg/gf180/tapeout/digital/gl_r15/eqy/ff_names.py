#!/usr/bin/env python3
"""11/28: the match points of the eqy proof of the r15 macro's netlist against its RTL (run_eqy_r15.sh): the ports and
the flip-flops' outputs, one name per signal, nothing combinational.

Why (each found as a false counterexample on 11/28):
  * a matched combinational net is a free input of the partitions it feeds, and the netlist after it may recompute
    the same function from the registers (u_cic.dcnt with dec = 1 while dcnt != CNT_LAST; drdy_pulse with drdy_nxt != 0
    while push_ok = 0 and drdy_cnt = 0): only flip-flop outputs and ports are matched;
  * eqy's insbuf turns the names of one signal into a chain of buffers and cuts the consumers at the last matched name
    of the chain, and the chains run in different orders in the RTL and the netlist (RTL: a_azero -> u_regs.a_azero ->
    TEST_CFG[5]; netlist: the flip-flop a_azero, its output buffer TEST_CFG[5]): with two names of one signal matched,
    the two sides read different free inputs (OFS, OFM, OFEN, MISO, ... in the first runs). So each signal (a bit with
    all its aliases) gets exactly one matched name, the same on both sides, and a port where the signal has one;
  * insbuf off instead drops the matches of names that are only aliases: 16 of the 25 output ports were then compared
    nowhere (checked by check_cover() in run_eqy_r15.sh).
Renamed by the synthesis (GATE_AS_GOLD): the FIFO's words went from 48 to 44 bits (status bits 0-2, always 0, and
VALID, always 1, removed) and the rest were renumbered, so the gate's u_fifo.mem[k][40..43] hold the RTL's
u_fifo.mem[k][43..46] (ERR, CHANGED, OVL, OVERRUN): seen in the netlist (the D cones: err & r_mask -> [40], ovl_iv /
ovl_hist -> [42], dflag_overrun -> [43]) and in eqy's counterexample of the same-name pairing; eqy proves the pairing.
Flip-flops of the RTL without a counterpart (the synthesis removed them as constant or unused) stay inside the
partitions; their x initial value only makes the comparison vacuous until they are loaded.
usage: ff_names.py <gold.json> <gate.json> <out: match lines>   (yosys write_json of the two sides as eqy reads them)
"""
import json
import re
import sys
from collections import defaultdict

FF = re.compile(r"^\$(_?(S|A|AL)?DFF|_DFF|_SDFF|_DFFE|_DFFSR|_ALDFF|_SDFFE|_SDFFCE|ff|_FF_|dff|adff|sdff|dffe|adffe|"
                r"sdffe|sdffce|aldff|aldffe|dffsr|dffsre)", re.I)
GATE_AS_GOLD = [(re.compile(r"^u_fifo\.mem\[(\d+)\]\[(4[0-3])\]$"),
                 lambda m: f"u_fifo.mem[{m[1]}][{int(m[2]) + 3}]")]


def as_gold(n):
    for rx, f in GATE_AS_GOLD:
        if (m := rx.match(n)):
            return f(m)
    return n


def load(path):
    d = json.load(open(path))
    (top, m), = [(k, v) for k, v in d["modules"].items() if v.get("attributes", {}).get("top")]
    qbits = set()
    for c in m["cells"].values():
        if FF.match(c["type"]) and "Q" in c["connections"]:
            qbits.update(b for b in c["connections"]["Q"] if isinstance(b, int))
    names = {n: v["bits"] for n, v in m["netnames"].items() if not n.startswith("$") and not v.get("hide_name")}
    cls = defaultdict(set)          # bit id -> the whole names with a bit on it
    for n, b in names.items():
        for x in b:
            if isinstance(x, int):
                cls[x].add(n)
    ports = {n: p for n, p in m["ports"].items()}
    single = {n: b[0] for n, b in names.items() if len(b) == 1 and isinstance(b[0], int)}
    return dict(top=top, qbits=qbits, names=names, cls=cls, ports=ports, single=single)


def main():
    g, t = load(sys.argv[1]), load(sys.argv[2])
    assert set(g["ports"]) == set(t["ports"]), set(g["ports"]) ^ set(t["ports"])
    gate_name = {}                  # gold name -> gate name (the same, or renamed by the synthesis)
    for n in t["single"]:
        gate_name.setdefault(as_gold(n), n)
    match = {}                      # gold name -> gate name
    for p in sorted(g["ports"]):
        match[p] = p
    port_bits_g = {x for p in g["ports"] for x in g["names"][p] if isinstance(x, int)}
    port_bits_t = {x for p in t["ports"] for x in t["names"][p] if isinstance(x, int)}
    gold_only, problems = [], []
    for q in sorted(g["qbits"]):
        if q in port_bits_g:
            continue                # the signal has a port: matched by the port's name only
        cands = sorted((n for n in g["cls"][q] if n in g["single"] and n in gate_name
                        and gate_name[n] in t["single"] and t["single"][gate_name[n]] in t["qbits"]),
                       key=lambda n: (n.count("."), len(n), n))
        if not cands:
            gold_only.append(sorted(g["cls"][q]))
            continue
        n = cands[0]
        tb = t["single"][gate_name[n]]
        if tb in port_bits_t:
            problems.append(f"{n}: the gate's signal has a port the RTL's has not ({sorted(t['cls'][tb])[:4]})")
            continue
        match[n] = gate_name[n]
    # one matched name per signal on each side
    for side, s, names in (("gold", g, list(match)), ("gate", t, list(match.values()))):
        seen = defaultdict(list)
        for n in names:
            for x in s["names"][n]:
                if isinstance(x, int):
                    seen[x].append(n)
        for x, ns in seen.items():
            if len(ns) > 1:
                problems.append(f"{side}: one signal with {len(ns)} matched names: {ns}")
    unmatched_gate = [sorted(t["cls"][q])[:3] for q in sorted(t["qbits"])
                      if not any(x in match.values() for x in t["cls"][q])]
    nreg = len(match) - len(g["ports"])
    print(f"gold: {len(g['qbits'])} flip-flop bits; gate: {len(t['qbits'])} flip-flop bits")
    print(f"matched: {len(g['ports'])} ports + {nreg} flip-flop names "
          f"({sum(1 for a, b in match.items() if a != b)} renamed by the synthesis)")
    print(f"RTL flip-flops without a counterpart in the netlist: {len(gold_only)}")
    for ns in gold_only:
        print("  gold-only", " ".join(ns[:3]))
    print(f"netlist flip-flops without a matched name: {len(unmatched_gate)}")
    for ns in unmatched_gate:
        print("  gate-only", " ".join(ns))
    print(f"problems: {len(problems)}")
    for p in problems:
        print("  " + p)
    with open(sys.argv[3], "w") as f:
        for a, b in match.items():
            f.write(f"gold-match {a}\n" if a == b else f"gold-match {a} {b}\n")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
