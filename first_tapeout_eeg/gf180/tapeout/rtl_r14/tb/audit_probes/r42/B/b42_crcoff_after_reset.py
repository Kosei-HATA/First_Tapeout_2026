# A chip reset unexpectedly (CRC off, every setting at its reset value) answering the host's CRC-format reads
# [0x80|a, 0, 0] as a CRC-off burst [R(a), R(a+1)]. Variable registers take every value they can take after the
# reset: STATUS fixed bits, ALERT 1 (RESET_FLAG), AFE_RST 1, CMD_PENDING / READY / DATA 0 (IDLE, empty FIFO), OVL_NOW any;
# STATE 0; FIFO_LEVEL 0; ERR odd (RESET_FLAG stays: the host's 3-byte writes are FRAME_ERR) with any other bits;
# DFLAG 0 (no FILL / RUN). Which reads pass the host's CRC check, and with what value?
def crc8(data, c=0):
    for d in data:
        c ^= d
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c
fixed = {0x00:[0xE6],0x01:[0x10],0x02:[0x18],0x04:[0],0x05:[0],0x07:[0],0x08:[0xFF],0x09:[0x03],
         0x0A:[0x03],0x0B:[0xE8],0x0C:[0x05],0x10:[0],0x11:[0],
         0x20:[0],0x21:[0],0x22:[0],0x23:[3],0x24:[8],0x25:[1],0x26:[1],0x27:[0x13],0x28:[7],
         0x30:[0],0x31:[0],0x32:[0],0x33:[3],0x34:[8],0x35:[1],0x36:[1],0x37:[0x13],0x38:[7],
         0x40:[0],0x50:[5],0x51:[0],0x52:[0x20],0x53:[3],0x54:[0x0D],0x55:[0],0x60:[0],0x61:[0],0x62:[0],0x70:[0],0x71:[0]}
fixed[0x03] = [0xA1, 0xA3]
fixed[0x06] = [e for e in range(256) if e & 1]
def vals(a): return fixed.get(a & 0x7F, [0])
hits = []
for a in sorted(fixed):
    if a == 0x40: continue
    for v in vals(a):
        for nx in vals(a + 1):
            if crc8([0x80 | a, v]) == nx:
                hits.append((hex(a), hex(v), hex(nx)))
print(hits)
