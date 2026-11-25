"""Single field edits of regmap.REGS through regmap.check(); passing edits listed with the generated artifacts they
change (defs/pkg text), so equivalence can be judged."""
import copy, sys, os, io, contextlib, time
SPEC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as RM
import numpy as np
_c = {}
_ff, _isin, _conv = np.fromfile, np.isin, np.convolve
def _fromfile(p, dtype=None, **k):              # the full-scale streams: read once (they do not depend on REGS)
    key = ("ff", p, str(dtype))
    if key not in _c:
        _c[key] = _ff(p, dtype=dtype, **k)
    return _c[key]
def _isin2(a, b, **k):
    if getattr(a, "size", 0) > 1000000:
        key = ("isin", a.size, int(a[:1000].sum()), tuple(np.atleast_1d(b).tolist()))
        if key not in _c:
            _c[key] = _isin(a, b, **k)
        return _c[key]
    return _isin(a, b, **k)
def _conv2(a, v, mode="full"):
    if getattr(a, "size", 0) > 1000000:
        key = ("conv", a.size, int(a.sum()), int(np.asarray(v).size), mode)
        if key not in _c:
            _c[key] = _conv(a, v, mode=mode)
        return _c[key]
    return _conv(a, v, mode=mode)
np.fromfile, np.isin, np.convolve = _fromfile, _isin2, _conv2
ORIG = copy.deepcopy(RM.REGS)

def run():
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            return RM.check(verbose=False)
        except Exception as ex:
            return ["CRASH " + repr(ex)[:100]]

def artifacts():
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return (RM.sv_defs(), RM.sv_package(), RM.md_tables())
    except Exception as ex:
        return ("ERR", repr(ex))

base_art = artifacts()
CLASSES = ["ro", "w1c", "apply", "imm", "cmd"]
PINS = sorted({f["pin"] for r in ORIG for f in r[4] if f["pin"]})
def edits():
    for ri, (a, n, acc, lock, fields, desc) in enumerate(ORIG):
        for acc2 in ("RO", "W1C", "RW", "WO"):
            if acc2 != acc:
                yield (n, f"access {acc}->{acc2}", lambda R, ri=ri, acc2=acc2: R.__setitem__(ri, (R[ri][0], R[ri][1], acc2, R[ri][3], R[ri][4], R[ri][5])))
        yield (n, f"lock {lock}->{not lock}", lambda R, ri=ri: R.__setitem__(ri, (R[ri][0], R[ri][1], R[ri][2], not R[ri][3], R[ri][4], R[ri][5])))
        for fi, f in enumerate(fields):
            fn = f["name"]
            w = f["msb"] - f["lsb"] + 1
            def setf(R, ri=ri, fi=fi, **kv):
                R[ri][4][fi].update(kv)
            for d in (-1, 1):
                if 0 <= f["lsb"] + d and f["msb"] + d <= 7:
                    yield (f"{n}.{fn}", f"shift {d:+d}", lambda R, ri=ri, fi=fi, d=d: R[ri][4][fi].update(msb=R[ri][4][fi]["msb"] + d, lsb=R[ri][4][fi]["lsb"] + d))
            if f["msb"] < 7:
                yield (f"{n}.{fn}", "msb+1", lambda R, ri=ri, fi=fi: R[ri][4][fi].update(msb=R[ri][4][fi]["msb"] + 1))
            if f["msb"] > f["lsb"]:
                yield (f"{n}.{fn}", "msb-1", lambda R, ri=ri, fi=fi: R[ri][4][fi].update(msb=R[ri][4][fi]["msb"] - 1))
            if f["lsb"] > 0:
                yield (f"{n}.{fn}", "lsb-1", lambda R, ri=ri, fi=fi: R[ri][4][fi].update(lsb=R[ri][4][fi]["lsb"] - 1))
            for v in sorted({f["reset"] - 1, f["reset"] + 1, 0, (1 << w) - 1} - {f["reset"]}):
                if 0 <= v < (1 << w):
                    yield (f"{n}.{fn}", f"reset {f['reset']}->{v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].update(reset=v))
            if f["legal"] is not None:
                lg = list(f["legal"])
                for v in sorted({lg[0], lg[-1]} | ({lg[len(lg) // 2]} if len(lg) > 2 else set())):
                    yield (f"{n}.{fn}", f"legal drop {v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].update(legal=[x for x in R[ri][4][fi]["legal"] if x != v]))
                for v in sorted({lg[0] - 1, lg[-1] + 1} - set(lg)):
                    if 0 <= v < (1 << w):
                        yield (f"{n}.{fn}", f"legal add {v}", lambda R, ri=ri, fi=fi, v=v: R[ri][4][fi].update(legal=sorted(R[ri][4][fi]["legal"] + [v])))
                yield (f"{n}.{fn}", "legal None", lambda R, ri=ri, fi=fi: R[ri][4][fi].update(legal=None))
            for c in CLASSES:
                if c != f["cls"]:
                    yield (f"{n}.{fn}", f"cls {f['cls']}->{c}", lambda R, ri=ri, fi=fi, c=c: R[ri][4][fi].update(cls=c))
            for p in [None] + PINS:
                if p != f["pin"]:
                    yield (f"{n}.{fn}", f"pin {f['pin']}->{p}", lambda R, ri=ri, fi=fi, p=p: R[ri][4][fi].update(pin=p))
        if len(fields) >= 2:                                   # two fields' bit positions exchanged
            for i in range(len(fields)):
                for j in range(i + 1, len(fields)):
                    if fields[i]["msb"] - fields[i]["lsb"] == fields[j]["msb"] - fields[j]["lsb"]:
                        def sw(R, ri=ri, i=i, j=j):
                            A, Bf = R[ri][4][i], R[ri][4][j]
                            A["msb"], A["lsb"], Bf["msb"], Bf["lsb"] = Bf["msb"], Bf["lsb"], A["msb"], A["lsb"]
                        yield (n, f"swap {fields[i]['name']}/{fields[j]['name']} positions", sw)

t0 = time.time(); n_ = npass = 0
with open(OUT, "w") as fo:
    fo.write(f"baseline: {len(run())} violations\n")
    for reg, desc, fn in edits():
        RM.REGS[:] = copy.deepcopy(ORIG)
        fn(RM.REGS)
        if RM.REGS == ORIG:
            continue
        n_ += 1
        rep = run()
        if not rep:
            npass += 1
            art = artifacts()
            fo.write(f"PASS {'same-artifacts' if art == base_art else 'ARTIFACTS-CHANGE'} {reg}: {desc}\n"); fo.flush()
    RM.REGS[:] = copy.deepcopy(ORIG)
    fo.write(f"done: {n_} edits, {npass} pass, {time.time() - t0:.0f} s\n")
