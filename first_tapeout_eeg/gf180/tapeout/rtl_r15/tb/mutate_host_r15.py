#!/usr/bin/env python3
"""mutate_host_r15.py - the host model's own mutation self-test (VER-06, 11/28): RTL errors that the model procedure of
5.4 must notice, each compiled into the two-chip board (tb/tb_host_r15.sv) in a copy of the sources and run through
tb/host_r15.py; every mutant must FAIL it and the copy without an edit must PASS. The edits are mutate_top_r15.py's
(by their exact names) and one of this file's own.

usage: mutate_host_r15.py [-j N] [--out DIR]
"""
import argparse
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import mutate_top_r15 as MT  # noqa: E402

PY = sys.executable
CATALOG = {m[0]: m for lst in (MT.MUTATIONS, MT.SEQ_MUTATIONS, MT.REGS_MUTATIONS, MT.FIFO_MUTATIONS, MT.SPI_MUTATIONS,
                              MT.R15_MUTATIONS) for m in lst}
OWN = [
    ("シーケンサ：IDLE の外の START に STATE_ERR を立てない", "eeg_seq.sv",
     "                end else begin\n                    a_serr = 1'b1;\n                end\n            end else if (is_apply || is_nr) begin",
     "                end else begin\n                    a_serr = 1'b0;\n                end\n            end else if (is_apply || is_nr) begin"),
]
PICK = [  # (name, the host model's check expected to catch it)
    ("（基準：変更なし）", "none: must pass"),
    ("最上位：SOFT_RESET で SEQ を戻す", "step 5 (i) after chip 1's SOFT_RESET"),
    ("最上位：SOFT_RESET でフレームの計数とチョッパを戻す", "step 5 (ii) after chip 1's SOFT_RESET"),
    ("レジスタ：nr_ok が 2 段を許す", "APPLY_NR of two steps: CFG_ERR"),
    ("SPI：書き込みの CRC を検査しない", "the MOSI fault: CRC_ERR and the setting written again"),
    ("最上位：CHANGED が 1 個少ない（2 ＋ T_ELEC）", "3 CHANGED samples after every APPLY_NR"),
    ("SPI：完了したフレームのあとのビットを無視する", "8 more SCLK: no pop, FRAME_ERR (SEQ gap / drop rule)"),
    ("シーケンサ：IDLE の外の START に STATE_ERR を立てない", "START in RUN: STATE_ERR"),
]
RTL = ["eeg_digital_top.sv", "eeg_seq.sv", "eeg_regs.sv", "eeg_spi_slave.sv", "eeg_fifo.sv", "eeg_ovl.sv", "eeg_cic3.sv",
       "eeg_clkgen.sv"]
OLD = ["eeg_chop1.sv", "eeg_raw.sv", "eeg_rnd_sat.sv"]


def run_one(k, name, catcher, out):
    m = CATALOG.get(name) or next(x for x in OWN if x[0] == name)
    d = os.path.join(out, f"h{k:02d}")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(os.path.join(d, "rtl_r15", "tb"))
    os.makedirs(os.path.join(d, "rtl_r15", "spec"))
    os.makedirs(os.path.join(d, "rtl"))
    for f in RTL:
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, "rtl_r15", f))
    for f in OLD:
        shutil.copy(os.path.join(ROOT, "..", "rtl", f), os.path.join(d, "rtl", f))
    shutil.copy(os.path.join(ROOT, "spec", "eeg_regs_defs.svh"), os.path.join(d, "rtl_r15", "spec"))
    shutil.copy(os.path.join(HERE, "tb_host_r15.sv"), os.path.join(d, "rtl_r15", "tb"))
    for f, old, new in MT.edits_of(m):
        p = os.path.join(d, "rtl_r15", f)
        t = open(p).read()
        if t.count(old) != 1:
            return k, name, catcher, "TOOL ERROR", f"the edit's text is in {f} {t.count(old)} times"
        open(p, "w").write(t.replace(old, new))
    r = os.path.join(d, "rtl_r15")
    vvp = os.path.join(d, "tb_host_r15.vvp")
    comp = subprocess.run(["iverilog", "-g2012", "-I", "spec", "-I", "tb", "-o", vvp] + RTL +
                          [f"../rtl/{f}" for f in OLD] + ["tb/tb_host_r15.sv"], cwd=r, capture_output=True, text=True)
    if comp.returncode != 0:
        return k, name, catcher, "TOOL ERROR", "compile: " + comp.stderr.strip().splitlines()[-1]
    t0 = time.time()
    p = subprocess.run([PY, os.path.join(HERE, "host_r15.py"), "--vvp", vvp, "--out", d], capture_output=True,
                       text=True, timeout=5400)
    tail = [ln for ln in p.stdout.splitlines() if ln.startswith("FAIL") or ln.startswith("PASS")]
    verdict = "PASS" if p.returncode == 0 and any(ln.startswith("PASS: host_r15") for ln in tail) else "FAIL"
    first = next((ln for ln in tail if ln.startswith("FAIL:") and "host_r15" not in ln), tail[-1] if tail else "")
    return k, name, catcher, verdict, f"{first} ({time.time() - t0:.0f} s)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "host_r15_mut"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    res = []
    with cf.ThreadPoolExecutor(a.j) as ex:
        futs = [ex.submit(run_one, k, n, c, a.out) for k, (n, c) in enumerate(PICK)]
        for f in cf.as_completed(futs):
            r = f.result()
            res.append(r)
            print(f"{r[3]:10s} h{r[0]:02d} {r[1]}  [{r[2]}]  {r[4]}", flush=True)
    res.sort()
    base_ok = res[0][3] == "PASS"
    det = [r for r in res[1:] if r[3] == "FAIL"]
    tool = [r for r in res if r[3] == "TOOL ERROR"]
    print(f"--- {len(det)} of {len(res) - 1} mutants detected by host_r15.py; the copy without an edit "
          f"{'passes' if base_ok else 'FAILS'}; {len(tool)} tool errors ({(time.time() - t0) / 60:.1f} min)")
    ok = base_ok and len(det) == len(res) - 1 and not tool
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
