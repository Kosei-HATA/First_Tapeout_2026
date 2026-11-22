#!/usr/bin/env python3
"""lockcov.py <mon_lock files...>: committed writes per writable register, split by the test key's state (locked /
unlocked) and by accepted (no event) / refused; and the DAC_CLK-in-reset line."""
import sys
RW = {0x08: "ALERT_MASK", 0x09: "ALERT_MASK_D", 0x20: "OFF_M_H", 0x21: "OFF_M_L", 0x22: "OFF_CTRL", 0x23: "AFE_IBIAS",
      0x24: "CPF_TRIM", 0x25: "BOOST_TRIM", 0x26: "CHOP_CFG", 0x27: "ADC_CFG", 0x28: "BLANK", 0x50: "T_WARM",
      0x51: "T_ELEC", 0x52: "T_REC", 0x53: "T_PRE", 0x54: "T_RST", 0x55: "IF_CFG", 0x06: "ERR", 0x07: "DFLAG"}
for path in sys.argv[1:]:
    cnt = {a: [0, 0, 0, 0] for a in RW}       # locked accepted, locked refused, unlocked accepted, unlocked refused
    tail = ""
    for ln in open(path):
        f = ln.split()
        if f and f[0] == "W":
            a, unl, ev = int(f[1], 16), int(f[3]), int(f[4], 16)
            if a in cnt:
                cnt[a][2 * unl + (1 if ev & 0x58 else 0)] += 1    # ADDR, STATE, RANGE events = refused
        elif f and f[0] == "E":
            tail = ln.strip()
    print(path, "|", tail)
    for a in sorted(cnt):
        la, lr, ua, ur = cnt[a]
        print(f"  0x{a:02X} {RW[a]:12s} locked: {la:4d} accepted {lr:3d} refused | unlocked: {ua:4d} accepted {ur:3d} refused")
