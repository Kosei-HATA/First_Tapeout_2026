#!/usr/bin/env python3
"""Power-on at the process corners, AVDD ±5 % and other supply ramps (11/15, figure 37): afe_startup.py's power mode
(the AFE held in reset, choppers idle) on the chip's own wiring, with the bias block's start-up branch saved too
(v(xb.sb), v(xb.g1)); the deck is afe_startup.py's otherwise.

  run     the 20 runs, two at a time at nice 5: corners typical / ss / ff / fs / sf at AVDD 3.135 / 3.3 / 3.465 V
          (1 ms ramp, to 10 ms), supply ramps of 10 µs, 10 ms and 100 ms (typical, 3.3 V), 100 ms at ss 3.135 V and
          sf 3.465 V; runs/startup/power_c1e-08_v<vdd>_<corner>_+0mV_su[_ramp<t>]_chip_<rev>/
  report  per run: the tail bias VBN at the AFE (within 1 % of its final value, final value at code 2), the bias
          block's VBN, G1, the core PMOS's VSG, SB at the end and when it fell (the start-up branch off), the AVDD
          current, VCM, the reference at the ADC, the last millisecond's p-p, the largest |OPI - ONI| (in reset)

Usage: EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/powerup_checks.py run|report
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REV = os.environ.get("EEG_PEX_REV", "")
SU = os.path.join(HERE, "runs", "startup")
EXTRA = " v(xb.sb) v(xb.g1)"


def runs():
    base = ["power", "--cvcm", "10n", "--jobs", "1"]
    chip = f"_chip_{REV}" if REV else "_chip"
    out = []
    for c in ("typical", "ss", "ff", "fs", "sf"):
        for v in ("3.135", "3.3", "3.465"):
            out.append(base + ["--corner", c, "--vdd", v, "--tstop", "0.01", "--tag", f"_su{chip}"])
    for tr, ts, tag in (("1e-5", "0.005", "10us"), ("1e-2", "0.02", "10ms"), ("0.1", "0.12", "100ms")):
        out.append(base + ["--tramp", tr, "--tstop", ts, "--tag", f"_su_ramp{tag}{chip}"])
    for c, v in (("ss", "3.135"), ("sf", "3.465")):
        out.append(base + ["--corner", c, "--vdd", v, "--tramp", "0.1", "--tstop", "0.12", "--tag", f"_su_ramp100ms{chip}"])
    return out


def one_run(args):
    """afe_startup.py's main with the start-up branch's nodes added to its saved vectors (child process)"""
    sys.path.insert(0, HERE)
    import afe_startup as A
    A.SAVE = A.SAVE + EXTRA
    sys.argv = ["afe_startup.py"] + args
    A.main()


def run_all():
    def one(args):
        t = time.time()
        r = subprocess.run(["nice", "-n", "5", sys.executable, os.path.abspath(__file__), "_one"] + args,
                           capture_output=True, text=True)
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        return f"{time.strftime('%m/%d %H:%M:%S')} {' '.join(args[4:])}: {last} [{time.time() - t:.0f} s]"

    todo = runs()
    print(f"{time.strftime('%m/%d %H:%M:%S')} {len(todo)} runs", flush=True)
    with ThreadPoolExecutor(2) as ex:
        for line in ex.map(one, todo):
            print(line, flush=True)


def report():
    import numpy as np
    import pandas as pd

    def settle(t, x, fin, tol):
        bad = np.nonzero(np.abs(x - fin) >= tol)[0]
        return t[0] if not len(bad) else (t[bad[-1] + 1] if bad[-1] + 1 < len(t) else np.nan)

    rows = []
    for n in sorted(os.listdir(SU)):
        if not (n.startswith("power_") and "_su" in n and n.endswith(f"_chip_{REV}" if REV else "_chip")):
            continue
        d = os.path.join(SU, n)
        if not os.path.exists(os.path.join(d, "tr.csv")):
            continue
        m = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c").to_numpy()
        v = {k: x[:, 2 * i + 1] for i, k in enumerate(m["vectors"])}
        t = x[:, 0]
        log = open(os.path.join(d, "run.log"), encoding="utf-8", errors="replace").read()
        vdd_b = v["avdd_bias"] - v["avss_bias"]
        vbn = v["vbn_afe"] - v["avss_afei"]
        sb = v["sb"] - v["avss_bias"]
        end = t >= t[-1] - 1e-3
        fin = vbn[end].mean()
        on = np.nonzero(sb > 0.5 * vdd_b)[0]
        t_off = t[on[-1] + 1] if len(on) and on[-1] + 1 < len(t) else np.nan
        vcm = v["vcm_afe"]
        r = dict(run=n, done=bool(t[-1] >= m["tstop"] * (1 - 1e-6) and "timestep too small" not in log.lower()),
                 corner=m["corner"], vdd=m["vdd"], tramp=m["tramp"], t_vbn_1pct_ms=settle(t, vbn, fin, 0.01 * fin) * 1e3,
                 vbn_afe_mv=fin * 1e3, vbn_bias_mv=(v["vbn_bias"] - v["avss_bias"])[end].mean() * 1e3,
                 g1_mv=(v["g1"] - v["avss_bias"])[end].mean() * 1e3, vsg_mv=(v["avdd_bias"] - v["gp"])[end].mean() * 1e3,
                 sb_end_mv=sb[end].mean() * 1e3, t_sb_off_ms=t_off * 1e3,
                 avdd_at_sb_off=float(np.interp(t_off, t, vdd_b)) if np.isfinite(t_off) else np.nan,
                 iavdd_ma=-v["iavdd"][end].mean() * 1e3, vcm_v=vcm[end].mean(),
                 t_vcm_1mv_ms=settle(t, vcm, vcm[end].mean(), 1e-3) * 1e3,
                 vref_mv=(v["vrefp_adc"] - v["vrefn_adc"])[end].mean() * 1e3, vbn_pp_late_uv=float(np.ptp(vbn[end])) * 1e6,
                 opi_oni_max_mv=float(np.max(np.abs(v["opi"] - v["oni"]))) * 1e3)
        rows.append(r)
        print(f"{r['corner']:7s} {r['vdd']:5.3f} V ramp {r['tramp'] * 1e3:7.3f} ms done {r['done']!s:5s} VBN 1 % at "
              f"{r['t_vbn_1pct_ms']:7.3f} ms, {r['vbn_afe_mv']:7.2f} mV (bias {r['vbn_bias_mv']:7.2f}) G1 {r['g1_mv']:6.1f} "
              f"VSG {r['vsg_mv']:6.1f} | SB end {r['sb_end_mv']:5.2f} mV, off at {r['t_sb_off_ms']:.3f} ms (AVDD "
              f"{r['avdd_at_sb_off']:.2f} V) | {r['iavdd_ma']:5.2f} mA, VCM {r['vcm_v']:.4f} V (1 mV at "
              f"{r['t_vcm_1mv_ms']:.2f} ms), VREF {r['vref_mv']:.2f} mV | late p-p {r['vbn_pp_late_uv']:.1f} uV | "
              f"|OPI-ONI| {r['opi_oni_max_mv']:.2f} mV", flush=True)
    json.dump(rows, open(os.path.join(SU, f"powerup_checks{'_' + REV if REV else ''}.json"), "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["_one"]:
        one_run(sys.argv[2:])
    elif sys.argv[1:2] == ["run"]:
        run_all()
    elif sys.argv[1:2] == ["report"]:
        report()
    else:
        print(__doc__)
