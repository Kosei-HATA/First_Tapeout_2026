#!/usr/bin/env python3
"""
ext2pex.py - Annotate a magic LVS-extracted netlist with layout parasitic
capacitances, producing a FLAT PEX (post-layout) ngspice netlist.

Inputs:
  - LVS spice (magic `ext2spice lvs` output): authoritative device/hierarchy
    connectivity.
  - magic .ext database (one file per cell): `node` (substrate cap) and `cap`
    (coupling cap) records.

Output:
  - One flat `.subckt OPAMP_ADC_0 VDD VSS VINP VINN VBIAS VREF VOUT DOUT`
    containing every extracted device (hierarchy inlined) plus one C element
    per parasitic capacitor.

Why flat: series-stacked (stack>1) ALIGN cells contain internal stack nodes
that are not subcircuit pins, yet parent-level .ext coupling caps reference
them (e.g. "NMOS_S_..._0/a_316_462#").  A flat netlist makes every internal
node a plain top-level node whose name matches the magic convention exactly
("<inst>/<inst>/.../<local>"), so all caps attach correctly.

Method (equivalent to `ext2spice cthresh 0` without the `lvs` option):
  * .ext `node` records -> capacitor to the cell's substrate net.  The sky130A
    tech excludes FET gate/diffusion capacitance ("device capacitances to
    substrate are taken care of by the models"), so these caps complement -
    not double-count - the BSIM ad/as/pd/ps junction terms.
  * .ext `cap` records -> coupling capacitor.
  * `merge` records -> union-find aliases; the canonical member is the one
    that lands on a net actually used by devices.
  * Cap values in .ext are attofarads (sky130A extract units).

Only capacitive parasitics are annotated (magic lumped-R is ignored; wire
resistances are single-digit ohms, negligible at this circuit's impedances).

Usage:  python3 lvs_work/ext2pex.py [--ext-dir DIR] [--lvs SPICE] [--out SPICE]
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOP_CELL = "OPAMP_ADC_0"
# Pin order for the top cell (matches align_work/designs/opamp_adc/opamp_adc.sp)
TOP_PINS = ["VDD", "VSS", "VINP", "VINN", "VBIAS", "VREF", "VOUT", "DOUT"]
# Net the default (p-substrate) plane ties to
SUBSTRATE = "VSS"

AF = 1e-18  # .ext capacitance unit (attofarad)

# --------------------------------------------------------------------------
# SPICE parsing
# --------------------------------------------------------------------------

def parse_spice(path):
    """Return ({name: {'pins': [...], 'lines': [...]}}, order) joining '+' lines."""
    with open(path) as f:
        raw = f.read().splitlines()
    lines = []
    for ln in raw:
        if ln.lstrip().startswith("+") and lines:
            lines[-1] += " " + ln.strip()[1:].strip()
        else:
            lines.append(ln)
    cells, order = {}, []
    cur = None
    for ln in lines:
        s = ln.strip()
        low = s.lower()
        if low.startswith(".subckt"):
            tok = s.split()
            cur = tok[1]
            cells[cur] = {"pins": tok[2:], "lines": []}
            order.append(cur)
        elif low.startswith(".ends"):
            cur = None
        elif cur is not None and s:
            cells[cur]["lines"].append(s)
    return cells, order


def split_xline(ln):
    """Split an X instance line: (name, [nodes], subckt, params_text).

    ext2spice format: X<name> <nodes...> <subckt> [param=val ...]
    The subckt token is the one right before the first 'param=' token,
    or the last token when no params are present.
    """
    tok = ln.split()
    name = tok[0]
    first_param = next((i for i, t in enumerate(tok) if "=" in t and i > 0),
                       len(tok))
    sub = tok[first_param - 1]
    nodes = tok[1:first_param - 1]
    params = " ".join(tok[first_param:])
    return name, nodes, sub, params

def spice_insts(cell_lines):
    """{instance name w/o leading X: (subckt, [nets])} for X lines."""
    insts = {}
    for ln in cell_lines:
        tok = ln.split()
        if tok and tok[0].upper().startswith("X"):
            name, nodes, sub, _ = split_xline(ln)
            insts[name[1:]] = (sub, nodes)
    return insts


# --------------------------------------------------------------------------
# .ext parsing
# --------------------------------------------------------------------------

RE_NODE = re.compile(r'^node\s+"([^"]+)"\s+(\S+)\s+(\S+)')
RE_CAP = re.compile(r'^cap\s+"([^"]+)"\s+"([^"]+)"\s+(\S+)')
RE_MERGE = re.compile(r'^merge\s+"([^"]+)"\s+"([^"]+)"')
RE_SUBSTR = re.compile(r'^substrate\s+"([^"]+)"\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)')


def parse_ext(path):
    nodes, caps, merges = [], [], []
    substrate = None
    with open(path) as f:
        for ln in f:
            m = RE_NODE.match(ln)
            if m:
                nodes.append((m.group(1), float(m.group(3))))
                continue
            m = RE_CAP.match(ln)
            if m:
                caps.append((m.group(1), m.group(2), float(m.group(3))))
                continue
            m = RE_MERGE.match(ln)
            if m:
                merges.append((m.group(1), m.group(2)))
                continue
            m = RE_SUBSTR.match(ln)
            if m:
                substrate = (m.group(1), m.group(2))
    return {"nodes": nodes, "caps": caps, "merges": merges, "substrate": substrate}

# --------------------------------------------------------------------------
# Union-find
# --------------------------------------------------------------------------

class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)

# --------------------------------------------------------------------------
# Flattener
# --------------------------------------------------------------------------

class Flat:
    """Flatten the spice hierarchy below TOP_CELL into hierarchical node names.

    Instance context = (cell, prefix, pinmap):
      prefix : "I1/I2/" style path of X-stripped instance names
      pinmap : cell pin name -> parent flat net
    """

    def __init__(self, cells, exts, top):
        self.cells = cells
        self.exts = exts
        self.top = top
        self.insts = {c: spice_insts(cells[c]["lines"]) for c in cells}
        self.flat_nets = set()          # nets used by flat devices
        self.dev_lines = []             # flat device lines
        self.dev_count = 0
        self.contexts = []              # every (cell, prefix, pinmap) instance
        self.warnings = []

    # -- node mapping inside a context -------------------------------------
    def map_node(self, cell, prefix, pinmap, node):
        if node in pinmap:
            return pinmap[node]
        return prefix + node

    def child_pinmap(self, cell, prefix, pinmap, inst):
        sub, conns = self.insts[cell][inst]
        pins = self.cells[sub]["pins"]
        pm = {}
        for i, p in enumerate(pins):
            pm[p] = self.map_node(cell, prefix, pinmap, conns[i])
        return sub, pm

    # -- recursive inline of devices ---------------------------------------
    def inline(self, cell, prefix, pinmap):
        self.contexts.append((cell, prefix, pinmap))
        for ln in self.cells[cell]["lines"]:
            tok = ln.split()
            if not tok or not tok[0].upper().startswith("X"):
                continue
            name, conns, sub, params = split_xline(ln)
            if sub in self.cells:  # hierarchy -> recurse
                subname = name[1:]
                _, pm = self.child_pinmap(cell, prefix, pinmap, subname)
                self.inline(sub, prefix + subname + "/", pm)
            else:  # PDK leaf device
                nodes = [self.map_node(cell, prefix, pinmap, n) for n in conns]
                self.flat_nets.update(nodes)
                dev = f"X{self.dev_count} " + " ".join(nodes) + f" {sub}"
                if params:
                    dev += " " + params
                self.dev_lines.append(dev)
                self.dev_count += 1

    # -- resolve any .ext name to a flat net --------------------------------
    def resolve(self, cell, prefix, pinmap, name):
        if "/" in name:
            inst, rest = name.split("/", 1)
            if inst not in self.insts[cell]:
                self.warnings.append(f"{prefix or cell}: unknown instance in {name}")
                return prefix + name
            sub, pm = self.child_pinmap(cell, prefix, pinmap, inst)
            if sub not in self.cells:
                self.warnings.append(f"{prefix or cell}: {name} not a hierarchy instance")
                return prefix + name
            # substrate of the child cell?
            sub_ext = self.exts.get(sub)
            if sub_ext and sub_ext["substrate"] and sub_ext["substrate"][0] == rest \
                    and rest not in self.cells[sub]["pins"]:
                return SUBSTRATE
            return self.resolve(sub, prefix + inst + "/", pm, rest)
        if name in pinmap:
            return pinmap[name]
        return prefix + name

    # -- union-find per cell context ---------------------------------------
    def build_uf(self, cell):
        uf = UF()
        for a, b in self.exts[cell]["merges"]:
            uf.union(a, b)
        return uf

    def canonical(self, cell, prefix, pinmap, uf, name):
        root = uf.find(name)
        if root == name and name not in uf.p:
            return self.resolve(cell, prefix, pinmap, name)
        members = [m for m in uf.p if uf.find(m) == root]
        resolved = [(m, self.resolve(cell, prefix, pinmap, m)) for m in members]
        for m, r in resolved:
            if r in self.flat_nets:
                return r
        for m, r in resolved:
            if "/" not in r:
                return r
        return resolved[-1][1]

    # -- cap emission --------------------------------------------------------
    def substrate_net(self, cell, prefix, pinmap):
        sub = self.exts[cell]["substrate"]
        if sub is None:
            return SUBSTRATE
        name, layer = sub
        if name in pinmap:
            return pinmap[name]
        if name in self.cells[cell]["pins"]:
            return pinmap.get(name, prefix + name)
        return SUBSTRATE  # default global p-substrate plane

    def emit_caps(self):
        cap_lines = []
        n_sub = n_cpl = 0
        tot_sub = tot_cpl = 0.0
        for cell, prefix, pinmap in self.contexts:
            ext = self.exts[cell]
            uf = self.build_uf(cell)
            subnet = self.substrate_net(cell, prefix, pinmap)
            agg = {}

            def res(n):
                if n in uf.p:
                    return self.canonical(cell, prefix, pinmap, uf, n)
                return self.resolve(cell, prefix, pinmap, n)

            for name, val in ext["nodes"]:
                if val == 0.0:
                    continue
                n1 = res(name)
                if n1 == subnet:
                    continue
                key = (n1, subnet)
                agg[key] = agg.get(key, 0.0) + val
                tot_sub += val
            for a, b, val in ext["caps"]:
                if val == 0.0:
                    continue
                na, nb = res(a), res(b)
                if na == nb:
                    continue
                key = (na, nb) if na <= nb else (nb, na)
                agg[key] = agg.get(key, 0.0) + val
                tot_cpl += val
            for (n1, n2), v in sorted(agg.items()):
                cap_lines.append(f"C{len(cap_lines)} {n1} {n2} {v * AF:.6e}")
        self.cap_lines = cap_lines
        return cap_lines, tot_sub, tot_cpl

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Annotate magic LVS netlist with .ext parasitics (flat)")
    ap.add_argument("--ext-dir", default=os.path.join(ROOT, "lvs_work", "pexfix", "ext"),
                    help="directory containing the magic .ext files")
    ap.add_argument("--lvs", default=os.path.join(ROOT, "lvs_work", "pexfix",
                                                  "opamp_adc.extracted.spice"),
                    help="LVS spice netlist from magic (ext2spice lvs)")
    ap.add_argument("--out", default=os.path.join(ROOT, "xschem", "opamp_adc_pex.spice"),
                    help="output PEX spice netlist")
    args = ap.parse_args()

    cells, order = parse_spice(args.lvs)

    exts = {}
    for c in order:
        p = os.path.join(args.ext_dir, c + ".ext")
        if os.path.exists(p):
            exts[c] = parse_ext(p)
        else:
            print(f"WARNING: no .ext for cell {c}; no parasitics added", file=sys.stderr)
            exts[c] = {"nodes": [], "caps": [], "merges": [], "substrate": None}

    fl = Flat(cells, exts, TOP_CELL)
    fl.inline(TOP_CELL, "", {p: p for p in TOP_PINS})
    cap_lines, tot_sub, tot_cpl = fl.emit_caps()

    # ---- verification: every cap endpoint must be a real flat net ---------
    bad = []
    known = fl.flat_nets | {SUBSTRATE} | set(TOP_PINS)
    for ln in cap_lines:
        _, n1, n2, _ = ln.split()
        for n in (n1, n2):
            if n not in known:
                bad.append(n)
    if bad:
        print(f"ERROR: {len(bad)} cap endpoints not found in flat netlist:",
              file=sys.stderr)
        for n in sorted(set(bad))[:10]:
            print("  " + n, file=sys.stderr)
        sys.exit(1)

    header = [
        "* NGSPICE flat PEX netlist for OPAMP_ADC_0 (sky130A)",
        "* Devices: magic `ext2spice lvs` netlist, hierarchy inlined by lvs_work/ext2pex.py",
        "* Parasitic capacitors: magic .ext database (node->substrate, cap->coupling)",
        "* sky130A extraction excludes FET gate/diffusion caps (kept in BSIM",
        "* ad/as/pd/ps terms), so no double counting. Caps in farads.",
        f"* totals: {fl.dev_count} devices, {len(cap_lines)} caps "
        f"({tot_sub * 1e-3:.3f} fF substrate + {tot_cpl * 1e-3:.3f} fF coupling)",
        "",
    ]
    body = [f".subckt {TOP_CELL} " + " ".join(TOP_PINS)]
    body += fl.dev_lines
    body += cap_lines
    body.append(".ends")
    body.append("")

    with open(args.out, "w") as f:
        f.write("\n".join(header + body) + "\n")

    print(f"wrote {args.out}")
    print(f"devices={fl.dev_count} caps={len(cap_lines)} "
          f"(sub {tot_sub * 1e-3:.3f} fF, cpl {tot_cpl * 1e-3:.3f} fF)")
    if fl.warnings:
        uniq = sorted(set(fl.warnings))
        print(f"{len(fl.warnings)} warnings ({len(uniq)} unique):")
        for w in uniq[:10]:
            print("  " + w)
    else:
        print("no unresolved names")


if __name__ == "__main__":
    main()
