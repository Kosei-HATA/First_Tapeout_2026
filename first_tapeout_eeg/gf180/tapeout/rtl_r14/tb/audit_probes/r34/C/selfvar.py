#!/usr/bin/env python3
"""selfvar.py <name> : a checker variant (VARIANTS[name]: module, [(old, new)] edits of the checker) in its own copy of
the spec folder and the documents; runs `<module> selftest`, then, if given, a specification edit (spec_edits: edits of
the module's data or of a document) with `<module> check`, both with the checker variant and with the original checker.
Writes scratchpad/a34C_selfvar/<name>.txt"""
import os, shutil, subprocess, sys
SP = "/private/tmp/claude-501/-Users-noah-Codings-First-Tapeout-2026-first-tapeout-eeg/e6a9fc49-8f0a-407f-94bd-50b555db57a9/scratchpad"
PY = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tools/venv310/bin/python"
BASE = os.path.join(SP, "a34C_sweep")
VARIANTS = {
    # fsm_spec check_timing: the count of the four weight quotes
    "fsm_wq_len": ("fsm_spec.py", [("    if len(quoted) != len(WEIGHT_QUOTES) or any(q != want for q in quoted):",
                                    "    if any(q != want for q in quoted):")],
                   [("doc_req", "R-21 ", None)]),
    # fsm_spec check_spi_props: CSF must go to HDR
    "fsm_csf_next": ("fsm_spec.py", [('        if "load_status" not in b["actions"] or b["next"] != "HDR":',
                                      '        if "load_status" not in b["actions"]:')], []),
    # fsm_spec check_spi_frames: data loads alone / CRC loads alone
    "fsm_loads_data": ("fsm_spec.py", [('                if d != loads["data"] or acts.count("load_crc") != loads["crc"]:',
                                        '                if acts.count("load_crc") != loads["crc"]:')], []),
    "fsm_loads_crc": ("fsm_spec.py", [('                if d != loads["data"] or acts.count("load_crc") != loads["crc"]:',
                                       '                if d != loads["data"]:')], []),
    # fsm_spec check_seq_branches: an output time with exactly one of store / discard
    "fsm_out_sd": ("fsm_spec.py", [('            if e == "OUT" and ("seq_inc" not in acts or len(acts & {"store", "discard"}) != 1):',
                                    '            if e == "OUT" and ("seq_inc" not in acts):')], []),
    # regmap check: cfg_ok at the top of each range (rejecting the top value)
    "rm_cfg_top": ("regmap.py", [("        if not cfg_ok(dict(base, RANGE=r_, M=mx)) or (r_ and cfg_ok(dict(base, RANGE=r_, M=mx + 1))):",
                                  "        if (r_ and cfg_ok(dict(base, RANGE=r_, M=mx + 1))):")], []),
    # regmap check: STATE's codes against the field width
    "rm_state_width": ("regmap.py", [('    if sorted(st["legal"] or []) != codes or max(codes) >= 1 << (st["msb"] - st["lsb"] + 1):',
                                      '    if sorted(st["legal"] or []) != codes:')], []),
    # regmap check: the overload rule's codes in the documents
    "rm_ovl_codes": ("regmap.py", [('        elif (int(mt.group(1)), int(mt.group(2))) != (R["window"], R["threshold"]) or \\\n'
                                    '                (int(mc.group(1)), int(mc.group(2))) != tuple(R["codes"]):',
                                    '        elif (int(mt.group(1)), int(mt.group(2))) != (R["window"], R["threshold"]):')], []),
    # regmap check: REG-08's registers: a field in a locked register / in a register the requirements fix
    "rm_lock_only": ("regmap.py", [("        if lock or n in set(FIELD_REGISTER_REQUIRED.values()):", "        if lock:")], []),
    "rm_req_only": ("regmap.py", [("        if lock or n in set(FIELD_REGISTER_REQUIRED.values()):",
                                   "        if n in set(FIELD_REGISTER_REQUIRED.values()):")], []),
    # regmap check: digital-only pins: exactly one source / a writable one
    "rm_dig_one": ("regmap.py", [('        if len(s_) != 1 or s_[0][2] == "ro":', '        if s_[0][2] == "ro":')], []),
    "rm_dig_ro": ("regmap.py", [('        if len(s_) != 1 or s_[0][2] == "ro":', '        if len(s_) != 1:')], []),
    # regmap check: the slip counts the requirements state (a count no longer stated)
    "rm_slip_stated": ("regmap.py", [("        if not got_ or any(g_ != SLIP_COUNTS_RECORDED.get(n_) for g_ in got_):",
                                      "        if any(g_ != SLIP_COUNTS_RECORDED.get(n_) for g_ in got_):")], []),
}

def mkcopy(dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.join(dst, "gf180/tapeout/rtl"))
    shutil.copytree(os.path.join(BASE, "documentation"), os.path.join(dst, "documentation"))
    shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl/spec"), os.path.join(dst, "gf180/tapeout/rtl/spec"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(BASE, "gf180/tapeout/rtl/build"), os.path.join(dst, "gf180/tapeout/rtl/build"),
                    symlinks=True)

def edit(path, old, new):
    t = open(path, encoding="utf-8").read()
    assert t.count(old) == 1, f"{old[:70]!r} occurs {t.count(old)} times in {path}"
    open(path, "w", encoding="utf-8").write(t.replace(old, new))

name = sys.argv[1]
mod, edits, spec_edits = VARIANTS[name]
dst = os.path.join(SP, "a34C_selfvar", name)
mkcopy(dst)
spec = os.path.join(dst, "gf180/tapeout/rtl/spec")
for o, n in edits:
    edit(os.path.join(spec, mod), o, n)
out = []
r = subprocess.run([PY, mod, "selftest"], cwd=spec, capture_output=True, text=True)
lines = r.stdout.strip().splitlines()
out.append(f"{name}: {mod} selftest with the checker variant: exit {r.returncode}; " + (lines[-1] if lines else "no output"))
out += [l for l in lines if l.startswith(("MISSED", "PROBLEM"))][:10]
open(os.path.join(SP, "a34C_selfvar", name + ".txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
