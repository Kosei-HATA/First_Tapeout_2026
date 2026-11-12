#!/usr/bin/env python3
"""Single-comparator checks of eeg_qcmp (gf180/tapeout/adc/eeg_quantizer.spice).

  op      preamp operating point, gain and bandwidth (ac), input-referred
          noise of the preamp (noise), per corner/temperature
  offset  threshold of one comparator from a slow input ramp across it
          (one decision per 976.6 ns strobe, read at e2 = strobe + 61 ns);
          --mc N repeats it with device mismatch on (seeds 1..N)
  delay   CLK rise -> TH settled, for overdrives +-0.01 .. 10 mV, alternating
          the sign every strobe (memory check)
  kick    charge drawn from INP/INN and RP/RN per strobe (common-mode and
          differential), for a decision of each sign

The comparator under test has RP - RN = THR (default +15.625 mV, comparator
k = 20), CM 1.65 V on all inputs; the bias is the eeg_quantizer arrangement
(IQ sunk from the PMOS diode W8/L2 x8). IQ defaults to the eeg_bias unit
current at that corner and temperature (bias_check.py: 31.4 uA typical, 21 uA
at ss/-20 C, 50 uA at ff/85 C).

Usage: python3 qcmp_check.py op|offset|delay|kick [--corner typical] [--temp 27]
       [--mc 0] [--thr 15.625e-3] [--iq <eeg_bias unit>] [--cm 1.65]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
QNET = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_quantizer.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
RES = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff", "sf": "res_typical", "fs": "res_typical"}
CAPC = {"ss": "ss", "ff": "ff"}  # MIM corner (the VBQ decoupling cap)
T = 1 / 1.024e6
TMCLK = T / 32
T0 = 100e-9  # first strobe
# eeg_bias unit current (bias_check.py op): by corner at 27 C, and the temperature factor
IQ27 = {"typical": 31.40e-6, "ss": 25.49e-6, "ff": 40.54e-6, "sf": 31.55e-6, "fs": 31.27e-6}
IQT = {-20: 25.66 / 31.40, 27: 1.0, 85: 38.88 / 31.40}


def iq_default(corner, temp):
    return IQ27[corner] * IQT[temp]


def header(corner, temp, seed=0, iq=31.25e-6):
    mm = f".param sw_stat_mismatch=1\n.options seed={seed}\n" if seed else ""
    return f"""* eeg_qcmp check
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
IQ VBQ 0 {iq}
XQP VBQ VBQ AVDD AVDD pfet_03v3 W=8u L=2u nf=1 m=8
CVBQ VBQ 0 2p
VRP RP 0 {{1.65+THR/2}}
VRN RN 0 {{1.65-THR/2}}
"""


def clock(n):
    return f"VCLK CLK 0 PULSE(0 3.3 {T0} 0.2n 0.2n {TMCLK - 0.2e-9:.6e} {T:.10e})\n"


def run(name, text):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(text)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    if re.search(r"stepping failed|Timestep too small|aborted", log):
        raise RuntimeError(f"{name}: simulation failed (see {d}/run.log)")
    return d, log


def vals(log):
    return {k: float(v) for k, v in re.findall(r"^(\S+)\s+=\s+([-0-9.e+]+)", log, re.M)}


def op(a):
    text = header(a.corner, a.temp, 0, a.iq) + f""".param THR={a.thr}
VCLK CLK 0 0
VINP INP 0 DC {{1.65+THR/2}} AC 0.5
VINN INN 0 DC {{1.65-THR/2}} AC -0.5
XC INP INN RP RN CLK TH VBQ AVDD 0 DVDD 0 eeg_qcmp
.control
op
print v(vbq) v(xc.vop) v(xc.von) v(xc.sa) @m.xc.xta.m0[id] @m.xc.xa1.m0[gm] @m.xc.xa1.m0[cgg] i(vavdd)
ac dec 20 1k 1g
let g = vdb(xc.vop, xc.von)
meas ac gdc find g at=1k
let g3 = gdc - 3
meas ac f3db when g=g3
noise v(xc.vop, xc.von) vinp dec 20 1k 1g 1
setplot noise2
print inoise_total onoise_total
quit
.endc
.end
"""
    d, log = run(f"op_{a.corner}_{a.temp}", text)
    v = vals(log)
    gdc = 10 ** (v["gdc"] / 20)
    print(f"{a.corner} {a.temp} C: VBQ {v['v(vbq)']:.3f} V, preamp out {v['v(xc.vop)']:.3f}/{v['v(xc.von)']:.3f} V, "
          f"tail {v['@m.xc.xta.m0[id]']*1e6:.2f} uA, gm {v['@m.xc.xa1.m0[gm]']*1e6:.1f} uS, "
          f"Cgg {v['@m.xc.xa1.m0[cgg]']*1e15:.1f} fF, gain {gdc:.2f}, f3dB {v['f3db']/1e6:.1f} MHz, "
          f"preamp output noise / gain {v['onoise_total'] / gdc * 1e6:.0f} uVrms")


def ramp_deck(a, seed, v0, v1, n):
    tstop = T0 + n * T
    return header(a.corner, a.temp, seed, a.iq) + f""".param THR={a.thr}
{clock(n)}BIN VD 0 V={v0}+({v1 - v0})*time/{tstop}
EINP INP 0 VALUE={{{a.cm}+V(VD)/2}}
EINN INN 0 VALUE={{{a.cm}-V(VD)/2}}
XC INP INN RP RN CLK TH VBQ AVDD 0 DVDD 0 eeg_qcmp
.control
tran 0.2n {tstop} 0 2n
wrdata out.csv v(vd) v(th)
quit
.endc
.end
"""


def threshold(d, n):
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t, vd, th = x[:, 0], x[:, 1], x[:, 3]
    ts = T0 + np.arange(n) * T
    dec = np.interp(ts + 2 * TMCLK, t, th) > 1.65
    vin = np.interp(ts, t, vd)
    k = np.flatnonzero(dec)
    if k.size == 0 or k[0] == 0 or not dec[k[0]:].all():
        return float("nan")
    return 0.5 * (vin[k[0] - 1] + vin[k[0]])


def offset(a):
    span, n = (12e-3, 241) if a.mc else (2e-3, 201)
    v0, v1 = a.thr - span, a.thr + span
    seeds = list(range(1, a.mc + 1)) or [0]

    def one(s):
        d, _ = run(f"offset_{a.corner}_{a.temp}_{a.thr*1e3:g}mV_cm{a.cm:g}_s{s}", ramp_deck(a, s, v0, v1, n))
        return threshold(d, n) - a.thr

    with ThreadPoolExecutor(8) as ex:
        off = np.array(list(ex.map(one, seeds)))
    if a.mc:
        ok = off[np.isfinite(off)]
        print(f"{a.corner} {a.temp} C, threshold {a.thr*1e3:g} mV, {len(seeds)} mismatch samples "
              f"({ok.size} monotonic): mean {ok.mean()*1e3:.3f} mV, sigma {ok.std(ddof=1)*1e3:.3f} mV, "
              f"max abs {np.abs(ok).max()*1e3:.3f} mV")
    else:
        print(f"{a.corner} {a.temp} C, threshold {a.thr*1e3:g} mV, input CM {a.cm:g} V: systematic offset {off[0]*1e6:.1f} uV "
              f"(ramp step {(v1 - v0) / n * 1e6:.1f} uV)")


def delay(a):
    ods = [10e-3, 1e-3, 0.1e-3, 0.01e-3]
    n = 2 * len(ods)
    pts, tt = [], 0.0
    for k in range(n):  # +od, -od, then the next overdrive; changes mid-frame
        od = ods[k // 2] * (1 if k % 2 == 0 else -1)
        t1 = T0 + (k - 0.5) * T if k else 0.0
        pts += [(t1, od), (t1 + 1e-9, od)]
    # PWL: hold each overdrive for one frame, switching half a frame before the strobe
    pwl = []
    for k in range(n):
        od = ods[k // 2] * (1 if k % 2 == 0 else -1)
        ts = T0 + k * T
        pwl += [(max(ts - T / 2, 0.0), od), (ts + T / 2 - 1e-9, od)]
    src = " ".join(f"{t:.10e} {v + a.thr:.8e}" for t, v in pwl)
    text = header(a.corner, a.temp, 0, a.iq) + f""".param THR={a.thr}
{clock(n)}VD VD 0 PWL({src})
EINP INP 0 VALUE={{1.65+V(VD)/2}}
EINN INN 0 VALUE={{1.65-V(VD)/2}}
XC INP INN RP RN CLK TH VBQ AVDD 0 DVDD 0 eeg_qcmp
.control
tran 0.02n {T0 + n * T} 0 0.2n
wrdata out.csv v(clk) v(th) v(xc.oa) v(xc.ob)
quit
.endc
.end
"""
    d, _ = run(f"delay_{a.corner}_{a.temp}", text)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t, th = x[:, 0], x[:, 3]
    print(f"{a.corner} {a.temp} C: CLK rise -> TH at 50 % (ns); TH is read at e2 = +61 ns")
    for k in range(n):
        od = ods[k // 2] * (1 if k % 2 == 0 else -1)
        ts = T0 + k * T + 0.1e-9
        w = (t > ts) & (t < ts + T - 50e-9)
        want = od > 0
        final = th[w][-1] > 1.65
        cross = np.flatnonzero(np.diff((th[w] > 1.65).astype(int)) != 0)
        tdec = t[w][cross[-1] + 1] - ts if cross.size else float("nan")
        state = "ok" if final == want else "WRONG"
        print(f"  overdrive {od*1e3:+8.3f} mV: TH {int(final)} ({state}), "
              f"{'no change' if not cross.size else f'{tdec*1e9:.2f} ns'}")


def kick(a):
    n = 4
    pwl = []
    for k in range(n):
        od = 5e-3 * (1 if k % 2 == 0 else -1)
        ts = T0 + k * T
        pwl += [(max(ts - T / 2, 0.0), od + a.thr), (ts + T / 2 - 1e-9, od + a.thr)]
    src = " ".join(f"{t:.10e} {v:.8e}" for t, v in pwl)
    text = header(a.corner, a.temp, 0, a.iq) + f""".param THR={a.thr}
{clock(n)}VD VD 0 PWL({src})
EINP INPS 0 VALUE={{1.65+V(VD)/2}}
EINN INNS 0 VALUE={{1.65-V(VD)/2}}
VMP INPS INP 0
VMN INNS INN 0
VMRP RP RPI 0
VMRN RN RNI 0
XC INP INN RPI RNI CLK TH VBQ AVDD 0 DVDD 0 eeg_qcmp
.control
tran 0.02n {T0 + n * T} 0 0.2n
wrdata out.csv i(vmp) i(vmn) i(vmrp) i(vmrn)
quit
.endc
.end
"""
    d, _ = run(f"kick_{a.corner}_{a.temp}", text)
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    ip, im, irp, irn = x[:, 1], x[:, 3], x[:, 5], x[:, 7]
    print(f"{a.corner} {a.temp} C: charge drawn from the input sources after the strobe (fC); "
          f"the inputs are ideal sources, so the charge flows back as the latch recovers")
    for k in range(1, n):
        ts = T0 + k * T - 5e-9
        w = (t >= ts) & (t <= ts + 200e-9)

        def q(i):
            """running charge (fC): value at the largest excursion, and at the end"""
            c = np.concatenate([[0.0], np.cumsum(0.5 * (i[w][1:] + i[w][:-1]) * np.diff(t[w]))]) * 1e15
            return c[np.argmax(np.abs(c))], c[-1]
        (pp, pe), (mp, me), (rpp, rpe), (rnp, rne) = q(ip), q(im), q(irp), q(irn)
        print(f"  decision {'1' if k % 2 == 0 else '0'}: peak INP {pp:+.2f}, INN {mp:+.2f} "
              f"(diff {pp - mp:+.2f}); peak RP {rpp:+.2f}, RN {rnp:+.2f} (diff {rpp - rnp:+.2f}); "
              f"left after 200 ns: INP-INN {pe - me:+.3f}, RP-RN {rpe - rne:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["op", "offset", "delay", "kick"])
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=int, default=27)
    ap.add_argument("--mc", type=int, default=0)
    ap.add_argument("--thr", type=float, default=15.625e-3)
    ap.add_argument("--iq", type=float, default=None, help="bias unit (default: eeg_bias at the corner)")
    ap.add_argument("--cm", type=float, default=1.65, help="input (O2) common mode; the ladder stays at 1.65 V")
    a = ap.parse_args()
    if a.iq is None:
        a.iq = iq_default(a.corner, a.temp)
    {"op": op, "offset": offset, "delay": delay, "kick": kick}[a.mode](a)


if __name__ == "__main__":
    main()
