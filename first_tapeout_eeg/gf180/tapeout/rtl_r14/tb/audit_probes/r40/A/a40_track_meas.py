# Audit 40 A: step 7's alternative tracking threshold "0.6 x the step measured as the difference of the readings at
# M and M +- 1" against the extracted DAC's local steps (gf180_realistic_eval_20261028.md, 1 段の大きさ):
#   range 1: 222..307 uV, range 2: 122..332 uV, ranges 3, 4: 100..332 uV (R_e ~ 0, input-referred); the largest step
#   is every bit-0 transition (even M -> M + 1, w0: 307 uV in range 1, 331.4 uV in ranges >= 2), the smallest the top
#   carries (63->64, 127->128, 255->256); measured on the extracted chip: 99->100 299.8, 995->996 263.0, 996->997 331.4.
# A host moving M by one step whenever the unmarked mean leaves +-T limit-cycles on a pair of local step s when
# T < s / 2: for offsets at fraction f of the pair with T/s < f < 1 - T/s both neighbours read beyond T.
# All values scale by (1 + R_e / R_sc) alike, so the fractions hold for every electrode.
import numpy as np
cases = [("range >= 2", 331.4, [100.0, 122.0, 222.0, 263.0, 299.8, 331.4]),
         ("range 1", 307.0, [222.0, 299.8, 307.0])]
print("fixed formula T = 0.6 x 301 uV = %.1f uV" % (0.6 * 301))
for name, s_big, meas in cases:
    print(name, "- largest local step (a bit-0 pair) %.1f uV, half %.1f uV" % (s_big, s_big / 2))
    for s_m in meas + [301.0]:
        T = 0.6 * s_m
        lo, hi = T / s_big, 1 - T / s_big
        frac = max(0.0, hi - lo)
        # walk: the true offset at the middle of the bit-0 pair, the host starts at the lower M
        f, m, moves = 0.5, 0, 0
        for _ in range(40):
            r = (f - m) * s_big
            if r > T: m += 1; moves += 1
            elif r < -T: m -= 1; moves += 1
        tag = "fixed formula" if s_m == 301.0 else "measured %.1f uV" % s_m
        print("   T = 0.6 x %-18s = %6.1f uV: offsets in that pair that limit-cycle %5.1f %%  (window %5.1f uV), moves in 40 decisions at f = 0.5: %d"
              % (tag, T, frac * 100, frac * s_big, moves))
# the documented chip example (range 4, 300 mV): residuals at 995, 996, 997 = +440.7, +177.6, -153.7 uV
T = 0.6 * 263.0
print("chip example: T from the 995->996 step = %.1f uV; at M 996 reading +177.6 -> %s; at 997 reading -153.7 -> %s"
      % (T, "move" if 177.6 > T else "stay", "move" if 153.7 > T else "stay"))
print("  the same chip with the offset 12 uV lower (f = %.3f of the 996/997 pair):" % ((177.6 - 12) / 331.4),
      "996 reads %+.1f, 997 reads %+.1f -> both beyond +-%.1f" % (177.6 - 12, -153.7 - 12, T))
# a host that averages the two sides of M at a top carry (range 3/4: 255->256 = 100 uV, 256->257 = w0 = 331.4 uV)
s_avg = (100.0 + 331.4) / 2
T = 0.6 * s_avg
print("mean of both sides at the 255/256 carry: %.1f uV -> T %.1f uV, limit-cycle share of the 256/257 pair %.1f %%"
      % (s_avg, T, 100 * max(0.0, 1 - 2 * T / 331.4)))
# the larger side (one side of every M is a pure bit-0 transition, the range's largest step)
print("larger side: T = 0.6 x 331.4 = %.1f uV >= half of the largest step %.1f uV" % (0.6 * 331.4, 331.4 / 2))
# margin of the fixed formula over the largest residual (typical 166.2; 167 at 2x and 169 at 4x the assumed MIM mismatch)
for r in (166.2, 167.0, 169.0):
    print("fixed formula 180.6 uV over the largest residual %.1f uV: margin %.1f %%" % (r, 100 * (180.6 / r - 1)))
