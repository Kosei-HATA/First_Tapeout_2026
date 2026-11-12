# Current-LVS 3.6 V startup/periodic stress and bounded controls

Two previously unexecuted controls were run after reconnecting MY-NOTE-2 and confirming no ngspice process or duplicate result existed. Both use the same current-LVS common-AVSS topology and preserve the original four-cycle waves and Q model.

## Startup controls, identical 0-1 us comparison interval
The reference is the saved 3.6 V TT27, 1 ns maximum-timestep run, cropped/interpolated to exactly 0-1 us.

| Case | Maximum gate-pair magnitude | Time above 3.63 V for that pair | Runtime |
|---|---:|---:|---:|
| Reference, 1 ns | 3.665517020 V | 3.313944603 ns | Existing record |
| Maximum timestep 0.25 ns | 3.665122777 V | 3.294887924 ns | 17.95 s |
| Q with 1e15 ohm terminal resistor, 1 ns | 3.665517105 V | 3.313944617 ns | 8.91 s |

Both new runs reach 1 us, with finite saved data and no analysis-abort diagnostic. The peak remains at output TG PMOS xa.xamp.xop_a.xp, VGB: gate NCDA, body global VDD, drain xa.opi, source OUTP. The smaller-timestep result changes the peak by -0.394 mV and exposure by -0.0191 ns; the excursion remains. Two time grids do not establish asymptotic numerical convergence.

The regularization comparison retains the original 1 ns maximum timestep, so resistor addition is its only numerical/model change. RREG 1 2 1e15 is added to both dedicated Q wrappers, affecting every bias/local-decap instance using them. It matches the explicit terminal resistance inserted by the pinned C-form implementation for these m=1 instances. It does not make the Q internal state/integration implementation identical to C form. Peak change is about +85 nV in this test. No statement about arbitrary states, geometries, multipliers or noise equivalence follows.

## Timing and source conditions
VDD rises from zero to 3.6 V over 0-100 ns. Ideal VRP=1.9 V, VRN=1.4 V and VIT=1 V are already present at t=0. Ideal logic amplitudes remain 3.3 V independently of the supply ramp. Reset is held asserted until 7.8125 us, then falls in 1 ns. Differential input does not change until 7.9125-7.9135 us. This is an explicitly specified diagnostic power sequence, not a confirmed board sequence.

At the reference worst startup time 0.532001308 us, NCDA=-0.065517020 V, body VDD=3.6 V, local VCLK=3.597241864 V and RST=3.595308374 V. Thus |VGB| is derived from actual terminals, not an assumed signal-to-ground rating. CIA is 3.598944798 V, CDA 3.551536597 V, and the device drain/source are 1.114594791/1.298431801 V. The input/reset stimulus has not yet been released or stepped. There is no external clock/reset transition at exactly this peak; it occurs in the initial circuit transient after first CHOP and BLANK transitions. Therefore its physical relevance depends on the real power/clock/reference startup sequence, which remains unspecified.

## Period-separated baseline result
All windows below come from the original four-cycle 1 ns record. Every exceeding device/pair and its interpolated exposure is preserved in summary.json.

- 0-1 us: 10 exceeding gate pairs. Worst xa.xamp.xop_a.xp VGB = 3.665517 V at 0.532001 us; exposure 3.313945 ns.
- 1-7.8125 us: 8 exceeding gate pairs. Worst xc.xcda3.xn VGS = 3.644228 V at 3.925821 us; exposure 0.097330 ns. This lies within the BLANK rising interval beginning 3.925732 us.
- 7.8125-15.625 us: 28 exceeding gate pairs. Worst xa.xoff.xop.xnph.xp VGS = 3.647154 V at 7.869922 us; exposure 0.035812 ns. It follows the next CHOP rise through the real input-phase/latch/OFPH-driver path.
- 15.625-23.4375 us: 28 exceeding gate pairs. Same worst pair reaches 3.647179 V at 15.682433 us; exposure 0.036127 ns.
- 23.4375-31.25 us: 28 exceeding gate pairs. Same worst pair reaches 3.646557 V at 23.494937 us; exposure 0.035615 ns.

These post-startup events mean the concern is not confined to power-on. However, their very short interpolated exposures have NOT been checked with a finer timestep in this topology; the new fine run covers only the first microsecond. Do not reuse the earlier independent-GCLK grid comparison for these common-AVSS results. Three later cycles also do not establish steady-state duty/lifetime.

## Assessment and limits
The startup maximum survives both tested controls. The added 1e15 ohm resistor is not the explanation for that excursion in this scenario. The result remains a Q-diagnostic screen, not official-model startup validation or a current-GDS manufacturing/lifetime verdict. Current-LVS ideal substrate connectivity still omits finite substrate/rail/package impedance, and the old separated-return design intention remains a distinct unresolved issue.

The GF180 public reliability guide sets a thin-oxide DC gate-to-any-node limit of 3.63 V, while periodic allowance depends on duty and TDDB lifetime. No numerical lifetime waiver was assumed: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html . A confirmed power sequence and applicable transient reliability criteria are needed before interpreting these startup/periodic excursions as acceptable or unacceptable physical operation.

No tolerance relaxation, GDS change, original-PDK change, extra long gain run or further solver search was performed.

## Evidence
summary.json: five baseline phase windows and three matched startup datasets, including all exceeding pairs. run_summary.json: completion/runtime of the two new cases. Each case directory preserves exact tb.spice/.spiceinit, run.log and wave.csv. q_models_regularized.spice is an independent copy. Scripts in the parent analog folder: run_afe_lvs_startup_controls.py and analyze_afe_lvs_startup_controls.py.

## Final bounded power-sequence scenario
One additional 0-1 us run used the same 0.25 ns maximum timestep and the ORIGINAL unregularized Q implementation as the fine-grid control. Only external VRP, VRN and AFE_RST were changed: each rises proportionally from zero over the same 100 ns interval as VDD, reaching 1.9 V, 1.4 V and 3.3 V respectively. The later reset-release timing is preserved. VIT=1 V is unchanged; it is the ITST test-port bias source, not a source we silently reinterpret as a model parameter.

The electrode input common-mode is NOT an independent fixed external source in this bench. EP/EN are dependent sources referred to the actual bias-generated VCM. VCM therefore remains an internal circuit response rather than being forced to track VDD. CHOP/BLANK ideal 3.3 V stimuli and all other sources remain unchanged. This is a partial diagnostic startup scenario, not a complete board power-sequencing specification; some logic transitions still occur before the 100 ns supply ramp completes.

The new case finishes 1 us in 18.11 s, with finite data. Maximum gate-pair magnitude is 3.653432204 V at xa.xamp.xop_a.xp VGB, at 0.264939896 us, shortly after the first BLANK falling transition finishes at about 0.264123047 us. The maximum is lower than the unchanged-source fine-grid case (3.665122777 V), but four MOS/four gate pairs still exceed 3.63 V. The worst pair has 3.631562 ns total exposure, longest 3.319486 ns over two intervals. Worst VDS is 3.641042805 V at xc.xcda3.xp. Peak reduction is not a pass; exposure duration does not monotonically decrease, and the event moves in time.

This shows that the selected external-reference/reset sequencing affects the transient, but does not by itself eliminate the diagnostic concern. It does not establish a permissible or mandatory user startup sequence. Later-cycle behavior was not rerun under this altered startup.

## Next concrete work and required specifications
- Obtain the intended AVDD range and ramp-rate range, VRP/VRN availability/ramps relative to AVDD, clock/blank enable timing, reset assertion/release requirements, and electrode common-mode behavior during startup. None is inferred as a permanent requirement from these tests.
- Resolve the design-intended isolated clock return versus substrate-tied LVS topology, and obtain a suitable substrate/rail/package impedance model before interpreting the screen as physical terminal stress.
- Obtain the applicable transient gate-oxide/HCI acceptance criteria and lifetime/duty targets. The public 3.63 V DC limit alone cannot approve repeated short excursions.
- If diagnostic/model validity is accepted for investigation, the next engineering work is to examine the NCDA output-driver/load coupling and sequence-dependent transient under those specified conditions, then propose a narrowly scoped mitigation with phase-nonoverlap and functional revalidation. No GDS change is justified solely by these limited screens.
- Settled gain, band-limited noise and 16.5-bit performance remain separate unverified tasks. This checkpoint deliberately stops bounded startup/solver exploration rather than launching unbounded parameter searches.

Final checkpoint file: final_summary.json. It includes the original phase analysis, all matched startup comparisons and runtime summaries. summary.json and summary_with_ramp.json preserve earlier stages. The new independent case is ramped_refs_reset/; scripts are ../run_afe_startup_ramped_refs.py and ../analyze_afe_startup_ramped_refs.py.
