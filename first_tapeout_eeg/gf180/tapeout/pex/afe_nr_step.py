#!/usr/bin/env python3
"""APPLY_NR's one offset-DAC step without AFE_RST, at the sequencer's tick, in RUN (audit of 11/20, round 10, A1).

A +-1 step of the offset DAC's magnitude M that crosses a binary carry (e.g. 511 -> 512) switches many bits at once:
a bit that turns off is pulled down through its clamp at once, a bit that turns on charges through its resistor
(about 65 ns), so the input's virtual ground sees the off-going units for a moment. The static analysis behind
APPLY_NR (the residual of one step, about 0.31 mV, against the AFE's saturation at about 4 mV) does not cover this
transient. This deck measures it: afe_startup.py's start deck (power-on, pads, board, bond wires, eeg_bias / eeg_ref /
afe_top extracted on the chip wiring, the RTL's sequence) with the DAC on from power-on at the code --m1 (the
electrode offset --vin in series with the electrodes, as afe_startup), released as the new sequencer releases AFE_RST
(at its tick, as afe_saturation.py --seq), and at --t-step the DAC's lines switch from --m1 to --m2 at the tick of
the frame in the middle of chopper phase A (frame cycle 24, the register outputs at e25), with no AFE_RST pulse and
the blanking unchanged (15 MCLK: the DAC is on). The lines that turn on rise and the lines that turn off fall at the
same instant (both are register outputs of the same edge).

Compare a step that crosses a carry (511 -> 512: 10 bits) with one that does not (510 -> 511: 1 bit) at the same
range and offset: the difference is the carry's transient. Output: afe_startup.py's run folder (tr.csv on a 100 ns
grid, run.log, meta.json with t_step, m1, m2 and the lines switched), tagged _nr<m1>to<m2>.

Usage: EEG_PEX_REV=r13 gf180/tools/venv310/bin/python gf180/tapeout/pex/afe_nr_step.py --vin 159.1 --m1 511 --m2 512
           [--t-step 6.5e-3] [--tstop 9.5e-3] [--corner ss] [--zp '100+51k|47n'] [--ibias 3]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import afe_startup as A  # noqa: E402
import pex_afe as P  # noqa: E402

OFM = re.compile(r"OFM(\d)_[NP]$")


def patch(text, t_step, m1, m2):
    """the deck (DAC lines set for m1 by afe_startup) with the magnitude lines that differ between m1 and m2 switched
    at t_step: a line that turns on to DACW (rises), one that turns off to DACWN (falls); (text, lines switched)"""
    lines = text.split("\n")
    i = next(k for k, s in enumerate(lines) if s.startswith("XDUT "))
    toks = lines[i].split()
    ports = P.ports()
    assert len(toks) == len(ports) + 2, (len(toks), len(ports))
    n = 0
    for k, port in enumerate(ports):
        m = OFM.match(port)
        if not m:
            continue
        b = int(m.group(1))
        b1, b2 = (m1 >> b) & 1, (m2 >> b) & 1
        assert toks[k + 1] == ("DVDDC" if b1 else "DVSSC"), (port, toks[k + 1], b1)
        if b1 != b2:
            toks[k + 1] = "DACW" if b2 else "DACWN"
            n += 1
    lines[i] = " ".join(toks)
    lines.insert(i + 1, f"VUDACW UDACW 0 PWL(0 0 {t_step:.9e} 0 {t_step + 2e-9:.9e} 1)\n"
                        f"BDACW DACW 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(UDACW)\n"
                        f"BDACWN DACWN 0 V=v(DVSSC)+v(DVDDC,DVSSC)*(1-v(UDACW))")
    return "\n".join(lines), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vin", type=float, required=True, help="electrode DC offset (mV), present from power-on; its "
                    "magnitude also picks the DAC's range as afe_startup does (159.1 mV: range 4)")
    ap.add_argument("--m1", type=int, required=True, help="the DAC code from power-on")
    ap.add_argument("--m2", type=int, required=True, help="the code after the step (APPLY_NR: m1 +- 1)")
    ap.add_argument("--t-step", type=float, default=6.5e-3, help="the step (s; moved to the tick of a period)")
    ap.add_argument("--tstop", type=float, default=None, help="default t-step + 3 ms (CHANGED: 3 outputs + T_ELEC)")
    ap.add_argument("--corner", default="typical", choices=list(A.MOSF))
    ap.add_argument("--vdd", type=float, default=3.3)
    ap.add_argument("--ibias", type=int, default=3, choices=range(4))
    ap.add_argument("--cvcm", default="10n")
    ap.add_argument("--zp", default="100", help="ELP leg (afe_startup's), e.g. 100+51k|47n")
    ap.add_argument("--zn", default="100", help="ELN leg")
    ap.add_argument("--tag", default=None, help="default _nr<m1>to<m2>_chip_<rev>")
    ap.add_argument("--ibias-reset", type=int, default=2, choices=range(4), help="afe_startup's (r14: 3)")
    ap.add_argument("--btrim-p", type=int, default=1, choices=range(4), help="afe_startup's (r14: 1)")
    ap.add_argument("--btrim-n", type=int, default=1, choices=range(4), help="afe_startup's (r14: 0)")
    ap.add_argument("--range", type=int, default=None, choices=range(1, 5), help="afe_startup's")
    s = ap.parse_args()
    if abs(s.m2 - s.m1) != 1:
        sys.exit("--m1 / --m2: APPLY_NR's step is one code")
    rev = os.environ.get("EEG_PEX_REV", "")
    sys.path.insert(0, os.path.join(HERE, "..", "rtl", "spec"))
    import fsm_spec as FS
    t_reset = 5e-3 - 0.2e-3
    r = FS.TIMING["rates"]["128k"]
    phase = (r["tick_frame"] * FS.FRAME + FS.TIMING["tick_cycle"] + 1) / FS.MCLK          # after the phase-A edge
    assert abs(r["period_frames"] * FS.FRAME / FS.MCLK - P.TCH) < 1e-15
    t_afe = t_reset + 26 * P.TCH + phase                     # the first tick after 0.2 ms (as afe_saturation --seq)
    t_step = t_reset + round((s.t_step - t_reset - phase) / P.TCH) * P.TCH + phase
    tstop = s.tstop if s.tstop else t_step + 3e-3
    tag = s.tag if s.tag is not None else f"_nr{s.m1}to{s.m2}" + (f"_chip_{rev}" if rev else "_chip")
    print(f"first release {t_afe * 1e3:.6f} ms, step {s.m1} -> {s.m2} at {t_step * 1e3:.6f} ms "
          f"({phase * 1e9:.1f} ns after a phase-A edge), tstop {tstop * 1e3:.3f} ms", flush=True)
    args = ["start", "--vin", f"{s.vin:g}", "--corner", s.corner, "--vdd", f"{s.vdd:g}", "--ibias", str(s.ibias),
            "--cvcm", s.cvcm, "--tstop", f"{tstop:.9e}", "--jobs", "1", "--tag", tag, "--zp", s.zp, "--zn", s.zn,
            "--t-afe", f"{t_afe:.9e}", "--t-reset", f"{t_reset:.9e}", "--dac-mag", str(s.m1),
            "--ibias-reset", str(s.ibias_reset), "--btrim-p", str(s.btrim_p), "--btrim-n", str(s.btrim_n)]
    if s.range:
        args += ["--range", str(s.range)]
    deck0 = A.deck
    switched = []

    def deck(a, mode, seed):
        text, n = patch(deck0(a, mode, seed), t_step, s.m1, s.m2)
        switched.append(n)
        return text

    A.deck = deck
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
        m.update(t_step=t_step, m1=s.m1, m2=s.m2, dac_lines_switched=switched[0] if switched else None,
                 apply_nr=True, afe_rst_again=None)
        json.dump(m, open(p, "w"), indent=1)
        real_print(f"{name}: step {s.m1} -> {s.m2} at {t_step * 1e3:.6f} ms, {switched[0] if switched else 0} "
                   f"DAC lines switched", flush=True)


if __name__ == "__main__":
    main()
