#!/usr/bin/env python3
"""11/28: the induction step of the netlist-versus-RTL proof as one combinational miter, for a design whose every
flip-flop is matched by name (eeg_adc_dig: 146 = 146 after run_eqy_r15.sh's RTL preprocessing).

Both sides are read as yosys JSON with only $_AND_, $_NOT_ and flip-flops ($_DFF_P_, $_DFF_PN0_, $_DFF_PN1_: the
RTL after the same preprocessing as eqy's gold plus dffunmap/techmap/aigmap; the netlist with the liberty functions,
flattened, the same). Every matched register bit becomes ONE free variable S shared by the two sides (the hypothesis:
the states are equal now); the inputs are shared too. The miter compares, for every input and every shared state:
  * each register's next state (an asynchronous reset in force gives its reset value; else D), so the reset values
    are compared as well, and
  * each output port, from the current state as the asynchronous resets leave it.
If no output of the miter can be 1, the two designs stay equal from any common state on, the reset state included:
together with the reset values compared here, the netlist equals the RTL from reset (the states correspond one to
one by name). ABC decides the miter (BDDs via collapse, else SAT sweeping), so arithmetic between registers that
PDR cannot settle (the popcount of 31 lines feeding the DWA rotation) is decided as a combinational question.
usage: comb_step.py <gold.json> <gate.json> <out.aag>    (then: yosys-abc -c "read_aiger out.aag; ...")
"""
import json
import re
import sys

FF_RV = {"$_DFF_P_": None, "$_DFF_PN0_": 0, "$_DFF_PN1_": 1, "$_DFF_PP0_": 0, "$_DFF_PP1_": 1}
FF_RPOL = {"$_DFF_PN0_": 0, "$_DFF_PN1_": 0, "$_DFF_PP0_": 1, "$_DFF_PP1_": 1}


class AIG:
    def __init__(self):
        self.n = 0                 # variables
        self.inputs = []           # literals
        self.ands = []             # (lhs, a, b)
        self.memo = {}

    def var(self):
        self.n += 1
        return 2 * self.n

    def inp(self):
        v = self.var()
        self.inputs.append(v)
        return v

    def AND(self, a, b):
        if a == 0 or b == 0:
            return 0
        if a == 1:
            return b
        if b == 1:
            return a
        if a == b:
            return a
        if a == (b ^ 1):
            return 0
        k = (min(a, b), max(a, b))
        if k in self.memo:
            return self.memo[k]
        v = self.var()
        self.ands.append((v, k[0], k[1]))
        self.memo[k] = v
        return v

    def OR(self, a, b):
        return self.AND(a ^ 1, b ^ 1) ^ 1

    def XOR(self, a, b):
        return self.OR(self.AND(a, b ^ 1), self.AND(a ^ 1, b))

    def MUX(self, s, a1, a0):
        return self.OR(self.AND(s, a1), self.AND(s ^ 1, a0))


def load(path):
    d = json.load(open(path))
    (m,) = [v for v in d["modules"].values() if v.get("attributes", {}).get("top")]
    names = {n: v["bits"] for n, v in m["netnames"].items() if not n.startswith("$")}
    byname = {}
    for n, b in names.items():
        if len(b) == 1 and isinstance(b[0], int):
            byname.setdefault(n, b[0])
        for i, x in enumerate(b):
            if isinstance(x, int):
                byname.setdefault(f"{n}[{i}]", x)
    drv, ffs = {}, {}
    for cn, c in m["cells"].items():
        t, con = c["type"], c["connections"]
        if t in ("$_AND_", "$_NOT_"):
            drv[con["Y"][0]] = (t, con)
        elif t in FF_RV:
            ffs[con["Q"][0]] = (t, con)
        elif t == "$scopeinfo":
            continue
        else:
            raise SystemExit(f"{path}: unexpected cell type {t} ({cn})")
    ports = {n: (p["direction"], p["bits"]) for n, p in m["ports"].items()}
    return dict(names=names, byname=byname, drv=drv, ffs=ffs, ports=ports)


def build(side, aig, pin, state):
    """literal of every bit of a side: inputs and shared states given; returns a resolver."""
    cache = {}

    def lit(b):
        if b == "0":
            return 0
        if b == "1":
            return 1
        if b == "x" or b == "z":
            raise SystemExit("undefined constant in the logic")
        if b in cache:
            return cache[b]
        if b in pin:
            r = pin[b]
        elif b in side["ffs"]:
            t, con = side["ffs"][b]
            s = state[b]
            rv = FF_RV[t]
            if rv is None:
                r = s
            else:                  # the asynchronous reset in force overrides the stored value
                act = lit(con["R"][0]) ^ (1 if FF_RPOL[t] == 0 else 0)     # 1 when the reset is active
                r = aig.MUX(act, 1 if rv else 0, s)
        elif b in side["drv"]:
            t, con = side["drv"][b]
            if t == "$_NOT_":
                r = lit(con["A"][0]) ^ 1
            else:
                r = aig.AND(lit(con["A"][0]), lit(con["B"][0]))
        else:
            raise SystemExit(f"undriven bit {b}")
        cache[b] = r
        return r
    return lit


def next_state(side, lit, aig, q):
    t, con = side["ffs"][q]
    d = lit(con["D"][0])
    rv = FF_RV[t]
    if rv is None:
        return d
    act = lit(con["R"][0]) ^ (1 if FF_RPOL[t] == 0 else 0)
    return aig.MUX(act, 1 if rv else 0, d)


def main():
    g, t = load(sys.argv[1]), load(sys.argv[2])
    assert set(g["ports"]) == set(t["ports"])
    # the register correspondence: a public single-bit name on a flip-flop's Q in both
    def regnames(s):
        out = {}
        for n, b in s["byname"].items():
            if b in s["ffs"]:
                out.setdefault(b, set()).add(n)
        return out
    gq, tq = regnames(g), regnames(t)
    tq_of = {}
    for b, ns in tq.items():
        for n in ns:
            tq_of[n] = b
    pairs, unmatched = [], []
    for b, ns in sorted(gq.items()):
        cand = sorted(n for n in ns if n in tq_of)
        if cand:
            pairs.append((b, tq_of[cand[0]], cand[0]))
        else:
            unmatched.append(sorted(ns)[0])
    gate_used = {p[1] for p in pairs}
    t_unm = [sorted(tq[b])[0] for b in tq if b not in gate_used]
    if unmatched or t_unm or len(pairs) != len(g["ffs"]) or len(gate_used) != len(t["ffs"]):
        raise SystemExit(f"not a one-to-one register correspondence: gold-only {unmatched[:5]}, gate-only {t_unm[:5]}")
    aig = AIG()
    pin_g, pin_t, names_in = {}, {}, []
    for n, (d, bits) in sorted(g["ports"].items()):
        if d != "input":
            continue
        tb = t["ports"][n][1]
        for i, (x, y) in enumerate(zip(bits, tb)):
            v = aig.inp()
            names_in.append(f"{n}[{i}]")
            pin_g[x] = v
            pin_t[y] = v
    st_g, st_t = {}, {}
    for gb, tb, n in pairs:
        v = aig.inp()
        names_in.append(f"S:{n}")
        st_g[gb] = v
        st_t[tb] = v
    lg, lt = build(g, aig, pin_g, st_g), build(t, aig, pin_t, st_t)
    outs, onames = [], []
    for gb, tb, n in pairs:
        outs.append(aig.XOR(next_state(g, lg, aig, gb), next_state(t, lt, aig, tb)))
        onames.append(f"next:{n}")
    for n, (d, bits) in sorted(g["ports"].items()):
        if d != "output":
            continue
        for i, (x, y) in enumerate(zip(bits, t["ports"][n][1])):
            outs.append(aig.XOR(lg(x), lt(y)))
            onames.append(f"out:{n}[{i}]")
    with open(sys.argv[3], "w") as f:
        f.write(f"aag {aig.n} {len(aig.inputs)} 0 {len(outs)} {len(aig.ands)}\n")
        for v in aig.inputs:
            f.write(f"{v}\n")
        for o in outs:
            f.write(f"{o}\n")
        for lhs, a, b in aig.ands:
            f.write(f"{lhs} {b} {a}\n")
        for i, n in enumerate(names_in):
            f.write(f"i{i} {n}\n")
        for i, n in enumerate(onames):
            f.write(f"o{i} {n}\n")
    const = sum(1 for o in outs if o == 0)
    print(f"{len(pairs)} register bits shared, {len(names_in) - len(pairs)} input bits; {len(outs)} miter outputs "
          f"({const} already constant 0), {len(aig.ands)} AND gates -> {sys.argv[3]}")


if __name__ == "__main__":
    main()
