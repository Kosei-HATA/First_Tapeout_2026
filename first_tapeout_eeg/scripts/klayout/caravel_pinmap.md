# Caravan wrapper integration — pin map

`GDSII/user_analog_project_wrapper.gds`: the test6 caravel analog
wrapper (2920 x 3520 um user area) with the example POR project removed
and the verified `eeg_afe_top` macro integrated
(`scripts/klayout/gen_wrapper.py`, 2026-09-12).

**2026-09-12 pin remap**: the original assignment used io_in[0..4] /
io_out[0..1] — mprj_io[4:0], which are SYSTEM-RESERVED (serial/WB/user
clock pads).  All digital signals moved to user-configurable pads
(io_in/out[5..26], 22 pads).  Pad mapping (template header):
io_in/out/oeb[13:0] <-> mprj_io[13:0] (east edge), io_in/out/oeb[26:14]
<-> mprj_io[37:25] (west edge); io_in[i] and io_out[i] share the same pad.

## Macro placement

`eeg_afe_top` (1842.5 x 2575.15 um) is placed **mirrored about the
vertical axis** at (2078, 890): local (x,y) -> abs (2078-x, 890+y).
Abs bbox: x 999.7..2842.2, y 99.8..2674.95.  Mirroring puts the macro's
west-side pins on the east — facing the wrapper's east-edge GPIO stubs —
and its north supply trunks just below the template's power buses.
DRC/LVS are invariant under the mirror (the cell is verified unmirrored;
the instance transform does not change extraction).

## Pin map

| Macro pin (eeg_afe_top) | Wrapper port | Pad (mprj_io) | Wrapper-side target |
|---|---|---|---|
| VDD18 | vdda1 | — | vdda1 m4 power bus (NE area) |
| VSS | vssa1 | — | vssa1 m4 power bus (N) |
| ELP | io_analog[0] | 14 | NE corner pad |
| ELN | io_analog[1] | 15 | north pad |
| VCM_REF | io_analog[2] | 16 | north pad |
| VP | io_analog[3] | 17 | north pad |
| VN | io_analog[4] | 18 | north pad |
| PHII / NPHII | io_in[5] / io_in[6] | 5 / 6 | east GPIO stubs (y240.76 / 464.05) |
| PHIBI / NPHIBI | io_in[7] / io_in[8] | 7 / 8 | east GPIO stubs (y1364.16 / 1586.27) |
| PHIM / NPHIM | io_in[9] / io_in[10] | 9 / 10 | east GPIO stubs (y1812.38 / 2044.49) |
| PHIBM / NPHIBM | io_in[11] / io_in[12] | 11 / 12 | east GPIO stubs (y2266.6 / 2488.71) |
| CLK16 | io_in[13] | 13 | east GPIO stub (y2935.82) |
| NCLK16 | io_in[14] | 25 | west GPIO stub (y2540.20) |
| S8 / S16 | io_in[15] / io_in[16] | 26 / 27 | west GPIO stubs (y2324.09 / 2107.98) |
| S32 / S64 | io_in[17] / io_in[18] | 28 / 29 | west GPIO stubs (y1891.87 / 1675.76) |
| BIT / NBIT | io_out[19] / io_out[20] | 30 / 31 | west GPIO stubs (y1453.74 / 1238.63) |

RST is tied to VSS inside the macro (no wrapper port).  vccd1 (and all
vdda2/vssa2/vccd2/vssd2, WB/LA, user_clock2, user_irq, gpio_analog[],
io_in_3v3[], io_in/out[0..4] (reserved), io_in/out[21..26], io_oeb and
io_analog[5..10]) are unused: no connection, no labels added.

## Template surgery (scripted in gen_wrapper.py, not hand edits)

- Removed the `user_analog_proj_example` instance (the only child
  instance of the wrapper cell; the padframe itself is flat shapes).
- Removed the example's wiring nets (thin 0.6 um m3 L-wires):
  io_out[11], io_out[12], io_out[15], io_out[16], gpio_analog[3],
  gpio_analog[7].  Nets identified by union-find over the wrapper cell's
  own metal, seeded from label positions.
- Removed the vssd1 distribution: the full-width m3 bar at y957..981
  (which made any macro placement impossible — the macro is 2575 um tall
  and the bar is the only full-width crossing) plus the east/west m4
  verticals and the example's four io_oeb[11/12/15/16] pulldown
  resistors.  vssd1 is a digital-domain supply the EEG macro does not
  use; its pads remain at the wrapper boundary (unconnected inside).
- Kept everything else: all pads and boundary stubs, the vdda1 / vssa1 /
  vccd1 power buses, the six north clamp resistors (vssa1<->io_clamp_*,
  io_analog[4]<->io_clamp_high[0]).

## Routing layers

- Long flights: **m5** (2.0 um wide) — the macro tops out at m4 except
  its own known m5 inventory (supply trunks/risers, OUT risers, RST run),
  which all routes dodge.  GPIO stub approaches on **m4** (cross the m5
  dives freely) landing on the 0.56-wide m3 stubs via via3 + m3 pad.
- Analog pads: m5 north runs + via4/via3 stacks onto the pads' m3
  (io_analog[0..3]) or onto io_analog[4]'s existing m5 stub.
- Power: m5 risers from the macro's m5 supply trunks, via4 + 4x4 m4 pads
  onto the vdda1 (m4) / vssa1 (m4) buses.
- **West highway** (NCLK16/S8..S64/BIT/NBIT to the west-edge stubs): the
  macro's digital pins all sit on its east half, and the west-edge stubs
  (x-4..2.4) are unreachable straight through the macro — so 7 m4 lanes
  at y2676.4..2698 (3.6 pitch) run ABOVE the macro top (2674.95) and
  below the vdda1 m4 riser (starts y2700.78).  m4 passes under every m5
  blocker (VDD18/VN/VP/VCM/VSS runs, S runs, ELP/ELN runs) — no
  underpasses needed.  Each signal: m5 north run from its pin to its lane,
  via4 down, m4 west to a staggered dive x (4/8/12/16/20/24/28), m5 dive
  to the stub y, m4 to x=1.8, stack_m3 at (1.8, ystub) onto the
  (x-4..2.4) west stub.  (An m5 highway was impossible: the VDD18/VN/VP/
  VCM/VSS m5 runs and the S runs wall off every y<3490 corridor.)
- The deck only reads */5 texts as labels: every connected net gets a
  new (70,5)/(72,5) label; the template's (70,16) pad labels are
  invisible to the KLayout LVS deck.

## Two walls and a thicket (why the routes look like that)

- **SDM west-side wall** (x 2752.7..2781.3, y ~1252..2586): m3 OINTP/OINTN
  drops + m4 INP/INN + m3 supply verticals.  m4 cannot cross it — the
  PHI-1/PHI-2 m4 eastbounds to the east-edge stubs (all at y1364..2488,
  inside the wall band) hop it on m5 (via4 stacks at x=2700/2790; the hop
  is applied only when the channel starts west of the wall — channels
  already east of it go direct, otherwise the m4 cuts the vdda1 riser).
- **ELP/ELN m5 runs** (x2827..2829 / x2833..2835, y 811..3517.75): a
  full-height m5 wall.  CLK16's flight crosses it on m4 (hop corridor
  x 2819.4..2845.6, verified empty of m3/m4).
- **PGA m4 thicket** (mirrored east side, x ..2543.3, y 889.9..978.59):
  interdigitated macro nets.  The PHI-2 lanes dead-end into it; the only
  verified m4 corridors are in4's (x 2509.4..2510.6) and the band at lane
  height and above (thicket fingers stop at y964.62).  in5/6/7 fan out by
  jogging down from their lane ends at staggered x to via4 stacks at the
  m5 flight levels (966.6/970.4/974.3), all inside that band.
- **Channel packing**: north-going m5 channels may not rise through a
  higher flight's level inside that flight's x-span — so up-channels run
  west->east with DESCENDING flight height (PHI-2: 974.3/970.4/966.6/942
  at x2582/2585.7/2589.4/2593.1).  PHI-1's high stubs (PHIBI->1364.16,
  NPHIBI->1586.27) use channels at x2596.8/2600.5 (NPHIBI's channel west
  of PHIBI's: NPHIBI's flight ends before it, PHIBI's flight passes under
  NPHIBI's channel bottom).  PHII's down-dive channel at x2605 is reached
  via an m4 mini-hop under both up-channels.
- m5 junction discipline: pads/runs must be edge-aligned (a run ending at
  a pad centerline leaves a <1.6 um tab that fails m5.1's euclidian width
  check); m5 dives overshoot their via4s by 0.71 so the via stays
  enclosed; a bare via4 at a flight end needs its own m5pad.

## Verification (2026-09-12)

- **Net self-check** (`check_wrapper_nets.py`, flatten + union-find +
  position-matched labels): NETS OK — all 23 macro pins land on their
  assigned pads/stubs, no nets merged.
- **DRC** (`scripts/klayout/run_drc.sh GDSII/user_analog_project_wrapper.gds`,
  stock sky130A.lydrc): **2 violations, both m4.5ab inherited from the
  template** (huge-m4 corner artifacts on the vssa1 bus appendage at
  x1787/1797, y3097-3099 — identical coordinates in the pristine test6
  template's own report, which has 19 violations: 14 m4.5ab + 3 m1.3ab +
  2 m3.3ab; the surgery removed 12 of the 14).  Zero violations introduced
  by the integration.  Baseline report:
  `GDSII/user_analog_project_wrapper_template_baseline.drc.txt`.
- **LVS** (`scripts/klayout/run_lvs.sh <wrapper gds>
  scripts/klayout/wrapper_ref.spice hier nopurge`):
  **"Congratulations! Netlists match."** — all 16 child circuits + the
  wrapper top circuit pair up; the six clamp resistors extract as
  res_generic_m3 (R=1.068, W=11, L=0.25) and match the ref.
  `nopurge` is required: NCLK16/S64 are unused inside
  eeg_sdm1ct/eeg_afe_pga, so `purge` cascades (child pin removed ->
  eeg_afe_top port floats -> wrapper io_in[9]/io_in[13] nets dropped)
  while the ref side is never purged.  The compare itself is unaffected
  (purge only deletes floating nets).
- vccd1 is intentionally unconnected; the template's VCCD1 label is not
  deck-visible, so the floating vccd1 bus is anonymous in extraction
  (benign — the ref declares the port but nothing hangs off it).
