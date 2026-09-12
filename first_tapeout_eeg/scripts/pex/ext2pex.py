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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_CELL = "eeg_afe_top"
# Pin order for the top cell (matches scripts/klayout/afe_top_ref.spice)
TOP_PINS = ["ELP", "ELN", "VCM_REF", "VP", "VN",
            "PHII", "NPHII", "PHIBI", "NPHIBI",
            "PHIM", "NPHIM", "PHIBM", "NPHIBM",
            "CLK16", "NCLK16", "BIT", "NBIT",
            "S8", "S16", "S32", "S64", "VDD18", "VSS"]
# Net the default (p-substrate) plane ties to
SUBSTRATE = "VSS"

# Measurement aliases: the PGA outputs are internal macro nets (magic names
# them after the SDM input ports).  Rename them and expose as extra pins so
# PEX testbenches can measure the AFE gain without hierarchical node refs.
ALIASES = {"eeg_sdm1ct_0/VINP": "PGA_OUTP", "eeg_sdm1ct_0/VINN": "PGA_OUTN"}
EXTRA_PINS = ["PGA_OUTP", "PGA_OUTN"]

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
    def resolve(self, cell, prefix, pinmap, name, _seen=frozenset()):
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
            return self.resolve(sub, prefix + inst + "/", pm, rest, _seen)
        if name in pinmap:
            return pinmap[name]
        # leaf name: apply this cell's merge aliases so parent-level records
        # that reach into child internals land on real device nets (_seen
        # breaks alias cycles)
        uf, merged = self.uf_for(cell)
        if name in merged and (cell, name) not in _seen:
            return self.canonical(cell, prefix, pinmap, uf, merged, name,
                                  _seen | {(cell, name)})
        return prefix + name

    # -- union-find per cell context ---------------------------------------
    def build_uf(self, cell):
        uf = UF()
        merged = set()
        for a, b in self.exts[cell]["merges"]:
            uf.union(a, b)
            merged.add(a)
            merged.add(b)
        return uf, merged

    def uf_for(self, cell):
        if not hasattr(self, "_uf_cache"):
            self._uf_cache = {}
        if cell not in self._uf_cache:
            self._uf_cache[cell] = self.build_uf(cell)
        return self._uf_cache[cell]

    def canonical(self, cell, prefix, pinmap, uf, merged, name,
                  _seen=frozenset()):
        root = uf.find(name)
        members = [m for m in merged if uf.find(m) == root]
        resolved = [(m, self.resolve(cell, prefix, pinmap, m, _seen))
                    for m in members]
        for m, r in resolved:
            if r in self.flat_nets:
                return r
        for m, r in resolved:
            if "/" not in r:
                return r
        return resolved[-1][1] if resolved else prefix + name

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
            uf, merged = self.build_uf(cell)
            subnet = self.substrate_net(cell, prefix, pinmap)
            agg = {}

            def res(n):
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
# Parallel-device merge
# --------------------------------------------------------------------------

def merge_parallel(dev_lines):
    """Merge X devices sharing (model, terminal tuple, geometry) into one.

    Groups are keyed by (model, nodes, non-summable params), so only
    identical-geometry devices merge.  Parallel BSIM FETs (same D/G/S/B)
    are exactly equivalent to one device with w, ad, as, pd, ps summed;
    MIM unit caps likewise (w summed, same l).  Magic extracts one device
    per finger/unit, so this recovers the schematic's combined devices and
    roughly halves the element count.
    """
    from collections import defaultdict
    SUM_PARAMS = ("w", "ad", "as", "pd", "ps", "a", "p")
    groups = defaultdict(list)
    for ln in dev_lines:
        tok = ln.split()
        fp = next((i for i, t in enumerate(tok) if "=" in t), len(tok))
        model = tok[fp - 1]
        nodes = tuple(tok[1:fp - 1])
        params = tok[fp:]
        keep = tuple(t for t in params
                     if t.partition("=")[0] not in SUM_PARAMS)
        groups[(model, nodes, keep)].append((tok[0], nodes, model, params))
    out = []
    n_merged = 0
    for (model, nodes, keep), devs in groups.items():
        name, nodes, model, params = devs[0]
        acc = {}
        for _, _, _, prm in devs:
            for t in prm:
                k, _, v = t.partition("=")
                if k in SUM_PARAMS:
                    try:
                        acc[k] = acc.get(k, 0.0) + float(v)
                    except ValueError:
                        pass
        n_merged += len(devs) - 1
        merged_params = [f"{k}={acc[k]:.6g}" if k in acc else t
                         for t in params
                         for k in [t.partition("=")[0]]]
        # FETs: the PDK bins models by per-finger width (wmax=100 um), so a
        # merged device must keep nf = finger count (per-finger w = the
        # original finger width; BSIM finger behavior preserved exactly)
        if ("nfet" in model or "pfet" in model) and \
                not any(t.partition("=")[0] == "nf" for t in params):
            merged_params.append(f"nf={len(devs)}")
        out.append(f"{name} {' '.join(nodes)} {model} "
                   f"{' '.join(merged_params)}".rstrip())
    return out, n_merged

def mim_to_ideal(dev_lines):
    """Replace cap_mim_m3_* X devices with ideal C elements (2 fF/um2).

    The PDK MIM subckt carries series-R (milliohms against ~100 pF) whose
    ~GHz poles force the transient timestep down orders of magnitude; the
    series R is negligible at this circuit's frequencies (8 Hz signal,
    1 kHz chopper).  C = 2 fF/um2 * w * l matches the design values exactly
    (0.8 pF per 20x20 unit, 0.5 pF per 20x12.5 unit).
    """
    out = []
    n = 0
    for ln in dev_lines:
        tok = ln.split()
        fp = next((i for i, t in enumerate(tok) if "=" in t), len(tok))
        model = tok[fp - 1]
        if "cap_mim_m3" not in model:
            out.append(ln)
            continue
        params = dict(t.partition("=")[::2] for t in tok[fp:])
        w = float(params.get("w", 1.0))
        l = float(params.get("l", 1.0))
        mf = float(params.get("mf", 1.0))
        c = 2e-15 * w * l * mf
        nodes = tok[1:fp - 1]
        out.append(f"CMIM{tok[0][1:]} {' '.join(nodes)} {c:.6e}")
        n += 1
    return out, n


def res_to_ideal(dev_lines):
    """Replace res_xhigh_po/res_high_po X devices with ideal R elements.

    The PDK resistor subckts evaluate ~15 formula params (mismatch, body
    voltage coefficients, end effects) per instance per iteration — the
    dominant transient cost with ~190 chain segments present.  At this
    circuit's frequencies the parasitic terms are second-order; the design
    value R = rsheet * l / w (rsheet = 2000 ohm/sq for xhigh_po) is what
    both the schematic and the KLayout LVS extraction use.
    """
    out = []
    n = 0
    for ln in dev_lines:
        tok = ln.split()
        fp = next((i for i, t in enumerate(tok) if "=" in t), len(tok))
        model = tok[fp - 1]
        if "res_xhigh_po" not in model and "res_high_po" not in model:
            out.append(ln)
            continue
        params = dict(t.partition("=")[::2] for t in tok[fp:])
        w = float(params.get("w", 0.69))
        l = float(params.get("l", 5.0))
        r = 2000.0 * l / w
        nodes = tok[1:fp - 1]
        out.append(f"R{tok[0][1:]} {' '.join(nodes[:2])} {r:.6g}")
        n += 1
    return out, n


def main():

    ap = argparse.ArgumentParser(description="Annotate magic LVS netlist with .ext parasitics (flat)")
    ap.add_argument("--ext-dir", default=os.path.join(ROOT, "GDSII", "pex"),
                    help="directory containing the magic .ext files")
    ap.add_argument("--lvs", default=os.path.join(ROOT, "GDSII", "pex",
                                                  "eeg_afe_top.extracted.spice"),
                    help="LVS spice netlist from magic (ext2spice lvs)")
    ap.add_argument("--out", default=os.path.join(
                        ROOT, "source", "trials", "20260902", "xschem",
                        "eeg_afe_top_pex.spice"),
                    help="output PEX spice netlist")
    ap.add_argument("--min-cap", type=float, default=20.0,
                    help="drop caps below this many attofarads (default 20; "
                         ">=20 aF keeps >=99.98%% of total charge here)")
    ap.add_argument("--top", default=TOP_CELL,
                    help="top cell to flatten (default: full macro)")
    ap.add_argument("--pins", default=" ".join(TOP_PINS),
                    help="top cell pin list, in order")
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

    top = args.top
    top_pins = args.pins.split()
    fl = Flat(cells, exts, top)
    fl.inline(top, "", {p: p for p in top_pins})
    cap_lines, tot_sub, tot_cpl = fl.emit_caps()

    # merge parallel fingers/unit devices (exact BSIM equivalence) and drop
    # negligible caps — the raw flat netlist is far too slow for ngspice
    dev_lines, n_merged = merge_parallel(fl.dev_lines)
    dev_lines, n_mim = mim_to_ideal(dev_lines)
    dev_lines, n_res = res_to_ideal(dev_lines)
    if args.min_cap > 0:
        floor = args.min_cap * AF
        cap_lines = [ln for ln in cap_lines if float(ln.split()[3]) >= floor]

    # ---- verification: every cap endpoint must be a real flat net ---------
    bad = []
    known = fl.flat_nets | {SUBSTRATE} | set(top_pins)
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

    # apply measurement aliases (whole-token renames in device + cap lines);
    # macro-level only (PGA's own PEX exposes OUTP/OUTN as pins already)
    extra_pins = EXTRA_PINS if top == TOP_CELL else []
    if ALIASES and top == TOP_CELL:
        def alias(ln):
            tok = ln.split()
            tok = [ALIASES.get(t, t) for t in tok]
            return " ".join(tok)
        dev_lines = [alias(ln) for ln in dev_lines]
        cap_lines = [alias(ln) for ln in cap_lines]

    header = [
        f"* NGSPICE flat PEX netlist for {top} (sky130A)",
        "* Devices: magic `ext2spice lvs` netlist, hierarchy inlined by ext2pex.py",
        "* (parallel fingers/unit devices merged: exact BSIM equivalence);",
        "* Parasitic capacitors: magic .ext database (node->substrate, cap->coupling)",
        "* sky130A extraction excludes FET gate/diffusion caps (kept in BSIM",
        "* ad/as/pd/ps terms), so no double counting. Caps in farads.",
    ]
    if extra_pins:
        header += [
            "* PGA_OUTP/PGA_OUTN are aliased internal nets (PGA outputs) exposed",
            "* as extra pins for the PEX testbenches.",
        ]
    header += [
        f"* totals: {len(dev_lines)} devices ({n_merged} parallel merged), "
        f"{len(cap_lines)} caps "
        f"({tot_sub * 1e-3:.3f} fF substrate + {tot_cpl * 1e-3:.3f} fF coupling)",
        "",
    ]
    body = [f".subckt {top} " + " ".join(top_pins + extra_pins)]
    body += dev_lines
    body += cap_lines
    body.append(".ends")
    body.append("")

    with open(args.out, "w") as f:
        f.write("\n".join(header + body) + "\n")

    print(f"wrote {args.out}")
    print(f"devices={len(dev_lines)} ({n_merged} parallel merged) "
          f"caps={len(cap_lines)} "
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
