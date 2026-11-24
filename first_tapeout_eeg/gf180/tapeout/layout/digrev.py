"""The digital macro eeg_digital_top that the chip takes (tracker C4, E7), for chip_lay.py,
gf180/tapeout/pex/supply_check.py and gf180/tapeout/chip/make_core_netlist.py:

  r14  gds/r14/: LibreLane run r14f of the r14 RTL (gf180/tapeout/rtl_r14), 440 x 900 um (the user's
       decision of 11/19, requirements NFR-02 / NFR-08); the 14th chip. The default.
  r13  gds/: LibreLane run f2 of the r13 RTL (gf180/tapeout/rtl), 440 x 700 um; the 13th chip.

EEG_DIG_REV=r13 selects the 13th chip's macro (to build that chip again)."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REV = os.environ.get("EEG_DIG_REV", "r14")
DIR = {"r13": os.path.join(HERE, "gds"), "r14": os.path.join(HERE, "gds", "r14")}[REV]
HEIGHT = {"r13": 700.0, "r14": 900.0}[REV]
