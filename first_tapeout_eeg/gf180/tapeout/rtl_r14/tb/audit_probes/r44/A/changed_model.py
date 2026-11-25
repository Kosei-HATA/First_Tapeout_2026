"""Audit 44 A: CHANGED marks vs. windows, from the CIC arithmetic (eeg_cic3: input of frame f at cycle 3; output n at
cycle 8 of frame 1024 n + 1023; window of output n = inputs of frames 1024(n-2) .. 1024 n + 1021 (3R-2 inputs ending two
before the interval's end)). A step applied at e25 of tick frame X affects inputs of frames > X. RTL marks the next
3 + T_ELEC outputs after the tick (eeg_digital_top chg_cnt)."""
R = 1024
bad = 0
for rate, (per, tf) in {"128k": (8, 1), "64k": (16, 3)}.items():
    for te in range(0, 6):
        for X in range(10 * R, 11 * R):
            if X % per != tf:
                continue
            n0 = (X - 1023 + R - 1) // R            # first output n with 1024 n + 1023 > X (output after the tick)
            while 1024 * n0 + 1023 <= X:
                n0 += 1
            marked = set(range(n0, n0 + 3 + te))
            need = set()
            for n in range(n0 - 2, n0 + 3 + te + 4):
                ws, we = R * (n - 2), R * n + 1021
                straddle = ws <= X < we                       # inputs <= X and > X both in the window
                early = ws > X and (ws - (X + 25 / 32)) * 32 / 32.768e6 < te * 1e-3   # starts < T_ELEC after the step
                if straddle or early:
                    need.add(n)
            if not need <= marked or any(n < n0 for n in need):
                bad += 1
                if bad < 5:
                    print(rate, te, X, sorted(need), sorted(marked))
            extra = marked - need
            if extra and te == 0 and X % R not in range(R - 8, R):  # marks beyond the need (conservative) only near output frames
                pass
print("mismatches (a window needing CHANGED left unmarked, or a need before the mark):", bad)
