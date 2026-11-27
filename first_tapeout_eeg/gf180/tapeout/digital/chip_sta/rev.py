"""Which chip the chip-level STA and the transistor-level checks of this directory look at (requirement VER-08; the
macro the chip takes: gf180/tapeout/layout/digrev.py, EEG_DIG_REV, r14 by default):

  r13  the 13th chip: the macros f2 / f3, the core LVS of r13 (layout/runs/chip_top/r13_20261119/), results in build/
       (the 10/24 and 11/23 runs), the macro's output buffers buf_1 (buf_16 for comparison, the candidate d1)
  r14  the 14th chip: the r14 macro (gf180/tapeout/digital/eeg_digital_top_r14), the core LVS of the 14th chip
       (layout/runs/chip_top/), results in build/r14/, the macro's output buffers clkbuf_2 (all 50 outputs; buf_16
       for comparison, as in r13's tables)
  r15  the 15th chip: the r15 macro (gf180/tapeout/digital/eeg_digital_top_r15, the same pins as r14, its 50 outputs
       clkbuf_2; r15m13 since the rebuild of 11/28), the core LVS database of the rebuilt 15th chip from KLayout 0.30.9
       (layout/runs/chip_top_r15/lvs_k309/eeg_core.lvsdb, run_lvs_k309_r15b.sh: 0.30.12 and 0.30.13 stop in the
       cross-reference sort after the compare on this design; 11/27's r15m1 chip used the precheck image's
       lvs_img/eeg_core.lvsdb, now on the external drive), results in build/r15/

CHIP_LVSDB overrides the LVS database, CHIP_STA_BUILD the results folder. build/ holds r13's macros with the chip
wiring of 10/24 (the 4th assembly: the numbers of gf180_digital_verification_20261024.md, section 5); the 13th chip's own
wiring (the 12th assembly moved clock and data lines, 11/13) was checked on 11/24 with
CHIP_STA_BUILD=build/r13 TOP_RUN=f2_rerun_20261119 ADC_RUN=f3_rerun_20261119 (macros identical to f2 / f3)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "gf180", "tapeout", "layout"))
import digrev  # noqa: E402

REV = digrev.REV
CHIPRUNS = os.path.join(REPO, "gf180", "tapeout", "layout", "runs", "chip_top")
LVSDB = os.environ.get("CHIP_LVSDB") or {"r13": os.path.join(CHIPRUNS, "r13_20261119", "eeg_core.lvsdb"),
                                         "r14": os.path.join(CHIPRUNS, "eeg_core.lvsdb"),
                                         "r15": os.path.join(CHIPRUNS + "_r15", "lvs_k309", "eeg_core.lvsdb")}[REV]
BUILD = os.environ.get("CHIP_STA_BUILD") or (os.path.join(HERE, "build") if REV == "r13"
                                              else os.path.join(HERE, "build", REV))
DIG_BOX = (3002.0, 542.0, 3442.0, 542.0 + digrev.HEIGHT)       # eeg_digital_top (mirrored about x)
DRIVE = {"r13": ("buf_1", "buf_16"), "r14": ("clkbuf_2", "buf_16"), "r15": ("clkbuf_2", "buf_16")}[REV]   # the macro's output buffer, the comparison
