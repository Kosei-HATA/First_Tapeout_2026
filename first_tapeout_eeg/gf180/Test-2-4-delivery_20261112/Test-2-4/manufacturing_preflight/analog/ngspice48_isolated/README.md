# Isolated ngspice development comparison (completed)

Official source: https://git.code.sf.net/p/ngspice/ngspice , branch pre-master-48.
Pinned commit: 8e03f9570eae8bb11dac18873587f052e7c8d02e.
This is a development build, not foundry qualification. Existing ngspice 46, original PDK and Test-2-4 design are not replaced.

## Reproduction and packaging
Include build_isolated.sh, run_comparison.py, commit.txt, remote_ref.txt, dependencies.txt, version.txt when ready, build timestamps, configure*.log, autogen.log, make.log, install.log, implementation_excerpt.txt, test_progress.json, comparison_summary.json when ready, and tests/.
Exclude source/, build/, install/ and any deps/ from the evidence ZIP. No downloaded dependency installation is used.

The first configure failed for missing readline headers. The second disables only interactive readline with --with-readline=no, and uses --without-x --disable-debug --enable-cider --enable-openmp. Compilation concurrency is make -j2.

## Implementation observations
The pinned inpcom.c capacitance expression conversion uses a G source, internal 1 uF reference capacitor, and a current measurement source. The multiplier is passed to the G source. The official conversion also inserts a 1e15 ohm terminal resistor; this is a simulator implementation difference and is not concealed as identical circuit topology. These observations are source inspection, source-level observations, interpreted together with the regression results below.

The initialization comparison copies the original 16 decks unchanged, preserves per-case startup method and solver, and uses the same 30 second wall-clock cap. Passing a short startup test does not establish the correct steady state or actual chopped gain. The resistor regression includes m=16 and explicit 16 parallel full wrappers with enable_noisy_r, plus the unflagged negative control. MOSCAP AC comparisons cover both polarities, voltage, length and multiplicity.

## Results (2026-11-11 UTC)

The isolated build completed at 14:04:54 UTC, 28 minutes 24 seconds after the successful configuration attempt began. The executable identifies itself as ngspice-47+, despite the official branch being named pre-master-48. The pinned commit, rather than the informal version label, identifies the tested code.

All 16 original initialization decks were copied without edits. All six single-MOSCAP cases now reach 1 us, including five cases that timed out after 30 seconds with version 46. The full bias and full AFE top still fail ordinary OP-to-transient startup with both gear and trap. The bias reaches 2 us with UIC/ramp, and the top reaches 0.5 us with UIC/ramp. These short runs do not prove a correct operating point, settled chopped gain, or system accuracy. The startup blocker remains.

The 60 MOSCAP small-signal comparisons cover NMOS and PMOS with the appropriate voltage polarity, five voltage points, length scaling of 1 and 2, and m of 1/2/4/8/16. Maximum relative difference from the official C(V) expression is 6.67e-16, and the saved capacitances are identical to the same decks evaluated with version 46. This validates these small-signal capacitances and tested multipliers only, not large-signal charge conservation across arbitrary waveforms.

The resistor multiplier noise limitation persists unchanged. In the same ADC RIN pair diagnostic, m=16 with enable_noisy_r gives 62.41977685 nVrms, while 16 explicit parallel complete wrappers give 248.60323113 nVrms over 0.5-100 Hz. The unflagged negative control gives 5.97823910 nVrms. This is not an electrode-referred system noise budget. Continue using the explicit-parallel thermal-analysis flow; do not apply a global numerical noise correction. Local resistor mismatch and flicker noise remain unqualified.

All 53 original inputs in the existing manifest are unchanged (input_integrity.json). No original PDK, GDS, or installed ngspice 46 was replaced. A NumPy trapz API mismatch interrupted only result processing after the first resistor run; the processor was changed to trapezoid and resumed from completed cases without rerunning them. The first driver log is preserved.

## Final evidence files

final_summary.json contains initialization, rin_noise, moscap_cv, cv_max_abs_analytical_relative_error and cv_max_abs_change_from46. comparison_summary.json is the earlier comparison output. tests/ contains all new-version decks/logs/waves; reference46_cv/ contains the independent old-version AC references. thermal_regression/ and thermal_regression_summary.json contain the additional eight-condition official-flag regression. Include all scripts, source provenance, build/configuration logs and input_integrity.json. Exclude source/, build/, install/ and any deps/ when packaging.

Relevant official issue records: https://sourceforge.net/p/ngspice/bugs/820/ (behavioral capacitor numerical implementation) and https://sourceforge.net/p/ngspice/bugs/876/ (multiplier handling). Source inspection is recorded in implementation_excerpt.txt. This development build is a diagnostic candidate, not a foundry-approved simulator replacement or manufacturing signoff.


The eight official-flag thermal regression cases all completed. Their saved AC and noise data are exactly equal to version 46 for these same decks, including hot/double-length/series/parallel cases and noiseless negative controls.


## Failure branch follow-up

The bias failure reports vit#branch. The unchanged test bench defines VIT ITST 0 1: this is a 1 V bias on the test-current output, not a zero-volt current measurement source. Replacing it by an ideal short would change the operating condition, so no node-merge experiment was performed. The full-top gear failure instead reports v.xb.xcvbcm1_1.vcurrmeasc_moscap#branch at 1.2744140625e-12 s. This is the new simulator-generated MOSCAP internal current measurement branch. Removing it would invalidate the behavioral-capacitance implementation and is not an equivalent external circuit simplification.
