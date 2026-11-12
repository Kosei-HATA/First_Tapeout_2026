# Nonlinear charge-integral diagnostic: four-cycle completion

Date: 2026-11-11 UTC. Two new simulations were performed, each bounded to 300 seconds. This is an analysis-only implementation experiment, not an official PDK model replacement or manufacturing acceptance result.

## Definition and mathematical equivalence
The official MOSCAP uses C(V)=A*(c1+c2*tanh(c3*V+c4)), where A is geometry times corner factor. The pinned ngspice source inpcom.c implements capacitance-form expressions as C(V) multiplied by measured dV/dt. Therefore this C is differential capacitance, not Q/V. The charge-form alternative is:
Q(V)=A*(c1*V+(c2/c3)*(ln(cosh(c3*V+c4))-ln(cosh(c4)))).
Its analytical derivative is the original C(V). Q(0)=0. Geometry is in m², coefficients in F/m², V in volts and Q in coulombs. Source current uses the simulator voltage-source sign convention; the reported replay currents have the opposite sign to current entering the capacitor.

The dedicated q_models.spice preserves NMOS/PMOS coefficients, terminal polarity, geometry and corner factor. It does not linearize C(V). All bias MOSCAP instances are mapped to these new names in bias_q_diagnostic.spice; the original bias and PDK files remain unchanged. The parent bias instance has m=1, and each original MOSCAP instance has m=1.

The independent mathematical audit covers 180 geometry/m/corner combinations and 1321 voltage points from -3.3 to +3.3 V per combination. Four-point central numerical derivatives differ from original C(V) by at most 5.27e-9 relative. Geometry uses three lengths and two widths, m=1/2/4/8/16, corner=0.9/1/1.1. This is arithmetic validation of multiplier scaling, not a SPICE validation of every hierarchy/m/temperature case.

The audit computes logcosh with logaddexp to avoid overflow. The actual SPICE expression uses ln(cosh()); over the tested interval its argument magnitude is at most 25.5625, far from overflow. Extrapolation outside this range is not authorized. Both diagnostic runs use 27 C and ordinary OP initialization, with initial terminal voltage zero. Other initial conditions or temperatures are unqualified.

## Simulator implementation is not identical
The official capacitance-form conversion in this pinned development build uses a large G source, internal 1 uF reference capacitor/current measurement and an added terminal 1e15 ohm regularization resistor. Its charge-form conversion uses a behavioral current source and an internal inductor. Thus equal analytical constitutive relations do not imply identical discrete integration, conditioning or regularization. The Q diagnostic does not reproduce the extra simulator-generated 1e15 ohm resistor. Finite differences and current discrepancies are explicitly retained, not hidden.

## Unit replay comparison
One combined deck evaluates official C and integral Q forms for both polarities under the same saved 8800-point voltage waveform. It finishes in 3.99 s. RMS current differences are 0.01427% NMOS and 0.01493% PMOS. Integrated endpoint-charge differences are 0.00664% and 0.01350%. Maximum cumulative charge differences are 6.626e-17 C and 5.243e-17 C, respectively, or 0.00375% and 0.00519% of maximum reference cumulative charge. These differences are not evidence of 16.5-bit precision.

The less-than-1% unit comparison gate only justified proceeding to a diagnostic full-top run. It is not a product acceptance specification.

## Full AFE diagnostic
Using the original four-cycle ramp stimulus and solver settings, with only the diagnostic MOSCAP implementation mapping, the full AFE finishes 31.25 us (4 cycles) in 116.57 s. Saved waveforms are finite. This is the first four-cycle completion in this investigation; it does not make the original official C-form startup issue disappear.

At selected common times before the old failure, maximum bias-node difference from C-form is 137.43 uV (0.5 us). At 7.8 us, VCM differs by about 1.875 uV. At the 31.25 us endpoint VCM is 1.565 V, so no settled gain is claimed. The existing waveform does not save source currents; full power/current qualification is unavailable.

Clock-driver outputs show transient rail excursions: RST -0.320 to 3.466 V, CIA -0.254 to 3.305 V and CDA -0.306 to 3.339 V. These require actual device terminal-stress and waveform-convergence analysis; node voltages alone do not prove an oxide or junction violation. No overshoot acceptance criterion is assumed.

## Limits and next decision
Original PDK/GDS/design files and previous outputs are preserved. No external issue was posted. The diagnostic suggests formulation/conditioning contributes to the observed failure, but does not uniquely establish a simulator bug. The missing finite-impedance current replay would require capturing per-port AFE-to-bias currents; existing waves do not contain them.

Before relying on this candidate for gain/noise, review its implementation equivalence, initial conditions, timestep/solver convergence, terminal stress and periodic settling. Any longer continuation must preserve the stimulus schedule, including blanking beyond the existing finite PWL sequence. Four cycles are not enough for steady state, 0.5-100 Hz response, PEX, mismatch/noise or manufacturing approval. No additional runs were launched.

## Evidence
summary.json, mathematical_equivalence.json, both cumulative_charge.csv files, q_models.spice and bias_q_diagnostic.spice; unit_equivalence/ and full_afe_q_diagnostic/ contain exact decks/logs/waves. Scripts in the parent analog directory: run_moscap_charge_equivalent.py, audit_moscap_charge_math.py, summarize_moscap_charge_top.py. Source implementation reference is ../ngspice48_isolated/implementation_excerpt.txt.
