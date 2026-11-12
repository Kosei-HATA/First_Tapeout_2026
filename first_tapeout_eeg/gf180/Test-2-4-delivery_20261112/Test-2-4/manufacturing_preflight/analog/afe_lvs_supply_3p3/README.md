# Current-LVS clock-supply diagnostic (Q implementation)

## Scope and topology
This is a separate diagnostic, preserving the earlier independent-return bench and its data. It follows the current Test-2-4 core LVS-reference connectivity, rather than the older isolated-clock-return simulation intention. The physical-design reference is not silently rewritten.

| Element | Earlier bench | Current-LVS diagnostic |
|---|---|---|
| Clock VSS | GCLK through ideal 100 ohm to global zero | Global AVSS (zero), matching the AVSS_CLK-to-AVSS LVS tie |
| Positive feed | Ideal 100 ohm | Official ppolyf_u_1k wrapper, VCLK to VDD, substrate zero, length 2 um / width 20 um |
| Negative feed | Distinct-endpoint 100 ohm | No isolation: current reference RRCKN has both endpoints at AVSS; an equal-endpoint resistor is electrically omitted |
| Local decoupling | Constant ideal 150 pF | Ten 28.6 x 92 um nonlinear MOSCAPs, using the same diagnostic integral-Q formulation |
| Model value | Voltage independent | Approximately 104.8 pF at saturated typical C(V), smaller during startup, before parasitics |

Source correspondence is recorded in ../clock_supply_model_reconciliation.json, with source hashes. Relevant locations are Test-2-4/source/layout/afe_lay.py (supply mapping/resistors/LVS tie), offdac_lay.py (28.6x92 um, rows [6,4]), chip_lay.py:678 (substrate ties), verification/prepare_core_lvs.py and verification/eeg_core_reference.cdl:23303-23315. The current reference connects clock VSS to AVSS and RRCKN AVSS AVSS AVSS. The delivered-core LVS reports Match under that convention.

The complete tie list also maps DVSS to AVSS. This AFE-only test does not instantiate the full digital block; only the clock-return correspondence is exercised. The layout's isolated-return intention and its substrate-tied LVS connectivity are distinct facts. LVS is not a finite-impedance substrate extraction. Shared-substrate, metal-route, package and bond-wire resistance/inductance remain unmodeled. This test does not resolve that physical-design intent discrepancy.

## Two cases and results
Only supply amplitude differs between the two new cases: VDD ramps in 100 ns to 3.3 or 3.6 V. TT, 27 C; reference voltages 1.9/1.4 V, VIT=1 V, ideal 3.3 V logic stimuli, reset/blanking/input schedule, full AFE, actual bias and external loads remain unchanged. The dedicated Q implementation is used for both bias and new local decoupling MOSCAPs. Solver and 1 ns maximum timestep are unchanged. Each run was capped at 300 seconds.

3.3 V: finishes 31.25 us in 130.38 s. Maximum gate-pair magnitude 3.354071136 V, output TG PMOS xa.xamp.xop_a.xp VGB at 0.579980 us. Maximum VDS 3.384990490 V. No gate-pair magnitude above 3.63 V in the monitored 58 MOS.

3.6 V: finishes 31.25 us in 132.07 s. Maximum gate-pair magnitude 3.665517020 V, the same output TG PMOS VGB at 0.532001 us. Its gate is NCDA, body VDD, drain xa.opi and source OUTP. The gate-body differential exceeds 3.63 V for one 3.313945 ns interval. Maximum VDS 3.684572191 V occurs in offset-DAC inverter NMOS xa.xoff.xop.xnph.xn at 7.869997 us, with total >3.63 V exposure 0.135233 ns. In total 24 monitored MOS have 36 gate-pair magnitudes exceeding 3.63 V.

All saved values are finite. The earlier approximately 3.955 V OFPH-to-global-supply stress from the independent-return bench is not reproduced as the current-LVS result. The smaller, differently located 3.6 V startup excursion remains a diagnostic concern. Neither result is a manufacturing or lifetime verdict.

## Interpretation limits
Official reliability basis: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html . The 3.63 V thin-oxide DC gate-to-any-node limit is not an unconditional transient allowance. Periodic overvoltage acceptance depends on duty and TDDB lifetime, and VDS/HCI stress also depends on conduction history. This startup record supplies no qualified lifetime calculation.

Only 58 MOS wrappers directly connected to clock-related signals are screened. Durations are piecewise-linear sampled estimates. Transient peak/duration convergence has not yet been checked for this new topology. The earlier smaller-timestep comparison belongs to the old independent-return bench and must not be reused as convergence proof here. This is not PEX, all-device, all-PVT, mismatch/noise or official C-form-model startup qualification. The integral-Q formulation's numerical regularization differences remain a separate limitation.

## Evidence
Each case preserves tb.spice, .spiceinit, run.log, wave.csv, connectivity.json, final summary.json and terminal_stress.csv. ../afe_lvs_supply_comparison.json summarizes both cases. Reproduction scripts: ../run_afe_lvs_supply_3p3.py / ../run_afe_lvs_supply_3p6.py and the corresponding finalize scripts. Old summaries have a supply_model_scope_correction field and pre-correction backup; their underlying waveforms/logs/numbers are preserved.

No original PDK, GDS or design source was modified. No new simulation or GDS mitigation beyond these two instructed diagnostic cases was launched.
