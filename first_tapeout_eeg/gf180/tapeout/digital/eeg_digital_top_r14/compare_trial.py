#!/usr/bin/env python3
"""The r14 area trial (11/19) against the r13 macro: LibreLane's metrics of each run side by side.

Runs: the r13 macro's 11/19 rerun (../eeg_digital_top/runs/f2_rerun_20261119, identical to f2, the chip's macro) and the
r14 trials in runs/ (t14_h700_20261119: the r13 outline 440 x 700 um; t14_h900_20261119: 440 x 900 um) and the r14 macro
(config.yaml, 440 x 900 um with the clean-up settings; run tag r14m1_20261119, or $R14_TAG). A run that did not finish is
read from the metrics of its last step that has them (and said so).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/digital/eeg_digital_top_r14/compare_trial.py
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = [("r13 macro (f2 rerun)", os.path.join(HERE, "..", "eeg_digital_top", "runs", "f2_rerun_20261119")),
        ("r14, 440 x 700", os.path.join(HERE, "runs", "t14_h700_20261119")),
        ("r14, 440 x 900", os.path.join(HERE, "runs", "t14_h900_20261119")),
        ("r14 macro (config.yaml)", os.path.join(HERE, "runs", os.environ.get("R14_TAG", "r14m1_20261119")))]

ROWS = [
    ("die area (um^2)", "design__die__area", "{:,.0f}"),
    ("core area (um^2)", "design__core__area", "{:,.0f}"),
    ("standard cells (um^2, no fill)", "design__instance__area__stdcell", "{:,.0f}"),
    ("  sequential", "design__instance__area__class:sequential_cell", "{:,.0f}"),
    ("  combinational", "design__instance__area__class:multi_input_combinational_cell", "{:,.0f}"),
    ("  timing repair buffers", "design__instance__area__class:timing_repair_buffer", "{:,.0f}"),
    ("  clock buffers and inverters", ("design__instance__area__class:clock_buffer",
                                       "design__instance__area__class:clock_inverter"), "{:,.0f}"),
    ("  taps and endcaps", ("design__instance__area__class:tap_cell", "design__instance__area__class:endcap_cell"),
     "{:,.0f}"),
    ("utilization (standard cells / core)", "design__instance__utilization__stdcell", "{:.1%}"),
    ("flip-flops", "design__instance__count__class:sequential_cell", "{:,.0f}"),
    ("cells (no fill, taps, endcaps)", None, "{:,.0f}"),
    ("setup WS max_ss_125C_3v00 (ns)", "timing__setup__ws__corner:max_ss_125C_3v00", "{:.3f}"),
    ("setup WS nom_tt_025C_3v30 (ns)", "timing__setup__ws__corner:nom_tt_025C_3v30", "{:.3f}"),
    ("hold WS min_ff_n40C_3v60 (ns)", "timing__hold__ws__corner:min_ff_n40C_3v60", "{:.3f}"),
    ("setup violations (all corners)", "timing__setup_vio__count", "{:,.0f}"),
    ("hold violations (all corners)", "timing__hold_vio__count", "{:,.0f}"),
    ("max slew / cap / fanout violations", ("design__max_slew_violation__count", "design__max_cap_violation__count",
                                            "design__max_fanout_violation__count"), "{:,.0f}"),
    ("routing DRC errors", "route__drc_errors", "{:,.0f}"),
    ("antenna violating nets", "antenna__violating__nets", "{:,.0f}"),
    ("routed wire length (um)", "route__wirelength", "{:,.0f}"),
    ("Magic DRC errors", "magic__drc_error__count", "{:,.0f}"),
    ("KLayout DRC errors", "klayout__drc_error__count", "{:,.0f}"),
    ("LVS errors", "design__lvs_error__count", "{:,.0f}"),
]


def metrics(run):
    f = os.path.join(run, "final", "metrics.json")
    if os.path.exists(f):
        return json.load(open(f)), "finished"
    steps = sorted(glob.glob(os.path.join(run, "*", "state_out.json")))
    for s in reversed(steps):
        m = json.load(open(s)).get("metrics") or {}
        if m:
            return m, "stopped after " + os.path.basename(os.path.dirname(s))
    return {}, "no metrics"


def value(m, key):
    if key is None:
        n = m.get("design__instance__count__stdcell")
        if n is None:
            return None
        for c in ("tap_cell", "endcap_cell"):
            n -= m.get(f"design__instance__count__class:{c}", 0)
        return n
    if isinstance(key, tuple):
        vs = [m.get(k) for k in key]
        return None if all(v is None for v in vs) else sum(v or 0 for v in vs)
    return m.get(key)


def main():
    cols = [(name,) + metrics(run) for name, run in RUNS]
    w0 = max(len(r[0]) for r in ROWS) + 2
    print(" " * w0 + "".join(f"{c[0][:23]:>24s}" for c in cols))
    print(" " * w0 + "".join(f"{c[2][:23]:>24s}" for c in cols))
    for label, key, fmt in ROWS:
        line = f"{label:<{w0}s}"
        for _, m, _ in cols:
            v = value(m, key)
            line += f"{(fmt.format(v) if v is not None else '-'):>24s}"
        print(line)


if __name__ == "__main__":
    main()
