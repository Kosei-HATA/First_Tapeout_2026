"""The digital macro eeg_digital_top that the chip takes (tracker C4, E7), for chip_lay.py,
gf180/tapeout/pex/supply_check.py and gf180/tapeout/chip/make_core_netlist.py:

  r14  gds/r14/: LibreLane run r14f of the r14 RTL (gf180/tapeout/rtl_r14), 440 x 900 um (the user's
       decision of 11/19, requirements NFR-02 / NFR-08); the 14th chip. The default.
  r15  gds/r15/: LibreLane run r15m1 of the r15 RTL (gf180/tapeout/rtl_r15; VERSION 0x11, CFG_GEN, DROP_CNT and
       the LATEST window), 440 x 900 um with the same pins as r14; the 15th chip (11/27). Built in runs/chip_top_r15
       so that runs/chip_top keeps the 14th chip.
  r13  gds/: LibreLane run f2 of the r13 RTL (gf180/tapeout/rtl), 440 x 700 um; the 13th chip.

EEG_DIG_REV=r13 selects the 13th chip's macro (to build that chip again), EEG_DIG_REV=r15 the 15th chip's."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REV = os.environ.get("EEG_DIG_REV", "r14")
DIR = {"r13": os.path.join(HERE, "gds"), "r14": os.path.join(HERE, "gds", "r14"), "r15": os.path.join(HERE, "gds", "r15")}[REV]
HEIGHT = {"r13": 700.0, "r14": 900.0, "r15": 900.0}[REV]
RUNS = {"r13": "chip_top", "r14": "chip_top", "r15": "chip_top_r15"}[REV]     # chip_lay.py's run directory under runs/
