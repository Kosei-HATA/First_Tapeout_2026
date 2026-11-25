"""Single field edits of regmap.REGS through regmap.check (in process); prints every edit that passes."""
import copy, sys, os, time, io, contextlib
SPEC = os.path.abspath(sys.argv[1])
PART = int(sys.argv[2]) if len(sys.argv) > 2 else 0
NPART = int(sys.argv[3]) if len(sys.argv) > 3 else 1
sys.path.insert(0, SPEC)
os.chdir(SPEC)
import regmap as R
ORIG = copy.deepcopy(R.REGS)
CLS = ("ro", "w1c", "apply", "imm", "cmd")
ACC = ("RO", "W1C", "RW", "WO")
pins = sorted({f["pin"] for r in ORIG for f in r[4] if f["pin"]})

def edits():
    E = []
    for ri, (a, n, acc, lock, fields, desc) in enumerate(ORIG):
        for acc2 in ACC:
            if acc2 != acc:
                E.append((f"{n} access {acc}->{acc2}", lambda t, ri=ri, acc2=acc2: t.__setitem__(ri, (t[ri][0], t[ri][1], acc2, t[ri][3], t[ri][4], t[ri][5]))))
        E.append((f"{n} lock {lock}->{not lock}", lambda t, ri=ri: t.__setitem__(ri, (t[ri][0], t[ri][1], t[ri][2], not t[ri][3], t[ri][4], t[ri][5]))))
        for d in (-1, 1, 0x10, -0x10):
            E.append((f"{n} addr {a:#x}->{(a + d) & 0x7F:#x}", lambda t, ri=ri, d=d: t.__setitem__(ri, ((t[ri][0] + d) & 0x7F, t[ri][1], t[ri][2], t[ri][3], t[ri][4], t[ri][5]))))
        for fi, f in enumerate(fields):
            nm = f"{n}.{f['name']}"
            w = f["msb"] - f["lsb"] + 1
            def setf(key, val, ri=ri, fi=fi):
                return lambda t: t[ri][4][fi].__setitem__(key, val)
            for d in range(-7, 8):
                if d and 0 <= f["lsb"] + d and f["msb"] + d <= 7:
                    E.append((f"{nm} moved {d:+d}", lambda t, ri=ri, fi=fi, d=d: (t[ri][4][fi].__setitem__("lsb", t[ri][4][fi]["lsb"] + d), t[ri][4][fi].__setitem__("msb", t[ri][4][fi]["msb"] + d))))
            for key, d in (("msb", 1), ("msb", -1), ("lsb", 1), ("lsb", -1)):
                v = f[key] + d
                if 0 <= v <= 7 and (f["lsb"] if key == "msb" else v) <= (v if key == "msb" else f["msb"]):
                    E.append((f"{nm} {key} {f[key]}->{v}", setf(key, v)))
            L = sorted(f["legal"] or [])
            cand = {(f["reset"] + 1) % (1 << w), (f["reset"] - 1) % (1 << w), 0, (1 << w) - 1} | (set(L) if len(L) <= 16 else {L[0], L[-1], L[1], L[-2]})
            for v in sorted(cand - {f["reset"]}):
                E.append((f"{nm} reset {f['reset']}->{v}", setf("reset", v)))
            if f["legal"] is not None:
                L = sorted(f["legal"])
                for v in (L if len(L) <= 16 else [L[0], L[1], L[-2], L[-1]]):
                    if v != f["reset"]:
                        E.append((f"{nm} legal -{v}", lambda t, ri=ri, fi=fi, v=v: t[ri][4][fi].__setitem__("legal", [x for x in t[ri][4][fi]["legal"] if x != v])))
                outs = [v for v in range(1 << w) if v not in f["legal"]]
                if len(outs) > 16:
                    outs = sorted({v for v in outs if v in (L[0] - 1, L[-1] + 1, 0, (1 << w) - 1)} | set(v for v in outs if any(abs(v - x) == 1 for x in L)))
                for v in outs:
                    if True:
                        E.append((f"{nm} legal +{v}", lambda t, ri=ri, fi=fi, v=v: t[ri][4][fi].__setitem__("legal", sorted(t[ri][4][fi]["legal"] + [v]))))
                        if w > 4 and v > 16 and v not in (254, 255, 30, 31, 62, 63, 126, 127, 128):
                            pass
                E.append((f"{nm} legal->None", setf("legal", None)))
            else:
                E.append((f"{nm} legal None->[reset]", setf("legal", [f["reset"]])))
            for c in CLS:
                if c != f["cls"]:
                    E.append((f"{nm} cls {f['cls']}->{c}", setf("cls", c)))
            for p in ([None] + pins if f["pin"] else ([pins[0]] if f["cls"] in ("imm", "ro") else [])):
                if p != f["pin"]:
                    E.append((f"{nm} pin {f['pin']}->{p}", setf("pin", p)))
    return E

def main():
    EE = edits()[PART::NPART]
    print(f"# part {PART}/{NPART}: {len(EE)} edits", flush=True)
    t0 = time.time(); npass = 0
    for desc, fn in EE:
        R.REGS[:] = copy.deepcopy(ORIG)
        try:
            fn(R.REGS)
            with contextlib.redirect_stdout(io.StringIO()):
                rep = R.check(verbose=False)
        except Exception as ex:
            rep = [f"EXC {type(ex).__name__}: {ex}"]
        if not rep:
            npass += 1
            print(f"PASS :: {desc}", flush=True)
    R.REGS[:] = ORIG
    print(f"# done {len(EE)} edits, {npass} pass, {time.time()-t0:.0f} s", flush=True)

main()
