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
  `GDSII/eeg_fd_ota_chopped_full2.gds` (1415.5 x 873.5 um; 2026-09-11 bias
  rebuild — was 1865 x 1433 when CFILT was 1 nF).  Sub-commands build
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

## 2026-09-11 — bias generator redesign (RSTART/RFILT/CFILT)

Canonical netlist `source/trials/20260902/xschem/eeg_bias_gen.spice`:
RSTART 20Meg resistor -> `eeg_pseudo_res`, RFILT 1Meg -> 10Meg (100
segs), CFILT 1nF -> 100pF (5x25 of 20x20 = 125 units, 110 x 560 um —
portrait orientation keeps the block east edge at the array, not the
trunks).  New bias_gen bbox: **114.4 x 813.5 um** (was ~562 x 1364).
`build_pseudo_res` moved to `klayout_common.py` and is IDEMPOTENT
(returns the existing cell, anchors from its A/B labels, when the layout
already has one — gen_pga reads full2's GDS, which now contains one
inside eeg_bias_gen; gen_sdm builds bias and the SDM's own pseudo-Rs in
one layout).  All re-verified DRC-clean + hier-LVS-matching
(test_bias.gds vs bias_ref.spice, then full2 vs full2_ref.spice).

New bias_gen structure: FET row + buses unchanged (VBN 8.0 / VBP 9.2 /
SNS2 10.4 / VSS -3.5 / VDD 13.5 / VBNF 6.8, m3); RFILT bank 5 rows x 20
at (20,-206.88) (start pad -> VBN via an m2 strap crossing the bank —
m2 over res cells is free; end pad (58,-11.73) -> VBNF); XRSTART pseudo
at (88,17.5) with A<-VDD / B<-VBN m2 links at x=96/90; CFILT at
(0,-790).

Bias-gen lessons (found the hard way, 2026-09-11):
- The CFILT top-plate tap: the old m3 stub (to y+1.0) + east link worked
  when xm=280 was east of the VBN bus end; with the 5x25 array xm=55
  sits UNDER the VBN bus (y 7.7..8.3) and the stub shorted VBNF to VBN.
  Now: via3 straight onto the VBNF bus, m3 pad 6.5..7.3 (0.4 clear of
  VBN, encloses the via 0.2 — via3.4 needs 0.06).
- The pseudo cell's west edge carries the M-link vertical (m3, local y
  -3.1..3.7): the parents' VDD18 m3 riser (abs x 984.2..984.8 = local
  84.2..84.8, y13.5..70) ran straight through a cell placed at x=85 —
  M and B(=VBN) merged into VDD18.  Only visible at full2 level: the
  standalone test_bias LVS passes either way.  Cell now at x=88.
- The CFILT top-plate m4 column (3.2 wide, rises at abs 953.4..956.6
  from y-229 to 7.7) vs full2's VSS trunk (m4, y-12): a crossing is an
  m4-over-m4 SHORT, and even a <3 um gap notches under m4.5ab's 1.5 um
  closing.  The trunk now ends at 950.0 (bias VSS riser at 948.5); the
  same numbers in ota_nc, where the end must still reach x=950 because
  gen_afe_top taps it through the SDM at SDM-local (1300,1388).
- The VBNF riser (bias VBNF -> VBN trunk) moved from x=1070 to 986
  (east of the VDD18 trunk end 984.8 — the riser may not cross that m4
  trunk); the VBN trunk now ends at 986.3.

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

`gen_pga.py` builds `GDSII/eeg_afe_pga.gds` (1842.5 x 1144.3 um after the
2026-09-11 bias rebuild — was 2224 x 1704 when CFILT was 1 nF), hier LVS
vs `pga_ref.spice` (`run_lvs.sh ... hier`).  **DRC clean + LVS match
(2026-09-05, re-verified 2026-09-11)**, all 11 circuits.  The verified
`eeg_fd_ota_chopped_full2` GDS is instanced as a block; the input network
west of it: CIN 32p MIM arrays (8x5 of 20x20 capm), the cross-coupled
feedback bank (unit 20x12.5 = 0.5 pF; CFB16 = 3 units, CFB8 = 7 units),
8 select/reset `eeg_tg_lowq` TGs (P row y=45, N row y=24), 2
`eeg_pseudo_res`, 4 `eeg_inv` (the schematic's behavioral complement
sources become real inverters: NS8/NS16/NS32/NRST).  S64 is unused in the
schematic (x64 = all switches open): a labeled m3 stub provides the pin
for LVS.

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
  -> up at x=1073/1078 (east of the bias VBNF m4 column at 986) ->
  west lanes at y=88/90 (above all full2 trunks) -> via3 down into the
  bank bottom-plate buses.  2026-09-11: the bias CFILT top-plate m4
  column (100p array, 5x25, xm=55) rises at x 953.4..956.6 through the
  lanes' path — both lanes duck under it on m3 (via3s at x=949.9/960.1;
  the m4 pads and lane ends keep a 3.2 um gap to the column, outside
  m4.5ab's 1.5 um closing radius).

## Standalone cells

`gen_pga.py pseudo_res|inv` -> `GDSII/test_pseudo_res.gds` /
`test_inv.gds`, refs `pseudo_res_ref.spice` / `inv_ref.spice`; both
DRC-clean + LVS-matching.  The pseudo-resistor's two pfets sit in
separate nwells (bulk = own source; guard rings tie to the A/B buses,
not VDD).

# `eeg_sdm1ct` (CT SDM ADC) — Tranche 3

`gen_sdm.py` (no argument) builds the full assembly:
`GDSII/eeg_sdm1ct.gds` vs `sdm_ref.spice`, DRC-clean + LVS-matching
(hierarchical; 2026-09-05, re-verified 2026-09-11 after the RF swap and
again after the bias-gen redesign).  `gen_sdm.py ota_nc` builds the
`eeg_fd_ota_full2_nc` sub-block alone: `GDSII/test_ota_nc.gds` vs
`ota_nc_ref.spice`, also DRC-clean + LVS-matching (rebuilt 2026-09-11
with the new bias: 1308.7 x 868.5 um).

**2026-09-11 — RF=100Meg lossy-integrator resistors replaced by
pseudo-resistors** (schematic-verified equal-or-better; RF version
archived as `source/trials/20260902/xschem/eeg_sdm1ct_rf_archive.spice`).
The two 1000-segment serpentines (x 44..246, y 42..1145) are gone;
XRFP (A=OINTN, B=INP) at (70,1105) and XRFN (A=OINTP, B=INN) at
(170,1070) instance the already-verified `eeg_pseudo_res` (its guard
rings tie to the A/B buses internally — floating nwells follow their
sources, so NO supply wiring is needed).  The strip y ~80..1060,
x 45..265 is now open floor.  CQP/CQN 1pF unchanged.
2026-09-11 (bias rebuild): the OTA's bias CFILT shrank (1nF -> 100p,
portrait 5x25), moving the OTA's east edge in by 450 um and its south
edge out of the floorplan; SDM bbox now **1338.5 x 1397.85 um** (x
21.7..1360.2, y 80.45..1478.3).

Pseudo-R wiring lessons (encoded in `build_sdm`):
- A sides rise on **m2** from a via2 on the cell's A bus — m2 crosses
  the cell's own m3 B bus (and the B-side m3 wires) freely — to via2s
  on the existing OINTN lane (y1143.5, x=80) / OINTP lane (y1142.5,
  x=178).  The risers must stop below the m2 CQ-top jog band
  (y1145.35..1145.65, x 45..196).
- B sides: m3 west extensions (y 1110.545 / 1075.545) to via3s on the
  INP (x=30) / INN (x=27) m4 verticals; the band is empty after the RF
  removal (only m2 crossings: QP/QN verticals, VSS south leg — free).
- The INP/INN m4 verticals were trimmed to start at y 117.9 / 197.9
  (their lowest remaining taps); the old RF taps at y 78.3/76.5 are
  gone.

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

`gen_afe_top.py` builds `GDSII/eeg_afe_top.gds` (top cell eeg_afe_top),
merged with `cell_conflict_resolution = SkipNewCell` (all shared cells
probed geometrically identical between the two block GDS files, labels
aside — including `eeg_pseudo_res` and `eeg_bias_gen`, instanced by both
blocks and built by the same shared builders).
**DRC-clean + hier LVS-matching** vs `afe_top_ref.spice`
(composed verbatim from pga_ref/sdm_ref subckts + the eeg_afe_top subckt
of source/trials/20260902/xschem/eeg_afe_top.spice; RST = VSS via the
XAFE pin map).

**2026-09-11 (second reflow): STACKED floorplan** — the caravan analog
user area (wrapper 2928 x 3528 um) is narrower than the side-by-side top
was wide (3321 um).  Now: PGA at (0,0), SDM ABOVE it (DX=-725, DY = PGA
top + 12 um gap - SDM bottom, both from measured bboxes), the SDM nested
inside the PGA's x-span.  Die: **1842.5 x 2575.15 um** (4.75 mm^2; was
3321.0 x 1410.55 side-by-side, 4152.9 x 1783.2 / 7.41 mm^2 before the
bias redesign).  Fits the user area with >1000 um width margin and ~950
um height margin for power rings.  Supply pins (VDD18/VCM_REF/VSS)
are m5 trunks at the TOP edge; ELP/ELN/PHI*/S8../RST on the PGA west
edge; CLK16/NCLK16/BIT/NBIT/VP/VN tapped at the SDM's west side.

Stacked routing (all m5, width 2.0, pitch >= 3.6):
- PGA_OUTP/OUTN are tapped on the PGA's internal m4 lanes y=90 (OUTP, x
  -455..1078) / y=88 (OUTN, x -465..1073) at x=-450/-460 and run straight
  UP the west side to the SDM's VINP/VINN stubs (abs x=-449 = SDM-local
  276).  Nothing crosses the inter-block gap.
- Supplies: three m5 trunks above the SDM top (T = sdm_top + 8/14/20).
  Every riser ascends from its block's m4 lane to its trunk; trunk ends
  are flush with the riser edges and NESTED (VDD18 innermost x-396..451,
  VCM_REF x459..471, VSS outermost x499..576) so no riser crosses a
  foreign trunk: a riser to a higher trunk sits outside every lower
  trunk's x-span on BOTH sides.  PGA risers at x=-395/460/500, SDM
  risers at local x=1175/1195/1300 (their lanes are the OTA's supply
  trunks passing through at SDM-local y1470/1474/1388).
- RST (PGA m3 stub at (-445,-41.6)): short m5 riser to y=-6, then east
  to the PGA VSS riser at x=500 — the y=-6 run passes under the OUT
  risers (which start at y=88/90).

Top-level reflow lessons (2026-09-11):
- **Subcell nets need PARENT CONTACTS, not just labels**: the deck's
  must-connect check fires for any named-net subnet inside a subcell
  that has no port to the parent (labels only count at the top level /
  for pin creation).  Symptom guide: `[must-connect] In cell <block>:
  Must-connect subnet of <net> does not have any pin` after a block
  boundary moved = a top-level tap dangling off the trimmed edge.
- **Supply risers and trunks on one layer form an ordering puzzle**:
  with all risers ascending from below, trunk x-spans must nest so that
  a riser to a higher trunk never crosses a lower trunk.  A lane landing
  BETWEEN trunks needs 5.2 um (2.0 pad + 2x1.6 spacing) in a 4.0 um
  gap; a lane ABOVE the trunks makes its riser cross the lower trunks
  (m5 over m5 merge — the first side-by-side reflow attempt shorted all
  three supplies this way).

General top-level wiring rules:
- Unlabeled top geometry over child metal creates the subcircuit port;
  the label makes the top-level pin.  ADC_OUTP/ADC_OUTN (SDM integrator
  outputs) are internal nets: tapped but NOT labeled.
- The PGA PHI clock lanes (0.6 wide, 1.0 pitch) cannot take via pads
  (m4.2); each lane is extended east on m4 past all lane ends —
  longest extension = lowest lane — and labeled on the extension.
- m5 L-corners must overlap the full bar width (jog starts flush at the
  riser edge): a 1 um offset leaves a diagonal neck that fails m5.1's
  euclidian 1.6 um width check.
- via3+via4 stacked at one point is legal (deck has no via3-via4 rule).

## Remaining tranches

- None — all four tranches built and verified.  2026-09-11 redesigns:
  the SDM's RF=100Meg serpentines became pseudo-resistors (Tranche 3
  section), the bias generator's RSTART/RFILT/CFILT shrank (Tranche 2
  section), and the top was restacked (PGA below SDM) to fit the caravan
  analog user area — die 4152.9 x 1783.2 (7.41 mm^2) -> 1842.5 x
  2575.15 (4.75 mm^2).  Open floor: the SDM strip x 45..265, y ~80..1060
  (SDM-local).  Further area-reduction candidates are recorded in
  `documentation/final_report_draft.md` section 7.



# Caravan wrapper integration (`user_analog_project_wrapper`) — 2026-09-12

`gen_wrapper.py` reads the pristine test6 caravan analog wrapper
(`source/trials/20260820/test6/gds/user_analog_project_wrapper.gds`,
2920 x 3520 um user area), strips the example POR project, and integrates
the verified `eeg_afe_top` macro.  Output: `GDSII/user_analog_project_wrapper.gds`.
Pin map, surgery list and wall/thicket details: `caravel_pinmap.md`.

```bash
scripts/klayout/.venv/bin/python scripts/klayout/gen_wrapper.py
scripts/klayout/.venv/bin/python scripts/klayout/check_wrapper_nets.py
scripts/klayout/run_drc.sh GDSII/user_analog_project_wrapper.gds
scripts/klayout/run_lvs.sh $(pwd)/GDSII/user_analog_project_wrapper.gds \
    $(pwd)/scripts/klayout/wrapper_ref.spice hier nopurge
```

Expected: `NETS OK`; DRC `TOTAL VIOLATIONS: 2` (both inherited m4.5ab —
see below); LVS `Congratulations! Netlists match.`

## Files

- `gen_wrapper.py` — the whole integration, scripted (no hand edits of
  the template binary): remove the `user_analog_proj_example` instance;
  union-find net removal (merged-region per layer + via-layer linking,
  seeds from label positions) for the example's io_out[11/12/15/16] and
  gpio_analog[3]/[7] wires and the vssd1 distribution (m3 bar y957..981 +
  m4 verticals + four io_oeb pulldown resistors); place the macro
  MIRRORED at (2078, 890) — local (x,y) -> (2078-x, 890+y), abs bbox
  x 999.7..2842.2, y 99.8..2674.95; route all 23 used pins; add 27
  deck-visible (*/5) labels; prune orphan cells (else the decks reject
  the GDS for multiple top cells).
- `check_wrapper_nets.py` — flatten + union-find + position-matched
  labels: every labeled group must be fully connected and no two groups
  may merge.  Prints the net<->labels map; ends `NETS OK`.
- `wrapper_ref.spice` — `afe_top_ref.spice` verbatim + the
  `user_analog_project_wrapper` subckt: one XAFE (pin map per
  caravel_pinmap.md) + the six template clamp res_generic_m3 (5x
  vssa1<->io_clamp_*, 1x io_analog[4]<->io_clamp_high[0]; deck-extracted
  params R=1.068 W=11 L=0.25, written as `R=` params — a positional value
  is mis-parsed as a third node for this 2-terminal class).

## Results

- **DRC**: 2 violations, both m4.5ab on the vssa1 bus appendage
  (x1787/1797, y3097-3099) — present identically in the pristine
  template's own DRC (19 total: 14 m4.5ab + 3 m1.3ab + 2 m3.3ab;
  baseline report `GDSII/user_analog_project_wrapper_template_baseline.drc.txt`).
  The integration introduces zero new violations.
- **LVS** (hier, nopurge): netlists match; all 17 circuits pair `Match`
  in the lvsdb xref.  Extracted: `GDSII/user_analog_project_wrapper_extracted.cir`.
- **`nopurge` is required** (run_lvs.sh 4th arg): NCLK16 and S64 are
  unused inside eeg_sdm1ct's / eeg_afe_pga's bodies, so `purge` cascades
  upwards (child pin purged -> eeg_afe_top port floats -> wrapper
  io_in[9]/io_in[13] nets dropped) while the ref is never purged.
  Purge only deletes floating nets — the compare is unaffected.

## Routing conventions (details in caravel_pinmap.md)

- Long flights on m5 (2.0 wide), GPIO stub approaches on m4 (cross m5
  freely), stacks m4pad+via4+m5pad / m3pad+via3+m4pad onto the 0.56-wide
  m3 stubs, analog pads reached by m5 runs + via4/via3 stacks, power via
  m5 risers + 4x4 m4 pads onto the vdda1/vssa1 m4 buses.
- Two walls: the SDM west-side verticals (x2752.7..2781.3, m3+m4 — cross
  on m5 only) and the ELP/ELN m5 runs (x2827..2835, full height — cross
  on m4 only).  The PGA's mirrored m4 thicket (x..2543.3, y889.9..978.59)
  walls off the PHI-2 lane ends except in4's corridor and the band at
  lane height; in5/6/7 fan out inside that band.
- m5 nubs fail m5.1 (euclidian 1.6): every pad/run junction is
  edge-aligned, and dives overshoot their via4s by 0.71 for enclosure.
