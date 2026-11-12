# Test-2-4: additional IO validation

## Results
Actual Test-2-4 cells were compared with independently installed GF180 IO SPICE/CDL, not with a reference copied from GDS extraction. Originals and PDK unchanged.

- asig_5p0 (47 instances): previous strict primitive LVS PASS, with width and diode-perimeter negative controls.
- dvdd (8), dvss (8), fill5 (22), fill10 (414): unique topology match, no property errors; deliberate +10% width perturbation detected.
- bi_24t (9): conditional PASS for the documented common VSS/DVSS use. Hierarchy-preserving Magic output, merge none, retains DSS geometry attributes. All 7 individual +10% perturbations (d_sab, s_sab, r_width, r_length, w, l, pj) trigger property errors. See hier_comparison.log and hier_negative_summary.json.
- cor (4): conditional PASS for documented common VSS/DVSS use, no property errors; +10% MOSCAP width negative control detected. See common_ground_comparison.log.
- fill1 (226), fillnc (20): independent references contain no devices, so Netgen does not check them. Polygon geometry is identical to the PDK across all layers. This is not a connectivity LVS pass.

Counts refer to direct IO references in the actual GDS. Cell-type LVS does not establish all placed instances or full-ring interconnections. Common-ground conditions are independently recorded in baseline/pad_geometry.json; evidence hashes and instance maps are saved beside each conditional result.

## Tool-output diagnosis
Magic flat hierarchy-off output loses d_sab/s_sab on repeated hierarchical DSS instances and outputs diode PJ 1e6 too small relative to raw .ext length units. No device dimension was ignored or filled from the reference to obtain a pass. The flat-output diode correction is derived from raw extraction area/perimeter and unit scale, with evidence saved. For bi_24t, hierarchy on + merge none preserves SAB and emits PJ in the correct units: normalize_bi_hier.py independently asserts each emitted PJ equals raw physical perimeter (factor 1). Netgen subsequently flattens the complete hierarchy and passes strict checks. This hierarchy-preserving flow should be preferred for future extraction.

The earlier bi_24t/flat_control attempt retained recursive labels and is NOT a signoff result: recursive internal labels are unsuitable as top terminal labels. Preserve it only as an unsuccessful diagnostic. jobs.json records initial comparisons, not the final conditional results above.

## Independent top reference
reference_draft/pad_fragment_incomplete.spice records 76 pad instances from independent chip_lay.py design intent and pad_geometry.json. It is explicitly incomplete: 43 CORE, 9 CORE_TIEHIGH, 45 CORE_TIELOW and 682 PAD_SPACER instance connections are absent from that sidecar. An extracted netlist cannot be substituted as an independent reference. The original final powered Verilog/ODB from RUN_2026-10-23_13-27-25 or an equivalent independent complete source is required.

Scoped searches in gf180 and the two parent-authorized project roots did not recover that exact run. The iic-osic-tools tree has earlier October 2/3/4 feasibility chip_top Verilog/ODB. They are not adopted as the October 23 design reference. The September 2 trials root yielded no matching ODB/chip_top/padring candidates in that search. No broad personal-directory search was performed.

## Remaining priorities
1. Recover the exact independent final top source and reconcile named core/pad/tie/spacer instance nets; then run full-ring device LVS with explicit common-ground intent. Do not use GDS self-comparison.
2. Establish extracted-net to schematic-net mapping on one matched core block using the preserved core_with_hints/eeg_core.lvsdb. Save mapping and check named power, differential and high-impedance nodes before capacitance back-annotation.
3. Validate MIM extraction on isolated known-area structures against the selected MIM-B option and official model. Existing pex.py has historical numeric corrections and layer-name assumptions; do not apply them blindly or double-count model capacitance.
4. Run scoped coupling/ground capacitance extraction, then resistance extraction with PDK-supported sheet/contact values and mesh convergence. Current standalone pad capacitance is not RC or full-chip PEX; extresist has not run.
5. Run post-layout corner/transient/noise simulations on correctly mapped RC networks and then appropriate IR/EM/ESD/package checks. Public-tool passes alone do not constitute foundry approval.

No full-chip high-memory job was launched in this task. Reproduction scripts and raw logs remain under extraction. Small-cell Magic runs took approximately 0.5 to 430 seconds each; no full-chip RAM estimate is asserted from these results.
