#!/usr/bin/env python3
"""11/28: the self-test of the eqy proof (run_eqy_r15.sh): netlist mutants that must each fail it.

Each mutant is r15m13's nl.v with one change (asserted to apply exactly once), run through the same flow
(EQY_NL=<mutant> run_eqy_r15.sh mut_<id>: the same RTL, liberty, match-point selection and strategies); the proof
must fail (a partition not proved) or the flow must refuse the netlist. A mutant that passes is a hole in the check.
usage: gf180/tools/venv310/bin/python mutate_eqy_r15.py [ids]   (out: work_mut_<id>/summary.txt, a table on stdout)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
NL = os.path.join(T, "layout", "gds", "r15", "eeg_digital_top.nl.v")

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
]


def main():
    ids = sys.argv[1:] or [m[0] for m in MUTANTS]
    src = open(NL).read()
    rows = []
    for mid, what, pat, rep in MUTANTS:
        if mid not in ids:
            continue
        new, n = re.subn(pat, rep, src, flags=re.S)
        assert n == 1, (mid, n)
        w = os.path.join(HERE, f"work_mut_{mid}")
        os.makedirs(w, exist_ok=True)
        path = os.path.join(w, "nl_mut.v")
        open(path, "w").write(new)
        env = dict(os.environ, EQY_NL=path)
        r = subprocess.run([os.path.join(HERE, "run_eqy_r15.sh"), f"mut_{mid}"], env=env, capture_output=True, text=True)
        out = r.stdout + r.stderr
        open(os.path.join(w, "run.out"), "w").write(out)
        failed = re.findall(r"^  (eeg_digital_top\.\S+)", out, re.M)
        passed = "DONE (PASS" in out and not failed
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
