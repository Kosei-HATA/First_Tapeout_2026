#!/usr/bin/env python3
"""ADC with and without parasitics (tracker D6): the transistor-level loop deck of
gf180/tapeout/sim/adc_loop/adc_deck.py (real bias, reference filter, RTL frame timing,
XSPICE DWA controller) on three versions of the ADC block eeg_adc:

  sch  the schematic gf180/tapeout/adc/eeg_adc.spice (with its 2 pF per integrator
       output that stood for the wiring until PEX);
  dev  the devices that magic extracts from the ADC layout (adc_top without its digital
       macro eeg_adc_dig), no parasitic capacitances;
  pex  dev with every extracted parasitic capacitance (pex.py adc_top, runs/adc_top_c).

The run folder gets adc_deck.py's files with the eeg_adc include swapped; out.csv has the
same columns, so gf180/tapeout/sim/e2e/tr_window.py (sine fits: loop gain, DAC1 level,
residual, O1/O2 swing and CM, AVDD) and gf180/tapeout/sim/adc_loop/analyze_tone.py apply.
The integrator nodes are saved at full resolution as well (vg.csv: I1P-I1N, O1P-O1N
around the DAC1 updates) for the settling comparison.

Usage: python3 gf180/tapeout/pex/pex_adc.py <variant> [adc_deck.py options, e.g. --tstop 100e-6 --fsig 20e3]
Then: (cd gf180/tapeout/pex/runs/adc/<variant>... && ngspice -b circuit.spice)
      python3 gf180/tapeout/pex/pex_adc.py settle <run folder> ...   (VG disturbance at the DAC1 updates)
      python3 gf180/tapeout/pex/pex_adc.py codes <run folder> ...    (quantizer decisions vs ideal thresholds)
"""
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
ADC_LOOP = os.path.join(REPO, "gf180", "tapeout", "sim", "adc_loop")
SCH = os.path.join(REPO, "gf180", "tapeout", "adc", "eeg_adc.spice")
_REV = os.environ.get("EEG_PEX_REV", "")              # pex.py: the extraction of a changed layout
PEXDIR = os.path.join(HERE, "runs", "adc_top_c" + (f"_{_REV}" if _REV else ""))


def settling(folder, t0=20e-6):
    """Virtual-ground disturbance of the first integrator at each DAC1 update (DAC_CLK
    rising, e4): the differential I1P - I1N relative to its value just before the edge,
    its largest excursion and what is left 50 / 100 / 200 / 500 ns later (averages of the
    magnitudes over the frames of the window)."""
    x = np.loadtxt(os.path.join(folder, "vg.csv"))
    t, vg, o1, clk = x[:, 0], x[:, 1] - x[:, 3], x[:, 5] - x[:, 7], x[:, 9]
    up = np.flatnonzero((clk[:-1] < 1.65) & (clk[1:] >= 1.65))
    edges = [t[i] for i in up if t[i] > t0 and t[i] + 0.6e-6 < t[-1]]
    pk, rest = [], {d: [] for d in (50e-9, 100e-9, 200e-9, 500e-9)}
    for te in edges:
        v0 = np.interp(te - 2e-9, t, vg)
        m = (t >= te) & (t <= te + 300e-9)
        pk.append(np.abs(vg[m] - v0).max())
        for d in rest:
            rest[d].append(abs(np.interp(te + d, t, vg) - v0))
    return dict(n=len(edges), peak=np.mean(pk), peak_max=np.max(pk),
                **{f"at{int(d * 1e9)}ns": np.mean(v) for d, v in rest.items()},
                vg_rms=np.std(vg[t > t0]))


def codes(folder, t0=20e-6):
    """The quantizer's decisions in the loop: O2P - O2N at each strobe edge (CMP_STROBE
    rises at TS0 + k T) quantized with the ideal thresholds (k - 15) x 3.125 mV, against
    the code the loop used (the DAC1 level norm1 at mid-frame after the load at
    T0_LOAD + k T: code = 31 - number of thresholds below O2). Returns the share of
    frames that agree, the mean difference (LSB) and the best common offset of the
    thresholds (mV) with its agreement."""
    T, TS0, T0L = 1 / 1.024e6, 1.9866597656e-06, 2.0784625e-06
    x = np.loadtxt(os.path.join(folder, "out.csv"))
    t, o2, n1 = x[:, 0], x[:, 11] - x[:, 13], x[:, 19]
    ks = np.arange(int(np.ceil((t0 - TS0) / T)), int((t[-1] - T0L) / T) - 1)
    act = np.rint((np.interp(T0L + (ks + 0.5) * T, t, n1) + 0.5) * 31).astype(int)
    o2s = np.interp(TS0 + ks * T, t, o2)
    th = (np.arange(31) - 15) * 3.125e-3
    ideal = lambda off: 31 - (o2s[:, None] > th[None, :] + off).sum(1)
    best = max(((np.mean(act == ideal(o)), o) for o in np.arange(-10e-3, 10.01e-3, 0.1e-3)))
    return dict(n=len(ks), agree=np.mean(act == ideal(0.0)), diff=np.mean(act - ideal(0.0)),
                best_off=best[1], best_agree=best[0], o2min=o2s.min(), o2max=o2s.max())


def main():
    if sys.argv[1] == "codes":
        print("| DUT | frames | agree with ideal thresholds | mean code - ideal (LSB) | best common offset (mV): agree "
              "| O2 at the strobes (mV) |")
        print("|---|---|---|---|---|---|")
        for f in sys.argv[2:]:
            r = codes(f)
            print(f"| {os.path.basename(f.rstrip('/'))} | {r['n']} | {r['agree'] * 100:.1f} % | {r['diff']:+.2f} | "
                  f"{r['best_off'] * 1e3:+.1f}: {r['best_agree'] * 100:.1f} % | {r['o2min'] * 1e3:.1f}..{r['o2max'] * 1e3:.1f} |")
        return
    if sys.argv[1] == "settle":
        print("| DUT | DAC1 updates | VG peak, mean (uV) | VG peak, max (uV) | after 50 ns | 100 ns | 200 ns | 500 ns "
              "| VG rms (uV) |")
        print("|---|---|---|---|---|---|---|---|---|")
        for f in sys.argv[2:]:
            r = settling(f)
            print(f"| {os.path.basename(f.rstrip('/'))} | {r['n']} | {r['peak'] * 1e6:.1f} | {r['peak_max'] * 1e6:.1f} | "
                  f"{r['at50ns'] * 1e6:.1f} | {r['at100ns'] * 1e6:.1f} | {r['at200ns'] * 1e6:.1f} | {r['at500ns'] * 1e6:.1f} | "
                  f"{r['vg_rms'] * 1e6:.1f} |")
        return
    variant, rest = sys.argv[1], sys.argv[2:]
    tag = "_".join(a.lstrip("-") for a in rest) or "default"
    out = os.path.join(HERE, "runs", "adc", f"{variant}_{tag}")
    subprocess.run([sys.executable, os.path.join(ADC_LOOP, "adc_deck.py"), out] + rest, check=True, cwd=ADC_LOOP)
    path = os.path.join(out, "circuit.spice")
    txt = open(path).read()
    if variant != "sch":
        assert txt.count(f".include {SCH}\n") == 1
        txt = txt.replace(f".include {SCH}\n", f".include {os.path.join(PEXDIR, f'eeg_adc_{variant}.spice')}\n")
    # integrator nodes at full resolution for the settling comparison
    txt = txt.replace("linearize\n", "wrdata vg.csv v(xadc.i1p) v(xadc.i1n) v(xadc.o1p) v(xadc.o1n) v(dac_clk)\nlinearize\n", 1)
    txt = txt.replace("save time ", "save time v(xadc.i1p) v(xadc.i1n) v(dac_clk) ", 1)
    open(path, "w").write(txt)
    print(f"wrote {out}/circuit.spice ({variant})")


if __name__ == "__main__":
    main()
