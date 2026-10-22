"""Layout helpers for the GF180 EEG chip (tracker E1): PDK pcells placed from Python,
metal and vias drawn as plain shapes, pin labels, and the DRC/LVS runners.

PDK: the wafer.space template's gf180mcuD (open_pdks 792ef670), the one its precheck
uses, for the pcells, the DRC deck (variant gf180mcuD: 5 metals, Metal5 on top at
11 kA, MIM option B between Metal4 and Metal5) and the LVS deck. The simulations use
the ciel install (open_pdks f6eeac7d); its ngspice models differ only in how the
poly-resistor substrate capacitance is written (cox / cj), which ngspice evaluates the
same (10/23).

Tools: generation runs in gf180/tools/venv310 (pip klayout 0.30.12 and gdsfactory, which
the pcells use). DRC and LVS run in the template's nix shell (KLayout 0.30.12 with Ruby
3.4; the KLayout.app build has an older Ruby that cannot read the deck), from the
working copy /Users/noah/Codings/ws_gf180/eeg_padring.

Conventions:
  - Units are um in the helpers; the layout uses dbu 1 nm.
  - Pins are text labels on the metal label layers (metal<n>_label) placed on a shape
    of that metal; the LVS netlist names the same pins.
  - The LVS netlist comes from the simulation netlist (gf180/tapeout/*/*.spice) through
    to_cdl(): X devices become M/R/C devices with the PDK model names.
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PDK = "/Users/noah/Codings/ws_gf180/gf180mcu-project-template/gf180mcu/gf180mcuD"
TECH = os.path.join(PDK, "libs.tech", "klayout", "tech")
NIX_DIR = "/Users/noah/Codings/ws_gf180/eeg_padring"

sys.path.insert(0, os.path.join(TECH, "pymacros"))
import pya  # noqa: E402
import cells  # noqa: E402  (GF180 pcell library; registers "gf180mcu")

_LIB = None

L = {  # (layer, datatype)
    "comp": (22, 0), "nwell": (21, 0), "poly2": (30, 0), "nplus": (32, 0), "pplus": (31, 0),
    "contact": (33, 0), "metal1": (34, 0), "via1": (35, 0), "metal2": (36, 0), "via2": (38, 0),
    "metal3": (42, 0), "via3": (40, 0), "metal4": (46, 0), "via4": (41, 0), "metal5": (81, 0),
    "fusetop": (75, 0), "dualgate": (55, 0), "pr_bndry": (0, 0),
    "sab": (49, 0), "resistor": (62, 0), "res_mk": (110, 5),
    "metal1_label": (34, 10), "metal2_label": (36, 10), "metal3_label": (42, 10),
    "metal4_label": (46, 10), "metal5_label": (81, 10), "poly2_label": (30, 10),
}
METALS = ["metal1", "metal2", "metal3", "metal4", "metal5"]
VIAS = ["via1", "via2", "via3", "via4"]
# via rules (um): size 0.26 (V*.1), spacing 0.36 in arrays of 4 x 4 or more (V*.2b; 0.26
# otherwise), metal enclosure 0.06 on all sides (covers V*.3/V*.4)
VIA_SIZE = 0.26
VIA_SPACE = 0.36
VIA_ENC = 0.06


def library():
    global _LIB
    if _LIB is None:
        _LIB = cells.gf180mcu()
    return _LIB


class Cell:
    """Drawing helpers (um) on one cell of a layout. Block is the top cell of its own
    layout; Block.new_cell() makes further cells in the same layout, placed with place()."""

    def __init__(self, ly, cell):
        self.ly = ly
        self.cell = cell
        self.top = cell  # the pya cell (name kept from the first version)
        self.name = cell.name

    def li(self, key):
        return self.ly.layer(*L[key])

    @staticmethod
    def um(v):
        return int(round(v * 1000))

    def box(self, key, x1, y1, x2, y2):
        b = pya.Box(self.um(min(x1, x2)), self.um(min(y1, y2)), self.um(max(x1, x2)), self.um(max(y1, y2)))
        self.cell.shapes(self.li(key)).insert(b)
        return b

    def label(self, metal, text, x, y):
        self.cell.shapes(self.li(metal + "_label")).insert(pya.Text(text, pya.Trans(self.um(x), self.um(y))))

    def pcell(self, name, params, x=0.0, y=0.0, rot=0, mirror=False):
        """Place a PDK pcell; returns (instance, terminals) where terminals maps each label
        text inside the pcell to its (layer key, x, y) in this cell's coordinates."""
        lib = library()
        pc = self.ly.create_cell(name, lib.name(), params)
        if pc is None:
            raise ValueError(f"pcell {name} not created ({params})")
        t = pya.Trans(rot, mirror, pya.Vector(self.um(x), self.um(y)))
        inst = self.cell.insert(pya.CellInstArray(pc.cell_index(), t))
        return inst, self.terminals(pc, t)

    def place(self, child, x=0.0, y=0.0, rot=0, mirror=False):
        """Place another Cell of the same layout at (x, y) um; rot in units of 90 degrees,
        mirror about the x axis before the rotation."""
        t = pya.Trans(rot, mirror, pya.Vector(self.um(x), self.um(y)))
        return self.cell.insert(pya.CellInstArray(child.cell.cell_index(), t))

    def bbox(self):
        """(x1, y1, x2, y2) um of everything in the cell"""
        b = self.cell.bbox()
        return b.left / 1000, b.bottom / 1000, b.right / 1000, b.top / 1000

    def shapes(self, inst, key):
        """Boxes (um, this cell's coordinates) of layer `key` inside a placed instance."""
        li = self.ly.find_layer(*L[key])
        out = []
        if li is None:
            return out
        it = self.ly.cell(inst.cell_index).begin_shapes_rec(li)
        while not it.at_end():
            bx = it.shape().bbox().transformed(inst.cplx_trans * it.trans())
            out.append((bx.left / 1000, bx.bottom / 1000, bx.right / 1000, bx.top / 1000))
            it.next()
        return out

    def terminals(self, cell, trans):
        out = {}
        for key, (lay, dt) in L.items():
            if not key.endswith("_label"):
                continue
            li = self.ly.find_layer(lay, dt)
            if li is None:
                continue
            it = cell.begin_shapes_rec(li)
            while not it.at_end():
                sh = it.shape()
                if sh.is_text():
                    p = (trans * it.trans()) * sh.text.trans.disp
                    out.setdefault(sh.text.string, []).append((key[:-6], p.x / 1000, p.y / 1000))
                it.next()
        return out

    def vias(self, via, x1, y1, x2, y2):
        """Fill the box (um) with a via array of the given via layer and draw both metals."""
        lo = METALS[VIAS.index(via)]
        hi = METALS[VIAS.index(via) + 1]
        self.box(lo, x1, y1, x2, y2)
        self.box(hi, x1, y1, x2, y2)
        pitch = VIA_SIZE + VIA_SPACE
        w, h = abs(x2 - x1) - 2 * VIA_ENC, abs(y2 - y1) - 2 * VIA_ENC
        nx, ny = max(1, int((w + VIA_SPACE) / pitch)), max(1, int((h + VIA_SPACE) / pitch))
        ox = min(x1, x2) + (abs(x2 - x1) - (nx * pitch - VIA_SPACE)) / 2
        oy = min(y1, y2) + (abs(y2 - y1) - (ny * pitch - VIA_SPACE)) / 2
        for i in range(nx):
            for j in range(ny):
                self.box(via, ox + i * pitch, oy + j * pitch, ox + i * pitch + VIA_SIZE, oy + j * pitch + VIA_SIZE)

    def stack(self, lo, hi, x1, y1, x2, y2):
        """Vias from metal lo to metal hi (e.g. 'metal1', 'metal4') over the box."""
        for k in range(METALS.index(lo), METALS.index(hi)):
            self.vias(VIAS[k], x1, y1, x2, y2)


class Block(Cell):
    """A layout with one top cell and helpers in um."""

    def __init__(self, name):
        library()
        ly = pya.Layout()
        ly.dbu = 0.001
        super().__init__(ly, ly.create_cell(name))

    def new_cell(self, name):
        """A further (empty) cell in this layout, to fill and place()."""
        if self.ly.has_cell(name):
            raise ValueError(f"cell {name} exists")
        return Cell(self.ly, self.ly.create_cell(name))

    def find_cell(self, name):
        return Cell(self.ly, self.ly.cell(name)) if self.ly.has_cell(name) else None

    def write(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.ly.write(path)  # hierarchical: the pcells stay cells (the decks run in deep mode)
        return path


# ----------------------------------------------------------------------------------
# generators
# ----------------------------------------------------------------------------------
MIM_CA = 1.99e-3    # cap_mim_2f0ff: F/m2 of area
MIM_CP = 2.383e-10  # F/m of perimeter
MIM_MAX_AREA = 10000.0  # um2 per MIM cap and per shared bottom plate (MIMTM.8b, MIMTM.11)


def mim_unit_side(c_total, n):
    """Side (um, 10 nm grid) of n equal square cap_mim_2f0ff units giving c_total (F) in all."""
    c = c_total / n
    a = (-4 * MIM_CP + ((4 * MIM_CP) ** 2 + 4 * MIM_CA * c) ** 0.5) / (2 * MIM_CA)  # m
    return round(a * 1e6, 2)


def mim_cap(w, l):
    """Capacitance (F) of one cap_mim_2f0ff of w x l um, as the ngspice model computes it."""
    return MIM_CA * w * l * 1e-12 + MIM_CP * 2 * (w + l) * 1e-6


def mim_array(b, nx, ny, w, l, x0=0.0, y0=0.0, top="TOP", bot="BOT", s=3.0, t=3.0, g=1.0, hgap=2.6,
              bw=5.0):
    """MIM capacitor array (MIM-B): nx x ny units of w x l um, all in parallel between the
    nets `top` (top plates) and `bot` (bottom plates), comb-routed on Metal5.

    The bottom plate (Metal4) may only be reached through Via4 (MIMTM.10) and may carry at
    most 10,000 um2 of MIM (MIMTM.11), so every unit keeps its own Metal4 island and both
    nets run on Metal5. Per column, west to east: the `top` spine (s um, touching the top
    plates), the units, a 1 um gap, the `bot` spine (t um) over a Metal4 tab of each unit's
    bottom plate with Via4. The `top` spines join a bus above the array, the `bot` spines a
    bus below it (bw um each), so the two combs interleave without crossing.
    Rows are hgap apart: the Metal4 of a bottom plate (0.6 um beyond the top plate) must
    stay 1.2 um from any other Metal4 (MIMTM.1).
    Returns the outline (x0, y0, x1, y1) in um.
    """
    if w * l > MIM_MAX_AREA:
        raise ValueError(f"MIM unit {w} x {l} um exceeds {MIM_MAX_AREA} um2")
    px, py = s + w + 1.0 + t + g, l + hgap
    yb = y0 + bw + 2.0                       # bottom edge of the first row of top plates
    ytop = yb + (ny - 1) * py + l            # top edge of the last row
    for i in range(nx):
        xk = x0 + i * px
        xs = xk + s + w + 1.0                # west edge of the bot spine
        for j in range(ny):
            yu = yb + j * py
            b.pcell("cap_mim", {"mim_option": "MIM-B", "metal_level": "M5", "wc": w, "lc": l}, x=xk + s, y=yu)
            b.box("metal4", xk + s + w + 0.3, yu - 0.6, xs + t, yu + l + 0.6)   # bottom-plate tab
            b.vias("via4", xs, yu + 0.4, xs + t, yu + l - 0.4)
        b.box("metal5", xk, yb, xk + s, ytop + 2.0 + bw)       # top spine, up into the top bus
        b.box("metal5", xs, y0, xs + t, ytop)                  # bot spine, down into the bottom bus
    x1 = x0 + nx * px - g
    b.box("metal5", x0, ytop + 2.0, x1, ytop + 2.0 + bw)       # top bus
    b.box("metal5", x0, y0, x1, y0 + bw)                       # bottom bus
    b.label("metal5", top, x0 + 1.0, ytop + 2.0 + bw / 2)
    b.label("metal5", bot, x0 + 1.0, y0 + bw / 2)
    return x0, y0, x1, ytop + 2.0 + bw


# ----------------------------------------------------------------------------------
# netlists for LVS
# ----------------------------------------------------------------------------------
def _subckt_blocks(text):
    blocks, cur = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt"):
            cur = s.split()[1]
            blocks[cur] = [line]
        elif cur:
            blocks[cur].append(line)
            if s.lower().startswith(".ends"):
                cur = None
    return blocks


_SI = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6}


def spice_num(v, env=None):
    """Value of a SPICE number (2.5u, 10p, 1meg) or a brace expression ({2.5u*s}) with the
    parameters in env."""
    v = v.strip()
    if v.startswith("{") and v.endswith("}"):
        e = re.sub(r"(\d+\.?\d*(?:e[-+]?\d+)?)(meg|[fpnumk])\b",
                   lambda m: f"({m.group(1)}*{_SI[m.group(2).lower()]})", v[1:-1], flags=re.I)
        return float(eval(e, {"__builtins__": {}}, dict(env or {})))
    m = re.fullmatch(r"([-+]?\d*\.?\d+(?:e[-+]?\d+)?)(meg|[fpnumk])?", v, flags=re.I)
    if not m:
        raise ValueError(f"not a number: {v}")
    return float(m.group(1)) * (_SI[m.group(2).lower()] if m.group(2) else 1.0)


def variant_name(name, params):
    """Name of a parameterized subcircuit for given parameter values (also the layout
    cell name): eeg_afe_inv with s=8 -> eeg_afe_inv_s8."""
    return name + "".join(f"_{k}{v:g}" for k, v in sorted(params.items()))


def _subckt_params(header):
    return {t.split("=", 1)[0].lower(): t.split("=", 1)[1] for t in header.split()[2:] if "=" in t}


def to_cdl(netlist_files, top):
    """The subcircuit `top` (and the subcircuits it calls) from the simulation netlists,
    with X devices rewritten for the KLayout LVS deck. Parameterized subcircuits (e.g.
    eeg_afe_inv s=1) become one plain subcircuit per parameter set, named by
    variant_name(). Ideal capacitors named CW* are pre-layout wiring estimates (eeg_adc)
    and are left out."""
    text = "\n".join(open(f).read() for f in netlist_files)
    text = re.sub(r"\n\+", " ", text)  # join continuation lines
    blocks = _subckt_blocks(text)
    out, done = [], set()

    def emit(name, env, vname):
        if vname in done:
            return
        done.add(vname)
        lines = blocks[name]
        ports = [t for t in lines[0].split()[2:] if "=" not in t and t.lower() != "params:"]
        body = []
        for line in lines[1:]:
            w = line.split()
            if not w or w[0].startswith("*") or w[0].lower().startswith(".ends"):
                continue
            if w[0][0] in "Xx":
                pos = [t for t in w[1:] if "=" not in t]
                model = pos[-1]
                kv = [t.split("=", 1) for t in w[1:] if "=" in t]
                if model in blocks:
                    defaults = _subckt_params(blocks[model][0])
                    if defaults:
                        cenv = {k: spice_num(v) for k, v in defaults.items()}
                        for k, v in kv:
                            cenv[k.lower()] = spice_num(v, env)
                        cname = variant_name(model, cenv)
                        emit(model, cenv, cname)
                    else:
                        if kv:
                            raise ValueError(f"parameters on {w[0]} of plain subcircuit {model}")
                        cname = model
                        emit(model, {}, model)
                    body.append(" ".join([w[0]] + pos[:-1] + [cname]))
                    continue
                vals = []
                for k, v in kv:
                    if "{" in v:
                        x = spice_num(v, env)
                        v = f"{x * 1e6:.6g}u" if k.lower() in ("w", "l", "r_width", "r_length", "c_width",
                                                              "c_length") else f"{x:.6g}"
                    vals.append(f"{k}={v}")
                line = " ".join([w[0]] + pos + vals)
            body.append(_device_line(line))
        out.append(f".subckt {vname} " + " ".join(ports))
        out.extend(body)
        out.append(f".ends {vname}")

    emit(top, {}, top)
    return "\n".join(out) + "\n"


_DEV = {"nfet_03v3": "M", "pfet_03v3": "M", "ppolyf_u": "R", "ppolyf_u_1k": "R", "ppolyf_u_3k": "R",
        "cap_nmos_03v3": "C", "cap_pmos_03v3": "C", "cap_mim_2f0ff": "C"}
_MODEL = {"cap_mim_2f0ff": "cap_mim_2f0fF"}


def _device_line(line):
    w = line.split()
    if w and w[0][:2].upper() == "CW":
        return "* wiring estimate, not a device: " + line
    if not w or w[0][0] not in "Xx":
        return line
    pos = [t for t in w[1:] if "=" not in t]
    model = pos[-1]
    if model not in _DEV:
        return line
    nodes = pos[:-1]
    params = [t for t in w[1:] if "=" in t]
    ren = {"r_length": "l", "r_width": "w", "c_length": "l", "c_width": "w"}
    params = [ren.get(p.split("=")[0].lower(), p.split("=")[0].lower()) + "=" + p.split("=", 1)[1] for p in params]
    params = [p for p in params if p.split("=")[0] in ("w", "l", "nf", "m")]
    return " ".join([_DEV[model] + w[0][1:]] + nodes + [_MODEL.get(model, model)] + params)


# ----------------------------------------------------------------------------------
# DRC and LVS (in the template's nix shell)
# ----------------------------------------------------------------------------------
def _nix(cmd, log):
    r = subprocess.run(["nix-shell", "--run", cmd], cwd=NIX_DIR, capture_output=True, text=True)
    open(log, "w").write(r.stdout + r.stderr)
    return r.returncode


def drc(gds, top, outdir, decks="all,-antenna,-density,-cup"):
    """Run the PDK DRC (variant gf180mcuD); returns {rule: count} of violations."""
    gds, outdir = os.path.abspath(gds), os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    rep = os.path.join(outdir, f"{top}.lyrdb")
    if os.path.exists(rep):
        os.remove(rep)
    cmd = (f"klayout -b -r {TECH}/drc/gf180mcu.drc -rd input={gds} -rd report={rep} -rd topcell={top} "
           f"-rd variant=gf180mcuD -rd decks={decks} -rd run_mode=deep -rd threads=max")
    _nix(cmd, os.path.join(outdir, f"{top}_drc.log"))
    if not os.path.exists(rep):
        raise RuntimeError(f"no DRC report; see {outdir}/{top}_drc.log")
    root = ET.parse(rep).getroot()
    counts = {}
    for item in root.iter("item"):
        cat = item.find("category").text.strip("'")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def lvs(gds, cdl, top, outdir, sub="VSS"):
    """Run the PDK LVS deck (variant D: 5LM, 11K top, MIM-B; substrate net `sub`) with the
    switches its run_lvs.py would pass (that wrapper needs docopt, which the nix shell's
    Python lacks). Returns (match, summary lines)."""
    gds, cdl, outdir = os.path.abspath(gds), os.path.abspath(cdl), os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    sw = {"thr": "8", "run_mode": "deep", "metal_top": "11K", "mim_option": "B", "metal_level": "5LM",
          "poly_res": "1k", "mim_cap": "2", "lvs_sub": sub, "verbose": "false", "spice_net_names": "true",
          "spice_comments": "false", "scale": "false", "schematic_simplify": "false", "net_only": "false",
          "top_lvl_pins": "false", "combine": "true", "purge": "false", "purge_nets": "false",
          "topcell": top, "input": gds, "schematic": cdl,
          "report": os.path.join(outdir, f"{top}.lvsdb"), "target_netlist": os.path.join(outdir, f"{top}_ext.cir")}
    shims = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shims")  # pmap stand-in
    cmd = f"PATH={shims}:$PATH klayout -b -r {TECH}/lvs/gf180mcu.lvs " + " ".join(f"-rd {k}={v}" for k, v in sw.items())
    log = os.path.join(outdir, f"{top}_lvs.log")
    _nix(cmd, log)
    txt = open(log).read()
    ok = "Congratulations! Netlists match" in txt
    lines = [l for l in txt.splitlines() if re.search(r"[Mm]atch|ERROR|Error", l)]
    return ok, lines[-6:]
