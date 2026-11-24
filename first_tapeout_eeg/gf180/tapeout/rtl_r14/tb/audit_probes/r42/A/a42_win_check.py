# Independent check (not from the RTL or fsm_spec): CIC window of output n (pipelined integrators, window 3R-2
# inputs ending 2 before the interval's end), the OVL intervals n-2..n, and the CHANGED marks (3 + T_ELEC outputs
# after a step at a tick), at every tick position of both rates over a 1 ms interval.
R = 1024
def window(n):            # inputs (frames) of output n's window; interval n = frames [R(n-1), Rn-1]
    newest = R * n - 3
    return range(newest - (3 * R - 2) + 1, newest + 1)
# 1) window = intervals n-2..n minus the last two inputs of interval n
for n in range(3, 8):
    w = window(n)
    assert w.start == R * (n - 3) and w.stop - 1 == R * n - 3
# 2) CHANGED: a step at the tick of frame f (outputs change at e25 of f; the first input affected is f+1)
bad = 0
for rate, (period, tframe) in {"128k": (8, 1), "64k": (16, 3)}.items():
    for T_ELEC in (0, 1, 2, 5):
        for f in range(R * 10, R * 11):
            if f % period != tframe:
                continue
            # outputs after the tick: output k at frame Rk-1, cycle 8 (> tick frame f, cycle 24)
            first_out = (f + 1 + R - 1) // R          # smallest k with Rk-1 > f  (f never equals Rk-1)
            marked = set(range(first_out, first_out + 3 + T_ELEC))
            # a window straddles the step if it holds inputs at or before f and after f; or it starts less
            # than T_ELEC ms (T_ELEC*R frames) after the step
            for k in range(first_out, first_out + 10 + T_ELEC):
                w = window(k)
                straddle = (w.start <= f < w.stop - 1)
                early = (w.start - (f + 1)) < T_ELEC * R
                need = straddle or early
                if need != (k in marked):
                    bad += 1
print("CHANGED marks vs straddling/early windows, both rates, every tick of an interval, T_ELEC 0/1/2/5: mismatches", bad)
# 3) the three non-hit extremes of a detection: largest weight they can have in the previous (unmarked) window
import itertools
h = lambda j: (j + 1) * (j + 2) // 2         # sinc^3 weight of the input j positions from the window's newest
best = 0.0
for hit_off in range(0, 32):                 # the hit (4th extreme) at the first frame of interval n
    pass
# hit at frame e+1 (e = end of interval n-1); the other three in [e-30, e]; window n-1's newest input is e-2
cands = [e for e in range(-30, 1)]           # offsets from e
w_in = [d for d in cands if d <= -2]         # inside window n-1
for trio in itertools.combinations(w_in, 3):
    best = max(best, sum(h(-2 - d) for d in trio) / R ** 3)
print(f"largest weight of the three non-hit extremes in the unmarked window: {best:.4e}")
