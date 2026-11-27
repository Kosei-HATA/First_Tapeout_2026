#!/usr/bin/env python3
"""Write the r15 versions of the ADC-block system tests (11/28) from gl_r14's (11/25): sys_adc_r15.sv, gl_sys_sdf_r15.sv,
sys_tb_top_r15.svh, sys_sys_sdf_r15.svh, run_sys_r15.sh and run_sys_sdf_r15.sh. The benches are the r14 ones with the
r15 names (gl_shadow_r15, sys_adc_r15, gl_sys_sdf_r15); the runners take the r15 tree (rtl_r15 and its spec), the r15
macro runs and gl_names_r15.py. The ADC block (eeg_adc_dig, the macro f3) is the same on every chip r12 .. r15.

usage: mk_sys_r15.py      (in gf180/tapeout/digital/gl_r15)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "gl_r14")


def gen(name_in, name_out, pairs, must=()):
    """pairs: (text, replacement) each required in the file, except the common renames R (replaced where they occur)"""
    t = open(os.path.join(SRC, name_in), encoding="utf-8").read()
    for a, b in pairs:
        if a not in t:
            if (a, b) in R:
                continue
            raise SystemExit(f"{name_in}: {a!r} not found")
        t = t.replace(a, b)
    for x in must:
        if x in t:
            raise SystemExit(f"{name_out}: {x!r} left")
    open(os.path.join(HERE, name_out), "w", encoding="utf-8").write(t)
    print("wrote", name_out)


R = [("sys_adc_r14", "sys_adc_r15"), ("gl_shadow_r14", "gl_shadow_r15"), ("gl_sys_sdf_r14", "gl_sys_sdf_r15"),
     ("sys_sys_sdf_r14", "sys_sys_sdf_r15"), ("sys_tb_top_r14", "sys_tb_top_r15")]
gen("sys_adc_r14.sv", "sys_adc_r15.sv",
    [("// sys_adc_r14 - the ADC's digital block (eeg_adc_dig: TH capture, CODE, the two DWA selectors; unchanged since the macro\n"
      "// f3 and the same on the chips r12, r13 and r14) on the r14 control macro's outputs (11/25; tracker C3).",
      "// sys_adc_r15 - the ADC's digital block (eeg_adc_dig: TH capture, CODE, the two DWA selectors; unchanged since the macro\n"
      "// f3 and the same on the chips r12 .. r15) on the r15 control macro's outputs (gl_r14/sys_adc_r14.sv of 11/25 with the\n"
      "// r15 names, mk_sys_r15.py, 11/28; tracker C3).")] + R
    + [("on the r14 control", "on the r15 control")],
    must=("sys_adc_r14", "gl_shadow_r14", "r14 control"))
gen("gl_sys_sdf_r14.sv", "gl_sys_sdf_r15.sv",
    [("// gl_sys_sdf_r14 - the r14 control macro", "// gl_sys_sdf_r15 - the r15 control macro (gl_r14/gl_sys_sdf_r14.sv of 11/25 with the r15 names,\n"
      "// mk_sys_r15.py, 11/28)")] + R + [("the r14 control", "the r15 control")],
    must=("gl_sys_sdf_r14", "gl_shadow_r14", "sys_adc_r14"))
gen("sys_tb_top_r14.svh", "sys_tb_top_r15.svh", R)
gen("sys_sys_sdf_r14.svh", "sys_sys_sdf_r15.svh", R)
RUN_PAIRS = [
    ("HERE=$T/digital/gl_r14", "HERE=$T/digital/gl_r15"),
    ("MAC=$T/digital/eeg_digital_top_r14/runs/$TAG", "MAC=$T/digital/eeg_digital_top_r15/runs/$TAG"),
    ("RUN=$T/digital/eeg_digital_top_r14/runs/sys_$TAG", "RUN=$T/digital/eeg_digital_top_r15/runs/sys_$TAG"),
    ("git archive $REV first_tapeout_eeg/gf180/tapeout/rtl_r14 first_tapeout_eeg/gf180/tapeout/rtl \\\n"
     "        first_tapeout_eeg/documentation/gf180_digital_control_spec_20261119.md",
     "git archive $REV first_tapeout_eeg/gf180/tapeout/rtl_r15 first_tapeout_eeg/gf180/tapeout/rtl \\\n"
     "        first_tapeout_eeg/documentation/gf180_digital_control_spec_r15_20261127.md"),
    ("(cd $SRC/rtl_r14 && $PY tb/gen_codes.py", "(cd $SRC/rtl_r15 && $PY tb/gen_codes.py"),
    ("$PY $HERE/gl_names.py", "$PY $HERE/gl_names_r15.py"),
    ("cd $SRC/rtl_r14 || exit 1", "cd $SRC/rtl_r15 || exit 1"),
    ("-I ../rtl/spec", "-I spec"),
] + R + [("on the r14 control", "on the r15 control"),
         ("# out:   gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_<tag>/", "# out:   gf180/tapeout/digital/eeg_digital_top_r15/runs/sys_<tag>/")]
gen("run_sys_r14.sh", "run_sys_r15.sh",
    [("# The r14 control macro with the ADC's digital block", "# The r15 control macro with the ADC's digital block (gl_r14/run_sys_r14.sh of 11/25 for the r15 tree, mk_sys_r15.py,\n# 11/28)"),
     ("# usage: run_sys_r14.sh", "# usage: run_sys_r15.sh"),
     ("# session edits gf180/tapeout/rtl_r14 in this checkout, which this never touches.",
      "# session edited the r14 tree in this checkout; r15: the commit's rtl_r15, never the checkout's.")] + RUN_PAIRS,
    must=("rtl_r14", "gl_shadow_r14", "sys_adc_r14", "eeg_digital_top_r14", "gl_names.py "))
gen("run_sys_sdf_r14.sh", "run_sys_sdf_r15.sh", RUN_PAIRS + [
    ("run_sys_sdf_r14.sh", "run_sys_sdf_r15.sh"),
    ("# The r14 control macro and the ADC's digital block", "# The r15 control macro (gl_r14/run_sys_sdf_r14.sh of 11/25 for the r15 tree, mk_sys_r15.py, 11/28)\n# and the ADC's digital block"),
    ("(the r14 run's final/sdf,", "(the r15 run's final/sdf,")],
    must=("rtl_r14", "gl_shadow_r14", "sys_adc_r14", "eeg_digital_top_r14", "gl_names.py "))
for f in ("run_sys_r15.sh", "run_sys_sdf_r15.sh"):
    os.chmod(os.path.join(HERE, f), 0o755)
