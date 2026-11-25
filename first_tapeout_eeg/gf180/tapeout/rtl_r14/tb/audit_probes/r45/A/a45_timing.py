# audit 45 A: independent arithmetic from the RTL's frame timing (not fsm_spec): tick frames, ALIGN length, release->clear,
# APPLY tick -> RUN minimum, CHOP1 boundary vs first stored window, rate-switch PRE lengths.
MCLK = 32.768e6
F = 32
def ticks(rate):            # tick frames mod period: 128k frame 1 of 8, 64k frame 3 of 16
    return (8, 1) if rate == 128 else (16, 3)
def next_tick(f, rate):     # first tick frame >= f
    p, t = ticks(rate)
    k = (f - t + p - 1) // p
    return k * p + t
res = {}
for rate in (128, 64):
    p, t = ticks(rate)
    al = []
    for a in range(t, 2048 + t, p):          # ALIGN entered at e25 of tick frame a
        Fo = 1023 + 1024 * ((a + 1 - 1023 + 1023) // 1024)   # first output frame > a
        Fo = min(x for x in range(1023, 6000, 1024) if x > a)
        al.append((Fo - a) * F + 8 - 25)
    res[rate] = (min(al), max(al))
print("ALIGN e25 -> clear e8 (MCLK):", res)
for rate in (128, 64):
    p, t = ticks(rate)
    rec = 29 * 8; rec = ((rec + p - 1) // p) * p if rate == 64 else rec
    lo, hi = res[rate]
    print(rate, "release->clear with T_REC 32 (ms): %.4f .. %.4f" % ((256*F + lo)/MCLK*1e3, (256*F + hi)/MCLK*1e3))
    pre, rst = 24, 104
    if rate == 64: pre, rst = 32, 112
    print(rate, "APPLY tick -> RUN min (ms): %.5f" % (((pre + rst + rec) * F + lo + 1 + 3072 * F) / MCLK * 1e3))
# CHOP1: APPLY in RUN at tick frame a (128k, default timers, T_ELEC 0): new rate from the first 1024k > a; first stored
# window starts at the clear's next frame
n_same = n_all = 0
for a in range(1, 1024, 8):
    clear_tick = a + 24 + 104 + 256
    Fo = min(x for x in range(1023, 6000, 1024) if x > clear_tick)
    b = min(x for x in range(1024, 6000, 1024) if x > a)
    n_all += 1; n_same += (b == Fo + 1)
print("CHOP1 change at the first stored window's first frame: %d / %d = %.3f" % (n_same, n_all, n_same / n_all))
# rate switch inside PRE
for T in (3, 4):
    out = []
    for a in (1, 9):            # 128 -> 64: switch at frame 16, then 64k ticks at 16k + 3
        e = a + 8 * T; f = min(x for x in range(19, 400, 16) if x >= e); out.append(("128->64", a, f - a))
    a = 3; e = a + 8 * T; f = min(x for x in range(17, 400, 8) if x >= e); out.append(("64->128", a, f - a))
    print("T_PRE", T, out)
