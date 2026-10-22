#!/usr/bin/env python3
"""OTA1 (gf180_inside_cascode_ota, import_20261021/adc_gain10_loop/otas.spice) noise,
frozen chopper phase, as seen by the ADC input and the electrode.

The OTA runs open loop with ideal inputs at CM (1.65 V, as in the loop: RIN and the
DAC1 resistors both return to CM) and its loop load on each output (C1 680.5 pF to
AC ground, 4 pF wiring). .ac gives the differential gain A(f), .noise every
generator's output density S_i(f); S_i/|A|^2 is that generator's OTA-input-referred
density N_i(f).

Chopping (input TGs before the pair, current commutators after the pair drains and
after the PMOS loads, outputs never swapped) moves the noise of the input pair and of
the PMOS loads to the chopper harmonics; what is left in band is the harmonic sum
sum_k 8/(pi k)^2 N_i(k fch) over odd k. Generators after the commutators (cascodes,
drain/load commutator TGs, CMFB, tail) are not chopped: their in-band N_i counts as is
(conservative for the commutator TGs). The input TGs are thermal only (no DC current),
so chopping does not change their contribution.

In the loop the OTA input noise reaches the ADC input with the noise gain
1 + RIN/RD1 = 1 + 9375/(300k/31) = 1.969 (RIN, RD1 and C1 at band frequencies), and
the electrode with that divided by the AFE gain (277 now, 318 if Cf is cut).

Usage: python3 ota1_noise.py [--fch 16e3 32e3 64e3 128e3] [--corner typical] [--temp 27]
       [--lin 2] [--mscale 1]
"""
import argparse
import os
import re
import subprocess
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "afe"))
import afe_noise  # noqa: E402  (read_raw, chop_sum, PDK)

OTAS = os.path.join(REPO, "gf180", "tapeout", "import_20261021", "adc_gain10_loop", "otas.spice")
BAND = (0.5, 100.0)
NG = 1 + 9375 / (300e3 / 31)  # OTA1 input -> ADC input noise gain
GAINS = (277.0, 318.0)  # AFE gain now / with Cf cut
# (group, device-path regex, chopped)
GROUPS = [("input pair", r"xcore\.xin_[pn]$", True),
          ("PMOS loads", r"xcore\.xload_[pn]$", True),
          ("input TGs", r"^xdut\.xi[pn]_[ab]\.", False),
          ("drain commutator TGs", r"xcore\.xd[pn]_[ab]\.", False),
          ("load commutator TGs", r"xcore\.xp[pn]_[ab]\.", False),
          ("NMOS cascodes", r"xcore\.xnc_[pn]$", False),
          ("PMOS cascodes", r"xcore\.xpc_[pn]$", False),
          ("tail", r"xcore\.xtail$", False),
          ("CMFB", r"xcmfb\.", False)]


def otas_variant(lin=2.0, mscale=1.0):
    """otas.spice with the OTA1 input pair (Xin_p/Xin_n of gf180_ct_core_currentchop,
    W 10 um, L 2 um, m 2048) at length lin um and multiplicity 2048 * mscale."""
    txt = open(OTAS).read()
    body = re.search(r"\.subckt gf180_ct_core_currentchop .*?\.ends gf180_ct_core_currentchop", txt, re.S).group(0)
    new = re.sub(r"^(Xin_[pn] .* W=10u L=)2u( nf=1 m=)2048 ",
                 lambda mo: f"{mo.group(1)}{lin:g}u{mo.group(2)}{int(round(2048 * mscale))} ", body, flags=re.M)
    if new.count(f"L={lin:g}u") < 2 and lin != 2.0:
        raise SystemExit("input-pair lines not found")
    return txt.replace(body, new)


def deck(corner, temp, otas=OTAS):
    return f"""* OTA1 frozen-phase (A) noise, open loop, loop load
.include {afe_noise.PDK}/design.ngspice
.lib {afe_noise.PDK}/sm141064.ngspice {corner}
.include {otas}
.temp {temp}
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
VBN1 VBN1 0 .85
VNC1 VNC1 0 2
VPC1 VPC1 0 1.7
VBCM1 VBCM1 0 .82
VSRC SRC 0 DC 0 AC 1
EP INP CM SRC 0 0.5
EN INN CM SRC 0 -0.5
XDUT INP INN OUTP OUTN CM VBN1 VNC1 VPC1 VBCM1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD 0 gf180_inside_cascode_ota
C1P OUTP 0 680.5p
C1N OUTN 0 680.5p
CLP OUTP 0 4p
CLN OUTN 0 4p
VCIA CIA 0 3.3
VNCIA NCIA 0 0
VCIB CIB 0 0
VNCIB NCIB 0 3.3
VCDA CDA 0 3.3
VNCDA NCDA 0 0
VCDB CDB 0 0
VNCDB NCDB 0 3.3
.control
set noaskquit
op
print i(vdd) v(outp) v(outn) v(xdut.xota.vbp)
print @m.xdut.xota.xcore.xin_p.m0[gm] @m.xdut.xota.xcore.xin_p.m0[id] @m.xdut.xota.xcore.xload_p.m0[gm]
print @m.xdut.xota.xcore.xin_p.m0[vds] @m.xdut.xota.xcore.xin_p.m0[vdsat] @m.xdut.xota.xcore.xload_p.m0[vds] @m.xdut.xota.xcore.xload_p.m0[vdsat]
print @m.xdut.xota.xcore.xnc_p.m0[vds] @m.xdut.xota.xcore.xnc_p.m0[vdsat] @m.xdut.xota.xcore.xpc_p.m0[vds] @m.xdut.xota.xcore.xpc_p.m0[vdsat]
print @m.xdut.xota.xcore.xtail.m0[vds] @m.xdut.xota.xcore.xtail.m0[vdsat]
print @m.xdut.xota.xcore.xin_p.m0[cgg] @m.xdut.xota.xcore.xin_p.m0[cgs] @m.xdut.xota.xcore.xin_p.m0[cgd]
ac dec 20 0.1 1e8
let hr = real(v(outp) - v(outn))
let hi = imag(v(outp) - v(outn))
wrdata ac.csv hr hi
noise v(outp, outn) VSRC dec 20 0.1 1e8 1
setplot noise1
set filetype=ascii
write noise.raw
quit
.endc
.end
"""


def run(corner, temp, fchs, lin=2.0, mscale=1.0):
    d = os.path.join(HERE, "runs", f"ota1_noise_{corner}_{temp}_l{lin:g}_m{mscale:g}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "otas.spice"), "w").write(otas_variant(lin, mscale))
    open(os.path.join(d, "tb.spice"), "w").write(deck(corner, temp, "otas.spice"))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    val = lambda k: float(re.search(rf"{re.escape(k)} = ([-0-9.e+]+)", log).group(1))
    op = {"IDD (mA)": -val("i(vdd)") * 1e3, "out CM (V)": (val("v(outp)") + val("v(outn)")) / 2,
          "pair gm (mS)": val("@m.xdut.xota.xcore.xin_p.m0[gm]") * 1e3,
          "pair Id (mA)": val("@m.xdut.xota.xcore.xin_p.m0[id]") * 1e3,
          "pair Cgg (pF)": val("@m.xdut.xota.xcore.xin_p.m0[cgg]") * 1e12,
          "pair Cgs (pF)": -val("@m.xdut.xota.xcore.xin_p.m0[cgs]") * 1e12}
    for dev in ("xin_p", "xload_p", "xnc_p", "xpc_p", "xtail"):
        op[f"{dev} VDS-VDSAT (V)"] = (abs(val(f"@m.xdut.xota.xcore.{dev}.m0[vds]"))
                                      - abs(val(f"@m.xdut.xota.xcore.{dev}.m0[vdsat]")))
    ac = np.loadtxt(os.path.join(d, "ac.csv"))
    f, h = ac[:, 0], ac[:, 1] + 1j * ac[:, 3]
    nz = afe_noise.read_raw(os.path.join(d, "noise.raw"))
    fn = nz["frequency"]
    a2 = np.abs(np.interp(fn, f, h.real) + 1j * np.interp(fn, f, h.imag)) ** 2
    gens = {}
    for n, v in nz.items():
        mo = re.match(r"onoise\.m\.(.+)\.m0\.(\w+)$", n)
        if mo:
            gens[mo.groups()] = v ** 2 / a2  # OTA-input-referred density (V^2/Hz)
    band = (fn >= BAND[0]) & (fn <= BAND[1])
    bw = BAND[1] - BAND[0]

    def inband(x):  # rms over the band of a density array (V^2/Hz)
        return np.sqrt(np.trapezoid(x[band], fn[band]))

    rows = {}
    for g, rx, chopped in GROUPS:
        th = sum((v for (p, k), v in gens.items() if re.search(rx, p) and k != "1overf"), np.zeros_like(fn))
        fl = sum((v for (p, k), v in gens.items() if re.search(rx, p) and k == "1overf"), np.zeros_like(fn))
        res = {"static th": inband(th), "static 1/f": inband(fl)}
        for fch in fchs:
            kmax = int(fn[-1] / fch) - 1
            if chopped:
                res[fch] = np.hypot(np.sqrt(afe_noise.chop_sum(fn, th, kmax, fch) * bw),
                                    np.sqrt(afe_noise.chop_sum(fn, fl, kmax, fch) * bw))
            else:
                res[fch] = np.hypot(res["static th"], res["static 1/f"])
        rows[g] = res
    allp = [p for (p, k) in gens]
    lost = [p for p in set(allp) if not any(re.search(rx, p) for _, rx, _ in GROUPS)]
    return op, rows, lost, fn, gens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fch", type=float, nargs="+", default=[16e3, 32e3, 64e3, 128e3])
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=int, default=27)
    ap.add_argument("--lin", type=float, default=2.0, help="input-pair L (um), import 2")
    ap.add_argument("--mscale", type=float, default=1.0, help="input-pair multiplicity scale (import 2048)")
    a = ap.parse_args()
    op, rows, lost, fn, gens = run(a.corner, a.temp, a.fch, a.lin, a.mscale)
    print(f"OTA1 {a.corner} {a.temp} C, pair L {a.lin:g} um m {2048 * a.mscale:g}: "
          + ", ".join(f"{k} {v:.4g}" for k, v in op.items()))
    if lost:
        print("  generators in no group: " + ", ".join(sorted(lost)))
    tot = {k: np.sqrt(sum(r[k] ** 2 for r in rows.values())) for k in ["static th", "static 1/f"] + a.fch}
    tot_static = np.hypot(tot["static th"], tot["static 1/f"])
    sel = (fn >= 10) & (fn <= 100)
    white = np.sqrt(np.mean(sum(gens.values())[sel]))
    print(f"  OTA-input density 10-100 Hz mean {white * 1e9:.2f} nV/rtHz; at 1 Hz "
          f"{np.sqrt(np.interp(1.0, fn, sum(gens.values()))) * 1e9:.1f} nV/rtHz")
    hdr = "| group | static thermal | static 1/f | " + " | ".join(f"chopped {f / 1e3:g} kHz" for f in a.fch) + " |"
    print("\nOTA input, 0.5-100 Hz (nVrms)\n" + hdr + "\n|---|---|---|" + "---|" * len(a.fch))
    for g, r in rows.items():
        print(f"| {g} | {r['static th'] * 1e9:.2f} | {r['static 1/f'] * 1e9:.2f} | "
              + " | ".join(f"{r[f] * 1e9:.2f}" for f in a.fch) + " |")
    print(f"| total | {tot['static th'] * 1e9:.2f} | {tot['static 1/f'] * 1e9:.2f} | "
          + " | ".join(f"{tot[f] * 1e9:.2f}" for f in a.fch) + " |")
    print(f"\nelectrode-referred (x {NG:.3f} / AFE gain), nVrms")
    for g in GAINS:
        print(f"  AFE gain {g:g}: unchopped {tot_static * NG / g * 1e9:.3f}; "
              + ", ".join(f"chopped {f / 1e3:g} kHz {tot[f] * NG / g * 1e9:.3f}" for f in a.fch))


if __name__ == "__main__":
    main()
