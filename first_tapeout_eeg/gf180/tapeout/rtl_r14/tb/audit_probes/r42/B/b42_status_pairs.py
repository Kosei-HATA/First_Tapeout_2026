import sys, importlib.util
spec = importlib.util.spec_from_file_location("regmap", sys.argv[1])
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
hz = rm.slip_hazards("STATUS")
pairs = [(v, x) for v, x in hz if v >= 0]
hdr = [(v, x) for v, x in hz if v < 0]
print("pairs", len(pairs), "header-slip values", len(hdr))
cp = 1 << 4
up = [(hex(v), hex(x)) for v, x in pairs if not v & cp and x & cp]
dn = [(hex(v), hex(x)) for v, x in pairs if v & cp and not x & cp]
print("CMD_PENDING 0->1:", len(up), up[:20])
print("CMD_PENDING 1->0:", len(dn), dn[:20])
for e in [(0x81, 0x82), (0x91, 0xA2), (0x88, 0x84), (0x88, 0x90), (0x8C, 0x98)]:
    print("example", [hex(t) for t in e], e in pairs)
# the header-slip ones with CMD_PENDING 0 (a false 0 when the header slips)
print("header slips reading CMD_PENDING 0:", sorted(hex(x) for v, x in hdr if not x & cp)[:30])
