"""Equivalence of the passing FSM edits: SEQ by seq_tick over every state x event case (and RST, REL, OUT) x condition
value; SPI by spi_walk's per-event trace over every enumerated frame. Usage: equiv.py SPEC sweep_out.json sweep.py"""
import ast, copy, itertools, json, os, sys
SPEC = os.path.abspath(sys.argv[1]); RES = json.load(open(sys.argv[2])); SW = os.path.abspath(sys.argv[3])
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as FS
src = open(SW).read().split("out = {")[0].split("import fsm_spec as FS", 1)[1]
g = {"FS": FS, "copy": copy, "itertools": itertools, "B": FS.B, "IGN": FS.IGN, "IMP": FS.IMP}
exec(src, g)
apply_ = g["apply"]

def seq_sig():
    timed = {x[0] for x in FS.SEQ_STATES if x[4]}
    out = []
    for s in [x[0] for x in FS.SEQ_STATES]:
        cases = FS.seq_tick_cases(s, timed) if s != "RESET" else [[c] for c in FS.SEQ_COMMANDS] + [["OUT"]]
        cases = cases + [c + ["RST"] for c in cases] + [["RST"]] + ([["REL"]] if s == "RESET" else [])
        for ev in cases:
            for vals in itertools.product((0, 1), repeat=len(FS.SEQ_CONDS)):
                env = dict(zip(FS.SEQ_CONDS, vals))
                try:
                    n, a = FS.seq_tick(s, ev, env)
                    out.append((s, tuple(ev), vals, n, tuple(sorted(a))))
                except Exception as ex:
                    out.append((s, tuple(ev), vals, "EXC " + type(ex).__name__))
    return out

def spi_sig():
    out = []
    for kind, crc_en, env, nbytes, extra in FS.spi_frame_cases():
        tr = []
        r = FS.spi_walk(nbytes, extra, env, trace=tr)
        out.append((kind, crc_en, tuple(sorted(env.items())), nbytes, extra, None if r is None else (tuple(r[0]), r[1]),
                    tuple((e, tuple(a)) for e, a in tr)))
    return out

base_seq, base_spi = seq_sig(), spi_sig()
noneq = []
for item in RES["passed"]:
    m = item[0]
    if m == "PRIO":
        FS.SEQ_PRIORITY[:] = item[1].split()
        same = seq_sig() == base_seq
        FS.SEQ_PRIORITY[:] = ["STOP", "START", "APPLY", "APPLY_NR", "FLUSH", "TMR"]
    else:
        F = FS.SEQ if m == "SEQ" else FS.SPI
        key = ast.literal_eval(item[1]); kind = item[2]
        i = ast.literal_eval(item[3]) if item[3] not in ("None",) else None
        arg = item[4]
        try:
            arg = ast.literal_eval(arg)
        except Exception:
            pass
        if kind == "cell" and isinstance(arg, str) and arg.startswith("[{"):
            arg = ast.literal_eval(arg)
        orig = F["table"]
        F["table"] = apply_(F, (key, kind, i, arg))
        same = (seq_sig() == base_seq) if m == "SEQ" else (spi_sig() == base_spi)
        F["table"] = orig
    if not same:
        noneq.append(item)
print(f"{len(RES['passed'])} passing edits: {len(RES['passed']) - len(noneq)} equivalent (same seq_tick on every case / same "
      f"spi_walk trace on every frame), {len(noneq)} not")
for x in noneq:
    print("  NOT EQUIVALENT", x)
