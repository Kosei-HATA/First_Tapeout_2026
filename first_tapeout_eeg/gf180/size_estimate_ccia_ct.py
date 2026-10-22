#!/usr/bin/env python3
"""GF180 area tally for the independent-environment candidate (2026-10-21):
CCIA AFE (gain 318, Cin 636p, Cpf 2.10p) + CT 2nd-order 5-bit ADC (gain10).

MOS are counted from the connected deck (flattened hierarchy). Each m-multiplied
FET is costed as nf=32 multi-finger devices using pcell bboxes measured by
gf180/klayout/measure_candidate_fets.py (bulk=None, no guard ring).
MIM at 2.0 fF/um2; resistors at ppolyf_u 3k ohm/sq with a 2W serpentine pitch.
Blocks that are still ideal/behavioral in the deck (quantizer, DAC switches,
bias, references, digital, clock drivers, decap, DC servo) are explicit
low/high estimates.

Run: python3 gf180/size_estimate_ccia_ct.py <deck_dir>
  deck_dir = .../enob18_20261015/ct_candidate/afe_adc_cap2_direct_threshold1u_20261020
  (circuit.spice + afe_model.spice + otas.spice + quantizer.spice)
"""
import hashlib
import math
import os
import re
import sys

# pcell bbox per finger / per device (um2), measured 2026-10-21 (nf=1 and nf=32)
FET_FOOTPRINT = {  # (type, w_finger_um, l_um): (per_finger, fixed)
    ("nfet", 10.0, 0.28): (9.07, 11.8), ("pfet", 10.0, 0.28): (9.79, 24.5),
    ("nfet", 10.0, 1.0): (17.24, 11.8), ("pfet", 10.0, 1.0): (18.60, 24.5),
    ("nfet", 10.0, 2.0): (28.58, 11.8), ("pfet", 10.0, 2.0): (30.84, 24.5),
    ("nfet", 10.0, 4.0): (51.26, 11.8), ("pfet", 10.0, 4.0): (55.32, 24.5),
    ("nfet", 20.0, 0.28): (17.07, 22.2), ("pfet", 40.0, 0.28): (33.79, 84.5),
    ("nfet", 1.0, 1.0): (3.56, 2.4), ("nfet", 1.0, 0.28): (1.87, 2.4),
    ("pfet", 2.0, 0.28): (3.39, 8.5),
}
FINGERS_PER_DEVICE = 32
MIM_F = 2.0e-15  # F/um2
RHO_HIGH = 3000.0  # ppolyf_u high-Rs, ohm/sq

SLOTS = {  # core inside the default pad ring (wafer.space, read 2026-10-21)
    "Half Width 0.5x1 (1.05 x 4.24 mm)": 4.46,
    "Half Height 1x0.5 (3.05 x 1.65 mm)": 5.02,
}

UNITS = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6,
         "n": 1e-9, "p": 1e-12, "f": 1e-15}


def value(tok, params):
    tok = tok.strip()
    if tok.startswith("{") and tok.endswith("}"):
        expr = tok[1:-1].lower()
        for k, v in params.items():
            expr = re.sub(rf"\b{re.escape(k)}\b", repr(v), expr)
        return float(eval(expr, {"__builtins__": {}}, {}))
    if tok.lower() in params:
        return params[tok.lower()]
    m = re.fullmatch(r"([-+0-9.eE]+)([a-zA-Z]*)", tok)
    if not m:
        raise ValueError(f"cannot parse value {tok!r}")
    num, suf = float(m.group(1)), m.group(2).lower()
    for s in ("meg", "t", "g", "k", "m", "u", "n", "p", "f"):
        if suf.startswith(s):
            return num * UNITS[s]
    return num


def read_deck(files):
    lines = []
    for f in files:
        for raw in open(f):
            raw = raw.rstrip("\n")
            if raw.startswith("+") and lines:
                lines[-1] += " " + raw[1:]
            else:
                lines.append(raw)
    subckts, top, cur, control = {}, [], None, False
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("*"):
            continue
        low = s.lower()
        if low.startswith(".control"):
            control = True
        elif low.startswith(".endc"):
            control = False
        elif control:
            continue
        elif low.startswith(".subckt"):
            tok = s.split()
            name = tok[1].lower()
            ports, params = [], {}
            for t in tok[2:]:
                if t.lower() == "params:":
                    continue
                if "=" in t:
                    k, v = t.split("=", 1)
                    params[k.lower()] = v
                else:
                    ports.append(t)
            cur = subckts[name] = {"ports": ports, "params": params, "body": []}
        elif low.startswith(".ends"):
            cur = None
        elif not s.startswith("."):
            (cur["body"] if cur else top).append(s)
    return subckts, top


def flatten(subckts, body, params, mult, path, out):
    for s in body:
        tok = s.split()
        kind = tok[0][0].upper()
        if kind == "X":
            kv = {t.split("=", 1)[0].lower(): t.split("=", 1)[1]
                  for t in tok[1:] if "=" in t}
            pos = [t for t in tok[1:] if "=" not in t]
            model = pos[-1].lower()
            m = value(kv.get("m", "1"), params)
            if model in ("nfet_03v3", "pfet_03v3"):
                out.append({"path": path + [tok[0]], "kind": "M",
                            "type": model[:4], "W": value(kv["w"], params),
                            "L": value(kv["l"], params),
                            "nf": int(value(kv.get("nf", "1"), params)),
                            "m": mult * m})
            elif model in subckts:
                sc = subckts[model]
                p = {k: value(v, params) for k, v in sc["params"].items()}
                p.update({k: value(v, params) for k, v in kv.items() if k != "m"})
                flatten(subckts, sc["body"], p, mult * m, path + [tok[0]], out)
            else:
                out.append({"path": path + [tok[0]], "kind": "X?", "model": model})
        elif kind in "CR":
            out.append({"path": path + [tok[0]], "kind": kind,
                        "val": value(tok[3], params), "m": mult})


def fet_area(e):
    w_f = round(e["W"] * 1e6 / e["nf"], 3)
    key = (e["type"], w_f, round(e["L"] * 1e6, 3))
    if key not in FET_FOOTPRINT:
        raise KeyError(f"no measured footprint for {key}: add it to measure_candidate_fets.py")
    per_finger, fixed = FET_FOOTPRINT[key]
    fingers = e["nf"] * e["m"]
    return math.ceil(fingers / FINGERS_PER_DEVICE) * fixed + fingers * per_finger


def res_area(r_ohm, w_um=1.0):
    return r_ohm / RHO_HIGH * 2.0 * w_um * w_um  # serpentine pitch 2W


def block_of(e):
    top = e["path"][0].upper()
    if top.startswith(("XAFE_", "CAFE_")):
        return "AFE"
    if top == "XOTA1":
        return "ADC OTA1"
    if top == "XOTA2":
        return "ADC OTA2"
    if re.fullmatch(r"XR[12][PN]", top):
        return "ADC reset TG"
    if re.fullmatch(r"(C[12][PN]|CL[12][PN])", top):
        return "ADC"
    return None  # testbench / ideal source models


def main():
    d = sys.argv[1]
    files = [os.path.join(d, f) for f in
             ("circuit.spice", "afe_model.spice", "otas.spice", "quantizer.spice")]
    subckts, top = read_deck(files)
    elems = []
    flatten(subckts, top, {}, 1, [], elems)

    mos, mim = {}, {}
    for e in elems:
        b = block_of(e)
        if b is None:
            continue
        if e["kind"] == "M":
            mos[b] = mos.get(b, 0.0) + fet_area(e)
        elif e["kind"] == "C":
            c = e["val"] * e["m"]
            if e["path"][0].upper().startswith("CAFE_PF"):
                c = 2.10e-12  # 10/21 candidate cpf210 (deck has 2.06p)
            mim[b] = mim.get(b, 0.0) + c

    rows = []  # (block, item, low_um2, high_um2, basis)
    for b, a in sorted(mos.items()):
        rows.append((b, "MOS (pcell bbox x1.5 / x2.5 for guard ring, dummies, routing)",
                     1.5 * a, 2.5 * a, f"bare {a/1e6:.3f} mm2"))
    for b, c in sorted(mim.items()):
        a = c / MIM_F
        rows.append((b if b != "ADC" else "ADC integrators", "MIM (x1.12 / x1.25)",
                     1.12 * a, 1.25 * a, f"{c*1e12:.1f} pF"))
    # ADC resistors: deck lumps each DAC into one R; physical = 31 units per side
    r_in = 2 * res_area(9375, 5.0)
    r_21 = 2 * res_area(1e6)
    dac1 = 62 * res_area(300e3, 2.0)
    dac2 = 62 * res_area(320e6 / 3)
    rows.append(("ADC resistors", "RIN 9375 x2, R21 1M x2, DAC1 300k x62 (x1.3 / x1.6)",
                 1.3 * (r_in + r_21 + dac1), 1.6 * (r_in + r_21 + dac1), "W=5/1/2 um"))
    rows.append(("ADC DAC2 (as drawn)", "106.7 Meg unit x62 (x1.1 / x1.3)",
                 1.1 * dac2, 1.3 * dac2, f"{dac2/1e6:.2f} mm2 bare"))
    # area-optimal DAC2: same R*C, C2 per side chosen to minimise R+C area
    k_rc = (320e6 / 3) * 1.953125e-12
    c2_opt = math.sqrt(62 * 2.0 / RHO_HIGH * k_rc / (2 / MIM_F))
    dac2_opt = 62 * res_area(k_rc / c2_opt) + 2 * c2_opt / MIM_F * 1.12
    rows.append(("ADC DAC2 (rescaled)", f"C2 {c2_opt*1e12:.0f} pF/side, unit "
                 f"{k_rc/c2_opt/1e6:.2f} Meg x62", 1.1 * dac2_opt, 1.3 * dac2_opt,
                 "same R*C; OTA2 must drive C2"))
    # MOS current-steering DAC2 with stage 2 scaled x10 (C2 19.5p, R21 100k):
    # 62 cells (~23 nA, long-channel source + cascode + 2 steering switches,
    # 150-300 um2 each) + poly-R referenced bias so k2 tracks R21.
    c2_mos = 2 * 1.953125e-12 * 10 / MIM_F
    rows.append(("ADC DAC2 (MOS current s=10)", "C2 19.5 pF/side, 62 cells ~23 nA, ref",
                 1.12 * c2_mos + 62 * 150 + 3000, 1.25 * c2_mos + 62 * 300 + 6000,
                 "k2 tracks R21 via poly-R reference"))
    est = [  # not yet physical in the deck: (block, item, low_mm2, high_mm2)
        ("ADC quantizer", "31 comparators (3.125 mV LSB, preamp/offset) + ladder", 0.05, 0.12),
        ("ADC DAC switches", "2 DACs x 62 units x VP/VN TG + drivers", 0.01, 0.03),
        ("Clock drivers", "64 kHz chopper phases (input TG gates ~3-7 pF) + ADC phases", 0.005, 0.02),
        ("Bias / VCM / references", "bias generators, VCM, ref buffers or filters", 0.05, 0.15),
        ("Electrode DC servo", "+-300 mV electrode offset handling (not designed)", 0.05, 0.20),
        ("Decoupling", "MOS decap for AFE/ADC supplies and references", 0.10, 0.25),
        ("Digital", "CIC3 R1024 W37, DWA, FIFO, SPI, regs, phase gen (50% util)", 0.25, 0.40),
    ]
    for b, item, lo, hi in est:
        rows.append((b, item, lo * 1e6, hi * 1e6, "estimate"))

    print("| block | item | low (mm2) | high (mm2) | basis |")
    print("|---|---|---|---|---|")
    for b, item, lo, hi, basis in rows:
        print(f"| {b} | {item} | {lo/1e6:.3f} | {hi/1e6:.3f} | {basis} |")

    def total(include):
        lo = sum(r[2] for r in rows if include(r[0]))
        hi = sum(r[3] for r in rows if include(r[0]))
        return lo * 1.15, hi * 1.25  # top-level routing/spacing

    dac2_rows = {"ADC DAC2 (as drawn)", "ADC DAC2 (rescaled)", "ADC DAC2 (MOS current s=10)"}
    cases = {
        name: (lambda keep: lambda b: b not in dac2_rows or b == keep)(keep)
        for name, keep in (("DAC2 as drawn", "ADC DAC2 (as drawn)"),
                           ("DAC2 rescaled (poly)", "ADC DAC2 (rescaled)"),
                           ("DAC2 MOS current DAC", "ADC DAC2 (MOS current s=10)"))
    }
    print()
    print("| case | total low (mm2) | total high (mm2) | " +
          " | ".join(f"vs {k}" for k in SLOTS) + " |")
    print("|---|---|---|" + "---|" * len(SLOTS))
    for name, inc in cases.items():
        lo, hi = total(inc)
        fits = []
        for core in SLOTS.values():
            fits.append(f"{lo/1e6/core:.0%}-{hi/1e6/core:.0%}")
        print(f"| {name} (+15%/+25% top routing) | {lo/1e6:.2f} | {hi/1e6:.2f} | "
              + " | ".join(fits) + " |")
    print()
    for f in files:
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
        print(f"- {os.path.basename(f)} sha256 {h}…")
    unknown = [e for e in elems if e["kind"] == "X?"]
    if unknown:
        print(f"- behavioral/unknown instances skipped: "
              f"{sorted({e['model'] for e in unknown})}")


if __name__ == "__main__":
    main()
