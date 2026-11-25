#!/usr/bin/env python3
"""Audit 45, auditor C: single edits of fsm_spec.TIMING (every field and entry +-1 or a neighbour value) through
fsm_spec.run_checks, regmap.check and wave.check (in one process; the modules share fsm_spec's TIMING)."""
import copy, os, sys
SPEC, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F  # noqa: E402
import regmap as RM  # noqa: E402
import wave as W  # noqa: E402
T0 = copy.deepcopy(F.TIMING)


def all_checks():
    a = F.run_checks(verbose=False)[0]
    b = RM.check(verbose=False)
    c = W.check()
    return a, b, c


assert not any(all_checks())


def edits():
    T = T0
    for k, v in T.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            for d in (-1, 1):
                yield f"{k} {v}->{v + d}", (k, v + d)
            if isinstance(v, float):
                for f in (0.5, 2.0):
                    yield f"{k} {v}->{v * f}", (k, v * f)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                for nv in (x - 1, x + 1, x * 2, x // 2):
                    v2 = list(v); v2[i] = nv
                    yield f"{k}[{i}] {x}->{nv}", (k, v2)
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    for k3, v3 in vv.items():
                        for nv in (v3 - 1, v3 + 1):
                            d2 = copy.deepcopy(v); d2[kk][k3] = nv
                            yield f"{k}.{kk}.{k3} {v3}->{nv}", (k, d2)
                elif isinstance(vv, tuple):
                    for i, x in enumerate(vv):
                        for f in (0.5, 0.99, 1.01, 2.0):
                            d2 = copy.deepcopy(v); t2 = list(vv); t2[i] = x * f; d2[kk] = tuple(t2)
                            yield f"{k}.{kk}[{i}] {x}->{x * f}", (k, d2)
                elif isinstance(vv, str):
                    d2 = copy.deepcopy(v); d2[kk] = vv + "（変）"
                    yield f"{k}.{kk} label +suffix", (k, d2)
                    if kk + 1 not in v:
                        d3 = copy.deepcopy(v); d3[kk + 1] = d3.pop(kk)
                        yield f"{k}: {kk} -> {kk + 1}", (k, d3)


n = npass = 0
with open(OUT, "w") as fo:
    for txt, (k, v) in edits():
        n += 1
        F.TIMING[k] = v
        try:
            try:
                a, b, c = all_checks()
                ok = not a and not b and not c
            except Exception as ex:   # noqa: BLE001
                ok = False
            if ok:
                npass += 1
                fo.write(f"PASS {txt}\n"); fo.flush()
        finally:
            F.TIMING.clear(); F.TIMING.update(copy.deepcopy(T0))
    fo.write(f"# {n} edits, {npass} pass\n")
print(n, npass)
