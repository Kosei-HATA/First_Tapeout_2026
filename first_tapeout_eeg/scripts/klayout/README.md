# KLayout batch layout flow — `eeg_fd_ota_core_soft`

Batch-mode (no GUI) layout generation + DRC + LVS for the stage-1
differential core of the EEG OTA, SkyWater sky130A (volare PDK).

## Files

- `gen_core.py` — layout generator. Draws all devices with the PDK's own
  KLayout generators (`cells/draw_fet.py`, `cells/res_poly_child.py`,
  unmodified) and adds S/D + gate strapping, buses, guard-ring ties and pin
  labels with plain `klayout.db` geometry. Output:
  `GDSII/eeg_fd_ota_core_soft.gds`, top cell `eeg_fd_ota_core_soft`
  (~597 x 55 um).
- `core_ref.spice` — LVS reference netlist (see header comments for the
  deck-specific conventions: SI units on M elements, positional-value
  3-terminal R elements, explicit dummy-finger device).
- `run_drc.sh` — KLayout DRC with the stock PDK deck
  `libs.tech/klayout/drc/sky130A.lydrc`; prints a per-category violation
  summary and exits nonzero on any violation. Report:
  `GDSII/eeg_fd_ota_core_soft.drc.txt`.
- `run_lvs.sh` — KLayout LVS with the stock PDK deck
  `libs.tech/klayout/lvs/sky130.lvs` vs `core_ref.spice`. Writes
  `GDSII/eeg_fd_ota_core_soft_extracted.cir`, `...lvsdb`, `GDSII/lvs.log`.
- `setup_venv.sh` — creates `.venv/` (Python 3.10 + gdsfactory 8.0.0 +
  klayout wheel) used by `gen_core.py`.
- `bin/pmap` — shim; the stock LVS deck's logger shells out to Linux `pmap`,
  which macOS lacks. `run_lvs.sh` puts `bin/` on PATH.

## Running

```bash
scripts/klayout/setup_venv.sh                 # once
scripts/klayout/.venv/bin/python scripts/klayout/gen_core.py
scripts/klayout/run_drc.sh
scripts/klayout/run_lvs.sh
```

Expected results: `TOTAL VIOLATIONS: 0` and
`INFO : Congratulations! Netlists match.`

`SKY130A_PDK` env var overrides the PDK path (default: the volare
`sky130A` under `~/.volare/.../0fe599b2...`).

## Layout notes

- **M1/M2** (`nfet_01v8` L=4 W=240 nf=24 each): one shared-diffusion strip,
  48 signal fingers + 2 end dummies, gate pattern `D ABBAx12 D`
  (centroid-balanced; finger centroids of A and B coincide at the strip
  center). Fingers are 10 um wide, L=4, gate contacts alternate top/bottom;
  gates are strapped by m2 verticals to m3 buses (INP/INN top and bottom,
  joined at the strip ends). S/D regions strap to OUTP/OUTN buses above and
  TAIL below. PDK psub guard ring, tied to VSS.
  - Caveat: the alternating drain/source rule forces both end dummies onto
    OUTP (they extract/combine as one W=20u device, `MMDP` in
    `core_ref.spice`) — a small extra dummy gate cap on OUTP vs OUTN.
- **M3/M4** (`pfet_01v8` L=4 W=48 nf=8): mirrored about the vertical axis,
  above the pair; gates bussed on m1 to VBP; PDK nwell-tap guard rings tied
  to VDD18.
- **M5** (`nfet_01v8` L=4 W=96 nf=16): centered below the pair; gate bar VBN
  on m1; sources to VSS, drains to TAIL; psub ring to VSS.
- **Resistors**: series chains of `sky130_fd_pr__res_xhigh_po_0p69` segments
  (PDK generator, w=0.69 um, l=34.38 um). The LVS deck extracts
  R = 2000 ohm/sq * L/W with L = l + 0.12 (poly_res marker), so each segment
  is exactly 100 kohm. RCM1/RCM2: 50 segments = 5 Mohm; RLOADP/RLOADN:
  20 segments = 2 Mohm. Segments alternate 180 deg rotation and chain on m1.
  `combine_devices` merges each chain into one device for LVS.
  - Note: layout uses RLOAD = 2 Mohm as specified; the trial schematic
    default is RLOAD=500k (`core_ref.spice` documents this).
  - The 5 Mohm resistors are ~100 x 40 um each — large but as specified.

## Verification status (2026-09-03)

- **DRC** (`sky130A.lydrc` stock configuration: FEOL=false, BEOL=true,
  OFFGRID=true): **clean, 0 violations**.
- **LVS** (`sky130.lvs`, stock): **netlists match**. Extracted:
  M1/M2 W=240 L=4, dummy W=20, M3/M4 W=48, M5 W=96, RCM=5.0000 Mohm,
  RLOAD=2.0000 Mohm.
- **FEOL=true variant** (deck flag flipped): 1818 violations, all licon.*:
  - `licon.15` (1804): npc enclosure of poly licon 0.1 um — the PDK
    FET/resistor generators draw npc with ~0.01/0.095 um enclosure.
    Generator-inherent (PDK pymacros are marked "not qualified" upstream).
  - `licon.1`/`licon.7` (10): the res_xhigh_po generator's slotted
    0.19x2.0 pad licons vs the deck's exact-0.17 rule (the deck's exclusion
    only covers rpm-marked resistors, not urpm/xhigh ones).
  - `licon.12` (4): "max S/D width without licon 5.7um" flags each FET
    cell's whole diffusion — the deck rule is too crude for L=4um
    shared-diffusion strips (licon covers the full strip width).
  None of these originate from the top-level routing; the stock deck
  configuration (which is what the PDK ships as default) is clean.

## Gotchas encoded in the scripts (do not "simplify" away)

- KLayout.app bundles Python 3.9; the PDK pcell generators need
  gdsfactory 8.x (Python >= 3.10) — hence the separate venv for generation.
  gdsfactory 8 renamed `gf.boolean` operations ("A-B" -> "not");
  `gen_core.py` monkey-patches a compatibility shim (PDK files are not
  modified).
- The kfactory default layout writes a bogus layer 99999/0 into generated
  cells; `gen_core.py` strips layers > 65535 before writing GDS.
- LVS: `lvs_sub=VSS` (substrate net name), `scale=false` (params in um,
  matching `L=4u`-style ref values), `combine=true` (finger/series merging).
- Resistor ref elements must be `R<n> A B BULK <value> <model> W=..u L=..u`:
  3 nets select DeviceClassResistorWithBulk and the positional value defeats
  the deck reader's appended `R=0`.
