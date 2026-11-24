# which SCLK fault (kind, pulse k) and header STATUS make the CRC STATUS read of 0x8A come out as 0x85 (rule (a) and the
# CRC both pass)
import sys, importlib.util
spec = importlib.util.spec_from_file_location("regmap", sys.argv[1])
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
h = 0x83
mosi = h << 24
kinds = ((lambda k: rm._skip(mosi, k), lambda x, k: rm._dup(x, k), "missed pulse"),
         (lambda k: rm._dup(mosi, k), lambda x, k: rm._skip(x, k), "extra pulse in the low phase before"),
         (lambda k: rm._dup(mosi, k), lambda x, k: rm._skip(x, k + 1), "bounce in the high phase of"),
         (lambda k: rm._skip(mosi, k + 1), lambda x, k: rm._dup(x, k), "merge with the next"))
for v in (0x8A, 0x8E, 0x9A, 0xAA):
    for ki, (chip, host, name) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24
            if h_ != h:
                continue
            st = v                                   # the header STATUS equals the register's value (same frame)
            hs = host((st << 24) | (v << 16) | (rm.crc8([h, v]) << 8), k)
            d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
            if (hs >> 30) == 2 and d != v and c == rm.crc8([h, d]):
                print(f"STATUS 0x{v:02X}: {name} pulse {k}: host reads header 0x{hs >> 24:02X}, data 0x{d:02X}, CRC 0x{c:02X} (valid)")
