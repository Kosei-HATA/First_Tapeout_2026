# NCDA driver/load coupling: bounded diagnostic candidates

Two additional simulations were performed, each capped at 300 seconds. Both use the same current-LVS common-AVSS, TT27, VDD=3.6 V startup scenario, 0-1 us, maximum timestep 0.25 ns and original unregularized integral-Q MOSCAP implementation. Original GDS, PDK and source netlists are not changed. No clamp, ideal stiffening source or removal of the signal path is used.

## Mechanism supported by existing waveforms
NCDA drives the PMOS gates of the two phase-A output transmission gates, XOP_A and XON_A. Each original PMOS has W=40 um, L=0.28 um, m=8; their S/D nodes connect OPI/ONI to OUTP/OUTN. NCDA is driven by XCDA3, an actual CMOS inverter from CDAI, with s=8.

At 520-545 ns in the original diagnostic, OPI/ONI and OUTP/OUTN rapidly fall from about 2.7 V to near 0.01 V. NCDA undershoots by about 65 mV while CDAI remains near 3.6 V. This supports S/D-to-gate capacitive coupling from the loaded transmission gates into a finite-strength low driver. It is not a direct clock-input edge at that time. Individual model displacement currents are not decomposed, so this is mechanism evidence rather than an exclusive identification of Cgd/Cgs versus other parasitic terms.

## Candidate copies
1. ncda_driver_2x: only XCDA3 strength changes s=8 to s=16 in clock_ncda_2x.spice. Both W and nf follow the existing inverter parameterization. Other clock stages and loads are unchanged. This is an asymmetric diagnostic sizing change, not a balanced-phase production design.
2. output_tg_half: only the eeg_afe_output_tg NMOS and PMOS m values change from 8 to 4 in afe_output_tg_half.spice. All four output transmission gates use that same reduced-size subcircuit. Input TGs and clock drivers are unchanged. This changes both gate/parasitic load and conduction strength, not an isolated ideal capacitance.

## Results
All runs complete 1 us with finite saved waveforms. Same-window gate-pair screening uses the mapped 58 MOS terminals.

| Diagnostic | Maximum absolute VGB in original 500-560 ns window | Worst gate-pair magnitude over 0-1 us | Worst-pair exposure >3.63 V |
|---|---:|---:|---:|
| Unchanged baseline | 3.665123 V | 3.665123 V | 3.294888 ns |
| NCDA driver 2x | 3.632501 V | 3.657693 V | 0.858122 ns |
| Output TG half size | 3.628883 V | 3.652568 V | 0.358676 ns |

The original common-mode-fall excursion is substantially reduced by either lower driver impedance or lower transmission-gate loading. However, a different transient near 264.8 ns, immediately following the first BLANK release through the actual driver, becomes dominant. Both candidates still exceed 3.63 V, so neither is an accepted mitigation. The smaller peak does not establish reliability, settled gain or physical-chip behavior.

## Effects and side effects to keep separate
- Driver sizing: stronger low hold reduces kickback, but increases preceding-stage input capacitance, switching current and changes complement delay/edge speed. Faster edges may worsen charge injection elsewhere. No full-cycle nonoverlap validation was performed.
- TG sizing/load: smaller devices reduce coupled capacitance and gate charge, but increase ON resistance and may degrade settling, thermal noise or distortion. The changed amplifier common-mode trajectory also affects the measured peak. Do not attribute the entire improvement to capacitance alone.
- Edge shaping: slower complementary-clock edges could reduce the newly dominant BLANK-release transient, but may extend overlap or reduce effective settling time. It would not directly fix a later kickback while the clock input is already static. This candidate was not tested.
- Supply limitation: the earlier 3.3 V screen has more margin than 3.6 V, but imposing a permanent lower supply limit requires actual system specifications and must not be invented as a fix. Rail/decap changes also affect droop and timing and require the correct substrate/package model.

## RTL startup scope correction
A separate project review reported that the real RTL uses 32.768 MHz MCLK, asynchronous RESET_N assertion and two-flop synchronized release; during reset CHOP/CHOP_OUT/BLANK are zero, AFE_RST is asserted, and CHOP_EN is enabled. AFE_RST release is software-controlled. The first CHOP_OUT event can differ from subsequent blanked events. The present ideal clock/blank schedule and fixed 7.8125 us AFE reset release are NOT that complete RTL startup sequence.

Accordingly these comparisons isolate mechanisms only within the same diagnostic scenario. They do not establish real startup failure, a mandatory user power sequence or a permanent GDS correction. The project review should be integrated with exact firmware/control requirements before selecting any design mitigation.

## Limits and next concrete work
The two sizing/load perturbations support a coupled-load/finite-driver mechanism but do not resolve all transients. The bounded scope stops here; a third exploratory simulation was not needed. The next useful step is to construct the specified RTL/firmware-consistent clock/reset sequence, retain appropriate external-reference sequencing, and evaluate candidate effects on nonoverlap, settling and stress under that scenario. Physical substrate/rail/package impedance and transient oxide/HCI acceptance criteria remain necessary. Official nonlinear C-form startup is still unresolved; integral-Q is a diagnostic model formulation.

## Evidence
summary.json: same-window comparisons, all exceeding pairs, NCDA minimum context, endpoints and the separated original-peak window. run_summary.json: runtimes/completion. Each case directory contains exact deck/settings/log/wave. Dedicated clock/AFE copies are stored here, not substituted into original design files. Scripts: ../run_afe_ncda_candidates.py and ../analyze_afe_ncda_candidates.py. No external submission or GDS edit was made.

