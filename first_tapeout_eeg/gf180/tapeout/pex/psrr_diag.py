#!/usr/bin/env python3
"""PSRR diagnostic (11/19, r12): where the conversion between the choppers comes from.

psrr.py found that AVDD ripple appears between the AFE's two choppers as a differential at the amplifier's output
(OPI - ONI, 1.10 V/V next to 128 kHz on the typical die, 1.05-1.13 V/V on Monte Carlo dies, 0.99-1.23 V/V on the MOS
corners), which the output chopper folds into band (52.4 dB next to 128 kHz on the typical die, 51.5 dB at ff). A static
scan of afe_top's extraction (explicit capacitances on the amplifier's summing nodes, in the typical AVDD-ripple deck)
shows INN with more capacitance than INP to nets that carry the AVDD ripple: AVDD 4528.07 against 2571.42 fF
(+1.957 pF), VBP 534.58 against 0.12 fF (+0.534 pF), BLP 155.84 fF against INP-BLN 0 fF; through the feedback
capacitance (Cin / gain = 636 pF / 297.47 = 2.14 pF) the first two give (1.957 + 0.534) / 2.14 = 1.17 V/V.

The diagnostic decks (runs/psrr_r12/diag_*, made by scaling those capacitances in a copy of a typical AVDD-ripple deck;
run_psrr_diag.sh, run_psrr_diag_c.sh): A matches INN-AVDD to INP's, B also INN-VBP and INN-BLP (to INP-BLN's), both
with legs of 100 ohm; C is B with ELP 100 ohm + 51 kohm || 47 nF. They are not a design change. Each is fitted alone
(no baselines; on the typical run the folded tones agree with the baseline fit to 1e-5) and compared with the typical
run of the same legs. The noise allowance (the regulator noise next to the chopper's harmonics that adds 5 % to the AFE's
own noise) scales with the folded tone: psrr.py's value for that typical run times the ratio of the folded tones.

Results (11/19): A 0.241 V/V (65.6 dB next to 128 kHz, 74.4 dB next to 384 kHz), B 0.058 V/V (78.0 dB, 87.7 dB),
against 1.100 V/V (52.4 dB, 61.2 dB): the extra couplings on INN make about 95 % of the conversion (A takes out 0.86 V/V
where the static estimate says 0.92). The MOS corners move it because the corner also sets the MIM capacitors (the
PDK's mimcap_ff 0.9, mimcap_ss 1.1 for the 2 fF/um2 MIM): Cf is MIM, the wiring is not, so the conversion goes as
1 / (the MIM factor) (ff 1.228 against 1.100 / 0.9 = 1.222, ss 0.994 against 1.000), while the AFE's gain (Cin / Cf,
both MIM) moves 1 % or less (the corner sine runs at 3.3 V: ff +0.9 %, ss -1.0 %).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr_diag.py --make     (writes runs/psrr_r12/diag_A, _B, _C)
       gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr_diag.py --layout   (runs/psrr_r12/diag_layout.json)
       gf180/tools/venv310/bin/python gf180/tapeout/pex/psrr_diag.py            (runs/psrr_r12/diag.json)
"""
import json
import os
import re
import sys

import numpy as np

import cmrr as C
import psrr as P

CIN_PF = P.CIN_PF
TYP = "start_c1e-08_v3.3_typical_+0mV_afe5ms_ib3_cm0mV50Hz_ripAVDD10mV_chip_r12"
TYP_IMB = "start_c1e-08_v3.3_typical_+0mV_afe5ms_ib3_cm0mV50Hz_zp100+51k_47n_ripAVDD10mV_chip_r12"
PAIRS = (("AVDD", "AVDD"), ("VBP", "VBP"), ("BLP", "BLN"), ("AVSS", "AVSS"), ("CORE.SP", "CORE.SP"))  # INN's, INP's
DIAG = (("A", TYP), ("B", TYP), ("C", TYP_IMB))
CORNERS = ("ff", "ss", "sf", "fs")
SINE = "start_c1e-08_v3.3_{}_+0mV_sine0.943mV2000Hz_afe5ms_ib3_chip_r12"       # figure 41's corner runs (3.3 V)
HI = sum(1 / k ** 2 for k in range(5, 2001, 2))                                  # the odd harmonics above 3, (2/pi)/k each


SCALE = {"A": ("AVDD",), "B": ("AVDD", "VBP", "BLP"), "C": ("AVDD", "VBP", "BLP")}
MATE = {"AVDD": "AVDD", "VBP": "VBP", "BLP": "BLN"}                             # INN's net -> INP's counterpart


def make_decks():
    """the diagnostic decks: a copy of the typical deck (of the same legs) with the explicit capacitors between INN and
    each net of SCALE scaled to INP's counterpart (11/19: A and B at 03:14, C at 09:57)"""
    for v, src in DIAG:
        lines = open(os.path.join(P.RUNS, src, "tb.spice")).read().splitlines()
        i0 = next(i for i, x in enumerate(lines) if x.startswith(".subckt afe_top"))
        i1 = next(i for i in range(i0, len(lines)) if lines[i].startswith(".ends"))

        def total(a, b, ls):
            return sum(float(t[3]) for t in (x.split() for x in ls[i0 + 1:i1]) if t and t[0][0] == "C" and {t[1], t[2]} == {a, b})

        out, note = list(lines), []
        for x in SCALE[v]:
            want, have = total("INP", MATE[x], lines), total("INN", x, lines)
            for i in range(i0 + 1, i1):
                t = out[i].split()
                if t and t[0][0] == "C" and {t[1], t[2]} == {"INN", x}:
                    t[3] = f"{float(t[3]) * want / have:.6e}"
                    out[i] = " ".join(t)
            note.append(f"INN-{x} {have * 1e15:.2f} -> {total('INN', x, out) * 1e15:.2f} fF (INP's {want * 1e15:.2f})")
        d = os.path.join(P.OUT, f"diag_{v}")
        os.makedirs(d, exist_ok=True)
        out[0] += f" [psrr diagnostic {v}: " + "; ".join(note) + "]"
        open(os.path.join(d, "tb.spice"), "w").write("\n".join(out) + "\n")
        m = json.load(open(os.path.join(P.RUNS, src, "meta.json"), encoding="utf-8"))
        m["diag"] = {"from": src, "scaled": note}
        json.dump(m, open(os.path.join(d, "meta.json"), "w"), indent=1)
        print(v, "; ".join(note))


# afe_top's KLayout LVS database (the run pex.py maps the r12 extraction with) and its layers, from the connectivity
# records: contact 33/0 (l8) - Metal1 l13 - via1 35/0 (l14) - Metal2 l15 - l16 - Metal3 l17 (label 42/10) - l19 - Metal4 l20
# (label 46/10) - l22 - Metal5 l23 (label 81/10); the n-well l6 (with its n-tap l7); poly l12
LVSDB = os.path.join(P.HERE, "..", "layout", "runs", "afe_top", "afe_top.lvsdb")
LVS_LAYERS = {"M3": "l17", "M4": "l20", "M5": "l23", "nwell": "l6", "poly": "l12"}
SHOW = (("INN", "M3"), ("INN", "M4"), ("INN", "M5"), ("INP", "M3"), ("INP", "M4"), ("INP", "M5"), ("AVDD", "nwell"),
        ("AVDD", "M5"), ("VBP", "poly"))


def layout_scan():
    """where the summing nodes' extra couplings sit: their Metal3-5 shapes, AVDD's n-wells and Metal5, VBP's poly
    (merged polygons, um) and the overlap areas between them, from afe_top's LVS database (runs/psrr_r12/diag_layout.json)"""
    import klayout.db as kdb
    lv = kdb.LayoutVsSchematic()
    lv.read(LVSDB)
    xr = lv.xref()
    nets = {}
    for cp in xr.each_circuit_pair():
        if cp.first() is None or cp.second() is None or cp.first().name.upper() != "AFE_TOP":
            continue
        for npair in xr.each_net_pair(cp):
            if npair.first() is not None and npair.second() is not None and npair.second().name in ("INN", "INP", "AVDD", "VBP"):
                nets[npair.second().name] = npair.first()
    dbu = lv.internal_layout().dbu
    reg = {(n, x): lv.shapes_of_net(nets[n], lv.layer_by_name(LVS_LAYERS[x]), True).merged() for n, x in SHOW}
    out = dict(bbox_um=list(lv.internal_layout().top_cell().dbbox().to_s().replace(";", ",").replace("(", "").replace(")", "").split(",")),
               area_um2={f"{n} {x}": r.area() * dbu * dbu for (n, x), r in reg.items()}, overlap_um2={}, polygons={})
    out["bbox_um"] = [float(v) for v in out["bbox_um"]]
    for s in ("INN", "INP"):
        for m in ("M3", "M4", "M5"):
            for t in (("AVDD", "nwell"), ("AVDD", "M5"), ("VBP", "poly")):
                if m == "M5" and t == ("AVDD", "M5"):
                    continue
                out["overlap_um2"][f"{s} {m} / {t[0]} {t[1]}"] = (reg[(s, m)] & reg[t]).area() * dbu * dbu
    for (n, x), r in reg.items():
        out["polygons"][f"{n} {x}"] = [[[round(pt.x * dbu, 2), round(pt.y * dbu, 2)] for pt in p.resolved_holes().each_point_hull()]
                                       for p in r.each()]          # holes cut to the hull
    json.dump(out, open(os.path.join(P.OUT, "diag_layout.json"), "w"))
    for k, v in out["area_um2"].items():
        print(f"{k}: {v:,.0f} um2 in {len(out['polygons'][k])} pieces")
    for k, v in out["overlap_um2"].items():
        print(f"  overlap {k}: {v:,.0f} um2")


def static_scan(deck):
    """the explicit capacitances on the summing nodes INP and INN in the deck's afe_top (fF): per other net, and in all"""
    lines = open(deck).read().splitlines()
    i0 = next(i for i, x in enumerate(lines) if x.startswith(".subckt afe_top"))
    i1 = next(i for i in range(i0, len(lines)) if lines[i].startswith(".ends"))
    per = {"INP": {}, "INN": {}}
    for x in lines[i0 + 1:i1]:
        t = x.split()
        if not t or t[0][0] != "C" or len(t) < 4:
            continue
        for a, b in ((t[1], t[2]), (t[2], t[1])):
            if a in per:
                per[a][b] = per[a].get(b, 0.0) + float(t[3]) * 1e15
    return per


def mim_factor(deck):
    """the PDK's 2 fF/um2 MIM corner factor of each MOS corner, from the deck's model library"""
    lib = next(re.search(r"^\.lib (\S+) mimcap_", x).group(1) for x in open(deck) if re.search(r"^\.lib \S+ mimcap_", x))
    txt = open(lib).read()
    out = {}
    for c in ("typical", "ff", "ss"):
        sec = txt.split(f".lib mimcap_{c}", 1)[1].split(".endl", 1)[0]
        out[c] = float(re.search(r"mim_corner_2p0ff\s*=\s*([0-9.]+)", sec).group(1))
    out["sf"] = out["fs"] = out["typical"]
    return out


def sine_gain(run):
    """the AFE's gain on a sine run, as cmrr.gain() takes it on figure 38's typical run"""
    v, m = C.load(os.path.join(C.RUNS, run), ["qo"])
    edges = m["t_reset"] + C.TCH / 4 + C.TCH * np.arange(int((v["t"][-1] - m["t_reset"] - C.TCH / 4) / C.TCH) + 1)
    y = C.means(v["t"], v["qo"], edges)
    tc = 0.5 * (edges[1:] + edges[:-1])
    a = tc >= v["t"][-1] - 1.5e-3
    ph, _ = C.fit(tc[a], y[a], m["fsig"], nh=1, poly=1)
    px, _ = C.fit(tc[a], C.sine_means(tc[a], m["sine"] * 1e-3, m["fsig"], m["t_afe"] + 20e-6), m["fsig"], nh=1, poly=1)
    return float(abs(ph[0] / px[0]))


def together(a1, a3):
    """the noise next to 128 and 384 kHz together, and with the odd harmonics above 3 (the conversion taken as flat)"""
    w = 1 / np.sqrt(1 / a1 ** 2 + 1 / a3 ** 2)
    return float(w), float(1 / np.sqrt(1 / w ** 2 + HI / a1 ** 2))


def main():
    g = C.gain()
    cf = CIN_PF / abs(g)
    deck = os.path.join(P.RUNS, TYP, "tb.spice")
    per = static_scan(deck)
    static = {f"{n}/{p}": (round(per["INP"].get(p, 0.0), 2), round(per["INN"].get(n, 0.0), 2)) for n, p in PAIRS}
    print(f"static (fF, INP / INN): " + ", ".join(f"{k} {a:.2f} / {b:.2f}" for k, (a, b) in static.items())
          + f"; in all INP {sum(per['INP'].values()) / 1e3:.2f} pF, INN {sum(per['INN'].values()) / 1e3:.2f} pF")
    dc = {k: (b - a) * 1e-3 for k, (a, b) in static.items()}
    pred = {"typical": (dc["AVDD/AVDD"] + dc["VBP/VBP"]) / cf, "A": dc["VBP/VBP"] / cf, "B": 0.0}
    out = dict(gain=g, cf_eff_pf=cf, static_ff=static, static_pred_vv=pred, runs=[], corners=[],
               static_total_pf={k: round(sum(v.values()) / 1e3, 3) for k, v in per.items()})

    allres = {(r["zp"], r["zn"]): r for r in json.load(open(os.path.join(P.OUT, "results.json"), encoding="utf-8"))["runs"]
              if r["supply"] == "AVDD" and r["corner"] == "typical" and r["seed"] is None and r["base"]}
    for name, d, ref in [("typical", os.path.join(P.RUNS, TYP), None), ("typical, ELP 51k||47n", os.path.join(P.RUNS, TYP_IMB), None)] \
            + [(v, os.path.join(P.OUT, f"diag_{v}"), src) for v, src in DIAG]:
        if not os.path.exists(os.path.join(d, "tr.csv")):
            print(f"{name}: not run yet")
            continue
        m = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        r = P.analyse(d, m, None, g)
        if r is None or not r["done"]:
            print(f"{name}: not at {P.T1 * 1e3:g} ms or stopped")
            continue
        base = allres[(m["zp"], m["zn"])]                        # psrr.py's typical run of the same legs (with baseline)
        bt = {x["harmonic"]: x for x in base["tones"]}
        for x in r["tones"]:
            if bt[x["harmonic"]].get("allowed_nv_rthz"):
                x["allowed_nv_rthz"] = bt[x["harmonic"]]["allowed_nv_rthz"] * bt[x["harmonic"]]["vdm_uv"] / x["vdm_uv"]
        by = {x["harmonic"]: x for x in r["tones"]}
        r["name"], r["diag"], r["legs"] = name, m.get("diag"), m["zp"]
        r["allowed_13"], r["allowed_odd"] = together(by[1]["allowed_nv_rthz"], by[3]["allowed_nv_rthz"])
        out["runs"].append(r)
        print(f"{name} ({m['zp']}): between the choppers {by[0]['between_vv']:.3f} V/V at 1 kHz, {by[1]['between_vv']:.3f} / "
              f"{by[2]['between_vv']:.3f} / {by[3]['between_vv']:.3f} V/V next to 128 / 256 / 384 kHz; in band "
              f"{by[1]['vdm_uv']:.3f} uV ({by[1]['psrr_board_db']:.1f} dB) at 1.25 kHz, {by[3]['vdm_uv']:.3f} uV "
              f"({by[3]['psrr_board_db']:.1f} dB) at 1.75 kHz; 1 kHz {by[0]['psrr_board_db']:.1f} dB, 257.5 kHz "
              f"{by[2]['psrr_board_db']:.1f} dB; allowed next to 128 and 384 kHz {r['allowed_13']:.1f} nV/rtHz "
              f"({r['allowed_odd']:.1f} with the odd harmonics above 3)")
    print(f"static estimate (VBP following AVDD fully, through Cf_eff {cf:.3f} pF): "
          + ", ".join(f"{k} {v:.2f} V/V" for k, v in pred.items()))

    # the MOS corners: the conversion against the MIM factor, and the AFE's gain on the corner sine runs
    mim = mim_factor(deck)
    stat = [r for r in json.load(open(os.path.join(P.OUT, "results.json"), encoding="utf-8"))["runs"]
            if r["supply"] == "AVDD" and r["zp"] == "100" and r["zn"] == "100" and r["seed"] is None]
    typ = next(r for r in stat if r["corner"] == "typical" and r["base"])
    t1 = next(x for x in typ["tones"] if x["harmonic"] == 1)["between_vv"]
    g0 = sine_gain(SINE.format("typical"))
    for c in ("typical",) + CORNERS:
        r = next((x for x in stat if x["corner"] == c and (c != "typical" or x["base"])), None)
        if r is None:
            continue
        by = {x["harmonic"]: x for x in r["tones"]}
        gc = sine_gain(SINE.format(c))
        row = dict(corner=c, mim=mim[c], between_vv=by[1]["between_vv"], between_1k_vv=by[0]["between_vv"],
                   pred_vv=t1 / mim[c], psrr_db=by[1]["psrr_board_db"], gain=gc, gain_ratio=gc / g0)
        out["corners"].append(row)
        print(f"{c:8s} MIM x{mim[c]:.3f}: {row['between_vv']:.3f} V/V next to 128 kHz (typical / MIM {row['pred_vv']:.3f}), "
              f"{row['between_1k_vv']:.3f} V/V at 1 kHz; the AFE's gain {gc:.2f} ({gc / g0 - 1:+.2%})")
    json.dump(out, open(os.path.join(P.OUT, "diag.json"), "w"), indent=1)


if __name__ == "__main__":
    if "--make" in sys.argv[1:]:
        make_decks()
    elif "--layout" in sys.argv[1:]:
        layout_scan()
    else:
        main()
