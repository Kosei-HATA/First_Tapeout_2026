# Test-2-4: isolated Magic RC validation

Updated 2026-11-11 UTC. Engineering evidence, not foundry sign-off.

## Outcome

The installed Magic 8.3.664 coupled-RC flow duplicated coupling-derived capacitance into substrate terms. Official Magic 8.3.697, commit e400017fdfb221a410cce9e1674910fe70a14e7d, was built with official Tcl/Tk 8.6.16 entirely under this directory. No installed tool, original GDS, or PDK was modified. Complete new-version extraction AND SPICE conversion passed six limited structures and seven deliberate negative controls. This establishes specific bookkeeping/connectivity improvements, not absolute or spatial RC accuracy.

See final_summary.json and provenance_manifest.json. Full evidence: full_tcl/status.json, full_tcl/validation.json, full_tcl/cap_matrix_check.json, full_tcl/inverter_link/killnode_validation.json. The earlier validation.before_correction.json is retained history, superseded by validation.json. Its two old uncovered claims (complete Tcl conversion and actual killnode test) are no longer current.

## Tests and scope

- Straight wire: 10.8955 fF conserved, 8.8205 ohm versus analytic 8.82 ohm from 0.09 ohm/square times 98 squares.
- Coupled wires: substrate 17.6217 fF and coupling 5.9027 fF conserved; two resistors and all four terminals retained. Full low-frequency lumped capacitance matrix conserved. Old version substrate total becomes 29.4271 fF and fails.
- Isolated MIM, flattened ADC capacitor, and hierarchical ADC capacitor: substrate/coupling totals conserved within printed precision; MIM remains a separate native model device, not replaced by parasitic C.
- Two connected inverters with an aggressor conductor: actual extraction produced three killnode records. New RC reconnects coupling and MOS terminals. Collapsed topology and parameters match, matrix maximum error 0.00002 fF.
- Seven negative controls detected: duplicated coupling, missing resistor, resistance +10%, missing port, missing reconnected coupling, stale killed endpoint, broken internal resistor.
- Matrix comparison collapses verified resistive subdivisions. It does not certify high-frequency distributed behavior, capacitance placement, mesh convergence, or contact/via resistance.

## ADC version difference resolved

Original coupling: old 17.5289 fF, new 17.3964 fF. Substrate terms and MIM dimensions unchanged.

Diagnostic-only tech copies were used, retaining the original PDK. Setting all defaultsidewall coefficients to zero gives exactly 6.54472 fF in both versions. M4-only differences are 10.3689 versus 10.3479 fF; M5-only 13.7047 versus 13.5932 fF. Their differences explain 0.1325 fF at output precision.

Official old/new extract/ExtTech.c shows old integer offset conversion and grid scaling versus new floating offsets. The coefficient 0.5 operation moved from final scaling into the parser; it is not an additional net halving. A diagnostic new-version tech copy quantizing offsets to old 0.05 um units (M4 0.611 -> 0.600 um; M5 0.025 -> 0) reproduces old coupling 17.5289 fF. Doubling coefficients instead produces 28.248 fF and rejects the simple half-coefficient hypothesis.

Therefore do not double coefficients or force new results to the old value. The diagnostic tech copies are NOT proposed production PDK replacements. Absolute model accuracy still requires independent calibrated extraction. Evidence: sidewall_diagnostic/factor_sweep.json, old_source/ExtTech.c, sidewall_diagnostic/new_legacy_offset/{changes.json,cap.spice,run.log}. All original inputs/logs remain.

## Reproduction

Scripts live two levels above this directory, in core_pex_probe:
- test_full_tcl.py recreates the six new-version extractions (do not rerun merely to inspect saved results).
- validate_full_tcl.py, validate_full_matrix.py, validate_killnode.py evaluate saved results.
- test_sidewall_change.py, test_sidewall_sweep.py, test_legacy_offset.py reproduce isolated coefficient/offset diagnostic controls.
- finalize_candidate.py records recheck results and provenance. Its before_correction backups must not be overwritten casually by a second run.

Use container gf180-audit-20261029, /work = C:\projects\ft\test1x. The isolated executable is install_tcl/bin/magic; set LD_LIBRARY_PATH to deps/lib. The original PDK magicrc is used. Configure/build logs document the isolated installation. New and old source provenance and hashes are in provenance_manifest.json.

## Realistic next steps

1. Extend the same small-structure harness to M1-M5 widths/lengths, contact/via arrays, bends and branches; compare analytic sheet/contact series/parallel R and verify invariance under subdivision and hierarchy.
2. Test a small actual ADC/AFE block with retained external ports, verified original LVS net/device mapping, native MIM model once only, and operating-point/AC/transient comparisons. Do not silently interpret internal bulk nodes as global ground.
3. Resolve KPEX physical-pin recognition, then use its independent 2.5D engine for C/R cross-checks where its GF180 layer/model support is established. Prior attempt recovered C but zero pins/no resistors, so it is not an RC validation pass.
4. Assess distributed RC convergence and capacitance location with independent geometry/field reference before scaling to full chip. Complete independent pad-ring reference remains separately necessary.

Do not describe the new build as foundry-qualified or all-chip PEX validated. No external submission was performed.

## Lightweight evidence packaging

Include this README, final_summary.json, provenance_manifest.json, recheck logs, configure/build/install logs, full_tcl test inputs/Tcl/raw ext/res.ext/SPICE/JSON/logs and negative cases, sidewall_diagnostic controls/logs/results, old_source small source excerpts with official URLs, and the reproduction scripts above. Include old coupled-wire baseline from ../coupled_wires for comparison.

Exclude source, source_tcl, dependencies, deps, install, install_tcl, .git, object files, and large unrelated full-chip databases. Earlier mixed-version tests are diagnostic history, not needed for the complete Tcl evidence bundle.

Official sources: https://github.com/RTimothyEdwards/magic ; https://github.com/tcltk/tcl ; https://github.com/tcltk/tk . Related upstream issue: https://github.com/RTimothyEdwards/magic/issues/550 . An issue report is not foundry approval.

## Additional resistance corner controls

See resistance_controls/README.md, results.json, and corner_results.json. Single via1 nominal/high/low corner resistances agree with the independent sheet-plus-contact analytic values to 0.0005 ohm. Missing-via negative is detected; a three-terminal branch is connected and its straight path matches analytic resistance. The low-resistance corner alone specifies zero contact resistance; nominal is 4.5 ohm and high is 15 ohm. These controls do not qualify mesh convergence or full-chip RC. Include resistance_controls and test_resistance_controls.py/test_resistance_corners.py in the lightweight evidence package. The original final_summary.json covers the preceding six-structure/seven-negative campaign; this is an additional, separately recorded campaign.
