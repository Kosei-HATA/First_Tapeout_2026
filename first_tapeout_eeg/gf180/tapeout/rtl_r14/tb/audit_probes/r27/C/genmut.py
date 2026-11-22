#!/usr/bin/env python3
"""Generate classic single-point mutants of the r14 RTL (operator, constant, negation, connection swaps) as
MUTANTS = {name: [(path, old_line, new_line)]}; each old text is a whole line, unique in its file."""
import os, re, sys, json
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(SP, "pristine")
FILES = {"eeg_digital_top.sv": "gf180/tapeout/rtl_r14", "eeg_regs.sv": "gf180/tapeout/rtl_r14",
         "eeg_spi_slave.sv": "gf180/tapeout/rtl_r14", "eeg_clkgen.sv": "gf180/tapeout/rtl_r14",
         "eeg_ovl.sv": "gf180/tapeout/rtl_r14", "eeg_cic3.sv": "gf180/tapeout/rtl_r14",
         "eeg_fifo.sv": "gf180/tapeout/rtl_r14", "eeg_seq.sv": "gf180/tapeout/rtl_r14",
         "eeg_chop1.sv": "gf180/tapeout/rtl", "eeg_raw.sv": "gf180/tapeout/rtl"}
out = {}
def add(fn, i, old, new, kind):
    rel = os.path.join(FILES[fn], fn)
    name = f"{fn[4:-3]}_L{i+1}_{kind}_{len(out)}"
    out[name] = [(rel, old, new)]
for fn, d in FILES.items():
    lines = open(os.path.join(ROOT, d, fn), encoding="utf-8").read().split("\n")
    text = "\n".join(lines)
    in_body = False
    for i, ln in enumerate(lines):
        code = ln.split("//")[0]
        s = code.strip()
        if s.startswith("module ") or s.startswith(")") and "(" not in s:
            pass
        if not s or s.startswith(("input", "output", "parameter", "`", "localparam", "logic", "wire", "function",
                                  "endfunction", "module", "endmodule", "/*", "*")):
            continue
        if text.count(ln) != 1 or len(ln.strip()) < 6:
            continue
        cands = []
        for a, b in ((" == ", " != "), (" != ", " == "), (" && ", " || "), (" || ", " && "), (" & ", " | "),
                     (" | ", " & "), (" > ", " >= "), (" >= ", " > "), (" < ", " <= ")):
            for m in re.finditer(re.escape(a), code):
                if a == " < " and code[m.start():m.start()+4] == " <= ":
                    continue
                if a in (" >= ",) and "<=" in code[:m.start()] and "assign" not in code and "if" not in code:
                    continue
                cands.append((code[:m.start()] + b + code[m.end():], f"op{a.strip()}{b.strip()}"))
        for m in re.finditer(r"(\d+)'d(\d+)", code):
            w, v = int(m.group(1)), int(m.group(2))
            for nv in (v + 1, v - 1):
                if 0 <= nv < (1 << w):
                    cands.append((code[:m.start()] + f"{w}'d{nv}" + code[m.end():], f"const{v}to{nv}"))
        for m in re.finditer(r"([~!])(\(?[A-Za-z_][A-Za-z_0-9\[\]:.]*)", code):
            cands.append((code[:m.start()] + code[m.start()+1:], f"neg{m.group(1)}"))
        for m in re.finditer(r"1'b([01])", code):
            cands.append((code[:m.start()] + f"1'b{1 - int(m.group(1))}" + code[m.end():], f"bit{m.group(1)}"))
        for new, kind in cands:
            nl = new + (("//" + ln.split("//", 1)[1]) if "//" in ln else "")
            if nl != ln:
                add(fn, i, ln, nl, kind)
print(len(out))
with open(os.path.join(SP, "tools", "auto_mutants.py"), "w") as fo:
    fo.write("MUTANTS = " + repr(out) + "\n")
