#!/usr/bin/env python3
"""VER-07 diagnostic of 11/22, step 7: the key numbers of the spike diagnostic, from the result files of wave.py,
beh_spike.py, beh_seq.py and xan.py (each part is skipped if its file is missing).

Inputs: runs/ver07_r14/adc_spike/wave.json, beh_spike.json, beh_seq.json, beh_sweep.json, xrun_*/xan.json.
Output: runs/ver07_r14/adc_spike/summary.json (also printed; ver07_spike_fig.py reads it).
Usage: nice -n 10 gf180/tools/venv310/bin/python -B gf180/tapeout/pex/adc_spike/summary.py
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, "gf180", "tapeout", "pex", "runs", "ver07_r14", "adc_spike")


def get(name):
    p = os.path.join(OUT, name)
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    s = {}
    wv = get("wave.json")
    if wv:
        for tag, r in wv.items():
            s[f"input_{tag}"] = dict(mean_mv=r["mean_qo_mv"], range_mv=(r["min_mv"], r["max_mv"]),
                                     chopper_means_mv=(r["chopper_means_mv"]["first"], r["chopper_means_mv"]["last"]),
                                     clip_mean_mv=r["mean_clip_mv"], above_fs_ns=r["above_fs_ns_per_segment"],
                                     above_fs_mvus=r["above_fs_mvus_per_segment"],
                                     peak_mv=max(x["peak_mv"] for x in r["spike"]),
                                     spike_area_mvus=float(np.mean([x["area_above_pre_mvus"] for x in r["spike"]])),
                                     pre_step_mv=float(np.mean([x["pre_step_mv"] for x in r["spike"]])),
                                     samples_rms_mv=r["check"]["samples_rms_mv"])
    bs = get("beh_spike.json")
    if bs:
        R = {(x["tag"], x["variant"]): x for x in bs["results"]}
        for (tag, var), x in R.items():
            dd = x["dies"]
            ss = next(q for q in dd if q["die"].startswith("MOS ss"))
            ty = next(q for q in dd if q["die"].startswith("MOS typical"))
            s[f"beh_{tag}_{var}"] = dict(
                input_mean_mv=x["input_mean_mv"], input_range_mv=(x["input_min_mv"], x["input_max_mv"]),
                ss=dict(o1_mv=ss["o1_peak_mv"], o2_mv=ss["o2_peak_mv"], o2_strobes_mv=ss["o2_peak_strobe_mv"],
                        codes=(ss["code_min"], ss["code_max"]), data_minus_input_uv=ss["data_minus_input_uv"],
                        tau1_us=ss["tau1_us"], vfs_mv=ss["vfs_mv"]),
                typical=dict(o1_mv=ty["o1_peak_mv"], o2_mv=ty["o2_peak_mv"], codes=(ty["code_min"], ty["code_max"]),
                             data_minus_input_uv=ty["data_minus_input_uv"]),
                all=dict(dies=len(dd), o1_mv=max(q["o1_peak_mv"] for q in dd), o2_mv=max(q["o2_peak_mv"] for q in dd),
                         o2_strobes_mv=max(q["o2_peak_strobe_mv"] for q in dd),
                         codes=(min(q["code_min"] for q in dd), max(q["code_max"] for q in dd)),
                         rail_codes=sum(q["rail_codes"] for q in dd), beyond_thresholds=sum(q["o2_beyond_thresholds"] for q in dd),
                         clip_clocks=sum(q["clip_clocks"] for q in dd), onebit=sum(q["onebit"] for q in dd),
                         data_minus_input_uv=(min(q["data_minus_input_uv"] for q in dd), max(q["data_minus_input_uv"] for q in dd))))
        for tag in "AB":
            a, c = R[(tag, "actual")], R[(tag, "dc")]
            d = [qa["data_minus_input_uv"] - qc["data_minus_input_uv"] for qa, qc in zip(a["dies"], c["dies"])]
            s[f"beh_{tag}_actual_minus_dc_uv"] = (min(d), max(d))
        a, k = R[("A", "actual")], R[("A", "clip")]
        d = [((qa["data_mean_mv"] - qk["data_mean_mv"]) - (a["input_mean_mv"] - k["input_mean_mv"])) * 1e3
             for qa, qk in zip(a["dies"], k["dies"])]
        s["beh_A_clip"] = dict(input_change_mv=a["input_mean_mv"] - k["input_mean_mv"], data_change_minus_input_uv=(min(d), max(d)))
    sq = get("beh_seq.json")
    if sq:
        s["seq"] = {k: dict(back_after_release_us=v["back_after_release_us"], after_back=v["after_back"],
                            onebit_end=v["onebit_end"], saturated_rail_share=v["saturated"]["rail_code_share"])
                    for k, v in sq.items()}
    sw = get("beh_sweep.json")
    if sw:
        s["sweep"] = {}
        for key in (("A", "actual"), ("A", "dc"), ("B", "actual")):
            r = [x for x in sw["rows"] if (x["tag"], x["variant"]) == key]
            s["sweep"]["_".join(key)] = dict(states=sw["states"] * len(r), onebit_max=max(x["onebit_share"] for x in r),
                                             not_back_max=max(x["not_back_share"] for x in r),
                                             slowest_us=max(x["t_max_us"] or 0 for x in r))
    for d in sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []:
        x = get(os.path.join(d, "xan.json")) if d.startswith("xrun_") else None
        if x:
            s[d] = dict(settle_us=x["settle_us"], o1_mv=x["o1_peak_mv"], o2_mv=x["o2_peak_mv"],
                        o2_strobes_mv=x["o2_at_strobes_peak_mv"], vg1_mv=x["vg1_peak_mv"],
                        vg1_outside_spikes_mv=x["vg1_peak_outside_spikes_mv"], vg2_mv=x["vg2_peak_mv"],
                        codes_dac_elements=x["codes_dac_elements"], rail_codes=x["rail_codes"],
                        o1cm_v=x["o1cm_range_v"], vg1cm_v=x["vg1cm_range_v"], spikes=len(x["spikes"]),
                        o1_step_mv=(min(q["o1_step_mv"] for q in x["spikes"]), max(q["o1_step_mv"] for q in x["spikes"])),
                        beh_spike_clock_o1_diff_mv=(min(b["spike_clock_o1_maxdiff_mv"] for b in x["beh"]),
                                                    max(b["spike_clock_o1_maxdiff_mv"] for b in x["beh"])))
    json.dump(s, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    for k, v in s.items():
        print(f"{k}: {json.dumps(v)}")


if __name__ == "__main__":
    main()
