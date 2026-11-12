# RTL-driven AFE 224 us checkpoint

One bounded 224 us AFE diagnostic, recalculated from time zero; unchanged circuit, solver, stimuli prefix and numerical settings. Full vectors and full time history retained for reproducibility and 58-MOS audit. No .tran tstart change. One process, 2100 s cap. Estimated 24 min based on actual 160 us run. Controls extended to 256 us. Fixed eight cycles: 159.318117 to 221.818117 us, same thresholds; earlier window failure preserved and not replaced. Assumed board startup, Q model and ideal common AVSS; not full system or ENOB acceptance. No unbounded extension on failure.

## Result
Completed in 1991.311 s (33 min 11 s), exit 0, 252914 rows, all saved vectors finite. No transient-abort errors. All seven fixed-window adjacent-cycle checks meet the unchanged engineering thresholds. Largest differential mean change 0.102853 uV, VCM mean change 74.3868 uV, differential RMS change 0.0642493 uV. VCM changes fall to 7.58468 uV by the last pair. Earlier 160 us window failure remains preserved; the later evaluation was declared before this run.

This is observed short-window periodic stability, not a claim of fully settled band response or gain. Do not divide the approximately 29.891 mV differential mean by the 100 uV input, since offset has not been independently removed. No further simulation was launched.

58-MOS whole-record screen has worst gate pair 3.348361 V and VDS 3.386044 V, identical to the earlier startup maxima. Output evaluation ranges are saved in final_summary.json. Scope: AFE-only, assumed board sequence, integral-Q MOSCAP diagnostic, ideal common AVSS, no finite PDN/substrate, no complete ADC/DWA loop or ENOB validation.

## Reproduction and evidence
steady/tb.spice, .spiceinit, run.log, wave.csv; rtl/tb.sv, controls.csv, compile.log, run.log; controls.inc; steady_criteria.json; mapping_and_assumptions.json; independent_audit/README.md and summary.json; steady_summary.json, steady_analysis.json, final_summary.json. Scripts in parent analog directory: prepare_afe_rtl_startup_224us.py, run_afe_rtl_224us.py, analyze_afe_rtl_224us.py. NumPy boolean JSON export error was fixed only by bool conversion and prior error log preserved; saved waveform reanalysis did not rerun SPICE.
