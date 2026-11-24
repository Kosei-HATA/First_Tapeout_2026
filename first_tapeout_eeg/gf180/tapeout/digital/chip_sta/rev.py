"""Which chip the chip-level STA and the transistor-level checks of this directory look at (requirement VER-08; the
macro the chip takes: gf180/tapeout/layout/digrev.py, EEG_DIG_REV, r14 by default):

  r13  the 13th chip: the macros f2 / f3, the core LVS of r13 (layout/runs/chip_top/r13_20261119/), results in build/
       (the 10/24 and 11/23 runs), the macro's output buffers buf_1 (buf_16 for comparison, the candidate d1)
  r14  the 14th chip: the r14 macro (gf180/tapeout/digital/eeg_digital_top_r14), the core LVS of the 14th chip
       (layout/runs/chip_top/), results in build/r14/, the macro's output buffers clkbuf_2 (all 50 outputs; buf_16
       for comparison, as in r13's tables)

CHIP_LVSDB overrides the LVS database."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "layout"))
import digrev  # noqa: E402

REV = digrev.REV
CHIPRUNS = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "chip_top")
LVSDB = os.environ.get("CHIP_LVSDB") or {"r13": os.path.join(CHIPRUNS, "r13_20261119", "eeg_core.lvsdb"),
                                         "r14": os.path.join(CHIPRUNS, "eeg_core.lvsdb")}[REV]
BUILD = os.path.join(HERE, "build") if REV == "r13" else os.path.join(HERE, "build", REV)
DIG_BOX = (3002.0, 542.0, 3442.0, 542.0 + digrev.HEIGHT)       # eeg_digital_top (mirrored about x)
DRIVE = {"r13": ("buf_1", "buf_16"), "r14": ("clkbuf_2", "buf_16")}[REV]   # the macro's output buffer, the comparison
