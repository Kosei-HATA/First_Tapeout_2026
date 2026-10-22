#!/usr/bin/env python3
"""Transistor-level switching-charge check of the DAC1 unit cell
(dac1_cell.spice), same method as gf180/sim/dac2_cell/run_cell.py: outputs at
ideal virtual grounds, D/DB patterns at 1.024 MHz through 1 kOhm, per-edge
charge minus the ideal step -> q01, q10; even part q_s = (q01+q10)/2 is the
signal-dependent (ISI) error. Requirement: |q_s| <= 1e-5 of the element's
differential charge 2*Iu*T = 1.627 pC, i.e. 0.016 fC (behavioral model:
1e-5 -> 107.5 dB with all elements erring in the same direction).

Usage: python3 run_cell.py [--skew ps] [--voff mV] [--corner c] [--temp C]
       [--mc seeds] [--rmis frac] [--tol A|B|C] [--tr ns]
--rmis applies a static P/N resistor mismatch (the PDK has no local resistor
mismatch model). Outputs go to ./runs/ (ignored by git).
"""
import argparse
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dac2_cell"))
import run_cell as dac2  # noqa: E402  (shared pattern/run/TOL helpers)

VDD, VCM, T = dac2.VDD, dac2.VCM, dac2.T


RES_CORNER = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff",
              "sf": "res_typical", "fs": "res_typical"}


def run(deck, name):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "tb.spice"), "w") as f:
        f.write(deck)
    r = dac2.subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    with open(os.path.join(d, "run.log"), "w") as f:
        f.write(r.stdout + r.stderr)
    return d


def header(args, mismatch, seed):
    return f"""* dac1 cell test
.include {dac2.PDK}/design.ngspice
.lib {dac2.PDK}/sm141064.ngspice {args.corner}
.lib {dac2.PDK}/sm141064.ngspice {RES_CORNER[args.corner]}
.param sw_stat_mismatch={1 if mismatch else 0}
.include {HERE}/dac1_cell.spice
.temp {args.temp}
.options sparse {dac2.TOLS[args.tol]} seed={seed}
VDD VDD 0 {VDD}
VRP VRP 0 {VCM + 0.25}
VRN VRN 0 {VCM - 0.25}
"""


def cell_lines(args, rl_p, rl_n):
    """Flattened unit cell so the P and N resistors can be mismatched."""
    if args.arch == "switched":
        return f"""XTPP XP VRP D  DB VDD 0 dac1_tg
XTPN XP VRN DB D  VDD 0 dac1_tg
XRP  XP OUTP 0 ppolyf_u_3k r_length={rl_p:.6e} r_width=2u
XTNP XN VRP DB D  VDD 0 dac1_tg
XTNN XN VRN D  DB VDD 0 dac1_tg
XRN  XN OUTN 0 ppolyf_u_3k r_length={rl_n:.6e} r_width=2u"""
    w = args.ws
    return f"""XRP  VRP XP 0 ppolyf_u_3k r_length={rl_p:.6e} r_width=2u
XSPP XP D  OUTP 0 nfet_03v3 W={w}u L=0.28u nf=1
XSPN XP DB OUTN 0 nfet_03v3 W={w}u L=0.28u nf=1
XRN  VRN XN 0 ppolyf_u_3k r_length={rl_n:.6e} r_width=2u
XSNN XN D  OUTN 0 nfet_03v3 W={w}u L=0.28u nf=1
XSNP XN DB OUTP 0 nfet_03v3 W={w}u L=0.28u nf=1"""


def charge(args, seed=1, mismatch=False, tag=""):
    reps = 16
    pats = {"tog1": [0, 1] * reps * 2, "tog2": [0, 0, 1, 1] * reps}
    t0, tr = 2e-6, args.tr * 1e-9
    out = {}
    for name, bits in pats.items():
        bits = [0, 0, 0, 0] + bits + [0, 0, 0, 0]
        tstop = t0 + len(bits) * T
        rl_p = 195.5e-6 * (1 + args.rmis / 2)
        rl_n = 195.5e-6 * (1 - args.rmis / 2)
        deck = header(args, mismatch, seed) + f"""
VOP OUTP 0 {VCM + args.voff * 1e-3 / 2}
VON OUTN 0 {VCM - args.voff * 1e-3 / 2}
VD DS 0 PWL({dac2.pattern_pwl(bits, t0, tr)})
VDB DBS 0 PWL({dac2.pattern_pwl(bits, t0, tr, skew=args.skew * 1e-12, invert=True)})
RD DS D 1k
RDB DBS DB 1k
{cell_lines(args, rl_p, rl_n)}
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
        os.remove(os.path.join(d, "tr.csv"))
        t, ip, inn = data[:, 0], data[:, 1], data[:, 3]
        idiff = ip - inn
        cq = np.concatenate([[0.0], np.cumsum(0.5 * (idiff[1:] + idiff[:-1]) * np.diff(t))])

        def q_at(x):
            return np.interp(x, t, cq)

        def i_mean(a, b):
            return (q_at(b) - q_at(a)) / (b - a)

        q01, q10 = [], []
        for k in range(1, len(bits)):
            if bits[k] == bits[k - 1]:
                continue
            te = t0 + k * T
            i_before = i_mean(te - 0.45 * T, te - 0.05 * T)
            i_after = i_mean(te + 0.55 * T, te + 0.95 * T) if k + 1 < len(bits) and bits[k + 1] == bits[k] \
                else i_mean(te + 0.4 * T, te + 0.48 * T)
            q = q_at(te + T / 2) - q_at(te - T / 2) - (i_before + i_after) * T / 2
            (q01 if bits[k] == 1 else q10).append(q)
        a, b = t0 + 4 * T, t0 + (len(bits) - 4) * T
        out[name] = dict(q01=np.median(q01), q10=np.median(q10), toggles=len(q01) + len(q10),
                         qtot=q_at(b) - q_at(a),
                         i1=np.median(idiff[(t > a) & (t < b) & (idiff > 0)]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skew", type=float, default=0.0)
    ap.add_argument("--voff", type=float, default=0.0)
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument("--mc", type=int, default=0)
    ap.add_argument("--rmis", type=float, default=0.0)
    ap.add_argument("--tol", choices=sorted(dac2.TOLS), default="A")
    ap.add_argument("--tr", type=float, default=1.0)
    ap.add_argument("--arch", choices=["switched", "steered"], default="switched",
                    help="switched: TGs select VRP/VRN; steered: resistors fixed, NMOS steer")
    ap.add_argument("--ws", type=float, default=1.0, help="steering NMOS width (um)")
    args = ap.parse_args()
    if args.mc:
        qs = []
        for s in range(1, args.mc + 1):
            r = charge(args, seed=s, mismatch=True, tag=f"_mc{s}")["tog1"]
            qs.append((r["q01"] + r["q10"]) / 2)
            print(f"seed {s}: q_s {qs[-1]*1e15:+.5f} fC, q_a {(r['q01']-r['q10'])/2*1e15:+.4f} fC, "
                  f"diff level {r['i1']*1e6:.4f} uA", flush=True)
        qs = np.array(qs)
        print(f"MC {len(qs)}: q_s mean {qs.mean()*1e15:+.5f} fC, sigma {qs.std(ddof=1)*1e15:.5f} fC, "
              f"max |q_s| {np.abs(qs).max()*1e15:.5f} fC (requirement 0.016 fC)")
        return
    out = charge(args)
    for name, r in out.items():
        qs, qa = (r["q01"] + r["q10"]) / 2, (r["q01"] - r["q10"]) / 2
        print(f"{name}: q01 {r['q01']*1e15:+.4f} fC, q10 {r['q10']*1e15:+.4f} fC -> even q_s "
              f"{qs*1e15:+.5f} fC, odd q_a {qa*1e15:+.4f} fC; diff level {r['i1']*1e6:.4f} uA")
    a, b = out["tog1"], out["tog2"]
    print(f"cross-check q_s from pattern totals: "
          f"{(a['qtot'] - b['qtot']) / (a['toggles'] - b['toggles']) * 1e15:+.5f} fC (requirement 0.016 fC)")


if __name__ == "__main__":
    main()
