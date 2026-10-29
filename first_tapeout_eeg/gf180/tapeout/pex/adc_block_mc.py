#!/usr/bin/env python3
"""Block-level Monte Carlo of the ADC's critical blocks on the extracted layout (sixth assembly, r6): global
process variation plus per-device mismatch, seeds 1-30 by default, and the typical / ss / ff / fs / sf corners
(no mismatch) at 27 C for reference. The per-seed distributions feed the behavioral loop model; the
transistor-level loop Monte Carlo runs separately (adc_loop_mc.py).

Variant: pex, the extracted devices with every extracted capacitance (pex.py, runs/<block>_c of 10/26; eeg_bias and
eeg_ref from pex_chipnets.py, the mask-identical rebuild of 10/27).

Models (afe_startup.head, imported, not edited): a seed loads the PDK's statistical section (sw_stat_global =
sw_stat_mismatch = 1, .options seed = N: reproducible, and the global draw of a seed is the same in every bench,
since the header and so the order of the global draws are the same: recorded per seed as `globals`), the PDK's
statistical resistor section with a per-instance mismatch stand-in for ppolyf_u / ppolyf_u_1k (3 %·um; the PDK
has none), mimcap_statistical with the MIM mismatch stand-in sim/mim_mm.spice (1.41 %·um; the PDK has none); the
MOS capacitors are the linear stand-ins of sim/moscap_lin.spice (no variation). par = M on every multiplied
instance (par_all: afe_startup.par_m for the transistors, also the resistors and MIM capacitors of the loads): the
mismatch scales with par, not with m. The extractions merge parallel fingers into M > 1 devices (the quantizer's
preamp input pairs W20/L1.25 nf 2 come out as w=10u M=2), so par matters there too. Corners: the PDK's MOS corner
with the matching resistor / MIM / diode corners.

Benches (one ngspice deck per job; at most --jobs (<= 2) at a time; a job with a res.json is skipped):
  quant   eeg_quantizer (pex) with its bias current IQ from eeg_bias (pex, reset codes), VREFP / VREFN ideal
          1.9 / 1.4 V, input CM 1.65 V: a slow differential ramp -60 -> +60 mV with one strobe per frame
          (CMP_STROBE 1 MCLK high), TH read at e2 (quantizer_check.py static). Frame QUANT['nm'] MCLK (the
          loop's frame is 32; 8 was checked against 32, see the report). Per comparator the threshold (the
          midpoint of the inputs at its last 0 and first 1), its error against (k - 15) x 3.125 mV, DNL, INL
          against the best-fit line, non-monotonic comparators, strobes with a thermometer bubble.
  dac1    adc_rdac (pex: RIN and DAC1), outputs at ideal virtual grounds (VCM), references VCM +- 0.25 V, frame
          timing of dac1_check.py (SEL at e3, DAC_CLK at e4) with a frame of DAC1['nm'] MCLK:
          even    dac1_check.even's measure: the charge error per toggle that does not depend on its direction,
                  from pattern totals of runs with the same frames on but a different number of toggles: a pattern
                  toggling every frame (8 pairs) against a reference that is on once for 8 frames (design p3s:
                  14 toggles of difference in 24 frames; dac1_check's reference toggles every other frame: 32 in 72
                  frames): cell 0 toggling with cells 1-14 on and 15-30 off (one), and all 31 toggling (all; per
                  element: the common part). At typical it gives -0.00137 / -0.00128 fC per toggle against
                  dac1_check's -0.00135 / -0.00125 (r6). Frame 32 MCLK (the loop's): at 8 MCLK the same test gave
                  -0.0030 / +0.0048 fC (the toggles are not independent at 244 ns), so the frame stays at 32.
          static  per-frame charges: all off, element 30 alone (so that every walk frame has one toggle on and one
                  off: the charge per toggle has an odd part of about 1.4 fC that cancels in such a pair), a walking
                  one (each element alone on for one frame: the element charges and their errors for the DWA
                  model), code 15, a code-15 rotation (DWA at code 15: the extra VRP charge per toggle, as
                  dac1_check.ref but within one run), all on, and RIN (INP / INN at VCM +- 50 mV, stepped inside
                  its first frame):
                  the element charge per loop frame u = i_e T (the DAC1 gain), the VRP current, RIN, the
                  input-referred full scale 31 i_e RIN. Also, per cell, the fall of D (in an all-on frame) and of
                  DB (in an all-off frame) after BRK rises: their difference times i_e is the even error that a
                  timing skew between the two switches gives (a per-cell proxy, checked against the one-cell test).
  ota     OTA1 (gf180_inside_cascode_ota, chopper frozen in phase A and in phase B) and OTA2
          (gf180_ct_ota_tel16_cmfb) with the stage loads of viz_data.ota_deck (OTA1: RIN, the DAC1 resistance,
          C1, R21, wiring; OTA2: R21, C2, the quantizer (pex), wiring), biased by eeg_bias (pex, reset codes)
          through eeg_ref (pex). 1e16 H across each integrating capacitor closes the loop at DC (unity feedback):
          the operating point gives the input offset v(IXP) - v(IXN) at the OTA pins and the output CM - VCM.
          AC as viz_data: T by double injection at the summing node / OTA input break, beta by output current
          injection, A = -T / beta: DC gain (1 Hz), unity-gain frequency of A (GBW with the load), T's
          unity-gain frequency, phase and gain margin; one deck runs the op and the three AC sweeps (alter).
          Changed from viz_data: the extracted bias and reference, and RD1, R21 (OTA1) and the input sources
          return to a buffered copy of VCM, so that VCM (the bias block's 50 kohm divider) carries no DC load.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_block_mc.py run [--blocks ota quant dac1]
           [--seeds 1-30] [--corners typical ss ff fs sf] [--jobs 2] [--hold-slot]
       gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_block_mc.py report [--seeds 1-30]
       gf180/tools/venv310/bin/python gf180/tapeout/pex/adc_block_mc.py checkq --seeds 1   (quantizer frame check)
       (several drivers may run at once: a lock in runs/adc_mc/locks keeps their ngspice processes at <= 2)
Output: runs/adc_mc/<block>/<test>_<case>/ (tb.spice, run.log, res.json; waveforms deleted after parsing),
        runs/adc_mc/adc_block_mc.json (per-seed distributions, corners, statistics), runs/adc_mc/summary.md.
"""
import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

if not hasattr(np, "trapezoid"):        # numpy < 2 (gf180/tools/venv310)
    np.trapezoid = np.trapz

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import afe_startup as S  # noqa: E402  (head(): the Monte Carlo model setup; par_m(); not edited)
import viz_data as V  # noqa: E402  (ota_deck(), middlebrook(), margins(), gain_margin(), unity())
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "dac1"))
import dac1_check as DC  # noqa: E402  (frame timing, tolerances)
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "sim", "quantizer"))
import quantizer_check as QC  # noqa: E402  (frame timing, ideal thresholds)

RUNS = os.path.join(HERE, "runs", "adc_mc")
NETS = os.path.join(RUNS, "nets")
PEXR = os.path.join(HERE, "runs")
SRC = {  # the extractions (pex.py; eeg_bias / eeg_ref: pex_chipnets.py, rebuild of 10/27, XOR-identical to r6)
    "eeg_quantizer": os.path.join(PEXR, "eeg_quantizer_c", "eeg_quantizer_pex.spice"),
    "adc_rdac": os.path.join(PEXR, "adc_rdac_c", "adc_rdac_pex.spice"),
    "ota1": os.path.join(PEXR, "gf180_inside_cascode_ota_c", "gf180_inside_cascode_ota_pex.spice"),
    "ota2": os.path.join(PEXR, "gf180_ct_ota_tel16_cmfb_c", "gf180_ct_ota_tel16_cmfb_pex.spice"),
    "eeg_bias": S.BIAS_PEX,
    "eeg_ref": S.REF_PEX,
}
CORNERS = ["typical", "ss", "ff", "fs", "sf"]
VDD = 3.3
# resistor / MIM subcircuits whose mismatch stand-ins (afe_startup.res_mm, sim/mim_mm.spice) scale with par
PAR_MODELS = {"ppolyf_u", "ppolyf_u_1k", "cap_mim_2f0ff", "cap_mim_1f5ff", "cap_mim_1f0ff"}
# global process draws recorded per seed (the PDK's statistical section: agauss(0, 1, 3), times mc_skew = 3 in
# the model equations; mc_rsh_ppolyf_u_1k: agauss(0, 49.754, 3) ohm/sq, times res_mc_skew = 3; mc_c_cox_2p0ff:
# relative, already times cap_mc_skew = 3)
GLOBALS = ["mc_sig_vth", "mc_sig_vthn", "mc_sig_vthp", "mc_toxe", "mc_toxen", "mc_toxep", "mc_xl", "mc_xln",
           "mc_xlp", "mc_xw", "mc_xwn", "mc_xwp", "mc_rdswn", "mc_rdswp", "mc_rsh_ppolyf_u_1k", "mc_c_cox_2p0ff"]
GLOBAL_SIGMA = {g: 1 / 3 for g in GLOBALS} | {"mc_rsh_ppolyf_u_1k": 49.754 / 3, "mc_c_cox_2p0ff": 0.025}
# a hard failure of the run, and the solver warnings that are recorded with a run that finished
FAIL_RX = re.compile(r"timestep too small|simulation\(s\) aborted|analysis aborted|error on line|unknown subckt|"
                     r"too few parameters|could not find (?:a )?(?:valid )?(?:model|subckt)", re.I)
WARN_RX = re.compile(r"^.*(?:singular matrix|gmin stepping failed|source stepping failed|no convergence|"
                     r"timestep too small).*$", re.I | re.M)


# ----------------------------------------------------------------------------------
# netlists, model headers, running
# ----------------------------------------------------------------------------------
def par_all(text):
    """afe_startup.par_m (par = M on the multiplied transistors), and the same for multiplied resistor and
    MIM instances (their mismatch stand-ins draw with the sigma of par units)."""
    text = S.par_m(text)
    out = []
    for ln in text.splitlines(keepends=True):
        t = ln.split()
        if t and t[0][:1] in "Xx" and PAR_MODELS & set(t) and not any(x.lower().startswith("par=") for x in t):
            m = next((x.split("=", 1)[1] for x in t if x.lower().startswith("m=")), "1")
            if m != "1":
                ln = ln.rstrip("\n") + f" par={m}\n"
        out.append(ln)
    return "".join(out)


def net(name):
    """The extraction with par = M (written once into runs/adc_mc/nets, again when the source is newer)."""
    src = SRC[name]
    dst = os.path.join(NETS, f"{name}_pex_par.spice")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        os.makedirs(NETS, exist_ok=True)
        open(dst, "w").write(f"* {os.path.relpath(src, REPO)} with par = M on the multiplied instances "
                             "(adc_block_mc.par_all)\n" + par_all(open(src).read()))
    return dst


def prepare_nets():
    for n in SRC:
        net(n)


def case_name(case):
    kind, v = case
    return f"mc{v}" if kind == "mc" else v


def head(case):
    """Model libraries (afe_startup.head, 27 C): a Monte Carlo seed (global + mismatch, around typical) or a
    corner; the MOS capacitors as linear stand-ins. A Monte Carlo deck also gets the global draws as DC sources
    (GLB<i>)."""
    kind, v = case
    if kind == "mc":
        h = S.head("typical", v, "lin", temp=27.0)
        h += "".join(f"VGLB{i} GLB{i} 0 {{{g}}}\nRGLB{i} GLB{i} 0 1\n" for i, g in enumerate(GLOBALS))
        return h
    return S.head(v, None, "lin", temp=27.0)


def glob_meas(kind):
    if kind != "mc":
        return ""
    if kind == "mc":
        return "".join(f"meas tran glb{i} find v(glb{i}) at=1n\n" for i in range(len(GLOBALS)))


def glob_print(kind):
    if kind != "mc":
        return ""
    return "".join(f"let glb{i} = v(glb{i})\nprint glb{i}\n" for i in range(len(GLOBALS)))


def read_vals(log):
    """name = value lines of ngspice's print / meas output"""
    return {k.lower(): float(v) for k, v in re.findall(r"^\s*(\S+)\s+=\s+([-+0-9.eE]+)(?=\s|$)", log, re.M)}


def globals_of(vals):
    if "glb0" not in vals:
        return None
    return {g: vals.get(f"glb{i}") for i, g in enumerate(GLOBALS)}


SLOTS = int(os.environ.get("ADC_MC_SLOTS", "2"))     # ngspice processes of this script at a time, all drivers
HELD = None                     # a slot held by the whole driver (--hold-slot: short jobs one after another)


def acquire_slot():
    """One of SLOTS lock files (runs/adc_mc/locks): every driver of this script together runs at most SLOTS
    ngspice processes (the machine is shared); the lock goes with the process if it dies."""
    os.makedirs(os.path.join(RUNS, "locks"), exist_ok=True)
    while True:
        for i in range(SLOTS):
            f = open(os.path.join(RUNS, "locks", f"slot{i}"), "w")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return f
            except BlockingIOError:
                f.close()
        time.sleep(3)


def run_deck(d, deck, outputs=()):
    """Write tb.spice in d, run ngspice; (log, error or None, seconds). The error names a failure: a non-zero
    exit, a solver failure in the log, or a missing output file."""
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    slot = acquire_slot() if HELD is None else None
    t = time.time()
    try:
        r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    finally:
        if slot is not None:
            fcntl.flock(slot, fcntl.LOCK_UN)
            slot.close()
    dt = time.time() - t
    if slot is not None:
        time.sleep(4)           # a waiting driver (it polls every 3 s) gets the slot before this one's next job
    log = r.stdout + r.stderr
    # keep the log small: the initial-solution node listing and the progress lines are dropped
    keep = [ln for ln in log.splitlines() if not ln.startswith(" Reference value")]
    if len(keep) > 400:
        keep = keep[:150] + [f"... ({len(keep) - 300} lines cut by adc_block_mc.run_deck)"] + keep[-150:]
    open(os.path.join(d, "run.log"), "w").write("\n".join(keep) + "\n")
    err = None
    m = FAIL_RX.search(log)
    if r.returncode:
        err = f"ngspice exit {r.returncode}" + (f": {m.group(0)}" if m else "")
    elif m:
        err = m.group(0)
    else:
        miss = [f for f in outputs if not os.path.exists(os.path.join(d, f))]
        if miss:
            err = f"no {', '.join(miss)}"
    if err:                     # partial waveforms of a failed run are not kept
        for f in outputs:
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
    warn = sorted({w.strip()[:160] for w in WARN_RX.findall(log)})
    if warn:
        open(os.path.join(d, "warnings.txt"), "w").write("\n".join(warn) + "\n")
    return log, err, dt


def job_dir(block, test, case):
    return os.path.join(RUNS, block, f"{test}_{case_name(case)}")


def done(d):
    p = os.path.join(d, "res.json")
    return json.load(open(p)) if os.path.exists(p) else None


def save_res(d, res):
    json.dump(res, open(os.path.join(d, "res.json"), "w"), indent=1)
    return res


# ----------------------------------------------------------------------------------
# quantizer: static thresholds
# ----------------------------------------------------------------------------------
TM = QC.TM                      # MCLK period (1/32.768 MHz)
TH = " ".join(f"TH{k}" for k in range(31))
BIAS_BLOCK = """* eeg_bias (extracted) at its reset codes (AFE_IBIAS 2, booster trims 4 units), as viz_data.BIAS_ADC
VCIB1 IB1 0 3.3
VCIB0 IB0 0 0
VCBP1 BP1 0 0
VCBP0 BP0 0 3.3
VCBN1 BN1 0 0
VCBN0 BN0 0 3.3
VITST ITST 0 1
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQB ITST VCMB VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0
+ AVDD 0 eeg_bias
CVCMPAD VCMB 0 100n
.nodeset v(xb.g1)=0.85 v(xb.gp)=2.2 v(xb.nt)=0.84 v(xb.nc)=0.81 v(xb.nd)=0.8 v(xb.sb)=0 v(xb.s2)=0.05
"""
# frame 8 MCLK: the thresholds of seed 1 (comparators 10-19) agree with the loop's frame of 32 MCLK within the
# ramp's resolution (mean +0.02, rms 0.06, max 0.13 mV at 0.2 mV steps; checkq), at half the time. Ramp step
# 0.4 mV for the seeds, 0.2 mV for the corners (the threshold to +-step / 2).
QUANT = dict(nm=8, v0=-60e-3, v1=60e-3, step=0.4e-3, step_corner=0.2e-3)   # --qframe / --qstep change them


def glob_saves(kind):
    return " ".join(f"v(glb{i})" for i in range(len(GLOBALS))) if kind == "mc" else ""


def quant_deck(case, nm, v0, v1, step):
    n = int(round((v1 - v0) / step))
    tf, t0 = nm * TM, 4 * TM
    tstop = t0 + n * tf
    sv = "v(vd) " + " ".join(f"v(th{k})" for k in range(31))
    return f"""* eeg_quantizer (pex) static thresholds: {case_name(case)}, frame {nm} MCLK, ramp {v0 * 1e3:g} -> {v1 * 1e3:g} mV, {n} strobes
{head(case)}.include {net('eeg_quantizer')}
.include {net('eeg_bias')}
.temp 27
.options klu reltol=1e-4 abstol=1e-12 vntol=1e-7
VAVDD AVDD 0 3.3
VDVDD DVDD 0 3.3
VRP VREFP 0 1.9
VRN VREFN 0 1.4
{BIAS_BLOCK}VMIQ IQB IQ 0
VSTB CMP_STROBE 0 PULSE(0 3.3 {t0:.10e} 0.5n 0.5n {TM - 0.5e-9:.10e} {tf:.10e})
BIN VD 0 V={v0}+({v1 - v0})*time/{tstop:.10e}
EINP INP 0 VALUE={{1.65+V(VD)/2}}
EINN INN 0 VALUE={{1.65-V(VD)/2}}
XQ INP INN VREFP VREFN CMP_STROBE {TH} IQ AVDD 0 DVDD 0 eeg_quantizer
.control
set noaskquit
save {sv} i(vavdd) i(vdvdd) i(vmiq) i(vrp) {glob_saves(case[0])}
tran {TM:.10e} {tstop:.10e} 0 2n
meas tran iavdd avg i(vavdd) from={t0:.10e} to={tstop:.10e}
meas tran idvdd avg i(vdvdd) from={t0:.10e} to={tstop:.10e}
meas tran iq avg i(vmiq) from={t0:.10e} to={tstop:.10e}
meas tran irefp avg i(vrp) from={t0:.10e} to={tstop:.10e}
{glob_meas(case[0])}linearize {sv}
set wr_singlescale
wrdata out.csv {sv}
quit
.endc
.end
"""


def quant_parse(d, nm, v0, v1, step):
    """Each comparator's threshold (V): the midpoint of the inputs at the last strobe with TH = 0 and the first
    with TH = 1 (non-monotonic: the midpoint of its first 1 and its last 0, flagged), and the strobes with a
    thermometer bubble (a comparator at 1 above one at 0)."""
    n = int(round((v1 - v0) / step))
    tf, t0 = nm * TM, 4 * TM
    tstop = t0 + n * tf
    x = np.loadtxt(os.path.join(d, "out.csv"))
    t = x[:, 0]
    th = x[:, 2:] > 1.65
    ts = t0 + np.arange(n) * tf
    dec = th[np.searchsorted(t, ts + 2 * TM - 1e-12)]          # TH at e2 of each strobe
    vin = v0 + (v1 - v0) * ts / tstop                            # the ramp at the strobe
    thr, width = np.full(31, np.nan), np.zeros(31)
    for k in range(31):
        on, off = np.flatnonzero(dec[:, k]), np.flatnonzero(~dec[:, k])
        if not on.size or not off.size:
            continue                                             # no transition in the ramp
        if off[-1] < on[0]:
            thr[k] = 0.5 * (vin[off[-1]] + vin[on[0]])
        else:                                                    # non-monotonic
            thr[k] = 0.5 * (vin[on[0]] + vin[off[-1]])
            width[k] = vin[off[-1]] - vin[on[0]]
    bub = np.any(dec[:, 1:] & ~dec[:, :-1], axis=1)
    os.remove(os.path.join(d, "out.csv"))
    return thr, width, int(bub.sum()), [float(v) for v in vin[bub]]


def quant_cfg(case):
    q = dict(QUANT)
    if case[0] == "corner" and "step_corner" in q:
        q["step"] = q["step_corner"]
    return q


def quant_job(case, force=False, q=None, tag=None):
    """q: quant_cfg(case) or an override (a check of the frame on part of the ramp); tag: its folder"""
    q = q or quant_cfg(case)
    d = job_dir("quant", tag or f"static_f{q['nm']}_s{q['step'] * 1e6:g}u", case)
    if not force and done(d):
        return done(d)
    log, err, dt = run_deck(d, quant_deck(case, q["nm"], q["v0"], q["v1"], q["step"]), ["out.csv"])
    res = dict(block="quant", test="static", case=case_name(case), ok=err is None, error=err, seconds=round(dt),
               frame_mclk=q["nm"], step_v=q["step"])
    if err is None:
        try:
            v = read_vals(log)
            thr, width, nbub, vbub = quant_parse(d, q["nm"], q["v0"], q["v1"], q["step"])
            res |= dict(thr_v=[float(a) for a in thr], err_v=[float(a) for a in thr - QC.THR],
                        nonmono_width_v=[float(a) for a in width], bubble_strobes=nbub, bubble_inputs_v=vbub,
                        iavdd_a=-v.get("iavdd", np.nan), idvdd_a=-v.get("idvdd", np.nan), iq_a=v.get("iq", np.nan),
                        irefp_a=-v.get("irefp", np.nan), globals=globals_of(v))
        except Exception as e:                                   # recorded, not dropped
            res.update(ok=False, error=f"parse: {type(e).__name__}: {e}")
    return save_res(d, res)


# ----------------------------------------------------------------------------------
# DAC1 (adc_rdac: RIN and DAC1)
# ----------------------------------------------------------------------------------
DT0 = DC.T0                      # 2 us before the first frame (dac1_check)
# dac1_check's tolerances, and D: ten times looser than A (checked against A, see the report)
TOLS = dict(DC.TOLS, D="method=gear maxord=2 reltol=1e-4 abstol=1e-12 vntol=1e-6 chgtol=1e-16")
# DAC1 benches at the loop's frame (32 MCLK; an 8-MCLK frame changed the even components, see the report), the even
# test as design p3s with 8 pairs at dac1_check's tolerances (A), the static test at tolerances D (agrees with A
# within 6 ppm on the element charges): the settings of the production runs. --dframe / --npat / --dtmax / --dtol /
# --design / --stol change them.
DAC1 = dict(nm=32, npat=8, tmax="0.5n", tol="A", design="p3s", stol="D")
VCM = DC.VCM


def dac1_wrapper():
    """adc_rdac (pex, par = M) as eeg_dac1m with RIN's ends as ports: the even test ties INP to OUTP and INN to
    OUTN (as pex_benches.dac1_wrapper: RIN carries no current), the static test drives them."""
    path = os.path.join(NETS, "eeg_dac1m.spice")
    sel = " ".join(f"SEL{i}" for i in range(31))
    txt = (f".include {net('adc_rdac')}\n.subckt eeg_dac1m INP INN OUTP OUTN VRP VRN {sel} DAC_CLK VDD VSS\n"
           f"XBLK INP INN OUTP OUTN VRP VRN {sel} DAC_CLK VDD VSS adc_rdac\n.ends eeg_dac1m\n")
    if not os.path.exists(path) or open(path).read() != txt:
        open(path, "w").write(txt)
    return path


def sel_pwl(bits, tf, tr=0.5e-9):
    """dac1_check.sel_pwl for a frame of tf: SEL changes 0.5 ns after e3 of the frame"""
    pts = [(0.0, VDD * bits[0])]
    for k in range(1, len(bits)):
        if bits[k] != bits[k - 1]:
            t = DT0 + k * tf + 3 * TM + 0.5e-9
            pts += [(t, VDD * bits[k - 1]), (t + tr, VDD * bits[k])]
    return " ".join(f"{t:.12e} {v:g}" for t, v in pts)


def dac1_deck(case, title, sels, nf, cfg, static=False, saves="i(vop) i(von) i(vrp)", ctrl="", src_extra="",
              writes=None):
    tf = cfg["nm"] * TM
    dclk = f"PULSE(0 {VDD} {DT0 + 4 * TM:.10e} 0.3n 0.3n {TM - 0.3e-9:.10e} {tf:.10e})"
    srcs = "\n".join(f"VS{i} SEL{i} 0 PWL({sel_pwl(b, tf)})" if len(set(b)) > 1 else f"VS{i} SEL{i} 0 {VDD * b[0]:g}"
                     for i, b in enumerate(sels))
    sel = " ".join(f"SEL{i}" for i in range(31))
    xd = (f"XD INP INN OUTP OUTN VRP VRN {sel} DAC_CLK VDD 0 eeg_dac1m" if static else
          f"XD OUTP OUTN OUTP OUTN VRP VRN {sel} DAC_CLK VDD 0 eeg_dac1m")
    return f"""* adc_rdac (pex) DAC1 {title}: {case_name(case)}, frame {cfg['nm']} MCLK, tmax {cfg['tmax']}, tol {cfg['tol']}
{head(case)}.include {dac1_wrapper()}
.temp 27
.options klu {TOLS[cfg['tol']]}
VDD VDD 0 {VDD}
VRP VRP 0 {VCM + 0.25}
VRN VRN 0 {VCM - 0.25}
VOP OUTP 0 {VCM}
VON OUTN 0 {VCM}
VDCLK DAC_CLK 0 {dclk}
{srcs}
{src_extra}{xd}
.control
set noaskquit
save {saves} {glob_saves(case[0])}
tran 0.05n {DT0 + nf * tf:.9e} 0 {cfg['tmax']}
{glob_meas(case[0])}{ctrl}set wr_singlescale
wrdata tr.csv {writes or saves}
quit
.endc
.end
"""


def even_patterns(npat, design="p2"):
    """dac1_check.even's patterns with npat [0, 1] pairs (32 there): p1 toggles every frame; the reference with the
    same frames on in the integration window toggles every other frame (design p2, dac1_check) or once on and
    once off (p3: one frame off, npat on, the rest off; about twice the toggle difference for the same frames)"""
    lead, tail = [0] * 4, [0] * 4
    p1 = lead + [0, 1] * npat + tail
    if design == "p2":
        pr = lead + [0, 0, 1, 1] * (npat // 2) + tail
    else:                                         # both toggles inside the window, as p1's first one
        pr = lead + [0] + [1] * npat + [0] * (npat - 1) + tail
    tog = lambda p: sum(p[j] != p[j - 1] for j in range(1, len(p)))
    assert sum(p1) == sum(pr) and len(p1) == len(pr)
    return p1, pr, tog(p1) - tog(pr)


def even_job(case, test, cfg=None, force=False, cell=0):
    """The charge into OUTP minus OUTN over the window of dac1_check.even. Design p2 (dac1_check): test one_a /
    one_b (cell 0 with p1 / the reference, cells 1-14 on, 15-30 off), all_a / all_b (all 31 with p1 / the
    reference). Design p3: all_ref (all with the reference), all_tog (all with p1), one_tog (cell 0 with p1, the
    others with the reference)."""
    cfg = cfg or DAC1
    d = job_dir("dac1", even_tag(test, cfg) + (f"_c{cell}" if cell else ""), case)
    if not force and done(d):
        return done(d)
    p1, pr, _ = even_patterns(cfg["npat"], cfg["design"])
    nf = len(p1)
    static = [[1] * nf if i < 15 else [0] * nf for i in range(31)]
    if cfg["design"] == "p2":
        p = p1 if test.endswith("_a") else pr
        sels = [p] + static[1:] if test.startswith("one") else [p] * 31
    elif cfg["design"] == "p3":     # first try: the others follow the reference in one_tog (30 cells flip together)
        sels = {"all_ref": [pr] * 31, "all_tog": [p1] * 31, "one_tog": [p1] + [pr] * 30}[test]
    else:                           # p3s: one cell against the static 15 on / 16 off of dac1_check
        sels = {"all_ref": [pr] * 31, "all_tog": [p1] * 31, "one_ref": [pr] + static[1:],
                "one_tog": [p1] + static[1:]}[test]
    if cell and test.startswith("one"):  # another cell toggles; its place among the 15 on / 16 off taken by cell 0
        sels = list(sels)
        sels[0], sels[cell] = sels[cell], sels[0]
    log, err, dt = run_deck(d, dac1_deck(case, f"even {test}", sels, nf, cfg), ["tr.csv"])
    res = dict(block="dac1", test=f"even_{test}", case=case_name(case), ok=err is None, error=err, seconds=round(dt),
               cfg=cfg)
    if err is None:
        try:
            x = np.loadtxt(os.path.join(d, "tr.csv"))
            os.remove(os.path.join(d, "tr.csv"))
            tf = cfg["nm"] * TM
            t, idiff = x[:, 0], x[:, 1] - x[:, 2]
            a, b = DT0 + 4 * tf + 4 * TM, DT0 + (nf - 2) * tf + 4 * TM
            m = (t >= a) & (t <= b)
            res |= dict(q_c=float(np.trapezoid(idiff[m], t[m])), globals=globals_of(read_vals(log)))
        except Exception as e:
            res.update(ok=False, error=f"parse: {type(e).__name__}: {e}")
    return save_res(d, res)


# static: frame plan of the static test (fast frames; the charges are per frame of the loop, T = 32 MCLK, below)
ST_LEAD, ST_WALK, ST_C15, ST_ROT, ST_ON, ST_OFF, ST_RIN = 4, 31, 3, 9, 3, 3, 3
ST_ROT_WIN = (4, 8)              # rotation frames integrated (steady from its second frame on)
ST_DV = 0.05                     # RIN test: INP / INN at VCM +- 50 mV


def static_plan():
    """SEL bits per frame and the frame indices of each part"""
    rows, part = [], {}

    def add(name, frames):
        part[name] = list(range(len(rows), len(rows) + len(frames)))
        rows.extend(frames)
    # lead: all off, its last frame element 30 alone, so that every walk frame has one toggle on and one off (the
    # charge per toggle has an odd part, about 1.4 fC, that cancels in such a pair; lead[-1] has it once)
    add("lead", [[0] * 31] * (ST_LEAD - 1) + [[1 if i == 30 else 0 for i in range(31)]])
    add("walk", [[1 if i == k else 0 for i in range(31)] for k in range(ST_WALK)])
    add("c15", [[1 if i < 15 else 0 for i in range(31)]] * ST_C15)
    rot, p = [], 0
    for _ in range(ST_ROT):                       # dac1_check.ref: 15 on, the window advancing by 15 per frame
        rot.append([1 if (i - p) % 31 < 15 else 0 for i in range(31)])
        p = (p + 15) % 31
    add("rot", rot)
    add("on", [[1] * 31] * ST_ON)
    add("off", [[0] * 31] * ST_OFF)
    add("rin", [[0] * 31] * ST_RIN)
    sels = [[rows[f][i] for f in range(len(rows))] for i in range(31)]
    return sels, part, rows


def static_cfg():
    return dict(DAC1, tol=DAC1.get("stol", DAC1["tol"]))


def static_job(case, cfg=None, force=False):
    cfg = cfg or static_cfg()
    d = job_dir("dac1", f"static_f{cfg['nm']}_t{cfg['tmax']}_{cfg['tol']}", case)
    if not force and done(d):
        return done(d)
    sels, part, rows = static_plan()
    nf = len(rows)
    tf = cfg["nm"] * TM
    e4 = lambda f: DT0 + f * tf + 4 * TM
    tr = e4(part["rin"][0]) + 2e-9                 # the RIN step: inside the first RIN frame (left out)
    src = (f"VINP INP 0 PWL(0 {VCM} {tr:.10e} {VCM} {tr + 1e-9:.10e} {VCM + ST_DV})\n"
           f"VINN INN 0 PWL(0 {VCM} {tr:.10e} {VCM} {tr + 1e-9:.10e} {VCM - ST_DV})\n")
    # D / DB fall after BRK rises, every cell: D in an all-on frame, DB in an all-off frame (no toggles there):
    # the switch that opens at a 1 -> 0 / 0 -> 1 toggle
    brk = "v(xd.xblk.dac1.brk)"
    fon, foff = part["on"][2], part["off"][2]
    ctrl = ""
    for k in range(31):     # gate falls to VDD / 2 and to 2.5 V (about where the switch, source at VCM, turns off)
        for tag, f, node in (("dd", fon, "d"), ("db", foff, "db")):
            for sfx, lvl in (("", 1.65), ("h", 2.5)):
                ctrl += (f"meas tran {tag}{sfx}{k} trig {brk} val=1.65 td={e4(f) - 1e-9:.10e} rise=1 "
                         f"targ v(xd.xblk.dac1.c{k}.{node}) val={lvl} td={e4(f) - 1e-9:.10e} fall=1\n")
    saves = ("i(vop) i(von) i(vrp) i(vinp) i(vinn) " + brk + " "
             + " ".join(f"v(xd.xblk.dac1.c{k}.d) v(xd.xblk.dac1.c{k}.db)" for k in range(31)))
    log, err, dt = run_deck(d, dac1_deck(case, "static", sels, nf, cfg, static=True, saves=saves, ctrl=ctrl,
                                         src_extra=src, writes="i(vop) i(von) i(vrp) i(vinp) i(vinn)"), ["tr.csv"])
    res = dict(block="dac1", test="static", case=case_name(case), ok=err is None, error=err, seconds=round(dt),
               cfg=cfg)
    if err is None:
        try:
            v = read_vals(log)
            x = np.loadtxt(os.path.join(d, "tr.csv"))
            os.remove(os.path.join(d, "tr.csv"))
            t = x[:, 0]
            idiff, ivrp, iinp, iinn = x[:, 1] - x[:, 2], -x[:, 3], x[:, 4], x[:, 5]
            q = lambda i, f: float(np.trapezoid(i[(t >= e4(f)) & (t <= e4(f + 1))], t[(t >= e4(f)) & (t <= e4(f + 1))]))
            res |= dict(frame_s=tf, part=part, rot_win=ST_ROT_WIN,
                        qdiff_c=[q(idiff, f) for f in range(nf - 1)], qvrp_c=[q(ivrp, f) for f in range(nf - 1)],
                        qinp_c=[q(iinp, f) for f in range(nf - 1)], qinn_c=[q(iinn, f) for f in range(nf - 1)],
                        toggles=[sum(rows[f][i] != rows[f - 1][i] for i in range(31)) if f else 0 for f in range(nf)],
                        d_fall_s=[v.get(f"dd{k}", np.nan) for k in range(31)],
                        db_fall_s=[v.get(f"db{k}", np.nan) for k in range(31)],
                        d_fall_25_s=[v.get(f"ddh{k}", np.nan) for k in range(31)],
                        db_fall_25_s=[v.get(f"dbh{k}", np.nan) for k in range(31)], globals=globals_of(v))
        except Exception as e:
            res.update(ok=False, error=f"parse: {type(e).__name__}: {e}")
    return save_res(d, res)


# ----------------------------------------------------------------------------------
# OTA1 / OTA2 with the integrator loads (viz_data.ota_deck)
# ----------------------------------------------------------------------------------
def ota_deck(case, which, phase):
    """viz_data.ota_deck (pex, the stage loads) with: the Monte Carlo / corner head, the extracted OTA,
    quantizer, eeg_ref and eeg_bias with par = M (viz_data has the schematic bias and reference), par on the
    multiplied resistors of the loads; all probe sources in one deck at AC 0: op, then the three AC runs
    (vz, iz, inj) by `alter` of the AC magnitudes."""
    base = V.ota_deck(which, "pex", phase, "vz")
    lines = base.split("\n")
    body = "\n".join(lines[lines.index(".temp 27"):])
    incs = [net(which)] + ([net("eeg_quantizer")] if which == "ota2" else []) + \
           [os.path.join(V.ADC, "eeg_adc.spice"), net("eeg_ref"), net("eeg_bias")]
    o = "o1" if which == "ota1" else "o2"
    probe = "VZP IXP IAP DC 0 AC 0.5\nVZN IXN IAN DC 0 AC -0.5\n"
    assert body.count(probe) == 1
    body = body.replace(probe, f"VZP IXP IAP DC 0 AC 0\nVZN IXN IAN DC 0 AC 0\nIZP 0 IXP AC 0\nIZN 0 IXN AC 0\n"
                               f"IOP 0 {o.upper()}P AC 0\nION 0 {o.upper()}N AC 0\n")
    body = body[:body.index(".control")]
    # RD1, R21 and the input sources return to a buffered copy of VCM (VCMX): in viz_data they load VCM, the bias
    # block's 50 kohm divider, so that the OTA's output CM pulls VCM (x 6 at DC with OTA1's loads). On the chip
    # RD1 (the DAC1 elements) returns to VREFP / VREFN (midpoint VCM), R21 to the stage-2 summing node, and the
    # inputs come from the AFE outputs (their own CM loop); VCM carries no DC load.
    ret = (("RD1P I1P VCM ", "RD1N I1N VCM ", "XR21P O1P VCM ", "XR21N O1N VCM ", "EP INP VCM ", "EN INN VCM ")
           if which == "ota1" else ("EP S2P VCM ", "EN S2N VCM "))
    for a in ret:
        assert body.count(a) == 1, a
        body = body.replace(a, a.replace(" VCM ", " VCMX "))
    x = "XOTA1 " if which == "ota1" else "XOTA2 "
    body = body.replace(x, "EVCMX VCMX 0 VCM 0 1\n" + x, 1)
    body = par_all(body)
    kind = case[0]

    def ac(tag, on, off):
        s = "".join(f"alter @{x}[acmag]=0\n" for x in off)
        s += f"alter @{on[0]}[acmag]=0.5\nalter @{on[1]}[acmag]=-0.5\n"
        return s + (f"ac dec 40 1 1e9\nlet vo = v({o}p) - v({o}n)\nlet vi = v(ixp) - v(ixn)\n"
                    f"let iz = -(i(vzp) - i(vzn))\n"
                    f"wrdata ac_{tag}.csv real(vo) imag(vo) real(vi) imag(vi) real(iz) imag(iz)\n")
    return f"""* ADC {which} (pex), chopper phase {phase if which == 'ota1' else '-'}: {case_name(case)}; viz_data.ota_deck with all probes
{head(case)}{''.join(f'.include {f}' + chr(10) for f in incs)}{body}.nodeset v(xb.g1)=0.85 v(xb.gp)=2.2 v(xb.nt)=0.84 v(xb.nc)=0.81 v(xb.nd)=0.8 v(xb.sb)=0 v(xb.s2)=0.05
.control
set noaskquit
op
let vos = v(ixp) - v(ixn)
let vod = v({o}p) - v({o}n)
let vocm = (v({o}p) + v({o}n)) / 2 - v(vcm)
let b_vcm = v(vcm)
let b_vbn1 = v(vbn1)
let b_vnc1 = v(vnc1)
let b_vpc1 = v(vpc1)
let b_vbcm1 = v(vbcm1)
let b_iavdd = i(vavdd)
print vos vod vocm b_vcm b_vbn1 b_vnc1 b_vpc1 b_vbcm1 b_iavdd
{glob_print(kind)}{ac('vz', ('vzp', 'vzn'), ())}{ac('iz', ('izp', 'izn'), ('vzp', 'vzn'))}{ac('inj', ('iop', 'ion'), ('izp', 'izn'))}quit
.endc
.end
"""


def ota_job(case, which, phase="A", force=False):
    d = job_dir(which, f"ac_{phase}" if which == "ota1" else "ac", case)
    if not force and done(d):
        return done(d)
    log, err, dt = run_deck(d, ota_deck(case, which, phase), ["ac_vz.csv", "ac_iz.csv", "ac_inj.csv"])
    res = dict(block=which, test=f"ac_{phase}" if which == "ota1" else "ac", case=case_name(case), ok=err is None,
               error=err, seconds=round(dt))
    if err is None:
        try:
            v = read_vals(log)
            f, c = V.read_pairs(os.path.join(d, "ac_vz.csv"), 6)
            v1 = c[2] + 1j * c[3]
            _, c = V.read_pairs(os.path.join(d, "ac_iz.csv"), 6)
            i2 = c[4] + 1j * c[5]
            _, c = V.read_pairs(os.path.join(d, "ac_inj.csv"), 6)
            beta = (c[2] + 1j * c[3]) / (c[0] + 1j * c[1])
            t = V.middlebrook(v1, i2)
            a = -t / beta
            fu, pm = V.margins(f, t)
            f180, gm = V.gain_margin(f, t)
            for tag in ("vz", "iz", "inj"):
                os.remove(os.path.join(d, f"ac_{tag}.csv"))
            np.save(os.path.join(d, "AT.npy"), np.vstack([f, a, t]).astype(np.complex64))   # 360 points, small
            res |= dict(vos_v=v.get("vos"), vod_v=v.get("vod"), vocm_v=v.get("vocm"), vcm_v=v.get("b_vcm"),
                        vbn1_v=v.get("b_vbn1"), vnc1_v=v.get("b_vnc1"), vpc1_v=v.get("b_vpc1"), vbcm1_v=v.get("b_vbcm1"),
                        iavdd_a=-v.get("b_iavdd", np.nan),
                        A_dc_db=float(V.db(a[0])), A_ugf_hz=V.unity(f, a), T_max_db=float(V.db(t).max()), T_ugf_hz=fu,
                        PM_deg=pm, GM_db=gm, f180_hz=f180, globals=globals_of(v))
        except Exception as e:
            res.update(ok=False, error=f"parse: {type(e).__name__}: {e}")
    return save_res(d, res)


# ----------------------------------------------------------------------------------
# jobs
# ----------------------------------------------------------------------------------
EVEN_TESTS = {"p2": ("one_a", "one_b", "all_a", "all_b"), "p3": ("all_ref", "all_tog", "one_tog"),
              "p3s": ("one_ref", "one_tog", "all_ref", "all_tog")}


def jobs_for(case, blocks):
    """(label, callable) for one case, cheap ones first"""
    out = []
    if "ota" in blocks:
        out += [(f"ota1 A {case_name(case)}", lambda c=case: ota_job(c, "ota1", "A")),
                (f"ota1 B {case_name(case)}", lambda c=case: ota_job(c, "ota1", "B")),
                (f"ota2 {case_name(case)}", lambda c=case: ota_job(c, "ota2"))]
    if "quant" in blocks:
        out.append((f"quant {case_name(case)}", lambda c=case: quant_job(c)))
    if "dac1" in blocks or "dac1_static" in blocks:
        out.append((f"dac1 static {case_name(case)}", lambda c=case: static_job(c)))
    if "dac1" in blocks or "dac1_even" in blocks:
        out += [(f"dac1 even {t} {case_name(case)}", lambda c=case, t=t: even_job(c, t))
                for t in EVEN_TESTS[DAC1["design"]]]
    return out


def parse_seeds(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def run_all(cases, blocks, nproc):
    """Every job of every case, at most nproc ngspice processes at a time; a job with a res.json is skipped (a
    failed one too: its res.json records the failure; delete it to retry)."""
    prepare_nets()
    dac1_wrapper()
    todo = [j for c in cases for j in jobs_for(c, blocks)]
    # the cheap OTA jobs of every case first, then the rest case by case
    todo = [j for j in todo if j[0].startswith("ota")] + [j for j in todo if not j[0].startswith("ota")]
    t0 = time.time()

    def one(job):
        label, fn = job
        t = time.time()
        try:
            r = fn()
            st = "ok" if r.get("ok") else f"FAILED: {r.get('error')}"
        except Exception as e:                                   # a parse error: recorded, the rest goes on
            st = f"EXCEPTION: {type(e).__name__}: {e}"
        print(f"[{time.strftime('%H:%M:%S')}] {label}: {st} ({time.time() - t:.0f} s, total {time.time() - t0:.0f} s)",
              flush=True)
        return label, st

    with ThreadPoolExecutor(nproc) as ex:
        res = list(ex.map(one, todo))
    bad = [(l, s) for l, s in res if s != "ok"]
    print(f"{len(res)} jobs, {len(bad)} not ok" + "".join(f"\n  {l}: {s}" for l, s in bad), flush=True)


# ----------------------------------------------------------------------------------
# analysis and report
# ----------------------------------------------------------------------------------
LSB = 3.125e-3                                   # quantizer LSB (VREF / 160)
T_FRAME = DC.T                                   # the loop's frame (1 / 1.024 MHz)


def load_res(block, test, case):
    p = os.path.join(job_dir(block, test, case), "res.json")
    return json.load(open(p)) if os.path.exists(p) else None


def quant_tag(case):
    q = quant_cfg(case)
    return f"static_f{q['nm']}_s{q['step'] * 1e6:g}u"


def even_tag(t, c=None):
    c = c or DAC1
    return f"even_{t}_f{c['nm']}_n{c['npat']}_t{c['tmax']}_{c['tol']}" + ("" if c["design"] == "p2" else f"_{c['design']}")


def static_tag():
    c = static_cfg()
    return f"static_f{c['nm']}_t{c['tmax']}_{c['tol']}"


def quant_metrics(r):
    thr = np.array(r["thr_v"], dtype=float)
    err = thr - QC.THR
    ok = np.isfinite(thr)
    out = dict(err_mv=[float(x) for x in err * 1e3], missing=int((~ok).sum()),
               nonmono=int(np.sum(np.array(r["nonmono_width_v"]) > 0)), bubble_strobes=r["bubble_strobes"])
    if ok.sum() < 3:
        return out
    dnl = np.diff(thr) / LSB - 1                                 # 30 steps, NaN where a threshold is missing
    b, a = np.polyfit(QC.THR[ok], thr[ok], 1)                   # best-fit line thr = a + b ideal
    inl = (thr - (a + b * QC.THR)) / LSB
    out |= dict(mean_mv=float(np.nanmean(err) * 1e3), sd_mv=float(np.nanstd(err, ddof=1) * 1e3),
                max_abs_mv=float(np.nanmax(np.abs(err)) * 1e3), dnl_lsb=[float(x) for x in dnl],
                max_abs_dnl_lsb=float(np.nanmax(np.abs(dnl))), inl_fit_lsb=[float(x) for x in inl],
                max_abs_inl_fit_lsb=float(np.nanmax(np.abs(inl))), max_abs_err_lsb=float(np.nanmax(np.abs(err)) / LSB),
                fit_offset_mv=float(a * 1e3), fit_gain=float(b), iavdd_ua=r["iavdd_a"] * 1e6,
                idvdd_ua=r["idvdd_a"] * 1e6, iq_ua=r["iq_a"] * 1e6,
                reordered=int(np.sum(np.diff(thr) < 0)))
    if ok.all():
        # the transfer the RTL sees: CODE = popcount(TH) (eeg_therm2bin.sv), so code c starts at the c-th
        # smallest threshold; out-of-order comparators only give bubbles
        srt = np.sort(thr)
        pdnl = np.diff(srt) / LSB - 1
        out |= dict(pop_max_abs_err_lsb=float(np.abs(srt - QC.THR).max() / LSB),
                    pop_max_abs_dnl_lsb=float(np.abs(pdnl).max()), pop_min_step_lsb=float(np.diff(srt).min() / LSB),
                    pop_dnl_lsb=[float(x) for x in pdnl])
    return out


def static_metrics(r):
    """per-element charges and errors, DAC1 gain, reference current, RIN, the D / DB timing (see static_job)"""
    part, tf = r["part"], r["frame_s"]
    q = np.array(r["qdiff_c"])
    qv = np.array(r["qvrp_c"])
    k_t = T_FRAME / tf                                         # fast frame -> loop frame
    lead_off = part["lead"][1:-1] if len(part["lead"]) > 3 else part["lead"][1:]   # the all-off lead frames
    q_off = np.mean([q[f] for f in lead_off + part["off"][1:]])
    drift = float(np.mean(q[part["off"][1:]]) - np.mean(q[lead_off]))
    dk = np.array([q[f] - q_off for f in part["walk"]])         # element k alone on: 2 i_e,k tf
    ie = dk / (2 * tf)                                          # i_e,k = I_P,k + |I_N,k|
    u = ie * T_FRAME                                            # element charge per loop frame (one side's swing)
    eps = dk / dk.mean() - 1
    q_on = np.mean(q[part["on"][1:]])
    q15 = np.mean(q[part["c15"][1:]])
    # RIN (the integration windows of the rin frames start after the step)
    rin = [f for f in part["rin"][1:] if f < len(r["qinp_c"])]
    i_p = -np.mean([r["qinp_c"][f] for f in rin]) / tf
    i_n = np.mean([r["qinn_c"][f] for f in rin]) / tf
    r_p, r_n = ST_DV / i_p, ST_DV / i_n
    r_avg = 2 / (1 / r_p + 1 / r_n)
    # reference: VRP current at codes 0 / 15 / 31, extra VRP charge per toggle of the code-15 rotation
    ivrp = lambda fr: float(np.mean([qv[f] for f in fr]) / tf)
    rot = part["rot"]
    a, b = r.get("rot_win", (6, 10))                           # (6, 10): the first static runs (12 rotation frames)
    tog = sum(r["toggles"][f] for f in rot[a:b])                # the toggles at the breaks inside the window
    q_rot = float(np.sum(qv[rot[a:b]]))
    q_st = ivrp(part["c15"][1:]) * (b - a) * tf
    dd, db = np.array(r["d_fall_s"], dtype=float), np.array(r["db_fall_s"], dtype=float)
    return dict(elem_err=[float(x) for x in eps], elem_q_fc=[float(x) for x in u * 1e15],
                u_mean_fc=float(u.mean() * 1e15), ie_mean_ua=float(ie.mean() * 1e6),
                elem_err_sd=float(eps.std(ddof=1)), elem_err_max_abs=float(np.abs(eps).max()),
                linearity_on_minus_sum=float(((q_on - q_off) - dk.sum()) / dk.sum()),
                c15_minus_sum=float(((q15 - q_off) - dk[:15].sum()) / dk.sum()),
                odd_per_toggle_fc=(float((q[part["lead"][-1]] - q[part["walk"][-1]]) * k_t * 1e15)
                                   if len(part["lead"]) > 3 else None),
                off_drift_fc_per_loop_frame=drift * k_t * 1e15,
                rin_p_ohm=float(r_p), rin_n_ohm=float(r_n), vfs_v=float(31 * ie.mean() * r_avg),
                adc_gain_factor=float(31 * ie.mean() * r_avg / (2 * 0.25)),
                ivrp_code0_ua=ivrp(part["off"][1:]) * 1e6, ivrp_code15_ua=ivrp(part["c15"][1:]) * 1e6,
                ivrp_code31_ua=ivrp(part["on"][1:]) * 1e6, ivrp_walk_ua=ivrp(part["walk"]) * 1e6,
                vrp_extra_per_toggle_fc=float((q_rot - q_st) / tog * 1e15),
                d_minus_db_ps=[float(x) for x in (dd - db) * 1e12],
                even_proxy_fc=[float(x) for x in ie.mean() * (dd - db) * 1e15],
                d_minus_db_25_ps=[float(x) for x in (np.array(r.get("d_fall_25_s", [np.nan] * 31), dtype=float)
                                                     - np.array(r.get("db_fall_25_s", [np.nan] * 31), dtype=float)) * 1e12])


# a pair whose run stops (ngspice: timestep too small) is run again, both runs of the pair, with these changes
EVEN_RETRY = [dict(tmax="0.4n")]


def even_metrics(case, cfg=None):
    """one / all from their run pairs; for design p3s a pair with a failed run is taken from the retry settings
    (EVEN_RETRY) when both of its runs are there; the failure stays in `failed`, the retry in `retried`."""
    cfg = cfg or DAC1
    if cfg["design"] == "p3s":
        out, missing, failed, retried = dict(seconds=0), [], {}, {}
        _, _, dtog = even_patterns(cfg["npat"], cfg["design"])
        for name, (tog, ref), n in (("even_one_fc", ("one_tog", "one_ref"), 1),
                                    ("even_all_fc", ("all_tog", "all_ref"), 31)):
            for k, c in enumerate([cfg] + [dict(cfg, **r) for r in EVEN_RETRY]):
                rs = {t: load_res("dac1", even_tag(t, c), case) for t in (tog, ref)}
                if k == 0:
                    missing += [t for t, v in rs.items() if v is None]
                    failed |= {t: v["error"] for t, v in rs.items() if v and not v["ok"]}
                if all(v and v["ok"] for v in rs.values()):
                    out[name] = (rs[tog]["q_c"] - rs[ref]["q_c"]) / (dtog * n) * 1e15
                    out["seconds"] += sum(v["seconds"] for v in rs.values())
                    if k:
                        retried[name] = c["tmax"]
                    break
        if failed:
            out["failed"] = failed
        if retried:
            out["retried"] = retried
        if "even_one_fc" not in out and "even_all_fc" not in out:
            return (dict(failed=failed) if failed else None), missing
        return out, ([] if ("even_one_fc" in out and "even_all_fc" in out) else missing)
    rs = {t: load_res("dac1", even_tag(t, cfg), case) for t in EVEN_TESTS[cfg["design"]]}
    if any(v is None for v in rs.values()):
        return None, [t for t, v in rs.items() if v is None]
    bad = {t: v["error"] for t, v in rs.items() if not v["ok"]}
    if bad:
        return dict(failed=bad), []
    _, _, dtog = even_patterns(cfg["npat"], cfg["design"])
    q = {t: v["q_c"] for t, v in rs.items()}
    if cfg["design"] == "p2":
        one = (q["one_a"] - q["one_b"]) / dtog
        all_ = (q["all_a"] - q["all_b"]) / (dtog * 31)
    else:
        one = (q["one_tog"] - q["all_ref"]) / dtog
        all_ = (q["all_tog"] - q["all_ref"]) / (dtog * 31)
    return dict(even_one_fc=one * 1e15, even_all_fc=all_ * 1e15,
                seconds=sum(v["seconds"] for v in rs.values())), []


OTA_KEYS = ["vos_v", "vocm_v", "A_dc_db", "A_ugf_hz", "T_ugf_hz", "PM_deg", "GM_db", "T_max_db", "vcm_v",
            "vbn1_v", "vnc1_v", "vpc1_v", "vbcm1_v"]


def stats(x):
    x = np.array([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    if not x.size:
        return None
    return dict(n=int(x.size), mean=float(x.mean()), sd=float(x.std(ddof=1)) if x.size > 1 else 0.0,
                min=float(x.min()), max=float(x.max()), max_abs=float(np.abs(x).max()))


def collect(seeds):
    cases = [("corner", c) for c in CORNERS] + [("mc", s) for s in seeds]
    out = dict(quant={}, dac1={}, ota1={}, ota2={}, globals={}, failures=[], missing=[])

    def note(block, test, case, r):
        if r is None:
            out["missing"].append(f"{block} {test} {case_name(case)}")
            return False
        if not r["ok"]:
            out["failures"].append(dict(block=block, test=test, case=case_name(case), error=r["error"]))
            return False
        if r.get("globals") and case[0] == "mc":
            out["globals"][str(case[1])] = r["globals"]
        return True

    for case in cases:
        key = case_name(case)
        r = load_res("quant", quant_tag(case), case)
        if note("quant", quant_tag(case), case, r):
            out["quant"][key] = quant_metrics(r)
        r = load_res("dac1", static_tag(), case)
        d = {}
        if note("dac1", static_tag(), case, r):
            d |= static_metrics(r)
        ev, miss = even_metrics(case)
        out["missing"] += [f"dac1 {even_tag(t)} {key}" for t in miss]
        if ev and "failed" in ev:
            out["failures"] += [dict(block="dac1", test=even_tag(t), case=key, error=e,
                                     retried_with=ev.get("retried")) for t, e in ev["failed"].items()]
        if ev:
            d |= {k: v for k, v in ev.items() if k != "failed"}
        if d:
            out["dac1"][key] = d
        for which, phases in (("ota1", ("A", "B")), ("ota2", (None,))):
            dd = {}
            for ph in phases:
                test = f"ac_{ph}" if ph else "ac"
                r = load_res(which, test, case)
                if note(which, test, case, r):
                    dd[ph or "-"] = {k: r.get(k) for k in OTA_KEYS}
            if which == "ota1" and "A" in dd and "B" in dd:
                a, b = dd["A"]["vos_v"], dd["B"]["vos_v"]
                dd["chopped_vos_v"] = (a - b) / 2            # the part the chopper flips (input pair, loads)
                dd["residual_vos_v"] = (a + b) / 2           # the part it does not (after the commutators)
            if dd:
                out[which][key] = dd
    return out


R6_NOMINAL_EVEN = dict(even_one_fc=-0.00135, even_all_fc=-0.00125)   # runs/dac1_even_r6.log: dac1_check, 72 frames


def validation_summary():
    """The checks behind the settings, from their stored results (typical unless noted)."""
    out = {}
    a = load_res("quant", "check_f8_r14", ("mc", 1))
    b = load_res("quant", "check_f32_r14", ("mc", 1))
    if a and b and a["ok"] and b["ok"]:
        ta, tb = np.array(a["thr_v"], dtype=float), np.array(b["thr_v"], dtype=float)
        m = np.isfinite(ta) & np.isfinite(tb)
        d = (ta - tb)[m] * 1e3
        out["quant_frame_8_vs_32_seed1"] = dict(comparators=[int(k) for k in np.flatnonzero(m)],
                                                mean_mv=float(d.mean()), rms_mv=float(np.sqrt(np.mean(d ** 2))),
                                                max_abs_mv=float(np.abs(d).max()), step_mv=QCHECK["step"] * 1e3,
                                                seconds=[a["seconds"], b["seconds"]])
    ev = {}
    for nm, npat, tol, design in ((32, 32, "A", "dac1_check (r6 log)"), (8, 16, "A", "p2"), (32, 16, "A", "p2"),
                                  (32, 8, "A", "p3"), (32, 8, "A", "p3s"), (32, 8, "D", "p3s")):
        key = f"frame {nm}, {npat} pairs, tol {tol}, {design}"
        if design.startswith("dac1_check"):
            ev[key] = R6_NOMINAL_EVEN
            continue
        r, _ = even_metrics(("corner", "typical"), dict(nm=nm, npat=npat, tmax="0.5n", tol=tol, design=design))
        if r and "failed" not in r:
            ev[key] = r
    out["dac1_even_typical"] = ev
    # the one-cell test of two seeds with dac1_check's reference (p2, 16 pairs) against the production design
    cfg2 = dict(nm=32, npat=16, tmax="0.5n", tol="A", design="p2")
    _, _, dtog2 = even_patterns(16, "p2")
    mcx = {}
    for s_ in (1, 2, 16):
        a_, b_ = (load_res("dac1", even_tag(t, cfg2), ("mc", s_)) for t in ("one_a", "one_b"))
        p3, _ = even_metrics(("mc", s_))
        if a_ and b_ and a_["ok"] and b_["ok"] and p3 and "even_one_fc" in p3:
            mcx[f"mc{s_}"] = dict(p2_16_pairs_fc=(a_["q_c"] - b_["q_c"]) / dtog2 * 1e15, production_fc=p3["even_one_fc"])
    out["dac1_even_one_cell_mc_crosscheck"] = mcx
    st = {}
    for tol in ("A", "D"):
        r = load_res("dac1", f"static_f32_t0.5n_{tol}", ("corner", "typical"))
        if r and r["ok"]:
            m = static_metrics(r)
            st[tol] = {k: m[k] for k in ("elem_err_sd", "u_mean_fc", "vfs_v", "rin_p_ohm", "rin_n_ohm", "ivrp_code0_ua",
                                         "ivrp_code31_ua", "vrp_extra_per_toggle_fc")} | dict(seconds=r["seconds"])
            st[tol]["elem_q_fc"] = m["elem_q_fc"]
            st[tol]["d_minus_db_ps"] = m["d_minus_db_ps"]
    if "A" in st and "D" in st:
        st["D_minus_A"] = dict(
            elem_q_max_abs_fc=float(np.abs(np.array(st["D"]["elem_q_fc"]) - np.array(st["A"]["elem_q_fc"])).max()),
            d_minus_db_max_abs_ps=float(np.abs(np.array(st["D"]["d_minus_db_ps"]) -
                                               np.array(st["A"]["d_minus_db_ps"])).max()))
    out["dac1_static_typical"] = st
    return out


def fmt(x, nd=3):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    if not np.isfinite(x):
        return "nan"
    return f"{x:.{nd}f}"


def summarize(data, seeds):
    """Per quantity: Monte Carlo n, mean, sigma, worst (largest |x| or the min / max that matters) over the seeds,
    and the five corners."""
    mc = [str(s) for s in seeds]
    rows = {}

    def add(block, name, getter, unit, scale=1.0, worst="abs", nd=3, ref=""):
        vals = []
        for s in mc:
            try:
                v = getter(data[block][f"mc{s}"])
            except (KeyError, TypeError, IndexError):
                v = None
            vals.append(None if v is None else v * scale)
        cor = {}
        for c in CORNERS:
            try:
                v = getter(data[block][c])
            except (KeyError, TypeError, IndexError):
                v = None
            cor[c] = None if v is None else v * scale
        st = stats(vals)
        w = None
        if st:
            w = {"abs": st["max_abs"], "min": st["min"], "max": st["max"]}[worst]
        rows.setdefault(block, []).append(dict(name=name, unit=unit, stats=st, worst=w, worst_kind=worst,
                                               corners=cor, ref=ref, nd=nd, per_seed=vals))
    return rows, add


def report(seeds, out_dir=RUNS):
    data = collect(seeds)
    rows, add = summarize(data, seeds)
    # quantizer
    q = lambda k: (lambda d: d.get(k))
    add("quant", "threshold error, mean of 31 (common offset)", q("mean_mv"), "mV", ref="10/22 sch: single comparator only")
    add("quant", "threshold error, sigma of 31 within a seed", q("sd_mv"), "mV", worst="max",
        ref="10/22 sch: sigma 2.12 mV (40 samples, mismatch); model: sigma 10 mV -> 147 dB (target 101.1 dB)")
    add("quant", "threshold error, largest |.| of 31", q("max_abs_mv"), "mV", worst="max", ref="10/22 sch: max 4.47 mV")
    add("quant", "DNL, largest |.| of 30", q("max_abs_dnl_lsb"), "LSB", worst="max")
    add("quant", "INL (best-fit line), largest |.| of 31", q("max_abs_inl_fit_lsb"), "LSB", worst="max")
    add("quant", "gain of the best-fit line", q("fit_gain"), "", worst="abs", nd=4)
    add("quant", "adjacent comparators out of order (of 30)", q("reordered"), "", worst="max", nd=0)
    add("quant", "strobes with a thermometer bubble (of the ramp)", q("bubble_strobes"), "", worst="max", nd=0,
        ref="10/22 sch: none (600 strobes); harmless: CODE = popcount(TH)")
    add("quant", "popcount transfer: largest |threshold error|", q("pop_max_abs_err_lsb"), "LSB", worst="max")
    add("quant", "popcount transfer: largest |DNL|", q("pop_max_abs_dnl_lsb"), "LSB", worst="max")
    add("quant", "popcount transfer: smallest step", q("pop_min_step_lsb"), "LSB", worst="min")
    add("quant", "non-monotonic comparators", q("nonmono"), "", worst="max", nd=0)
    add("quant", "IQ from eeg_bias", q("iq_ua"), "uA", worst="min", nd=2)
    add("quant", "AVDD current (with IQ)", q("iavdd_ua"), "uA", worst="max", nd=1)
    # DAC1
    add("dac1", "even component, one cell (cell 0)", q("even_one_fc"), "fC/toggle", nd=5,
        ref="req 0.008; 10/22 sch MC sigma 0.0062 (8 samples); r6 pex nominal -0.00135")
    add("dac1", "even component, all 31 (common part, per element)", q("even_all_fc"), "fC/toggle", nd=5,
        ref="req 0.016; 10/22 sch MC sigma 0.0007; r6 pex nominal -0.00125")
    add("dac1", "element error, sigma of 31 within a seed", q("elem_err_sd"), "ppm", scale=1e6, worst="max", nd=0,
        ref="resistor mismatch stand-in 3 %·um")
    add("dac1", "element error, largest |.| of 31", q("elem_err_max_abs"), "ppm", scale=1e6, worst="max", nd=0)
    add("dac1", "element charge per frame u = i_e T (DAC1 gain)", q("u_mean_fc"), "fC", worst="abs", nd=2,
        ref="2 Iu T = 0.81 pC nominal")
    add("dac1", "input-referred full scale 31 i_e RIN", q("vfs_v"), "mV", scale=1e3, worst="abs", nd=2,
        ref="31/32 x 0.5 V = 484.4 mV")
    add("dac1", "RIN, P side", q("rin_p_ohm"), "ohm", nd=1)
    add("dac1", "RIN, N side", q("rin_n_ohm"), "ohm", nd=1)
    add("dac1", "VRP current, code 0", q("ivrp_code0_ua"), "uA", nd=4, ref="r6 pex nominal 12.8524")
    add("dac1", "VRP current, code 31", q("ivrp_code31_ua"), "uA", nd=4, ref="r6 pex nominal 12.8512")
    add("dac1", "VRP current code 31 - code 0", lambda d: d["ivrp_code31_ua"] - d["ivrp_code0_ua"], "nA", scale=1e3,
        nd=2)
    add("dac1", "extra VRP charge per toggle (code-15 rotation)", q("vrp_extra_per_toggle_fc"), "fC", nd=4,
        ref="r6 pex nominal +0.053")
    add("dac1", "D - DB fall after BRK, sigma of 31 within a seed", lambda d: float(np.std(d["d_minus_db_ps"], ddof=1)),
        "ps", worst="max", nd=2)
    add("dac1", "D - DB fall after BRK, cell 0", lambda d: d["d_minus_db_ps"][0], "ps", nd=2)
    # OTAs
    for which, phases in (("ota1", ("A", "B")), ("ota2", ("-",))):
        for ph in phases:
            g = lambda k, ph=ph: (lambda d: d[ph][k])
            tag = f" (phase {ph})" if ph != "-" else ""
            add(which, f"input offset{tag}", g("vos_v"), "uV", scale=1e6, nd=1)
            add(which, f"output CM - VCM{tag}", g("vocm_v"), "mV", scale=1e3, nd=3)
            add(which, f"DC gain (loaded){tag}", g("A_dc_db"), "dB", worst="min", nd=2,
                ref="behavioral model A1 2710 (68.7 dB), A2 3000 (69.5 dB)")
            add(which, f"unity-gain frequency of A (GBW, loaded){tag}", g("A_ugf_hz"), "MHz", scale=1e-6, worst="min", nd=2)
            add(which, f"integrator loop: T unity-gain frequency{tag}", g("T_ugf_hz"), "MHz", scale=1e-6, worst="min",
                nd=2)
            add(which, f"integrator loop: phase margin{tag}", g("PM_deg"), "deg", worst="min", nd=2)
            add(which, f"integrator loop: gain margin{tag}", g("GM_db"), "dB", worst="min", nd=2)
        if which == "ota1":
            add(which, "offset the chopper flips (A - B)/2", lambda d: d["chopped_vos_v"], "uV", scale=1e6, nd=1)
            add(which, "offset it does not flip (A + B)/2", lambda d: d["residual_vos_v"], "uV", scale=1e6, nd=1)
        g = lambda k, ph=phases[0]: (lambda d: d[ph][k])
        add(which, "bias VBN1 (eeg_bias)", g("vbn1_v"), "V", worst="abs", nd=4)
        add(which, "VCM (eeg_bias divider)", g("vcm_v"), "V", worst="abs", nd=4)

    # the D / DB timing as a proxy of the per-cell even error: cell 0's timing against its measured one-cell
    # value over the seeds (least squares e = a + b dt); the fit then estimates every cell of a seed
    proxy = {}
    for lvl, key in (("1.65 V", "d_minus_db_ps"), ("2.5 V", "d_minus_db_25_ps")):
        xs, ys = [], []
        for s_ in seeds:
            d = data["dac1"].get(f"mc{s_}", {})
            if key in d and "even_one_fc" in d and np.isfinite(d[key][0]):
                xs.append(d[key][0])
                ys.append(d["even_one_fc"])
        if len(xs) >= 5:
            xs, ys = np.array(xs), np.array(ys)
            b, a = np.polyfit(xs, ys, 1)
            r = float(np.corrcoef(xs, ys)[0, 1])
            res = ys - (a + b * xs)
            proxy[lvl] = dict(key=key, n=len(xs), a_fc=float(a), b_fc_per_ps=float(b), r=r,
                              residual_sd_fc=float(res.std(ddof=2)), measured_sd_fc=float(ys.std(ddof=1)))
    best = max(proxy.values(), key=lambda v: abs(v["r"])) if proxy else None
    if best and abs(best["r"]) < 0.7:     # too weak to estimate the other cells from their timing
        best = None

    # pooled statistics for the behavioral model
    pooled = {}
    qe = np.array([data["quant"][f"mc{s_}"]["err_mv"] for s_ in seeds if f"mc{s_}" in data["quant"]], dtype=float)
    if qe.size:
        means = np.nanmean(qe, axis=1)
        pooled["quant"] = dict(
            n_seeds=int(qe.shape[0]), pooled_sd_mv=float(np.nanstd(qe, ddof=1)), pooled_mean_mv=float(np.nanmean(qe)),
            pooled_max_abs_mv=float(np.nanmax(np.abs(qe))), common_offset_sd_mv=float(np.std(means, ddof=1)),
            within_seed_sd_rms_mv=float(np.sqrt(np.mean(np.nanvar(qe - means[:, None], axis=1, ddof=1)))),
            per_comparator_mean_mv=[float(x) for x in np.nanmean(qe, axis=0)],
            per_comparator_sd_mv=[float(x) for x in np.nanstd(qe, axis=0, ddof=1)],
            frac_beyond_1lsb=float(np.mean(np.abs(qe) > LSB * 1e3)))
    de = np.array([data["dac1"][f"mc{s_}"]["elem_err"] for s_ in seeds
                   if "elem_err" in data["dac1"].get(f"mc{s_}", {})], dtype=float)
    if de.size:
        pooled["dac1_elements"] = dict(
            n_seeds=int(de.shape[0]), pooled_sd_ppm=float(de.std(ddof=1) * 1e6),
            pooled_max_abs_ppm=float(np.abs(de).max() * 1e6),
            per_element_mean_ppm=[float(x) for x in de.mean(axis=0) * 1e6],
            per_element_sd_ppm=[float(x) for x in de.std(axis=0, ddof=1) * 1e6])
    one = np.array([data["dac1"][f"mc{s_}"]["even_one_fc"] for s_ in seeds
                    if "even_one_fc" in data["dac1"].get(f"mc{s_}", {})])
    al = np.array([data["dac1"][f"mc{s_}"]["even_all_fc"] for s_ in seeds
                   if "even_all_fc" in data["dac1"].get(f"mc{s_}", {})])
    if one.size > 1 and al.size > 1:
        sd1, sda = one.std(ddof=1), al.std(ddof=1)
        pooled["dac1_even"] = dict(
            n_seeds=int(one.size), one_mean_fc=float(one.mean()), one_sd_fc=float(sd1), one_max_abs_fc=float(np.abs(one).max()),
            all_mean_fc=float(al.mean()), all_sd_fc=float(sda), all_max_abs_fc=float(np.abs(al).max()),
            per_cell_random_sd_fc=float(np.sqrt(max(sd1 ** 2 - sda ** 2, 0.0))),
            frac_one_beyond_0p008=float(np.mean(np.abs(one) > 0.008)),
            one_relative_to_2IuT=float(sd1 / np.mean([data["dac1"][f"mc{s_}"]["u_mean_fc"] for s_ in seeds
                                                     if "u_mean_fc" in data["dac1"].get(f"mc{s_}", {})])))

    # the JSON for the behavioral model: per-seed distributions
    per_seed = {}
    for s in seeds:
        k = f"mc{s}"
        e = {}
        if k in data["quant"]:
            e["quant_threshold_error_mv"] = data["quant"][k]["err_mv"]
            e["quant_bubble_strobes"] = data["quant"][k]["bubble_strobes"]
        if k in data["dac1"]:
            d = data["dac1"][k]
            e |= {x: d.get(x) for x in ("elem_err", "elem_q_fc", "u_mean_fc", "vfs_v", "rin_p_ohm", "rin_n_ohm",
                                        "even_one_fc", "even_all_fc", "ivrp_code0_ua", "ivrp_code31_ua",
                                        "vrp_extra_per_toggle_fc", "d_minus_db_ps") if x in d}
            if best and best["key"] in d:
                e["even_cell_estimate_fc"] = [best["a_fc"] + best["b_fc_per_ps"] * x for x in d[best["key"]]]
        for which in ("ota1", "ota2"):
            if k in data[which]:
                e[which] = data[which][k]
        e["globals"] = data["globals"].get(str(s))
        per_seed[str(s)] = e
    corners = {c: {b: data[b].get(c) for b in ("quant", "dac1", "ota1", "ota2")} for c in CORNERS}
    meta = dict(
        date=time.strftime("%Y-%m-%d %H:%M"), seeds=seeds, variant="pex (extracted devices and capacitances)",
        extractions={k: dict(path=os.path.relpath(v, REPO), mtime=time.strftime("%Y-%m-%d %H:%M",
                                                                                time.localtime(os.path.getmtime(v))))
                     for k, v in SRC.items()},
        models=("afe_startup.head: PDK statistical section (sw_stat_global = sw_stat_mismatch = 1, .options seed), "
                "res_mm (ppolyf mismatch stand-in 3 %·um, the PDK has none), mimcap_statistical + mim_mm.spice "
                "(MIM mismatch stand-in 1.41 %·um, the PDK has none), MOS capacitors linear (moscap_lin.spice, no "
                "mismatch); par = M on multiplied instances; 27 C; corners: PDK MOS corner with the matching "
                "resistor / MIM corners, no mismatch"),
        quant=QUANT, dac1=DAC1, even_proxy_fit=proxy, even_proxy_used=best,
        units=dict(elem_err="relative (element charge / mean - 1)",
                   even_cell_estimate_fc=("per cell even error (fC/toggle) estimated from its D / DB timing by the fit "
                                          "of cell 0's measured one-cell value over the seeds (even_proxy_used); an "
                                          "estimate, only cell 0 is simulated per seed"),
                                           elem_q_fc="element charge per loop frame i_e T (fC)",
                                           d_minus_db_ps="D fall - DB fall after BRK rise (ps), per cell",
                                           even_proxy_fit=("D - DB timing of cell 0 against its measured one-cell "
                                                           "even error over the seeds; r about 0.2: the timing is not "
                                                           "the mechanism, so no per-cell estimates are given")),
        globals_note=("GLOBALS: raw draws of the PDK statistical section; z = value / GLOBAL_SIGMA "
                      f"{GLOBAL_SIGMA}"),
        failures=data["failures"], missing=data["missing"], validation=validation_summary())
    js = dict(meta=meta, pooled=pooled, per_seed=per_seed, corners=corners,
              summary={b: [{k: v for k, v in r.items() if k != "per_seed"} for r in rr] for b, rr in rows.items()})
    os.makedirs(out_dir, exist_ok=True)
    jp = os.path.join(out_dir, "adc_block_mc.json")
    json.dump(js, open(jp, "w"), indent=1, default=float)
    # markdown
    md = [f"# ADC block Monte Carlo (pex), {meta['date']}", "",
          f"Seeds: {len(seeds)} ({seeds[0]}-{seeds[-1]}); corners at 27 C without mismatch. "
          f"quantizer: frame {QUANT['nm']} MCLK, ramp step {QUANT['step'] * 1e3:g} mV (seeds) / "
          f"{QUANT.get('step_corner', QUANT['step']) * 1e3:g} mV (corners); "
          f"DAC1: frame {DAC1['nm']} MCLK, even test design {DAC1['design']} with {DAC1['npat']} pairs at tolerances "
          f"{DAC1['tol']}, static test at tolerances {DAC1['stol']} (tmax {DAC1['tmax']}). OTAs: frozen chopper phases, "
          "op and AC.", ""]
    names = {"quant": "Quantizer (eeg_quantizer)", "dac1": "DAC1 (adc_rdac)", "ota1": "OTA1 (gf180_inside_cascode_ota)",
             "ota2": "OTA2 (gf180_ct_ota_tel16_cmfb)"}
    for b, rr in rows.items():
        md += [f"## {names[b]}", "", "| quantity | unit | n | MC mean | MC sigma | MC worst | " +
               " | ".join(CORNERS) + " | reference |", "|---" * (7 + len(CORNERS)) + "|"]
        for r in rr:
            st, nd = r["stats"], r["nd"]
            md.append(f"| {r['name']} | {r['unit']} | {st['n'] if st else 0} | {fmt(st and st['mean'], nd)} | "
                      f"{fmt(st and st['sd'], nd)} | {fmt(r['worst'], nd)} | "
                      + " | ".join(fmt(r["corners"][c], nd) for c in CORNERS) + f" | {r['ref']} |")
        md.append("")
    md += ["## Pooled over the seeds (behavioral model inputs)", ""]
    pq, pd, pe = pooled.get("quant"), pooled.get("dac1_elements"), pooled.get("dac1_even")
    if pq:
        pc = np.array(pq["per_comparator_mean_mv"])
        md.append(f"- Quantizer, {pq['n_seeds']} seeds x 31 comparators: threshold error mean {pq['pooled_mean_mv']:+.3f} mV, "
                  f"sigma {pq['pooled_sd_mv']:.3f} mV, largest {pq['pooled_max_abs_mv']:.2f} mV; common offset of a seed "
                  f"sigma {pq['common_offset_sd_mv']:.3f} mV, within a seed sigma (rms) {pq['within_seed_sd_rms_mv']:.3f} mV; "
                  f"per-comparator mean over the seeds within {np.abs(pc).max():.2f} mV; |error| > 1 LSB in "
                  f"{pq['frac_beyond_1lsb'] * 100:.1f} % of the comparators")
    if pd:
        pm = np.array(pd["per_element_mean_ppm"])
        md.append(f"- DAC1 elements, {pd['n_seeds']} seeds x 31: element error sigma {pd['pooled_sd_ppm']:.0f} ppm, largest "
                  f"{pd['pooled_max_abs_ppm']:.0f} ppm; per-element mean over the seeds within {np.abs(pm).max():.0f} ppm")
    if pe:
        md.append(f"- DAC1 even, {pe['n_seeds']} seeds: one cell mean {pe['one_mean_fc']:+.5f}, sigma {pe['one_sd_fc']:.5f}, "
                  f"largest {pe['one_max_abs_fc']:.5f} fC/toggle ({pe['frac_one_beyond_0p008'] * 100:.0f} % beyond 0.008 fC); "
                  f"all 31 mean {pe['all_mean_fc']:+.5f}, sigma {pe['all_sd_fc']:.5f}, largest {pe['all_max_abs_fc']:.5f}; "
                  f"per-cell random part sigma {pe['per_cell_random_sd_fc']:.5f} fC "
                  f"({pe['one_relative_to_2IuT'] * 1e6:.1f} ppm of the element charge)")
    md.append("")
    md += ["## Stand-ins and idealizations", "",
           "- Resistor (ppolyf_u, ppolyf_u_1k) and MIM mismatch: stand-in Pelgrom coefficients 3 %·um and 1.41 %·um "
           "(afe_startup.res_mm, sim/mim_mm.spice); the PDK has no local model for either. The PDK's global "
           "resistor and MIM variation and its MOS global + mismatch models are used as they are.",
           "- MOS capacitors (eeg_bias, eeg_ref): linear stand-ins (sim/moscap_lin.spice), no variation.",
           "- Benches: ideal supplies (3.3 V), 27 C, no noise. Quantizer: ideal VREFP / VREFN at its pins, ideal "
           "differential ramp at CM 1.65 V, IQ from eeg_bias (pex). DAC1: ideal virtual grounds at VCM, ideal "
           "references VCM +- 0.25 V, ideal SEL / DAC_CLK edges. OTAs: chopper frozen (AC of each phase), eeg_bias "
           "and eeg_ref (pex) with ideal pad sources, RD1 an ideal 19.355 kohm (viz_data), RD1 / R21 / the input "
           "sources returned to a buffered VCM.",
           "- Corners have no mismatch; seeds are global + mismatch around typical.", ""]
    val = meta["validation"]
    md += ["## Checks behind the settings (typical unless noted)", ""]
    q_ = val.get("quant_frame_8_vs_32_seed1")
    if q_:
        md.append(f"- Quantizer frame 8 vs 32 MCLK (seed 1, comparators {q_['comparators'][0]}-{q_['comparators'][-1]}, "
                  f"ramp step {q_['step_mv']:g} mV): threshold difference mean {q_['mean_mv']:+.3f} mV, rms "
                  f"{q_['rms_mv']:.3f} mV, max {q_['max_abs_mv']:.3f} mV; run time {q_['seconds'][0]} / {q_['seconds'][1]} s.")
    for k, v in val.get("dac1_even_typical", {}).items():
        md.append(f"- DAC1 even, {k}: one cell {v['even_one_fc']:+.5f}, all 31 {v['even_all_fc']:+.5f} fC/toggle"
                  + (f" ({v['seconds']} s)" if "seconds" in v else ""))
    for k, v in val.get("dac1_even_one_cell_mc_crosscheck", {}).items():
        md.append(f"- DAC1 even, one cell, {k}: dac1_check's reference (p2, 16 pairs) {v['p2_16_pairs_fc']:+.5f}, "
                  f"production (p3s, 8 pairs) {v['production_fc']:+.5f} fC/toggle")
    for lvl, v in proxy.items():
        md.append(f"- DAC1 per-cell even proxy (D - DB fall at {lvl}, cell 0, {v['n']} seeds): e = {v['a_fc']:+.5f} "
                  f"{v['b_fc_per_ps']:+.6f} x dt(ps) fC, r = {v['r']:.3f}, residual sigma {v['residual_sd_fc']:.5f} fC "
                  f"(measured sigma {v['measured_sd_fc']:.5f} fC)")
    for k, v in val.get("dac1_static_typical", {}).items():
        md.append(f"- DAC1 static, tol {k}: " + ", ".join(f"{a} {b:.6g}" for a, b in v.items() if not isinstance(b, list)))
    md.append("")
    md += ["## Failures", ""] + ([f"- {f['block']} {f['test']} {f['case']}: {f['error']}"
                                  + (f" (the pair run again with tmax {list(f['retried_with'].values())[0]}: "
                                     f"{', '.join(f['retried_with'])} from the retry)" if f.get("retried_with") else "")
                                  for f in data["failures"]]
                                or ["none"]) + ["", "## Missing", ""] + (data["missing"][:200] or ["none"])
    mp = os.path.join(out_dir, "summary.md")
    open(mp, "w").write("\n".join(md) + "\n")
    print(f"wrote {os.path.relpath(jp, REPO)}, {os.path.relpath(mp, REPO)}")
    return js


QCHECK = dict(v0=-14e-3, v1=14e-3, step=0.2e-3)     # the frame check: comparators 11-19 of one seed


def check_quant_frame(seed, frames=(8, 32)):
    """The same ramp (QCHECK) with one strobe per `frame` MCLK (32: the loop's frame): the thresholds of the
    comparators inside the range should not depend on it (preamp settling, kickback recovery between strobes)."""
    case = ("mc", seed)
    with ThreadPoolExecutor(len(frames)) as ex:
        res = list(ex.map(lambda nm: quant_job(case, q=dict(QCHECK, nm=nm), tag=f"check_f{nm}_r14"), frames))
    thr = {nm: np.array(r["thr_v"], dtype=float) for nm, r in zip(frames, res) if r["ok"]}
    if len(thr) == len(frames):
        a, b = (thr[nm] for nm in frames)
        m = np.isfinite(a) & np.isfinite(b)
        dif = (a - b)[m] * 1e3
        print(f"seed {seed}: thresholds of {m.sum()} comparators, frame {frames[0]} - frame {frames[1]} MCLK: "
              f"mean {dif.mean():+.4f} mV, rms {np.sqrt(np.mean(dif ** 2)):.4f} mV, max |.| {np.abs(dif).max():.4f} mV "
              f"(ramp step {QCHECK['step'] * 1e3:g} mV); seconds {[r['seconds'] for r in res]}")
        for k in np.flatnonzero(m):
            print(f"  comparator {k}: {a[k] * 1e3:+.3f} / {b[k] * 1e3:+.3f} mV (ideal {QC.THR[k] * 1e3:+.3f})")
    else:
        print("failed:", [(r["case"], r["error"]) for r in res])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["run", "report", "checkq"])
    ap.add_argument("--blocks", nargs="+", default=["ota", "quant", "dac1"],
                    choices=["ota", "quant", "dac1", "dac1_static", "dac1_even"])
    ap.add_argument("--seeds", default="1-30")
    ap.add_argument("--corners", nargs="*", default=CORNERS)
    ap.add_argument("--jobs", type=int, default=2, help="concurrent ngspice processes")
    ap.add_argument("--qframe", type=int, default=QUANT["nm"], help="quantizer frame (MCLK)")
    ap.add_argument("--qstep", type=float, default=QUANT["step"], help="quantizer ramp step per strobe (V)")
    ap.add_argument("--dframe", type=int, default=DAC1["nm"], help="DAC1 frame (MCLK)")
    ap.add_argument("--npat", type=int, default=DAC1["npat"], help="DAC1 even test: [0, 1] pairs")
    ap.add_argument("--dtmax", default=DAC1["tmax"], help="DAC1 largest time step")
    ap.add_argument("--dtol", default=DAC1["tol"], choices=sorted(TOLS), help="DAC1 tolerances (TOLS)")
    ap.add_argument("--design", default=DAC1["design"], choices=sorted(EVEN_TESTS), help="DAC1 even test design")
    ap.add_argument("--stol", default=DAC1["stol"], choices=sorted(TOLS), help="DAC1 static test tolerances")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--hold-slot", action="store_true",
                    help="take one ngspice slot for the whole run and run its jobs one after another (short jobs)")
    a = ap.parse_args()
    QUANT.update(nm=a.qframe, step=a.qstep)
    DAC1.update(nm=a.dframe, npat=a.npat, tmax=a.dtmax, tol=a.dtol, design=a.design, stol=a.stol)
    seeds = parse_seeds(a.seeds)
    if a.what == "checkq":
        for s_ in seeds:
            check_quant_frame(s_)
        return
    if a.what == "run":
        global HELD
        cases = [("corner", c) for c in a.corners] + [("mc", s) for s in seeds]
        if a.hold_slot:
            HELD = acquire_slot()
        try:
            run_all(cases, a.blocks, 1 if a.hold_slot else min(a.jobs, 2))
        finally:
            if HELD is not None:
                fcntl.flock(HELD, fcntl.LOCK_UN)
                HELD.close()
    if not a.no_report:
        report(seeds)


if __name__ == "__main__":
    main()
