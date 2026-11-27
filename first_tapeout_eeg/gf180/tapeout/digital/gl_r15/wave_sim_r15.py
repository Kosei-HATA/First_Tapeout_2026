#!/usr/bin/env python3
"""The simulated waveforms of the r15 macro against the specification's timing diagrams (11/28; requirement VER-05,
tracker C4).

Reads the VCDs of run_wave_r15.sh (gl_sdf_r15.sv with GL_WAVE_VCD: the pins of the RTL and of the final netlist with
the SDF of one corner, in lockstep, and the RTL's frame cycle) and compares them with the diagrams that wave.py
generates from the specification sources (gf180/tapeout/rtl_r15/spec/wave_frame.json, wave_spi.json):

  frame    every complete frame of the capture, every MCLK cycle (the value just before the edge that ends the cycle,
           when every output of that edge has settled): CMP_STROBE, TH_CAPTURE, DAC_LOAD and DAC_CLK high exactly in
           the cycles the frame diagram draws them (its columns are cycle 31 of the previous frame and cycles 0..31);
           CHOP and CHOP_OUT change only at e0 (the edge into cycle 0), every 4 frames at 128 kHz (CHOP_FAST's reset
           value) and together; CHOP_BLANK high exactly from cycle 31 before such an edge for BLANK_LEN + 1 cycles
           (the diagram draws BLANK_LEN 15, the run has the reset value 7: the rule, not the drawn length, is compared);
           CHOP1 changes only at e16. For the RTL and for the netlist.
  delay    the netlist's output changes after the MCLK edge that launched them (the pin edge; clock tree, flip-flop
           and output buffer, as the SDF gives them): per pin, the shortest and the longest.
  spi      the frames of the capture decoded at SCLK's rising edges (mode 0): the LATEST read's header 0xCF and the
           sample read's 0xC0 on MOSI, MISO's first byte STATUS (bits 7:6 = 10), 8 bytes as the SPI diagram's
           LATEST and sample frames draw them (STATUS, 状態, SEQ 上/下, DATA 上/中/下, CRC), the CRC-8 (0x07) of
           the LATEST word started from LAT_HDR 0xCF (and not from 0xC0), the sample's from 0xC0; the netlist's MISO
           bytes equal the RTL's; MISO's change after each SCLK falling edge and its setup before the next rising edge.

usage: wave_sim_r15.py <run folder gl_<tag>>      writes <run>/wave/wave_sim.json and prints the verdicts
"""
import bisect
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.normpath(os.path.join(HERE, "..", "..", "rtl_r15", "spec"))
CORNERS = ("max_ss_125C_3v00", "nom_tt_025C_3v30", "min_ff_n40C_3v60")
PINS = ("CMP_STROBE", "TH_CAPTURE", "DAC_LOAD", "DAC_CLK", "CHOP", "CHOP_OUT", "CHOP_BLANK", "CHOP1", "AFE_RST",
        "CHOP_EN", "DRDY_N", "MISO", "MISO_OE")
SPI_PINS = ("CS_N", "SCLK", "MOSI")


def read_vcd(path, want):
    """{(scope, name): [(t_ps, value)]} for the wanted (scope, name) pairs; the value a string ('0', '1', 'x', or the
    binary digits of a vector)."""
    ids, scope, sig, t = {}, [], {}, 0
    with open(path) as f:
        for line in f:
            w = line.split()
            if not w:
                continue
            if w[0] == "$scope":
                scope.append(w[2])
            elif w[0] == "$upscope":
                scope.pop()
            elif w[0] == "$var":
                key = (".".join(scope), w[4])
                if key in want:
                    ids.setdefault(w[3], []).append(key)
                    sig[key] = []
            elif w[0].startswith("#"):
                t = int(w[0][1:])
            elif w[0][0] in "01xzXZ" and len(w) == 1:
                for k in ids.get(w[0][1:], ()):
                    sig[k].append((t, w[0][0].lower()))
            elif w[0][0] in "bB" and len(w) == 2:
                for k in ids.get(w[1], ()):
                    sig[k].append((t, w[0][1:].lower()))
    return sig


def value_at(ch, t):
    """The value of a change list just before time t (the last change at a time < t)."""
    lo, hi = 0, len(ch)
    while lo < hi:
        mid = (lo + hi) // 2
        if ch[mid][0] < t:
            lo = mid + 1
        else:
            hi = mid
    return ch[lo - 1][1] if lo else "x"


def levels(wave):
    """A WaveDrom wave string as one level per column ('.' repeats the previous)."""
    out, prev = [], None
    for c in wave:
        v = prev if c == "." else c
        out.append(v)
        prev = v
    return out


def spec_frame():
    d = json.load(open(os.path.join(SPEC, "wave_frame.json"), encoding="utf-8"))
    lanes = {ln["name"]: ln for ln in d["signal"] if isinstance(ln, dict) and "name" in ln}
    cyc = lanes["フレームサイクル"]["data"]
    pos = [int(x) for x in cyc]                       # cycle 31 of the previous frame, then 0..31
    def lane(prefix):
        nm = next(n for n in lanes if n.startswith(prefix))
        return nm, levels(lanes[nm]["wave"])
    strobes = {}
    for pin, prefix in (("CMP_STROBE", "ADC：CMP_STROBE"), ("TH_CAPTURE", "ADC：TH_CAPTURE"),
                        ("DAC_LOAD", "ADC：DAC_LOAD"), ("DAC_CLK", "ADC：DAC_CLK")):
        nm, lv = lane(prefix)
        high = {pos[i] for i, v in enumerate(lv) if v == "1"}
        strobes[pin] = (nm, sorted(high))
    nm_c, lv_c = lane("縁のフレーム：CHOP／CHOP_OUT")
    edge_col = next(i for i in range(1, len(lv_c)) if lv_c[i] != lv_c[i - 1])
    nm_b, lv_b = lane("縁のフレーム：CHOP_BLANK")
    b_cols = [i for i, v in enumerate(lv_b) if v == "1"]
    nm_1, lv_1 = lane("CHOP1 の縁のフレーム：CHOP1")
    c1_col = next(i for i in range(1, len(lv_1)) if lv_1[i] != lv_1[i - 1])
    m = re.search(r"（(\d+)）", nm_b)
    return dict(pos=pos, strobes=strobes, chop=(nm_c, pos[edge_col]), blank=(nm_b, [pos[i] for i in b_cols],
                int(m.group(1)) if m else None), chop1=(nm_1, pos[c1_col]))


def regs_defs(name):
    t = open(os.path.join(SPEC, "eeg_regs_defs.svh")).read()
    m = re.search(rf"localparam logic \[\d+:0\] {name} = \d+'[dh]([0-9a-fA-F]+);", t)
    return int(m.group(1), 16 if "'h" in m.group(0) else 10)


def crc8(data, init=0):
    c = init
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def analyse(vcd):
    TB, SH, DUT = "gl_sdf_r15", "gl_shadow_r15", "gl_sdf_r15.dut"
    want = {(TB, "MCLK"), (DUT, "cycle")} | {(TB, p) for p in PINS + SPI_PINS} | {(SH, p.lower()) for p in PINS}
    sig = read_vcd(vcd, want)
    miss = sorted(k for k in want if not sig.get(k))
    if miss:
        return {"error": f"signals missing in {vcd}: {miss}"}
    S = spec_frame()
    blank_len = regs_defs("BLANK_BLANK_LEN_RST")
    mclk = sig[(TB, "MCLK")]
    rise = [t for (t, v), (_t0, v0) in zip(mclk[1:], mclk[:-1]) if v == "1" and v0 == "0"]
    half = (rise[1] - rise[0]) / 2
    cyc = sig[(DUT, "cycle")]
    # the cycle of each interval [rise[i], rise[i+1]): the RTL's counter after the edge rise[i]
    cyc_of = [int(value_at(cyc, r + half), 2) if value_at(cyc, r + half) not in ("x", "z") else None for r in rise]
    res = {"cycles": len(rise) - 1, "blank_len": blank_len, "frame": {}, "delay": {}, "spi": {}}
    # complete frames: intervals from a cycle 31 (the column before the frame) through the frame's cycle 31
    starts = [i for i in range(1, len(rise) - 33) if cyc_of[i] == 0 and cyc_of[i - 1] == 31]
    res["frames"] = len(starts)
    for src, name in (("rtl", lambda p: (TB, p)), ("netlist", lambda p: (SH, p.lower()))):
        bad, n_chk, n_edges, n_c1 = [], 0, 0, 0
        lvl = {p: [value_at(sig[name(p)], rise[i + 1] - 1) for i in range(len(rise) - 1)] for p in PINS}
        for i0 in starts:
            for p, (_nm, high) in S["strobes"].items():
                for k in range(-1, 32):               # cycle 31 of the previous frame, then the frame
                    c = cyc_of[i0 + k]
                    exp = "1" if c in high else "0"
                    n_chk += 1
                    if lvl[p][i0 + k] != exp:
                        bad.append(f"{p} frame at {rise[i0] / 1e3:.1f} ns cycle {c}: {lvl[p][i0 + k]}, spec {exp}")
        # CHOP / CHOP_OUT: changes only into cycle 0, together; CHOP_BLANK by the rule around each such edge; CHOP1
        # only into cycle 16
        for i in range(1, len(rise) - 1):
            c = cyc_of[i]
            for p in ("CHOP", "CHOP_OUT"):
                if lvl[p][i] != lvl[p][i - 1]:
                    n_edges += p == "CHOP"
                    if c != S["chop"][1]:
                        bad.append(f"{p} changes into cycle {c} at {rise[i] / 1e3:.1f} ns, spec e{S['chop'][1]}")
            if (lvl["CHOP"][i] != lvl["CHOP"][i - 1]) != (lvl["CHOP_OUT"][i] != lvl["CHOP_OUT"][i - 1]):
                bad.append(f"CHOP and CHOP_OUT not together into cycle {c} at {rise[i] / 1e3:.1f} ns")
            if lvl["CHOP1"][i] != lvl["CHOP1"][i - 1]:
                n_c1 += 1
                if c != S["chop1"][1]:
                    bad.append(f"CHOP1 changes into cycle {c}, spec e{S['chop1'][1]}")
        edges = [i for i in range(1, len(rise) - 1) if lvl["CHOP"][i] != lvl["CHOP"][i - 1]]
        gaps = sorted({(b - a) for a, b in zip(edges, edges[1:])})
        if gaps and gaps != [128]:
            bad.append(f"CHOP edges {gaps} MCLK apart, spec 128 (128 kHz, 4 frames)")
        # CHOP_BLANK: high from the cycle 31 before each edge for BLANK_LEN + 1 cycles, low otherwise (checked from the
        # first edge's cycle 31 to the last edge's blank)
        for i in (range(max(1, edges[0] - 1), min(len(rise) - 1, edges[-1] + blank_len + 1)) if edges else ()):
            exp = "1" if any(e - 1 <= i <= e - 1 + blank_len for e in edges) else "0"
            n_chk += 1
            if lvl["CHOP_BLANK"][i] != exp:
                bad.append(f"CHOP_BLANK cycle {cyc_of[i]} at {rise[i] / 1e3:.1f} ns: {lvl['CHOP_BLANK'][i]}, spec {exp}")
        if not edges:
            bad.append("no CHOP edge in the capture")
        res["frame"][src] = {"checks": n_chk, "chop_edges": n_edges, "chop1_edges": n_c1, "mismatches": len(bad),
                             "first": bad[:6]}
    # the netlist's delays after the launching MCLK edge
    for p in PINS:
        ds = []
        for t, v in sig[(SH, p.lower())]:
            if t <= rise[0] or v not in ("0", "1"):
                continue
            k = bisect.bisect_right(rise, t) - 1          # the last MCLK rising edge at or before the change
            ds.append((t - rise[k]) / 1e3)
        if ds:
            res["delay"][p] = {"n": len(ds), "min_ns": round(min(ds), 3), "max_ns": round(max(ds), 3)}
    # the SPI frames
    cs, sclk, mosi = sig[(TB, "CS_N")], sig[(TB, "SCLK")], sig[(TB, "MOSI")]
    falls = [t for t, v in cs if v == "0"]
    rises_cs = [t for t, v in cs if v == "1"]
    frames = []
    for tf in falls:
        tr = next((t for t in rises_cs if t > tf), None)
        if tr is None:
            continue
        sr = [t for (t, v) in sclk if tf < t < tr and v == "1"]
        sf = [t for (t, v) in sclk if tf < t < tr and v == "0"]
        def bytes_of(ch):
            bits = [value_at(ch, t + 1) for t in sr]  # the level at the rising edge (after any change at that time)
            return [int("".join(bits[8 * k:8 * k + 8]), 2) if all(b in "01" for b in bits[8 * k:8 * k + 8]) else None
                    for k in range(len(bits) // 8)]
        mo = bytes_of(mosi)
        fr = {"t_ns": round(tf / 1e3, 1), "n": len(mo), "mosi": mo, "miso_rtl": bytes_of(sig[(TB, "MISO")]),
              "miso_gl": bytes_of(sig[(SH, "miso")])}
        # MISO (netlist) after each SCLK falling edge, and its setup before the next rising edge
        chg = [t for t, v in sig[(SH, "miso")] if tf < t < tr]
        after, setup = [], []
        for t in chg:
            f0 = max((x for x in sf if x <= t), default=None)
            r1 = min((x for x in sr if x > t), default=None)
            if f0 is not None:
                after.append((t - f0) / 1e3)
            if r1 is not None:
                setup.append((r1 - t) / 1e3)
        fr["miso_after_sclk_fall_ns"] = [round(min(after), 2), round(max(after), 2)] if after else None
        fr["miso_setup_ns"] = round(min(setup), 2) if setup else None
        frames.append(fr)
    lat = [f for f in frames if f["mosi"] and f["mosi"][0] == 0xCF]
    smp = [f for f in frames if f["mosi"] and f["mosi"][0] == 0xC0]
    spi_bad = []
    for f, init_hdr, other in ([(x, 0xCF, 0xC0) for x in lat] + [(x, 0xC0, 0xCF) for x in smp]):
        g = f["miso_gl"]
        if f["n"] != 8:
            spi_bad.append(f"frame at {f['t_ns']} ns: {f['n']} bytes, spec 8")
            continue
        if g != f["miso_rtl"]:
            spi_bad.append(f"frame at {f['t_ns']} ns: netlist MISO {g}, RTL {f['miso_rtl']}")
        if g[0] is None or (g[0] >> 6) != 0b10:
            spi_bad.append(f"frame at {f['t_ns']} ns: first MISO byte {g[0]} without STATUS's bits 10")
        if None in g or crc8(g[1:7], crc8([init_hdr])) != g[7]:
            spi_bad.append(f"frame at {f['t_ns']} ns: CRC 0x{g[7]:02X} is not the CRC-8 from 0x{init_hdr:02X}")
        elif crc8(g[1:7], crc8([other])) == g[7]:
            spi_bad.append(f"frame at {f['t_ns']} ns: the CRC also passes from 0x{other:02X}")
    # the SPI diagram's LATEST and sample frames: 8 bytes, MISO labels
    d = json.load(open(os.path.join(SPEC, "wave_spi.json"), encoding="utf-8"))
    groups = {g[0]: {ln["name"]: ln for ln in g[1:] if isinstance(ln, dict) and "name" in ln}
              for g in d["signal"] if isinstance(g, list) and g}
    lat_lanes = next(v for k, v in groups.items() if k.startswith("最新値"))
    spec_lat = {"mosi0": lat_lanes["MOSI"]["data"][0], "miso": lat_lanes["MISO"]["data"]}
    if spec_lat["mosi0"] != "R＋0x4F" or len(spec_lat["miso"]) != 8:
        spi_bad.append(f"the SPI diagram's LATEST frame: {spec_lat}")
    res["spi"] = {"frames": frames, "latest_reads": len(lat), "sample_reads": len(smp), "mismatches": len(spi_bad),
                  "first": spi_bad[:6], "spec_latest": spec_lat}
    if not lat:
        res["spi"]["first"].append("no LATEST read in the capture")
        res["spi"]["mismatches"] += 1
    return res


def main():
    run = sys.argv[1]
    out, ok = {}, True
    for c in CORNERS:
        vcd = os.path.join(run, "wave", f"{c}.vcd")
        if not os.path.exists(vcd):
            print(f"FAIL  {c}: no {vcd}")
            ok = False
            continue
        r = analyse(vcd)
        out[c] = r
        if "error" in r:
            print(f"FAIL  {c}: {r['error']}")
            ok = False
            continue
        fr = r["frame"]
        good = (all(fr[s]["mismatches"] == 0 and fr[s]["checks"] > 0 for s in ("rtl", "netlist")) and r["frames"] >= 40
                and fr["netlist"]["chop_edges"] >= 10 and r["spi"]["mismatches"] == 0 and r["spi"]["latest_reads"] >= 1)
        ok &= good
        lat = [f for f in r["spi"]["frames"] if f["mosi"] and f["mosi"][0] == 0xCF]
        print(f"{'PASS' if good else 'FAIL'}  {c}: {r['frames']} frames, {r['cycles']} cycles; frame lanes == spec "
              f"(RTL {fr['rtl']['checks']} checks / {fr['rtl']['mismatches']} off, netlist {fr['netlist']['checks']} / "
              f"{fr['netlist']['mismatches']} off; CHOP edges {fr['netlist']['chop_edges']}, BLANK_LEN {r['blank_len']}); "
              f"SPI: {r['spi']['latest_reads']} LATEST, {r['spi']['sample_reads']} sample reads, "
              f"{r['spi']['mismatches']} off" + (f"; LATEST bytes {' '.join(f'{b:02X}' for b in lat[0]['miso_gl'])}, "
                                                 f"MISO {lat[0]['miso_after_sclk_fall_ns']} ns after SCLK falls, setup "
                                                 f"{lat[0]['miso_setup_ns']} ns" if lat else ""))
        for s in ("rtl", "netlist"):
            for x in fr[s]["first"]:
                print(f"      {s}: {x}")
        for x in r["spi"]["first"]:
            print(f"      spi: {x}")
        print("      delays after the MCLK edge (netlist): " + ", ".join(
            f"{p} {v['min_ns']:.2f}-{v['max_ns']:.2f} ns" for p, v in r["delay"].items()))
    json.dump(out, open(os.path.join(run, "wave", "wave_sim.json"), "w"), indent=1)
    print("PASS: the simulated waveforms equal the spec's diagrams (3 corners)" if ok else "FAIL: wave_sim_r15")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
