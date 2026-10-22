"""Summary of a KLayout LVS database: per circuit pair, the nets, devices, pins and
subcircuits that did not match.  Usage: python lvsdiag.py <file.lvsdb> [max lines]"""
import sys
import klayout.db as db


def main(path, nmax=40):
    lvs = db.LayoutVsSchematic()
    lvs.read(path)
    xref = lvs.xref()
    S = db.NetlistCrossReference
    bad = {S.Mismatch: "mismatch", S.NoMatch: "nomatch", S.Skipped: "skipped"}
    n = 0
    for cp in xref.each_circuit_pair():
        a, b = cp.first(), cp.second()
        name = f"{a.name if a else '-'} / {b.name if b else '-'}"
        st = cp.status()
        lines = []
        for np_ in xref.each_net_pair(cp):
            if np_.status() in bad:
                lines.append(f"  net {np_.first().expanded_name() if np_.first() else '-'} / "
                             f"{np_.second().expanded_name() if np_.second() else '-'}: {bad[np_.status()]}")
        for dp in xref.each_device_pair(cp):
            if dp.status() in bad:
                d1, d2 = dp.first(), dp.second()
                lines.append(f"  device {d1.expanded_name() if d1 else '-'} / {d2.expanded_name() if d2 else '-'}: {bad[dp.status()]}")
        for sp in xref.each_subcircuit_pair(cp):
            if sp.status() in bad:
                s1, s2 = sp.first(), sp.second()
                lines.append(f"  subckt {s1.expanded_name() if s1 else '-'} / {s2.expanded_name() if s2 else '-'}: {bad[sp.status()]}")
        for pp in xref.each_pin_pair(cp):
            if pp.status() in bad:
                p1, p2 = pp.first(), pp.second()
                lines.append(f"  pin {p1.expanded_name() if p1 else '-'} / {p2.expanded_name() if p2 else '-'}: {bad[pp.status()]}")
        if lines or st in bad:
            print(f"circuit {name}: {bad.get(st, 'match')}")
            for l in lines:
                if n < nmax:
                    print(l)
                n += 1


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40)
