#!/usr/bin/env python3
"""Statement-deletion mutants (a class the earlier rounds' generators did not have: an assignment line inside an
always block dropped), outside reset branches, each old line unique in its file. Writes tools/del_mutants.py."""
import os, re
AC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {"eeg_digital_top.sv": "gf180/tapeout/rtl_r14", "eeg_regs.sv": "gf180/tapeout/rtl_r14",
         "eeg_spi_slave.sv": "gf180/tapeout/rtl_r14", "eeg_fifo.sv": "gf180/tapeout/rtl_r14",
         "eeg_seq.sv": "gf180/tapeout/rtl_r14", "eeg_ovl.sv": "gf180/tapeout/rtl_r14",
         "eeg_cic3.sv": "gf180/tapeout/rtl_r14", "eeg_clkgen.sv": "gf180/tapeout/rtl_r14",
         "eeg_chop1.sv": "gf180/tapeout/rtl", "eeg_raw.sv": "gf180/tapeout/rtl"}
out = {}
for fn, d in FILES.items():
    text = open(os.path.join(AC, d, fn), encoding="utf-8").read()
    lines = text.split("\n")
    in_always = False; depth = 0; in_reset = False; rdepth = 0
    for i, ln in enumerate(lines):
        code = ln.split("//")[0]
        s = code.strip()
        if s.startswith(("always_ff", "always_comb", "always @")):
            in_always = True; depth = 0
        if in_always:
            if re.search(r"if \(!(rst_n|tm_rst_n|pin_rst_n|RESET_N)\)", s):
                in_reset = True; rdepth = depth
            opens = len(re.findall(r"\bbegin\b", code)); closes = len(re.findall(r"\bend\b", code))
            if in_reset and s.startswith("end else") and depth - closes + 0 <= rdepth + 1 and closes:
                in_reset = False
            m = re.match(r"^\s*(?:if \(.*\)\s*)?([A-Za-z_][\w\[\]:+ ]*?)\s*(<=|=)\s*[^=].*;\s*$", code)
            if (not in_reset and m and not s.startswith(("logic", "assign", "for", "case", "localparam"))
                    and text.count(ln) == 1 and "begin" not in code):
                indent = ln[:len(ln) - len(ln.lstrip())]
                new = indent + ";   // (mutant) dropped: " + s
                out[f"del_{fn[4:-3]}_L{i+1}"] = [(f"{d}/{fn}", ln, new)]
            depth += opens - closes
            if depth <= 0 and (closes and opens == 0) and s.startswith("end"):
                in_always = False
print(len(out))
with open(os.path.join(AC, "tools", "del_mutants.py"), "w") as fo:
    fo.write("MUTANTS = " + repr(out) + "\n")
