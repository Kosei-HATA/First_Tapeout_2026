#!/usr/bin/env python3
"""Compare extracted .cir vs reference .spice and report net/device mismatches."""
import sys
import klayout.db as kdb

EXT, REF = sys.argv[1], sys.argv[2]
TOP = "eeg_fd_ota_chopped_full2"

reader = kdb.NetlistSpiceReader()
na = kdb.Netlist(); na.read(EXT, reader)
nb = kdb.Netlist(); nb.read(REF, reader)

class Cmp(kdb.NetlistComparer):
    def dont_match_nets(self, a, b):
        if not self._on:
            return
        def desc(n):
            if n is None:
                return "-"
            devs = []
            for t in n.each_terminal():
                d = t.device()
                devs.append(f"{d.expanded_name() or d.device_class().name}:{t.terminal_def().name}")
            subs = [f"{s.subcircuit().circuit_ref().name}.{s.subcircuit().expanded_name()}"
                    for s in n.each_subcircuit_pin()]
            return f"{n.expanded_name()} devs[{len(devs)}]={sorted(devs)} subs={sorted(subs)}"
        print("NET MISMATCH:")
        print("  ext:", desc(a))
        print("  ref:", desc(b))
    def dont_match_devices(self, a, b):
        if not self._on:
            return
        def dd(d):
            if d is None:
                return "-"
            ts = {t.terminal_def().name: (t.net().expanded_name() if t.net() else "?")
                  for t in d.each_terminal()}
            return f"{d.expanded_name()} {d.device_class().name} {ts}"
        print("DEV MISMATCH:")
        print("  ext:", dd(a))
        print("  ref:", dd(b))
    def begin_circuit(self, a, b):
        self._on = (a.name == TOP)
    def end_circuit(self, a, b):
        self._on = False

cmp = Cmp()
cmp._on = False
same = cmp.compare(na, nb)
print("MATCH" if same else "MISMATCH")
