#!/usr/bin/env python3
"""Electrode-offset cancellation (tracker B7, documentation/gf180_electrode_dc_20261022.md):
chopped transient of the written eeg_afe (gf180/tapeout/afe/eeg_afe.spice, with the
offset DAC and the switched-capacitor DC path) for an electrode DC offset.

Both choppers run at 128 kHz (clocks of afe_chop_gain.py, ideal drive through 10 ohm);
the output chopper is blanked for 7 MCLK after each edge and the outputs are held on
30 pF. INP/INN are reset until 10 us. The bias is the ideal set of the netlist check
(make_afe_netlist.py --check). The DAC phase OFPH rises when the phase-A input TG closes
and falls when the phase-B TG closes. The DAC code (sign-magnitude) is chosen for the
applied offset: magnitude = round(abs(offset) / 0.311 mV), limited by the range.

Printed per case: the demodulated output averaged over 100-200 us (input-referred with
the chopped gain 277), its peak-to-peak outside the blanking windows, and the largest
amplifier output swing |OPI - ONI| (saturation check).

With --clkdrv the clocks come from the AFE clock drivers (gf180/tapeout/afe/eeg_afe_clk.spice,
tracker B8) fed with the RTL-like CHOP, CHOP_OUT = CHOP and CHOP_BLANK (1 MCLK before to
--blank MCLK after each edge); otherwise ideal PWL phases with a 5 ns dead time.
With --sine A (mV) a sine of fch/64 rides on the offset; the output is integrated over
every chopper period and HD2..HD5 come from an FFT over 4 signal periods after 0.5 ms
(the method of afe_chop_distortion.py).

Usage: python3 afe_offset.py [--cases 0:0 0:4 300:4 m300:4 ...] [--rs 100] [--blank 7]
       [--sine 0.943]
       case = offset_mV:range[:magnitude]  (m for minus; range 0 = DAC off, 1..4 =
       +-39/79/159/318 mV)
"""
import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import afe_noise
import afe_chop_gain

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
AFE = os.path.join(REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
CLK = os.path.join(REPO, "gf180", "tapeout", "afe", "eeg_afe_clk.spice")
FCH = 128e3
TCH = 1 / FCH
BLANK = 7 / 32.768e6
UNIT_MV = 60e-15 * 3.3 / 636e-12 * 1e3   # 0.311 mV of differential electrode offset per magnitude unit
NBITS = {0: 0, 1: 7, 2: 8, 3: 9, 4: 10}
GAIN = 277.0
T_AVG = (100e-6, 200e-6)


def mag_for(vos_mv, rng):
    nb = NBITS[rng]
    return min(int(round(abs(vos_mv) / UNIT_MV)), 2 ** nb - 1) if nb else 0


def deck(vos_mv, rng, mag, rs, tstop, blank, afe=AFE, sine_mv=0.0, clkdrv=False):
    a, b = afe_chop_gain.clocks(TCH)
    ao, bo = afe_chop_gain.clocks(TCH, blank)
    tr = afe_chop_gain.TR
    ph = f"0 3.3 {TCH / 2:.6e} 3.3 {TCH / 2 + tr:.6e} 0 {TCH - tr:.6e} 0 {TCH:.6e} 3.3"
    sign = "VDD" if vos_mv < 0 else "0"
    bits = " ".join("VDD" if (mag >> k) & 1 else "0" for k in range(10))
    ens = " ".join("VDD" if g < rng else "0" for g in range(4))
    if clkdrv:
        mclk = 1 / 32.768e6
        chop = f"PULSE(0 3.3 {TCH / 2:.6e} 0.5n 0.5n {TCH / 2 - 0.5e-9:.6e} {TCH:.6e})"
        bl = f"PULSE(0 3.3 {TCH / 2 - mclk:.6e} 0.5n 0.5n {mclk + blank - 0.5e-9:.6e} {TCH / 2:.6e})"
        clocks = (f".include {CLK}\nVCHOP CHOP_S 0 {chop}\nVBLK BLANK_S 0 {bl}\n"
                  "XCLK CHOP_S CHOP_S BLANK_S VDD 0 CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RSTX VDD 0 eeg_afe_clk")
    else:
        clocks = "\n".join([
            f"VCIA CIA_D 0 PWL({a}) r=0", "ENCIA NCIA_D 0 VDD CIA_D 1",
            f"VCIB CIB_D 0 PWL({b}) r=0", "ENCIB NCIB_D 0 VDD CIB_D 1",
            f"VCDA CDA_D 0 PWL({ao}) r=0", "ENCDA NCDA_D 0 VDD CDA_D 1",
            f"VCDB CDB_D 0 PWL({bo}) r=0", "ENCDB NCDB_D 0 VDD CDB_D 1",
            "RGCIA CIA_D CIA 10", "RGNCIA NCIA_D NCIA 10", "RGCIB CIB_D CIB 10", "RGNCIB NCIB_D NCIB 10",
            "RGCDA CDA_D CDA 10", "RGNCDA NCDA_D NCDA 10", "RGCDB CDB_D CDB 10", "RGNCDB NCDB_D NCDB 10",
            f"VOFPH OFPH_D 0 PWL({ph}) r=0", "RGOFPH OFPH_D OFPH 10"])
    return f"""* eeg_afe electrode-offset check: {vos_mv:+g} mV, range {rng}, magnitude {mag}, RS {rs:g}
.include {afe_noise.PDK}/design.ngspice
.lib {afe_noise.PDK}/sm141064.ngspice typical
.include {afe}
.temp 27
.options sparse reltol=1e-5 vntol=1e-8 abstol=1e-12 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
VBN VBN 0 0.8485
VBCM VBCM 0 0.82
IBLP BLP 0 125u
IBLN VDD BLN 125u
VRST RST_D 0 PWL(0 3.3 10u 3.3 11u 0)
RGRST RST_D RST 10
VSRC SRC 0 DC {vos_mv * 1e-3:.6g}{f' SIN({vos_mv * 1e-3:.6g} {sine_mv * 1e-3:.9e} {FCH / 64:g})' if sine_mv else ''}
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 -0.5
RSP SRC_P ELP {rs:g}
RSN SRC_N ELN {rs:g}
CLOADP OUTP 0 4p
CLOADN OUTN 0 4p
RLOADP OUTP CM 9375
RLOADN OUTN CM 9375
XA ELP ELN OUTP OUTN CM VBN VBCM BLP BLN RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB
+ OFPH {sign} {bits} {ens} VDD 0 eeg_afe
{clocks}
.nodeset v(xa.inp)=1.65 v(xa.inn)=1.65 v(xa.opi)=1.65 v(xa.oni)=1.65 v(outp)=1.65 v(outn)=1.65
.control
set noaskquit
tran 4n {tstop:.6e} 0 4n
let vo = v(outp) - v(outn)
let va = v(xa.opi) - v(xa.oni)
wrdata tr.csv vo va v(cda) v(cdb)
quit
.endc
.end
"""


def run(case, rs, tstop, blank, afe=AFE, sine_mv=0.0, clkdrv=False):
    vos, rng, mag = case
    tag = "" if afe == AFE else "_" + os.path.splitext(os.path.basename(afe))[0]
    tag += f"_sin{sine_mv:g}" if sine_mv else ""
    tag += "_clkdrv" if clkdrv else ""
    d = os.path.join(HERE, "runs", f"offset{tag}_{vos:+g}mV_r{rng}_m{mag}_rs{rs:g}_bl{blank * 32.768e6:.0f}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(vos, rng, mag, rs, tstop, blank, afe, sine_mv, clkdrv))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    t, vo, va, cda, cdb = x[:, 0], x[:, 1], x[:, 3], x[:, 5], x[:, 7]
    if sine_mv:  # one average per chopper period, FFT over 4 signal periods after 0.5 ms
        q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
        edges = 0.5e-3 + TCH * np.arange(64 * 4 + 1)
        per = np.diff(np.interp(edges, t, q)) / TCH
        spec = np.abs(np.fft.rfft(per)) / (len(per) / 2)
        return case, per.mean(), [spec[4 * k] for k in range(1, 6)], np.abs(va[t > 0.5e-3]).max()
    m = (t >= T_AVG[0]) & (t <= T_AVG[1])
    avg = np.trapezoid(vo[m], t[m]) / (t[m][-1] - t[m][0])
    held = m & ((cda > 1.65) | (cdb > 1.65))  # output chopper connected (outside blanking)
    pp = vo[held].max() - vo[held].min()
    return case, avg, pp, np.abs(va[m]).max()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["0:0", "0:4", "300:4", "m300:4"])
    ap.add_argument("--rs", type=float, default=100.0)
    ap.add_argument("--tstop", type=float, default=200e-6)
    ap.add_argument("--blank", type=int, default=7, help="output-chopper blanking in MCLK")
    ap.add_argument("--afe", default=AFE, help="AFE netlist (default: the written eeg_afe.spice)")
    ap.add_argument("--sine", type=float, default=0.0, help="sine amplitude (mV) at fch/64 for distortion")
    ap.add_argument("--clkdrv", action="store_true", help="clocks from eeg_afe_clk (B8) instead of ideal PWL")
    a = ap.parse_args()
    cases = []
    for c in a.cases:
        f = c.split(":")
        vos, rng = float(f[0].replace("m", "-")), int(f[1])
        cases.append((vos, rng, int(f[2]) if len(f) > 2 else mag_for(vos, rng)))
    blank = a.blank / 32.768e6
    if a.sine:
        print(f"RS {a.rs:g} ohm per leg, blanking {a.blank} MCLK, sine {a.sine:g} mV at {FCH / 64 / 1e3:g} kHz")
        print("| offset (mV) | range | magnitude | gain | HD2 (dBc) | HD3 (dBc) | HD4 (dBc) | HD5 (dBc) "
              "| max abs(OPI-ONI) (V) |")
        print("|---|---|---|---|---|---|---|---|---|")
        with ThreadPoolExecutor(len(cases)) as ex:
            for (vos, rng, mag), _avg, h, vamax in ex.map(
                    lambda c: run(c, a.rs, 0.5e-3 + 4 * 64 * TCH, blank, a.afe, a.sine, a.clkdrv), cases):
                print(f"| {vos:+g} | {rng} | {mag} | {h[0] / (a.sine * 1e-3):.1f} | "
                      + " | ".join(f"{20 * np.log10(x / h[0]):.1f}" for x in h[1:]) + f" | {vamax:.2f} |", flush=True)
        return
    print(f"RS {a.rs:g} ohm per leg, blanking {a.blank} MCLK; residual = output average / {GAIN:g}")
    print("| offset (mV) | range | magnitude | cancelled (mV) | output avg (mV) | residual (mV, input) "
          "| output p-p outside blanking (mV) | max abs(OPI-ONI) (V) |")
    print("|---|---|---|---|---|---|---|---|")
    with ThreadPoolExecutor(len(cases)) as ex:
        for (vos, rng, mag), avg, pp, vamax in ex.map(lambda c: run(c, a.rs, a.tstop, blank, a.afe, 0.0, a.clkdrv), cases):
            canc = (1 if vos >= 0 else -1) * mag * UNIT_MV
            print(f"| {vos:+g} | {rng} | {mag} | {canc:+.2f} | {avg * 1e3:+.1f} | "
                  f"{avg / GAIN * 1e3:+.3f} | {pp * 1e3:.1f} | {vamax:.2f} |", flush=True)


if __name__ == "__main__":
    main()
