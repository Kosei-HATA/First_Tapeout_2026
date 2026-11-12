# AFE original-stimulus numerical controls: unresolved startup

Date: 2026-11-11 UTC. This completes a bounded four-case numerical investigation. No further parameter search is scheduled by this test script.

## Unchanged physical problem
All tests retain the complete AFE, actual bias and clock driver, original nonlinear GF180 MOSCAPs, 100 ns VDD ramp, initial ideal references, VIT=1 V, 128 kHz clock and blanking, original 1 ns reset release, differential input schedule and explicit resistor loads of the four-cycle ramp pilot. The requested stop is 31.25 us. No linear capacitor replacement or circuit deletion is used.

The simulator is the isolated official pre-master-48 commit 8e03f9570eae8bb11dac18873587f052e7c8d02e, which identifies as ngspice-47+. Existing version 46, original GDS, model files and earlier results remain intact.

## One-variable comparisons
Original numerical settings: gear, reltol=1e-4, abstol=1e-12, vntol=1e-7, maximum timestep 1 ns, default Sparse 1.3. This is distinct from having KLU support compiled into the binary.

1. Matrix solver changed to KLU only: stops at 0.140915162924 us, 21.57 s runtime, v.xb.xcvbcm1_1.vcurrmeasc_moscap#branch.
2. reltol tightened to 1e-5 only: stops at 7.812651412967 us, 45.94 s, v.xb.xcvbn_3.vcurrmeasc_moscap#branch.
3. Maximum timestep reduced to 0.25 ns only: stops at 7.813172457307 us, 99.71 s, v.xb.xcvbcm_1.vcurrmeasc_moscap#branch.
4. Integration method changed to trap only: stops at 7.813215746576 us, 31.45 s, v.xb.xcvbcm_1.vcurrmeasc_moscap#branch.

Every case reports timestep too small. No case reaches four cycles or the differential input step. Matrix solver identity is printed in each log: KLU for case 1 and Sparse 1.3 for the other three. No tolerances were relaxed. Saved finite partial waveforms and a zero process exit code do not turn an aborted analysis into a pass. Voltage/current ranges and partial cycle counts are available in summary.json, but are not accepted operating or performance ranges.

## Conclusion
Startup with the real nonlinear model remains unverified. The limited numerical controls do not resolve the failure, and KLU performs worse in this specific scenario. A settled gain or electrode-referred noise claim cannot be based on these runs. The earlier linearized-capacitance or amplifier-only analyses must retain their limited scope.

The combined evidence is reproducible but does not yet isolate a minimal simulator bug: single-MOSCAP voltage replay succeeds, while the interacting full circuit fails around switching events. Do not report this as proven silicon failure or a demonstrated simulator root cause. Future work needs a justified circuit/model-level diagnosis rather than unbounded tolerance tuning.

## Reproduction and evidence
Run ../run_afe_numeric_controls.py in the existing Docker environment to reproduce the four sequential tests, each capped at 300 seconds. Each case directory stores the exact tb.spice, local .spiceinit, run.log and partial wave.csv. The script prints completed-case results and writes summary.json after each. input_integrity.json verifies the original 53 manifest inputs are unchanged.

The predecessor full-ramp deck is ../afe_ramp_fourcycle/ngspice47plus/tb.spice. The isolated binary is ../ngspice48_isolated/install/bin/ngspice. Build reproduction and pinned source details are documented in ../ngspice48_isolated/README.md. Packaging should retain scripts, exact decks, logs, waveforms and JSON, but omit the large source/build/install directories.

Official numerical-options reference: https://ngspice.sourceforge.io/docs/ngspice-44-manual.pdf , section 11.1.1. Sparse is the default; selecting KLU is a numerical matrix-solver change, not evidence that the physical circuit changed.
