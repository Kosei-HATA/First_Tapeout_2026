# Saved-wave MOSCAP reduction (2026-11-11 UTC)

## Outcome
The full-circuit timestep failure was NOT reproduced by this terminal-voltage-driven single-MOSCAP reduction. All four bounded comparisons completed in 2.16-2.51 seconds, with finite saved values and no timestep diagnostic. This negative result does not establish that either the full circuit or the simulator is correct.

## Target and stimulus
The latest failing branch belongs to XCVBCM_1, connected VBCM to VSS in eeg_bias. It is one cap_nmos_03v3 wrapper, c_length=28.6u, c_width=44u, implicit m=1. The original circuit also contains a second parallel wrapper XCVBCM_0, a ppolyf_u_1k resistor from NC to VBCM (1.8u by 2u), a diode-connected NFET and a PFET mirror upstream, and AFE loads. Those interacting elements are deliberately not represented by an ideal terminal-voltage replay.

The official typical equation is C(V)=28.6e-6*44e-6*(0.002003+0.00198*tanh(6.25*V-3.9375)). The positive terminal is VBCM and the negative terminal is VSS=0. No PDK equation was modified.

The held-reset full-circuit wave provides all 8,800 converged VBCM samples from 0 to 7.832482490343594 us. Time points are strictly increasing; the minimum interval is 1.61275e-18 s. All points were written with 17 significant digits into stimulus.inc, without resampling or filtering. The initial terminal voltage is zero; ordinary OP initialization is used, not UIC. The waveform is driven by an ideal voltage source, so the original finite driving impedance and internal MOSCAP state are not preserved.

A further 100 ns of constant final voltage is appended only to test endpoint holding. This added interval is not a measured full-circuit trajectory and must not be described as the original circuit surviving beyond its failure.

## Four comparisons
Version 46 and the isolated official pre-master-48 commit (reported ngspice-47+) each evaluated:
1. The unchanged official single MOSCAP, explicit m=1.
2. A diagnostic linear capacitor of 4.578690217752828 pF, equal to official C(V) at the final replay voltage.

The linear capacitor is only endpoint small-signal equivalent. It is not equivalent to nonlinear startup charge over the full waveform and was never inserted into the real AFE. Maximum source current differs accordingly: approximately 16.014 uA for the official MOSCAP and 30.353 uA for the constant capacitor.

All runs use gear, reltol=1e-4, abstol=1e-12, vntol=1e-7, maximum timestep 1 ns and 27 C, with a 300 second wall-clock cap per run. Each reaches 7.932482490343595 us. Maximum replay-voltage discrepancy is 8.33e-16 V. These are numerical replay diagnostics, not gain/noise/precision acceptance tests.

## Interpretation and next scope
Saved converged terminal samples do not include rejected Newton iterations or the exact state that triggered failure. Ideal voltage forcing removes feedback through the surrounding circuit impedance. Thus this is not a minimal reproducer for an external bug report. Prior official issue #820 describes related many-capacitor numerical behavior, but similarity is not proof of the same cause. No external report was submitted.

Further reduction would need a reproducible finite-impedance bias/AFE environment or a state-preserving diagnostic around the clock event. No further runs were launched under this four-test scope. Original AFE, PDK, GDS and both simulator installations remain unchanged.

## Evidence
summary.json records source timing, stimulus hash, runtime and all four outcomes. stimulus.inc stores the complete replay. Each case directory contains deck, local settings, log and wave.csv. Reproduction script: ../run_moscap_saved_wave_replay.py.
