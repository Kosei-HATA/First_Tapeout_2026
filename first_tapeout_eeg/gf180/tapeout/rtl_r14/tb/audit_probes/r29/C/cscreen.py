#!/usr/bin/env python3
"""cscreen.py <mutants.py> <out.txt> [-j N] [names...]: screen each mutant: a copy of the sources (audit29_C, build/
inputs copied from its finished baseline), the unit benches of the edited file as run_tests_r14.sh runs them, then
tb_top_r14 (8-deep, killed at its first ERROR/FAIL line, then its two checkers) for the ones the unit benches pass.
One line per mutant: DETECTED <where> / PASSED-UNIT+TOP (needs the rest: spi, struct, top4, full run) / ERROR."""
import os, runpy, shutil, subprocess, sys, concurrent.futures as cf, pty, select
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(SP, "audit29_C")
PY = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python"
RTL = ("eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv "
       "../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv").split()
IV = ["iverilog", "-g2012", "-I", "../rtl/spec", "-I", "tb", "-I", "build"]
SHARED = ("top_r14.codes", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes", "ovl.split", "reg_tests.svh", "pin_tests.svh")
muts = runpy.run_path(sys.argv[1])["MUTANTS"]
outp = sys.argv[2]
jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 2
names = [a for a in sys.argv[3:] if a in muts] or list(muts)

def mkcopy(name):
    dst = os.path.join(SP, "mut2", name)
    shutil.rmtree(dst, ignore_errors=True)
    ign = shutil.ignore_patterns("build", "__pycache__", "audit_probes", "*.png")
    shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl_r14"), os.path.join(dst, "gf180/tapeout/rtl_r14"), ignore=ign)
    shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl"), os.path.join(dst, "gf180/tapeout/rtl"), ignore=ign)
    os.makedirs(os.path.join(dst, "gf180/tapeout/rtl_r14/build"))
    for x in SHARED:
        shutil.copy(os.path.join(BASE, "gf180/tapeout/rtl_r14/build", x), os.path.join(dst, "gf180/tapeout/rtl_r14/build", x))
    for f, old, new in muts[name]:
        p = os.path.join(dst, f)
        t = open(p, encoding="utf-8").read()
        if t.count(old) != 1:
            return None, f"NOT APPLIED ({t.count(old)})"
        open(p, "w", encoding="utf-8").write(t.replace(old, new))
    return dst, ""

def sh(d, cmd, timeout=None):
    return subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout)

def run_kill(d, cmd, log, limit=3000):
    m, sl = pty.openpty()
    p = subprocess.Popen(["nice", "-n", "5"] + cmd, cwd=d, stdout=sl, stderr=sl, close_fds=True)
    os.close(sl)
    first, buf = None, b""
    import time
    t0 = time.time()
    with open(os.path.join(d, log), "wb") as fo:
        while True:
            if time.time() - t0 > limit:
                first = "HANG (no end in %d s)" % limit; p.kill(); break
            try:
                r, _, _ = select.select([m], [], [], 5.0)
                if not r:
                    if p.poll() is not None: break
                    continue
                data = os.read(m, 65536)
            except OSError:
                break
            if not data: break
            fo.write(data); buf += data
            *lines, buf = buf.split(b"\n")
            for ln in lines:
                t = ln.decode(errors="replace").strip()
                if first is None and t.startswith(("ERROR", "SPI ERROR", "FAIL")):
                    first = t
            if first is not None:
                p.kill(); break
    p.wait(); os.close(m)
    return first

def unit(d, fn):
    r14 = d
    def ok(v, word):
        return word in v.stdout and "ERROR" not in v.stdout and "FAIL" not in v.stdout
    if fn == "eeg_seq.sv":
        c = sh(r14, IV + ["-o", "build/s.vvp", "eeg_seq.sv", "tb/tb_seq.sv"])
        if c.returncode: return "COMPILE " + c.stderr[-150:]
        v = sh(r14, ["vvp", "-n", "build/s.vvp", "+n=600000", "+seed=11", "+trace=build/seq_trace.txt"], 1800)
        k = sh(r14, [PY, "tb/check_seq_trace.py", "build/seq_trace.txt"])
        if not ok(v, "PASS: tb_seq") or k.returncode: return "tb_seq: " + ((k.stdout.splitlines() or ["?"])[0] if ok(v, "PASS") else next((l for l in v.stdout.splitlines() if l.startswith(("ERROR", "FAIL"))), "FAIL"))[:140]
        sh(r14, IV + ["-o", "build/x.vvp", "eeg_seq.sv", "tb/tb_seq_exh.sv"])
        sh(r14, ["vvp", "-n", "build/x.vvp", "+trace=build/seq_exh.txt"], 1200)
        k2 = sh(r14, [PY, "tb/check_seq_exh.py", "build/seq_exh.txt"])
        if k2.returncode: return "tb_seq_exh: " + (k2.stdout.splitlines() or ["?"])[0][:140]
    elif fn == "eeg_fifo.sv":
        for dd in ([], ["-DDEPTH4"]):
            c = sh(r14, IV + dd + ["-o", "build/f.vvp", "eeg_fifo.sv", "tb/tb_fifo.sv"])
            if c.returncode: return "COMPILE " + c.stderr[-150:]
            v = sh(r14, ["vvp", "-n", "build/f.vvp", "+n=400000", "+trace=build/fifo_trace.txt"], 1200)
            k = sh(r14, [PY, "tb/check_fifo_trace.py", "build/fifo_trace.txt"])
            if not ok(v, "PASS: tb_fifo") or k.returncode: return f"tb_fifo{dd}: " + (k.stdout.splitlines() or ["?"])[0][:140]
    elif fn == "eeg_ovl.sv":
        c = sh(r14, IV + ["-o", "build/o.vvp", "eeg_ovl.sv", "tb/tb_ovl.sv"])
        if c.returncode: return "COMPILE " + c.stderr[-150:]
        sh(r14, ["vvp", "-n", "build/o.vvp"], 1200)
        k = sh(r14, [PY, "tb/check_ovl.py"])
        if k.returncode: return "tb_ovl: " + (k.stdout.splitlines() or ["?"])[0][:140]
    elif fn == "eeg_cic3.sv":
        sh(r14, [PY, "tb/check_cic_arm.py", "gen", "7", "13"])
        c = sh(r14, IV + ["-o", "build/c.vvp", "eeg_cic3.sv", "../rtl/eeg_rnd_sat.sv", "tb/tb_cic_arm.sv"])
        if c.returncode: return "COMPILE " + c.stderr[-150:]
        for kk in (3, 5, 7, 9):
            sh(r14, ["vvp", "-n", "build/c.vvp", f"+k={kk}"], 1200)
            k = sh(r14, [PY, "tb/check_cic_arm.py", "check", str(kk)])
            if k.returncode: return f"tb_cic_arm k={kk}"
    if fn in ("eeg_clkgen.sv", "eeg_chop1.sv"):
        runs = []
        if fn == "eeg_clkgen.sv":
            runs += [("tick", ["eeg_clkgen.sv", "tb/tb_tick.sv"], "PASS: tick"), ("clkgen", ["eeg_clkgen.sv", "../rtl/tb/tb_clkgen.sv"], "PASS: tb_clkgen")]
        runs += [("chop1", ["eeg_clkgen.sv", "../rtl/eeg_chop1.sv", "../rtl/tb/tb_chop1.sv"], "PASS: chop1")]
        for nm, srcs, word in runs:
            c = sh(r14, IV + ["-o", f"build/{nm}.vvp"] + srcs)
            if c.returncode: return "COMPILE " + c.stderr[-150:]
            try:
                v = sh(r14, ["vvp", "-n", f"build/{nm}.vvp"], 300)
            except subprocess.TimeoutExpired:
                return f"{nm}: HANG"
            if not ok(v, word): return f"{nm}: " + next((l for l in v.stdout.splitlines() if l.startswith(("ERROR", "FAIL"))), "no PASS")[:140]
    return ""

def top(d):
    c = sh(d, IV + ["-o", "build/t.vvp"] + RTL + ["tb/tb_top_r14.sv"])
    if c.returncode: return "COMPILE " + (c.stderr.strip().splitlines() or ["?"])[-1][:150]
    f = run_kill(d, ["vvp", "-n", "build/t.vvp"], "build/t.log")
    if f: return "tb_top_r14: " + f[:160]
    log = open(os.path.join(d, "build/t.log"), errors="replace").read()
    if "PASS: tb_top_r14" not in log: return "tb_top_r14: NO VERDICT"
    k = sh(d, [PY, "tb/check_top_r14.py"]); k2 = sh(d, [PY, "tb/check_seq_trace.py", "build/top_seq_trace.txt", "--no-cover"])
    if k.returncode: return "check_top_r14: " + next((l for l in k.stdout.splitlines() if "mismatch" in l), "FAIL")[:150]
    if k2.returncode: return "check_seq_trace: " + (k2.stdout.splitlines() or ["?"])[0][:150]
    return ""

def one(name):
    d0, err = mkcopy(name)
    if d0 is None:
        return f"{name}: ERROR {err}"
    d = os.path.join(d0, "gf180/tapeout/rtl_r14")
    fn = os.path.basename(muts[name][0][0])
    try:
        u = unit(d, fn)
    except subprocess.TimeoutExpired:
        u = "unit: TIMEOUT"
    if u:
        shutil.rmtree(d0, ignore_errors=True)
        return f"{name}: DETECTED unit {u}"
    t = top(d)
    if t:
        shutil.rmtree(d0, ignore_errors=True)
        return f"{name}: DETECTED {t}"
    return f"{name}: PASSED-UNIT+TOP"

with cf.ThreadPoolExecutor(jobs) as ex, open(outp, "a") as fo:
    futs = [ex.submit(one, n) for n in names]
    for fu in cf.as_completed(futs):
        r = fu.result()
        fo.write(r + "\n"); fo.flush()
        print(r, flush=True)
