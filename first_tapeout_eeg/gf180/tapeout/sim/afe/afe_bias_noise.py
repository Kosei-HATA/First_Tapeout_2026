#!/usr/bin/env python3
"""AFE netlist of this rev (gf180/tapeout/afe/eeg_afe.spice) driven by the real
bias block (gf180/tapeout/bias/eeg_bias.spice): operating point, saturation
margins, frozen-phase gain and the chopped noise estimate of afe_noise.py, over
process corners, temperature and the AFE_IBIAS code.

The amplifier level (eeg_afe_amp) is used so that the testbench can keep the
noiseless 1e16 H INP/INN DC path of afe_noise.py; Cin, Cf and Cpf are the same
values as in eeg_afe.

Cases are corner:temperature:AFE_IBIAS code[:NBLN:NBLP], where NBLN/NBLP are the
booster reference units (default 4 each; NBLN sets the PMOS-cascode boosters,
NBLP the NMOS-cascode boosters).

--cdsl C adds C (pF) from each amplifier input (INP, INN) to the common mode: the
noise-gain load of an electrode DC-servo capacitor, whose other plate is driven
from a low impedance (B7 study). --rtau T puts a resistor T/C in series with it
(the thermal noise of an RC-shaped offset-DAC drive); with --cact A only A of the C
(the active offset-DAC bits) gets the series resistor T/A, the rest is direct.

Usage: python3 afe_bias_noise.py [--cases typical:27:2 ss:27:2:2:4 ...] [--rs 100] [--cdsl 0]
"""
import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import afe_noise

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
AFE = os.path.join(REPO, "gf180", "tapeout", "afe", "eeg_afe.spice")
BIAS = os.path.join(REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
RES_CORNER = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff", "sf": "res_typical", "fs": "res_typical"}
CAPC = {"ss": "ss", "ff": "ff"}  # MIM corner


def bcode(units):
    """Booster trim code for 2/4/6/8 reference units."""
    return {2: 0, 4: 1, 6: 2, 8: 3}[units]


def deck(corner, temp, code, rs, afe=AFE, nbln=4, nblp=4, cdsl=0.0, rtau=0.0, cact=None):
    t = afe_noise.deck(1, 256, "A", rs, 0.85, 2.15)
    for line in ("VBN VBN 0 0.8485\n", "VBCM VBCM 0 0.82\n", "VNC VNC 0 2.2\n", "VPC VPC 0 0.85\n"):
        assert line in t, line
        t = t.replace(line, "")
    t = re.sub(r"^XDUT .*gf180_ccia_local_feedback$",
               "XDUT VINP VINN WP WN INP INN OPI ONI OUTP OUTN CM VBN VBCM BLP BLN VBP CIA NCIA CIB NCIB "
               "CDA NCDA CDB NCDB VDD 0 eeg_afe_amp\n"
               "VRP VREFP 0 1.9\nVRN VREFN 0 1.4\nVITST ITST 0 1\nXB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCMX VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0 VDD 0 eeg_bias\nXDQ IQ IQ 0 0 nfet_03v3 W=4u L=2u nf=1 m=8\n"
               f"VIB1 IB1 0 {3.3 * ((code >> 1) & 1)}\nVIB0 IB0 0 {3.3 * (code & 1)}\n"
               f"VBP1 BP1 0 {3.3 * ((bcode(nbln) >> 1) & 1)}\nVBP0 BP0 0 {3.3 * (bcode(nbln) & 1)}\n"
               f"VBN1 BN1 0 {3.3 * ((bcode(nblp) >> 1) & 1)}\nVBN0 BN0 0 {3.3 * (bcode(nblp) & 1)}", t, flags=re.M)
    t = t.replace(f".lib {afe_noise.PDK}/sm141064.ngspice typical",
                  f".lib {afe_noise.PDK}/sm141064.ngspice {corner}\n"
                  f".lib {afe_noise.PDK}/sm141064.ngspice {RES_CORNER[corner]}\n"
                  f".lib {afe_noise.PDK}/sm141064.ngspice mimcap_{CAPC.get(corner, 'typical')}\n"
                  f".lib {afe_noise.PDK}/sm141064.ngspice cap_mim")
    t = t.replace(".include cand.spice", f".include {afe}\n.include {BIAS}")
    t = t.replace(".temp 27", f".temp {temp}")
    t = t.replace("print i(vdd) v(vbp) v(opi) v(oni) v(inp)",
                  "print i(vdd) v(vbp) v(opi) v(oni) v(inp) v(vbn) v(vbcm) @m.xb.xmn1.m0[id]")
    # initial guess for the bias block (the beta multiplier also has a zero-current state)
    t = t.replace(".control", ".nodeset v(xb.g1)=0.85 v(xb.gp)=2.2 v(vbn)=0.84 v(vbcm)=0.81 v(xb.nt)=0.84\n"
                  "+ v(xb.nc)=0.81 v(xb.nd)=0.8 v(xb.sb)=0 v(bln)=1.1 v(blp)=1.5 v(xb.s2)=0.05\n.control", 1)
    if cdsl and rtau:
        ca = cdsl if cact is None else cact
        r = rtau / (ca * 1e-12)
        extra = ""
        if ca < cdsl:
            extra = f"CDSLP INP CM {cdsl - ca:g}p\nCDSLN INN CM {cdsl - ca:g}p\n"
        t = t.replace("\nXDUT ", f"\n{extra}CACTP INP DSP {ca:g}p\nRDSLP DSP CM {r:.6g}\n"
                      f"CACTN INN DSN {ca:g}p\nRDSLN DSN CM {r:.6g}\nXDUT ", 1)
        assert "RDSLP" in t
    elif cdsl:
        t = t.replace("\nXDUT ", f"\nCDSLP INP CM {cdsl:g}p\nCDSLN INN CM {cdsl:g}p\nXDUT ", 1)
        assert "CDSLP" in t
    assert "eeg_bias" in t and f".temp {temp}" in t
    return t


def run(case, rs, afe=AFE, tag="", cdsl=0.0, rtau=0.0, cact=None):
    corner, temp, code, nbln, nblp = (list(case) + [4, 4])[:5]
    d = os.path.join(HERE, "runs", f"biased{tag}_{corner}_{temp}_{code}_n{nbln}_p{nblp}_rs{rs:g}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(deck(corner, temp, code, rs, afe, nbln, nblp, cdsl, rtau, cact))
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    if re.search(r"stepping failed|Transient op", log):
        return case, None, log
    res = afe_noise.analyze(d, log, 128e3)
    v = {k: float(x) for k, x in re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}
    res["i0"] = v.get("@m.xb.xmn1.m0[id]", float("nan"))
    res["vbn"] = v.get("v(vbn)", float("nan"))
    return case, res, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=[
        "typical:27:2", "ss:27:2", "ff:27:2", "sf:27:2", "fs:27:2", "typical:-20:2", "typical:85:2",
        "ss:27:3", "ss:85:3", "ff:85:2"])
    ap.add_argument("--rs", type=float, default=afe_noise.RS)
    ap.add_argument("--afe", default=AFE, help="AFE netlist (default: the written eeg_afe.spice)")
    ap.add_argument("--cdsl", type=float, default=0.0, help="pF from INP/INN to CM (DC-servo capacitor)")
    ap.add_argument("--rtau", type=float, default=0.0, help="series resistor = rtau / C (s)")
    ap.add_argument("--cact", type=float, default=None, help="pF of the C that has the series resistor")
    a = ap.parse_args()
    tag = "" if a.afe == AFE else "_" + os.path.splitext(os.path.basename(a.afe))[0]
    if a.cdsl:
        tag += (f"_cdsl{a.cdsl:g}p" + (f"_rtau{a.rtau * 1e9:g}n" if a.rtau else "")
                + (f"_cact{a.cact:g}p" if a.cact is not None else ""))
    afe_noise.BOOST = "tr"
    cases = [tuple([c.split(":")[0]] + [int(x) for x in c.split(":")[1:]]) for c in a.cases]
    print("| corner | T (C) | code | booster units P/N | I0 (uA) | AFE IDD (mA) | chopped gain | thermal | 1/f | "
          "total (nVrms) | min margin (V) | margins |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    with ThreadPoolExecutor(6) as ex:
        for case, r, log in ex.map(lambda c: run(c, a.rs, a.afe, tag, a.cdsl, a.rtau, a.cact), cases):
            corner, temp, code, nbln, nblp = (list(case) + [4, 4])[:5]
            if r is None:
                print(f"| {corner} | {temp} | {code} | {nbln}/{nblp} | operating point failed | | | | | | | |")
                continue
            t = r["total"]
            worst = min(r["sat"].items(), key=lambda kv: kv[1])
            allm = " ".join(f"{k[1:]} {v:.2f}" for k, v in r["sat"].items())
            print(f"| {corner} | {temp} | {code} | {nbln}/{nblp} | {r['i0']*1e6:.1f} | {r['idd_mA']:.2f} | {r['gain_chop']:.1f} | "
                  f"{t[1]:.2f} | {t[2]:.2f} | {(t[1]**2 + t[2]**2)**0.5:.2f} | {worst[1]:.2f} ({worst[0]}) | {allm} |",
                  flush=True)


if __name__ == "__main__":
    main()
