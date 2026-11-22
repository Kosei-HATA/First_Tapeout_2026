#!/usr/bin/env python3
"""screen.py <mut dir> <bench>...: a quick screen of a mutant copy: top (tb_top_r14, 8-deep, killed at its first ERROR/FAIL
line, then its two checkers), top4, spi (tb_spi_r14 +n=1500 +seed=5 and its checker), regs, struct, seq, fifo, tick,
clkgen, chop1, cic, ovl. Prints one verdict line per bench: DETECTED <why> / PASSED. Not a substitute for run_tests_r14.sh."""
import os, subprocess, sys
PY = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python"
D = os.path.abspath(sys.argv[1]); R14 = os.path.join(D, "gf180/tapeout/rtl_r14")
RTL = ("eeg_digital_top.sv eeg_seq.sv eeg_regs.sv eeg_spi_slave.sv eeg_fifo.sv eeg_ovl.sv eeg_cic3.sv eeg_clkgen.sv "
       "../rtl/eeg_chop1.sv ../rtl/eeg_raw.sv ../rtl/eeg_rnd_sat.sv").split()
IV = ["iverilog", "-g2012", "-I", "../rtl/spec", "-I", "tb", "-I", "build"]
os.makedirs(os.path.join(R14, "build"), exist_ok=True)
def sh(cmd, **k):
    return subprocess.run(cmd, cwd=R14, capture_output=True, text=True, **k)
def gen():
    if not os.path.exists(os.path.join(R14, "build/reg_tests.svh")):
        for c in ([PY, "tb/gen_codes.py"], [PY, "tb/gen_reg_tests.py"], [PY, "tb/gen_ok_vectors.py"]):
            r = sh(c)
            if r.returncode: print("GEN ERROR", c, r.stdout[-300:], r.stderr[-300:]); sys.exit(2)
def run_kill(cmd, log):
    """vvp on a pseudo-terminal (line-buffered output), killed at its first ERROR / FAIL line"""
    import pty, select
    m, sl = pty.openpty()
    p = subprocess.Popen(["nice", "-n", "5"] + cmd, cwd=R14, stdout=sl, stderr=sl, close_fds=True)
    os.close(sl)
    first, buf = None, b""
    with open(os.path.join(R14, log), "wb") as fo:
        while True:
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
    p.wait()
    os.close(m)
    return first
def top(fifo4=False):
    gen()
    out = "build/s_top4.vvp" if fifo4 else "build/s_top.vvp"
    c = sh(IV + (["-DFIFO4"] if fifo4 else []) + ["-o", out] + RTL + ["tb/tb_top_r14.sv"])
    if c.returncode: return "COMPILE ERROR " + c.stderr[-200:]
    f = run_kill(["vvp", "-n", out], "build/s_top.log")
    if f: return "DETECTED " + f
    log = open(os.path.join(R14, "build/s_top.log")).read()
    if "PASS: tb_top_r14" not in log: return "NO VERDICT " + log[-200:]
    k = sh([PY, "tb/check_top_r14.py"]); k2 = sh([PY, "tb/check_seq_trace.py", "build/top_seq_trace.txt", "--no-cover"])
    if k.returncode: return "DETECTED check_top_r14 " + k.stdout[-300:]
    if k2.returncode: return "DETECTED check_seq_trace " + k2.stdout[-300:]
    return "PASSED " + [l for l in log.splitlines() if l.startswith("tb_top_r14:")][-1][:200]
def spi():
    c = sh(IV + ["-o", "build/s_spi.vvp"] + RTL + ["tb/tb_spi_r14.sv"])
    if c.returncode: return "COMPILE ERROR " + c.stderr[-200:]
    v = sh(["nice", "-n", "5", "vvp", "-n", "build/s_spi.vvp", "+n=1500", "+seed=5", "+log=build/s_spi_trace.txt"])
    k = sh([PY, "tb/check_spi_trace.py", "build/s_spi_trace.txt"])
    bad = [l for l in v.stdout.splitlines() if l.startswith(("ERROR", "SPI ERROR", "FAIL"))]
    if bad or k.returncode: return "DETECTED " + (bad[0] if bad else k.stdout.splitlines()[0])
    return "PASSED " + k.stdout.splitlines()[0][:150]
def regs():
    gen()
    c = sh(IV + ["-o", "build/s_regs.vvp", "eeg_regs.sv", "tb/tb_regs.sv"])
    if c.returncode: return "COMPILE ERROR " + c.stderr[-200:]
    v = sh(["vvp", "-n", "build/s_regs.vvp"])
    return ("PASSED " if "PASS: tb_regs" in v.stdout and "ERROR" not in v.stdout else "DETECTED ") + v.stdout.strip().splitlines()[-1][:150]
def struct():
    k = subprocess.run([PY, os.path.join(R14, "tb/check_outputs_registered.py")], cwd=R14, capture_output=True, text=True)
    return ("PASSED " if k.returncode == 0 else ("DETECTED " if k.returncode == 1 else "TOOL ERROR ")) + (k.stdout.strip().splitlines() or ["?"])[-1][:200]
def seq():
    c = sh(IV + ["-o", "build/s_seq.vvp", "eeg_seq.sv", "tb/tb_seq.sv"]); 
    if c.returncode: return "COMPILE ERROR"
    v = sh(["vvp", "-n", "build/s_seq.vvp", "+n=600000", "+seed=11", "+trace=build/s_seq_trace.txt"])
    k = sh([PY, "tb/check_seq_trace.py", "build/s_seq_trace.txt"])
    c = sh(IV + ["-o", "build/s_seqx.vvp", "eeg_seq.sv", "tb/tb_seq_exh.sv"])
    v2 = sh(["vvp", "-n", "build/s_seqx.vvp", "+trace=build/s_seq_exh.txt"])
    k2 = sh([PY, "tb/check_seq_exh.py", "build/s_seq_exh.txt"])
    ok = "PASS" in v.stdout and "ERROR" not in v.stdout and k.returncode == 0 and k2.returncode == 0
    return ("PASSED " if ok else "DETECTED ") + (k.stdout.splitlines() or ["?"])[0][:120] + " | " + (k2.stdout.splitlines() or ["?"])[-1][:120]
def fifo():
    out = []
    for d4 in ([], ["-DDEPTH4"]):
        c = sh(IV + d4 + ["-o", "build/s_fifo.vvp", "eeg_fifo.sv", "tb/tb_fifo.sv"])
        v = sh(["vvp", "-n", "build/s_fifo.vvp", "+n=400000", "+trace=build/s_fifo_trace.txt"])
        k = sh([PY, "tb/check_fifo_trace.py", "build/s_fifo_trace.txt"])
        out.append("PASS" in v.stdout and "ERROR" not in v.stdout and k.returncode == 0)
    return ("PASSED" if all(out) else "DETECTED") + f" {out}"
def tick():
    out = []
    for nm, srcs in (("s_tick", ["eeg_clkgen.sv", "tb/tb_tick.sv"]), ("s_clk", ["eeg_clkgen.sv", "../rtl/tb/tb_clkgen.sv"]),
                     ("s_c1", ["eeg_clkgen.sv", "../rtl/eeg_chop1.sv", "../rtl/tb/tb_chop1.sv"])):
        sh(IV + ["-o", f"build/{nm}.vvp"] + srcs)
        try:
            v = sh(["vvp", "-n", f"build/{nm}.vvp"], timeout=240)
        except subprocess.TimeoutExpired:
            out.append(f"{nm} HANG (no end in 240 s)")
            continue
        if not ("PASS" in v.stdout and "ERROR" not in v.stdout and "FAIL" not in v.stdout):
            out.append(f"{nm} FAIL")
    if not out:
        return "PASSED tick/clkgen/chop1"
    return ("DETECTED " if any("FAIL" in o for o in out) else "HANG ") + "; ".join(out)
def cic():
    gen()
    r = sh([PY, "tb/check_cic_arm.py", "gen", "7", "13"])
    c = sh(IV + ["-o", "build/s_cic.vvp", "eeg_cic3.sv", "../rtl/eeg_rnd_sat.sv", "tb/tb_cic_arm.sv"])
    if c.returncode: return "COMPILE ERROR"
    for kk in (3, 5, 7, 9):
        sh(["vvp", "-n", "build/s_cic.vvp", f"+k={kk}"]); k = sh([PY, "tb/check_cic_arm.py", "check", str(kk)])
        if k.returncode: return "DETECTED tb_cic_arm k=%d" % kk
    return "PASSED tb_cic_arm"
def ovl():
    gen()
    c = sh(IV + ["-o", "build/s_ovl.vvp", "eeg_ovl.sv", "tb/tb_ovl.sv"]); v = sh(["vvp", "-n", "build/s_ovl.vvp"])
    k = sh([PY, "tb/check_ovl.py"])
    return ("PASSED " if k.returncode == 0 else "DETECTED ") + k.stdout.splitlines()[0][:150]
F = dict(top=top, top4=lambda: top(True), spi=spi, regs=regs, struct=struct, seq=seq, fifo=fifo, tick=tick, cic=cic, ovl=ovl)
for b in sys.argv[2:]:
    r = F[b]()
    print(f"{os.path.basename(D)} {b}: {r}", flush=True)
    if r.startswith("DETECTED"):
        break
