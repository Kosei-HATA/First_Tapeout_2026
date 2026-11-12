# RTL-driven AFE startup and periodicity diagnostic

## Scope
This is a transistor-level AFE/bias/clock-driver diagnostic with logical control waveforms produced by the unmodified project RTL, not a full chip simulation. ADC analog loops, DWA feedback, quantizer, decimation performance, pad/board interfaces and finite substrate/rail/package impedance are omitted. RTL CODE input is fixed at 16 only to exercise the digital block; it is not an analog ADC result. Integral-Q MOSCAPs remain an analysis-only equivalent-form candidate, not a foundry-qualified substitute.

## Explicit assumed board scenario
AVDD and the ideal digital output amplitude ramp to 3.3 V during 0-1 us. External references ramp to 1.9/1.4 V over the same interval. MCLK begins at 2 us with nominal 32.768 MHz; absolute scheduled edges limit quantization error to the 1 ps HDL precision rather than accumulating rounded half-period error. RESET_N is released at 3 us. VIT remains the prior 1 V test-port bias. Electrode common-mode follows the actual internal VCM through ideal dependent sources, with no electrode impedance/noise model. These are assumptions pending board requirements, not permanent user constraints.

The RTL testbench uses actual SPI mode-0 bytes 0x20,0x02,0x64 at 2 MHz, starting CS assertion at 8 us and ending at 21 us. This clears only CONTROL.AFE_RST from reset value 0x74. It does not disable CHOP_EN or treat it as a clock stop. Register application is observed at 21.104006 us, after synchronized SPI completion. A 100 uV differential step follows one chop period later at 28.916506 us, with a 1 ns analog edge.

## RTL fidelity and mapping
The actual two-flop synchronized reset releases ADC_RST_N at captured time 3.037600 us; initial CHOP and CHOP_OUT rise at 3.068117 us with BLANK=0. Subsequent blanking is taken from the RTL, not hand-added. The event CSV is sampled 2 ps after logical updates; PWL starts its assumed 0.5 ns transition at that CSV time. Consequently a 50% analog crossing is approximately 252 ps after the logical RTL event. This is an ideal pad-slew assumption, not gate-level timing signoff.

CPF_TRIM reset value 8 maps CPF0/1/2 low and CPF3 high. Bias reset values 2/1/1 map IB1 high, IB0 low; BP1 low/BP0 high; BN1 low/BN0 high. The generator maps ports by name and asserts constant reset trims/offset settings throughout this test. All software writes are enumerated above; no other configuration writes occur. mapping_and_assumptions.json records connected RTL outputs, unused outputs, fixed/omitted elements, pin maps and original RTL file hashes. Independent review confirmed the names/bit orders and first-edge behavior.

## Pilot
The 32 us pilot completed in 146.21 s with finite waveforms and no analysis-abort diagnostic. It reaches the SPI reset release and differential input step. Endpoint VCM=1.51018 V is not evidence of settling. Monitored worst gate pair is 3.34836 V and worst VDS 3.38604 V within this assumed nominal-supply record. There is no steady-state evaluation window in the pilot, so steady_evaluation_available=false; short-run completion is not treated as steady operation.

## Fixed periodicity criteria and long-window plan
steady_criteria.json is the controlling engineering diagnostic criterion, not a device specification. Wait eight chop cycles after the last signal/control step, then evaluate two consecutive four-cycle windows, phase-aligned to rising CHOP. Evaluation is 96.818117-159.318117 us. All adjacent cycle changes must meet: differential-output mean <=1 uV, VCM mean <=100 uV, differential-output RMS change <=max(1 uV,0.1% of previous RMS). Both windows and every intervening comparison are retained; no unfavorable cycle is dropped. No steady gain, noise or ENOB claim follows from satisfying these periodicity criteria.

The 160 us diagnostic is one process with a 1200 second wall-clock limit. RTL and PWL were extended to 192 us beforehand. The complete earlier controls.csv prefix is identical; old 128 us CSV/testbench/PWL copies are preserved. Last observed digital event is at 190.781740 us and each PWL ends at 192 us, so clocks cannot silently freeze at 128 us during the 160 us test.

If periodicity fails, report the measured drift and estimate a justified next settling duration instead of repeatedly extending without bounds. A step-response ratio during transient is not substituted for a settled transfer measurement.

## Files
rtl/tb.sv, compile.log, run.log, controls.csv and preserved .128us versions; controls.inc and controls_128us.inc; mapping_and_assumptions.json; steady_criteria.json with prior versions. pilot/ and steady/ contain independent decks/settings/logs/waves. pilot_summary.json and pilot_analysis.json are complete. steady_summary.json and steady_analysis.json are complete; final_summary.json records the result and bounded next-step estimate. Reproduction scripts in the parent analog directory: prepare_afe_rtl_startup.py, run_afe_rtl_pilot.py, run_afe_rtl_steady.py and analyze_afe_rtl_startup.py.

## Completed 160 us result
Completed in 1035.004 s (17 min 15 s), exit 0, no analysis errors, all saved vectors finite at 160 us. Fixed periodicity criterion is NOT MET: VCM adjacent-cycle mean drift decreases from 1.55938 mV to 159.196 uV, still above 100 uV in every one of seven comparisons. Differential mean changes 0.269 to 0.122 uV and RMS changes 0.178 to 0.073 uV meet their respective limits. No criterion was changed. VCM endpoint is 1.648532 V.

The empirical VCM decay ratio is 0.683643 per 7.8125 us cycle (time constant 20.542 us). Extrapolation predicts the first sub-100 uV comparison after 2 additional cycles and a complete eight-cycle evaluation around 221.818 us. A possible future bounded test is 224 us with RTL/PWL extended to 256 us, estimated 24.2 min using actual observed throughput. This is only a local forecast, not observed settling; slower modes remain possible. No additional simulation was started.

The 58 selected MOS screen retains worst gate pair xc.xcda3.xn VGS=3.348361 V at 14.756459 us and worst VDS xa.xoff.xop.xnph.xn=3.386044 V at 10.888773 us. This is neither whole-chip nor reliability signoff. The final-cycle differential mean is 29.890272 mV; dividing this by the 100 uV input would mix offset with gain and is not valid. Scope remains nominal-supply assumed-sequence AFE/Q diagnostic only.
