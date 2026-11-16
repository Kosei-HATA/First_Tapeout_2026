#!/usr/bin/env python3
"""The ADC integrator OTAs' static transfer on the extracted OTAs (11/15): the differential virtual-ground voltage
against the differential output, with the stage loads, for the ADC's own distortion at full scale. The loop model
(adc_beh_mc.py) has the OTAs linear (a DC gain only); enob_sine.py --ota-nl adds what this finds.

Bench: adc_block_mc.ota_deck (viz_data.ota_deck with the Monte Carlo / corner head, the extracted OTA with par = M,
eeg_bias and eeg_ref extracted; the stage loads: OTA1 RIN, the DAC1 resistance RD1, C1, R21 and the output wiring
capacitance; OTA2 R21, C2, the quantizer and wiring), OTA1's chopper frozen in phase A or B. The 1e16 H across each
integrating capacitor (DC unity feedback) gets a series source of -+VD/2 per side, so that at DC the output sits
at VD (differential) and the OTA's inputs settle where the OTA needs them: v(IXP) - v(IXN) = -VD / A(VD) + offset,
with the output current that R21 (OTA1) or the quantizer and its wiring (OTA2) draw at VD. VD is swept (.dc).
gmin 1e-15 (the pex devices with M > 1, memory ngspice-gmin-junction-artifact).

The OTAs, eeg_bias, eeg_ref and the bench loads are the same from r11 on (the OTA cells are r6's by XOR; RIN,
DAC1 and R21 on ppolyf_u since r11; adc_top's O1 / O2 wiring capacitance is the same in r11 and r12), so the r11
block benches (EEG_PEX_REV=r11, runs/adc_mc_r11/nets) serve r12.

Not here: the OTA's dynamic errors (the current into C1 from the quantization residue is below 1 uA against the
R21 current of the static sweep; the finite bandwidth is the loop model's excess delay); the poly resistors'
voltage coefficient (the PDK has none).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/ota_static.py run [--cases typical ss ff fs sf mc1-10]
           [--which ota1 ota2] [--vmax 0.6] [--step 0.002]
       gf180/tools/venv310/bin/python gf180/tapeout/pex/ota_static.py report
Output: runs/ota_static_r12/<ota>_<phase>_<case>/ (tb.spice, run.log, dc.csv), runs/ota_static_r12/ota_static.json
(per bench: A0, offset, the polynomial of vx(vo), the nonlinear part at a few outputs). nl_poly() gives the
nonlinear part to the loop model (enob_sine.py --ota-nl, ota_distortion.py).
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "runs", "ota_static_r12")
P = np.polynomial.polynomial
_M = None


def bench():
    """adc_block_mc (ota_deck, run_deck, head; not edited) with the block benches of r11 (= r12 for the OTAs and
    their loads). Imported only to run the benches: it reads EEG_PEX_REV when it loads, and the curves below are
    also read by scripts that run the r12 loop model (enob_sine.py --ota-nl)."""
    global _M
    if _M is None:
        os.environ["EEG_PEX_REV"] = "r11"
        import adc_block_mc
        _M = adc_block_mc
    return _M


def parse_cases(spec):
    out = []
    for s in spec:
        m = re.fullmatch(r"mc(\d+)(?:-(\d+))?", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            out += [("mc", k) for k in range(a, b + 1)]
        else:
            out.append(("corner", s))
    return out


def static_deck(case, which, phase, vmax, step):
    s = "1" if which == "ota1" else "2"
    base = bench().ota_deck(case, which, phase)
    lp, ln = f"LF{s}P I{s}P O{s}N 1e16\n", f"LF{s}N I{s}N O{s}P 1e16\n"
    assert base.count(lp) == 1 and base.count(ln) == 1
    # v(O_N) = v(I_P) - VD/2 and v(O_P) = v(I_N) + VD/2 at DC: v(O_P) - v(O_N) = VD - (v(I_P) - v(I_N))
    base = base.replace(lp, f"LF{s}P I{s}P XF{s}P 1e16\nESH{s}P O{s}N XF{s}P VSW 0 -0.5\n")
    base = base.replace(ln, f"LF{s}N I{s}N XF{s}N 1e16\nESH{s}N O{s}P XF{s}N VSW 0 0.5\n")
    base = base[:base.index(".control")]
    o = f"o{s}"
    return base + f""".options gmin=1e-15 reltol=1e-9 vntol=1e-12 abstol=1e-15
VSW VSW 0 DC 0
.control
set noaskquit
op
let vos = v(ixp) - v(ixn)
let b_iavdd = i(vavdd)
print vos b_iavdd
dc VSW {-vmax} {vmax} {step}
let vo = v({o}p) - v({o}n)
let vx = v(ixp) - v(ixn)
let vocm = (v({o}p) + v({o}n)) / 2 - v(vcm)
let vicm = (v(ixp) + v(ixn)) / 2 - v(vcm)
wrdata dc.csv vo vx vocm vicm
quit
.endc
.end
"""


def job(case, which, phase, vmax, step, force=False):
    M = bench()
    tag = f"{which}_{phase}_{M.case_name(case)}" if which == "ota1" else f"{which}_{M.case_name(case)}"
    d = os.path.join(OUT, tag)
    if not force and os.path.exists(os.path.join(d, "dc.csv")):
        return tag, None
    log, err, dt = M.run_deck(d, static_deck(case, which, phase, vmax, step), ["dc.csv"])
    print(f"{tag}: {'ok' if err is None else err} ({dt:.0f} s)", flush=True)
    return tag, err


def load(tag):
    """the sweep of one bench: VD, the output vo = v(OP) - v(ON), the inputs vx = v(IXP) - v(IXN), the output and
    input CM against VCM (V)"""
    a = np.loadtxt(os.path.join(OUT, tag, "dc.csv"))
    return a[:, 0], a[:, 1], a[:, 3], a[:, 5], a[:, 7]


# the fits: OTA1 over |vo| <= 0.3 V (the loop model's O1 peaks at 88 mV at full scale, figure 35's run), OTA2 over
# |vo| <= 0.2 V (O2 within the quantizer's +-46.9 mV)
SPAN = {"ota1": 0.3, "ota2": 0.2}
DEG = 7


def fit(tag):
    """vx(vo) over SPAN as a polynomial (ascending): the coefficients, A0 = 1 / c1 and the fit's largest residue"""
    which = tag.split("_")[0]
    _, vo, vx, _, _ = load(tag)
    sel = np.abs(vo) <= SPAN[which]
    c = P.polyfit(vo[sel], vx[sel], DEG)
    return c, 1.0 / c[1], float(np.abs(vx[sel] - P.polyval(vo[sel], c)).max())


def tags_of(which, case):
    """the bench tags of an OTA and case ('typical', 'ss', 'mc3', ...): OTA1 both chopper phases"""
    t = [f"ota1_A_{case}", f"ota1_B_{case}"] if which == "ota1" else [f"ota2_{case}"]
    return [x for x in t if os.path.exists(os.path.join(OUT, x, "dc.csv"))]


def nl_poly(which, case):
    """The static nonlinearity of an OTA (vx minus its offset and its slope at 0, V against the output vo), as
    ascending polynomial coefficients; OTA1: the mean of its chopper phases (the in-band part: the difference of
    the phases is chopped to 4 kHz). None if the case has no bench."""
    t = tags_of(which, case)
    if not t:
        return None
    c = np.mean([fit(x)[0] for x in t], axis=0)
    c[:2] = 0.0
    return c


def case_of(label):
    """the bench case of a loop-model die (adc_beh_mc labels: 'MOS typical', 'MOS ss (res_ss, mimcap_ss)', 'mc3';
    the resistor / MIM corners have typical blocks)"""
    if re.fullmatch(r"mc\d+", label):
        return label
    g = re.match(r"MOS (\w+)", label)
    return g.group(1) if g else "typical"


def die_nl(which, label):
    """an OTA's nonlinear part for a loop-model die: its own bench, typical where it has none; and the case used"""
    case = case_of(label)
    c = nl_poly(which, case)
    return (c, case) if c is not None else (nl_poly(which, "typical"), "typical")


def loop_nl(dies, m):
    """nl1, nl2 (S, DEG + 1) for adc_beh_mc.simulate, and per die the bench cases used ('ota1 case / ota2 case').
    nl1: OTA1's nonlinear part times 1 + RIN / RD1 (= 1 + vfs / VREF: the virtual-ground error drives both RIN and
    the steered DAC1 resistors), as an error at the input. nl2: OTA2's nonlinear part through R21 alone (DAC2
    steers currents), as an error in DAC2's level: RD2 / (R21 VREF). m: ct2_dac2_options."""
    nl1, nl2, used = [], [], []
    for d in dies:
        (c1, k1), (c2, k2) = die_nl("ota1", d.label), die_nl("ota2", d.label)
        used.append(f"{k1} / {k2}")
        nl1.append(c1 * (1.0 + d.vfs / m.VREF))
        nl2.append(c2 * (m.RD2_0 * d.k_rd2) / (m.R21_0 * d.k_r * m.VREF))
    return np.array(nl1), np.array(nl2), used


def report():
    rows = {}
    for tag in sorted(os.listdir(OUT)):
        if not os.path.exists(os.path.join(OUT, tag, "dc.csv")):
            continue
        which = tag.split("_")[0]
        c, a0, r = fit(tag)
        _, vo, vx, vocm, vicm = load(tag)
        nl = c.copy()
        nl[:2] = 0.0
        vs = (-0.2, -0.1, -0.05, 0.05, 0.1, 0.2) if which == "ota1" else (-0.1, -0.05, 0.05, 0.1)
        rows[tag] = dict(offset_uv=c[0] * 1e6, a0=a0, a0_db=20 * np.log10(abs(a0)), fit_resid_pv=r * 1e12,
                         poly=c.tolist(), nl_nv={f"{v:+.2f}": float(P.polyval(v, nl) * 1e9) for v in vs},
                         vo_range_v=[float(vo.min()), float(vo.max())],
                         vocm_mv_at_span=float(np.interp(SPAN[which], vo, vocm) * 1e3),
                         vicm_mv_at_span=float(np.interp(SPAN[which], vo, vicm) * 1e3))
        print(f"{tag:16s} A0 {rows[tag]['a0_db']:7.3f} dB  offset {c[0] * 1e6:+8.3f} uV  fit {r * 1e12:5.1f} pV  "
              f"nonlinear part at {'/'.join(f'{v:+.2f}' for v in vs)} V: "
              + " ".join(f"{v:+.3f}" for v in rows[tag]["nl_nv"].values()) + " nV")
    json.dump(rows, open(os.path.join(OUT, "ota_static.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "report"])
    ap.add_argument("--cases", nargs="+", default=["typical", "ss", "ff", "fs", "sf"])
    ap.add_argument("--which", nargs="+", default=["ota1", "ota2"])
    ap.add_argument("--vmax", type=float, default=0.6)
    ap.add_argument("--step", type=float, default=0.002)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "report":
        report()
        return
    os.makedirs(OUT, exist_ok=True)
    jobs = [(c, w, ph) for c in parse_cases(a.cases) for w in a.which for ph in (("A", "B") if w == "ota1" else ("-",))]
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(lambda j: job(*j, a.vmax if j[1] == "ota1" else min(a.vmax, 0.3), a.step, a.force), jobs))
    report()


if __name__ == "__main__":
    main()
