#!/usr/bin/env python3
"""Build stage-2 rescale variants (orig / s10 / s47) of the independent-environment
ADC loop deck for a local transistor check: sine input 0.3 V pk at 1 kHz,
1.25 ms, DLOAD events for every clock.

Usage: python3 make_variants.py <deck_dir> <out_dir>
  deck_dir = .../ct_candidate/adc_gain10_loop_20261020/results/positive_32
Then run `ngspice -b circuit.spice` in each <out_dir>/<variant> and
`python3 analyze.py <out_dir>`. See documentation/gf180_large_resistors_20261022.md."""
import sys
import os
import re
import shutil

SRC = sys.argv[1]
OUT = sys.argv[2]
PDK = os.path.expanduser("~/.ciel/ciel/gf180mcu/versions/"
                         "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice")
T = 1 / 1.024e6
TSTOP = 1.25e-3
VARIANTS = {"orig": 1.0, "s10": 10.0, "s47": 47.6}


def events():
    lines = ["0 0s 1s", "1.054e-06 0s 0s"]
    t0 = 2.0784625e-06
    k = 0
    while t0 + k * T < TSTOP:
        t = t0 + k * T
        lines += [f"{t:.10e} 1s 0s", f"{t + 32e-9:.10e} 0s 0s"]
        k += 1
    return "\n".join(lines) + "\n"


def deck(text, s):
    text = re.sub(r"/Volumes/mukiebi/Codex/gf180_ishi_env_20261015/native_runtime/pdk/"
                  r"gf180mcuD/libs.tech/ngspice", PDK, text)
    text = re.sub(r"^VSIG .*$", "VSIG SIG 0 SIN(0 0.3 1k 1.1u)", text, flags=re.M)
    text = re.sub(r"^R21([PN]) (\S+) (\S+) 1Meg$",
                  lambda m: f"R21{m.group(1)} {m.group(2)} {m.group(3)} {1e6 / s:.6g}",
                  text, flags=re.M)
    text = re.sub(r"^RD2([PN]) (\S+) (\S+) \{320000000/3/31\}$",
                  lambda m: f"RD2{m.group(1)} {m.group(2)} {m.group(3)} {{320000000/3/31/{s}}}",
                  text, flags=re.M)
    text = re.sub(r"^C2([PN]) (\S+) (\S+) 1\.953125p$",
                  lambda m: f"C2{m.group(1)} {m.group(2)} {m.group(3)} {1.953125 * s:.6g}p",
                  text, flags=re.M)
    text = re.sub(r"^\.save .*$", "", text, flags=re.M)
    text = re.sub(r"^\.tran .*$", "", text, flags=re.M)
    text = re.sub(r"^\.end\s*$", "", text, flags=re.M)
    ctrl = f"""
.control
set noaskquit
save time v(sig) v(o1p) v(o1n) v(i1p) v(i1n) v(o2p) v(o2n) v(i2p) v(i2n) v(norm1) i(vdd_src)
tran 5n {TSTOP} 0 1e-09
wrdata out.csv v(sig) v(o1p) v(o1n) v(i1p) v(i1n) v(o2p) v(o2n) v(i2p) v(i2n) v(norm1) i(vdd_src)
quit
.endc
.end
"""
    return text + ctrl


def main():
    src = open(os.path.join(SRC, "circuit.spice")).read()
    for name, s in VARIANTS.items():
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        for f in ("otas.spice", "quantizer.spice"):
            shutil.copy(os.path.join(SRC, f), d)
        open(os.path.join(d, "events.txt"), "w").write(events())
        txt = deck(src, s)
        for key in ("R21P", "RD2P", "C2P"):
            assert re.search(rf"^{key} .*", txt, re.M), key
        open(os.path.join(d, "circuit.spice"), "w").write(txt)
        print(name, [l for l in txt.splitlines() if re.match(r"^(R21P|RD2P|C2P|VSIG) ", l)])


if __name__ == "__main__":
    main()
