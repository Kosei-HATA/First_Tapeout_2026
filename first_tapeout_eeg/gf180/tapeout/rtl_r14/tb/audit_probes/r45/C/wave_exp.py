#!/usr/bin/env python3
"""Audit 45, auditor C: lane edits of wave.py's diagrams the check may not read. Each edit in its own copy of the spec
root; runs wave.check() (as wave.py fresh does, without the PNG part) and wave.py selftest."""
import os, shutil, subprocess, sys
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(S, "a45C_spec", "root")
PY = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python"
EDITS = {
    "startup_drdy_never": ("{\"name\": \"DRDY_N（パルス）\", \"wave\": \"1..........0101\"}", "{\"name\": \"DRDY_N（パルス）\", \"wave\": \"1..............\"}"),
    "frame_tick_c23": ('{"name": "新設：tick（相 A の中ほど）", "wave": levels(n, hi({tc}))}',
                       '{"name": "新設：tick（相 A の中ほど）", "wave": levels(n, hi({tc - 1}))}'),
    "frame_out_e24": ("    up = pos.index(tc) + 1 ", "    up = pos.index(tc) "),
    "chop_cic_f14": ("    out = {slot(15, 8)}", "    out = {slot(14, 8)}"),
    "chop_128_phaseB": ("    c128 = {i for i in range(n) if (i // 2) % 8 < 4}", "    c128 = {i for i in range(n) if (i // 2) % 8 >= 4}"),
    "chop_64_tick_B": ('t64 = {slot(f, tc) for f in range(16) if f % r64["period_frames"] == r64["tick_frame"]}',
                       't64 = {slot(f, tc) for f in range(16) if f % r64["period_frames"] == r64["tick_frame"] + 8}'),
    "startup_fill_2ms": ('"3 出力（3 ms）"', '"2 出力（2 ms）"'),
    "apply_pre_trst": ('dur = ["", timer_text("T_PRE"), timer_text("T_RST"),', 'dur = ["", timer_text("T_RST"), timer_text("T_PRE"),'),
}
ONLY = sys.argv[1:] or list(EDITS)
for tag, (old, new) in [(k, v) for k, v in EDITS.items() if k in ONLY]:
    d = os.path.join(S, "a45C_spec", "wave_exp", tag)
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(ROOT, d, symlinks=True)
    p = os.path.join(d, "gf180/tapeout/rtl/spec/wave.py")
    t = open(p, encoding="utf-8").read()
    if t.count(old) != 1:
        print(tag, "NOT APPLIED", t.count(old)); continue
    open(p, "w", encoding="utf-8").write(t.replace(old, new))
    sd = os.path.dirname(p)
    c = subprocess.run([PY, "-c", "import wave as W, json; e = W.check(); print('check violations', len(e)); [print('  ', x[:200]) for x in e]"],
                       cwd=sd, capture_output=True, text=True)
    st = subprocess.run([PY, "wave.py", "selftest"], cwd=sd, capture_output=True, text=True)
    fr = subprocess.run([PY, "wave.py", "fresh"], cwd=sd, capture_output=True, text=True)
    print(f"== {tag}: {c.stdout.strip()} {c.stderr.strip()[-200:]}")
    print("   selftest rc", st.returncode, (st.stdout.strip().splitlines() or [''])[-1][:200])
    print("   fresh rc", fr.returncode, (fr.stdout.strip().splitlines() or [''])[-1][:200])
