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

# `eeg_fd_ota_chopped_full2` (chopped full OTA)

Batch layout of the complete chopped front-end OTA:
`eeg_fd_ota_chopped_full2` = input chopper (XCHIN) + stage-1 core +
mid chopper (XCHMID) + two CMFB amps (XCM1 `eeg_cmfb_amp_dl2` W9=4,
XCM2 `eeg_cmfb_amp_dl2_s2` W9=0.5) + bias generator (XBG) + stage-2
output stage (`stage2` cell: M21-24, RCMO/RLOADO 5M/2M, RZ 20k,
Miller CC 10pF MIMs).  Chopping at 1 kHz; the DSL block was removed
from the design (no-DSL pump test), so XDSL is not laid out.
VOS1 (0 V, DVOS=0) is a direct wire in layout.

## Files

- `gen_full2.py` — generator.  Bare `gen_full2.py` builds the full chip to
  `GDSII/eeg_fd_ota_chopped_full2.gds` (~1865 x 1433 um, dominated by the
  1 nF CFILT MIM array in the bias generator).  Sub-commands build
  standalone test GDS for each block: `tg`, `chopper`, `cmfb`, `cmfb2`,
  `bias`, `stage2`, `mim` (-> `GDSII/test_<name>.gds`).
- `<block>_ref.spice` / `full2_ref.spice` — LVS references.  Conventions
  as in `core_ref.spice`, plus: MIM caps extract as
  `sky130_fd_pr__model__cap_mim` (C = 2 fF/um2 exactly; the deck compares
  A and P, in SI units in the ref; first net = bottom plate = m3), and
  fully-parallel FETs combine into one device (documented per ref).
- `trace_nets.py`, `compare_debug.py` — LVS debug helpers (union-find net
  tracer over m1..m4; netlist cross-reference dump from the `.lvsdb`).

## Running

```bash
scripts/klayout/.venv/bin/python scripts/klayout/gen_full2.py
scripts/klayout/run_drc.sh GDSII/eeg_fd_ota_chopped_full2.gds
scripts/klayout/run_lvs.sh GDSII/eeg_fd_ota_chopped_full2.gds \
    scripts/klayout/full2_ref.spice hier
```

Expected: `TOTAL VIOLATIONS: 0` and `Congratulations! Netlists match.`
with all 8 circuits (top + 7 blocks) `Match` in the `.lvsdb` xref.

**Use `hier` mode for the full chip.**  In `flat` mode the deck's
`make_top_level_pins` promotes every block port label inside the
flattened layout to a top-level pin (27 vs the ref's 15), which can
never match; hierarchical mode compares each block cell against its
subckt (all blocks are individually verified) and the top level against
the 15 chip pins.  Cell names must equal subckt names — they do.

## Verification status (2026-09-05)

- **DRC** (stock deck config): **clean, 0 violations**.
- **LVS** (hier): **netlists match**; every block circuit and the top
  circuit report `Match` with 0 bad nets/devices/pins.
- Standalone block tests (`test_*.gds` vs their refs, flat mode) all
  match as well.

## Routing hazards found the hard way (full2 top level)

- Same-layer crossings of different nets are not DRC errors — only LVS
  (or `trace_nets.py`) finds them.  m4-over-m3 / m3-over-m4 /
  m2-over-anything are free; m3-over-m3 and m4-over-m4 merges are fatal.
- The core's four signal rails are m3 at y 11.7..16.2 with 0.7 um gaps —
  no m3 wire fits between them; the OUTP rail extends west to x=-298.5
  and has m3 tap verticals at x=+/-240/+/-292 (y 13..18.3), so m3 cannot
  approach the core's west side above y=13 at all.  Cross the rail band
  on m4 only.
- XCHMID's m4 rails (y 12.7..20.3, x 329..424.5) block all m4 verticals;
  its m3 rail-feed verticals (x 344.5/368.5/392.5, y 3.8..16.2) and clock
  drops (x 343..355, y 16.7..83.3) block m3.  Enter its rails from the
  rail ends (x=424.5) or drop between 424.5 and stage2's buses (x=428).
- XCM1's internal NTAIL link (m3) and NLEFT pad (m3) sit right above its
  VCM_SENSE bus: tap VCM_SENSE with a via3 directly on the bus and rise
  on m4 (the cmfb cells contain no m4), never on m3.
- XCM1's VSS drop (m4, x=162.5, y -12..38.3) crosses the whole mid-band:
  N1N hops over it on m4 at y=43.5/47.

# `eeg_afe_pga` (chopped PGA front-end)

`gen_pga.py` builds `GDSII/eeg_afe_pga.gds` (~2224 x 1704 um), hier LVS
vs `pga_ref.spice` (`run_lvs.sh ... hier`).  **DRC clean + LVS match
(2026-09-05)**, all 11 circuits.  The verified `eeg_fd_ota_chopped_full2`
GDS is instanced as a block; the input network west of it: CIN 32p MIM
arrays (8x5 of 20x20 capm), the cross-coupled feedback bank (unit
20x12.5 = 0.5 pF; CFB16 = 3 units, CFB8 = 7 units), 8 select/reset
`eeg_tg_lowq` TGs (P row y=45, N row y=24), 2 `eeg_pseudo_res`, 4
`eeg_inv` (the schematic's behavioral complement sources become real
inverters: NS8/NS16/NS32/NRST).  S64 is unused in the schematic (x64 =
all switches open): a labeled m3 stub provides the pin for LVS.

Layout rules learned here (now encoded in gen_pga.py):
- **Huge-metal closing rule (m3.3ab/m4.5ab)**: the deck computes
  `huge = sized(-1.5).sized(1.5)`; thin (<3 um) metal merging a MIM
  plate/sheet leaves a notch artifact -> violation.  Connections to
  plates: via3 pads fully inside the plate/tab footprint, or >=3.2 um
  wide stubs.  mim_array top tabs are 1.6 tall so a via3's m4 pad fits
  inside while its m3 pad clears the bottom sheet by 0.5.
- m2 is the magic free layer: it crosses m3 sheets, m4 plates and buses
  without interacting (via1/via2 only where intended).  All bank
  descents and the digital distribution run on m2.
- Every m2 column dodges the placed cells' internal m2/via1/via2 via
  y-aware rectangle picking (`busy_rects`/`pick_x`); cells whose buses
  are fully strapped internally (eeg_inv) get 3 um bus extensions into
  the empty inter-cell gaps and the joins land there.
- The west-block VSS rail must not cross full2's VDD18 m3 rise at
  x=-405: VSS stops at -406.5 and closes the gap on m2.
- Outputs loop: stage2 m3 buses -> east at y=-1/0.2 (under everything)
  -> up at x=1073/1078 (east of the bias VBNF m4 column at 1070) ->
  west lanes at y=88/90 (above all full2 trunks) -> via3 down into the
  bank bottom-plate buses.

## Standalone cells

`gen_pga.py pseudo_res|inv` -> `GDSII/test_pseudo_res.gds` /
`test_inv.gds`, refs `pseudo_res_ref.spice` / `inv_ref.spice`; both
DRC-clean + LVS-matching.  The pseudo-resistor's two pfets sit in
separate nwells (bulk = own source; guard rings tie to the A/B buses,
not VDD).

# `eeg_sdm1ct` (CT SDM ADC) — Tranche 3

`gen_sdm.py` (no argument) builds the full assembly:
`GDSII/eeg_sdm1ct.gds` vs `sdm_ref.spice`, DRC-clean + LVS-matching
(hierarchical, 2026-09-05).  `gen_sdm.py ota_nc` builds the
`eeg_fd_ota_full2_nc` sub-block alone: `GDSII/test_ota_nc.gds` vs
`ota_nc_ref.spice`, also DRC-clean + LVS-matching.

Assembly lessons (encoded in `build_sdm`):
- The CQN/CQP top-plate (VSS) wiring cannot use a thin m4 bridge between
  the two cap sheets: m4.5ab (`huge_m4 = m4.sized(-1.5).sized(1.5)`)
  flags any sub-3um appendage that touches a huge sheet.  CQN instead
  hops east on m3 at y=1158.5 (south of the CQP sheet/junction box,
  north of its own sheet) to the clear corridor at x=170 — east of
  XND1's internal m2 columns (last one ends at 162.87), west of the QN
  rise (188.31) — then north on m2 into the y=1209.75 jog.
- The QP bottom lane (m2, y=1166.35..1166.65, x=52.81..152.19) plus its
  m3 junction box (x=105.5..152.7, y=1164.7..1168.3) block any vertical
  CQN-top descent west of x=152.7 on BOTH m2 and m3.

`gen_sdm.py nand2|strongarm` builds the standalone cells.  Both are
**DRC-clean + LVS-matching (2026-09-05)**: `GDSII/test_nand2.gds` vs
`nand2_ref.spice`, `GDSII/test_strongarm.gds` vs `strongarm_ref.spice`
(~24 x 27 um, 11 FETs: M0 tail, M1/M2 input pair, M3/M4 n-latch,
M5/M6 p-latch, M7/M8 + M9/M10 precharge).

Strongarm lessons (encoded in `build_strongarm`):
- The shared CLK gate column cannot weave between a device's own source
  and drain strap columns (strip corridors are < 0.7 um wide; an m2
  column needs 0.19 half-width + 0.3 clearance each side).  Row B picks
  up CLK at X_CLKB=10.3, row C at x_clk=9.05; both join the CLK2 bus.
  Symptom was D1 absorbed into CLK (the column overlapped M9's drain
  descent at 9.18) — masked while a bigger merge swallowed all nets.
- Ring ties that cannot reach a bus straight get a side-band
  `ring_tap(..., side=...)` + jog + rise; the rise may land EXACTLY on a
  same-net strap column (via2s coincide -> legal merge).  M9's tie rides
  M7's source/tie column at 5.5; M10's rides its own source column.
- When a split bus (D1/D2 at Y_D) moves with a device coordinate, keep
  the gap between the spans >= 0.41 (m3.2) — D2_L is clamped to D1_R +
  0.41.
- Fast LVS debug: read the `.lvsdb` with `kdb.LayoutVsSchematic()` and
  walk `xref().each_circuit_pair()` / `each_net_pair(cp)` (the comparer
  Python callbacks do not fire in this klayout version); the extracted
  `.cir` SUBCKT header shows merged nets as `A|B`.

# `eeg_afe_top` (analog top) — Tranche 4

`gen_afe_top.py` builds `GDSII/eeg_afe_top.gds` (top cell eeg_afe_top):
eeg_afe_pga at (0,0) + eeg_sdm1ct at (1578.5,-1100), merged with
`cell_conflict_resolution = SkipNewCell` (all 39 shared cells probed
geometrically identical between the two block GDS files, labels aside).
**DRC-clean + hier LVS-matching (2026-09-05)** vs `afe_top_ref.spice`
(composed verbatim from pga_ref/sdm_ref subckts + the eeg_afe_top subckt
of source/trials/20260902/xschem/eeg_afe_top.spice; RST = VSS via the
XAFE pin map).  Die: **4152.9 x 1783.2 um** (7.41 mm^2).

Top-level wiring strategy:
- The blocks use nothing above m4, so the five inter-block nets
  (PGA_OUTP/N, VDD18, VCM_REF, VSS+RST) run on **m5** highways (width
  2.0, pitch >= 3.6, via4 = exactly 0.8x0.8 with m4/m5 enclosure pads).
  PGA_OUTP rises to a y=4 trunk and drops at x=1858.5 into VINP; PGA_OUTN
  dives to a y=-6 trunk and drops at x=1850 into VINN — no crossings.
  Supplies trunk above both blocks: VDD18 y=420, VCM_REF y=426, VSS
  y=432 (RST riser at x=-445, PGA VSS riser at x=836 west of everything).
- Every other block pin gets a same-layer tap + label: m4 pins get m4
  pads/staggered lane extensions with m4L labels; m3 pins get
  via3 + m4 pad + m4L label.  Unlabeled top geometry over child metal
  creates the subcircuit port; the label makes the top-level pin.
- ADC_OUTP/ADC_OUTN (SDM integrator outputs) are internal nets: tapped
  (so the subcircuit ports exist) but NOT labeled — a label would create
  extra top-level pins and break the LVS pin match.
- The PGA PHI clock lanes (0.6 wide, 1.0 pitch) cannot take via pads
  (m4.2); each lane is extended east on m4 past all lane ends —
  longest extension = lowest lane — and labeled on the extension.
- m5 L-corners must overlap the full bar width (jog starts flush at the
  riser edge): a 1 um offset leaves a diagonal neck that fails m5.1's
  euclidian 1.6 um width check.
- via3+via4 stacked at one point is legal (deck has no via3-via4 rule).

## Remaining tranches

- None — all four tranches built and verified.  Reminder: the SDM's
  RF=100Meg pseudo-resistor (1000 segs!) is **intentional** (lossy
  integrator, DC gain 46 dB, pole ~80 Hz) — do NOT shrink/replace
  without re-simulation; area-reduction candidates are recorded in
  `documentation/final_report_draft.md` section 7.


