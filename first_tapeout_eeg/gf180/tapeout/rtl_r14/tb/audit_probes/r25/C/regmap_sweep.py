"""Single edits of regmap's tables outside REGS' fields (new kinds, audit round 25, C) through regmap.check."""
import copy, os, sys, json, itertools
SPEC = os.path.abspath(sys.argv[1]); OUT = os.path.abspath(sys.argv[2])
sys.path.insert(0, SPEC); os.chdir(SPEC)
import regmap as RM
import fsm_spec as FS

def run():
    try:
        return RM.check(verbose=False)
    except Exception as ex:
        return ["CRASH " + type(ex).__name__ + ": " + str(ex)[:100]]

res = {"passed": [], "crashed": [], "n": 0}
def trial(name, apply_, undo):
    apply_()
    try:
        r = run()
    finally:
        undo()
    res["n"] += 1
    if not r:
        res["passed"].append(name)
    elif any(x.startswith("CRASH") for x in r):
        res["crashed"].append((name, r[0]))

# RANGE_MAX_M: every entry +-1, +-2, and swapped pairs
orig = dict(RM.RANGE_MAX_M)
for k in orig:
    for d in (-2, -1, 1, 2):
        trial(f"RANGE_MAX_M[{k}] {orig[k]}->{orig[k]+d}", lambda k=k, d=d: RM.RANGE_MAX_M.__setitem__(k, orig[k] + d),
              lambda: (RM.RANGE_MAX_M.clear(), RM.RANGE_MAX_M.update(orig)))
for a, b in itertools.combinations(orig, 2):
    trial(f"RANGE_MAX_M swap {a}<->{b}", lambda a=a, b=b: (RM.RANGE_MAX_M.__setitem__(a, orig[b]), RM.RANGE_MAX_M.__setitem__(b, orig[a])),
          lambda: (RM.RANGE_MAX_M.clear(), RM.RANGE_MAX_M.update(orig)))
# BLANK_WITH_DAC, SHADOW_MIRROR, TEST_KEY
for nm, vals in (("BLANK_WITH_DAC", range(0, 16)), ("SHADOW_MIRROR", (0x08, 0x18, 0x20, 0x30)), ("TEST_KEY", (0x3D, 0x3E, 0xBC, 0x7C, 0x1C, 0x5A))):
    o = getattr(RM, nm)
    for v in vals:
        if v == o:
            continue
        trial(f"{nm} {o}->{v}", lambda nm=nm, v=v: setattr(RM, nm, v), lambda nm=nm, o=o: setattr(RM, nm, o))
# OVL_RULE
oo = dict(RM.OVL_RULE)
for k, vs in (("window", (16, 31, 33, 64)), ("threshold", (2, 3, 5, 8)), ("codes", ((0,), (31,), (0, 1, 30, 31), (1, 30), (0, 30)))):
    for v in vs:
        trial(f"OVL_RULE {k} -> {v}", lambda k=k, v=v: RM.OVL_RULE.__setitem__(k, v), lambda: (RM.OVL_RULE.clear(), RM.OVL_RULE.update(oo)))
# COMMANDS: each code changed by one bit, two bits, swapped
oc = dict(RM.COMMANDS)
for k in oc:
    for b in range(8):
        trial(f"COMMANDS {k} ^ bit {b}", lambda k=k, b=b: RM.COMMANDS.__setitem__(k, oc[k] ^ (1 << b)), lambda: (RM.COMMANDS.clear(), RM.COMMANDS.update(oc)))
for a, b in itertools.combinations(oc, 2):
    trial(f"COMMANDS swap {a}<->{b}", lambda a=a, b=b: (RM.COMMANDS.__setitem__(a, oc[b]), RM.COMMANDS.__setitem__(b, oc[a])), lambda: (RM.COMMANDS.clear(), RM.COMMANDS.update(oc)))
# SAMPLE_STATUS: move a bit / swap two rows' bits
os_ = list(RM.SAMPLE_STATUS)
for i, j in itertools.combinations(range(len(os_)), 2):
    def ap(i=i, j=j):
        a, b = RM.SAMPLE_STATUS[i], RM.SAMPLE_STATUS[j]
        RM.SAMPLE_STATUS[i] = (a[0], b[1], a[2]); RM.SAMPLE_STATUS[j] = (b[0], a[1], b[2])
    trial(f"SAMPLE_STATUS swap bits of {os_[i][0]}/{os_[j][0]}", ap, lambda: RM.SAMPLE_STATUS.__setitem__(slice(None), os_))
# ANALOG_CONTROLS / DIGITAL_ONLY / SEQ_DRIVEN: drop one entry
for nm in ("ANALOG_CONTROLS",):
    o = list(getattr(RM, nm))
    for x in o:
        trial(f"{nm} drop {x}", lambda nm=nm, x=x: getattr(RM, nm).remove(x), lambda nm=nm, o=o: getattr(RM, nm).__setitem__(slice(None), o))
od = set(RM.DIGITAL_ONLY)
for x in od:
    trial(f"DIGITAL_ONLY drop {x}", lambda x=x: RM.DIGITAL_ONLY.discard(x), lambda: (RM.DIGITAL_ONLY.clear(), RM.DIGITAL_ONLY.update(od)))
# PIN_OF_CONTROL: each control pointed at each other key
op = dict(RM.PIN_OF_CONTROL)
keys = sorted(set(op.values()))
for c in op:
    for k in keys:
        if k != op[c]:
            trial(f"PIN_OF_CONTROL {c}: {op[c]}->{k}", lambda c=c, k=k: RM.PIN_OF_CONTROL.__setitem__(c, k), lambda: (RM.PIN_OF_CONTROL.clear(), RM.PIN_OF_CONTROL.update(op)))
# FS.TIMING entries the map uses (chop1 periods)
ot = copy.deepcopy(FS.TIMING)
for i in range(len(ot["chop1_periods_frames"])):
    for v in (16, 48, 96, 1024, 2048):
        def ap(i=i, v=v):
            FS.TIMING["chop1_periods_frames"] = list(ot["chop1_periods_frames"]); FS.TIMING["chop1_periods_frames"][i] = v
        trial(f"TIMING chop1_periods_frames[{i}] -> {v}", ap, lambda: FS.TIMING.__setitem__("chop1_periods_frames", list(ot["chop1_periods_frames"])))
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)
print(res["n"], "edits;", len(res["passed"]), "passed;", len(res["crashed"]), "crashed")
for p in res["passed"]:
    print("  PASSED", p)
for c in res["crashed"]:
    print("  CRASH", c)
