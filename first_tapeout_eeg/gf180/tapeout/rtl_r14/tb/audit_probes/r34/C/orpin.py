#!/usr/bin/env python3
"""Which operands of the Or conditions that fire a violation in the checks are pinned by a self-test mutation
(audit 34, C; the kind of hole of round 33's C3). The module is loaded with every Or in an `if` test (positive sense:
the Or itself decides the append) replaced by a recorder that evaluates every operand (safely) and logs, per run of
the checks, the operands that were true whenever the Or was true. Then the self-test runs as written. An operand i of
a site is pinned iff some mutation that expects the site's message has every firing of the site depend on operand i
alone (only i true): removing i would make that mutation lose the message.
Usage: orpin.py <spec dir> fsm|regmap"""
import ast, os, sys, types, collections
SPEC, WHICH = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
modname, path = ("fsm_spec", os.path.join(SPEC, "fsm_spec.py")) if WHICH == "fsm" else ("regmap", os.path.join(SPEC, "regmap.py"))
src = open(path, encoding="utf-8").read()
tree = ast.parse(src)
NAMES = ("errs", "P")
FUNCS_FSM = ("check_tables", "check_vocab", "check_seq_columns", "check_graph", "seq_properties", "check_seq_ticks",
             "check_seq_branches", "check_seq_commands", "check_spi_props", "check_spi_frames", "check_fifo",
             "check_timing", "check_doc_blocks")
FUNCS = FUNCS_FSM if WHICH == "fsm" else ("check",)

def appends_in(stmts):
    out = []
    for s in stmts:
        for n in ast.walk(s):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id in NAMES):
                out.append(n.lineno)
    return out

SITES = {}          # site id -> (func, line, n operands, operand sources, append lines)
class T(ast.NodeTransformer):
    def __init__(self, fn):
        self.fn = fn
    def visit_If(self, node):
        self.generic_visit(node)
        t = node.test
        ors = []
        if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or):
            ors = [t]
        elif isinstance(t, ast.BoolOp) and isinstance(t.op, ast.And):
            ors = [v for v in t.values if isinstance(v, ast.BoolOp) and isinstance(v.op, ast.Or)]
        apps = appends_in(node.body)
        if apps and ors:
            o = ors[0]
            sid = len(SITES)
            SITES[sid] = (self.fn, o.lineno, len(o.values), [ast.get_source_segment(src, v)[:90] for v in o.values], apps)
            mk = lambda body: ast.Lambda(args=ast.arguments(posonlyargs=[], args=[], vararg=None, kwonlyargs=[],
                                                            kw_defaults=[], kwarg=None, defaults=[]), body=body)
            lams = [mk(v) for v in o.values]
            call = ast.Call(func=ast.Name(id="_if_rec", ctx=ast.Load()), args=[ast.Constant(sid), mk(t)] + lams, keywords=[])
            node.test = ast.copy_location(call, t)
        return node
for f in tree.body:
    if isinstance(f, ast.FunctionDef) and f.name in FUNCS:
        T(f.name).visit(f)
    if WHICH == "regmap" and isinstance(f, ast.FunctionDef) and f.name == "check":
        st0 = f.body[0]
        inc = ast.Expr(value=ast.Call(func=ast.Name(id="_run_inc", ctx=ast.Load()), args=[], keywords=[]))
        ast.copy_location(inc, st0)
        f.body.insert(1 if isinstance(st0, ast.Expr) and isinstance(getattr(st0, "value", None), ast.Constant) else 0, inc)
ast.fix_missing_locations(tree)
code = compile(tree, path, "exec")
mod = types.ModuleType(modname)
mod.__file__ = path
sys.modules[modname] = mod
LOG = collections.defaultdict(list)      # run index -> [(sid, truth tuple)]
RUN = [0]
def _or_rec(sid, *lams):
    vals = []
    for l in lams:
        try:
            vals.append(bool(l()))
        except Exception:
            vals.append(None)
    res = False
    for l in lams:                        # the original short-circuit result
        v = l()
        if v:
            res = True
            break
    if res:
        LOG[RUN[0]].append((sid, tuple(vals)))
    return res
mod.__dict__["_or_rec"] = _or_rec
def _run_inc():
    RUN[0] += 1
mod.__dict__["_run_inc"] = _run_inc
def _if_rec(sid, whole, *lams):
    res = bool(whole())
    if res:
        vals = []
        for l in lams:
            try:
                vals.append(bool(l()))
            except Exception:
                vals.append(None)
        LOG[RUN[0]].append((sid, tuple(vals)))
    return res
mod.__dict__["_if_rec"] = _if_rec
exec(code, mod.__dict__)
M = mod
# count the runs of the checks: wrap the entry point the self-test calls for each mutation
entry = "run_checks" if WHICH == "fsm" else "check"
if WHICH == "fsm":
    orig_entry = M.__dict__[entry]
    def wrapped(*a, **k):
        RUN[0] += 1
        return orig_entry(*a, **k)
    M.__dict__[entry] = wrapped
msgs = M.check_messages()
if WHICH == "fsm":
    line2txt = {ln: t for fn, ln, t, _ in msgs}
else:
    line2txt = {ln: t for ln, t, _ in msgs}
# run the self-test's mutations, remembering each run's index
if WHICH == "fsm":
    RUN[0] = 0
    results = M.selftest_runs()
    # the runs: one per result, in order (run_checks called once per mutation in selftest_runs)
    names = [r[1] for r in results]
    expect = M.SELFTEST_EXPECT
    run_of = {}
    # the k-th call of run_checks is results[k-1]
    for k, nm in enumerate(names, 1):
        run_of[nm] = k
else:
    names, run_of, expect = None, None, M.SELFTEST_EXPECT
    import io, contextlib
    RUN[0] = 0
    calls = []
    orig2 = M.__dict__[entry]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = M.selftest()
    out = buf.getvalue()
    names = []
    for ln in out.splitlines():
        if ln.startswith(("detected ", "MISSED")):
            rest = ln[8:].strip() if ln.startswith("detected") else ln[8:].strip()
            names.append(rest.rsplit(": ", 1)[0])
    print("regmap selftest rc", rc, "; mutation lines", len(names), "; check() calls", RUN[0])
    print("\n".join(l for l in out.splitlines() if l.startswith(("MISSED", "PROBLEM")))[:2000])
    run_of = {nm: k for k, nm in enumerate(names, 1)}
print("sites", len(SITES), "runs", RUN[0], "mutations", len(names))
# per site: the message(s) of its appends, the mutations expecting them, and per operand pinned?
for sid, (fn, ln, nops, ops, apps) in SITES.items():
    txts = [line2txt.get(a) for a in apps]
    txts = [t for t in txts if t]
    exp_ms = [nm for nm, want in expect.items() if any(w in txts for w in want)]
    fir = {nm: [v for s_, v in LOG.get(run_of[nm], []) if s_ == sid] for nm in exp_ms if nm in run_of}
    missing_nm = [nm for nm in exp_ms if nm not in run_of]
    if missing_nm:
        print("  (names not mapped:", missing_nm[:3], ")")
    pinned = []
    for i in range(nops):
        if fir is None:
            pinned.append("?")
            continue
        ok = any(f and all(v[i] and not any(v[j] for j in range(nops) if j != i) for v in f) for f in fir.values())
        pinned.append("pinned" if ok else "UNPINNED")
    print(f"site {sid}: {fn} line {ln}, {nops} operands, message(s) {[t[:60] for t in txts]}, expected by {len(exp_ms)} mutation(s)")
    for i in range(nops):
        print(f"    operand {i}: {pinned[i]:8s} {ops[i]}")
    if fir is not None:
        for nm, f in fir.items():
            print(f"      {nm[:50]}: {len(f)} firings, truth sets {sorted(set(f))[:4]}")
