# Independent resistor-noise review

Read-only review of the original noise-model behavior plus one isolated small-signal replay. No PDK/model repair or competing fix was developed.

Conclusion: the reported thermal-noise coverage failure is confirmed quantitatively.

At 27 C (300.15 K), zero DC bias and 0.5 Hz:
- Re(Zout) from a 1 A AC ideal current stimulus: 299777.458524329 ohm.
- Im(Zout): -0.0035312 ohm, negligible for this check. The expectation uses Re(Z), not magnitude.
- onoise_spectrum: 1.695144533869008e-9 V/sqrt(Hz).
- inoise_spectrum: 5.654676446366082e-15 A/sqrt(Hz), because the specified input is a current source.
- onoise/inoise equals 299777.458524329 ohm, agreeing with AC impedance. The two noise columns are not confused.
- sqrt(4*k*T*Re(Z)) = 7.049207547448069e-8 V/sqrt(Hz).
- Measured/expected PSD = 0.0005782729424770971.

The circuit has no finite parallel load resistor or AC input voltage short. Its ideal current source supplies zero small-signal shunt conductance. The substrate capacitance is included in measured impedance and is negligible at this frequency. wrdata noise1 stores spectral densities, not integrated noise2 values, an FFT, or a finite-band RMS. The independent replay has output density flat across the requested band to relative 3.1e-12. Existing ideal-R positive control reproduces 4kTR with PSD ratio 0.999999652; the tiny offset is simulator physical-constant precision, not a material discrepancy. Existing ideal-B and noiseless-R controls give zero. Series/parallel controls and doubling body length are consistent with the same failure.

## Direct model evidence

The original source ppolyf_u_1k body resistor uses a voltage-dependent expression even though this nominal model's voltage coefficients are zero. The simulator's expanded listing represents that body as b.xr.brb, while r.xr.rt1 and r.xr.rt2 remain ordinary noisy resistors. See body_terminal_evidence.txt and expanded.log.

Independent arithmetic using the model's width/length, 25 C reference temperature and temperature coefficients gives:
- Body: 299604.1052710561 ohm.
- Each terminal: 86.67662664880463 ohm after the 27 C correction.
- Total: 299777.4585243537 ohm, agreeing with measured AC Re(Z).
- Noise of the TWO terminal resistors alone: 1.6951448285382474e-9 V/sqrt(Hz).
- Measured PSD divided by terminal-only predicted PSD: 0.9999996523374184, the same precision residual as the ideal-R positive control.

Thus the entire observed output thermal noise is explained by the terminal pair. The missing body contribution is not caused by output/input referral, wrong temperature, loading, resistance estimation or bandwidth integration. The stored `show r` report lists the uncorrected nominal terminal resistance 88.0565 ohm; it must not be confused with the temperature-adjusted resistance used by the small-signal calculation above.

This establishes the failure for this model/tool configuration. It does not certify any repair, finite-bias flicker model, device-noise corner or fabrication noise. Deterministic circuit-function results must be distinguished from physical noise qualification.

## Evidence

review.json contains the independent numerical checks and source-model SHA256. tb.spice is the replay deck; ac.csv/noise.csv are original simulator outputs; run.log, expanded.log, resistor_values.log and body_terminal_evidence.txt provide simulator evidence. Reproduction script: ../review_resistor_noise.py. The source model was not altered. The analog worker owns correction development and validation.

