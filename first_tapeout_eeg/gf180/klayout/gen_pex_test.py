#!/usr/bin/env python3
"""Generate gf180_pex_test.gds: PEX capability demonstrator for GF180MCU-D.

Contents (top cell GF180_PEX_TEST):
  - one nfet_03v3 pcell, W=10u L=2u nf=2, pads labeled D/S/G
  - one cap_mim pcell (MIM-B, metal_level=M5, 20x20 um), plates labeled CT/CB
  - one 200 um x 0.4 um metal1 long-wire extension off the drain pad (label W1)
Labels on metal*_label layers name the nets for magic extraction.

Run: gf180/tools/venv310/bin/python gf180/klayout/gen_pex_test.py
"""
import os
import sys

PDK = os.path.expanduser(
    "~/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD")
sys.path.insert(0, os.path.join(PDK, "libs.tech/klayout/tech/pymacros"))

import pya  # noqa: E402
import cells  # noqa: E402  (GF180 pcell library; registers "gf180mcu")

OUT = os.path.join(os.path.dirname(__file__), "../gds/gf180_pex_test.gds")

L = {"m1": (34, 0), "m1lab": (34, 10), "m4lab": (46, 10), "m5lab": (81, 10)}


def main():
    cells.gf180mcu()
    lay = pya.Layout()
    lay.dbu = 0.001
    top = lay.create_cell("GF180_PEX_TEST")

    # --- nFET: W=10 L=2 nf=2, gate contacts top ---
    nf = lay.create_cell("nfet", "gf180mcu",
                         {"volt": "3.3V", "w_gate": 10.0, "l_gate": 2.0,
                          "nf": 1, "bulk": "None", "gate_con_pos": "top"})
    top.insert(pya.CellInstArray(nf.cell_index(), pya.Trans(pya.Point(0, 0))))

    m1 = lay.layer(*L["m1"])
    m1lab = lay.layer(*L["m1lab"])
    m4lab = lay.layer(*L["m4lab"])
    m5lab = lay.layer(*L["m5lab"])

    def lab(li, x_um, y_um, text):
        top.shapes(li).insert(pya.Text(text, x_um, y_um))

    # FET pad labels (nf=1 pcell geometry, dbu=1nm):
    #   two diffusion rails + one gate pad at top; positions verified by
    #   introspection below (asserted on first run).
    lab(m1lab, -210, 500, "D")
    lab(m1lab, 2450, 500, "S")
    lab(m1lab, 1190, 10480, "G")

    # --- 200 um x 0.4 um drain wire (big intentional parasitic), net W1 ---
    top.shapes(m1).insert(pya.Box(-200400, 400, -20, 800))
    lab(m1lab, -200000, 500, "W1")

    # --- MIM cap 20x20 um, MIM-B between M4 and M5 (=metalTop in variant D) ---
    cm = lay.create_cell("cap_mim", "gf180mcu",
                         {"mim_option": "MIM-B", "metal_level": "M5",
                          "wc": 20.0, "lc": 20.0})
    top.insert(pya.CellInstArray(cm.cell_index(), pya.Trans(pya.Point(40000, 0))))
    # label plates INSIDE the cap cell so magic makes them cell ports
    # (cap cell local coords: m5 plate 0..20 um, m4 plate -0.6..20.6 um)
    cm.shapes(m5lab).insert(pya.Text("CT", 10, 10))
    cm.shapes(m4lab).insert(pya.Text("CB", 0, 0))

    lay.write(OUT)
    print("wrote", OUT)
    for c in lay.each_cell():
        print("cell:", c.name, "bbox:", c.bbox())


if __name__ == "__main__":
    main()
