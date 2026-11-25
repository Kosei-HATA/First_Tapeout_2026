"""Audit 44 A: independent frame-level model of the r14 tick grid and timer semantics (written from eeg_clkgen.sv /
eeg_seq.sv reading, not from fsm_spec). Recomputes the documented timing claims."""
MCLK = 32.768e6
F = 32  # MCLK per frame

def tick_frames(fast_of_sp, n_sp):
    """ticks (absolute frame index) given the rate per 16-frame superperiod"""
    out = []
    for sp in range(n_sp):
        f0 = 16 * sp
        if fast_of_sp(sp):
            out += [f0 + 1, f0 + 9]
        else:
            out += [f0 + 3]
    return out

def next_tick(ticks, f):
    for t in ticks:
        if t >= f:
            return t
    raise ValueError

# 1. tick spacing incl. switches
sp_set = set()
for pat in range(1 << 8):
    fast = lambda sp, pat=pat: (pat >> (sp % 8)) & 1
    t = tick_frames(fast, 16)
    sp_set |= {b - a for a, b in zip(t, t[1:])}
print("tick spacings (frames):", sorted(sp_set))

# 2. timer: loaded at e25 of tick frame X with N frames; decrements at e0 of X+1.. ; zero from e0 of X+N;
#    expiry at the first tick frame >= X+N. Duration in frames = expiry - X.
def expire(ticks, X, N):
    return next_tick(ticks, X + N)

# 3. ALIGN -> clear: ALIGN entered at e25 of tick frame X, clear at e8 of the first output frame F > X
#    (output frames F = 1024 j + 1023). MCLK from e25 of X to e8 of F = 32 (F - X) - 17.
for name, fast in (("128k", lambda sp: 1), ("64k", lambda sp: 0)):
    t = tick_frames(fast, 4096)
    outs = [1024 * j + 1023 for j in range(70)]
    mn, mx = 10 ** 9, 0
    for X in t[16:3000]:
        Fo = next(o for o in outs if o > X)
        d = 32 * (Fo - X) - 17
        mn, mx = min(mn, d), max(mx, d)
    print(f"{name}: ALIGN entry -> clear {mn}..{mx} MCLK")
    # release (PULSE expiry at tick P) -> RECOVER T_REC=32 (256 frames) -> ALIGN -> clear
    mn, mx = 10 ** 9, 0
    for P in t[16:2500]:
        R = expire(t, P, 256)
        Fo = next(o for o in outs if o > R)
        d = 32 * (Fo - P) - 17
        mn, mx = min(mn, d), max(mx, d)
    print(f"{name}: release -> clear {mn / MCLK * 1e3:.4f}..{mx / MCLK * 1e3:.4f} ms")
    # APPLY tick -> RUN (FILL store at the 3rd output after the clear): min over tick positions, min timers
    best = 10 ** 9
    for X in t[16:2500]:
        p = expire(t, X, 8 * 3); q = expire(t, p, 8 * 13); r = expire(t, q, 8 * 29)
        Fo = next(o for o in outs if o > r)
        run_f = Fo + 3 * 1024                      # store at cycle 8 of that frame -> RUN at e9
        d = 32 * (run_f - X) + 9 - 25
        best = min(best, d)
    print(f"{name}: APPLY tick -> RUN min {best / MCLK * 1e3:.4f} ms (T_PRE 3, T_RST 13, T_REC 29)")

# 4. PRE length across a rate switch (APPLY at tick X of the old rate; the switch at the next wrap)
for T in (3, 4, 5):
    res = {}
    for old in (1, 0):
        for X0 in ([1, 9] if old else [3]):
            fast = lambda sp, old=old: old if sp == 0 else 1 - old
            t = tick_frames(fast, 64)
            e = expire(t, X0, 8 * T)
            res.setdefault(("128->64" if old else "64->128"), set()).add(e - X0 - 8 * T)
    print(f"T_PRE {T}: PRE = 8T + {res}")
