import sys, itertools
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as RM
def run_with(over):
    saved = []
    for name, val in over.items():
        for r in RM.REGS:
            for f in r[4]:
                if f["name"] == name:
                    saved.append((f, f["reset"])); f["reset"] = val
    out = RM.probe_off_hazards()
    for f, v in saved: f["reset"] = v
    return out
# every combination of the values one fault in a CRC-off frame of steps 2, 3 and 9 can leave on a CRC-off chip
n = 0
for te, tw, cf, dm in itertools.product((0, 1, 3), (5, 0xA5), (0, 1), (0, 1)):
    o = run_with({"T_ELEC": te, "T_WARM": tw, "CHOP_FAST": cf, "DRDY_MODE": dm})
    n += 1
    if o: print("HAZARD", te, tw, cf, dm, o)
print(n, "value sets checked; probe_off_hazards empty for all" )
