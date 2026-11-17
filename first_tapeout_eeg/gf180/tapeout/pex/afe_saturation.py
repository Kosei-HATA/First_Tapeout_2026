#!/usr/bin/env python3
"""The first power-on with an electrode DC offset, as the host procedure runs it (gf180_electrode_dc_20261022.md,
"使い方"): AFE_RST is released with the offset DAC off, so an offset beyond about 4 mV saturates the AFE; the host reads
the output, then writes the DAC's range and magnitude M together with BLANK = 15 MCLK, and the AFE has to come out of
saturation. afe_startup.py's start deck (power-on, pads, board, bond wires, eeg_bias / eeg_ref / afe_top extracted on
the chip wiring, the RTL's sequence, AFE_IBIAS written to --ibias) with one change: the DAC's register lines (OFS, OFM*,
OFEN* of both halves) sit at DVSS (DAC off, range 0) and the blanking at 7 MCLK until --t-dac, where the lines that the
final code sets go to DVDD and the blanking to 15 MCLK. The write lands in the middle of a chopper half period (clear of
the edges and the blanking); the final code is afe_startup's (--vin, --dac-mag). Output: afe_startup.py's run folder
(tr.csv on a 100 ns grid, run.log, meta.json with t_dac added), tagged _sat<t_dac in ms>.

With --rst-pulse (11/16): the host then re-asserts AFE_RST (CONTROL[4]) for that long and releases it again at the
chopper phase of the first release (t_afe + n TCH, the first such time --rst-gap after the write plus the pulse): the
AFE restarts from its reset with the DAC already on, as figure 27's runs start (the ADC's integrators are reset by
AFE_RST too, which this bench does not model). Tagged _sat<ms>_rst<pulse in us>us; tstop defaults to the re-release
+ 1.5 ms.

The ADC is afe_startup's: its input resistors into a virtual ground that follows its VCM pin, so this shows the AFE
alone; the ADC's own overload is a separate check (adc_overload.py).

11/18: --zp / --zn, the electrodes' impedances (afe_startup's; the offset sits in series with them). --chop-hold:
CHOP_EN low whenever AFE_RST is high (CONTROL[5] and [4] in the same write: the host clears CHOP_EN as it raises
AFE_RST and sets it as it releases; at power-on as if CONTROL's reset value had CHOP_EN 0), so the input chopper
stays in phase A while the amplifier is held. While held with the chopper running, the pins look like the chopped
input capacitors alone, about 5.4 kohm differential (cmrr.py's runs, 4.8-5.0 ms), and an electrode's offset charges
its capacitance. Tagged _chophold. Without these options the deck is the same as before.

Usage: EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/afe_saturation.py --vin 30 --dac-mag 100
           [--t-dac 6e-3] [--tstop 8e-3] [--corner ss] [--vdd 3.135] [--ibias 3] [--rst-pulse 20e-6 [--rst-gap 20e-6]]
           [--zp '100+51k|47n'] [--chop-hold]
"""
import argparse
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import afe_startup as A  # noqa: E402
import pex_afe as P  # noqa: E402

OF = re.compile(r"OF(S|M\d|EN\d)_[NP]$")


def patch(text, t_dac, rst=None, chop_hold=False):
    """the deck with the DAC's lines and the blanking switched at t_dac, and with rst = (t_on, t_off) AFE_RST
    re-asserted from t_on to t_off; with chop_hold, CHOP_EN low whenever AFE_RST is high; (text, number of lines
    switched)"""
    lines = text.split("\n")
    i = next(k for k, s in enumerate(lines) if s.startswith("XDUT "))
    toks = lines[i].split()
    ports = P.ports()
    assert len(toks) == len(ports) + 2, (len(toks), len(ports))
    n = 0
    for k, port in enumerate(ports):
        if OF.match(port) and toks[k + 1] == "DVDDC":
            toks[k + 1] = "DACW"
            n += 1
    lines[i] = " ".join(toks)
    j = next(k for k, s in enumerate(lines) if s.startswith("VUBLK UBLK 0 PULSE("))
    v = lines[j][len("VUBLK UBLK 0 PULSE("):].rstrip(")").split()        # v1 v2 td tr tf pw per
    pw15 = float(v[5])
    assert abs(pw15 - (16 * P.MCLK - 0.5e-9)) < 1e-12, pw15                 # the deck has the DAC's 15 MCLK
    pw7 = pw15 - 8 * P.MCLK
    lines[j] = (f"VUBLK7 UBLK7 0 PULSE({' '.join(v[:5])} {pw7:.9e} {v[6]})\n"
                f"VUBLK15 UBLK15 0 PULSE({' '.join(v[:5])} {pw15:.9e} {v[6]})\n"
                f"VUDACW UDACW 0 PWL(0 0 {t_dac:.9e} 0 {t_dac + 2e-9:.9e} 1)\n"
                f"BUBLK UBLK 0 V=v(UBLK7)*(1-v(UDACW))+v(UBLK15)*v(UDACW)\n"
                f"BDACW DACW 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(UDACW)")
    if rst:
        k = next(k for k, s in enumerate(lines) if s.startswith("VURST URST 0 PWL("))
        v = lines[k][len("VURST URST 0 PWL("):].rstrip(")").split()
        assert len(v) == 6 and v[5] == "0", lines[k]                          # 1 until the release, then 0
        lines[k] = (f"VURST URST 0 PWL({' '.join(v)} {rst[0]:.9e} 0 {rst[0] + 2e-9:.9e} 1 {rst[1]:.9e} 1 "
                    f"{rst[1] + 2e-9:.9e} 0)")
    if chop_hold:
        old = "BCHEN CHOP_EN 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(ONE)"
        k = lines.index(old)
        lines[k] = "BCHEN CHOP_EN 0 V=v(DVSSC)+v(DVDDC,DVSSC)*(1-v(URST))"
    return "\n".join(lines), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vin", type=float, required=True, help="electrode DC offset (mV), present from power-on")
    ap.add_argument("--dac-mag", type=int, default=None, help="the code M the host writes (default round(|vin| / step))")
    ap.add_argument("--t-dac", type=float, default=6e-3, help="the host's write (s; moved to the middle of a half period)")
    ap.add_argument("--tstop", type=float, default=None, help="default t-dac + 2 ms")
    ap.add_argument("--corner", default="typical", choices=list(A.MOSF))
    ap.add_argument("--vdd", type=float, default=3.3)
    ap.add_argument("--mc", type=int, default=None)
    ap.add_argument("--ibias", type=int, default=3, choices=range(4))
    ap.add_argument("--cvcm", default="10n")
    ap.add_argument("--tag", default=None, help="default _sat<t_dac ms>[_rst<us>us]_chip_<rev>")
    ap.add_argument("--rst-pulse", type=float, default=0.0, help="AFE_RST re-asserted for this long after the write (s)")
    ap.add_argument("--rst-gap", type=float, default=20e-6, help="from the write to the re-assertion, at least (s)")
    ap.add_argument("--zp", default="100", help="ELP leg (afe_startup's), e.g. 100+51k|47n")
    ap.add_argument("--zn", default="100", help="ELN leg")
    ap.add_argument("--chop-hold", action="store_true", help="CHOP_EN low whenever AFE_RST is high")
    s = ap.parse_args()
    if not s.vin:
        sys.exit("--vin: an offset is the point")
    rev = os.environ.get("EEG_PEX_REV", "")
    t_reset = 5e-3 - 0.2e-3
    half = P.TCH / 2
    t_dac = t_reset + (round((s.t_dac - t_reset) / half - 0.5) + 0.5) * half
    rst = None
    if s.rst_pulse:
        t_afe = 5e-3
        n = int(np.ceil((t_dac + s.rst_gap + s.rst_pulse - t_afe) / P.TCH - 1e-9))
        rst = (t_afe + n * P.TCH - s.rst_pulse, t_afe + n * P.TCH)
    tstop = s.tstop if s.tstop else (rst[1] + 1.5e-3 if rst else t_dac + 2e-3)
    tag = s.tag if s.tag is not None else (f"_sat{t_dac * 1e3:.0f}ms" + (f"_rst{s.rst_pulse * 1e6:g}us" if rst else "") +
                                           ("_chophold" if s.chop_hold else "") + (f"_chip_{rev}" if rev else "_chip"))
    args = ["start", "--vin", f"{s.vin:g}", "--corner", s.corner, "--vdd", f"{s.vdd:g}", "--ibias", str(s.ibias),
            "--cvcm", s.cvcm, "--tstop", f"{tstop:.9e}", "--jobs", "1", "--tag", tag, "--zp", s.zp, "--zn", s.zn]
    if s.dac_mag is not None:
        args += ["--dac-mag", str(s.dac_mag)]
    if s.mc is not None:
        args += ["--mc", str(s.mc)]
    deck0 = A.deck
    switched = []

    def deck(a, mode, seed):
        text, n = patch(deck0(a, mode, seed), t_dac, rst, s.chop_hold)
        switched.append(n)
        return text

    A.deck = deck
    # afe_startup's own run (folder name, meta.json, ngspice), with the patched deck
    printed = []
    real_print = print

    def capture(*x, **k):
        printed.append(" ".join(map(str, x)))
        real_print(*x, **k)

    A.print = capture
    sys.argv = ["afe_startup.py"] + args
    A.main()
    name = printed[-1].split(":")[0] if printed else None
    if name:
        p = os.path.join(A.RUNS, name, "meta.json")
        m = json.load(open(p, encoding="utf-8"))
        m.update(t_dac=t_dac, dac_lines_switched=switched[0] if switched else None, blank_before="7 MCLK", blank_after="15 MCLK",
                 afe_rst_again=list(rst) if rst else None, chop_hold=s.chop_hold)
        json.dump(m, open(p, "w"), indent=1)
        real_print(f"{name}: t_dac {t_dac * 1e3:.6f} ms, {switched[0] if switched else 0} DAC lines switched", flush=True)


if __name__ == "__main__":
    main()
