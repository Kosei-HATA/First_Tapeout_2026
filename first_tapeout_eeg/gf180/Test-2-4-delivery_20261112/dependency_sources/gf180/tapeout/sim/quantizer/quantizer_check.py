#!/usr/bin/env python3
"""Whole-quantizer checks of eeg_quantizer (gf180/tapeout/adc/eeg_quantizer.spice):
ladder, preamp bias, strobe buffer and the 31 comparators together.

  static  slow differential ramp -60 -> +60 mV at the input (CM 1.65 V), one
          strobe per 976.6 ns frame (30.5 ns high, 0.5 ns edges), TH read at
          e2 = strobe + 61 ns. Prints each comparator's threshold against the
          ideal (k - 15) x 3.125 mV, thermometer bubbles, and the supply and
          reference currents. --mc N repeats it with device mismatch (seeds
          1..N) and prints the spread over all comparators.
  timing  8 strobes with the input stepping between codes (CM 1.65 V), each TH
          loaded with 0.3 pF (route to the digital block): CMP_STROBE rise to
          the last TH at 50 %, the charge per frame from AVDD/DVDD, and the
          kickback (largest displaced charge) on INP/INN and VREFP/VREFN.
          --iq sets the bias unit (default: the eeg_bias unit current at the
          corner and temperature, see qcmp_check.py).

VREFP/VREFN are 1.9/1.4 V, IQ is an ideal 31.25 uA (one bias unit).

Usage: python3 quantizer_check.py static|timing [--corner typical] [--temp 27] [--mc 0]
       [--step 0.2e-3] [--iq 31.25e-6]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from qcmp_check import iq_default

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
QNET = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_quantizer.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
RES = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff", "sf": "res_typical", "fs": "res_typical"}
CAPC = {"ss": "ss", "ff": "ff"}  # MIM corner (the VBQ decoupling cap)
T = 1 / 1.024e6
TM = T / 32          # MCLK period; the strobe and e2 fall on this grid
T0 = 4 * TM          # first strobe
THR = (np.arange(31) - 15) * 3.125e-3
TH = " ".join(f"TH{k}" for k in range(31))


def deck(corner, temp, seed, v0, v1, n):
    tstop = T0 + n * T
    mm = f".param sw_stat_mismatch=1\n.options seed={seed}\n" if seed else ""
    return f"""* eeg_quantizer static check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.lib {PDK}/sm141064.ngspice {RES[corner]}
.lib {PDK}/sm141064.ngspice mimcap_{CAPC.get(corner, 'typical')}
.lib {PDK}/sm141064.ngspice cap_mim
{mm}.include {QNET}
.temp {temp}
.options sparse reltol=1e-4 abstol=1e-12 vntol=1e-7
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
VRP VREFP 0 1.9
VRN VREFN 0 1.4
IQ AVDD IQ {iq_default(corner, temp)}
VSTB CMP_STROBE 0 PULSE(0 3.3 {T0:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})
BIN VD 0 V={v0}+({v1 - v0})*time/{tstop:.10e}
EINP INP 0 VALUE={{1.65+V(VD)/2}}
EINN INN 0 VALUE={{1.65-V(VD)/2}}
XQ INP INN VREFP VREFN CMP_STROBE {TH} IQ AVDD 0 DVDD 0 eeg_quantizer
.control
tran {TM:.10e} {tstop:.10e} 0 2n
meas tran iavdd avg i(vavdd) from={T0:.10e} to={tstop:.10e}
meas tran idvdd avg i(vdvdd) from={T0:.10e} to={tstop:.10e}
meas tran irefp avg i(vrp) from={T0:.10e} to={tstop:.10e}
linearize v(vd) {" ".join(f"v(th{k})" for k in range(31))}
wrdata out.csv v(vd) {" ".join(f"v(th{k})" for k in range(31))}
quit
.endc
.end
"""


def run(name, text):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(text)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    if re.search(r"stepping failed|Timestep too small|aborted", log):
        raise RuntimeError(f"{name}: simulation failed (see {d}/run.log)")
    return d, {k: float(v) for k, v in re.findall(r"^(\S+)\s+=\s+([-0-9.e+]+)", log, re.M)}


def thresholds(d, n):
    """Transition point of each comparator (V), and the number of frames with a
    thermometer bubble (a 1 above a 0)."""
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t, vd = x[:, 0], x[:, 1]
    th = x[:, 3::2] > 1.65
    ts = T0 + np.arange(n) * T
    idx = np.searchsorted(t, ts + 2 * TM - 1e-12)  # sample at e2 (on the linearized grid)
    dec, vin = th[idx], np.interp(ts, t, vd)
    out = np.full(31, np.nan)
    for k in range(31):
        on = np.flatnonzero(dec[:, k])
        if on.size and on[0] > 0 and dec[on[0]:, k].all():
            out[k] = 0.5 * (vin[on[0] - 1] + vin[on[0]])
    bubbles = int(np.sum(np.any(dec[:, 1:] & ~dec[:, :-1], axis=1)))
    return out, bubbles


def static(a):
    v0, v1 = -60e-3, 60e-3
    n = int(round((v1 - v0) / a.step))
    seeds = list(range(1, a.mc + 1)) or [0]

    def one(s):
        d, v = run(f"static_{a.corner}_{a.temp}_s{s}", deck(a.corner, a.temp, s, v0, v1, n))
        thr, bub = thresholds(d, n)
        return thr - THR, bub, v

    with ThreadPoolExecutor(min(8, len(seeds))) as ex:
        res = list(ex.map(one, seeds))
    err, bub, v = res[0]
    print(f"{a.corner} {a.temp} C: AVDD {-v['iavdd']*1e6:.0f} uA, DVDD {-v['idvdd']*1e6:.1f} uA (average), "
          f"VREFP {-v['irefp']*1e6:.2f} uA; ramp step {a.step*1e6:.0f} uV")
    if not a.mc:
        print("| k | ideal (mV) | error (mV) |")
        print("|---|---|---|")
        for k in range(31):
            print(f"| {k} | {THR[k]*1e3:+.3f} | {err[k]*1e3:+.3f} |")
        print(f"frames with a thermometer bubble: {bub}; mean error {np.nanmean(err)*1e3:+.3f} mV, "
              f"rms {np.sqrt(np.nanmean(err**2))*1e3:.3f} mV")
    else:
        e = np.concatenate([r[0] for r in res])
        print(f"{len(seeds)} mismatch samples x 31 comparators: error mean {np.nanmean(e)*1e3:+.3f} mV, "
              f"sigma {np.nanstd(e)*1e3:.3f} mV, max abs {np.nanmax(np.abs(e))*1e3:.3f} mV, "
              f"not monotonic {int(np.isnan(e).sum())}; frames with bubbles per sample "
              f"{[r[1] for r in res]}")


def timing(a):
    n = 8
    levels = [1.6e-3, -1.6e-3, 20e-3, -45e-3, 0.05e-3, 47e-3, -0.05e-3, 3.1e-3]
    pwl = []
    for k, v in enumerate(levels):
        ts = T0 + k * T
        pwl += [(max(ts - T / 2, 0.0), v), (ts + T / 2 - 1e-9, v)]
    src = " ".join(f"{x:.10e} {y:.6e}" for x, y in pwl)
    tstop = T0 + n * T
    loads = "\n".join(f"CTH{k} TH{k} 0 0.3p" for k in range(31))
    text = f"""* eeg_quantizer timing check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {a.corner}
.lib {PDK}/sm141064.ngspice {RES[a.corner]}
.lib {PDK}/sm141064.ngspice mimcap_{CAPC.get(a.corner, 'typical')}
.lib {PDK}/sm141064.ngspice cap_mim
.include {QNET}
.temp {a.temp}
.options sparse reltol=1e-4 abstol=1e-12 vntol=1e-7
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
VRP VREFP 0 1.9
VRN VREFN 0 1.4
IQ AVDD IQ {a.iq}
VSTB CMP_STROBE 0 PULSE(0 3.3 {T0:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {T:.10e})
VD VD 0 PWL({src})
EINP INPS 0 VALUE={{1.65+V(VD)/2}}
EINN INNS 0 VALUE={{1.65-V(VD)/2}}
VMP INPS INP 0
VMN INNS INN 0
XQ INP INN VREFP VREFN CMP_STROBE {TH} IQ AVDD 0 DVDD 0 eeg_quantizer
{loads}
.control
tran 0.02n {tstop:.10e} 0 0.5n
wrdata out.csv v(cmp_strobe) i(vavdd) i(vdvdd) i(vmp) i(vmn) i(vrp) i(vrn) {" ".join(f"v(th{k})" for k in range(31))}
quit
.endc
.end
"""
    d, _ = run(f"timing_{a.corner}_{a.temp}_{a.iq*1e6:g}u", text)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    stb, iav, idv, ip, im, irp, irn = (x[:, 2 * i + 1] for i in range(7))
    th = x[:, 15::2]
    print(f"{a.corner} {a.temp} C, IQ {a.iq*1e6:g} uA, TH loads 0.3 pF:")
    for k in range(1, n):
        ts = T0 + k * T
        w = (t > ts - 20e-9) & (t < ts + T - 40e-9)
        tw = t[w]
        t50 = tw[np.flatnonzero(np.diff((stb[w] > 1.65).astype(int)) > 0)[0]]
        last = 0.0
        for j in range(31):
            ch = np.flatnonzero(np.diff((th[w, j] > 1.65).astype(int)) != 0)
            if ch.size:
                last = max(last, tw[ch[-1] + 1] - t50)
        code = int(np.sum(th[w][-1] > 1.65))

        def q(i):
            return -np.trapezoid(i[w], tw) * 1e12

        def peak(i):
            """largest displaced charge (fC) from the strobe to +150 ns, before the
            mid-frame input step; the DC current before the strobe is removed"""
            pre = (t > ts - 60e-9) & (t < ts - 5e-9)
            wk = (t >= ts - 5e-9) & (t <= ts + 150e-9)
            i0 = np.trapezoid(i[pre], t[pre]) / (t[pre][-1] - t[pre][0])
            y, tk = i[wk] - i0, t[wk]
            c = np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(tk))]) * 1e15
            return c[np.argmax(np.abs(c))]
        print(f"  input {levels[k]*1e3:+7.2f} mV -> code {code:2d}: last TH at +{last*1e9:.2f} ns; "
              f"charge per frame AVDD {q(iav):.2f} pC, DVDD {q(idv):.2f} pC; kickback peak "
              f"INP {peak(ip):+.1f} fC, INN {peak(im):+.1f} fC (diff {peak(ip) - peak(im):+.2f}), "
              f"VREFP {peak(irp):+.2f} fC, VREFN {peak(irn):+.2f} fC")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["static", "timing"])
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=int, default=27)
    ap.add_argument("--mc", type=int, default=0)
    ap.add_argument("--step", type=float, default=0.2e-3)
    ap.add_argument("--iq", type=float, default=None)
    a = ap.parse_args()
    if a.iq is None:
        a.iq = iq_default(a.corner, a.temp)
    {"static": static, "timing": timing}[a.mode](a)


if __name__ == "__main__":
    main()
