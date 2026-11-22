#!/usr/bin/env python3
"""mkcopy.py <mutants.py> <name> [<name> ...]: fresh copy of the pristine 3ebd90f5 sources (git archive) in
audit30_C/mut/<name>/ with the external inputs linked and the edits of MUTANTS[name] applied (each old text exactly
once, in order). Also writes screen.sh (the RTL groups of run_tests_r14.sh, cheapest first, stopping at the first
failing group; tb_top_r14 / _fifo4 killed at their first ERROR/FAIL line)."""
import os, runpy, shutil, subprocess, sys
W = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(W)
REPO = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg"
muts = runpy.run_path(sys.argv[1])["MUTANTS"]
for name in sys.argv[2:]:
    dst = os.path.join(BASE, "mut", name)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    a = subprocess.run(["git", "-C", REPO, "archive", "3ebd90f5", "gf180/tapeout/rtl", "gf180/tapeout/rtl_r14",
                        "documentation/gf180_digital_control_requirements_20261119.md",
                        "documentation/gf180_digital_control_spec_20261119.md",
                        "documentation/gf180_digital_control_audit_20261120.md"], capture_output=True, check=True)
    subprocess.run(["tar", "-x"], input=a.stdout, cwd=dst, check=True)
    os.makedirs(os.path.join(dst, "gf180/tapeout/rtl/build/e2e"))
    for f in ("s4.codes", "s20.codes"):
        os.symlink(f"{REPO}/gf180/tapeout/rtl/build/e2e/{f}", os.path.join(dst, "gf180/tapeout/rtl/build/e2e", f))
    for R in ("typical_ov2.5V_150u_then_dc-39mV_300u", "typical_ov2.5V_50u_rec60u_f20k_a0.28"):
        d = os.path.join(dst, "gf180/tapeout/pex/runs/adc_overload_r12", R)
        os.makedirs(d)
        os.symlink(f"{REPO}/gf180/tapeout/pex/runs/adc_overload_r12/{R}/out.csv", os.path.join(d, "out.csv"))
    ok = True
    for f, old, new in muts[name]:
        p = os.path.join(dst, f)
        t = open(p, encoding="utf-8").read()
        if t.count(old) != 1:
            print(f"{name}: NOT APPLIED, the text occurs {t.count(old)} times in {f}: {old[:80]!r}")
            ok = False
            break
        open(p, "w", encoding="utf-8").write(t.replace(old, new))
    if not ok:
        shutil.rmtree(dst)
        continue
    # screen.sh: run_tests_r14.sh without the spec group, groups reordered, stop at the first FAIL
    r14 = os.path.join(dst, "gf180/tapeout/rtl_r14")
    s = open(os.path.join(r14, "run_tests_r14.sh"), encoding="utf-8").read()
    head, tail = s.split("run spec 1800 spec\n", 1)
    head = head.replace(
        '    while kill -0 "$pid" 2>/dev/null && (( SECONDS - t0 < lim )); do sleep 1; done',
        '    while kill -0 "$pid" 2>/dev/null && (( SECONDS - t0 < lim )); do sleep 1;\n'
        '        if grep -qE "FAIL|ERROR" "build/$name.log" 2>/dev/null; then sleep 2; killtree "$pid"; wait "$pid" 2>/dev/null;\n'
        '            RES+=("FAIL  $name  (early: build/$name.log)"); printf "%s\\n" "${RES[@]}"; exit 1; fi; done')
    assert "early:" in head
    order = ["codes 600 codes", "tb_seq 1200 seq_t", "tb_tick 600 tick_t", "tb_clkgen 600 clkgen_t",
             "tb_chop1 600 chop1_t", "tb_cic_arm 600 cic_t", "tb_ovl 600 ovl_t", "tb_rnd_sat 600 rnd_t",
             "tb_regs 600 regs_t", "tb_fifo 900 fifo_t", "tb_fifo4 900 fifo4_t", "outputs 1200 outputs_t",
             "tb_spi_r14 3600 spi_t", "tb_top_r14 5400 top_t", "tb_top_r14_fifo4 5400 top4_t"]
    body = "".join(f'run {o}\nif printf "%s\\n" "${{RES[@]}}" | grep -q FAIL; then printf "%s\\n" "${{RES[@]}}"; exit 1; fi\n'
                   for o in order)
    body += 'printf "%s\\n" "${RES[@]}"\necho "SCREEN: ALL RTL GROUPS PASS"\n'
    open(os.path.join(r14, "screen.sh"), "w", encoding="utf-8").write(head + body)
    os.chmod(os.path.join(r14, "screen.sh"), 0o755)
    print(dst)
