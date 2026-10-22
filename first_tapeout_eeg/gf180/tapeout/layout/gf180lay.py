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


class Block:
    """A layout with one top cell and helpers in um."""

    def __init__(self, name):
        library()
        self.ly = pya.Layout()
        self.ly.dbu = 0.001
        self.top = self.ly.create_cell(name)
        self.name = name

    def li(self, key):
        return self.ly.layer(*L[key])

    @staticmethod
    def um(v):
        return int(round(v * 1000))

    def box(self, key, x1, y1, x2, y2):
        b = pya.Box(self.um(min(x1, x2)), self.um(min(y1, y2)), self.um(max(x1, x2)), self.um(max(y1, y2)))
        self.top.shapes(self.li(key)).insert(b)
        return b

    def label(self, metal, text, x, y):
        self.top.shapes(self.li(metal + "_label")).insert(pya.Text(text, pya.Trans(self.um(x), self.um(y))))

    def pcell(self, name, params, x=0.0, y=0.0, rot=0, mirror=False):
        """Place a PDK pcell; returns (instance, terminals) where terminals maps each label
        text inside the pcell to its (layer key, x, y) in top coordinates."""
        lib = library()
        decl = lib.layout().pcell_declaration(name)
        pc = self.ly.create_cell(name, lib.name(), params)
        if pc is None:
            raise ValueError(f"pcell {name} not created ({params})")
        t = pya.Trans(rot, mirror, pya.Vector(self.um(x), self.um(y)))
        inst = self.top.insert(pya.CellInstArray(pc.cell_index(), t))
        return inst, self.terminals(pc, t)

    def shapes(self, inst, key):
        """Boxes (um, top coordinates) of layer `key` inside a placed instance."""
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

    def write(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.ly.write(path)  # hierarchical: the pcells stay cells (the decks run in deep mode)
        return path


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


def to_cdl(netlist_files, top):
    """The subcircuit `top` (and the subcircuits it calls) from the simulation netlists,
    with X devices rewritten for the KLayout LVS deck."""
    text = "\n".join(open(f).read() for f in netlist_files)
    text = re.sub(r"\n\+", " ", text)  # join continuation lines
    blocks = _subckt_blocks(text)
    order, todo = [], [top]
    while todo:
        name = todo.pop()
        if name in order:
            continue
        order.append(name)
        for line in blocks[name][1:]:
            w = line.split()
            if w and w[0][0] in "Xx":
                cell = [t for t in w[1:] if "=" not in t][-1]
                if cell in blocks:
                    todo.append(cell)
    out = []
    for name in reversed(order):
        for line in blocks[name]:
            out.append(_device_line(line))
    return "\n".join(out) + "\n"


_DEV = {"nfet_03v3": "M", "pfet_03v3": "M", "ppolyf_u": "R", "ppolyf_u_1k": "R", "ppolyf_u_3k": "R",
        "cap_nmos_03v3": "C", "cap_pmos_03v3": "C", "cap_mim_2f0ff": "C"}
_MODEL = {"cap_mim_2f0ff": "cap_mim_2f0fF"}


def _device_line(line):
    w = line.split()
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
    os.makedirs(outdir, exist_ok=True)
    sw = {"thr": "8", "run_mode": "deep", "metal_top": "11K", "mim_option": "B", "metal_level": "5LM",
          "poly_res": "1k", "mim_cap": "2", "lvs_sub": sub, "verbose": "false", "spice_net_names": "true",
          "spice_comments": "false", "scale": "false", "schematic_simplify": "false", "net_only": "false",
          "top_lvl_pins": "false", "combine": "false", "purge": "false", "purge_nets": "false",
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
