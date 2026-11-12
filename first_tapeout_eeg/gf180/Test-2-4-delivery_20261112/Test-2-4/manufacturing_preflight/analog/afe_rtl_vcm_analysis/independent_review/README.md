# VCM ripple path independent read-only review

## Result

The approximately 95 mVpp value is the **VCM reference node**, not (OUTP + OUTN)/2. It is a repeatable input-chopper-edge transient. The strongest supported explanation is physical switch feedthrough/charge injection interacting with the present VCM loading and electrode-source return assumptions. The existing voltage-only data do not uniquely separate the contributions or prove that the Q model caused it.

No SPICE run was launched. No original source, deck, PDK, waveform or parent analysis was modified. Only this directory's README.md and summary.json were written.

## Independent waveform check

Source: `../../afe_rtl_startup_224us/steady/wave.csv`. The 651,759,420-byte file has 252,914 rows. Only 22 necessary columns were loaded with NumPy `usecols`; the column mapping is in summary.json. Evaluation remains 159.318117–221.818117 us. Window boundaries were linearly interpolated and every interior saved sample was retained.

- VCM reference: 1.612508605–1.707413670 V, 94.905065 mVpp; time-weighted AC RMS 2.132848 mV.
- Last complete cycle, 214.005617–221.818117 us: VCM 94.645990 mVpp, AC RMS 2.132083 mV. The spikes persist after cycle-mean drift becomes small.
- Output common mode, (OUTP + OUTN)/2: 5.137760 mVpp, AC RMS 0.361508 mV.
- Differential output: 10.751318 mVpp, AC RMS 1.541365 mV, mean 29.890697 mV. This mean is not offset-corrected gain.
- Internal (OPI + ONI)/2: 81.437728 mVpp. Input-stage and electrode-side common modes also show edge transients.
- VCLK: 2.805755968–3.300068689 V. VBN: 1.403425 mVpp; VBCM: 27.730285 uVpp.

AC RMS above removes each stated window mean and integrates the square of the piecewise-linear saved waveform. It includes deterministic switching ripple and any residual drift, not measured random noise. It is different from the original periodicity criterion's total differential RMS.

Final-cycle timing evidence:

- CIA rising 1.65 V crossing: 214.013528470 us.
- VCM minimum: 214.015268906 us, 1.740 ns later, at 1.612767680 V.
- VCM maximum: 217.919782415 us at 1.707413670 V; CIB rising crossing: 217.919824729 us, approximately 42 ps later.
- These crossings are interpolated observations, not claims of picosecond accuracy or numerical convergence. The large excursion is synchronous with switching, not proof of the unique current mechanism.

## Circuit versus bench assumptions

Paths below are relative to `manufacturing_preflight/analog` unless otherwise stated.

1. **VCM generation and missing external decoupling.** `moscap_charge_equivalent/bias_q_diagnostic.spice:30,161–163` and the unchanged `sim_work/gf180/tapeout/bias/eeg_bias.spice:30,161–163` describe two nominal 100 kohm resistors from VREFP through VCM to VREFN and explicitly say the VCM pad is decoupled off chip. There is no active VCM buffer. `afe_rtl_startup_224us/steady/tb.spice:15–69` has no explicit external VCM capacitor. The actual pad is labelled VCM/analog[9] in `Test-2-4/source/layout/chip_lay.py:622,688–690`. Layout connectivity is not a board-capacitance specification.

2. **Electrode return path.** `steady/tb.spice:34–36` connects the output terminals of ideal dependent sources between ELP/ELN and VCM, imposing ELP = VCM + SRC/2 and ELN = VCM − SRC/2. The saved wave obeys both constraints to <1e-15 V. Therefore these sources can return electrode-side charging current into VCM, rather than providing independent electrodes referenced to an external body/source impedance. This is a bench assumption, not a verified electrode/board model.

3. **Physical switching mechanism.** `sim_work/gf180/tapeout/afe/eeg_afe.spice:13–16,57–60` contains real input TGs with NMOS W20 um and PMOS W40 um, each m=256. They precede the roughly 636 pF per-side Cin arrays (`:337–371,378–379`). `eeg_afe_clk.spice:5–9,40–59` describes/drives these large gate loads. Charge injection and feedthrough are real-circuit candidate mechanisms. Saved timing strongly supports this switching path but does not quantify its separate current contribution.

4. **VCM is not capacitance-free or unloaded.** CMFB reference gates connect at `eeg_afe.spice:43–51,66`. With OFEN=0, disabled OFFDAC groups park their top plates at VCM (`:79,100–107,193–200`), with about 61.38 pF nominal MIM per half, about 122.76 pF total (`:114–178,207–271`). CPF trim also has VCM parking paths (`:304–334`). Reset controls are confirmed in `prepare_afe_rtl_startup_224us.py:6` (OFEN=0, OFM=0, CPF=8). In addition, `steady/tb.spice:38–69` returns OUTP and OUTN through 16 parallel resistors per side to VCM. These paths and device parasitics matter to both transient loading and settling.

## Existing 100 nF examples, not a settled board requirement

- `sim_work/gf180/tapeout/sim/adc_loop/adc_deck.py:14,104`: explicitly describes and instantiates `CVCMPAD VCM 0 100n`.
- `sim_work/gf180/tapeout/sim/e2e/e2e_deck.py:92`: the same 100 nF capacitor.
- The end-to-end example also has 100 ohm electrode series resistors at `:94–99`, absent from this startup deck.

These are historical bench assumptions. They do not authorize adopting 100 nF as the actual external capacitor or copying the old benches' other modelling shortcuts.

Using the source's nominal divider values only, Rth is about 50 kohm and 100 nF gives about **5 ms**. This is an unloaded-divider estimate, not the full active circuit's settling time. Output return resistors, other loads, initial charge and startup can change it substantially. Adding an external capacitor may reduce ripple but also changes startup; the existing 224 us window cannot automatically establish settling for that new case.

## Q-model distinction and preservation

No integral-Q capacitor is connected directly across VCM. The substitutions occur in 21 bias-filter/decoupling instances and 10 VCLK-decoupling instances (`bias_q_diagnostic.spice:66,86–95,125–149`; `steady/tb.spice:21–33`). They can influence VCM indirectly through bias and clock waveforms. The observed VCLK droop makes that clock path worth separating; it does not prove a Q-specific artifact.

`q_models.spice:1–7` is the analytical integral of the original nonlinear C(V). The prior `moscap_charge_equivalent/README.md`, section “Simulator implementation is not identical,” explicitly distinguishes constitutive equivalence from integration/conditioning equivalence. No original PDK replacement or qualification is implied.

Independent byte comparisons confirmed original `C:/projects/ft/test1x/gf180/tapeout/` bias, AFE, AFE clock and end-to-end deck files equal their sim_work copies. SHA256 values are recorded in summary.json. The Q bias text equals the source text exactly after only the two MOSCAP model-name substitutions. This review did not modify any of these files.

## Bounded next diagnostics (proposals only)

1. Complete the planned zero-input comparison with unchanged topology, startup/control sequence, solver and evaluation window. It separates input-dependent response from offset/switching behavior, but cannot alone identify the VCM-current contributor.
2. In a separate labelled bench diagnostic, change only the ideal electrode-source return to ground while preserving the intended common-mode waveform. Save source currents. This tests artificial return-path loading; it is not a realistic electrode model or acceptance result.
3. Obtain actual VCM-pad capacitance, ESR/ESL, electrode/source impedance and startup requirements. If unknown, use explicitly hypothetical sensitivity cases rather than silently selecting 100 nF. Declare runtime bounds and applicable startup/ripple criteria before execution.
4. Save currents through EP/EN, the divider, output-load returns, CMFB-reference/parking paths and any external capacitor. Integrate per-edge charge and check KCL. Existing voltage-only waveforms cannot uniquely allocate the approximately 95 mVpp excursion.
5. Separate clock-supply/bias-model and timestep/solver sensitivity in bounded diagnostic cases, with original PDK preserved. Do not merge such changed-condition results into the original periodicity pass.

The original fixed-eight-cycle periodicity PASS remains limited to its declared criteria. It is not a low-ripple, random-noise, ENOB, slow-settling, PVT/mismatch, or full ADC/DWA acceptance result. No additional investigation or simulation was initiated by this saved review.
