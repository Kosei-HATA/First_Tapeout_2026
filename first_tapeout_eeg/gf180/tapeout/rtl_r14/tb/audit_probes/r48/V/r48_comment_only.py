#!/usr/bin/env python3
"""Audit round 48 (the fix side's check of A3): two versions of a (System)Verilog source differ only inside comments.
Every comment (// to the end of the line, /* ... */) is blanked to spaces, its newlines kept, outside string literals;
a comment that carries a tool directive (synopsys, pragma, synthesis, translate_off/on, verilator, yosys, lint_off/on)
is kept as code. The blanked texts, with each line's trailing blanks removed (a comment at a line's end may change its
length), must be equal character for character, so every code token keeps its line and column (a synthesis run's
source attributes are the same) and the line count is the same; a comment inside a line that changes its length moves
the code after it and counts as a difference.
Usage: r48_comment_only.py OLD_DIR NEW_DIR FILE...   (FILE relative to both directories)
Prints per file: byte-identical, comment-only (the number of lines whose comments differ), or DIFFERS; exits 1 if any
file differs outside comments."""
import hashlib
import re
import sys

DIRECTIVE = re.compile(r"\b(synopsys|pragma|synthesis|translate_off|translate_on|verilator|yosys|lint_off|lint_on)\b")


def blank(s):
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':                                   # a string literal: copied as is
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            out.append(s[i:j + 1])
            i = j + 1
        elif s.startswith("//", i):
            j = s.find("\n", i)
            j = n if j < 0 else j
            com = s[i:j]
            out.append(com if DIRECTIVE.search(com) else " " * len(com))
            i = j
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j < 0:
                sys.exit("unterminated block comment")
            com = s[i:j + 2]
            out.append(com if DIRECTIVE.search(com) else re.sub(r"[^\n]", " ", com))
            i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main():
    a, b, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    bad = 0
    for f in files:
        x = open(f"{a}/{f}", encoding="utf-8").read()
        y = open(f"{b}/{f}", encoding="utf-8").read()
        if x == y:
            print(f"byte-identical  {f}")
            continue
        bx, by = ("\n".join(ln.rstrip() for ln in blank(t).split("\n")) for t in (x, y))
        if bx == by:
            nl = sum(1 for p, q in zip(x.split("\n"), y.split("\n")) if p != q)
            h = hashlib.sha256(bx.encode()).hexdigest()[:16]
            print(f"comment-only    {f}  ({nl} lines differ only in comments; {x.count(chr(10))} lines in both; "
                  f"code sha256 {h})")
        else:
            bad += 1
            xl, yl = bx.split("\n"), by.split("\n")
            k = next((k for k, (p, q) in enumerate(zip(xl, yl)) if p != q), min(len(xl), len(yl)))
            print(f"DIFFERS         {f}  (first code difference at line {k + 1})")
    print("PASS: only comments differ" if bad == 0 else f"FAIL: {bad} files differ outside comments")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
