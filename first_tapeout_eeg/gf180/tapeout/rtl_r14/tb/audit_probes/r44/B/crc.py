def crc8(bs, c=0):
    for b in bs:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c
if __name__ == "__main__":
    print("crc8(0x83,0x80)=%02x" % crc8([0x83,0x80]))
    print("crc8(0x85,0x00)=%02x" % crc8([0x85,0x00]))
    print("crc8(0x86,0x01)=%02x" % crc8([0x86,0x01]))
    print("crc8(0x84,0x00)=%02x" % crc8([0x84,0x00]))
    print("crc8(0xC0)=%02x" % crc8([0xC0]))
    print("crc8(0xC0,0*6)=%02x" % crc8([0xC0]+[0]*6))
    print("crc8(0xD5,0x25)=%02x" % crc8([0xD5,0x25]))
    for x in range(4): print("crc8(0xD5,%02x)=%02x" % (x, crc8([0xD5,x])))
