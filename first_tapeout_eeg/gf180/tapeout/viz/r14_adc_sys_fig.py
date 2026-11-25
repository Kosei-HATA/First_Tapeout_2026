#!/usr/bin/env python3
"""Figure 58 (r14, 11/26): the ADC's digital block (eeg_adc_dig, the macro f3 on the chips r12..r14) with the r14 control
macro, and why the 13th chip's pair failed at gate level with delays on 11/20 (tracker C3):
  (a) one frame of the quantizer outputs TH: launched by e0 on the chip (eeg_adc_dig's constraints: settled 15 ns after
      it), captured at e2; the logic from TH to the capture flip-flops at max ss from the f3 run's post-route STA; the
      window rtl/tb/tb_top.sv and tb_e2e.sv gave TH (1.5 to 2.5 MCLK after e0)
  (b) the 13th chip's pair (f2 + f3) at gate level with the SDF: the runs of 11/20 (the testbenches as they are), the
      first 2 ms with TH as it is and with TH launched 15 ns after e0, and both testbenches to their end that way
  (c) the r14 control with the ADC block: tb_top_r14 (every phase) with the block's RTL, both netlists without delays
      (the loop closed at gate level), gl_sys_sdf_r14 without delays and with the SDF of three corners
Logs: gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_* and sys_diag_*, gf180/tapeout/rtl/build/{logs,e2e} (11/20).
Usage: gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_adc_sys_fig.py [--interim]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vizstyle as V  # noqa: E402
from vizstyle import BAD, INK, INK2, LIGHT, MUTED, OK, WARN  # noqa: E402

V.CHIP, V.CHIP_DATE = "r14", "20261124"
V.CHIP_LABEL = "Chip r14 (fourteenth assembly, 24 Nov 2026)"
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
T = os.path.join(REPO, "gf180", "tapeout")
RUNS = os.path.join(T, "digital", "eeg_digital_top_r14", "runs")
OUT = os.path.join(REPO, "documentation", "figures", "gf180", f"{V.CHIP}_{V.CHIP_DATE}", "viz")
STA = os.path.join(T, "digital", "eeg_adc_dig", "runs", "f3_rerun_20261119", "55-openroad-stapostpnr",
                   "max_ss_125C_3v00", "max.rpt")
TCLK = 1000.0 / 32.768
CORNERS = ("max_ss_125C_3v00", "nom_tt_025C_3v30", "min_ff_n40C_3v60")
CLAB = {"max_ss_125C_3v00": "ss 125 °C 3.0 V", "nom_tt_025C_3v30": "tt 25 °C 3.3 V", "min_ff_n40C_3v60": "ff −40 °C 3.6 V"}


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return None


def th_path():
    """The worst setup path from TH at max ss: input delay, arrival at the flip-flop, required time."""
    s = read(STA)
    blk = s[s.index("Startpoint: TH["):]
    arr = float(re.search(r"([\d.]+)\s+data arrival time", blk).group(1))
    req = float(re.search(r"([\d.]+)\s+data required time", blk).group(1))
    dly = float(re.search(r"([\d.]+)\s+[\d.]+ \^ input external delay", blk).group(1))
    src = re.search(r"Startpoint: (TH\[\d+\])", blk).group(1)
    return src, dly, arr, req


def gl_verdict(path):
    """(state, text): PASS / FAIL / RUN from a gate-level log of gl_shadow (r13) or gl_shadow_r14 / sys_adc_r14."""
    s = read(path)
    if s is None:
        return "RUN", "running"
    m = re.search(r"^FAIL: gate level != RTL in (\d+) of (\d+) cycles", s, re.M)
    if m:
        return "FAIL", f"{int(m.group(1)):,} of {int(m.group(2)):,} cycles differ"
    m = re.search(r"^PASS: gate level.*?\((\d+) cycles", s, re.M)
    if m:
        return "PASS", f"all {int(m.group(1)):,} cycles equal"
    return "RUN", "running"


def bench_verdict(path, name):
    s = read(path)
    if s is None:
        return None
    if re.search(rf"^PASS: {name}", s, re.M):
        return "PASS"
    m = re.search(rf"^FAIL: {name} \((\d+) errors", s, re.M)
    return f"FAIL ({int(m.group(1)):,})" if m else None


def sys_numbers(path):
    s = read(path)
    if s is None:
        return None
    m = re.search(r"CODE taken by the control (\d+) times.*?(\d+) SEL updates \(DWA (\d+), thermometer (\d+), "
                  r"DWA_EN changes (\d+)\).*?errors (\d+)", s)
    if not m:
        return None
    ok = bool(re.search(r"^PASS: ADC block on the r14 control", s, re.M))
    return dict(take=int(m.group(1)), upd=int(m.group(2)), dwa=int(m.group(3)), therm=int(m.group(4)),
                chg=int(m.group(5)), err=int(m.group(6)), ok=ok)


def settle(path, which):
    s = read(path) or ""
    pat = r"eeg_adc_dig gate level with SDF.*?latest output change ([\d.]+) ns" if which == "adc" else \
        r"^gate level with SDF.*?latest output change ([\d.]+) ns"
    m = re.search(pat, s, re.M)
    return float(m.group(1)) if m else None


def main():
    interim = "--interim" in sys.argv
    src, dly, arr, req = th_path()
    logic = arr - dly
    fig = V.figure(13.4, 10.2,
                   "The ADC's digital block with the r14 control, and the 13th chip's pair at gate level with delays",
                   "eeg_adc_dig (f3, the same on r12, r13 and r14) had not been in any r14 test: the r14 testbenches "
                   "give the control's CODE from a model of it. On 11/20 the 13th chip's pair (f2 + f3) failed at gate "
                   "level with the SDF at ss and tt: the testbenches gave the quantizer outputs TH too late for the "
                   "two-cycle path the block is built and constrained for." + ("  INTERIM: runs still going." if interim else ""),
                   "Logs: gf180/tapeout/digital/eeg_digital_top_r14/runs/sys_*, sys_diag_* and gf180/tapeout/rtl/build "
                   "(11/20); STA: the f3 re-run's post-route max_ss report. Scripts: gf180/tapeout/digital/gl_r14 "
                   "(run_sys_r14.sh, run_sys_sdf_r14.sh, run_old_sdf_th*.sh).")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.25], width_ratios=[1.0, 1.15])

    # ------------------------------------------------------------------ (a) TH in one frame
    ax = fig.add_subplot(gs[0, :])
    e = [i * TCLK for i in range(4)]
    rows = [("On the chip, as constrained", 2.0), ("tb_top / tb_e2e until 11/25", 1.0), ("Fixed for the diagnosis", 0.0)]
    for x, lab in zip(e, ("e0  CMP_STROBE", "e1", "e2  TH captured", "e3  SEL updated")):
        ax.axvline(x, color=LIGHT, lw=0.9, ls=(0, (3, 3)), zorder=1)
        ax.text(x + 0.6, 2.62, lab, fontsize=8, color=MUTED, va="bottom")
    req_c = req - 2 * 30.5 + 2 * TCLK      # the STA's required time at the bench's period
    # chip
    ax.barh(2.0, 15.0, left=0, height=0.36, color="#e2e8f0", zorder=2)
    ax.barh(2.0, logic, left=15.0, height=0.36, color="#0d9488", zorder=2)
    ax.plot([req_c, req_c], [1.72, 2.28], color=INK, lw=1.4, zorder=3)
    ax.text(15.0 + logic / 2, 2.0, f"logic from TH, max ss: {logic:.1f} ns", color="white", fontsize=8.5,
            ha="center", va="center", zorder=4)
    ax.text(7.5, 2.0, "launch 15 ns", fontsize=8, color=INK2, ha="center", va="center", zorder=4)
    ax.text(req_c + 1.0, 2.24, f"required {req:.2f} ns: slack +{req - arr:.2f} ns ({src})", fontsize=8.2, color=OK,
            va="bottom")
    # old bench
    ax.barh(1.0, 1.5 * TCLK, left=0, height=0.36, color="#fecaca", zorder=2)
    ax.text(0.75 * TCLK, 1.0, "random bits", fontsize=8, color=BAD, ha="center", va="center", zorder=4)
    ax.barh(1.0, TCLK, left=1.5 * TCLK, height=0.36, color="#cbd5e1", zorder=2)
    ax.barh(1.0, logic, left=1.5 * TCLK, height=0.12, color=BAD, zorder=3)
    ax.text(1.5 * TCLK + logic + 0.8, 0.86, f"the same logic: {1.5 * TCLK + logic:.1f} ns, after e2 at ss",
            fontsize=8.2, color=BAD, va="center")
    ax.text(2.0 * TCLK, 1.17, "TH = code", fontsize=8, color=INK2, ha="center", va="bottom", zorder=4)
    ax.plot([req_c, req_c], [0.72, 1.28], color=INK, lw=1.4, zorder=3)
    # fixed
    ax.barh(0.0, 15.0, left=0, height=0.36, color="#e2e8f0", zorder=2)
    ax.barh(0.0, 3 * TCLK + 6 - 15.0, left=15.0, height=0.36, color="#99f6e4", zorder=2)
    ax.text(15.0 + 30, 0.0, "TH = code from 15 ns after e0 to 15 ns after the next e0", fontsize=8, color=INK2,
            ha="left", va="center", zorder=4)
    ax.plot([req_c, req_c], [-0.28, 0.28], color=INK, lw=1.4, zorder=3)
    ax.set_yticks([r[1] for r in rows], [r[0] for r in rows], fontsize=8.8)
    ax.set_xlim(-2, 3 * TCLK + 8)
    ax.set_ylim(-0.6, 2.95)
    ax.set_xlabel("time after the CMP_STROBE edge e0 (ns); MCLK 32.768 MHz, 30.52 ns")
    ax.grid(axis="y", visible=False)
    ax.set_title("(a) The quantizer outputs TH in one frame: launched at e0, captured at e2 (a two-cycle path)")

    # ------------------------------------------------------------------ (b) the 13th chip's pair
    ax = fig.add_subplot(gs[1, 0])
    ax.axis("off")
    ax.set_title("(b) The 13th chip's pair (f2 + f3: r12, r13), SDF")
    L13 = os.path.join(T, "rtl", "build")
    D2 = os.path.join(RUNS, "sys_diag_old_sdf_20261125")
    DF = os.path.join(RUNS, "sys_diag_old_sdf_full_20261125")
    DE = os.path.join(RUNS, "sys_diag_old_sdf_e2e_20261126")
    lines = []
    for c in CORNERS:
        lines.append((CLAB[c], None, None))
        lines.append(("  11/20, tb_top as it is", *gl_verdict(os.path.join(L13, "logs", f"top_dlc2_gl_sdf_{c}.log"))))
        lines.append(("  11/20, e2e slice as it is", *gl_verdict(os.path.join(L13, "e2e", f"s4_0of200_gl_sdf_{c}.log"))))
        if c != "min_ff_n40C_3v60":
            lines.append(("  11/25, first 2 ms, as it is", *gl_verdict(os.path.join(D2, f"orig_{c}.log"))))
            lines.append(("  11/25, first 2 ms, TH at 15 ns", *gl_verdict(os.path.join(D2, f"th15_{c}.log"))))
            st, tx = gl_verdict(os.path.join(DF, f"tb_top_{c}.log"))
            bv = bench_verdict(os.path.join(DF, f"tb_top_{c}.log"), "tb_top")
            lines.append(("  tb_top to its end, TH at 15 ns", st, tx + (f"; bench {bv}" if bv and st != "RUN" else "")))
            st, tx = gl_verdict(os.path.join(DE, f"tb_e2e_{c}.log"))
            bv = bench_verdict(os.path.join(DE, f"tb_e2e_{c}.log"), "tb_e2e")
            lines.append(("  e2e slice to its end, TH at 15 ns", st, tx + (f"; bench {bv}" if bv and st != "RUN" else "")))
    y = 0.97
    col = {"PASS": OK, "FAIL": BAD, "RUN": WARN}
    for lab, st, tx in lines:
        if st is None:
            ax.text(0.0, y, lab, fontsize=9, fontweight="semibold", color=INK, transform=ax.transAxes, va="top")
        else:
            ax.text(0.0, y, lab, fontsize=8.5, color=INK2, transform=ax.transAxes, va="top")
            ax.text(0.47, y, {"PASS": "equal", "FAIL": "differs", "RUN": "running"}[st], fontsize=8.5,
                    fontweight="semibold", color=col[st], transform=ax.transAxes, va="top")
            ax.text(0.61, y, tx, fontsize=8.2, color=MUTED, transform=ax.transAxes, va="top")
        y -= 0.058

    # ------------------------------------------------------------------ (c) r14 with the ADC block
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    ax.set_title("(c) The r14 control (r14f5) with the ADC block, ed9c0ebe's bench")
    S = os.path.join(RUNS, "sys_r14f5_20261124_b44", "sys_rtl.log")
    G = os.path.join(RUNS, "sys_r14f5_20261124_b44g", "sys_gl.log")
    Z = os.path.join(RUNS, "sys_r14f5_20261124_b44s")
    rows = [("tb_top_r14, every phase, the block's RTL", S, "rtl"),
            ("tb_top_r14, both netlists, no delays", G, "gl"),
            ("gl_sys_sdf_r14, both netlists, no delays", os.path.join(Z, "syssdf_zero.log"), "gl")]
    rows += [(f"gl_sys_sdf_r14, SDF {CLAB[c]}", os.path.join(Z, f"syssdf_{c}.log"), "sdf") for c in CORNERS]
    y = 0.97
    for lab, p, kind in rows:
        n = sys_numbers(p)
        s = read(p) or ""
        done = n is not None and re.search(r"^exit \d", s, re.M)
        if not done:
            st, tx = "RUN", "running"
        else:
            okc = n["ok"] and n["err"] == 0
            if kind != "rtl":
                okc = okc and re.search(r"^PASS: gate level", s, re.M) and re.search(r"^PASS: eeg_adc_dig gate level", s, re.M)
                cyc = re.search(r"^PASS: eeg_adc_dig gate level.*?\((\d+) cycles", s, re.M)
            st = "PASS" if okc else "FAIL"
            tx = (f"CODE taken {n['take']:,}, SEL {n['upd']:,} (DWA {n['dwa']:,}, therm. {n['therm']:,}, "
                  f"DWA_EN changes {n['chg']}), errors {n['err']}")
            if kind != "rtl" and okc:
                tx += f"; both blocks equal in {int(cyc.group(1)):,} cycles"
            if kind == "sdf" and okc:
                tx += (f"; latest output change control {settle(p, 'top'):.1f} ns, ADC block {settle(p, 'adc'):.1f} ns")
        ax.text(0.0, y, lab, fontsize=8.8, fontweight="semibold", color=INK, transform=ax.transAxes, va="top")
        ax.text(1.0, y, {"PASS": "pass", "FAIL": "fail", "RUN": "running"}[st], fontsize=8.8, fontweight="semibold",
                color=col[st], transform=ax.transAxes, va="top", ha="right")
        ax.text(0.0, y - 0.052, V.wrap(tx, 7.0, 8.0), fontsize=8.0, color=MUTED, transform=ax.transAxes, va="top")
        y -= 0.16
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"gf180_viz_{V.CHIP}_58_adc_dig_system.png")
    fig.savefig(out)
    print(out)


if __name__ == "__main__":
    main()
