def crc8(data, c=0):
    for d in data:
        c ^= d
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c
print("x with CRC8(D5,x)=0:", [hex(x) for x in range(256) if crc8([0xD5,x])==0])
print("CRC8(50,FF)=%02X" % crc8([0x50,0xFF]))
print("CRC8(D5,0..3):", [hex(crc8([0xD5,x])) for x in range(4)])
print("CRC8(C0,0*6)=%02X" % crc8([0xC0]+[0]*6))
