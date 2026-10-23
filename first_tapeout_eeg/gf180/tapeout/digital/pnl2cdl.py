#!/usr/bin/env python3
"""Gate-level SPICE (CDL) netlist of a LibreLane macro, for chip-level LVS.

Reads the powered netlist (final/pnl/<macro>.pnl.v: flat, one instance per line group,
named connections) and the standard-cell SPICE library (for each cell's subcircuit pin
order) and writes .SUBCKT <macro> <ports...> with one X line per cell instance. Bus
ports become one pin per bit (CODE[0] ... CODE[4]), as the macro's GDS pin labels.
Fill, tap and decap cells are kept: they are in the layout, and the decap cells
(fillcap) contain MOS devices. The cell library itself is not included; the LVS run
must read it (libs.ref/<scl>/spice/<scl>.spice of the PDK).

Usage: python3 pnl2cdl.py <macro.pnl.v> <scl.spice> <out.cdl>
"""
import re
import sys


def cell_pins(spice):
    pins = {}
    cur = None
    for line in open(spice):
        if line.startswith("+") and cur:
            pins[cur] += line[1:].split()
            continue
        m = re.match(r"\s*\.subckt\s+(\S+)\s+(.*)", line, re.I)
        if m:
            cur = m.group(1)
            pins[cur] = m.group(2).split()
        else:
            cur = None
    return pins


def net_name(tok):
    tok = tok.strip()
    if tok.startswith("\\"):
        tok = tok[1:]
    if re.fullmatch(r"\d+'b[01]", tok):
        raise ValueError(f"constant connection {tok}: tie cells expected")
    return tok


def main(pnl, spice, out):
    pins = cell_pins(spice)
    text = open(pnl).read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    m = re.search(r"\bmodule\s+(\S+)\s*\((.*?)\);", text, re.S)
    top = m.group(1)
    body = text[m.end():text.index("endmodule", m.end())]
    widths = {}
    order = [p.strip() for p in m.group(2).split(",") if p.strip()]
    for d in re.finditer(r"\b(input|output|inout)\s+(?:wire\s+)?(?:\[(\d+):(\d+)\]\s*)?([^;]+);", body):
        for name in d.group(4).split(","):
            name = name.strip()
            widths[name] = (int(d.group(2)), int(d.group(3))) if d.group(2) else None
    if re.search(r"\bassign\b", body):
        raise ValueError("assign statements in the netlist are not handled")
    ports = []
    for p in order:
        w = widths.get(p)
        if w is None:
            ports.append(p)
        else:
            hi, lo = w
            step = 1 if hi >= lo else -1
            ports += [f"{p}[{i}]" for i in range(lo, hi + step, step)] if lo <= hi else \
                     [f"{p}[{i}]" for i in range(hi, lo + 1)]
    lines = [f"* {top}: gate-level netlist from {pnl.split('/')[-1]} (pnl2cdl.py)",
             f"* needs the standard-cell library subcircuits: {spice.split('/')[-1]}"]
    hdr = f".SUBCKT {top} " + " ".join(ports)
    lines.append(hdr)
    n = 0
    for inst in re.finditer(r"(\S+)\s+(\\\S+\s|\S+)\s*\((\s*\..*?)\);", body, re.S):
        cell, name, conns = inst.group(1), inst.group(2).strip(), inst.group(3)
        if cell in ("input", "output", "inout", "wire"):
            continue
        if cell not in pins:
            raise KeyError(f"cell {cell} not in {spice}")
        cmap = {}
        for c in re.finditer(r"\.(\w+)\s*\(\s*((?:\\\S+\s)|[^()]*?)\s*\)", conns):
            if c.group(2).strip():
                cmap[c.group(1)] = net_name(c.group(2))
        # pins left out of the netlist get a net of their own: the output of a CTS
        # dummy load, and the well pins of the endcap cells (which have no devices)
        for p in pins[cell]:
            if p not in cmap:
                if p in ("VDD", "VSS"):
                    raise ValueError(f"{name} ({cell}): supply pin {p} unconnected")
                cmap[p] = f"nc_{name.lstrip(chr(92))}_{p}"
        lines.append(f"X{name.lstrip(chr(92))} " + " ".join(cmap[p] for p in pins[cell]) + f" {cell}")
        n += 1
    lines.append(f".ENDS {top}")
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{top}: {len(ports)} pins, {n} instances -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
