import sys
sys.path.insert(0, "../gf180/tapeout/rtl/spec")
import regmap as R
for key in ["STATE", "FIFO_LEVEL", "DFLAG", "IF_CFG", "ERR", "CAPS", "ID", "VERSION", "OFF_M_L.ACT", "OFF_M_H.ACT", "OFF_CTRL.ACT"]:
    legal = R.slip_hazards(key)
    anyv = R.slip_hazards(key, any_value=True)
    addr, vals = R.slip_target(key)
    extra = [p for p in anyv if p not in legal]
    print(f"{key}: legal-only {len(legal)} pairs {legal[:6]}; any-value {len(anyv)}; illegal reads {len(extra)}")
    if extra:
        print("   ", [(hex(a) if a>=0 else a, hex(b)) for a,b in extra[:40]])
