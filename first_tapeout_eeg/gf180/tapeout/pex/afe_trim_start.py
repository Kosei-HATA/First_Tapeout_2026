#!/usr/bin/env python3
"""The AFE release with the cascode-booster trim written by the firmware (11/16): afe_startup.py's start deck (power-on,
pads, board, bond wires, eeg_bias / eeg_ref / afe_top extracted on the chip wiring, the RTL's sequence, AFE_IBIAS written
to --ibias) with one change: BOOST_TRIM (BTRIM_P = BP1:BP0, BTRIM_N = BN1:BN0; codes 0..3 = 2 / 4 / 6 / 8 units, reset
value 1 / 1 = 4 / 4) goes from its reset value to --bp / --bn at the same write as AFE_IBIAS (--t-write after RESET_N),
as the corner table of gf180_afe_noise_20261022.md sets it (ss 2/2, ff 8/6, sf 8/4, fs 2/6). Output: afe_startup.py's
run folder, tagged _bt<P>-<N> (the units).

Usage: EEG_PEX_REV=r12 gf180/tools/venv310/bin/python gf180/tapeout/pex/afe_trim_start.py --corner ss --bp 0 --bn 0
           [--sine 0.943 --fsig 2000] [--vdd 3.3] [--tstop 7e-3]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import afe_startup as A  # noqa: E402

RESET = {"BP": 1, "BN": 1}
UNITS = {0: 2, 1: 4, 2: 6, 3: 8}


def patch(text, code, tw):
    """the deck with BP1/BP0/BN1/BN0 switched at tw to code {'BP': c, 'BN': c}; (text, lines switched)"""
    n = 0
    src = ""
    for reg in ("BP", "BN"):
        for b in (1, 0):
            r, x = (RESET[reg] >> b) & 1, (code[reg] >> b) & 1
            if r == x:
                continue
            old = f"B{reg}{b} {reg}{b} 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v({'ONE' if r else 'ZERO'})\n"
            assert text.count(old) == 1, old
            text = text.replace(old, f"B{reg}{b} {reg}{b} 0 V=v(DVSSC)+v(DVDDC,DVSSC)*v(UBT{reg}{b})\n")
            src += f"VUBT{reg}{b} UBT{reg}{b} 0 PWL(0 {r} {tw:.9e} {r} {tw + 2e-9:.9e} {x})\n"
            n += 1
    if src:
        anchor = "VONE ONE 0 1\n"
        assert text.count(anchor) == 1
        text = text.replace(anchor, anchor + src)
    return text, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="typical", choices=list(A.MOSF))
    ap.add_argument("--bp", type=int, required=True, choices=range(4), help="BTRIM_P code (0..3 = 2/4/6/8 units)")
    ap.add_argument("--bn", type=int, required=True, choices=range(4), help="BTRIM_N code")
    ap.add_argument("--vdd", type=float, default=3.3)
    ap.add_argument("--ibias", type=int, default=3, choices=range(4))
    ap.add_argument("--sine", type=float, default=0.943, help="mV pk from 20 us after the release")
    ap.add_argument("--fsig", type=float, default=2000.0)
    ap.add_argument("--cvcm", default="10n")
    ap.add_argument("--tstop", type=float, default=7e-3)
    ap.add_argument("--t-write", type=float, default=20e-6)
    s = ap.parse_args()
    rev = os.environ.get("EEG_PEX_REV", "")
    tag = f"_bt{UNITS[s.bp]}-{UNITS[s.bn]}" + (f"_chip_{rev}" if rev else "_chip")
    args = ["start", "--corner", s.corner, "--vdd", f"{s.vdd:g}", "--ibias", str(s.ibias), "--cvcm", s.cvcm,
            "--tstop", f"{s.tstop:g}", "--t-write", f"{s.t_write:g}", "--jobs", "1", "--tag", tag]
    if s.sine:
        args += ["--sine", f"{s.sine:g}", "--fsig", f"{s.fsig:g}"]
    code = {"BP": s.bp, "BN": s.bn}
    deck0 = A.deck
    switched = []

    def deck(a, mode, seed):
        text, n = patch(deck0(a, mode, seed), code, a.t_reset + a.t_write)
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
        m.update(boost_trim=dict(bp=s.bp, bn=s.bn, units=f"{UNITS[s.bp]}/{UNITS[s.bn]}", lines_switched=switched[0] if switched else 0))
        json.dump(m, open(p, "w"), indent=1)
        real_print(f"{name}: BOOST_TRIM {UNITS[s.bp]}/{UNITS[s.bn]}, {switched[0] if switched else 0} lines switched", flush=True)


if __name__ == "__main__":
    main()
