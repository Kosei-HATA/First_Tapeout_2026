"""Re-check the fsm sweep's SPI passes marked NOT-EQUIVALENT with a reachable-behaviour signature: every frame case
of fsm_spec.spi_frame_cases walked through the table (the action trace and the state at CS_N rising), as round 45's
auditor C compared them, plus the same walks for every value of the conditions the walk does not set (busy, head,
crc_ok, wr_ok, addr_ok)."""
import copy, itertools, os, re, sys
SPEC, SWEEP_OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, SPEC); os.chdir(SPEC)
import fsm_spec as F
B, ALWAYS = F.B, F.ALWAYS
ORIG = copy.deepcopy(F.SPI["table"])

def sig():
    out = {}
    for kind, crc_en, env, nbytes, extra in F.spi_frame_cases():
        tr = []
        r = F.spi_walk(nbytes, extra, env, trace=tr)
        out[(kind, crc_en, tuple(sorted(env.items())), nbytes, extra)] = (None if r is None else r[1],
                                                                          tuple((e, tuple(a)) for e, a in tr))
    return out
base = sig()
for line in open(SWEEP_OUT):
    if "NOT-EQUIVALENT SPI" not in line:
        continue
    m = re.search(r"SPI \('(\w+)', '(\w+)'\) pair guard -> '(.*)'$", line.strip())
    if not m:
        print("skip (not a pair edit):", line.strip()); continue
    s, e, g2 = m.groups()
    t = copy.deepcopy(ORIG)
    t[(s, e)][0]["guard"] = g2; t[(s, e)][1]["guard"] = f"not ({g2})"
    F.SPI["table"] = t
    eq = sig() == base
    F.SPI["table"] = copy.deepcopy(ORIG)
    print(("walk-equivalent " if eq else "WALK-DIFFERENT  ") + f"({s}, {e}) -> {g2!r}")
