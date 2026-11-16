#!/usr/bin/env python3
"""Saturation margins of the AFE core over process corner, supply, BOOST_TRIM and AFE_IBIAS
(11/16), with the output held at the full-scale peak.

The chip-level corner releases of 11/16 (afe_startup.py / afe_trim_start.py on the r12 chip,
a full-scale 2 kHz sine) put the AFE's HD3 at -97.6 dBc at ss with BOOST_TRIM 4/4 and
-59.6 dBc at ss with AVDD -5 %: the PMOS-cascode boosters are referenced to AVDD, so the
PMOS pair drain sits at AVDD - VSG(booster) and the PMOS cascodes lose whatever the AFE's
supply loses, while the output common mode stays at VCM. The trim table of 10/22
(afe_bias_noise.py) was made at 3.3 V with AFE_IBIAS code 2; on the chip the AFE sees
AVDD_AFEI - AVSS_AFEI = 3.196 V at 3.3 V (typical) and the firmware writes code 3.

This bench is afe_bias_noise.py's (the amplifier level eeg_afe_amp of eeg_afe.spice with the
real bias block eeg_bias, one chopper phase frozen, the 1e16 H INP/INN DC path), with:
  - the AFE's supply and VCM as the chip gives them, relative to the AFE's AVSS
    (--vdd, --vcm; defaults: the typical 3.3 V chip run);
  - a DC source in series with each DC-path inductor, so that the operating point is solved
    with OPI - ONI forced to --swing values (INP = ONI + d/2, INN = OPI - d/2: the inputs
    stay at the common mode). Full scale is about +-0.30 V at OPI - ONI (0.943 mV x 297.5
    at the ADC plus the output-chopper loss);
  - VDS - VDSAT of the tails, both halves of each pair, the four cascodes and the boosters.

Cases are corner:code:NBLN:NBLP:vdd (NBLN: PMOS-cascode boosters, NBLP: NMOS-cascode
boosters, units 2/4/6/8; vdd relative to the AFE's AVSS). --grid runs every corner x code x
trim at the three supplies of --avdd (board AVDD; the AFE's VDD and VCM follow the chip runs'
drops per corner, table CHIP below).

Usage: python3 afe_margin_map.py [--cases ss:3:2:2:3.212 ...] [--swing 0 0.3 -0.3]
       python3 afe_margin_map.py --grid [--avdd 3.135 3.3 3.465] [--jobs 3]
       python3 afe_margin_map.py --hd-window [--corners ...] [--avdd ...] [--codes 3] [--jobs 3]

--hd-window: the frozen-phase sine of afe_distortion.py on this bench (run_tran: a 1 kHz full-scale sine, 8 periods,
the ADC input RIN 18.75 kohm as the load) at BOOST_TRIM 4/4 and at the trim with the largest swing margin, against the
board AVDD. Calibrated on the chip-level corner releases of 11/16 (runs/margin_map/calib.py): the AFE output's HD3 here
tracks the chip's 2 kHz HD3 in order, within about +-5 dB, mostly on the pessimistic side.
"""
import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor

import afe_bias_noise as abn
import afe_noise

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs", "margin_map")
# AFE supply and ground (V, against the board ground) in the r12 chip runs at AVDD 3.3 V, AFE_IBIAS 3, BOOST_TRIM 4/4,
# averaged over the last 1 ms of the sine (corner_nodes.py, 11/16), and VCM at the AFE. The AFE's AVDD follows the
# board's one to one (ss / ff at 3.135 V: -0.165 V within 1.5 mV), its AVSS does not move.
CHIP = {"typical": (3.2558, 0.0598, 1.6507), "ss": (3.2624, 0.0505, 1.6505), "ff": (3.2462, 0.0733, 1.6506),
        "fs": (3.2560, 0.0595, 1.6506), "sf": (3.2556, 0.0600, 1.6506)}
DEVS = ["xnt", "xpt", "xn_p", "xn_n", "xp_p", "xp_n", "xnc_p", "xnc_n", "xpc_p", "xpc_n",
        "xgncpb", "xgncnb", "xgpcpb", "xgpcnb", "xgncpl", "xgncnl", "xgpcpl", "xgpcnl"]
NODES = ["opi", "oni", "inp", "inn", "vbp", "vbn", "xdut.xcore.dpp", "xdut.xcore.dpn", "xdut.xcore.dnp",
         "xdut.xcore.dnn", "xdut.xcore.sp", "xdut.xcore.sn", "xdut.xcore.gpcp", "xdut.xcore.gncp"]


def chip_supply(corner, avdd):
    """(vdd, vcm) relative to the AFE's AVSS for a board AVDD."""
    vd, vs, cm = CHIP[corner]
    return vd + (avdd - 3.3) - vs, cm - vs


def deck(corner, code, nbln, nblp, vdd, vcm, swings, nsteps=8):
    """Two DC sweeps of the DC-path offset from 0 to + and - the largest swing (continuation from the balanced point:
    separate .op runs at +-0.30 V failed to converge at some trims, 11/16); VOFN follows VOFP with the opposite sign."""
    afe_noise.BOOST = "tr"
    t = abn.deck(corner, 27, code, afe_noise.RS, abn.AFE, nbln, nblp)
    for old, new in (("VDD VDD 0 3.3\n", f"VDD VDD 0 {vdd:.5f}\n"), ("VCM CM 0 1.65\n", f"VCM CM 0 {vcm:.5f}\n"),
                     ("LDCP INP ONI 1e16\n", "LDCP INP XOFP 1e16\nVOFP XOFP ONI DC 0\n"),
                     ("LDCN INN OPI 1e16\n", "LDCN INN XOFN 1e16\nEOFN XOFN OPI XOFP ONI -1\n")):
        assert old in t, old
        t = t.replace(old, new, 1)
    # the bias block's code inputs are 3.3 V logic levels: keep them at the supply
    t = re.sub(r"^(V(?:IB|BP|BN)[01] \S+ 0) 3\.3$", rf"\1 {vdd:.5f}", t, flags=re.M)
    # the chopper phase controls likewise
    t = re.sub(r"^(V(?:N?C[ID][AB]) \S+ 0) 3\.3$", rf"\1 {vdd:.5f}", t, flags=re.M)
    vecs = ["i(vdd)"] + [f"v({n})" for n in NODES] + \
           [f"@m.xdut.xcore.{d}.m0[{q}]" for d in DEVS for q in ("vds", "vdsat", "id")]
    smax = max(abs(x) for x in swings) / 2
    step = smax / nsteps if smax else 0.01
    body = ["save all " + " ".join(v for v in vecs if v.startswith("@"))]
    for k, sign in enumerate((1, -1)):
        body += [f"dc vofp 0 {sign * smax:.6f} {sign * step:.6f}", f"wrdata sweep{k}.csv " + " ".join(vecs)]
    ctl = ".control\nset noaskquit\nset wr_singlescale\n" + "\n".join(body) + "\nquit\n.endc\n.end\n"
    t = re.sub(r"\.control.*", lambda m: ctl, t, flags=re.S)
    return t


F0, NPER, NSKIP, TSIG = 1e3, 8, 2, 20e-6     # afe_distortion.py's frozen-phase sine


def tran_deck(corner, code, nbln, nblp, vdd, vcm, amp=0.943396e-3, rload=18750.0):
    """afe_distortion.py on this bench: phase A frozen, a 1 kHz sine at the electrodes from 20 us, INP / INN reset by
    switches until 10 us and then held (the 1e16 H path is fragile in .tran), the ADC input RIN 18.75 kohm per side as
    the load. FFT of 8 signal periods after 2."""
    afe_noise.BOOST = "tr"
    t = abn.deck(corner, 27, code, afe_noise.RS, abn.AFE, nbln, nblp)
    rst = ("XRSTP INP RST ONI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5\n"
           "XRSTN INN RST OPI 0 nfet_03v3 W=1u L=1u nf=1 m=1 ad=.5p as=.5p pd=3u ps=3u nrd=.5 nrs=.5\n"
           "VRST RST_D 0 PWL(0 3.3 10u 3.3 11u 0)\nRGRST RST_D RST 10\n")
    for old, new in (("VDD VDD 0 3.3\n", f"VDD VDD 0 {vdd:.5f}\n"), ("VCM CM 0 1.65\n", f"VCM CM 0 {vcm:.5f}\n"),
                     ("LDCP INP ONI 1e16\nLDCN INN OPI 1e16\n", rst),
                     ("VSRC SRC 0 DC 0 AC 1", f"VSRC SRC 0 DC 0 SIN(0 {amp:.9e} {F0:g} {TSIG:g})"),
                     ("RLOADP OUTP CM 9375", f"RLOADP OUTP CM {rload:g}"),
                     ("RLOADN OUTN CM 9375", f"RLOADN OUTN CM {rload:g}")):
        assert old in t, old
        t = t.replace(old, new, 1)
    t = re.sub(r"^(V(?:IB|BP|BN)[01] \S+ 0) 3\.3$", rf"\1 {vdd:.5f}", t, flags=re.M)
    t = re.sub(r"^(V(?:N?C[ID][AB]) \S+ 0) 3\.3$", rf"\1 {vdd:.5f}", t, flags=re.M)
    tstop = TSIG + (NSKIP + NPER) / F0
    ctl = f""".control
set noaskquit
tran 0.2u {tstop:.6e} 0 0.2u
let vo = v(outp) - v(outn)
let vc = v(opi) - v(oni)
let vi = v(inp) - v(inn)
let vdn = v(xdut.xcore.dnp) - v(xdut.xcore.dnn)
let vdp = v(xdut.xcore.dpp) - v(xdut.xcore.dpn)
linearize vo vc vi vdn vdp
wrdata tr.csv vo vc vi vdn vdp
quit
.endc
.end
"""
    return re.sub(r"\.control.*", lambda m: ctl, t, flags=re.S)


def run_tran(case, amp=0.943396e-3):
    import numpy as np
    corner, code, nbln, nblp, vdd, vcm = case
    d = os.path.join(RUNS, f"hd_{corner}_c{code}_n{nbln}_p{nblp}_v{vdd:.4f}_cm{vcm:.4f}_a{amp * 1e3:.4g}")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "tr.csv")
    txt = tran_deck(corner, code, nbln, nblp, vdd, vcm, amp)
    old = os.path.join(d, "tb.spice")
    if not (os.path.exists(f) and os.path.exists(old) and open(old).read() == txt):   # reuse a finished identical run
        open(old, "w").write(txt)
        r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
        open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    if not os.path.exists(f):
        return case, None
    x = np.loadtxt(f)
    t = x[:, 0]
    m = t >= TSIG + NSKIP / F0 - 1e-12
    n = int(round(NPER / F0 / (t[1] - t[0])))
    out = {}
    for lab, col in (("out", 1), ("core", 3), ("in", 5), ("dn", 7), ("dp", 9)):
        spec = np.abs(np.fft.rfft(x[m, col][:n])) / (n / 2)
        h = [spec[k * NPER] for k in range(1, 6)]
        out[lab] = dict(fund=h[0], hd=[20 * np.log10(v / h[0]) for v in h[1:]])
    out["gain"] = out["out"]["fund"] / amp
    return case, out


def parse(d, swings):
    """the two sweep files -> {swing (OPI - ONI target, V): {sat, idd_mA, nodes}} at the requested swings"""
    import numpy as np
    vecs = ["i(vdd)"] + [f"v({n})" for n in NODES] + \
           [f"@m.xdut.xcore.{dv}.m0[{q}]" for dv in DEVS for q in ("vds", "vdsat", "id")]
    pts = {}
    for k in (0, 1):
        f = os.path.join(d, f"sweep{k}.csv")
        if not os.path.exists(f):
            continue
        x = np.atleast_2d(np.loadtxt(f))
        if x.shape[1] != len(vecs) + 1:
            continue
        for row in x:
            pts[round(2 * row[0], 6)] = dict(zip(vecs, row[1:]))
    res = {}
    for sw in swings:
        key = min(pts, key=lambda q: abs(q - sw)) if pts else None
        if key is None or abs(key - sw) > 1e-4:
            return None                          # the sweep did not reach this swing
        v = pts[key]
        sat = {dv: abs(v[f"@m.xdut.xcore.{dv}.m0[vds]"]) - abs(v[f"@m.xdut.xcore.{dv}.m0[vdsat]"]) for dv in DEVS}
        res[sw] = dict(sat=sat, idd_mA=-v["i(vdd)"] * 1e3, nodes={n: v[f"v({n})"] for n in NODES})
    return res


def run(case, swings):
    corner, code, nbln, nblp, vdd, vcm = case
    d = os.path.join(RUNS, f"{corner}_c{code}_n{nbln}_p{nblp}_v{vdd:.4f}_cm{vcm:.4f}")
    os.makedirs(d, exist_ok=True)
    for k in (0, 1):
        if os.path.exists(os.path.join(d, f"sweep{k}.csv")):
            os.remove(os.path.join(d, f"sweep{k}.csv"))
    for nsteps in (8, 32):                       # a sweep that stops short is retried with finer steps
        open(os.path.join(d, "tb.spice"), "w").write(deck(corner, code, nbln, nblp, vdd, vcm, swings, nsteps))
        r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
        open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
        res = parse(d, swings)
        if res is not None:
            break
    return case, res


def summary(res, swing):
    """min margins at +-swing: PMOS cascodes, NMOS cascodes, PMOS pair, NMOS pair, tails, boosters"""
    out = {}
    groups = {"pc": ("xpc_p", "xpc_n"), "nc": ("xnc_p", "xnc_n"), "pp": ("xp_p", "xp_n"), "np": ("xn_p", "xn_n"),
              "tail": ("xnt", "xpt"), "boost": ("xgncpb", "xgncnb", "xgpcpb", "xgpcnb", "xgncpl", "xgncnl", "xgpcpl",
                                                 "xgpcnl")}
    for g, devs in groups.items():
        vals = [res[s]["sat"][dv] for s in res if abs(abs(s) - swing) < 1e-6 for dv in devs if dv in res[s]["sat"]]
        out[g] = min(vals) if vals else float("nan")
    out["q_pc"] = min(res[s]["sat"][dv] for s in res if abs(s) < 1e-6 for dv in ("xpc_p", "xpc_n"))
    out["q_nc"] = min(res[s]["sat"][dv] for s in res if abs(s) < 1e-6 for dv in ("xnc_p", "xnc_n"))
    out["idd"] = res[min(res, key=abs)]["idd_mA"]
    return out


def best_trim(corner, code, avdd, swings=(0.0, 0.30, -0.30)):
    """The booster trim with the largest swing margin (cascodes and booster loads at full scale) among those that keep
    the pairs and tails at least 50 mV in saturation; None when no trim does."""
    vdd, vcm = chip_supply(corner, avdd)
    best, least_bad = None, None
    for n in (2, 4, 6, 8):
        for p in (2, 4, 6, 8):
            _, res = run((corner, code, n, p, vdd, vcm), list(swings))
            if not res:
                continue
            sm = summary(res, max(abs(s) for s in swings))
            sw = min(sm["pc"], sm["nc"], sm["boost"])
            worst = min(sw, sm["pp"], sm["np"], sm["tail"])
            if least_bad is None or worst > least_bad[0]:
                least_bad = (worst, n, p, sm)
            if min(sm["pp"], sm["np"], sm["tail"]) < 0.05:
                continue
            if best is None or sw > best[0]:
                best = (sw, n, p, sm)
    # no trim keeps the pairs 50 mV in saturation (ff / sf at high AVDD): the one whose smallest margin is largest
    return best or least_bad


def hd_window(corners, avdds, codes, jobs, out):
    """Frozen-phase HD3 against the board AVDD: BOOST_TRIM 4/4 and the best-margin trim of each point."""
    jobs_l = []
    picks = {}
    for c in corners:
        for av in avdds:
            for code in codes:
                b = best_trim(c, code, av)
                picks[(c, av, code)] = b
                vdd, vcm = chip_supply(c, av)
                jobs_l.append((c, av, code, 4, 4, vdd, vcm))
                if b and (b[1], b[2]) != (4, 4):
                    jobs_l.append((c, av, code, b[1], b[2], vdd, vcm))
    print(f"{len(jobs_l)} frozen-phase runs", flush=True)
    rows = []

    def one(j):
        c, av, code, n, p, vdd, vcm = j
        _, o = run_tran((c, code, n, p, vdd, vcm))
        return j, o

    with ThreadPoolExecutor(jobs) as ex:
        for j, o in ex.map(one, jobs_l):
            c, av, code, n, p, vdd, vcm = j
            b = picks[(c, av, code)]
            row = dict(corner=c, avdd=av, code=code, nbln=n, nblp=p, vdd=vdd, vcm=vcm, best=bool(b and (b[1], b[2]) == (n, p)),
                       margin=(b[3] if b and (b[1], b[2]) == (n, p) else None),
                       hd_out=o["out"]["hd"] if o else None, hd_core=o["core"]["hd"] if o else None,
                       gain=o["gain"] if o else None)
            rows.append(row)
            print(f"{c:7s} AVDD {av:.3f} code {code} trim {n}/{p}{' (best)' if row['best'] else ''}: " +
                  (f"out HD3 {o['out']['hd'][1]:.1f} core {o['core']['hd'][1]:.1f} dBc, HD2 {o['out']['hd'][0]:.1f}, gain "
                   f"{o['gain']:.1f}" if o else "failed"), flush=True)
            json.dump(rows, open(out, "w"), indent=1, default=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=None)
    ap.add_argument("--grid", action="store_true")
    ap.add_argument("--hd-window", action="store_true", help="frozen-phase HD3 against AVDD, 4/4 and the best trim")
    ap.add_argument("--corners", nargs="+", default=["typical", "ss", "ff", "sf", "fs"])
    ap.add_argument("--codes", nargs="+", type=int, default=[0, 1, 2, 3])
    ap.add_argument("--units", nargs="+", type=int, default=[2, 4, 6, 8])
    ap.add_argument("--trims", nargs="+", default=None, help="grid: only these P/N trims (e.g. 4/4 2/2 4/2)")
    ap.add_argument("--avdd", nargs="+", type=float, default=[3.135, 3.3, 3.465])
    ap.add_argument("--swing", nargs="+", type=float, default=[0.0, 0.30, -0.30])
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(RUNS, "map.json"))
    a = ap.parse_args()
    if a.hd_window:
        hd_window(a.corners, a.avdd, [c for c in a.codes], a.jobs,
                  a.out if a.out != os.path.join(RUNS, "map.json") else os.path.join(RUNS, "hd_window.json"))
        return
    if a.grid:
        cases = []
        for c in a.corners:
            for av in a.avdd:
                vdd, vcm = chip_supply(c, av)
                tr = ([tuple(int(q) for q in t.split("/")) for t in a.trims] if a.trims else
                      [(n, p) for n in a.units for p in a.units])
                cases += [(c, k, n, p, vdd, vcm) for k in a.codes for n, p in tr]
    else:
        cases = []
        for s in a.cases or ["typical:3:4:4:3.1960"]:
            f = s.split(":")
            c = f[0]
            vdd = float(f[4]) if len(f) > 4 else chip_supply(c, 3.3)[0]
            vcm = float(f[5]) if len(f) > 5 else chip_supply(c, 3.3)[1]
            cases.append((c, int(f[1]), int(f[2]), int(f[3]), vdd, vcm))
    rows = []
    print("| corner | VDD (V) | VCM (V) | code | booster P/N | IDD (mA) | PMOS casc. (0 / FS) | NMOS casc. (0 / FS) | "
          "PMOS pair | NMOS pair | tails | boosters |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    with ThreadPoolExecutor(a.jobs) as ex:
        for case, res in ex.map(lambda c: run(c, a.swing), cases):
            c, k, n, p, vdd, vcm = case
            if res is None:
                print(f"| {c} | {vdd:.4f} | {vcm:.4f} | {k} | {n}/{p} | failed | | | | | | |", flush=True)
                continue
            fs = max(abs(s) for s in res)
            sm = summary(res, fs)
            rows.append(dict(corner=c, vdd=vdd, vcm=vcm, code=k, nbln=n, nblp=p, swing=fs, **sm,
                             detail={f"{s:+.3f}": res[s] for s in res}))
            print(f"| {c} | {vdd:.4f} | {vcm:.4f} | {k} | {n}/{p} | {sm['idd']:.2f} | {sm['q_pc']:.3f} / {sm['pc']:.3f} | "
                  f"{sm['q_nc']:.3f} / {sm['nc']:.3f} | {sm['pp']:.3f} | {sm['np']:.3f} | {sm['tail']:.3f} | "
                  f"{sm['boost']:.3f} |", flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
