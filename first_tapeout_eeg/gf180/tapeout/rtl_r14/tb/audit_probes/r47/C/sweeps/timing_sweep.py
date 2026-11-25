import copy, io, contextlib, os, sys
SPEC = os.path.abspath(sys.argv[1]); sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F, regmap as R, wave as W
ORIG = copy.deepcopy(F.TIMING)
def leaves(d, path=()):
    if isinstance(d, dict):
        for k, v in d.items(): yield from leaves(v, path + (k,))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d): yield from leaves(v, path + (i,))
    else:
        yield path, d
def setp(d, path, v):
    for k in path[:-1]: d = d[k]
    if isinstance(d, tuple): raise TypeError
    d[path[-1]] = v
def run():
    with contextlib.redirect_stdout(io.StringIO()):
        r1, _ = F.run_checks(verbose=False)
        r2 = R.check(verbose=False)
        try:
            r3 = W.check()
        except Exception as ex:
            r3 = [f"wave exc {ex}"]
    return r1 + r2 + r3
edits = []
for path, v in leaves(ORIG):
    if isinstance(v, bool) or not isinstance(v, (int, float)): continue
    for nv in sorted({v + 1, v - 1, v * 2, v / 2 if isinstance(v, float) else v // 2} - {v}):
        edits.append((path, v, nv))
npass = 0
for path, v, nv in edits:
    T = copy.deepcopy(ORIG)
    try:
        setp(T, path, nv)
    except TypeError:
        # tuple leaf (timers): rebuild the tuple
        d = T
        for k in path[:-2]: d = d[k]
        tl = list(d[path[-2]]); tl[path[-1]] = nv; d[path[-2]] = tuple(tl)
    F.TIMING.clear(); F.TIMING.update(T)
    try:
        rep = run()
    except Exception as ex:
        rep = [f"EXC {ex}"]
    if not rep:
        npass += 1
        print("PASS", path, v, "->", nv, flush=True)
F.TIMING.clear(); F.TIMING.update(ORIG)
print("#", len(edits), "edits,", npass, "pass")
