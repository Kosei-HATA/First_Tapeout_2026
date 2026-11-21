"""Make one mutant copy: mkmut.py NAME EDITS.json  (EDITS: [[file relative to gf180/tapeout, old, new], ...];
each old text must occur exactly once when its turn comes). The copy holds gf180/tapeout/rtl, rtl_r14 (no build) and
documentation, with the untracked inputs linked as in the audit copy."""
import json, os, shutil, sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # audit25_C
REPO = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg"
name, edits = sys.argv[1], json.load(open(sys.argv[2]))
d = os.path.join(BASE, "mut", name)
shutil.rmtree(d, ignore_errors=True)
ign = shutil.ignore_patterns("build")
shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl"), os.path.join(d, "gf180/tapeout/rtl"), ignore=ign)
shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl_r14"), os.path.join(d, "gf180/tapeout/rtl_r14"), ignore=ign)
shutil.copytree(os.path.join(BASE, "documentation"), os.path.join(d, "documentation"))
os.makedirs(os.path.join(d, "gf180/tapeout/rtl/build/e2e"))
for f in ("s4.codes", "s20.codes"):
    os.symlink(os.path.join(REPO, "gf180/tapeout/rtl/build/e2e", f), os.path.join(d, "gf180/tapeout/rtl/build/e2e", f))
for r in ("typical_ov2.5V_150u_then_dc-39mV_300u", "typical_ov2.5V_50u_rec60u_f20k_a0.28"):
    p = os.path.join(d, "gf180/tapeout/pex/runs/adc_overload_r12", r)
    os.makedirs(p)
    os.symlink(os.path.join(REPO, "gf180/tapeout/pex/runs/adc_overload_r12", r, "out.csv"), os.path.join(p, "out.csv"))
for f, old, new in edits:
    p = os.path.join(d, "gf180/tapeout", f)
    t = open(p, encoding="utf-8").read()
    if t.count(old) != 1:
        sys.exit(f"{name}: the text occurs {t.count(old)} times in {f}")
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
print("made", d)
