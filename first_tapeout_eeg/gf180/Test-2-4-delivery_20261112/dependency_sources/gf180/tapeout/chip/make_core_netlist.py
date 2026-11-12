#!/usr/bin/env python3
"""Write the chip core netlist gf180/tapeout/chip/eeg_core.spice (tracker E7): every block
inside the padring and how the blocks connect, for the chip-level LVS of the layout
(gf180/tapeout/layout/chip_lay.py) and for chip-level simulation.

Blocks (each from its own netlist):
  eeg_afe        AFE (gf180/tapeout/afe/eeg_afe.spice)
  eeg_afe_clk    its clock driver (gf180/tapeout/afe/eeg_afe_clk.spice), on AVDD_CLK /
                 AVSS_CLK: 100 ohm (ppolyf_u_1k 2 x 20 um) from AVDD / AVSS each, and the
                 105 pF decoupling under offdac_n's MIMs (10 cap_nmos_03v3 28.6 x 92 um)
  eeg_adc        ADC (gf180/tapeout/adc/eeg_adc.spice)
  eeg_adc_dig    the ADC-side digital block (LibreLane macro, gate-level CDL)
  eeg_digital_top  the digital block (LibreLane macro, gate-level CDL)
  eeg_bias       bias generator (gf180/tapeout/bias/eeg_bias.spice); its VCM divider
                 makes the chip's VCM, which also goes to the VCM pad
  eeg_ref        reference filter between the VREFP / VREFN pads and the ADC
  eeg_testmux    analog test multiplexer to the ATP pad: AFE outputs (codes 12/13), ADC
                 stage-2 outputs O2P / O2N (14/15), bias and reference nodes
  decoupling     MOS capacitors AVDD-AVSS beside the AFE and ADC supply trunks (Ch-A) and
                 DVDD-DVSS beside the digital block (documentation/gf180_test_decap_20261022.md)

Digital-to-analog connections: TEST_CFG[4:0] -> test mux, TEST_CFG[5] -> ADC_ZERO,
TEST_CFG[7:6] (DBG_SEL) unused outside the digital block; CPF_TRIM -> AFE CPF0..3;
AFE_IBIAS -> bias IB1/IB0, BTRIM_P -> BP1/BP0, BTRIM_N -> BN1/BN0; OFM / OFS / OFEN ->
offset DAC; CHOP CHOP_OUT CHOP_BLANK CHOP_EN AFE_RST -> AFE clock driver; AFE_RST also
resets the ADC integrators; CHOP1 CMP_STROBE DAC_CLK -> ADC.

Ports of eeg_core (pad nets): ELP ELN (two pads each), VCM, VREFP_PAD, VREFN_PAD, ATP,
the digital pad signals MCLK RESET_N SCLK CS_N MOSI (pad to core) and MISO MISO_OE
DRDY_N RAW_DATA RAW_CLK (core to pad), AVDD AVSS (three pads each), DVDD DVSS (ring).
The substrate joins AVSS, AVSS_CLK and DVSS (one p-substrate; separate metal).

Usage: python3 gf180/tapeout/chip/make_core_netlist.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TAPEOUT = os.path.dirname(HERE)
GDS = os.path.join(TAPEOUT, "layout", "gds")
OUT = os.path.join(HERE, "eeg_core.spice")

# decoupling (cap_nmos_03v3 units; the layout's arrays, chip_lay.py)
DECAP_UNIT = (28.6, 44.0)        # c_length x c_width um, about 5.3 pF each
N_DECAP_A = 75                   # AVDD-AVSS in Ch-A under the trunks (about 400 pF; 72 before the
                                 # AFE of 10/24 moved the Metal4 supply jumpers that rows avoid)
N_DECAP_D = 48                   # DVDD-DVSS above the digital block (about 250 pF)


def cdl_ports(path, name):
    txt = open(path).read()
    m = re.search(rf"^\.SUBCKT {name} (.*?)$((?:\n\+.*$)*)", txt, re.M | re.I)
    words = (m.group(1) + " " + m.group(2).replace("\n+", " ")).split()
    return words


def bus(words, net):
    """Map a macro's port list to chip nets: net(port) -> chip net name."""
    return " ".join(net(w) for w in words)


def main():
    afe_ofs = " ".join([f"OFM{k}" for k in range(10)] + [f"OFEN{k}" for k in range(4)])
    sel1 = " ".join(f"SEL1_{k}" for k in range(31))
    sel2 = " ".join(f"SEL2_{k}" for k in range(31))
    th = " ".join(f"TH{k}" for k in range(31))
    dig_map = {"VDD": "DVDD", "VSS": "DVSS", "AFE_IBIAS[0]": "IB0", "AFE_IBIAS[1]": "IB1",
               "BTRIM_N[0]": "BN0", "BTRIM_N[1]": "BN1", "BTRIM_P[0]": "BP0", "BTRIM_P[1]": "BP1",
               "TEST_CFG[5]": "ADC_ZERO", "TEST_CFG[6]": "DBG_SEL0", "TEST_CFG[7]": "DBG_SEL1"}

    def dig_net(w):
        if w in dig_map:
            return dig_map[w]
        m = re.match(r"(\w+)\[(\d+)\]$", w)
        if m:
            base, k = m.groups()
            return {"CODE": "CODE", "CPF_TRIM": "CPF", "OFEN": "OFEN", "OFM": "OFM", "TEST_CFG": "TC"}[base] + k
        return w

    def adig_net(w):
        if w in ("VDD", "VSS"):
            return "D" + w
        if w == "RST_N":
            return "ADC_RST_N"
        m = re.match(r"(\w+)\[(\d+)\]$", w)
        if m:
            base, k = m.groups()
            return {"CODE": "CODE", "SEL1": "SEL1_", "SEL2": "SEL2_", "TH": "TH"}[base] + k
        return w
    dig = cdl_ports(os.path.join(GDS, "eeg_digital_top.cdl"), "eeg_digital_top")
    adig = cdl_ports(os.path.join(GDS, "eeg_adc_dig.cdl"), "eeg_adc_dig")
    cl, cw = DECAP_UNIT
    L = ["* eeg_core: the chip core of the GF180 EEG ADC (this rev), written by make_core_netlist.py",
         "* (do not edit). Blocks, their connections and the pad nets: see the script's doc string.",
         ".subckt eeg_core ELP ELN VCM VREFP_PAD VREFN_PAD ATP MCLK RESET_N SCLK CS_N MOSI MISO",
         "+ MISO_OE DRDY_N RAW_DATA RAW_CLK AVDD AVSS DVDD DVSS",
         "* AFE, its clock driver and the driver's supply",
         "XAFE ELP ELN OUTP OUTN VCM VBN VBCM BLP BLN RSTA CIA NCIA CIB NCIB CDA NCDA CDB NCDB",
         f"+ OFPH OFS {afe_ofs} CPF0 CPF1 CPF2 CPF3 AVDD AVSS eeg_afe",
         "XACLK CHOP CHOP_OUT CHOP_BLANK CHOP_EN AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RSTA",
         "+ AVDD_CLK AVSS_CLK eeg_afe_clk",
         "XRCKP AVDD_CLK AVDD AVSS ppolyf_u_1k r_length=2u r_width=20u",
         "XRCKN AVSS_CLK AVSS AVSS ppolyf_u_1k r_length=2u r_width=20u"]
    L += [f"XDCK{k} AVDD_CLK AVSS_CLK cap_nmos_03v3 c_length=28.6u c_width=92u" for k in range(10)]
    L += ["* ADC and its digital block",
          "XADC OUTP OUTN CHOP1 DAC_CLK CMP_STROBE AFE_RST ADC_ZERO",
          f"+ {sel1}", f"+ {sel2}", f"+ {th}",
          "+ VREFP VREFN VCM VBN1 VNC1 VPC1 VBCM1 VBPC2 VBNC2 IDP IDN IQ O2P O2N AVDD AVSS DVDD DVSS eeg_adc",
          f"XADIG {bus(adig, adig_net)} eeg_adc_dig",
          "* digital block",
          f"XDIG {bus(dig, dig_net)} eeg_digital_top",
          "* bias, references, test multiplexer",
          "XBIAS VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM VREFP VREFN IB1 IB0 BP1 BP0",
          "+ BN1 BN0 AVDD AVSS eeg_bias",
          "XREF VREFP_PAD VREFN_PAD VREFP VREFN AVSS eeg_ref",
          "XTM ATP TC0 TC1 TC2 TC3 TC4 VCM VREFP VREFN VBN VBCM VBN1 VNC1 VPC1 VBPC2 VBNC2 ITST OUTP OUTN O2P O2N",
          "+ AVDD AVSS eeg_testmux",
          f"* decoupling: {N_DECAP_A} x AVDD-AVSS, {N_DECAP_D} x DVDD-DVSS ({cl} x {cw} um cap_nmos_03v3)"]
    L += [f"XDCA{k} AVDD AVSS cap_nmos_03v3 c_length={cl}u c_width={cw}u" for k in range(N_DECAP_A)]
    L += [f"XDCD{k} DVDD DVSS cap_nmos_03v3 c_length={cl}u c_width={cw}u" for k in range(N_DECAP_D)]
    L += [".ends eeg_core", ""]
    open(OUT, "w").write("\n".join(L))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
