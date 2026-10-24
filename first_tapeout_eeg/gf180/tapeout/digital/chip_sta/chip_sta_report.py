#!/usr/bin/env python3
"""Tables of the chip-level STA (run_chip_sta.sh): <dir>/<corner>/summary.txt and the
port reports -> <dir>/report.md (and stdout). Usage: chip_sta_report.py <dir>

Times are from the MCLK edge at the pad (MCLK_PAD), in ns. Checks derived here:
  * TH: worst setup slack of the 31 TH inputs of eeg_adc_dig (2-cycle path, e0 -> e2)
  * blocks: setup / hold slack of TH_CAPTURE, DAC_LOAD, DWA_EN, RST_N (eeg_adc_dig) and
    CODE (eeg_digital_top), MCLK skew between the two macros' pins
  * DAC1: SEL1 (changes at e3) must be at the DAC1 latches before DAC_CLK (rises at e4)
    opens them: T + DAC_CLK(min) - SEL1(max)
  * blanking: CHOP_BLANK rises 1 MCLK before each CHOP_OUT edge and falls BLANK_LEN = 7
    MCLK after it: T + CHOP_OUT(min) - CHOP_BLANK(max) and 7 T + CHOP_BLANK(min) - CHOP_OUT(max)
  * slews at the analog receivers (30-70 % values of the libraries, as reported)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
B = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "f2_f3")
T = 30.5
CORNERS = [f"{rc}_{pv}" for pv in ("ss_125C_3v00", "tt_025C_3v30", "ff_n40C_3v60") for rc in ("max", "nom", "min")]


def parse_summary(c):
    d = {"clock": {}, "endpoint": {}, "analog": {}}
    with open(os.path.join(B, c, "summary.txt")) as f:
        for line in f:
            w = line.split()
            if w[0] == "clock":
                d["clock"][w[1]] = {"max": float(w[4]), "min": float(w[6]), "slew": float(w[9])}
            elif w[0] == "endpoint":
                d["endpoint"][w[1]] = {"setup": float(w[3]), "hold": float(w[5]) if w[5] != "inf" else float("inf"),
                                       "amax": float(w[8]), "amin": float(w[10]), "slew": float(w[13])}
            elif w[0] == "analog":
                d["analog"][w[1]] = {"max": float(w[4]), "min": float(w[6]), "slew": float(w[9])}
            elif w[0] == "worst":
                d["worst"] = (float(w[2]), float(w[4]))
    return d


def parse_ports(c, kind):
    """{port: (arrival, slew at the port)} from report_checks -to <port>."""
    out = {}
    txt = open(os.path.join(B, c, f"ports_{kind}.rpt")).read()
    for blk in txt.split("Startpoint:")[1:]:
        m = re.search(r"Endpoint: (\S+) \(output port", blk)
        if not m:
            continue
        port = m.group(1)
        mo = re.search(r"^\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+[v^] " + re.escape(port) + r" \(out\)", blk, re.M)
        ma = re.search(r"([\d.]+)\s+data arrival time", blk)
        if mo and ma:
            out[port] = (float(ma.group(1)), float(mo.group(1)))
    return out


def main():
    rows = []
    for c in CORNERS:
        s = parse_summary(c)
        pm, pn = parse_ports(c, "max"), parse_ports(c, "min")
        ep = s["endpoint"]
        th = [v for k, v in ep.items() if k.startswith("u_adc/TH[")]
        blk = {k.split("/")[1]: v for k, v in ep.items() if not k.startswith("u_adc/TH[")}
        sel1 = [pm[p][0] for p in pm if p.startswith("SEL1_")]
        sel2 = [pm[p][0] for p in pm if p.startswith("SEL2_")]
        sel2n = [pn[p][0] for p in pn if p.startswith("SEL2_")]
        r = {"corner": c, "worst": s["worst"],
             "mclk_top": s["clock"]["u_top/MCLK"], "mclk_adc": s["clock"]["u_adc/MCLK"],
             "th_setup": min(v["setup"] for v in th), "th_amax": max(v["amax"] for v in th),
             "blk_setup": min(v["setup"] for v in blk.values()), "blk_hold": min(v["hold"] for v in blk.values()),
             "blk": blk, "strobe": s["analog"]["u_q/CK"],
             "dac1": T + pn["DAC_CLK"][0] - max(sel1), "sel1_max": max(sel1), "dacclk": (pn["DAC_CLK"][0], pm["DAC_CLK"][0]),
             "sel2": (min(sel2n), max(sel2)),
             "blank_rise": T + pn["CHOP_OUT"][0] - pm["CHOP_BLANK"][0],
             "blank_fall": 7 * T + pn["CHOP_BLANK"][0] - pm["CHOP_OUT"][0],
             "slew": {p: pm[p][1] for p in ("CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP1", "CHOP_EN", "AFE_RST",
                                              "DAC_CLK", "ADC_ZERO")},
             "arr": {p: (pn[p][0], pm[p][0]) for p in ("CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP1", "DAC_CLK")},
             "sel_slew": max(pm[p][1] for p in pm if p.startswith("SEL"))}
        rows.append(r)

    L = [f"# Chip-level STA of the digital interface (run_chip_sta.sh, {os.path.basename(B)})", "",
         "Times in ns from the MCLK edge at the pad. Corner = macro timing model corner "
         "(min / nom / max RC of the macros) with the chip wiring of the same name "
         "(coupling counted 0 / 1 / 2 times).", "",
         "| corner | MCLK at top / adc (max) | TH setup (worst of 31) | blocks setup / hold "
         "| CMP_STROBE at the quantizer: arrival max, slew | DAC1: SEL1 before DAC_CLK | SEL2 arrival min..max "
         "| blanking margin rise / fall |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['corner']} | {r['mclk_top']['max']:.2f} / "
                 f"{r['mclk_adc']['max']:.2f} | {r['th_setup']:+.2f} (TH by {r['th_amax']:.1f}) | "
                 f"{r['blk_setup']:+.2f} / {r['blk_hold']:+.2f} | {r['strobe']['max']:.2f}, {r['strobe']['slew']:.2f} | "
                 f"{r['dac1']:+.2f} | {r['sel2'][0]:.2f}..{r['sel2'][1]:.2f} | {r['blank_rise']:+.2f} / {r['blank_fall']:+.1f} |")
    L += ["", "Slews (max, 30-70 %) and arrival (min..max) at the analog receivers:", "",
          "| corner | " + " | ".join(rows[0]["slew"]) + " | SEL (max) |", "|---" * (len(rows[0]["slew"]) + 2) + "|"]
    for r in rows:
        L.append(f"| {r['corner']} | " + " | ".join(f"{v:.1f}" for v in r["slew"].values()) + f" | {r['sel_slew']:.1f} |")
    L += ["", "| corner | " + " | ".join(rows[0]["arr"]) + " |", "|---" * (len(rows[0]["arr"]) + 1) + "|"]
    for r in rows:
        L.append(f"| {r['corner']} | " + " | ".join(f"{a:.1f}..{b:.1f}" for a, b in r["arr"].values()) + " |")
    L += ["", "Endpoints between the blocks (setup / hold slack):", "",
          "| corner | " + " | ".join(sorted(rows[0]["blk"])) + " |", "|---" * (len(rows[0]["blk"]) + 1) + "|"]
    for r in rows:
        L.append(f"| {r['corner']} | " + " | ".join(f"{r['blk'][k]['setup']:+.1f} / {r['blk'][k]['hold']:+.1f}"
                                                    for k in sorted(r["blk"])) + " |")
    txt = "\n".join(L) + "\n"
    with open(os.path.join(B, "report.md"), "w") as f:
        f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
