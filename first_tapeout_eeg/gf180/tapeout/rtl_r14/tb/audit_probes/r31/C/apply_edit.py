#!/usr/bin/env python3
"""apply_edit.py <file> <edits.json>: each edit [old, new] must occur exactly once when applied"""
import json, sys
p, ej = sys.argv[1], sys.argv[2]
t = open(p, encoding='utf-8').read()
for old, new in json.load(open(ej, encoding='utf-8')):
    n = t.count(old)
    if n != 1:
        sys.exit(f"NOT APPLIED: {old[:60]!r} occurs {n} times in {p}")
    t = t.replace(old, new)
open(p, 'w', encoding='utf-8').write(t)
print("applied", p)
