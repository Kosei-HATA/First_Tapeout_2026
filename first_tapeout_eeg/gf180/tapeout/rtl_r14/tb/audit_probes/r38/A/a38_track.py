# Audit 38 A: step 7's tracking threshold (+-54 mV at the ADC input, "0.6 step") against the step size the same
# paragraph gives, 0.301 mV x (1 + R_e / R_sc) x 287 at the ADC input. A host moving M by one step whenever the
# unmarked mean leaves +-T, simulated on an ideal staircase (no noise): does it settle or limit-cycle?
import numpy as np
T = 54.0                      # mV at the ADC input, the requirement's number
for rsc in (5.67, 5.56):
    print(f"R_sc = {rsc} kOhm")
    for re in (0.1, 1.0, 1.42, 2.0, 5.0, 10.0, 20.0):
        s = 0.301 * (1 + re / rsc) * 287.0          # one M step at the ADC input, mV
        ratio = T / s
        # optimum at fractional position f between M and M+1: mean at M is +f*s, at M+1 is -(1-f)*s
        fs = np.linspace(0, 1, 10001)
        cyc = np.mean((fs * s > T) & ((1 - fs) * s > T))     # both neighbours outside +-T: the host never stops
        # walk: start at M with residual f*s, move while |residual| > T, count moves in 40 decisions
        f = 0.5
        m, moves = 0, 0
        for _ in range(40):
            r = (f - m) * s
            if r > T: m += 1; moves += 1
            elif r < -T: m -= 1; moves += 1
        print(f"  R_e {re:5.2f} kOhm: step {s:6.1f} mV, +-54 mV = {ratio:4.2f} step, "
              f"optimum positions that limit-cycle {cyc*100:5.1f} %, moves in 40 decisions at f=0.5: {moves}")
print("0.6 x 0.301 mV =", 0.6 * 0.301, "mV;  0.6 x 0.311 mV =", 0.6 * 0.311, "mV")
print("0.6 x 0.301 x 287 =", 0.6 * 0.301 * 287, "mV;  0.6 x 0.311 x 287 =", 0.6 * 0.311 * 287, "mV;  54/86.4 =", 54 / (0.301 * 287))
