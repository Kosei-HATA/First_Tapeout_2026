# Q diagnostic upper-supply terminal-stress screen: 3.6 V

This single TT, 27 C run completed 31.25 us (four 128 kHz cycles) in 132.33 seconds. Saved waveforms are finite. It is a diagnostic stress screen, not official-model qualification, lifetime prediction or manufacturing approval.

## Exactly changed condition
Relative to the 3.3 V terminal-vector run, only the VDD PWL endpoint changes from 3.3 to 3.6 V; its 100 ns rise time is unchanged. VRP=1.9 V, VRN=1.4 V, VIT=1 V, electrode stimulus, 3.3 V ideal clock/reset/blank input amplitudes and timing remain unchanged. The physical clock driver and AFE run from the changed supply and existing rail impedances. This is not a blanket claim that every control amplitude was scaled to the upper supply. The same Q-integral diagnostic MOSCAP implementation and solver settings are retained.

## Results requiring attention
Among 58 directly clock-connected MOS wrappers, 40 have at least one saved gate-to-terminal magnitude above 3.63 V (64 VGS/VGD/VGB pairs). The full results and threshold exposure durations are in summary.json and terminal_stress.csv.

Worst gate stress: xa.xoff.xop.xnph.xp, a PMOS inverter receiving OFPH in the offset-DAC. Gate=OFPH, source/body=VDD, drain=xa.xoff.xop.nph. VGS reaches -3.955384389 V at 23.488804115 us. Its absolute VGS exceeds 3.63 V for 3.484539 ns total, longest interval 1.293372 ns, six intervals in this record. This reflects a negative OFPH excursion relative to the 3.6 V source, not merely an absolute output voltage reading.

Worst drain-source stress: xc.xan4.xn, NCIA final driver NMOS. Drain=NCIA, gate=xc.an3, source/body=GCLK. VDS reaches 3.788097704 V at 23.488638488 us; time above 3.63 V is 0.730756 ns total, longest 0.247802 ns.

Direct RST group: xa.xrstp VGB reaches 3.773481824 V; >3.63 V total 0.254533 ns, longest 0.130537 ns.
Direct CIA group: xc.xol1.xpa |VGS| reaches 3.724168657 V; >3.63 V total 0.291597 ns, longest 0.097256 ns.
Direct CDA group: xc.xcda2.xp |VGD| reaches 3.670822219 V; >3.63 V total 0.479057 ns, longest 0.068991 ns.

Durations use piecewise-linear interpolation of signed voltage differences with positive and negative crossings evaluated separately. They are sampled-wave estimates. Record fractions are startup-record fractions, not demonstrated steady-state duty cycles. Peak/duration convergence has not been established, particularly for the shortest intervals.

## Interpretation and limits
Official basis: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html , sections 14.1.2 and 14.1.4. Thin-oxide gate-to-any-terminal DC limit is 3.63 V. Periodic overvoltage acceptance depends on duty and TDDB lifetime, with no numerical waiver table on that page. Hot-carrier/VDS reliability also depends on conduction and operation history. Thus these transient exceedances are material unresolved stress concerns, not proof of immediate failure or a quantified lifetime. They cannot be dismissed solely because the intervals are short.

This is one typical, schematic-level, Q-diagnostic run. It does not validate official C-form startup, PVT/PEX/mismatch, full-chip/all-device stress, intrinsic nodes behind model series resistance, or long-term steady operation. No design change was made. Do not proceed to manufacture based on this screen.

The appropriate next step is to confirm the peaks with a controlled timestep/convergence comparison and examine the clock-driver rail/ground movement and OFPH coupling before proposing a circuit mitigation. Any mitigation must then preserve phase nonoverlap, settling and functionality. No extra run or mitigation was started here.

## Reproduction and evidence
Exact deck/settings/log/wave.csv; connectivity.json; final summary.json; terminal_stress.csv. Scripts in parent analog directory: run_afe_q_terminal_stress_3p6.py and finalize_afe_q_terminal_stress_3p6.py. Original 3.3 V results, PDK, GDS and simulator installations are preserved.

## Subsequent supply-model scope correction
Current Test-2-4 LVS reference joins AVSS_CLK to AVSS and uses ten 28.6x92 um MOSCAPs, not an independent 100 ohm return with ideal 150 pF. These stress values are diagnostic-bench results, not confirmed current-GDS terminal voltages. See ../afe_q_stress_convergence/README.md for source/LVS reconciliation and the matched-window timestep comparison.

