#!/usr/bin/env python3
"""Noise folding by the output-chopper blanking of the AFE (tracker A6, chopper
artifacts).

During each blanking (BLANK_LEN MCLK after every chopper edge, plus 1 MCLK before it,
256 kHz) the output TGs are open and OUTP/OUTN are held on 30 pF (discharging into the
ADC's RIN). The output therefore carries a sample of the amplifier's wideband noise,
taken every 3.9 us, instead of the noise itself for that part of the time. Wideband
noise folds into the band that way; the frozen-phase noise analysis (afe_noise.py)
cannot see it.

Method: the chopped transient of afe_offset.py (eeg_afe with the ideal clocks, offset
DAC off, RS 100 ohm per leg, load --rload and 4 pF), with a white noise of --en V/rtHz
(ngspice trnoise, --nt sample step, smoothed at 30 MHz) in series with each input of
the amplifier core, i.e. an input-referred amplifier noise. One deck holds two copies
of the AFE on the same noise sources (global nodes NZP/NZN) and the same input-chopper
clocks: XA without blanking (the output phases follow the input phases with their 5 ns
dead time) and XB with --blank MCLK. Each has its own electrode resistors, booster
bias, clock resistors and load, so they do not interact. The outputs averaged over
every chopper period give 128 kHz sequences; their densities at low frequencies
(--fmax) are the in-band levels, and their ratio is the folding penalty for the
amplifier's white noise. The density of the difference of the two sequences is the
part the blanking changes.

The copies are needed because ngspice-46 does not repeat a trnoise realization:
neither "set rndseed" in .control, nor ".options seed", nor a .spiceinit fixes it (a
two-source test deck gave uncorrelated noise run after run, 10/22). The runs before
that compared separate runs, i.e. independent realizations, so their ratios carried
the full scatter of the density estimates (about 16 % in power each). --seed only
names the replicate.

With --pool nothing is simulated: the replicates already run with the same settings
(every --seed) are pooled. Printed: the ratio of the summed variances of the period
averages (all 0..64 kHz, where the folded noise is white), the same for the in-band
densities, the variance of the difference, and the spread of the per-replicate
ratios.

Usage: python3 afe_blank_noise.py [--en 30e-9] [--nt 3.14159265e-9] [--tstop 2.1e-3]
       [--blank 7] [--fmax 20e3] [--seed 1] [--afe <netlist>] [--rload 9375] [--pool]
"""
import argparse
import glob
import os
import subprocess
import numpy as np
import afe_chop_gain
import afe_offset

HERE = os.path.dirname(os.path.abspath(__file__))
TCH = afe_offset.TCH
T_START = 0.1e-3


def noisy_afe(afe=afe_offset.AFE):
    """eeg_afe.spice with the global noise nodes NZP/NZN in series with the core inputs"""
    txt = open(afe).read()
    old = "XAMP ELP ELN WP WN INP INN OPI ONI "
    assert txt.count(old) == 1
    return txt.replace(old, "ENZP INPX INP NZP 0 1\nENZN INNX INN NZN 0 1\n"
                            "XAMP ELP ELN WP WN INPX INNX OPI ONI ")


def deck(o, afe):
    d = afe_offset.deck(0.0, 0, 0, o.rs, o.tstop, 0.0, afe, rload=o.rload)
    na = o.en / np.sqrt(2 * o.nt)  # rms of the samples for a one-sided density en up to 1/(2 nt)
    # the trnoise samples are breakpoints; driving the large core gate capacitance from
    # them directly stopped the solver where one fell next to a chopper edge, so the
    # noise is smoothed (RC at 30 MHz, far above the AFE bandwidth) and applied through
    # controlled sources
    noise = "\n".join([
        ".global NZP NZN",
        f"VNZSP NZPR 0 DC 0 TRNOISE({na:.6e} {o.nt:g} 0 0)", "RNZP NZPR NZP 1k", "CNZP NZP 0 5.3p",
        f"VNZSN NZNR 0 DC 0 TRNOISE({na:.6e} {o.nt:g} 0 0)", "RNZN NZNR NZN 1k", "CNZN NZN 0 5.3p"])
    i0 = d.index("+ OFPH ")
    pins = d[i0:d.index("\n", i0)].replace("+ OFPH ", "+ OFPH2 ", 1)
    ao, bo = afe_chop_gain.clocks(TCH, o.blank / 32.768e6)
    second = "\n".join([
        f"* the same AFE with blanking {o.blank} MCLK (XB), on the same noise and input clocks",
        "IBLP2 BLP2 0 125u", "IBLN2 VDD BLN2 125u", "RGRST2 RST_D RST2 10",
        f"RSP2 SRC_P ELP2 {o.rs:g}", f"RSN2 SRC_N ELN2 {o.rs:g}",
        "CLOADP2 OUTP2 0 4p", "CLOADN2 OUTN2 0 4p", f"RLOADP2 OUTP2 CM {o.rload:g}", f"RLOADN2 OUTN2 CM {o.rload:g}",
        "XB ELP2 ELN2 OUTP2 OUTN2 CM VBN VBCM BLP2 BLN2 RST2 CIA2 NCIA2 CIB2 NCIB2 CDA2 NCDA2 CDB2 NCDB2", pins,
        f"VCDA2 CDA2_D 0 PWL({ao}) r=0", "ENCDA2 NCDA2_D 0 VDD CDA2_D 1",
        f"VCDB2 CDB2_D 0 PWL({bo}) r=0", "ENCDB2 NCDB2_D 0 VDD CDB2_D 1",
        "RGCIA2 CIA_D CIA2 10", "RGNCIA2 NCIA_D NCIA2 10", "RGCIB2 CIB_D CIB2 10", "RGNCIB2 NCIB_D NCIB2 10",
        "RGCDA2 CDA2_D CDA2 10", "RGNCDA2 NCDA2_D NCDA2 10", "RGCDB2 CDB2_D CDB2 10", "RGNCDB2 NCDB2_D NCDB2 10",
        "RGOFPH2 OFPH_D OFPH2 10",
        ".nodeset v(xb.inp)=1.65 v(xb.inn)=1.65 v(xb.opi)=1.65 v(xb.oni)=1.65 v(outp2)=1.65 v(outn2)=1.65"])

    def sub(old, new):
        nonlocal d
        assert d.count(old) == 1, old
        d = d.replace(old, new)

    sub("VDD VDD 0 3.3\n", "VDD VDD 0 3.3\n" + noise + "\n")
    sub("\n.nodeset ", "\n" + second + "\n.nodeset ")
    sub("wrdata tr.csv vo va v(cda) v(cdb)", "let vo2 = v(outp2) - v(outn2)\nwrdata tr.csv vo vo2")
    return d


def folder(o, seed):
    tag = "" if o.afe == afe_offset.AFE else "_" + os.path.splitext(os.path.basename(o.afe))[0]
    tag += f"_rl{o.rload:g}" if o.rload != 9375.0 else ""
    return os.path.join(HERE, "runs", f"blank_pair{tag}_bl{o.blank}_en{o.en * 1e9:g}n_t{o.tstop * 1e3:g}m_s{seed}")


def pool(o):
    files = sorted(glob.glob(os.path.join(folder(o, "*"), "seq.npz")))
    if not files:
        raise SystemExit("no replicates found for these settings")
    v0 = v1 = vd = b0 = b1 = 0.0
    ratios = []
    for f in files:
        z = np.load(f)
        s0, s1 = z["seq0"] - z["seq0"].mean(), z["seq1"] - z["seq1"].mean()
        v0, v1, vd = v0 + s0.var(), v1 + s1.var(), vd + (s1 - s0).var()
        b0, b1 = b0 + density(s0, o.fmax)[0], b1 + density(s1, o.fmax)[0]
        ratios.append(s1.var() / s0.var())
    n = len(files)
    err = np.std(ratios, ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    print(f"blanking {o.blank} MCLK, {n} replicates of {o.tstop * 1e3:g} ms: variance ratio {v1 / v0:.4f} "
          f"(+-{err:.4f}, amplitude {np.sqrt(v1 / v0):.4f}); in-band density ratio {b1 / b0:.4f}; "
          f"difference {vd / v0:.4f} of the variance without blanking; per replicate "
          + " ".join(f"{r:.3f}" for r in ratios))


def run(o):
    d = folder(o, o.seed)
    os.makedirs(d, exist_ok=True)
    afe = os.path.join(d, "afe_noisy.spice")
    open(afe, "w").write(noisy_afe(o.afe))
    tb, cache = os.path.join(d, "tb.spice"), os.path.join(d, "seq.npz")
    text = deck(o, afe)
    if os.path.exists(cache) and os.path.exists(tb) and open(tb).read() == text:
        z = np.load(cache)
        return z["seq0"], z["seq1"]
    open(tb, "w").write(text)
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True)
    open(os.path.join(d, "run.log"), "w").write(r.stdout + r.stderr)
    x = np.loadtxt(os.path.join(d, "tr.csv"))
    os.remove(os.path.join(d, "tr.csv"))
    t = x[:, 0]
    n = int((t[-1] - T_START) / TCH)
    edges = T_START + TCH * np.arange(n + 1)
    seqs = []
    for vo in (x[:, 1], x[:, 3]):  # output averaged over each chopper period
        q = np.concatenate([[0.0], np.cumsum(0.5 * (vo[1:] + vo[:-1]) * np.diff(t))])
        seqs.append(np.diff(np.interp(edges, t, q)) / TCH)
    np.savez(cache, seq0=seqs[0], seq1=seqs[1])
    return seqs


def density(seq, fmax):
    """mean one-sided density (V^2/Hz) of the 128 kHz sequence over (1 bin .. fmax)"""
    w = np.hanning(len(seq))
    s = 2 * np.abs(np.fft.rfft((seq - seq.mean()) * w)) ** 2 / (afe_offset.FCH * np.sum(w ** 2))
    f = np.fft.rfftfreq(len(seq), TCH)
    sel = (f > f[1]) & (f <= fmax)
    return np.mean(s[sel]), int(sel.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--en", type=float, default=30e-9, help="input-referred white noise per core input (V/rtHz)")
    ap.add_argument("--nt", type=float, default=3.14159265e-9,
                    help="trnoise sample step (s); off the 1 ns grid of the clock breakpoints, which an "
                         "exact multiple hit at 250 us and stopped the solver")
    ap.add_argument("--tstop", type=float, default=2.1e-3)
    ap.add_argument("--blank", type=int, default=7, help="blanking in MCLK")
    ap.add_argument("--fmax", type=float, default=20e3)
    ap.add_argument("--rs", type=float, default=100.0)
    ap.add_argument("--seed", type=int, default=1, help="replicate label (ngspice draws new noise every run)")
    ap.add_argument("--afe", default=afe_offset.AFE, help="AFE netlist (study variants, e.g. with an output low-pass)")
    ap.add_argument("--rload", type=float, default=9375.0, help="ADC input resistor per side")
    ap.add_argument("--pool", action="store_true", help="pool the replicates already run, simulate nothing")
    o = ap.parse_args()
    if o.pool:
        pool(o)
        return
    seq0, seq1 = run(o)
    s0, nb = density(seq0, o.fmax)
    s1, _ = density(seq1, o.fmax)
    sd, _ = density(seq1 - seq0, o.fmax)
    g = afe_offset.GAIN
    print(f"input-referred core noise {o.en * 1e9:g} nV/rtHz per input, {len(seq0)} chopper periods, "
          f"{nb} bins up to {o.fmax / 1e3:g} kHz, replicate {o.seed}")
    print(f"  output density without blanking {np.sqrt(s0) * 1e9:.1f} nV/rtHz "
          f"(electrode-referred {np.sqrt(s0) / g * 1e9:.3f} nV/rtHz)")
    print(f"  with blanking {o.blank} MCLK          {np.sqrt(s1) * 1e9:.1f} nV/rtHz "
          f"(ratio {np.sqrt(s1 / s0):.4f}, power {s1 / s0:.4f}; difference of the two "
          f"{np.sqrt(sd) * 1e9:.1f} nV/rtHz, {sd / s0:.4f} of the power without blanking)")


if __name__ == "__main__":
    main()
