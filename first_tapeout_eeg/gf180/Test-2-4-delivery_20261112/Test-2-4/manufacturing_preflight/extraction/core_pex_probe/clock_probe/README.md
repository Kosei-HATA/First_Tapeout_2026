# Actual ADC clock block: limited PEX applicability

2026-11-11 UTC. Qualified_for_full_chip = false. No timing sign-off or fabrication approval.

## Scope and provenance

The actual Test-2-4 GDS contains eeg_adc_clk at chip_top/eeg_core/adc_top (full instance path in geometry_precheck.json). Its bounding box is (0.4,-1) to (145.4,83.5) um, 46 child instances and 3255 direct shapes. The extracted labeled small GDS is 437072 bytes. Only the scratch copy adds 11 terminal labels; original GDS/PDK remain unchanged. Independent reference.cdl is the recursive 14-subcircuit closure from /work/Test-2-4/verification/eeg_core_reference.cdl, not generated from extracted geometry. Source design intent exists in /work/gf180/tapeout/adc/eeg_adc_clk.spice and layout/netblock.py.

The saved whole-core LVS DB was read once (55.8 seconds, peak RSS 5069080 KB); no whole-chip extraction was run. All proposed pin coordinates first intersected actual Metal3 geometry, then mapped through the existing core LVS cross-reference:
- CHOP1 -> CHOP1
- CIA/NCIA/CIB/NCIB/CDA/NCDA/CDB/NCDB -> ADC.<same pin>
- VDD -> AVDD, VSS -> AVSS

All eleven were unambiguous. Mapping.json contains detailed evidence, including supply-connected devices. external_loads.json narrows this to the actual signal loads.

## Independent circuit validation

KLayout official GF180 LVS deck compares labeled.gds against independent reference.cdl: PASS in 5.86 seconds, about 692 MB. See clock_lvs.log, clock.lvsdb and clock_extracted.cir.

Magic complete isolated 8.3.697 build, explicit extract style ngspice() (nominal), extracted the small block in 4.69 seconds. Native hierarchy output is NOT usable: 78 resistor components cannot be mapped back to original connected parent nets. Actual child .res.ext killnode records remove auto-named boundary nets such as eeg_aclk_inv_s24/a_172_2100# and a_236_340#, while child SPICE declarations retain those names without the required resistor connection to interior terminals. This is not fixed merely by retaining the eleven top-level ports. Hierarchical cap.spice/rc.spice and rc_preservation.json are retained as failing diagnostics.

## Successful bounded alternative

Flattening only this small GDS before Magic extraction avoids implicit child boundary ports. Geometry is preserved, only hierarchy removed. No threshold tuning or coupling deletion is used.

- flat/cap.spice: 486 MOS, 390 parasitic C.
- flat/rc.spice: 486 MOS, 7330 R, 4077 C; eleven top-level pins preserved.
- The flat MOS-only projection removes explicitly identified parasitic C and expresses known four-terminal MOS wrappers as primitive MOS for Netgen. Official PDK setup compares to the independent reference: 486 fingers parallel-merge to 96 equivalent devices; 51 nets; unique match, no property errors.
- Independent-reference slow-NMOS length 4.0 -> 4.4 um negative control produces property errors. No width/length forced matching was introduced.
- RC connected components map unambiguously to every original net. Collapsed device topology and all printed parameters match C-only extraction. No disconnected component remains for an original net.
- Full pairwise collapsed capacitance is conserved within explicitly calculated half-last-digit printing uncertainty. Largest absolute pair delta is VDD/VSS 0.002620 fF around 498.08 fF. This is not a free arbitrary tolerance.
- Removing R0 creates two disconnected pieces of a_972_8460# and fails. Adding 1 fF CHOP1-to-VSS fails capacitance conservation. See flat/negative_checks.json.

The different raw finger counts between hierarchical (474) and flat (486) output are not treated as proof of failure or success by themselves; independent Netgen topology and total-device-geometry comparison is the relevant check for the flat alternative.

## Actual external loads and what is NOT preserved yet

The core LVS DB confirms 24 external MOS gate loads:
- CIA/CIB: two NMOS each, summed W 320 um per output.
- NCIA/NCIB: two PMOS each, summed W 640 um per output.
- CDA/CDB: four NMOS each, summed W 640 um per output.
- NCDA/NCDB: four PMOS each, summed W 1280 um per output.

All external connections on these outputs are gate terminals, matching the independently documented chopper topology. Device names and parameters are in external_loads.json. These loads are NOT included in the isolated clock RC netlist. Nor are parent-level output routes, neighboring coupling, supply distribution or actual TG source/drain/bulk operating trajectories. Replacing these with guessed capacitors would not be a verified real-load simulation.

Therefore the isolated block preserves its internal delay chains and drivers but cannot alone establish chopper overlap/dead-time in the complete circuit. A next testbench can replace the independent clock subcircuit by flat/rc.spice inside the existing independent ADC/OTA circuit, retaining all 24 physical load models and their analog bias behavior. Before that, confirm model wrapper units/names, include parasitics only once, and account separately for missing parent routing. Alternatively an explicitly bounded gate-load sweep can be reported as a sensitivity test, not the actual load solution.

## Next validation and cost

- Build and sanity-check the above independent loaded testbench: estimated 30-60 minutes of setup; transient duration/model convergence must be measured before estimating full PVT runtime.
- Compare schematic vs C-only vs flat-RC overlap/dead-time, output rise/fall and supply current with explicit nominal RC and device corner. Use the same stimulus and analog operating conditions.
- Add output route extraction only after identifying net-connected geometry and endpoints; do not crop a rectangle that silently removes loads or coupling.
- Small via/contact and branch tests already support nominal and high/low resistance bookkeeping. Low-R PDK corner specifies zero contact resistance as a model bound; this does not imply zero physical resistance. Distributed RC convergence and absolute field accuracy remain unqualified.

## Evidence and reproduction

Files in this directory preserve the original small GDS, labeled copy, independent reference, mapping, load list, all raw Magic ext/res.ext, SPICE outputs, Tcl scripts, LVS logs/database, negative cases and hashes. manifest.json hashes generated evidence before this README.

Scripts in parent core_pex_probe:
inventory_clock.py, map_clock.py, extract_clock.py, summarize_clock_loads.py, validate_clock_rc.py, extract_clock_flat.py, validate_clock_flat_rc.py, compare_clock_magic.py, strengthen_clock_validation.py, negative_clock_lvs.py.

Use saved results instead of rerunning expensive core DB reads. Note extract_clock_flat.py currently regenerates the base flat validator; if rerunning the whole pipeline, follow it with strengthen_clock_validation.py exactly once to restore the explicit rounding/disconnection/negative checks. The complete saved validator is validate_clock_flat_rc.py.

For lightweight packaging include this README, manifest, independent reference, geometry/mapping summaries, external_loads, extraction status, LVS logs, all flat validation/netlist/raw extraction files and script sources. Full mapping.json includes many supply-connected devices and can be omitted from a very small bundle if retained locally and accompanied by the eleven-port probe subset. No binary tool build or dependency trees are needed.

## Completed handoff supplement

external_load_terminals.json resolves all 24 external MOS D/G/S/B connections from the independent core reference, with exact source lines and hierarchy chains. terminal_mapping.json contains the compact eleven-port core-LVS correspondence. The load-bench worker has received these plus the audited flat netlists; no simulation uses the failing hierarchical RC file. final_summary.json records the scope.
