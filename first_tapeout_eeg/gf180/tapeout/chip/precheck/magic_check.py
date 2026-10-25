#!/usr/bin/env python3
"""Magic DRC of the chip as the precheck runs it, but without the dummy COMP and Poly2 fill
(tracker E8), natively in the template's nix shell (Magic 8.3.677).

With the COMP fill, Magic 8.3 (revision 660 in the precheck image, 677 here) crashes in
bpBinArrayBuild during "drc listall why" (DRCInteractionCheck -> drcSubCheckPaint): the
precheck flattens COMP_FILL into chip_top, and chip_top with only COMP_FILL and afe_top
already crashes. The precheck does not notice (LibreLane runs Magic with check=False and
reads the empty report as 0 errors). Without COMP_FILL Magic finished up to the fourth
assembly (10/25); with the fifth (WN Metal5 back over the chopper's gate-lane corridor in
afe_top) the POLY2_FILL trips the same crash (without COMP, Metal5 or all the metal fill it
still crashes; without COMP and Poly2 it finishes), so both are left out. The dummy COMP and
poly themselves are checked by the KLayout decks (dummy_comp, density). Details:
documentation/gf180_chip_assembly_20261023.md.

Input: the precheck run's GDS after the ID insertion (dummy metal / poly already moved to
the drawing layers), runs/precheck/runs/<tag>/04-klayout-generateid/chip_top.gds.

usage: gf180/tools/venv310/bin/python gf180/tapeout/chip/precheck/magic_check.py [run tag]
       (default: the newest run under gf180/tapeout/layout/runs/precheck/runs/)
"""
import collections
import glob
import os
import subprocess
import sys

import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
TAPEOUT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(TAPEOUT, "layout"))
import gf180lay as g  # noqa: E402  (PDK and the nix shell of the template work copy)

RUNS = os.path.join(TAPEOUT, "layout", "runs", "precheck")


def main():
    if len(sys.argv) > 1:
        run = os.path.join(RUNS, "runs", sys.argv[1])
    else:
        run = max(glob.glob(os.path.join(RUNS, "runs", "*")), key=os.path.getmtime)
    tag = os.path.basename(run)
    src = os.path.join(run, "04-klayout-generateid", "chip_top.gds")
    out = os.path.join(RUNS, f"magic_{tag}")
    os.makedirs(out, exist_ok=True)

    ly = db.Layout()
    ly.read(src)
    top = ly.cell("chip_top")
    skip = ("COMP_FILL", "POLY2_FILL")
    for inst in list(top.each_inst()):
        if ly.cell(inst.cell_index).name in skip:
            inst.delete()
    for name in skip:
        ly.cell(name).prune_cell()
    gds = os.path.join(out, "chip_top_nocomp.gds")
    ly.write(gds)

    rpt, log = os.path.join(out, "drc.magic.rpt"), os.path.join(out, "magic.log")
    rc = os.path.join(g.PDK, "libs.tech", "magic", "gf180mcuD.magicrc")
    cmd = (f"env GDS={gds} RPT={rpt} TOP=chip_top PDK_ROOT={os.path.dirname(g.PDK)} PDK=gf180mcuD "
           f"magic -dnull -noconsole -rcfile {rc} {os.path.join(HERE, 'magic_drc.tcl')}")
    r = subprocess.run(["nix-shell", "--run", cmd], cwd=g.NIX_DIR, capture_output=True, text=True)
    open(log, "w").write(r.stdout + r.stderr)
    done = "DRC Checking DONE" in r.stdout
    print(f"Magic DRC ({tag}, without COMP and Poly2 fill): exit {r.returncode}, {'finished' if done else 'DID NOT FINISH'}")
    if not done:
        sys.exit(1)
    counts, rule = collections.Counter(), None
    for line in open(rpt):
        line = line.rstrip("\n")
        if not line or line.startswith("---") or line.startswith("[INFO]") or line == "chip_top":
            continue
        if line.startswith(" "):
            counts[rule] += 1
        else:
            rule = line
    for rule, n in counts.most_common():
        print(f"  {n:6d}  {rule}")
    print(f"report: {rpt}")


if __name__ == "__main__":
    main()
