# Mismatch/noise model audit and next pilot plan
Date: 2026-11-11. Investigation only; no new heavy simulation started. Existing static32 outputs and delivered ZIP untouched.

## Highest priority: prove model coverage and reproducible sampling
The installed models/design.ngspice executable defaults are sw_stat_global=0 and sw_stat_mismatch=0 (lines62/63), despite an earlier descriptive comment discussing defaults1/1. Follow executable values.
nfet_03v3/pfet_03v3 wrappers (sm141064.ngspice approx46931/46945) contain local agauss samples for Vth and current coefficient, mapped to delvto and mulu0 under sw_stat_mismatch.
ppolyf_u_1k (approx38786) has no sw_stat_mismatch/local random term. Its rsh/width/terminal variations use sw_stat_global. Thus existing DAC --mc seeds evaluates MOS mismatch only, not the principal resistor unit-cell mismatch.
Official device table confirms ppolyf_u_1k Local Statistical=N, Global Statistical=Y:
https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_1_4_4.html
The section9.5 resistor mismatch heading is not evidence that this high-sheet-resistance device has a local model:
https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_9_5.html
Do not silently substitute ppolyf_u or invent a matching coefficient. A bounded assumed-error sensitivity can be useful, but must be labeled uncalibrated, not foundry Monte Carlo/yield.

Proposed first pilot, 1 process, about1–3min:
- Four netlist-expansion/operating-point cases: mismatch off seed1; on seed1 repeatA/repeatB; on seed2. Use exact ngspice46 executable, fixed model hashes, identical device order and decks.
- Examine all MOS delvto/mulu0 in expanded netlist. Repeatseed equality, differentseed differences, off=nominal; test duplicate identical device instances for distinct local samples.
- Extract resistor body/terminal values for each unit: prove local mismatch switch does not create resistor spread. Global variation, if later tested, is separate from local mismatch.
- Existing .options seed=N is intended seed setting, but confirm actual expanded parameters rather than assume syntax proves reproducibility. Explicit seed must occur before parameter sampling; a late control setseed without reparsing is insufficient.
- Save expanded listings, seed/version/hash, normalized parameter vectors and comparisons. Do not launch MC if same-seed samples differ or all instances share an unintended random sample.
Ngspice seed documentation:
https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf
https://nmg.gitlab.io/ngspice-manual/interactiveinterpreter/commands/setseed_settheseedvaluefortherandomnumbergenerator.html

After pilot validated and resources available:
- MOS-only mismatch seed1, code0/15/16/31, 12frame each. About8–12min at2parallel from static runs248–343sec/run; repeat representative code with same seed and seed2 adds~5–10min. This detects MOS switch/latch offset and repeatability, not full DAC matching or yield.
- Full32codes ~65–90min/seed with2parallel, not recommended before determining useful limits and resistor uncertainty.
- Avoid code-dependent seed/reordered random draws: same chip sample must be preserved across all codes. Verify expanded MOS parameter vector is identical across code decks before comparing INL.
- For ADC/AFE using large m or nf, separately audit PDK par (mismatch area) semantics. Electrical m scaling is not automatically proof of physically correct mismatch averaging across thousands of fingers.

## Physical noise coverage
ppolyf_u_1k body explicitly sets noise=1, af=1, kf=2.62e-26; terminal resistor model also has af/kf. MOS models/wrappers support device noise with fnoicor0 (as-extracted) /1 (worst flicker setting) documented in design.ngspice.
A normal deterministic transient with mismatch enabled is not a time-domain physical-noise simulation. Integration residuals, solver differences, and FFT numerical floors are not thermal/flicker noise.
Proposed inexpensive noise sanity pilot after seed audit: simple resistor/MOS bias point and .noise analysis, model noise versus analytic thermal sanity, compare fnoicor0/1. 1 process, seconds to few minutes. Check PSD units, amplitude-density versus PSD, differential summation and exact0.5/100Hz endpoints before integration.

## Existing system noise benches need reconciliation before reuse
gf180/tapeout/sim/adc_loop/ota1_noise.py uses old RIN9375, DAC branch300kohm, C1=680.5pF, AFE gains277/318 and frozen chopper harmonic sums. Current DAC branch is600kohm; do not reuse old noise-gain numbers unchanged.
gf180/tapeout/sim/afe/afe_noise.py describes frozen-phase approximation, intentionally noiseless electrode and RIN ledger terms and low-source-impedance reference. It explicitly warns high source impedance can invalidate the approximation.
Both are analytical/chopped estimates built from stationary .ac/.noise. They are not full periodically time-varying transistor noise or implemented-decimator SNDR.
First inventory exact current OTA/AFE/RIN/C1, biases, source impedance, chopping frequency and actual gain. Then rerun stationary noise and reconcile separate noise ledger. Estimate5–15min for a few small-signal points only after a dry setup check; no assurance until actual run.
Noise aliasing, cyclostationary behavior, switch sampling and decimator response need separate treatment. An uncalibrated injected behavioral noise sequence does not prove physical ENOB.

## 16.5bit traceability
Historical acceptance_source.json: SNDR>=101.100811dB, differential input0.943396mVpk, band0.5–100Hz, equivalent total residual5.876768nVrms. 4s records (20s low-frequency), frequency0.5/2/8/32/97Hz, amplitudes0.1/0.5/1x, actual decimator and gain calibration.
These are design targets, not established validation of currentGDS. Separate chip-intrinsic input noise from external source thermal noise and specify source impedance.
Before long full-loop verification, close resistor-mismatch model gap or report it explicitly, establish physical noise ledger, and reconcile actual clock1.024MHz/MCLK32.768MHz/decimation with acceptance. Nominal static DAC INL is not ADC ENOB.

## Completed short model-expansion pilot
See mismatch_seed_audit/README.md and summary.json. Ten cases completed, fixed-seed repeatability and distinct localMOS samples verified. Explicit res_statistical is required for resistor global randomness; res_typical keeps coefficients0. Across124 terminal models/31unit body expressions the statistical resistor variation is common in this tested engine, not per-instance local mismatch.
Important noise implementation caveat: ppolyf_u_1k body expands into a behavioral B current source. Whether its physical thermal/flicker noise survives conversion is unverified. A one-resistor .noise versus4kTR sanity check (1–3min, oneprocess) should precede larger circuit noise work. Model noise flags alone are not proof.
