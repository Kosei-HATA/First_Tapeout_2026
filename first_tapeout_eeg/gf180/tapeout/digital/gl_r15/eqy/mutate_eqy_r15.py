#!/usr/bin/env python3
"""11/28: the self-test of the eqy proof (run_eqy_r15.sh): netlist mutants that must each fail it.

Each mutant is r15m13's nl.v with one change (asserted to apply exactly once), run through the same flow
(EQY_NL=<mutant> run_eqy_r15.sh mut_<id>: the same RTL, liberty, match-point selection and strategies); the proof
must fail (a partition not proved) or the flow must refuse the netlist. A mutant that passes is a hole in the check.
usage: gf180/tools/venv310/bin/python mutate_eqy_r15.py [ids]   (out: work_mut_<id>/summary.txt, a table on stdout)
       ids of eeg_adc_dig's mutants start with adc_ (EQY_DESIGN=adc_dig, layout/gds/eeg_adc_dig.nl.v, 7-track cells)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
NL = {"top": os.path.join(T, "layout", "gds", "r15", "eeg_digital_top.nl.v"),
      "adc_dig": os.path.join(T, "layout", "gds", "eeg_adc_dig.nl.v")}

MUTANTS = [
    ("logic", "論理：OFS を取り込む条件の oai21 を aoi21 に（_09213_）",
     r"gf180mcu_fd_sc_mcu9t5v0__oai21_1 _09213_ ", "gf180mcu_fd_sc_mcu9t5v0__aoi21_1 _09213_ "),
    ("reset", "リセット値：TEST_CFG[5]（a_azero）のフリップフロップを 1 に set する型に（_11660_）",
     r"gf180mcu_fd_sc_mcu9t5v0__dffrnq_1 _11660_ \(\.D\(_00408_\),\n    \.RN\(",
     "gf180mcu_fd_sc_mcu9t5v0__dffsnq_1 _11660_ (.D(_00408_),\n    .SETN("),
    ("swap", "配線：FIFO の語 0 のデータの 0 と 1 ビットの D の入れ替え（_11042_、_11043_）",
     r"_11042_ \(\.D\(_00655_\),(.*?)_11043_ \(\.D\(_00656_\),",
     r"_11042_ (.D(_00656_),\1_11043_ (.D(_00655_),"),
    ("port", "出力端子：TEST_CFG[5] の出力の緩衝器を反転器に（output56）",
     r"gf180mcu_fd_sc_mcu9t5v0__clkbuf_2 output56 \(\.I\(net56\),\n    \.Z\(TEST_CFG\[5\]\)\);",
     "gf180mcu_fd_sc_mcu9t5v0__clkinv_2 output56 (.I(net56),\n    .ZN(TEST_CFG[5]));"),
    ("adc_logic", "eeg_adc_dig の論理：k_q[0] を受けるポインタの加算の xor2 を xnor2 に（_1716_）",
     r"gf180mcu_fd_sc_mcu7t5v0__xor2_1 _1716_ \(\.A1\(\\u_dwa1\.k_q\[0\] \),\n    \.A2\(_0971_\),\n    \.Z\(",
     r"gf180mcu_fd_sc_mcu7t5v0__xnor2_1 _1716_ (.A1(\\u_dwa1.k_q[0] ),\n    .A2(_0971_),\n    .ZN("),
    ("adc_reset", "eeg_adc_dig のリセット値：k_q[0] のフリップフロップを 1 に set する型に（_3004_）",
     r"gf180mcu_fd_sc_mcu7t5v0__dffrnq_1 _3004_ \(\.D\(_0101_\),\n    \.RN\(",
     "gf180mcu_fd_sc_mcu7t5v0__dffsnq_1 _3004_ (.D(_0101_),\n    .SETN("),
    ("adc_port", "eeg_adc_dig の出力端子：CODE[0] の出力の緩衝器を反転器に（output33）",
     r"gf180mcu_fd_sc_mcu7t5v0__buf_2 output33 \(\.I\(net33\),\n    \.Z\(CODE\[0\]\)\);",
     "gf180mcu_fd_sc_mcu7t5v0__inv_2 output33 (.I(net33),\n    .ZN(CODE[0]));"),
    ("adc_rot", "eeg_adc_dig の回転：DWA1 の rot_q[0] と rot_q[1] の D の入れ替え（_3014_、_3015_）",
     r"_3014_ \(\.D\(_0111_\),(.*?)_3015_ \(\.D\(_0112_\),",
     r"_3014_ (.D(_0112_),\1_3015_ (.D(_0111_),"),
]


def main():
    ids = sys.argv[1:] or [m[0] for m in MUTANTS]
    rows = []
    for mid, what, pat, rep in MUTANTS:
        if mid not in ids:
            continue
        design = "adc_dig" if mid.startswith("adc_") else "top"
        src = open(NL[design]).read()
        new, n = re.subn(pat, rep, src, flags=re.S)
        assert n == 1, (mid, n)
        w = os.path.join(HERE, f"work_mut_{mid}")
        os.makedirs(w, exist_ok=True)
        path = os.path.join(w, "nl_mut.v")
        open(path, "w").write(new)
        env = dict(os.environ, EQY_NL=path, EQY_DESIGN=design)
        if design == "top":
            r = subprocess.run([os.path.join(HERE, "run_eqy_r15.sh"), f"mut_{mid}"], env=env, capture_output=True, errors="replace",
                               text=True)
            out = r.stdout + r.stderr
            open(os.path.join(w, "run.out"), "w").write(out)
            failed = re.findall(r"^  (eeg_\w+\.\S+)", out, re.M)
            passed = "DONE (PASS" in out and not failed
        else:                           # eeg_adc_dig: the complete check is the combinational step (run_comb_step.sh)
            r = subprocess.run([os.path.join(HERE, "run_comb_step.sh"), f"mut_{mid}"], env=env, capture_output=True, errors="replace",
                               text=True)
            out = r.stdout + r.stderr
            open(os.path.join(w, "step.out"), "w").write(out)
            failed = [f"step: {x}" for x in re.findall(r"can differ: (\S+)", out)]
            passed = "STEP PASS" in out
        verdict = "survived" if passed else "detected"
        rows.append((mid, what, verdict, ", ".join(failed[:4]) or out.strip().splitlines()[-1][:80]))
        print(f"{mid}: {verdict} ({rows[-1][3]})", flush=True)
    print("| mutant | change | result | not proved |")
    print("|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    sys.exit(0 if all(r[2] == "detected" for r in rows) else 1)


if __name__ == "__main__":
    main()
