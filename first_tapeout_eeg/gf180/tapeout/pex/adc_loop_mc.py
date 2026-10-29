#!/usr/bin/env python3
"""ADC loop with manufacturing variation (tracker D7): pex_adc.py's extracted loop (adc_deck.py:
bias generator, reference filter, RTL frame timing, the XSPICE DWA controller, eeg_adc extracted)
under the PDK's statistical models and on the chip's operating point:

  - Monte Carlo (--mc SEED ...): afe_startup.head's statistical sections (global process and
    per-device mismatch, .options seed per run; the resistor and MIM mismatch stand-ins), par = M
    on every multiplied transistor (afe_startup.par_m) of the extracted ADC, eeg_bias and eeg_ref;
  - resistor / MIM corners (--rc R_C ..., e.g. ss_ff: res_ss with mimcap_ff), typical MOS;
  - --typical: typical models, no variation (the reference of both);
  - the chip's operating point (--chip, the default): AVDD at the ADC --avdd (3.245 V, the
    supply the ADC has in e2e_startup.py's power-on run), eeg_bias and eeg_ref extracted, and the
    reference path with the chip wiring's resistance (runs/chipnets/README.md (f): bond pad ->
    eeg_ref 1.27 + 41.1 / 87.1 ohm, eeg_ref -> ADC 200.8 / 187.1 ohm, eeg_ref -> the bias
    block's divider 426.6 / 413.1 ohm); --no-chip keeps adc_deck.py's ideal 3.3 V and 0.2 ohm;
  - the time step set by the clock edges (--tmax 10e-6: no 1 ns limit; e2e_startup.py's comparison
    on the pex deck gave identical codes and at most 30 uV at the strobes, at typical).

Each run is analyzed by tr_window.py (loop gain, DAC1 level, residual, O1 / O2 swings and CM)
and pex_adc.codes (the quantizer's decisions against the ideal thresholds, O2 at the strobes).
Runs go to runs/adc_mc_loop/<name>/ (with EEG_PEX_REV=r7, pex.py: the r7 extraction, runs/adc_mc_loop_r7/).

Usage: python3 adc_loop_mc.py [--typical] [--mc 1 2 ...] [--rc ss_ss ss_ff ff_ss ff_ff ff_typical] [--tstop 100e-6]
       [--fsig 20e3] [--amp 0.28] [--no-chip] [--tmax 10e-6] [--jobs 2]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import afe_startup as S  # noqa: E402  (model libraries, par_m, the extracted bias and reference)
import pex_adc  # noqa: E402  (ADC_LOOP, SCH, PEXDIR, codes)

_REV = os.environ.get("EEG_PEX_REV", "")              # pex.py: the extraction of a changed layout
RUNS = os.path.join(HERE, "runs", "adc_mc_loop" + (f"_{_REV}" if _REV else ""))
TRW = os.path.join(S.P.REPO, "gf180", "tapeout", "sim", "e2e", "tr_window.py")
BIAS_SCH = os.path.join(S.P.REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
REF_SCH = os.path.join(S.P.REPO, "gf180", "tapeout", "adc", "eeg_ref.spice")
PAD_R = 1.2716                                   # pad cell, bond pad -> core edge (pex_chipnets pad)
R_REF_PAD = (41.1, 87.1)                         # core edge -> eeg_ref's inputs (VREFP_PAD, VREFN_PAD)
R_REF_ADC = (200.8, 187.1)                       # eeg_ref -> the ADC's VREFP / VREFN
R_REF_BIAS = (426.6, 413.1)                      # eeg_ref -> the bias block's divider


def header(kind, seed):
    """the model section: Monte Carlo, an R_C corner with typical MOS, or typical"""
    if kind == "mc":
        return S.head("typical", seed, "lin")
    if kind == "rc":
        r, c = seed.split("_")
        P = S.P.PDK
        return (f".include {P}/design.ngspice\n.lib {P}/sm141064.ngspice typical\n.lib {P}/sm141064.ngspice res_{r}\n"
                f".lib {P}/sm141064.ngspice mimcap_{c}\n.lib {P}/sm141064.ngspice cap_mim\n"
                f".lib {P}/sm141064.ngspice diode_typical\n.param moscap_corner=1.0\n.include {S.P.MOSLIN}\n" + S.CAP06)
    return S.head("typical", None, "lin")


def local(d, src, mc):
    """a copy of a netlist in the run folder, with par = M for a Monte Carlo run"""
    dst = os.path.join(d, os.path.basename(src))
    txt = open(src).read()
    open(dst, "w").write(S.par_m(txt) if mc else txt)
    return dst


def build(a, kind, seed):
    name = {"mc": f"mc{seed}", "rc": f"rc_{seed}", "typ": "typical"}[kind] + \
        f"_f{a.fsig / 1e3:g}k_a{a.amp:g}_t{a.tstop * 1e6:g}u" + ("" if a.chip else "_nochip") + \
        ("" if a.tmax == 10e-6 else f"_tmax{a.tmax * 1e9:g}n")
    d = os.path.join(RUNS, name)
    os.makedirs(d, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(pex_adc.ADC_LOOP, "adc_deck.py"), d, "--tstop", f"{a.tstop:g}",
                    "--fsig", f"{a.fsig:g}", "--amp", f"{a.amp:g}"], check=True, cwd=pex_adc.ADC_LOOP,
                   capture_output=True)
    path = os.path.join(d, "circuit.spice")
    txt = open(path).read()
    mc = kind == "mc"
    # models
    i0 = txt.index(".include ")
    i1 = txt.index(f".include {S.P.MOSLIN}\n") + len(f".include {S.P.MOSLIN}\n")
    assert txt[i0:i1].startswith(f".include {S.P.PDK}/design.ngspice")
    txt = txt[:i0] + header(kind, seed) + txt[i1:]
    # the extracted ADC, bias and reference (par = M for Monte Carlo)
    adc = local(d, os.path.join(pex_adc.PEXDIR, "eeg_adc_pex.spice"), mc)
    assert txt.count(f".include {pex_adc.SCH}\n") == 1
    txt = txt.replace(f".include {pex_adc.SCH}\n", f".include {adc}\n")
    bias = local(d, S.BIAS_PEX if a.chip else BIAS_SCH, mc)
    assert txt.count(f".include {BIAS_SCH}\n") == 1
    txt = txt.replace(f".include {BIAS_SCH}\n", f".include {bias}\n")
    ref = local(d, S.REF_PEX if a.chip else REF_SCH, mc)
    assert txt.count(f".include {REF_SCH}\n") == 1
    txt = txt.replace(f".include {REF_SCH}\n", f".include {ref}\n")
    if a.chip:
        txt = txt.replace("VAVDD AVDD 0 3.3\n", f"VAVDD AVDD 0 {a.avdd:g}\n", 1)
        txt = txt.replace("RBP EP PADP 0.2\n", f"RBP EP PADP {0.2 + PAD_R + R_REF_PAD[0]:g}\n", 1)
        txt = txt.replace("RBN EN PADN 0.2\n", f"RBN EN PADN {0.2 + PAD_R + R_REF_PAD[1]:g}\n", 1)
        assert txt.count("XREF PADP PADN VREFP VREFN 0 eeg_ref\n") == 1
        txt = txt.replace("XREF PADP PADN VREFP VREFN 0 eeg_ref\n",
                          "XREF PADP PADN VREFP_R VREFN_R 0 eeg_ref\n"
                          f"RREFADCP VREFP_R VREFP {R_REF_ADC[0]:g}\nRREFADCN VREFN_R VREFN {R_REF_ADC[1]:g}\n"
                          f"RREFBP VREFP_R VREFP_B {R_REF_BIAS[0]:g}\nRREFBN VREFN_R VREFN_B {R_REF_BIAS[1]:g}\n")
        old = "IDP IDN IQ ITST VCM VREFP VREFN IB1 IB0"
        assert txt.count(old) == 1
        txt = txt.replace(old, "IDP IDN IQ ITST VCM VREFP_B VREFN_B IB1 IB0")
    if mc:                                        # par = M on the deck's own multiplied devices too
        txt = S.par_m(txt)
    # the clock edges set the step (--tmax)
    txt, n = re.subn(r"^(tran \S+ \S+ 0) 1e-09$", rf"\g<1> {a.tmax:g}", txt, flags=re.M)
    assert n == 1
    open(path, "w").write(txt)
    json.dump({"kind": kind, "seed": seed, "chip": a.chip, "avdd": a.avdd if a.chip else 3.3, "tstop": a.tstop,
               "fsig": a.fsig, "amp": a.amp}, open(os.path.join(d, "meta.json"), "w"), indent=1)
    return name, d


def run_one(a, kind, seed):
    name, d = build(a, kind, seed)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "circuit.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    dt = time.time() - t
    if not os.path.exists(os.path.join(d, "out.csv")) or "timestep too small" in (r.stdout + r.stderr).lower():
        return name, None, dt
    w = subprocess.run([sys.executable, TRW, d, "--kind", "adc", "--fsig", f"{a.fsig:g}"], capture_output=True,
                       text=True).stdout
    c = pex_adc.codes(d)
    res = {"tr_window": w.strip(), **{k: float(v) for k, v in c.items()}}
    json.dump(res, open(os.path.join(d, "result.json"), "w"), indent=1)
    return name, res, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--typical", action="store_true")
    ap.add_argument("--mc", nargs="+", type=int, default=[])
    ap.add_argument("--rc", nargs="+", default=[], help="resistor_MIM corners with typical MOS, e.g. ss_ff")
    ap.add_argument("--tstop", type=float, default=100e-6)
    ap.add_argument("--fsig", type=float, default=20e3)
    ap.add_argument("--amp", type=float, default=0.28, help="input sine at the ADC (V pk, differential)")
    ap.add_argument("--avdd", type=float, default=3.245, help="AVDD at the ADC on the chip (V)")
    ap.add_argument("--no-chip", dest="chip", action="store_false",
                    help="adc_deck.py's ideal supply and reference path, schematic bias / reference")
    ap.add_argument("--tmax", type=float, default=10e-6, help="the transient's largest step (adc_deck.py's own is 1e-9)")
    ap.add_argument("--jobs", type=int, default=2)
    a = ap.parse_args()
    jobs = ([("typ", None)] if a.typical else []) + [("mc", s) for s in a.mc] + [("rc", c) for c in a.rc]
    with ThreadPoolExecutor(min(a.jobs, len(jobs))) as ex:
        for name, res, dt in ex.map(lambda j: run_one(a, *j), jobs):
            if res is None:
                print(f"{name}: FAILED (see run.log) ({dt:.0f} s)", flush=True)
                continue
            print(f"{name} ({dt:.0f} s): codes agree {res['agree'] * 100:.1f} %, O2 at the strobes "
                  f"{res['o2min'] * 1e3:.1f}..{res['o2max'] * 1e3:.1f} mV\n  " + res["tr_window"].replace("\n", "\n  "),
                  flush=True)


if __name__ == "__main__":
    main()
