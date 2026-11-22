#!/usr/bin/env python3
"""Single-field edits of regmap.REGS through regmap.check(); prints every edit that passes, with the generated
eeg_regs_defs.svh / package / test-generator differences it would make. Usage: regs_sweep.py <spec dir> <out.txt>"""
import contextlib
import copy
import io
import sys
import time

sys.path.insert(0, sys.argv[1])
import regmap as R  # noqa: E402

ORIG = copy.deepcopy(R.REGS)


def run_check():
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            errs = R.check(verbose=False)
        return errs
    except Exception as ex:                     # noqa: BLE001  a crash is no pass
        return [f"CRASH {ex!r}"]


def defs_text():
    try:
        return R.sv_defs() + R.sv_package()
    except Exception as ex:                     # noqa: BLE001
        return f"EXC {ex!r}"


def edits():
    cls_all = ["apply", "imm", "ro", "w1c", "cmd"]
    acc_all = ["RO", "RW", "W1C", "WO"]
    pins = sorted({f["pin"] for r in ORIG for f in r[4] if f["pin"]})
    for ri, (a, n, acc, lock, fields, d) in enumerate(ORIG):
        def reg_edit(**kw):
            regs = copy.deepcopy(ORIG)
            r = list(regs[ri])
            for k, v in kw.items():
                r[{"addr": 0, "name": 1, "acc": 2, "lock": 3}[k]] = v
            regs[ri] = tuple(r)
            return regs
        for acc2 in acc_all:
            if acc2 != acc:
                yield f"{n}: access {acc}->{acc2}", reg_edit(acc=acc2)
        yield f"{n}: lock {lock}->{not lock}", reg_edit(lock=not lock)
        for da in (-1, 1, 0x10, -0x10):
            yield f"{n}: addr 0x{a:02X}->0x{(a + da) & 0x7F:02X}", reg_edit(addr=(a + da) & 0x7F)
        for fi, f in enumerate(fields):
            def fe(**kw):
                regs = copy.deepcopy(ORIG)
                regs[ri][4][fi].update(kw)
                return regs
            tag = f"{n}.{f['name']}"
            w = f["msb"] - f["lsb"] + 1
            leg = f["legal"]
            # reset value
            cand = set()
            if leg:
                cand |= {min(leg), max(leg), f["reset"] + 1, f["reset"] - 1, min(leg) - 1, max(leg) + 1}
            else:
                cand |= {f["reset"] + 1, f["reset"] ^ 1}
            for v in sorted(cand):
                if v != f["reset"] and 0 <= v < (1 << w):
                    yield f"{tag}: reset {f['reset']}->{v}", fe(reset=v)
            # legal values
            if leg:
                L = sorted(leg)
                for v in (L[0], L[-1]) + ((L[len(L) // 2],) if len(L) > 2 else ()):
                    yield f"{tag}: legal without {v}", fe(legal=[x for x in L if x != v])
                for v in (L[0] - 1, L[-1] + 1):
                    if 0 <= v < (1 << w) and v not in L:
                        yield f"{tag}: legal with {v}", fe(legal=sorted(L + [v]))
            # bits
            if f["lsb"] > 0:
                yield f"{tag}: down one bit", fe(lsb=f["lsb"] - 1, msb=f["msb"] - 1)
                yield f"{tag}: widen down", fe(lsb=f["lsb"] - 1)
            if f["msb"] < 7:
                yield f"{tag}: up one bit", fe(lsb=f["lsb"] + 1, msb=f["msb"] + 1)
                yield f"{tag}: widen up", fe(msb=f["msb"] + 1)
            if w > 1:
                yield f"{tag}: narrow top", fe(msb=f["msb"] - 1)
                yield f"{tag}: narrow bottom", fe(lsb=f["lsb"] + 1)
            # class
            for c2 in cls_all:
                if c2 != f["cls"]:
                    yield f"{tag}: class {f['cls']}->{c2}", fe(cls=c2)
            # pin
            if f["pin"]:
                yield f"{tag}: pin {f['pin']}->None", fe(pin=None)
            for p2 in pins:
                if p2 != f["pin"]:
                    yield f"{tag}: pin {f['pin']}->{p2}", fe(pin=p2)


def main():
    out = open(sys.argv[2], "w")
    t0 = time.time()
    base_errs = run_check()
    assert not base_errs, base_errs
    base_defs = defs_text()
    n = npass = 0
    for name, regs in edits():
        R.REGS[:] = regs
        n += 1
        errs = run_check()
        if not errs:
            npass += 1
            dd = defs_text()
            out.write(f"PASS {name}: generated defs/package {'same' if dd == base_defs else 'DIFFER'}\n")
            out.flush()
        R.REGS[:] = copy.deepcopy(ORIG)
    s = f"{n} edits, {npass} passed; {time.time() - t0:.0f} s"
    out.write(s + "\n")
    print(s)


if __name__ == "__main__":
    main()
