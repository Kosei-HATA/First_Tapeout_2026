#!/usr/bin/env python3
"""Audit round 29 (C): classic single-point mutants of the r14 blocks that earlier rounds' classic sweeps did not cover
(eeg_seq, eeg_fifo, eeg_ovl, eeg_cic3, eeg_clkgen, eeg_chop1, eeg_raw, and eeg_digital_top from line 190): operators
(== !=, && ||, & |, > >=, < <=, + -), constants (N'dK -> K+1, K-1; 1'b0 <-> 1'b1), a dropped negation (! ~).
Writes MUTANTS = {name: [(relpath, old_line, new_line)]} to classic_mutants.py; each old line is unique in its file."""
import os, re, sys
SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(SP, "audit29_C")
FILES = {"eeg_seq.sv": ("gf180/tapeout/rtl_r14", 82, 214), "eeg_fifo.sv": ("gf180/tapeout/rtl_r14", 40, 74),
         "eeg_ovl.sv": ("gf180/tapeout/rtl_r14", 30, 53), "eeg_cic3.sv": ("gf180/tapeout/rtl_r14", 60, 151),
         "eeg_clkgen.sv": ("gf180/tapeout/rtl_r14", 130, 221), "eeg_chop1.sv": ("gf180/tapeout/rtl", 1, 999),
         "eeg_raw.sv": ("gf180/tapeout/rtl", 1, 999), "eeg_digital_top.sv": ("gf180/tapeout/rtl_r14", 190, 286)}
OPS = ((" == ", " != "), (" != ", " == "), (" && ", " || "), (" || ", " && "), (" & ", " | "), (" | ", " & "),
       (" > ", " >= "), (" >= ", " > "), (" < ", " <= "), (" <= ", " < "), (" + ", " - "), (" - ", " + "))
out = {}
for fn, (d, lo, hi) in FILES.items():
    path = os.path.join(ROOT, d, fn)
    lines = open(path, encoding="utf-8").read().split("\n")
    text = "\n".join(lines)
    body = False
    for i, ln in enumerate(lines):
        if ln.startswith("module "):
            body = True
        if not body or not (lo <= i + 1 <= hi):
            continue
        code = ln.split("//")[0]
        s = code.strip()
        if not s or s.startswith(("input", "output", "parameter", "`", "localparam", "logic", "wire", "function",
                                  "endfunction", "module", "endmodule", "/*", "*", "(*")) or "<=" not in code and "=" not in code and "if" not in code:
            continue
        if text.count(ln) != 1:
            continue
        cands = []
        for a, b in OPS:
            for m in re.finditer(re.escape(a), code):
                if a == " < " and code[m.start():m.start() + 4] == " <= ":
                    continue
                if a == " <= " and code[:m.start()].count("(") - code[:m.start()].count(")") <= 0:
                    continue                              # a non-blocking assignment, not a comparison
                cands.append((code[:m.start()] + b + code[m.end():], f"op{a.strip()}{b.strip()}"))
        for m in re.finditer(r"(\d+)'d(\d+)", code):
            w, v = int(m.group(1)), int(m.group(2))
            for nv in (v + 1, v - 1):
                if 0 <= nv < (1 << w):
                    cands.append((code[:m.start()] + f"{w}'d{nv}" + code[m.end():], f"const{v}to{nv}"))
        for m in re.finditer(r"1'b([01])", code):
            nv = "1" if m.group(1) == "0" else "0"
            cands.append((code[:m.start()] + f"1'b{nv}" + code[m.end():], f"bit{m.group(1)}to{nv}"))
        for m in re.finditer(r"[!~](?=[\w(])", code):
            cands.append((code[:m.start()] + code[m.end():], "dropneg"))
        for new_code, kind in cands:
            new = new_code + (ln[len(code):] if len(ln) > len(code) else "")
            if new == ln:
                continue
            name = f"{fn[4:-3]}_L{i + 1}_{kind}_{len(out)}"
            out[name] = [(os.path.join(d, fn), ln, new)]
with open(os.path.join(SP, "c29tools", "classic_mutants.py"), "w") as fo:
    fo.write("MUTANTS = " + repr(out) + "\n")
from collections import Counter
print(len(out), Counter(n.split("_L")[0] for n in out))
