#!/usr/bin/env python3
"""batch_screen.py <mutants.py> <nworkers> <out> [names...]: screen mutants in per-worker copies (mut/w<k>/), restoring
the pristine RTL before each, the shared generated inputs copied from the baseline build. Benches per edited file
(screen.py); the first DETECTED stops a mutant. One result line per mutant in <out>."""
import os, runpy, shutil, subprocess, sys, threading, queue
AC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python"
muts = runpy.run_path(sys.argv[1])["MUTANTS"]
nw = int(sys.argv[2]); out = sys.argv[3]
names = sys.argv[4:] or list(muts)
WBASE = int(os.environ.get("WBASE", "0"))
BASE_BUILD = os.path.join(AC, "gf180/tapeout/rtl_r14/build")
SHARED = ("top_r14.codes", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes", "ovl.split", "reg_tests.svh", "pin_tests.svh")
RTLF = {"eeg_digital_top.sv": "gf180/tapeout/rtl_r14", "eeg_regs.sv": "gf180/tapeout/rtl_r14",
        "eeg_spi_slave.sv": "gf180/tapeout/rtl_r14", "eeg_fifo.sv": "gf180/tapeout/rtl_r14",
        "eeg_seq.sv": "gf180/tapeout/rtl_r14", "eeg_ovl.sv": "gf180/tapeout/rtl_r14",
        "eeg_cic3.sv": "gf180/tapeout/rtl_r14", "eeg_clkgen.sv": "gf180/tapeout/rtl_r14",
        "eeg_chop1.sv": "gf180/tapeout/rtl", "eeg_raw.sv": "gf180/tapeout/rtl", "eeg_rnd_sat.sv": "gf180/tapeout/rtl"}
PLAN = {"eeg_seq.sv": ["seq", "top"], "eeg_fifo.sv": ["fifo", "top"], "eeg_ovl.sv": ["ovl", "top"],
        "eeg_cic3.sv": ["cic", "top"], "eeg_clkgen.sv": ["tick", "top"], "eeg_chop1.sv": ["tick", "top"],
        "eeg_regs.sv": ["struct", "regs", "top", "spi"], "eeg_spi_slave.sv": ["struct", "top", "spi"],
        "eeg_digital_top.sv": ["struct", "top", "spi"], "eeg_raw.sv": ["struct", "top"], "eeg_rnd_sat.sv": ["top"]}
def setup(k):
    d = os.path.join(AC, "mut", f"w{k}")
    if not os.path.exists(os.path.join(d, "gf180/tapeout/rtl_r14/run_tests_r14.sh")):
        subprocess.run([PY, os.path.join(AC, "tools/mkmut.py"), os.path.join(AC, "tools/none.py"), f"w{k}"], check=True,
                       capture_output=True)
    return d
open(os.path.join(AC, "tools/none.py"), "w").write("MUTANTS = {" + ",".join(f"'w{k}': []" for k in range(8)) + "}\n")
q = queue.Queue()
for n in names: q.put(n)
lock = threading.Lock()
def worker(k):
    d = setup(k)
    while True:
        try: n = q.get_nowait()
        except queue.Empty: return
        for f, sub in RTLF.items():
            shutil.copy(os.path.join(AC, sub, f), os.path.join(d, sub, f))
        b = os.path.join(d, "gf180/tapeout/rtl_r14/build")
        shutil.rmtree(b, ignore_errors=True); os.makedirs(b)
        for x in SHARED: shutil.copy(os.path.join(BASE_BUILD, x), os.path.join(b, x))
        res = None; files = []
        for rel, old, new in muts[n]:
            p = os.path.join(d, rel); t = open(p, encoding="utf-8").read()
            if t.count(old) != 1: res = f"NOT APPLIED ({t.count(old)})"; break
            open(p, "w", encoding="utf-8").write(t.replace(old, new)); files.append(os.path.basename(rel))
        if res is None:
            benches = []
            for f in files:
                for bb in PLAN[f]:
                    if bb not in benches: benches.append(bb)
            r = subprocess.run([PY, os.path.join(AC, "tools/screen.py"), d] + benches, capture_output=True, text=True)
            lines = [l for l in r.stdout.splitlines() if l.strip()]
            res = " | ".join(l.split(": ", 1)[1] if ": " in l else l for l in lines)[:3000] or ("CRASH " + r.stderr[-200:])
        with lock, open(out, "a") as fo:
            fo.write(f"{n}: {res}\n")
ts = [threading.Thread(target=worker, args=(WBASE + k,)) for k in range(nw)]
for t in ts: t.start()
for t in ts: t.join()
print("done")
