#!/usr/bin/env python3
"""Stand-alone checks of gf180/tapeout/bias/eeg_bias.spice.

  op     master current I0 (MN1 drain current), the four AFE_IBIAS codes, VBN,
         VBCM, BLP/BLN currents, over resistor corners and temperature
  start  supply ramp 0 -> 3.3 V in 10 us: the reference must start
  --rl   overrides the length of the reference resistor (sizing)

Loads: BLN into an NMOS diode W20/L8 x4 and BLP from a PMOS diode W20/L8 x4,
as in the AFE booster mirrors; IQ into an NMOS diode W4/L2 x8, as in the
quantizer; VBN/VBCM drive gates only.

Usage: python3 bias_check.py [op|start] [--rl 2.9u]
"""
import argparse
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
BIAS = os.path.join(REPO, "gf180", "tapeout", "bias", "eeg_bias.spice")
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")


def run(name, text, bias_text=None):
    d = os.path.join(HERE, "runs", name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "tb.spice"), "w").write(text)
    if bias_text is not None:
        open(os.path.join(d, "bias.spice"), "w").write(bias_text)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(d, "run.log"), "w").write(log)
    if re.search(r"stepping failed|Transient op|aborted", log):
        raise RuntimeError(f"{name}: did not converge directly (see run.log)")
    return {k: float(v) for k, v in re.findall(r"^(\S+) = ([-0-9.e+]+)", log, re.M)}


def build(code, corner="typical", temp=27, rl=None, start=False):
    """Deck text and the (possibly resized) bias netlist."""
    ib1, ib0 = (code >> 1) & 1, code & 1
    bias = open(BIAS).read()
    if rl:
        bias = re.sub(r"(XR0 S2 VSS VSS ppolyf_u_1k r_length=)\S+", rf"\g<1>{rl}", bias)
    rcorner = {"typical": "res_typical", "ss": "res_ss", "ff": "res_ff"}.get(corner, "res_typical")
    ccorner = {"ss": "ss", "ff": "ff"}.get(corner, "typical")
    vdd = "VDD VDD 0 PWL(0 0 10u 3.3)" if start else "VDD VDD 0 3.3"
    ana = ("tran 10n 40u 0 10n\nlet ibln = i(vmbln)\nprint ibln[length(ibln)-1] v(vbn)[length(v(vbn))-1]"
           if start else "op\nprint @m.xb.xmn1.m0[id] v(vbn) v(vbcm) i(vmbln) i(vmblp) v(xb.gp) v(xb.g1) "
           "@m.xb.xmn1.m0[gm] i(vdd) v(xb.sb) @m.xb.xsu3.m0[id]\n"
           "print v(vbn1) v(vbcm1) v(vnc1) v(vpc1) v(vbpc2) v(vbnc2) i(vmidn) i(vmidp) v(vcm) i(vmiq) i(vmitst)")
    text = f"""* eeg_bias check
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
.lib {PDK}/sm141064.ngspice {rcorner}
.lib {PDK}/sm141064.ngspice mimcap_{ccorner}
.lib {PDK}/sm141064.ngspice cap_mim
.include bias.spice
.temp {temp}
.options sparse reltol=1e-5
{vdd}
VIB1 IB1 0 {3.3 * ib1}
VIB0 IB0 0 {3.3 * ib0}
VBP1 BP1 0 0
VBP0 BP0 0 3.3
VBN1 BN1 0 0
VBN0 BN0 0 3.3
VMBLN BLN BLNL 0
XLN BLNL BLNL 0 0 nfet_03v3 W=20u L=8u nf=1 m=4
VMBLP BLPL BLP 0
XLP BLPL BLPL VDD VDD pfet_03v3 W=20u L=8u nf=1 m=4
VRP VREFP 0 1.9
VRN VREFN 0 1.4
VMIDN IDN IDNL 0
XDLN IDNL IDNL 0 0 nfet_03v3 W=1u L=20u nf=1 m=10
VMIDP IDPL IDP 0
XDLP IDPL IDPL VDD VDD pfet_03v3 W=1u L=20u nf=1 m=10
VMIQ IQ IQL 0
VMITST ITST 0 1
XDQ IQL IQL 0 0 nfet_03v3 W=4u L=2u nf=1 m=8
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM VREFP VREFN IB1 IB0 BP1 BP0 BN1 BN0 VDD 0 eeg_bias
.control
set noaskquit
{ana}
quit
.endc
.end
"""
    return text, bias


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="op", choices=["op", "start"])
    ap.add_argument("--rl", default=None, help="reference resistor length, e.g. 2.9u")
    a = ap.parse_args()
    if a.mode == "start":
        for corner in ("typical", "ss", "ff"):
            text, bias = build(2, corner, 27, a.rl, start=True)
            v = run(f"start_{corner}_{a.rl}", text, bias)
            vals = list(v.values())
            print(f"start-up {corner}: BLN current {vals[0]*1e6:.1f} uA, VBN {vals[1]:.3f} V at 40 us")
        return
    print("| corner | T (C) | code | I0 (uA) | gm/Id | VBN (V) | VBCM (V) | BLN (uA) | BLP (uA) | IDD (uA) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    cases = [("typical", 27, c) for c in range(4)] + [
        (c, t, 2) for c in ("ss", "ff", "sf", "fs") for t in (27,)] + [("typical", t, 2) for t in (-20, 85)]
    for corner, temp, code in cases:
        text, bias = build(code, corner, temp, a.rl)
        v = run(f"op_{corner}_{temp}_{code}_{a.rl}", text, bias)
        i0 = v["@m.xb.xmn1.m0[id]"]
        print(f"| {corner} | {temp} | {code} | {i0*1e6:.2f} | {v['@m.xb.xmn1.m0[gm]']/i0:.1f} | {v['v(vbn)']:.4f} | "
              f"{v['v(vbcm)']:.4f} | {v['i(vmbln)']*1e6:.1f} | {v['i(vmblp)']*1e6:.1f} | {-v['i(vdd)']*1e6:.0f} | "
              f"SB {v['v(xb.sb)']:.3f} V, start-up {v['@m.xb.xsu3.m0[id]']*1e9:.1f} nA | "
              f"ADC: VBN1 {v['v(vbn1)']:.4f}, VBCM1 {v['v(vbcm1)']:.4f}, VNC1 {v['v(vnc1)']:.3f}, VPC1 {v['v(vpc1)']:.3f}, "
              f"VBPC2 {v['v(vbpc2)']:.3f}, VBNC2 {v['v(vbnc2)']:.3f}, "
              f"DAC2 ref {v['i(vmidn)']*1e9:.0f}/{v['i(vmidp)']*1e9:.0f} nA, VCM {v['v(vcm)']:.4f}, "
              f"IQ {v['i(vmiq)']*1e6:.2f} uA, ITST {v['i(vmitst)']*1e6:.2f} uA (sourced into 1 V) |",
              flush=True)


if __name__ == "__main__":
    main()
