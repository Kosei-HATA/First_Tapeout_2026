#!/usr/bin/env python3
"""AFE (CCIA, gain 318 'cpf210' candidate) noise analysis from frozen-chopper
small-signal runs.

One chopper phase (A or B) is frozen: .ac gives the electrode-to-output transfer
H(f), .noise gives every noise generator's output density S_i(f) (ngspice keeps
the per-generator spectra when pts_per_summary is set). Two numbers come out:

  frozen thermal  : sum of the non-flicker generators, divided by |H|^2 and
                    averaged over 10-100 Hz, i.e. the white floor of the stopped
                    amplifier (comparable to the independent environment's
                    "AFE native thermal").
  chopped estimate: the output chopper multiplies the amplifier output by a
                    +-1 square wave with Fourier weights |c_k|^2 = 4/(pi k)^2 at
                    odd k, so the in-band output density is
                    sum_k 8/(pi k)^2 S_i(k fch) and the in-band signal gain is
                    G = sum_k 8/(pi k)^2 Re H(k fch). The electrode-referred
                    density sqrt(sum ...)/G includes the 1/f noise that chopping
                    leaves at the chopper harmonics. This holds for every source
                    after the input chopper's modulation point (amplifier, both
                    TG sets, CMFB); the electrode resistors, which would see G^2,
                    are noiseless here.

Electrode source resistors and the ADC-load model (RIN 9375) are noiseless
(other ledgers). The INP/INN DC path (reset state, INP=ONI at DC) is a 1e16 H
inductor: DC short, open in band, noiseless. The real path (pseudo-R) is
upconverted by the output chopper and stays below 1e-3 nV/rtHz.

Design knobs (multipliers relative to the imported candidate):
  --core m    input pairs, tails and cascodes (m=1 is the import: N 2048, P 4096 ...)
  --tg m      input chopper TG multiplicity (import 64)
  --ln/--lp   NMOS/PMOS input-pair length in um (import 0.28)
  --mp        PMOS input-pair multiplicity scale (import 4096)
  --itail     bias current scale (NMOS tail multiplicity at fixed VBN)
  --scasc     PMOS tail and cascode size scale (default = itail)
  --vpc       PMOS cascode gate bias (import 1.1 V)
  --cpf       impedance-boost capacitor in pF (import 2.10)
  --boost     cascode gain boosting: 0 (import), tr (transistor boosters BOOST_N/BOOST_P),
              or a behavioural booster gain

The chip-intrinsic reference is a low-impedance source (RS 100 ohm per leg).
With a larger RS the chopped estimate grows: the amplifier noise at fch flows
through the input capacitances into RS (an input current noise). Above a few
kohm the baseband-side capacitance of the input TGs, which a frozen phase
cannot represent, makes this estimate inaccurate (afe_chop_gain.py compares the
gain with a chopped transient: 236.1 vs 236.6 at 1 ohm, 166 vs 198 at 50 kohm).

Usage: python3 afe_noise.py [--core 1] [--tg 64] [--ln 0.28] [--lp 0.28] [--rs 100]
       [--fch 64e3] [--phase A|B] [--keep]
"""
import argparse
import os
import re
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
CAND = os.path.join(REPO, "gf180", "tapeout", "import_20261021", "afe_cpf210", "candidate.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
FCH = 64e3
BAND = (0.5, 100.0)
RS = 100.0  # per leg: low-impedance bench source (chip-intrinsic reference)
BOOST = 0  # cascode gain boosting: 0 = off (import), "tr" = transistor boosters, number = behavioural gain
BOOST_N = [20.0, 4.0, 16, 1e-3]  # NMOS-cascode booster: W um, L um, m, bias current A
BOOST_P = [20.0, 2.0, 64, 600e-6]  # PMOS-cascode booster
BOOST_LOAD = True  # transistor mirror loads for the boosters (False: ideal current sources)
LOAD_L = 8.0  # booster load length (um); the finger count scales with it at constant W/L
BOOST_POLE = 100e3  # behavioural booster: dominant pole (Hz); unity-gain frequency = gain x pole
GROUPS = [("NMOS pair", r"xcore\.xn_[np]$"), ("PMOS pair", r"xcore\.xp_[np]$"), ("tails", r"xcore\.x[np]t$"),
          ("cascodes", r"xcore\.x[np]c_[np]$"), ("CMFB", r"xcmfb\."),
          ("input TG", r"\.xi[pn]_[ab]\."), ("output TG", r"\.xo[pn]_[ab]\."),
          ("boosters", r"xcore\.xg[np]c[pn]b$"), ("booster loads", r"xcore\.xg[np]c[pn]l$"),
          ("booster bias", r"xcore\.xbl[pn]d$")]


def candidate(core, tg, ln=0.28, lp=0.28, mp=1.0, itail=1.0, scasc=None, tgo=8, lnc=1.0, lpc=1.0,
              boost=None, dnref=1.0535, dpref=2.2582):
    """Scale the core device multiplicities and the input TG; set the input-pair
    lengths (um) of the NMOS (ln) and PMOS (lp) halves, scale the PMOS pair
    multiplicity (mp) and the bias current (itail: NMOS tail multiplicity at
    fixed VBN). scasc scales the PMOS tail and the cascodes (default: itail,
    i.e. constant current density)."""
    scasc = itail if scasc is None else scasc
    boost = BOOST if boost is None else boost
    txt = open(CAND).read()
    txt = re.sub(r"^(XN_[PN] .* L=)0\.28u", rf"\g<1>{ln:g}u", txt, flags=re.M)
    txt = re.sub(r"^(XP_[PN] .* L=)0\.28u", rf"\g<1>{lp:g}u", txt, flags=re.M)
    txt = re.sub(r"^(XNC_[PN] .* L=)1u", rf"\g<1>{lnc:g}u", txt, flags=re.M)
    txt = re.sub(r"^(XPC_[PN] .* L=)1u", rf"\g<1>{lpc:g}u", txt, flags=re.M)

    def scale(rx, k):
        return lambda mo: (mo.group(0).replace(f"m={mo.group(1)} ", f"m={int(round(int(mo.group(1)) * k))} ")
                           if re.match(rx, mo.group(0)) else mo.group(0))
    txt = re.sub(r"^X\S+ .* m=(\d+) .*$", scale(r"XP_[PN] ", mp), txt, flags=re.M)
    txt = re.sub(r"^X\S+ .* m=(\d+) .*$", scale(r"XNT ", itail), txt, flags=re.M)
    txt = re.sub(r"^X\S+ .* m=(\d+) .*$", scale(r"X(PT|NC_[PN]|PC_[PN]) ", scasc), txt, flags=re.M)

    def scale_core(mo):
        line, m = mo.group(0), int(mo.group(1))
        return line.replace(f"m={m} ", f"m={int(round(m * core))} ")
    body = re.search(r"\.subckt gf180_reuse_cascoded_core.*?\.ends", txt, re.S).group(0)
    new = re.sub(r"^X\S+ .* m=(\d+) .*$", scale_core, body, flags=re.M)
    txt = txt.replace(body, new)
    tgb = re.search(r"\.subckt reuse_input_tg_m64.*?\.ends", txt, re.S).group(0)
    txt = txt.replace(tgb, tgb.replace("m=64", f"m={tg}"))
    if boost == "tr":  # transistor regulated cascodes: one common-source booster per cascode,
        # current-source loads (ideal here; BN/BP = booster W um, L um, m, bias current A)
        bn, bp = BOOST_N, BOOST_P
        for dev, gate, src, kind, (w, l, m, ib) in (
                ("XNC_P", "VNC", "DNP", "n", bn), ("XNC_N", "VNC", "DNN", "n", bn),
                ("XPC_P", "VPC", "DPP", "p", bp), ("XPC_N", "VPC", "DPN", "p", bp)):
            g = "G" + dev[1:].replace("_", "")
            txt = re.sub(rf"^({dev} \S+ ){gate} ", rf"\g<1>{g} ", txt, flags=re.M)
            # load: mirror copy of a diode (LOAD_L um long, W/L 10 per finger group of LOAD_L/2
            # fingers, 125 uA per group) fed by an ideal reference current; BOOST_LOAD = False
            # keeps an ideal current source
            ll = LOAD_L
            mf = max(1, int(round(ib / 125e-6))) * int(round(ll / 2))
            if kind == "n":
                amp = f"X{g}B {g} {src} VSS VSS nfet_03v3 W={w:g}u L={l:g}u nf=1 m={m}\n"
                amp += (f"X{g}L {g} BLP VDD VDD pfet_03v3 W=20u L={ll:g}u nf=1 m={mf}\n" if BOOST_LOAD
                        else f"I{g}B VDD {g} {ib:g}\n")
            else:
                amp = f"X{g}B {g} {src} VDD VDD pfet_03v3 W={w:g}u L={l:g}u nf=1 m={m}\n"
                amp += (f"X{g}L {g} BLN VSS VSS nfet_03v3 W=20u L={ll:g}u nf=1 m={mf}\n" if BOOST_LOAD
                        else f"I{g}B {g} VSS {ib:g}\n")
            txt = txt.replace(".ends gf180_reuse_cascoded_core", amp + ".ends gf180_reuse_cascoded_core")
        if BOOST_LOAD:
            txt = txt.replace(".ends gf180_reuse_cascoded_core",
                              f"XBLPD BLP BLP VDD VDD pfet_03v3 W=20u L={LOAD_L:g}u nf=1 m={int(round(LOAD_L / 2))}\n"
                              "IBLP BLP VSS 125u\n"
                              f"XBLND BLN BLN VSS VSS nfet_03v3 W=20u L={LOAD_L:g}u nf=1 m={int(round(LOAD_L / 2))}\n"
                              "IBLN VDD BLN 125u\n"
                              ".ends gf180_reuse_cascoded_core")
    elif boost:  # behavioural gain-boosted (regulated) cascodes: gm-R-C amplifier per cascode,
        # gain A = gm*Ro (Ro = 100 kohm to VNC/VPC), pole 100 kHz, gate = VNC/VPC + A (ref - source)
        ro, co = 100e3, 1 / (2 * np.pi * 100e3 * BOOST_POLE)
        for dev, gate, src, ref in (("XNC_P", "VNC", "DNP", dnref), ("XNC_N", "VNC", "DNN", dnref),
                                    ("XPC_P", "VPC", "DPP", dpref), ("XPC_N", "VPC", "DPN", dpref)):
            g = "G" + dev[1:].replace("_", "")
            txt = re.sub(rf"^({dev} \S+ ){gate} ", rf"\g<1>{g} ", txt, flags=re.M)
            txt = txt.replace(".ends gf180_reuse_cascoded_core",
                              f"V{g}REF {g}REF VSS {ref:g}\n"
                              f"G{g}B VSS {g} {g}REF {src} {boost / ro:g}\n"
                              f"R{g}B {g} {gate} {ro:g}\nC{g}B {g} {gate} {co:g}\n"
                              ".ends gf180_reuse_cascoded_core")
    tgo_b = re.search(r"\.subckt reuse_tg .*?\.ends", txt, re.S).group(0)
    txt = txt.replace(tgo_b, tgo_b.replace("m=8 ", f"m={tgo} "))
    return txt


def set_boost(s):
    """Command-line value of --boost: "0", "tr" or a behavioural gain."""
    global BOOST
    BOOST = s if s == "tr" else float(s)


def deck(core, tg, phase, rs=RS, vpc=1.1, cpf=2.10, vnc=2.2):
    a, b = ("3.3", "0") if phase == "A" else ("0", "3.3")
    return f"""* AFE frozen-phase noise, core x{core}, input TG m={tg}, phase {phase}
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice typical
.include cand.spice
.temp 27
.options sparse reltol=1e-6 vntol=1e-10 abstol=3e-13 bypass=0
VDD VDD 0 3.3
VCM CM 0 1.65
VBN VBN 0 0.8485
VBCM VBCM 0 0.82
VNC VNC 0 {vnc:g}
VPC VPC 0 {vpc:g}
VSRC SRC 0 DC 0 AC 1
EP SRC_P CM SRC 0 0.5
EN SRC_N CM SRC 0 -0.5
RSP SRC_P VINP {rs:g} noisy=0
RSN SRC_N VINN {rs:g} noisy=0
CINP WP INP 636p
CINN WN INN 636p
CFBP ONI INP 2p
CFBN OPI INN 2p
CPFP WP OPI {cpf:g}p
CPFN WN ONI {cpf:g}p
CLOADP OUTP 0 4p
CLOADN OUTN 0 4p
RLOADP OUTP CM 9375 noisy=0
RLOADN OUTN CM 9375 noisy=0
* DC path = reset state (INP=ONI at DC), open in band: 1e16 H in parallel with
* Cf (2 pF) resonates at 1.1 mHz.
LDCP INP ONI 1e16
LDCN INN OPI 1e16
XDUT VINP VINN WP WN INP INN OPI ONI OUTP OUTN CM VBN VBCM VNC VPC VBP CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD 0 gf180_ccia_local_feedback
VCIA CIA 0 {a}
VNCIA NCIA 0 {b}
VCIB CIB 0 {b}
VNCIB NCIB 0 {a}
VCDA CDA 0 {a}
VNCDA NCDA 0 {b}
VCDB CDB 0 {b}
VNCDB NCDB 0 {a}
* initial guess from the independent-environment reset-state operating point
.nodeset v(inp)=1.65 v(inn)=1.65 v(opi)=1.64995 v(oni)=1.64995 v(outp)=1.64995 v(outn)=1.64995
+ v(wp)=1.65 v(wn)=1.65 v(vbp)=2.3312 v(xdut.xcmfb.nd)=2.3518 v(xdut.xcmfb.nta)=0.7027
+ v(xdut.xcmfb.ntb)=0.7027 v(xdut.xcore.dnn)=0.9626 v(xdut.xcore.dnp)=0.9626
+ v(xdut.xcore.dpn)=2.4364 v(xdut.xcore.dpp)=2.4364 v(xdut.xcore.sn)=0.6856 v(xdut.xcore.sp)=2.7712
.control
set noaskquit
op
print i(vdd) v(vbp) v(opi) v(oni) v(inp)
print @m.xdut.xcore.xnt.m0[vds] @m.xdut.xcore.xnt.m0[vdsat] @m.xdut.xcore.xpt.m0[vds] @m.xdut.xcore.xpt.m0[vdsat]
print @m.xdut.xcore.xn_p.m0[vds] @m.xdut.xcore.xn_p.m0[vdsat] @m.xdut.xcore.xp_p.m0[vds] @m.xdut.xcore.xp_p.m0[vdsat]
print @m.xdut.xcore.xnc_p.m0[vds] @m.xdut.xcore.xnc_p.m0[vdsat] @m.xdut.xcore.xpc_p.m0[vds] @m.xdut.xcore.xpc_p.m0[vdsat]
ac dec 20 0.1 1e7
let hr = real(v(outp) - v(outn))
let hi = imag(v(outp) - v(outn))
wrdata ac.csv hr hi
noise v(outp, outn) VSRC dec 20 0.1 1e7 1
setplot noise1
set filetype=ascii
write noise.raw
quit
.endc
.end
"""


def read_raw(path):
    """ngspice ASCII raw file -> {name: array}."""
    txt = open(path).read()
    head, vals = txt.split("Values:\n", 1)
    names = re.findall(r"^\s+\d+\s+(\S+)\s+\S+", head.split("Variables:\n", 1)[1], re.M)
    data = np.array(vals.split(), float).reshape(-1, len(names) + 1)[:, 1:]
    return {n: data[:, i] for i, n in enumerate(names)}


def chop_sum(f, s, kmax, fch=FCH):
    """sum over odd k of 8/(pi k)^2 s(k fch), log-f interpolation."""
    k = np.arange(1, kmax + 1, 2)
    w = 8 / (np.pi * k) ** 2
    return np.sum(w * np.interp(np.log(k * fch), np.log(f), s))


def analyze(d, log, fch=FCH, keep=False):
    """Operating point, saturation margins and the frozen/chopped noise ledger of a
    finished run folder (ac.csv, noise.raw and the ngspice log)."""
    idd = float(re.search(r"i\(vdd\) = ([-0-9.e+]+)", log).group(1))
    sat = {}  # device: VDS - VDSAT (V, magnitudes)
    for dev in ("xnt", "xpt", "xn_p", "xp_p", "xnc_p", "xpc_p"):
        vds = float(re.search(rf"xcore\.{dev}\.m0\[vds\] = ([-0-9.e+]+)", log).group(1))
        vdsat = float(re.search(rf"xcore\.{dev}\.m0\[vdsat\] = ([-0-9.e+]+)", log).group(1))
        sat[dev] = abs(vds) - abs(vdsat)
    ac = np.loadtxt(os.path.join(d, "ac.csv"))
    f, h = ac[:, 0], ac[:, 1] + 1j * ac[:, 3]
    nz = read_raw(os.path.join(d, "noise.raw"))
    fn = nz["frequency"]
    gens = {}  # (device path, generator) -> output density^2
    for n, v in nz.items():
        mo = re.match(r"onoise\.m\.(.+)\.m0\.(\w+)$", n)
        if mo:
            gens[mo.groups()] = v ** 2
    kmax = int(fn[-1] / fch) - 1
    habs2 = np.abs(np.interp(fn, f, h.real) + 1j * np.interp(fn, f, h.imag)) ** 2
    g_chop = abs(chop_sum(f, h.real, kmax, fch))
    sel = (fn >= 10) & (fn <= 100)
    bw = BAND[1] - BAND[0]

    def ledger(match):
        th = sum((v for (p, g), v in gens.items() if match(p) and g != "1overf"), np.zeros_like(fn))
        fl = sum((v for (p, g), v in gens.items() if match(p) and g == "1overf"), np.zeros_like(fn))
        frozen_th = np.sqrt(np.mean(th[sel] / habs2[sel]) * bw)
        chop_th = np.sqrt(chop_sum(fn, th, kmax, fch) * bw) / g_chop
        chop_fl = np.sqrt(chop_sum(fn, fl, kmax, fch) * bw) / g_chop
        return frozen_th * 1e9, chop_th * 1e9, chop_fl * 1e9

    res = dict(idd_mA=-idd * 1e3, sat=sat,
               gain10=np.sqrt(np.interp(10, fn, habs2)), gain_chop=g_chop,
               total=ledger(lambda p: True),
               groups={g: ledger(lambda p, rx=rx: re.search(rx, p)) for g, rx in GROUPS})
    covered = sum(np.array(v) ** 2 for v in res["groups"].values())
    res["unassigned"] = np.sqrt(np.maximum(np.array(res["total"]) ** 2 - covered, 0))
    if not keep:
        for x in ("ac.csv", "noise.raw"):
            os.remove(os.path.join(d, x))
    return res


def run(core, tg, phase, keep=False, rs=RS, ln=0.28, lp=0.28, fch=FCH, mp=1.0, itail=1.0, scasc=None,
        vpc=1.1, cpf=2.10):
    sc = itail if scasc is None else scasc
    name = (f"core{core:g}_tg{tg}_ln{ln:g}_lp{lp:g}_mp{mp:g}_it{itail:g}_sc{sc:g}_vpc{vpc:g}_b{BOOST}_{phase}"
            f"_cpf{cpf:g}_rs{rs:g}_f{fch/1e3:g}k")
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "cand.spice"), "w").write(candidate(core, tg, ln, lp, mp, itail, sc))
    open(os.path.join(d, "tb.spice"), "w").write(deck(core, tg, phase, rs, vpc, cpf))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    if re.search(r"stepping failed|Transient op", log):
        raise RuntimeError(f"{name}: operating point did not converge directly (see run.log)")
    res = analyze(d, log, fch, keep)
    res.update(core=core, tg=tg, ln=ln, lp=lp, mp=mp, itail=itail, scasc=sc, vpc=vpc, rs=rs, fch=fch, phase=phase)
    return res


def report(r):
    t = r["total"]
    print(f"core x{r['core']:g}, TG m={r['tg']}, L N/P {r['ln']:g}/{r['lp']:g} um, RS {r['rs']:g}, "
          f"fch {r['fch']/1e3:g} kHz, phase {r['phase']}: IDD {r['idd_mA']:.3f} mA, "
          f"gain@10Hz {r['gain10']:.2f} (chopped {r['gain_chop']:.2f})")
    print(f"  electrode-referred, {BAND[0]}-{BAND[1]} Hz (nVrms): frozen thermal {t[0]:.3f}, "
          f"chopped thermal {t[1]:.3f}, chopped 1/f {t[2]:.3f}, chopped total {np.hypot(t[1], t[2]):.3f}")
    for g, (a, b, c) in r["groups"].items():
        print(f"    {g:11s} frozen th {a:6.3f}  chopped th {b:6.3f}  chopped 1/f {c:6.3f}")
    print("    VDS-VDSAT (V): " + ", ".join(f"{k} {v:.3f}" for k, v in r["sat"].items()))
    if max(r["unassigned"]) > 0.01 * max(t):
        print(f"    unassigned {r['unassigned']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=float, default=1.0)
    ap.add_argument("--tg", type=int, default=64)
    ap.add_argument("--phase", default="A")
    ap.add_argument("--rs", type=float, default=RS, help="source resistance per leg (ohm)")
    ap.add_argument("--ln", type=float, default=0.28, help="NMOS input-pair L (um)")
    ap.add_argument("--lp", type=float, default=0.28, help="PMOS input-pair L (um)")
    ap.add_argument("--fch", type=float, default=FCH, help="chopper frequency for the harmonic sum")
    ap.add_argument("--mp", type=float, default=1.0, help="PMOS input-pair multiplicity scale")
    ap.add_argument("--itail", type=float, default=1.0, help="bias current scale (NMOS tail)")
    ap.add_argument("--scasc", type=float, default=None,
                    help="PMOS tail and cascode size scale (default: same as --itail)")
    ap.add_argument("--vpc", type=float, default=1.1, help="PMOS cascode gate bias (V)")
    ap.add_argument("--cpf", type=float, default=2.10, help="impedance-boost capacitor (pF)")
    ap.add_argument("--boost", default="0", help="cascode boosting: 0, tr, or a behavioural gain")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    set_boost(a.boost)
    report(run(a.core, a.tg, a.phase, a.keep, a.rs, a.ln, a.lp, a.fch, a.mp, a.itail, a.scasc, a.vpc,
               a.cpf))


if __name__ == "__main__":
    main()
