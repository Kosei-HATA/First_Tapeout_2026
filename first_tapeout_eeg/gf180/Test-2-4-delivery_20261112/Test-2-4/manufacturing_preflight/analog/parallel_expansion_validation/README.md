# Full-wrapper parallel expansion validation and AFE-gain prerequisites
2026-11-11. Analysis-only; original PDK/GDS/design and delivered results unchanged.

## Expansion flow
../expand_resistor_parallel.py expands a literal integer m on a ppolyf_u_1k X-instance into m uniquely named X-instances, each m=1. All pins and other parameters are preserved. Each subcircuit therefore owns independent internal nodes, original terminal/body resistors/capacitances/noise sources.
No uniform noise multiplication or internal-body-only replacement is used.
Only literal positive integer m for this wrapper is supported; parameter expressions are rejected rather than guessed. This is a focused analysis helper, not a general SPICE parser or hierarchy-wide transformation. Use on reviewed netlist copies and retain mapping.json. Existing generated-name collisions must be checked by caller before application to a larger deck.
Local mismatch is absent from this wrapper; flicker validity remains unverified. Do not generalize to MOS m/nf/par or other wrappers without tests.

## Validation
20 original/expanded pairs,40 sequential short runs:
m1/2/4/8/16,27/85C,length291.28/582.56um,width1um.
Directory-local official enable_noisy_r, actual PDK coefficients, DCcurrent -1/0/+1uA, AC0.5..100Hz, zero-bias thermal noise.
Expanded4kTR PSD ratios:0.999999652332..0.999999652340.
Max original-to-expanded AC relative difference4.3603e-12.
Max DC voltage difference2.38698e-13V.
All results in summary.json, per-case decks/log/DC/AC/noise CSV and expanded-instance mappings.
This supports electrical/thermal equivalence only for tested conditions; no mismatch/flicker/foundry certification.

## Current AFE gain evidence
functional/afe_actual_bias.log reports typical27 gain275.6,SS85 268.6,FF-20 282.2. However afe_bias_noise.py explicitly derives frozen-phase gain and approximate chopped harmonic noise, uses only eeg_afe_amp with an ideal DC path, and delegates deck construction to afe_noise.py.
afe_noise.py lines186/187 still set RLOADP/N=9375ohm noiseless. Current eeg_adc.spice RIN is300kohm-unit m16, measured18736.091ohm. Therefore old gain/noise numbers are not verified current loaded system performance.
Existing afe_chop_gain.py is a useful methodological reference but uses imported cpf210 candidate, ideal clocks and old9375 load. It cannot be run unchanged and called currentGDS gain.
Current eeg_afe.spice is available with actual devices; eeg_afe_clk and bias are available. Existing bias validations support initial operating points, not the full periodic signal path.

## Proposed next gain workflow (not started)
1. Build independent bench using current eeg_afe top plus actual bias/clock controls, present ADC input passive load including measured/current geometryRIN and relevant wiring/hold caps. Confirm reset/blanking/CHOP and low-impedance source reference match intended operating mode.
2. Reuse OP data to verify DC state and transistor headroom; a frozen-phase AC run may be a diagnostic, not demodulated system gain.
3. Time-varying deterministic gain pilot: symmetric ±small differential input, actual chopper at intended64/128kHz, start with32–64chopper periods and inspect settling/period averages. 10–30minute wall-time budget for initial pair is an uncalibrated estimate; stop and report runtime after a shorter startup/4period dry run. Do not launch long runs before resource review.
4. Extend averaging duration and halve timestep; vary input amplitude to separate offset, gain and distortion. A short DC-transfer/chopped-average test establishes midband local gain only, not full0.5Hz AC-coupled response.
5. To claim0.5–100Hz electrode noise budget, obtain full frequency-dependent signal transfer under actual DC-servo/source impedance and integrate referred noise using|H(f)|, with alias/chopper/noise conversion handled separately. Low-frequency0.5Hz behavior may require seconds of simulated time or an independently validated multirate/periodic analysis. Do not extrapolate a250us transient to that band.
ADC RIN thermal248.603nVrms remains an ADC-input component. Divide by no assumed275.6/318 gain for acceptance. Electrode5.876768nVrms is total target, not a per-component allowance.
