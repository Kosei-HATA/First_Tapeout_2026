# Reset and clock-event isolation (2026-11-11 UTC)

Three sequential bounded tests used the same full AFE, original PDK MOSCAPs, 100 ns VDD ramp, fixed references, VIT=1 V, external loads and isolated ngspice development commit as the preceding four-cycle pilot. Each had a 300 second wall limit and a 31.25 us requested stop. No solver setting or circuit/model element changed. Only the reset stimulus changed, as recorded in each deck. These are deliberately altered physical test scenarios, not design fixes or production startup qualification.

## Results
- Reset held high: failure at 7.83248249034359 us, runtime 37.96 s.
- Reset release delayed to 10 us with the original 1 ns fall: identical failure time, runtime 37.10 s. The saved waves are exactly identical to held reset up to this failure, before the delayed event exists.
- Original release start at 7.8125 us but 100 ns fall: failure at 7.86285589779833 us, runtime 33.23 s.

All three failures report timestep too small at v.xb.xcvbcm_1.vcurrmeasc_moscap#branch. All saved terminal samples are finite, but none completes four cycles or the planned input step.

The held/delayed failure time matches the BLANK rising-edge end at 7.83248242187 us to about 0.068 ps. The 100 ns slew case gets past that event but fails during/just after the CHOP rise beginning at 7.8625 us (0.5 ns rise). Thus reset deassertion is not the sole trigger, and the result does not support attributing the failure only to the original absolute time. Switching-event numerical conditioning is implicated, but the exact solver/internal-state root cause is not established.

## MOSCAP diagnostics and limitations
Across saved samples, the monitored NMOSCAP terminal voltages range from 0 to 1.92696 V. The GP-to-VDD PMOSCAP terminal range is -1.45362428 to 0 V. No gross overvoltage beyond the 3.3 V device designation is visible in these saved terminals; this is not proof of full model-domain validity.

The original problem-instance VBCM1 MOSCAP has a smooth, strictly positive calculated C(V), ranging from 30.84 fF to 4.94957 pF in startup. Its saved internal auxiliary voltage tracks VBCM1 within 7.33 nV. This monitors the earlier xcvbcm1_1 instance, while the latest failure names xcvbcm_1. The saved converged values do not expose rejected Newton iterations or prove absence of an internal current-conditioning defect at the failing instance.

Official model documentation https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_6.html leaves Model Limitations and Restrictions as “To be added.” Consequently a characterized transient-voltage/geometry validity region cannot be certified from that page. The tanh model itself has no mathematical voltage discontinuity; smoothness alone does not ensure transient solver robustness.

## Next decision
A long settling/gain run remains unjustified. A next limited investigation could keep reset asserted and shift or hold the blanking/control event in a dedicated diagnostic, while separately testing one solver/timestep change against the unmodified stimulus. Timing changes must remain explicitly distinct from numerical changes and cannot be adopted as a functional fix without checking nonoverlap and signal behavior. No further runs were launched.

## Evidence
summary.json includes exact reset definitions, input hashes, timing, runtime, diagnostics, full saved-vector ranges and selected internal-node comparisons. held/, delayed_10us/ and slew_100ns/ each contain the exact deck, local settings, log and partial wave.csv. Reproduction scripts are ../run_afe_reset_isolation.py and ../summarize_afe_reset_isolation.py. Original decks, models, GDS and both simulator installations are unchanged.
