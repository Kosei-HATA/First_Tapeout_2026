#!/usr/bin/env python3
"""Segmented-run machinery for the sdm3_mb decks (dodges the deterministic
ngspice timestep-collapse artifact at ~62.502 ms / PH1 edge of cycle 32001
that kills any single-process run crossing it, independent of trajectory).

Each segment simulates < 62.5 ms of process time. Continuity via:
  - all source TDs shifted by -B_prev, so segment k's t=0 == global B_{k-1}.
    NOTE (2026-10-04): ngspice-46 treats a NEGATIVE PULSE TD as TD=0 (verified
    with tb_pulse_negtd.spice), so PULSE delays are wrapped into the positive
    phase-equivalent ((base - Bprev) % TCLK). SIN negative TD works correctly
    (verified with tb_sin_negtd.spice) and is left as-is.
  - .nodeset on all state-bearing nodes from the previous segment's snapshot
    (integrator outputs = CI state, summing nodes, bias-filter VBN/VBNRAW/
    VBP_BIAS, OTA internal rails, 15 flash latch pairs, C2R register)
  - snapshot taken via meas ... at=B-0.6us (mid-PH2 plateau, settled)
Boundaries are PH1-rise instants: B_k = 0.661us + 30720*k*TCLK patterns.
"""
import sys, re

TCLK = 1.953125e-6
PH1_TD = 0.661e-6  # shifted clock set (v5)

def boundary_at_or_after(t_ms):
    n = int((t_ms * 1e-3 - PH1_TD) / TCLK) + 1
    return (PH1_TD + n * TCLK) * 1e3

STATE_NODES = (
    ["XSDM.O1P", "XSDM.O1N", "XSDM.O2P", "XSDM.O2N",
     "XSDM.XINT1.INP", "XSDM.XINT1.INN", "XSDM.XINT2.INP", "XSDM.XINT2.INN",
     "XSDM.C2R"]
    + [f"TH{i}" for i in range(63)]
    + [f"XSDM.XFLASH.BIT{i}" for i in range(63)]
    + [f"XSDM.XINT{x}.XOTA.{n}" for x in (1, 2)
       for n in ("N1P", "N1N", "VCM1", "VCM2", "VBP1", "VBP2")]
    + [f"XSDM.XINT{x}.XOTA.{n}" for x in (1, 2)
       for n in ("VBN", "VBNRAW", "VBP_BIAS")]
)

def make_seg(template, k, Bprev_ms, Lk_ms, csvbase, nodesets_file, seg_file):
    """Write segment deck. Bprev_ms: global time of this segment's t=0.
    Lk_ms: local sim length. Snapshot (for k>0 decks) appended at Lk-0.6us."""
    src = open(template).read()
    # shift all source delays by -Bprev
    src = src.replace("SIN({VCM} 15m 32 0 0 180)", f"SIN({{VCM}} 15m 32 {-Bprev_ms}m 0 180)")
    src = src.replace("SIN({VCM} 15m 32)", f"SIN({{VCM}} 15m 32 {-Bprev_ms}m)")
    for old, base in [("PULSE(0 {VDD} 0.661u", 0.661),
                      ("PULSE(0 {VDD} 1.6375u", 1.6375),
                      ("PULSE(0 {VDD} 1.261u", 1.261),
                      ("PULSE(0 {VDD} 0.671u", 0.671)]:
        td_phase = (base - Bprev_ms * 1e3) % (TCLK * 1e6)  # positive, phase-exact
        new = f"PULSE(0 {{VDD}} {td_phase:.6f}u"
        src = src.replace(old, new)
    # save state nodes too (meas needs saved vectors); wrdata stays TH-only
    # NOTE: must use THIS module's STATE_NODES (153 nodes, BIT0..62), not
    # mb_seg's 4bit 57-node list — that bug left BIT15..30 unsaved and
    # broke the seg1 snapshot (st_55..70 meas failed).
    extra = " ".join(f"v({n})" for n in STATE_NODES)
    src = re.sub(r"save time (v\(TH0\))", f"save time \\1 {extra}", src)
    src = re.sub(r"tran 50n [\d.]+m", f"tran 50n {Lk_ms:.6f}m", src)
    src = re.sub(r"wrdata \.\./results/[\w.]+\.csv",
                 f"wrdata ../results/{csvbase}_seg{k}.csv", src)
    if nodesets_file:
        ns = open(nodesets_file).read().strip()
        # append dumped nodesets after the template's own .nodeset block
        i = src.find(".control")
        src = src[:i] + ns + "\n" + src[i:]
    # state snapshot for the next segment
    snap_t = Lk_ms - 0.0006
    meas = "\n".join(
        f"meas tran st_{j} find v({n}) at={snap_t:.6f}m"
        for j, n in enumerate(STATE_NODES))
    src = src.replace("\nquit\n", "\n" + meas + "\nquit\n", 1)
    open(seg_file, "w").write(src)

def parse_snapshot(logfile, out_nodesets):
    txt = open(logfile, errors="ignore").read()
    vals = re.findall(r"st_(\d+)\s+=\s+([-\d.eE+]+)", txt)
    found = {int(j): float(v) for j, v in vals}
    missing = [j for j in range(len(STATE_NODES)) if j not in found]
    if missing:
        raise SystemExit(f"snapshot incomplete in {logfile}: missing {missing}")
    with open(out_nodesets, "w") as f:
        for j, n in enumerate(STATE_NODES):
            f.write(f".nodeset v({n})={found[j]:.9e}\n")
    print(f"nodesets written: {len(found)} nodes -> {out_nodesets}")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "make":
        # make <template> <k> <Bprev_ms> <Lk_ms> <csvbase> <nodesets_file|none> <seg_file>
        nf = None if sys.argv[7] == "none" else sys.argv[7]
        make_seg(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]),
                 float(sys.argv[5]), sys.argv[6], nf, sys.argv[8])
        print("wrote", sys.argv[8])
    elif cmd == "snap":
        parse_snapshot(sys.argv[2], sys.argv[3])
