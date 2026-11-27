#!/usr/bin/env python3
"""The flip-flop Q nets of the r15 macro's gate-level netlist that gl_shadow_r15.sv compares and forces (VER-05).

gl_r14/gl_names.py with one more register: u_regs.drop_cnt (8 bits), which tb_r15 deposits (253, to reach the stop at
255) and gl_shadow_r15.sv mirrors into the netlist.

usage: gl_names_r15.py <netlist.v> <out.svh>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gl_r14"))
import gl_names as G  # noqa: E402

G.TARGETS["GL_DROP"] = (["\\u_regs.drop_cnt[{k}]", "\\drop_cnt[{k}]"], 8)

if __name__ == "__main__":
    G.main()
