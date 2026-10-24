"""Extract layout data for the chip dashboard from the final chip (unfilled GDS and the core
LVS database): blocks, devices per block, top-level routing by net class and layer, the
longest top-level nets, pads, and white-background routing images.

usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/extract.py . gf180/tapeout/viz/data"""
import csv
import os
import re
import sys
from collections import Counter, defaultdict

import klayout.db as db
import klayout.lay as lay
from PIL import Image, ImageDraw, ImageFont

REPO, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
RUNS = os.path.join(REPO, "gf180/tapeout/layout/runs/chip_top")
GDS = os.path.join(RUNS, "chip_top.gds")
LVSDB = os.path.join(RUNS, "eeg_core.lvsdb")
PADS = os.path.join(REPO, "gf180/tapeout/chip/padring/pad_coordinates.csv")
DIE = (0.0, 0.0, 3932.0, 2531.0)

METALS = [("Metal1", (34, 0), ["l13"]), ("Metal2", (36, 0), ["l15"]), ("Metal3", (42, 0), ["l17"]),
          ("Metal4", (46, 0), ["l20", "l25"]), ("Metal5", (81, 0), ["l23", "l26"])]
VIAS = [("Via1", (35, 0)), ("Via2", (38, 0)), ("Via3", (40, 0)), ("Via4", (41, 0))]

CLASSES = ["Supply", "Ground", "Electrode input", "AFE output", "Reference and bias", "Clocks and phases",
           "Digital control", "Digital I/O", "Block-internal"]


def net_class(name):
    n = name.upper()
    if n in ("AVDD", "DVDD", "AVDD_CLK"):
        return "Supply"
    if n in ("AVSS", "DVSS", "AVSS_CLK"):
        return "Ground"
    if n in ("ELP", "ELN"):
        return "Electrode input"
    if n in ("OUTP", "OUTN"):
        return "AFE output"
    if n in ("VCM", "VREFP", "VREFN", "VREFP_PAD", "VREFN_PAD", "VBN", "VBCM", "BLP", "BLN", "VBN1", "VNC1",
             "VPC1", "VBCM1", "VBPC2", "VBNC2", "IDP", "IDN", "IQ", "ITST", "ATP", "O2P", "O2N"):
        return "Reference and bias"
    if n in ("CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP_EN", "CHOP1", "DAC_CLK", "CMP_STROBE", "AFE_RST",
             "RSTA", "CIA", "NCIA", "CIB", "NCIB", "CDA", "NCDA", "CDB", "NCDB", "OFPH", "ADC_RST_N"):
        return "Clocks and phases"
    if n in ("MCLK", "RESET_N", "SCLK", "CS_N", "MOSI", "MISO", "MISO_OE", "DRDY_N", "RAW_DATA", "RAW_CLK"):
        return "Digital I/O"
    if re.fullmatch(r"(OFS|OFM\d+|OFEN\d+|TC\d+|IB\d|BP\d|BN\d|CPF\d|ADC_ZERO|DBG_SEL\d|SEL1_\d+|SEL2_\d+|"
                    r"TH\d+|CODE\d+)", n):
        return "Digital control"
    return None


# ---- blocks (from the GDS) ----------------------------------------------------------------
ly = db.Layout()
ly.read(GDS)
top = ly.top_cell()
LABEL = {"afe_top": "AFE", "adc_top": "ADC", "eeg_digital_top": "Digital controller", "eeg_bias": "Bias generator",
         "eeg_ref": "Reference filter", "eeg_testmux": "Test multiplexer", "padring": "Pad ring"}
groups = defaultdict(list)
for inst in top.each_inst():
    name = ly.cell(inst.cell_index).name
    bb = inst.dbbox()
    if name == "chip_decap":
        name = "decap_avdd" if bb.left < 2900 else "decap_dvdd"
    groups[name].append(bb)
LABEL.update({"decap_avdd": "AVDD decoupling", "decap_dvdd": "DVDD decoupling"})
blocks = []
for name, bbs in groups.items():
    u = bbs[0]
    for b in bbs[1:]:
        u = u + b
    area = sum(b.width() * b.height() for b in bbs)
    blocks.append(dict(block=LABEL.get(name, name), cell="chip_decap" if name.startswith("decap") else name,
                       instances=len(bbs), x0=round(u.left, 2), y0=round(u.bottom, 2), x1=round(u.right, 2),
                       y1=round(u.top, 2), width_um=round(u.width(), 2), height_um=round(u.height(), 2),
                       area_mm2=round(area / 1e6, 4)))
order = ["AFE", "ADC", "Digital controller", "Bias generator", "Reference filter", "Test multiplexer",
         "AVDD decoupling", "DVDD decoupling", "Pad ring"]
blocks.sort(key=lambda b: order.index(b["block"]) if b["block"] in order else 99)
print("blocks:", [(b["block"], b["instances"]) for b in blocks])

# ---- core LVS: devices per block, net names from the schematic side --------------------------
lvs = db.LayoutVsSchematic()
lvs.read(LVSDB)
nl = lvs.netlist()
core = next(nl.each_circuit_top_down())
inner = [b for b in blocks if b["block"] != "Pad ring"]


def which_block(x, y):
    for b in inner:
        if b["x0"] <= x <= b["x1"] and b["y0"] <= y <= b["y1"]:
            return b["block"]
    return "Top level"


devs = defaultdict(lambda: dict(count=0, gate_um2=0.0, cap_pf=0.0, res_kohm=0.0))
for d in core.each_device():
    c = d.device_class().name
    p = d.trans.disp
    key = (which_block(p.x, p.y), c)
    e = devs[key]
    e["count"] += 1
    pn = {pd.name for pd in d.device_class().parameter_definitions()}
    if "W" in pn and "L" in pn and ("fet" in c):
        e["gate_um2"] += d.parameter("W") * d.parameter("L")
    if c.startswith("cap_mim") and "A" in pn:
        e["cap_pf"] += (d.parameter("A") * 1.99 + d.parameter("P") * 0.238) / 1000.0
    if c.startswith("cap_") and "C" in pn and not c.startswith("cap_mim"):
        e["cap_pf"] += d.parameter("C") * 1e12
    if "R" in pn and c.startswith("ppoly"):
        e["res_kohm"] += d.parameter("R") / 1000.0
with open(os.path.join(OUT, "devices.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["block", "device", "count", "gate_area_um2", "capacitance_pF", "resistance_kohm"])
    for (b, c), e in sorted(devs.items()):
        w.writerow([b, c, e["count"], round(e["gate_um2"], 1), round(e["cap_pf"], 3), round(e["res_kohm"], 1)])
print("device rows:", len(devs))

# schematic names for layout nets
xref = lvs.xref()
names = {}
for cp in xref.each_circuit_pair():
    for np in xref.each_net_pair(cp):
        a, b = np.first(), np.second()
        if a is not None and b is not None and b.name:
            names[a.cluster_id] = b.name
cls_nets = defaultdict(list)
for n in core.each_net():
    nm = names.get(n.cluster_id) or n.name or ""
    k = net_class(nm) if nm else None
    if k:
        cls_nets[k].append((nm, n))
print("classified nets:", {k: len(v) for k, v in cls_nets.items()})

# ---- top-level routing by class and layer ---------------------------------------------------
TOP = {}
for lname, (l, d), _ in METALS:
    li = ly.find_layer(l, d)
    TOP[lname] = db.Region(top.shapes(li)).merged() if li is not None else db.Region()
VIA_TOP = {}
for vname, (l, d) in VIAS:
    li = ly.find_layer(l, d)
    VIA_TOP[vname] = db.Region(top.shapes(li)) if li is not None else db.Region()

route_rows, net_rows = [], []
class_regions = defaultdict(db.Region)
for lname, _, lv in METALS:
    layer_regions = [lvs.layer_by_name(x) for x in lv]
    used = db.Region()
    for k in CLASSES[:-1]:
        reg = db.Region()
        for nm, n in cls_nets.get(k, []):
            for lr in layer_regions:
                reg += lvs.shapes_of_net(n, lr, True)
        part = (reg.merged() & TOP[lname])
        used += part
        class_regions[k] += part
        route_rows.append([k, lname, round(part.area() * ly.dbu ** 2, 1)])
    rest = TOP[lname] - used
    class_regions["Block-internal"] += rest
    route_rows.append(["Block-internal", lname, round(rest.area() * ly.dbu ** 2, 1)])
    print(lname, "top-level area um2:", round(TOP[lname].area() * ly.dbu ** 2))
with open(os.path.join(OUT, "routing.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["net_class", "layer", "top_level_area_um2"])
    w.writerows(route_rows)
with open(os.path.join(OUT, "vias.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["via_layer", "top_level_cuts"])
    for vname, r in VIA_TOP.items():
        w.writerow([vname, r.count()])

# per-net top-level metal and span (signal nets only, not supplies)
for k in CLASSES[2:-1]:
    for nm, n in cls_nets.get(k, []):
        reg = db.Region()
        for lname, _, lv in METALS:
            for x in lv:
                reg += lvs.shapes_of_net(n, lvs.layer_by_name(x), True) & TOP[lname]
        if reg.is_empty():
            continue
        bb = reg.bbox().to_dtype(ly.dbu)
        net_rows.append([nm, k, round(reg.area() * ly.dbu ** 2, 1), round((bb.width() + bb.height()) / 1000, 3)])
net_rows.sort(key=lambda r: -r[3])
with open(os.path.join(OUT, "nets.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["net", "net_class", "top_level_area_um2", "span_mm"])
    w.writerows(net_rows)
print("nets with top-level metal:", len(net_rows))

with open(os.path.join(OUT, "blocks.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(list(blocks[0].keys()))
    for b in blocks:
        w.writerow(list(b.values()))

# ---- pads -----------------------------------------------------------------------------------
with open(PADS) as f, open(os.path.join(OUT, "pads.csv"), "w", newline="") as g:
    r = csv.DictReader(f)
    w = csv.writer(g)
    w.writerow(["side", "position", "instance", "cell", "signal", "bond_x_um", "bond_y_um", "x0", "y0", "x1", "y1"])
    for row in r:
        w.writerow([row["side"], row["pos_from_top_or_west"], row["inst"], row["cell"], row["signal"],
                    row["bond_x_um"], row["bond_y_um"], row["cell_x0_um"], row["cell_y0_um"],
                    row["cell_x1_um"], row["cell_y1_um"]])

# ---- images: top-level routing by class, and by layer -----------------------------------------
COL = {"Supply": "#ea580c", "Ground": "#4f46e5", "Electrode input": "#e11d48", "AFE output": "#0d9488",
       "Reference and bias": "#9333ea", "Clocks and phases": "#d97706", "Digital control": "#0284c7",
       "Digital I/O": "#16a34a", "Block-internal": "#cbd5e1"}
LCOL = {"Metal1": "#334155", "Metal2": "#334155", "Metal3": "#334155", "Metal4": "#334155", "Metal5": "#334155"}


def render(layers, png, width):
    """layers: [(region, color, outline_only)] in drawing order; block outlines on top."""
    v = db.Layout()
    v.dbu = ly.dbu
    c = v.create_cell("viz")
    idx = []
    for i, (reg, color, frame) in enumerate(layers):
        li = v.layer(1000 + i, 0)
        c.shapes(li).insert(reg)
        idx.append((li, color, frame))
    tmp = png + ".gds"
    v.write(tmp)
    view = lay.LayoutView()
    view.load_layout(tmp, True)
    view.set_config("background-color", "#ffffff")
    view.set_config("grid-visible", "false")
    view.set_config("text-visible", "false")
    view.clear_layers()
    for li, color, frame in idx:
        info = v.get_info(li)
        p = lay.LayerPropertiesNode()
        p.source = f"{info.layer}/{info.datatype}@1"
        rgb = int(color[1:], 16)
        p.fill_color = rgb
        p.frame_color = rgb
        p.dither_pattern = 1 if frame else 0
        p.width = 1
        view.insert_layer(view.end_layers(), p)
    view.max_hier()
    bb = db.DBox(*DIE)
    h = int(width * bb.height() / bb.width())
    view.resize(width, h)
    view.zoom_box(bb)
    view.save_image_with_options(png, width, h, 0, 3, 0, bb, False)
    os.remove(tmp)


render([(class_regions[k], COL[k], False) for k in CLASSES[::-1]], os.path.join(OUT, "route_class_hi.png"), 4000)
for lname, _, _ in METALS:
    render([(TOP[lname], LCOL[lname], False)], os.path.join(OUT, f"route_{lname}_hi.png"), 2000)
print("images written")
