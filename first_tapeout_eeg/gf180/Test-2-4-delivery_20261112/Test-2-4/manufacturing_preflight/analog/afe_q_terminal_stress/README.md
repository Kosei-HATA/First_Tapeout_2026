# Q diagnostic: MOS terminal stress screen at 3.3 V

The unchanged four-cycle Q diagnostic was rerun once with only additional saved terminal vectors. It completed 31.25 us in 130.16 s with finite data. Connectivity was recursively traced through the actual AFE and clock-driver subcircuits. The resulting screen covers 58 MOS wrappers directly connected to RST, CIA/NCIA, CIB/NCIB, CDA/NCDA, CDB/NCDB or OFPH, using 47 saved nodes. It is not all-device or extracted-layout reliability signoff.

For each device, signed VGS, VGD, VGB, VDS, VDB and VSB were calculated from its actual mapped terminals, including local clock supply/ground. The report does not infer oxide stress from a single node relative to global ground. Duration above absolute thresholds is calculated using piecewise-linear interpolation of the signed terminal difference, treating positive and negative crossings separately. Fractions refer to this startup record, not steady-state TDDB duty.

Worst gate-to-terminal magnitude is 3.614497877 V: xa.xoff.xon.xnph.xp, VGD, at 23.488867459 us. The difference from 3.63 V is only 15.502 mV. Worst VDS is 3.462463434 V at xc.xbn4.xn. No monitored gate pair or VDS exceeds 3.63 V in the saved record. Direct RST/CIA/CDA-connected groups reach 3.466180512 / 3.419292493 / 3.368585658 V gate-pair magnitudes, respectively. Their total time above nominal 3.3 V is 6.25556 us / 1.98781 ns / 2.01557 us for the reported worst pairs; this is not itself a violation of the 3.63 V DC limit.

Official basis: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html , sections 14.1.2 and 14.1.4. The thin-oxide DC gate-to-any-node limit is 3.63 V. Periodic overvoltage allowance depends on duty and TDDB lifetime; the page does not provide a numerical duty/lifetime acceptance table. VDS reliability also depends on conduction and hot-carrier effects. Therefore this screen is not lifetime prediction, and no universal transient waiver is assumed.

The single typical27 C, 3.3 V run uses the integral-Q diagnostic MOSCAP implementation and 1 ns maximum timestep. It has no demonstrated transient-peak convergence, PVT coverage, mismatch or PEX. It measures wrapper terminals rather than all intrinsic nodes behind model series resistance. The small 15.5 mV margin must not be presented as robust reliability compliance.

No extra 1e15 ohm resistor was added to the Q model for this measurement. Such an addition would match one part of the official C-form simulator regularization, but would constitute a separate numerical comparison. At 3.3 V its DC current is only 3.3 fA; its possible conditioning role cannot be dismissed on current magnitude alone. The present dataset is deliberately unchanged so it remains comparable with the first four-cycle Q diagnostic.

Evidence: summary.json, connectivity.json, exact tb.spice/.spiceinit, run.log and wave.csv. Scripts: ../run_afe_q_terminal_stress.py and ../finalize_afe_q_terminal_stress.py. No original PDK, GDS or prior output was replaced.

## Subsequent supply-model scope correction
Current Test-2-4 LVS reference joins AVSS_CLK to AVSS and uses ten 28.6x92 um MOSCAPs, not an independent 100 ohm return with ideal 150 pF. These stress values are diagnostic-bench results, not confirmed current-GDS terminal voltages. See ../afe_q_stress_convergence/README.md for source/LVS reconciliation and the matched-window timestep comparison.

