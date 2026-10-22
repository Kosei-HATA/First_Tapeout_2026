#!/usr/bin/env python3
"""Transistor-level checks of the DAC2 unit cell (dac2_cell.spice).

dc     : unit current, output resistance, PMOS/NMOS (CM) mismatch vs VOUT
charge : switching charge per transition from data patterns at the stage-2
         clock (1.024 MHz) with the outputs held at ideal virtual grounds.
         For each edge the differential charge in [t_edge-T/2, t_edge+T/2]
         minus the ideal step gives q01 (0->1) and q10 (1->0);
         even part q_s = (q01+q10)/2 (signal-dependent, spec <= 0.11 fC),
         odd part  q_a = (q01-q10)/2 (= first difference of the DAC code,
         linear and harmless). A cross-check compares toggle-every-clock and
         toggle-every-2-clocks patterns of equal duty.

Usage: python3 run_cell.py dc|charge [--skew ps] [--voff mV] [--mc seeds]
       [--corner typical|ss|ff|sf|fs] [--temp C] [--tr ns] [--tol A|B|C]
       [--cells N] [--bias-r ohm] [--keep]
Charges are reported per cell. --cells 31 --bias-r 10e3 switches the whole
array at once through a shared, non-ideal cascode bias line (worst-case
kickback). Outputs go to ./runs/ (ignored by git).
"""
import argparse
import os
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
VDD, VCM = 3.3, 1.65
T = 1 / 1.024e6
IREF = 234.4e-9  # 10 x Iu
VBPC, VBNC = 1.8, 1.5
# numerical settings; results are compared across these to confirm convergence
# (abstol 1e-14 / chgtol 1e-18 made the steering edges fail with "timestep too small")
TOLS = {
    "A": "method=gear maxord=2 reltol=1e-5 abstol=1e-13 vntol=1e-7 chgtol=1e-17",
    "B": "method=trap reltol=1e-5 abstol=1e-13 vntol=1e-7 chgtol=1e-17",
    "C": "method=gear maxord=2 reltol=1e-6 abstol=1e-12 vntol=1e-6 chgtol=1e-16",
}
TOL = TOLS["A"]


def header(corner, temp, mismatch, seed, bias_r=0.0):
    """bias_r > 0 drives the cascode gates through that source resistance
    (shared bias line with its 1 pF decoupling) instead of ideal sources."""
    if bias_r > 0:
        casc = (f"VBPC VBPCS 0 {VBPC}\nRBPC VBPCS VBPC {bias_r}\n"
                f"VBNC VBNCS 0 {VBNC}\nRBNC VBNCS VBNC {bias_r}\n")
    else:
        casc = f"VBPC VBPC 0 {VBPC}\nVBNC VBNC 0 {VBNC}\n"
    return f"""* dac2 cell test
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.param sw_stat_mismatch={1 if mismatch else 0}
.include {HERE}/dac2_cell.spice
.temp {temp}
.options sparse {TOL} seed={seed}
VDD VDD 0 {VDD}
IRP XIRP 0 DC {IREF}
IRN VDD XIRN DC {IREF}
{casc}XB XIRP XIRN VBP VBPC VBN VBNC VDD 0 dac2_bias
"""


def run(deck, name):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "tb.spice"), "w") as f:
        f.write(deck)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    with open(os.path.join(d, "run.log"), "w") as f:
        f.write(r.stdout + r.stderr)
    return d


def dc(args):
    deck = header(args.corner, args.temp, False, 1) + f"""
VOP OUTP 0 {VCM}
VON OUTN 0 {VCM}
VD D 0 {VDD}
VDB DB 0 0
XC OUTP OUTN D DB VBP VBPC VBN VBNC VDD 0 dac2_cell
.control
set noaskquit
op
print i(vop) i(von) v(vbp) v(vbn) v(xc.xs) v(xc.xp) v(xc.ys) v(xc.yn)
dc vop {VCM - 0.05} {VCM + 0.05} 0.005
wrdata dc_vop.csv i(vop)
quit
.endc
.end
"""
    d = run(deck, f"dc_{args.corner}_{args.temp}")
    print(open(os.path.join(d, "run.log")).read().split("Node")[0][-1500:])
    data = np.loadtxt(os.path.join(d, "dc_vop.csv"))
    v, i = data[:, 0], data[:, 1]
    g = np.polyfit(v, i, 1)[0]
    print(f"OUTP current at VCM: {np.interp(VCM, v, i)*1e9:.3f} nA, "
          f"Rout = {1/abs(g)/1e9:.2f} GOhm (from +-50 mV sweep)")


def pattern_pwl(bits, t0, tr, skew=0.0, invert=False):
    pts = [(0.0, VDD * ((1 - bits[0]) if invert else bits[0]))]
    for k in range(1, len(bits)):
        if bits[k] != bits[k - 1]:
            t = t0 + k * T + skew
            a = (1 - bits[k - 1]) if invert else bits[k - 1]
            b = (1 - bits[k]) if invert else bits[k]
            pts += [(t, VDD * a), (t + tr, VDD * b)]
    return " ".join(f"{t:.12e} {v:.6g}" for t, v in pts)


def charge(args, seed=1, mismatch=False, tag=""):
    reps = 16
    pats = {"tog1": [0, 1] * reps * 2, "tog2": [0, 0, 1, 1] * reps, "tog4": [0, 0, 0, 0, 1, 1, 1, 1] * (reps // 2)}
    t0 = 2e-6
    out = {}
    for name, bits in pats.items():
        bits = [0, 0, 0, 0] + bits + [0, 0, 0, 0]
        tstop = t0 + len(bits) * T
        tr = args.tr * 1e-9
        cells = "\n".join(f"RD{c} DS D{c} 1k\nRDB{c} DBS DB{c} 1k\n"
                          f"XC{c} OUTP OUTN D{c} DB{c} VBP VBPC VBN VBNC VDD 0 dac2_cell"
                          for c in range(args.cells))
        deck = header(args.corner, args.temp, mismatch, seed, args.bias_r) + f"""
VOP OUTP 0 {VCM + args.voff * 1e-3 / 2}
VON OUTN 0 {VCM - args.voff * 1e-3 / 2}
VD DS 0 PWL({pattern_pwl(bits, t0, tr)})
VDB DBS 0 PWL({pattern_pwl(bits, t0, tr, skew=args.skew * 1e-12, invert=True)})
{cells}
.control
set noaskquit
tran 0.1n {tstop:.9e} 0 0.5n
wrdata tr.csv i(vop) i(von)
quit
.endc
.end
"""
        d = run(deck, f"charge_{name}{tag}")
        data = np.loadtxt(os.path.join(d, "tr.csv"))
        if not args.keep:  # ~9 MB per run; keep only the deck and log
            os.remove(os.path.join(d, "tr.csv"))
        t, ip, inn = data[:, 0], data[:, 1], data[:, 3]
        idiff = ip - inn
        cq = np.concatenate([[0.0], np.cumsum(0.5 * (idiff[1:] + idiff[:-1]) * np.diff(t))])
        icm = 0.5 * (ip + inn)

        def q_at(x):
            return np.interp(x, t, cq)

        def i_mean(a, b):
            return (q_at(b) - q_at(a)) / (b - a)

        q01, q10 = [], []
        for k in range(1, len(bits)):
            if bits[k] == bits[k - 1]:
                continue
            te = t0 + k * T
            a, b = te - T / 2, te + T / 2
            # static levels from the quiet second half of the neighbouring periods
            i_before = i_mean(te - 0.45 * T, te - 0.05 * T)
            i_after = i_mean(te + 0.55 * T, te + 0.95 * T) if k + 1 < len(bits) and bits[k + 1] == bits[k] \
                else i_mean(te + 0.4 * T, te + 0.48 * T)
            q = q_at(b) - q_at(a) - (i_before + i_after) * T / 2
            (q01 if bits[k] == 1 else q10).append(q)
        # equal-duty pattern totals over whole pattern repeats
        a, b = t0 + 4 * T, t0 + (len(bits) - 4) * T
        n = args.cells  # report per cell (all cells toggle together)
        out[name] = dict(q01=np.median(q01) / n, q10=np.median(q10) / n,
                         toggles=len(q01) + len(q10), qtot=(q_at(b) - q_at(a)) / n,
                         icm=np.median(icm[(t > a) & (t < b)]) / n,
                         i1=np.median(idiff[(t > a) & (t < b) & (idiff > 0)]) / n)
    return out


def report(out):
    for name, r in out.items():
        qs, qa = (r["q01"] + r["q10"]) / 2, (r["q01"] - r["q10"]) / 2
        print(f"{name}: q01 {r['q01']*1e15:+.4f} fC, q10 {r['q10']*1e15:+.4f} fC -> "
              f"even q_s {qs*1e15:+.4f} fC, odd q_a {qa*1e15:+.4f} fC; "
              f"pattern total {r['qtot']*1e15:+.4f} fC over {r['toggles']} toggles; "
              f"diff level {r['i1']*1e9:.3f} nA, CM {r['icm']*1e12:+.1f} pA")
    a, b = out["tog1"], out["tog2"]
    print(f"cross-check q_s from pattern totals (tog1 - tog2): "
          f"{(a['qtot'] - b['qtot']) / (a['toggles'] - b['toggles']) * 1e15:+.4f} fC")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dc", "charge"])
    ap.add_argument("--skew", type=float, default=0.0, help="DB edge skew vs D (ps)")
    ap.add_argument("--voff", type=float, default=0.0, help="OUTP-OUTN offset (mV)")
    ap.add_argument("--mc", type=int, default=0, help="number of mismatch seeds")
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--tr", type=float, default=1.0, help="gate edge time (ns)")
    ap.add_argument("--tol", choices=sorted(TOLS), default="A", help="numerical setting")
    ap.add_argument("--keep", action="store_true", help="keep waveform CSVs in runs/")
    ap.add_argument("--cells", type=int, default=1, help="cells switching together (array)")
    ap.add_argument("--bias-r", type=float, default=0.0, help="cascode bias source R (ohm)")
    args = ap.parse_args()
    global TOL
    TOL = TOLS[args.tol]
    if args.mode == "dc":
        dc(args)
    elif args.mc:
        qs = []
        for s in range(1, args.mc + 1):
            out = charge(args, seed=s, mismatch=True, tag=f"_mc{s}")
            r = out["tog1"]
            qs.append((r["q01"] + r["q10"]) / 2)
            print(f"seed {s}: q_s {qs[-1]*1e15:+.4f} fC, q_a {(r['q01']-r['q10'])/2*1e15:+.4f} fC, "
                  f"diff level {r['i1']*1e9:.3f} nA, CM {r['icm']*1e12:+.1f} pA", flush=True)
        qs = np.array(qs)
        print(f"MC {len(qs)}: q_s mean {qs.mean()*1e15:+.4f} fC, sigma {qs.std(ddof=1)*1e15:.4f} fC, "
              f"max |q_s| {np.abs(qs).max()*1e15:.4f} fC")
    else:
        report(charge(args))


if __name__ == "__main__":
    main()
