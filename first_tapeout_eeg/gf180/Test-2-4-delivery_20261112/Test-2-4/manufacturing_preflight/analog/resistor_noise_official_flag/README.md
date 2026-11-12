# Resistor noise: verified official thermal-analysis workflow
2026-11-11. ngspice46, directory-local initialization only. Original PDK/GDS/functional/static32 data unchanged.

## Root cause and official support
PDK ppolyf_u_1k body has a voltage-dependent expression even though current coefficients r_vc1/r_vc2 are0. ngspice expands it into a behavioral current source. Behavioral-resistor white noise is disabled by default unless enabled on the instance or before netlist parsing. The body .model noise=1 did not enable that converted contribution in the tested flow.
Official manual, behavioral resistors:
https://nmg.gitlab.io/ngspice-manual/circuitelementsandmodels/elementarydevices/resistors,dependentonexpressions_behavioralresistor.html
Short excerpt: “As a default the behavioral resistor is noiseless.”
ngspice developer ticket614 (2023-01-27 final resolution):
https://sourceforge.net/p/ngspice/bugs/614/
Short excerpt: “Added a user definable variable enable_noisy_r (for .spiceinit)”
Relevant locations: maintainer edit2023-01-26 for instance noisy=1; final2023-01-27 message for global enable_noisy_r and per-instance noisy=0 override.
This is already supported in installed46; no new version installation/build was needed. Local source tree was not present; actual expansion plus behavior and maintainer documentation were checked.

## Preferred workflow
Use original unmodified decks/model with a fresh analysis-only directory .spiceinit:
set ngbehavior=hsa
set num_threads=1
set enable_noisy_r
Invoke /foss/tools/bin/ngspice directly from that directory. Existing sim_bin/ngspice rewrites .spiceinit without the flag, so do not accidentally use that wrapper for this noise flow. Do not alter global user initialization. .control is too late for flags needed during netlist parsing.

## Independent results
All8 original-deck cases completed: PDK1/2series/2parallel/double-length/85C, idealR, noiselessR and idealB.
Five PDK cases and idealR: PSD/4kTR=0.9999996523, same simulator physical-constant precision. Negative controls remain0.
One PDK resistor noise recovered from1.695nV/sqrtHz to70.492063nV/sqrtHz, matching thermal expectation.
Independent verification-only copied subckt with only body-instance noisy=1 gives identical results; see ../resistor_noise_instance_fix. This confirms the official flag result without idealR substitution.
Copy-model DC ±1uA change <=2.787e-13V, AC relative resistance change <5e-13 across tested sizes/temperatures/topologies. No intentional circuit characteristic changes. Official flag and copied-instance spectra agree.
Raw evidence in case directories, summary.json, and instance_fix/dc_comparison.json. Three negative/positive controls were rerun with the flag, not merely inferred.

## Scope and remaining blockers
Thermal-only compatibility verification. It does not demonstrate preservation/calibration of model kf/af flicker noise at finite DC, nor voltage-coefficient noise behavior, physical matching, PEX or chopper/noise folding. Do not call this foundry model certification, manufacturing signoff or ADC16.5bit qualification.
The original unflagged noise results remain invalid for complete body thermal noise. Correctly flagged future stationary noise analysis can proceed with explicitly documented thermal scope. Before system SNDR claims, reconcile flicker, source/AFE/ADC noise ledger, current circuit parameters, actual chopping/decimator, and missing resistor local mismatch.
