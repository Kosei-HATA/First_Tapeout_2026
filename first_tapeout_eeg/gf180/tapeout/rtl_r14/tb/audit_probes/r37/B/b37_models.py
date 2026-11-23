"""Audit round 37, auditor B: model computations (run from gf180/tapeout/rtl/spec with the venv's python).
1. A CRC-off chip at its reset values (ERR 0x01, 0x03, 0x09, 0x0B): does any CRC-form read [0x80|a, 0, 0] of any
   address a give the host a CRC-valid (value, next value) pair?  (rule (c)'s first trigger)
2. ID and VERSION under one SCLK slip, without the single-legal-value filter, with any FIFO head and with the FIFO
   empty (step 3's state)."""
import sys
sys.path.insert(0, ".")
import regmap as R

vals = {}
for a, n, acc, lock, fl, _ in R.REGS:
    v = R.reset_of(n) if acc != "WO" and n != "SAMPLE" else 0
    vals[a] = v
    if any(f["cls"] == "apply" for f in fl):
        vals[a + 0x10] = v
vals[0x03] = 0xA1
for errv in (0x01, 0x03, 0x09, 0x0B):
    vals[0x06] = errv
    hits = [hex(a) for a in range(128) if R.crc8([0x80 | a, vals.get(a, 0)]) == vals.get((a + 1) & 0x7F, 0)]
    print(f"1. ERR=0x{errv:02X}: CRC-valid CRC-form reads on a reset chip: {hits}")

orig_vals, orig_resp = R.reg_values, R.slip_responses
R.reg_values = lambda n: set(range(256)) if n in ("ID", "VERSION") else orig_vals(n)
for k in ("ID", "VERSION"):
    print(f"2. {k}, any FIFO head: {R.slip_hazards(k)}")
R.slip_responses = lambda h_: ([(s, 0) for s in (0x00, 0x08, 0x20, 0x28, 0x40, 0x48, 0x60, 0x68)]
                               if h_ & 0x80 and (h_ & 0x7F) == 0x40 else orig_resp(h_))
for k in ("ID", "VERSION"):
    print(f"2. {k}, FIFO empty (step 3): {R.slip_hazards(k)}")
print("window slip neighbours:", [hex(x) for x in R.window_slip_neighbours()])
