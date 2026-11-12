"""Bit-exact golden model of eeg_cic3 (and helpers shared by the testbenches).

eeg_cic3 arithmetic (identical here, plain Python integers):
  * input x = 2c - 31 on every accepted input
  * W = 37 bit registers, modulo 2^W (two's complement wrap, no saturation)
  * pipelined integrators: i1 += x, i2 += old i1, i3 += old i2
  * on the R-th accepted input since reset/clear (R = 1024) the combs run on
    the updated i3: a = i3 - d1, d1 = i3; b = a - d2, d2 = a; y = b - d3, d3 = b
  * output = saturate_24(round_half_even(y / 2^12))
  * the first NSKIP = 2 output strobes after reset/clear are invalid

Operation stream (one byte per operation, shared with tb_cic.sv):
  0x00..0x1F  accept one input with code c = byte
  0x80        clear (FILTER_CLEAR); the testbench leaves the filter idle
              around it so that no output is in flight
  0xC0..0xDF  clear in the same cycle as an input with code (byte & 0x1F);
              clear wins and that input is NOT accepted
"""

W = 37
R = 1024
SH = 12
WO = 24
NSKIP = 2

MASK = (1 << W) - 1
HALF_RANGE = 1 << (W - 1)

OP_CLEAR = 0x80
OP_CLEAR_EN = 0xC0


def wrap(v):
    """Reduce v modulo 2^W into the signed range [-2^(W-1), 2^(W-1))."""
    return ((v + HALF_RANGE) & MASK) - HALF_RANGE


def round_sat(v, sh=SH, wo=WO):
    """Round-half-to-even right shift by sh, then saturate to signed wo bits."""
    q = v >> sh                       # floor (Python >> is arithmetic)
    r = v & ((1 << sh) - 1)           # remainder 0 .. 2^sh - 1
    half = 1 << (sh - 1)
    if r > half or (r == half and (q & 1)):
        q += 1
    lo = -(1 << (wo - 1))
    hi = (1 << (wo - 1)) - 1
    return min(max(q, lo), hi)


def cic3_run(ops):
    """Run the CIC over an operation stream.

    Returns (outputs, stats). outputs is a list of (data, valid) per output
    strobe (data = signed int). stats counts accepted inputs, clears, wrap
    events per register and rounding cases (coverage information).
    """
    i1 = i2 = i3 = 0
    d1 = d2 = d3 = 0
    cnt = 0
    nstb = 0
    out = []
    st = {"inputs": 0, "clears": 0, "dropped_by_clear": 0,
          "wrap_i1": 0, "wrap_i2": 0, "wrap_i3": 0,
          "wrap_c1": 0, "wrap_c2": 0, "wrap_c3": 0,
          "tie_even": 0, "tie_odd": 0, "round_up": 0, "round_down": 0,
          "saturated": 0}
    half = 1 << (SH - 1)
    for op in ops:
        if op & 0x80:
            # clear (with or without a simultaneous, discarded input)
            i1 = i2 = i3 = 0
            d1 = d2 = d3 = 0
            cnt = 0
            nstb = 0
            st["clears"] += 1
            if op & 0x40:
                st["dropped_by_clear"] += 1
            continue

        x = 2 * op - 31
        # pipelined integrators: each stage adds the OLD value of the previous one
        s1 = i1 + x
        s2 = i2 + i1
        s3 = i3 + i2
        i1 = wrap(s1)
        i2 = wrap(s2)
        i3 = wrap(s3)
        if i1 != s1:
            st["wrap_i1"] += 1
        if i2 != s2:
            st["wrap_i2"] += 1
        if i3 != s3:
            st["wrap_i3"] += 1
        st["inputs"] += 1

        cnt += 1
        if cnt < R:
            continue
        cnt = 0

        # comb section on the updated i3
        s = i3 - d1
        a = wrap(s)
        st["wrap_c1"] += (a != s)
        d1 = i3
        s = a - d2
        b = wrap(s)
        st["wrap_c2"] += (b != s)
        d2 = a
        s = b - d3
        y = wrap(s)
        st["wrap_c3"] += (y != s)
        d3 = b

        r = y & ((1 << SH) - 1)
        if r == half:
            st["tie_odd" if ((y >> SH) & 1) else "tie_even"] += 1
        elif r > half:
            st["round_up"] += 1
        else:
            st["round_down"] += 1
        data = round_sat(y)
        if data != round_sat(y, wo=64):
            st["saturated"] += 1

        valid = nstb >= NSKIP
        if nstb <= NSKIP:
            nstb += 1
        out.append((data, valid))
    return out, st


def crc8(data, poly=0x07, init=0x00):
    """CRC-8, MSB first, no reflection, no final xor (CRC-8/SMBUS)."""
    c = init
    for byte in data:
        c ^= byte
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


if __name__ == "__main__":
    # self checks
    assert crc8(b"123456789") == 0xF4
    assert round_sat(2048) == 0 and round_sat(6144) == 2 and round_sat(-2048) == 0
    assert round_sat(-6144) == -2 and round_sat(2049) == 1 and round_sat(-2049) == -1
    assert round_sat(1 << 40) == (1 << 23) - 1 and round_sat(-(1 << 40)) == -(1 << 23)
    # DC input: every valid output is exactly x * 2^18
    outs, _ = cic3_run([20] * (5 * R))
    assert [d for d, v in outs if v] == [9 << 18] * 3, outs
    print("cic_golden self checks passed")
