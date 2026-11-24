"""Audit round 40, B: step 5 (i) in level mode with the round-39 duty. Frame times of round 39's estimate (tcss 1 us,
tcsh 0.5 us, 1 us between frames): an 8-byte frame T8, a 3-byte read T3. Steady state (step 6, level): one frame per
chip per output. A round of (i) with one compared chip adds the empty words of the reference, the compared chip and
the reference's second read-out (3 T8) and two DFLAG reads (2 T3). The deferred reads must be repaid from the spare
1000 - N T8 us per output within the window a deferred chip may wait: FIFO_DEPTH - 1 = 7 output times (the duty; a
chip read at n-1 and skipped at the round's output n is read by n+6: 6 intervals to repay), or about 2 ms after its
DRDY_N fall if step 6's 2-ms rule applies (read by about n+2: 2 intervals, plus one FIFO_LEVEL read T3)."""
for f, T8, T3 in ((1, 66.0, 26.0), (2, 34.25, 14.25)):
    E = 3 * T8 + 2 * T3
    print(f"SCLK {f} MHz: round extra {E:.2f} us")
    for N in range(10, 31):
        S = 1000.0 - N * T8
        if S < 0:
            break
        duty = 6 * S >= E
        wd = 2 * S >= E + T3
        print(f"  N {N:2d}: spare {S:7.2f} us/ms  duty-only {'ok' if duty else 'NO'}  with 2-ms rule {'ok' if wd else 'NO'}")
