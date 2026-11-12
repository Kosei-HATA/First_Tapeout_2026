#!/usr/bin/env python3
"""Study (11/12): the ADC's RIN and DAC1 in ppolyf_u instead of ppolyf_u_1k, against the poly flicker noise found by
gf180/tapeout/pex/adc_flicker.py (documentation/gf180_realistic_eval_20261028.md, figure 33 of r10). Nothing in the
design changes: the netlist is copied and edited under runs/ppolyf_u_study/.

  unit   a 300 kohm unit as two ppolyf_u strips of 0.8 um (PRES.1, the minimum width) in series, the length solved so
         that it matches the ppolyf_u_1k unit (291.28 x 1 um) at 27 C typical; its flicker noise at the DAC1 strings'
         current against the 1k unit (adc_flicker.header(): res_mm with the variation off), and its resistance at
         res_typical / ss / ff and -40 / 27 / 85 C against the 1k unit's
  dac1   dac1_check.py's brk, even (voff 0 and 5 mV) and ref on eeg_dac1 with the 1k units and with the ppolyf_u units
         (each 1k unit -> two strips in series), at --corner / --temp
  plan   the resistor array of rdac1_lay.py (156 units -> 312 strips) with the margins of analog.res_cell and
         fets.res_array, gap 0.4 um (PRES.2) or 0.6 um (as now), and the adc_rdac block around it (the present
         block's overhead), against the room in adc_top (block boxes from layout/gds/adc_top.gds, r10)
  fig    documentation/figures/gf180/plan_20261112/gf180_rdac_ppolyf_u_20261112.png

usage: gf180/tools/venv310/bin/python gf180/tapeout/sim/dac1/ppolyf_u_study.py [unit dac1 plan fig]
       [--corner typical] [--temp 27]      (from the repo root; no part given: all four)"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "pex"))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "viz"))
import dac1_check as D  # noqa: E402
import adc_flicker as AF  # noqa: E402

if not hasattr(np, "trapezoid"):     # dac1_check.py uses numpy 2's name; venv310 has numpy 1.x
    np.trapezoid = np.trapz

RUNS = os.path.join(HERE, "runs", "ppolyf_u_study")
JSON = os.path.join(RUNS, "study.json")
FIG_DIR = os.path.join(REPO, "documentation", "figures", "gf180", "plan_20261112")
GDS = os.path.join(REPO, "gf180", "tapeout", "layout", "gds", "adc_top.gds")
K_B, T_K = 1.380649e-23, 300.15
I_STR = 0.4064                       # uA: a DAC1 string's current (adc_flicker.py, typical)
W_PU = 0.8                           # um, PRES.1
# generator margins (analog.res_cell, fets.res_array): ring + 0.8, RESISTOR beyond the body, Metal2 pads
RING_W, RES_RX, RES_RY, PAD = 0.42, 1.04, 0.40, 1.6
X_DVDD = 1203.0                      # adc_lay.py: the DVDD riser along the east edge (Metal5)


def load():
    return json.load(open(JSON)) if os.path.exists(JSON) else {}


def save(d):
    os.makedirs(RUNS, exist_ok=True)
    json.dump(d, open(JSON, "w"), indent=1)


def ng(name, body, i_ua=I_STR, temp=27, corner=None, noise=True):
    d = os.path.join(RUNS, "ng", name)
    os.makedirs(d, exist_ok=True)
    pdk = AF.S.P.PDK
    hdr = f".include {pdk}/design.ngspice\n.lib {pdk}/sm141064.ngspice {corner}\n" if corner else AF.header()
    nz = "noise v(n) I1 dec 1 10 10\nsetplot noise1\nprint onoise_spectrum\n" if noise else ""
    deck = (f"* ppolyf_u study\n{hdr}\n.temp {temp}\n{body}\nI1 0 n dc {i_ua}u ac 1\n.control\nop\n"
            f"let rdc = v(n) / {i_ua}u\nprint rdc\n{nz}.endc\n.end\n")
    open(os.path.join(d, "tb.spice"), "w").write(deck)
    log = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=d, capture_output=True, text=True).stdout
    open(os.path.join(d, "run.log"), "w").write(log)
    r = float(re.search(r"rdc = ([-0-9.e+]+)", log).group(1))
    s = float(re.findall(r"onoise_spectrum = ([-0-9.e+]+)", log)[0]) if noise else float("nan")
    return r, s


def pu_body(length):
    return (f"XR1 n m 0 ppolyf_u r_length={length:.2f}u r_width={W_PU}u\n"
            f"XR2 m 0 0 ppolyf_u r_length={length:.2f}u r_width={W_PU}u")


ONE_K = "XR n 0 0 ppolyf_u_1k r_length=291.28u r_width=1u"


def unit():
    r1k, s1k = ng("1k", ONE_K)
    lo, hi = 250.0, 400.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        r, _ = ng("solve", pu_body(mid), noise=False)
        lo, hi = (mid, hi) if r < r1k else (lo, mid)
    length = round(0.5 * (lo + hi), 2)
    rpu, spu = ng("pu", pu_body(length))
    rel = lambda r, s: (s ** 2 - 4 * K_B * T_K * r) * 10 / (I_STR * 1e-6 * r) ** 2   # noqa: E731  S_I/I^2 x f
    out = dict(length=length, w=W_PU, r1k=r1k, rpu=rpu, nv1k=s1k * 1e9, nvpu=spu * 1e9, rel1k=rel(r1k, s1k),
               relpu=rel(rpu, spu), ratio=math.sqrt(rel(rpu, spu) / rel(r1k, s1k)), area1k=291.28, areapu=2 * length * W_PU,
               corners={})
    for corner in ("res_typical", "res_ss", "res_ff"):
        for temp in (-40, 27, 85):
            a, _ = ng(f"c_{corner}_{temp}_1k", ONE_K, temp=temp, corner=corner, noise=False)
            b, _ = ng(f"c_{corner}_{temp}_pu", pu_body(length), temp=temp, corner=corner, noise=False)
            out["corners"][f"{corner} {temp}"] = (a / r1k, b / rpu)
    fl = json.load(open(os.path.join(AF.OUT, "adc_flicker.json")))["summary"]
    out["fs_nv_1k"] = fl["fs_b_nv"]
    out["fs_nv_pu"] = fl["fs_b_nv"] * out["ratio"]
    out["enob_1k"] = AF.enob(math.hypot(fl["base_nv"], fl["fs_b_nv"]))
    out["enob_pu"] = AF.enob(math.hypot(fl["base_nv"], out["fs_nv_pu"]))
    print(f"unit: 2 x {length} x {W_PU} um ppolyf_u, R {rpu:.1f} (1k {r1k:.1f}); flicker x{out['ratio']:.4f}; "
          f"full scale {out['fs_nv_pu']:.2f} nVrms, {out['enob_pu']:.2f} bit (1k {out['enob_1k']:.2f})")
    for k, (a, b) in out["corners"].items():
        print(f"  {k:16s}: 1k {a:.4f}, ppolyf_u {b:.4f}")
    return out


def dac1(length, corner, temp):
    src = open(D.DAC1).read().splitlines()
    lines, n = [], 0
    for ln in src:
        m = re.match(r"^(XR[PN][AB]) (\S+) (\S+) VSS ppolyf_u_1k r_length=291.28u r_width=1u$", ln)
        if m:
            name, a, b = m.groups()
            lines += [f"{name}1 {a} {name[1:]}M VSS ppolyf_u r_length={length:.2f}u r_width={W_PU}u",
                      f"{name}2 {name[1:]}M {b} VSS ppolyf_u r_length={length:.2f}u r_width={W_PU}u"]
            n += 1
        else:
            lines.append(ln)
    assert n == 4, n
    os.makedirs(RUNS, exist_ok=True)
    pu = os.path.join(RUNS, "eeg_dac1_ppolyf_u.spice")
    open(pu, "w").write("\n".join(lines) + "\n")
    orig = D.DAC1
    out = {}
    for variant, path in (("1k", orig), ("pu", pu)):
        D.DAC1, D.HERE = path, os.path.join(RUNS, f"dac1_{variant}")
        t0 = time.time()
        o = types.SimpleNamespace(corner=corner, temp=temp, voff=0.0, tol="A")
        # each check's result is kept as soon as it is done (dac1_<variant>/results_<corner><temp>.json),
        # so a run that stops resumes at the check it was in; delete the file to run everything again
        cache = os.path.join(D.HERE, f"results_{corner}{temp:g}.json")
        r = json.load(open(cache)) if os.path.exists(cache) else {}

        def step(key, fn):
            if key not in r:
                r[key] = fn()
                os.makedirs(D.HERE, exist_ok=True)
                json.dump(r, open(cache, "w"), indent=1)
        step("brk", lambda: D.brk(o))
        for voff in (0.0, 5.0):
            o.voff = voff
            step(f"even_v{voff:g}", lambda: {k: v * 1e15 for k, v in D.even(o).items()})
        o.voff = 0.0
        step("ref", lambda: D.ref(o))
        r["sens_one"] = (r["even_v5"]["one"] - r["even_v0"]["one"]) / 5.0
        r["sens_all"] = (r["even_v5"]["all"] - r["even_v0"]["all"]) / 5.0
        out[variant] = r
        print(f"dac1 [{variant}] {corner} {temp:g} C ({time.time() - t0:.0f} s): even one {r['even_v0']['one']:+.5f} fC, "
              f"all {r['even_v0']['all']:+.5f} fC; per mV of OUTN - OUTP one {r['sens_one']:+.5f}, all {r['sens_all']:+.5f} "
              f"fC/mV; BRK {r['brk']['BRK width (ns)']:.3f} ns; extra VRP charge per toggle "
              f"{r['ref']['extra VRP charge per toggle (fC)']:+.4f} fC", flush=True)
    D.DAC1 = orig
    return out


def plan(length):
    import klayout.db as db
    ly = db.Layout()
    ly.read(GDS)
    top = ly.top_cell()
    boxes = {}
    for inst in top.each_inst():
        bb = inst.dbbox()
        boxes.setdefault(inst.cell.name, []).append((bb.left, bb.bottom, bb.right, bb.top))
    arr = ly.cell("rdac_r").dbbox()
    rdac = boxes["adc_rdac"][0]
    ota1 = boxes["gf180_inside_cascode_ota"][0]
    c1x = sorted(boxes["eeg_c1x"], key=lambda b: b[1])
    east = max(b[2] for k in ("adc_c2", "gf180_ct_ota_tel16_cmfb", "eeg_adc_clk", "adc_rst_tg") for b in boxes[k]
               if b[1] > 450 and b[3] < 1030)                       # the band's east parts
    m = RING_W + 0.8
    dx_blk = (rdac[2] - rdac[0]) - arr.width()                      # the block around its array (switches, logic)
    dy_blk = (rdac[3] - rdac[1]) - arr.height()

    def array(l, w, n, gap):
        return l + 2 * (m + RES_RX + PAD), 2 * (m + RES_RY) + n * (w + gap) - gap

    now = array(291.28, 1.0, 156, 0.6)
    out = dict(array_now_gds=(arr.width(), arr.height()), array_now=now, rdac_now=(rdac[2] - rdac[0], rdac[3] - rdac[1]),
               rdac_box=rdac, ota1_box=ota1, c1x=c1x, east=east, boxes=boxes, dx_blk=dx_blk, dy_blk=dy_blk,
               room_y=c1x[1][1] - c1x[0][3], strap_gap=ota1[0] - rdac[2], east_room=X_DVDD - east, options={})
    for gap in (0.4, 0.6):
        aw, ah = array(length, W_PU, 312, gap)
        out["options"][f"{gap}"] = dict(array=(aw, ah), block=(aw + dx_blk, ah + dy_blk),
                                        shift=aw + dx_blk - (rdac[2] - rdac[0]))
    print(f"plan: array now {arr.width():.1f} x {arr.height():.1f} um (formula {now[0]:.1f} x {now[1]:.1f}), block "
          f"{out['rdac_now'][0]:.1f} x {out['rdac_now'][1]:.1f}; room between the C1 remainders {out['room_y']:.1f} um, "
          f"to OTA1 {out['strap_gap']:.1f} um, east parts to the DVDD riser {out['east_room']:.1f} um")
    for gap, o in out["options"].items():
        print(f"  gap {gap} um: array {o['array'][0]:.1f} x {o['array'][1]:.1f}, block {o['block'][0]:.1f} x "
              f"{o['block'][1]:.1f}, band shift east {o['shift']:.1f} um")
    return out


def fig(d):
    import vizstyle
    vizstyle.CHIP_LABEL = "Study for the next assembly (12 Nov 2026)"
    from vizstyle import ACCENT, BAD, HAIR, INK, INK2, LIGHT, MUTED, figure
    import matplotlib.patches as mp
    u, p, k = d["unit"], d["plan"], d.get("dac1", {})
    o4 = p["options"]["0.4"]
    o6 = p["options"]["0.6"]
    shift = o4["shift"]
    fig_ = figure(13.6, 8.6, "RIN and DAC1 in ppolyf_u: does it fit, and what it changes",
                  f"Each 300 kΩ unit as two ppolyf_u strips of {u['length']:.2f} × {W_PU} µm (PRES.1) instead of one "
                  f"ppolyf_u_1k strip of 291.28 × 1 µm · the ADC's west band (adc_top, r10) with the generator's margins · "
                  f"DAC1 by dac1_check.py, typical, 27 °C",
                  note=f"Noise: ngspice .noise on adc_flicker.header() at the strings' {I_STR:.2f} µA; full scale with the "
                       f"PDK's level at that current (figure 33 of r10). Array: 312 strips (156 units), the margins of "
                       f"analog.res_cell (ring, RESISTOR, Metal2 pads) and the present block's overhead around the array "
                       f"({p['dx_blk']:.1f} µm across for the switches and logic, {p['dy_blk']:.1f} µm up). PRES.2 allows 0.4 µm "
                       f"between the strips; the present array uses 0.6. The band's parts east of rdac (OTA1, OTA2, C2, the "
                       f"chopper driver, the reset TGs, R21) would move east together; the DVDD riser is at x = {X_DVDD:.0f} µm. "
                       f"DAC1: the schematic cell (two units per side) with its units replaced, outputs at ideal virtual grounds; "
                       f"the loop HD3 is scaled from the 22 Oct behavioral model (ref_behav.py --steered: −0.031 fC/mV on a cell "
                       f"of 2·Iu·T = 1.63 pC gave −140.1 dBc, ten times that −120.1 dBc). "
                       f"Run: gf180/tapeout/sim/dac1/ppolyf_u_study.py.")
    gs = fig_.add_gridspec(1, 2, width_ratios=[1.0, 1.05])
    ax = fig_.add_subplot(gs[0, 0])
    keep = {"eeg_c1a": "C1 (MIM)", "eeg_c1x": "C1 remainder", "adc_rdac": "RIN + DAC1 (now)",
            "gf180_inside_cascode_ota": "OTA1", "gf180_ct_ota_tel16_cmfb": "OTA2", "adc_c2": "C2",
            "eeg_adc_clk": "chopper\ndriver", "adc_r21": "R21", "adc_zero": "ADC_ZERO", "eeg_quantizer": "quantizer",
            "eeg_dac2": "DAC2"}
    for name, lab in keep.items():
        for i, (x1, y1, x2, y2) in enumerate(p["boxes"].get(name, [])):
            ax.add_patch(mp.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=True, facecolor="#f1f5f9", edgecolor=LIGHT, lw=0.9))
            if name in ("adc_zero",) or (name == "adc_r21"):
                continue
            if (x2 - x1) > 60 and (y2 - y1) > 40:
                ax.text((x1 + x2) / 2, (y1 + y2) / 2, lab, fontsize=7.3, color=MUTED, ha="center", va="center")
    r = p["rdac_box"]
    c1x = p["c1x"]
    y0 = c1x[0][3] + 0.5 * (p["room_y"] - o4["block"][1])
    ax.add_patch(mp.Rectangle((r[0], y0), o4["block"][0], o4["block"][1], fill=False, edgecolor=ACCENT, lw=1.8))
    ax.text(r[0] + 8, y0 + o4["block"][1] - 8, f"ppolyf_u, gap 0.4 µm: {o4['block'][0]:.0f} × {o4['block'][1]:.0f} µm",
            fontsize=7.6, color=ACCENT, va="top")
    y6 = c1x[0][3] + 0.5 * (p["room_y"] - o6["block"][1])
    ax.add_patch(mp.Rectangle((r[0], y6), o6["block"][0], o6["block"][1], fill=False, edgecolor=BAD, lw=1.2, ls=(0, (4, 2.5))))
    ax.annotate(f"gap 0.6 µm (as now): {o6['block'][0]:.0f} × {o6['block'][1]:.0f} µm,\n"
                f"{o6['block'][1] - p['room_y']:.0f} µm more than the room between\nthe C1 remainders",
                (r[0] + 0.5 * o6["block"][0], y6 + o6["block"][1]), xytext=(r[0] + 20, 1110), textcoords="data",
                fontsize=7.3, color=BAD, va="bottom", bbox=dict(facecolor="white", edgecolor="none", pad=1.2),
                arrowprops=dict(arrowstyle="->", color=BAD, lw=0.9))
    zx = p["boxes"]["adc_zero"][0]
    ax.text(zx[2] + 4, (zx[1] + zx[3]) / 2, "ADC_ZERO (would move)", fontsize=6.8, color=MUTED, va="center")
    for name in ("gf180_inside_cascode_ota", "gf180_ct_ota_tel16_cmfb", "adc_c2", "eeg_adc_clk", "adc_r21"):
        for (x1, y1, x2, y2) in p["boxes"].get(name, []):
            ax.add_patch(mp.Rectangle((x1 + shift, y1), x2 - x1, y2 - y1, fill=False, edgecolor=ACCENT, lw=0.9,
                                      ls=(0, (3, 2))))
    ax.axvline(X_DVDD, color=INK2, lw=1.0, ls=(0, (1, 2)))
    ax.text(X_DVDD - 4, 1440, "DVDD riser", fontsize=7.3, color=INK2, ha="right", va="top")
    ax.annotate("", xy=(p["ota1_box"][0] + shift, 470), xytext=(p["ota1_box"][0], 470),
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=1.2))
    ax.text(p["ota1_box"][0] + shift + 6, 470, f"OTA1 and stage 2 east by {shift:.0f} µm\n(room to the riser: "
                                               f"{p['east_room']:.0f} µm)", fontsize=7.3, color=ACCENT, va="center")
    ax.set_xlim(-10, 1220)
    ax.set_ylim(-10, 1457)
    ax.set_aspect("equal")
    ax.set_xlabel("x in adc_top (µm)")
    ax.set_ylabel("y in adc_top (µm)")
    ax.set_title(f"Fits with 0.4 µm gaps if the band moves east by {shift:.0f} µm", fontsize=9.5)

    ax = fig_.add_subplot(gs[0, 1])
    ax.axis("off")
    rows = [("Unit (300 kΩ)", "ppolyf_u_1k (now)", "ppolyf_u"),
            ("Strips, poly area", "1 × 291.28 × 1 µm, 291 µm²", f"2 × {u['length']:.2f} × {W_PU} µm, {u['areapu']:.0f} µm²"),
            ("Resistance, 27 °C typical", f"{u['r1k'] / 1e3:.2f} kΩ", f"{u['rpu'] / 1e3:.2f} kΩ"),
            (f"Flicker at {I_STR:.2f} µA, 10 Hz", f"{u['nv1k']:.0f} nV/√Hz", f"{u['nvpu']:.0f} nV/√Hz (×{u['ratio']:.3f})"),
            ("Full scale (PDK level at our current)", f"{u['fs_nv_1k']:.2f} nVrms, {u['enob_1k']:.2f} bit",
             f"{u['fs_nv_pu']:.2f} nVrms, {u['enob_pu']:.2f} bit")]
    for key, lab in (("res_typical -40", "typical, −40 / 85 °C"), ("res_ff 85", "ff, 85 °C (fastest RC)"),
                     ("res_ss -40", "ss, −40 °C (slowest)")):
        a, b = u["corners"][key]
        if key == "res_typical -40":
            a2, b2 = u["corners"]["res_typical 85"]
            rows.append((f"R / typical 27 °C, {lab}", f"{a:.3f} / {a2:.3f}", f"{b:.3f} / {b2:.3f}"))
        else:
            rows.append((f"R / typical 27 °C, {lab}", f"{a:.3f}", f"{b:.3f}"))
    if k:
        g = lambda v: f"{v:+.5f}"                                                # noqa: E731
        # loop HD3 of the per-mV term, scaled from the 22 Oct behavioral model (ref_behav.py --steered:
        # -0.031 fC/mV on the cell of one unit per side, 2 Iu T = 1.63 pC, gave -140.1 dBc, ten times that
        # -120.1 dBc); the cell now has two units per side, 2 Iu T = 0.81 pC, so the same fC/mV is twice
        # the relative error
        q_el = 2 * 0.25 / (2 * u["r1k"]) / 1.024e6
        q_22 = 2 * 0.25 / 300e3 / 1.024e6
        hd3 = lambda s: -140.1 + 20 * np.log10(abs(s) / q_el / (0.031 / q_22))  # noqa: E731
        rows += [("DAC1 even error per toggle, one / all cells", f"{g(k['1k']['even_v0']['one'])} / {g(k['1k']['even_v0']['all'])} fC",
                  f"{g(k['pu']['even_v0']['one'])} / {g(k['pu']['even_v0']['all'])} fC"),
                 ("   per mV of OUTN − OUTP (one cell)", f"{k['1k']['sens_one']:+.4f} fC/mV", f"{k['pu']['sens_one']:+.4f} fC/mV"),
                 ("   loop HD3 from that (scaled, see note)", f"≈ {hd3(k['1k']['sens_one']):.0f} dBc",
                  f"≈ {hd3(k['pu']['sens_one']):.0f} dBc"),
                 ("   requirement (1e-5 of 2·Iu·T = 0.81 pC)", "0.008 fC", ""),
                 ("Extra VRP charge per toggle", f"{k['1k']['ref']['extra VRP charge per toggle (fC)']:+.3f} fC",
                  f"{k['pu']['ref']['extra VRP charge per toggle (fC)']:+.3f} fC"),
                 ("BRK width, BRK to D / DB fall", f"{k['1k']['brk']['BRK width (ns)']:.2f}, "
                  f"{k['1k']['brk']['BRK to D fall, 1 -> 0 (ns)']:.2f} / {k['1k']['brk']['BRK to DB fall, 0 -> 1 (ns)']:.2f} ns",
                  f"{k['pu']['brk']['BRK width (ns)']:.2f}, {k['pu']['brk']['BRK to D fall, 1 -> 0 (ns)']:.2f} / "
                  f"{k['pu']['brk']['BRK to DB fall, 0 -> 1 (ns)']:.2f} ns")]
    rows += [("Resistor array (156 / 312 strips)", f"{p['array_now_gds'][0]:.0f} × {p['array_now_gds'][1]:.0f} µm",
              f"{o4['array'][0]:.0f} × {o4['array'][1]:.0f} µm (gap 0.4)"),
             ("adc_rdac block", f"{p['rdac_now'][0]:.0f} × {p['rdac_now'][1]:.0f} µm",
              f"{o4['block'][0]:.0f} × {o4['block'][1]:.0f} µm"),
             ("Room: between the C1 remainders / to OTA1", f"{p['room_y']:.0f} µm / {p['strap_gap']:.0f} µm", "")]
    xs = (0.0, 0.43, 0.70)
    for xc, h_ in zip(xs, rows[0]):
        ax.text(xc, 1.0, h_, fontsize=8.2, fontweight="semibold", color=INK, va="top", transform=ax.transAxes)
    ax.plot([0, 1], [0.962, 0.962], color=HAIR, lw=1.0, transform=ax.transAxes, clip_on=False)
    step = 0.93 / (len(rows) - 1)
    for i, row in enumerate(rows[1:]):
        y = 0.94 - i * step
        for xc, txt in zip(xs, row):
            ax.text(xc, y, txt.replace("-", "−") if xc else txt, fontsize=7.5, color=INK2 if xc else INK, va="top",
                    transform=ax.transAxes)
    ax.set_title("What changes", fontsize=9.5)
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, "gf180_rdac_ppolyf_u_20261112.png")
    fig_.savefig(path)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*", default=["unit", "dac1", "plan", "fig"])
    ap.add_argument("--corner", default="typical")
    ap.add_argument("--temp", type=float, default=27.0)
    a = ap.parse_args()
    os.chdir(REPO)
    d = load()
    if "unit" in a.parts:
        d["unit"] = unit()
        save(d)
    if "plan" in a.parts:
        d["plan"] = plan(d["unit"]["length"])
        save(d)
    if "dac1" in a.parts:
        d["dac1"] = dac1(d["unit"]["length"], a.corner, a.temp)
        save(d)
    if "fig" in a.parts:
        fig(d)


if __name__ == "__main__":
    main()
