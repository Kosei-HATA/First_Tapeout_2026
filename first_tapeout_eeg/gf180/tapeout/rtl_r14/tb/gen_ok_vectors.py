#!/usr/bin/env python3
"""cfg_ok / nr_ok vectors for tb_regs, generated from the specification (gf180/tapeout/rtl/spec/regmap.py cfg_ok,
nr_ok, the field layout and the legal values), not from the RTL (audit round 4, 11/20: no test moved the high bits of
M, OFF_M_H = M[9:8]; a copy that took the step from M[7:0] alone, and one that also required M[9:8] unchanged,
passed every test).

build/ok_vectors.txt:
  line 1: the number of registers that hold applied fields, then their addresses (hex)
  then one vector per line: the active registers' bytes, the shadow registers' bytes (same order), cfg_ok, nr_ok
The bench writes the active bytes, applies (shadow -> active), writes the shadow bytes and compares eeg_regs's cfg_ok
and nr_ok with the expected values.

Vectors: every pair of M in a boundary set (0, 1, 2, 126..129, 254..258, 510..514, 766..769, 1021..1023) with both
signs and every range, the shadow one or two steps away, across the byte boundaries, with only M_H or only M_L
changed, with the sign flipped, with the range changed, and with one other applied field changed; and random pairs.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/gen_ok_vectors.py
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import regmap as RM  # noqa: E402

OUT = os.path.join(HERE, "..", "build", "ok_vectors.txt")

FIELDS = [(a, f) for a, _n, _acc, _lock, f in RM.all_fields() if f["cls"] == "apply"]
ADDRS = sorted({a for a, _ in FIELDS})
LEGAL = {f["name"]: list(f["legal"]) for _, f in FIELDS}
RESET = {f["name"]: f["reset"] for _, f in FIELDS}
OTHERS = [f["name"] for _, f in FIELDS if f["name"] not in ("M_H", "M_L", "SIGN", "RANGE")]


def model(d):
    """regmap's view: M instead of M_H / M_L."""
    m = {k: v for k, v in d.items() if k not in ("M_H", "M_L")}
    m["M"] = (d["M_H"] << 8) | d["M_L"]
    return m


def with_m(d, m, s=None):
    out = dict(d, M_H=m >> 8, M_L=m & 0xFF)
    if s is not None:
        out["SIGN"] = s
    return out


def regbytes(d):
    b = {a: 0 for a in ADDRS}
    for a, f in FIELDS:
        b[a] |= (d[f["name"]] & ((1 << (f["msb"] - f["lsb"] + 1)) - 1)) << f["lsb"]
    return [b[a] for a in ADDRS]


def vectors():
    rnd = random.Random(20261120)
    out = []

    def add(ac, sh):
        out.append((ac, sh, RM.cfg_ok(model(sh)), RM.nr_ok(model(sh), model(ac))))

    ms = sorted({0, 1, 2, 126, 127, 128, 129, 254, 255, 256, 257, 258, 510, 511, 512, 513, 514, 766, 767, 768, 769,
                 1021, 1022, 1023})
    for r in range(5):
        for m in ms:
            for s in (0, 1):
                ac = with_m(dict(RESET, RANGE=r), m, s)
                for d in (0, 1, -1, 2, -2, 255, -255, 256, -256, 257, -257):
                    m2 = m + d
                    if 0 <= m2 <= 1023:
                        add(ac, with_m(ac, m2))
                if m >> 8 != 3:
                    add(ac, dict(ac, M_H=(m >> 8) + 1))      # only M_H changed (256 steps)
                if m >> 8:
                    add(ac, dict(ac, M_H=(m >> 8) - 1))
                add(ac, dict(ac, M_L=(m & 0xFF) ^ 0x01))     # only M_L's last bit
                add(ac, dict(ac, SIGN=1 - s))                 # the sign flipped (one step only from M 0 or 1)
                add(ac, with_m(ac, 1, 1 - s) if m == 0 else with_m(ac, m))
                for r2 in range(5):
                    if r2 != r:
                        add(ac, dict(ac, RANGE=r2))
                        add(ac, with_m(dict(ac, RANGE=r2), min(m + 1, 1023)))
    base = with_m(dict(RESET, RANGE=4), 300, 0)
    for f in OTHERS:                                          # one other applied field changed, with and without a step
        for v in LEGAL[f]:
            if v != base[f]:
                add(base, dict(base, **{f: v}))
                add(base, with_m(dict(base, **{f: v}), 301))
    for _ in range(4000):                                     # random pairs, mostly near each other
        ac = {f: rnd.choice(LEGAL[f]) for f in LEGAL}
        k = rnd.random()
        if k < 0.4:
            m = ((ac["M_H"] << 8) | ac["M_L"]) + rnd.choice((-257, -256, -255, -2, -1, 0, 1, 2, 255, 256, 257))
            sh = with_m(ac, min(max(m, 0), 1023), rnd.choice((ac["SIGN"], ac["SIGN"], 1 - ac["SIGN"])))
        elif k < 0.6:
            f = rnd.choice(list(LEGAL))
            sh = dict(ac, **{f: rnd.choice(LEGAL[f])})
        else:
            sh = {f: rnd.choice(LEGAL[f]) for f in LEGAL}
        add(ac, sh)
    return out


def main():
    vs = vectors()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fo:
        fo.write(f"{len(ADDRS)} " + " ".join(f"{a:02x}" for a in ADDRS) + "\n")
        for ac, sh, c, n in vs:
            fo.write(" ".join(f"{b:02x}" for b in regbytes(ac) + regbytes(sh)) + f" {int(c)} {int(n)}\n")
    nc = sum(1 for v in vs if v[2])
    nn = sum(1 for v in vs if v[3])
    print(f"wrote {os.path.relpath(OUT, os.path.join(HERE, '..'))}: {len(vs)} vectors over {len(ADDRS)} registers "
          f"(cfg_ok {nc}, nr_ok {nn})")


if __name__ == "__main__":
    main()
