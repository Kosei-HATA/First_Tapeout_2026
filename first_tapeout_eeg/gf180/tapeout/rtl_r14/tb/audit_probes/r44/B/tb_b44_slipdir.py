"""audit round 44, B: directed RTL run - the values regmap.slip_hazards records pairs for; every recorded pair with
that sent value must appear in the RTL (positive), and no accepted wrong value outside the record (negative)."""
import sys
sys.path.insert(0, sys.argv[1])
import regmap as R
vals = {0x21: ("OFF_M_L", 0xDA), 0x31: ("OFF_M_L.ACT", 0xAA), 0x53: ("T_PRE", 0x41), 0x52: ("T_REC", 0x32),
        0x54: ("T_RST", 0x94), 0x51: ("T_ELEC", 0xC5), 0x08: ("ALERT_MASK", 0x4D), 0x09: ("ALERT_MASK_D", 0x02),
        0x50: ("T_WARM", 0x8A), 0x60: ("TEST_MUX", 0x1A)}
got = {a: set() for a in vals}
bad = []
for line in open(sys.argv[2]):
    if not line.startswith("ACC"):
        continue
    d = dict(kv.split("=") for kv in line.split()[1:])
    a, read, true = int(d["a"], 16), int(d["read"], 16), int(d["true"], 16)
    dec = int(d["dec"], 16) if "x" not in d["dec"] else None
    key, v = vals[a]
    if true != v:
        bad.append(f"true value 0x{true:02X} is not the set 0x{v:02X}: {line.strip()}")
    if read == true:
        continue
    if int(d["fault"]) == 1:
        bad.append("MOSI flip accepted: " + line.strip())
        continue
    pair = (true, read) if dec == (0x80 | a) else (-1, read)
    got[a].add(pair)
for a, (key, v) in vals.items():
    want = {p for p in R.slip_hazards(key) if p[0] == v}
    extra = got[a] - set(R.slip_hazards(key))
    print(f"{key} = 0x{v:02X}: model {sorted((hex(x), hex(y)) for x, y in want)}, RTL {sorted((hex(x), hex(y)) for x, y in got[a])}"
          + ("" if got[a] == want else "  <-- differs"))
    if extra:
        bad.append(f"{key}: RTL pairs not in the model {extra}")
for b in bad[:20]:
    print("BAD:", b)
print("PASS" if not bad else f"FAIL {len(bad)}")
