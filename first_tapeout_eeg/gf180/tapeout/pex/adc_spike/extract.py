#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 1: the ADC input of the two start-deck runs, copied out (read only).

The diagnostic asks whether the ADC (the sigma-delta modulator) tolerates the ADC input that the analog start deck
produced: run A (ss, 300 mV electrode offset, M 991) has a +0.64 V spike for ~90 ns after every output-chopper
blanking window; run B (typical, M 997) is the control. The start deck models the ADC only as its input resistors.

Inputs (read only): gf180/tapeout/pex/runs/startup/<RUN[tag]>/tr.csv and meta.json (afe_saturation.py --seq,
ver07_r14/run_ver07_r14_b.sh and run_ver07_r14_c.sh).
Outputs: gf180/tapeout/pex/runs/ver07_r14/adc_spike/data/<tag>.npz (from 4.7 ms on: t, qo = the deck's integ of
OUTP_ADC - OUTN_ADC on the raw points, outp_adc, outn_adc, afe_rst, vrefp_adc, vrefn_adc, opi, oni) and
<tag>_meta.json (a copy of the run's meta.json).

Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/extract.py
"""
import json
import os
import shutil

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
RUNS = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "startup")
OUT = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")
RUN = dict(
    A="start_c1e-08_v3.3_ss_+300mV_m991_afe5.00486ms_ib3_ibr3_bt10_sat6ms_rst101.563us_seq_chip_r13",
    B="start_c1e-08_v3.3_typical_+300mV_m997_afe5.00486ms_ib3_ibr3_bt10_sat6ms_rst101.563us_seq_chip_r13")
KEEP = ["qo", "outp_adc", "outn_adc", "afe_rst", "vrefp_adc", "vrefn_adc", "opi", "oni"]
T0 = 4.7e-3                                    # before t_reset (4.8 ms): the whole sequence for beh_seq.py


def main():
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    for tag, name in RUN.items():
        d = os.path.join(RUNS, name)
        meta = json.load(open(os.path.join(d, "meta.json")))
        shutil.copy(os.path.join(d, "meta.json"), os.path.join(OUT, "data", f"{tag}_meta.json"))
        vec = meta["vectors"]
        cols = [0] + [2 * vec.index(k) + 1 for k in KEEP]      # wrdata: column 2 i + 1 is vectors[i]
        x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=cols).to_numpy()
        order = sorted(cols)                                   # usecols keeps the file's column order
        arr = {("t" if c == 0 else vec[(c - 1) // 2]): x[:, order.index(c)] for c in cols}
        w = arr["t"] >= T0
        out = {k: v[w] for k, v in arr.items()}
        np.savez(os.path.join(OUT, "data", f"{tag}.npz"), **out)
        dt = np.diff(out["t"])
        print(f"{tag} {name}: {w.sum()} rows, t {out['t'][0]:.6g}..{out['t'][-1]:.6g} s, grid {dt.min():.4g}..{dt.max():.4g} s")


if __name__ == "__main__":
    main()
