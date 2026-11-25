"""Audit 43 B: after an unexpected reset the chip is CRC-off at its reset values; the host keeps sending CRC-form
3-byte reads [0x80|a, 0, 0] and the chip answers a continuous read [v(a), v(a+1)]. Does any read pass the host's CRC?
Reachable values: reset values; STATUS any with the fixed bits; STATE 0; FIFO_LEVEL 0; ERR RESET_FLAG with FRAME_ERR
(the host's 3-byte writes) and ADDR_ERR / CMD_ERR / RANGE_ERR / CRC_ERR / STATE_ERR / CFG_ERR not reachable; DFLAG 0."""
import sys
sys.path.insert(0, sys.argv[1])
import regmap as RM
vals = {}
for a, n, acc, lock, fl, _ in RM.REGS:
    if n == "STATUS":
        v = [x for x in range(0x80, 0xC0)]
    elif n == "ERR":
        v = [0x01, 0x03, 0x00, 0x02]          # RESET_FLAG (until cleared), FRAME_ERR from 3-byte frames
    elif n in ("STATE", "FIFO_LEVEL", "DFLAG", "COMMAND", "TEST_KEY", "SAMPLE"):
        v = [0]
    else:
        v = [RM.reset_of(n)]
    vals[a] = v
    if any(f["cls"] == "apply" for f in fl):
        vals[a + RM.SHADOW_MIRROR] = v
hits = []
for a in range(128):
    if a not in vals or a == 0x40:
        continue
    for x in vals[a]:
        for y in vals.get((a + 1) & 0x7F, [0]):
            if RM.crc8([0x80 | a, x]) == y:
                hits.append((hex(a), hex(x), hex(y)))
print("CRC-form reads of a reset CRC-off chip that pass:", hits)
