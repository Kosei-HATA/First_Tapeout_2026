# Current full AFE initialization/speed pilot
Requested:4 full128kHz periods (31.25us),1process,600s wall limit.
Observed:4.5847s wall, TRAN aborted at2.54028ps due timestep too small in e.xb.xcvbn_3.ec_moscap#branch. Only4 waveform rows; no chopper cycle completed. Process returncode0 must not be interpreted as success. No gain measurement.

## Circuit correspondence
Original current eeg_afe top, not amp-only: actualCin/Cf/Cpf, SCfeedback, offsetDAC, reset, hold capacitors retained.
Original eeg_bias, IBIAS code2, boostP/N4units (codes1), external1.9/1.4Vreferences, realVCM output. Original MOSCAP library selected; no linear cap replacement.
Original eeg_afe_clk fed ideal128kHz digitalCHOP/CHOP_OUT,0delay,CHOP_ENhigh; blanking from1MCLK before to7MCLK after edges, MCLK32.768MHz. Real transistorclock stages, analog clock supply100ohm perrail and150pF decap; no dummygate loads because actual AFE gate loads connected.
Reset asserted through firstchopper period, then released. Offset magnitude/enable andCPFtrim all0; OFS0; OFPH driven byclock. Symmetric differential input planned0→100uV after reset, referenced to actualVCM, low-impedance ideal source.
Load uses actualRIN geometry16 explicit parallel wrappers/side intoVCM,≈18736ohm/side, full source-model impedance. This approximates an ideal ADC virtual ground; it is not a complete ADC loop.
Clock input is the documented representative digital setting, not a claim everyRTLconfiguration was simulated.

## Time constants and valid conclusions
Top comments identify two54.52fF SCtransfers/side/chopper period. ApproxRsc=1/(2*fch*Csc):71.65Mohm at128kHz,143.3Mohm at64kHz. Cf roughly2pF gives internalRC≈0.14/0.29ms. 5–10such internalconstants suggest0.7–3ms as a diagnostic duration, not proof of settling or baseband pole.
Because inputchopper modulates electrodeDC tocarrier, this RC is not directly the electrodehigh-pass cutoff. True transfer requires periodic operation and matched input/output modulation, not a stationaryDC shortcut.
The old62.5–218.75us gain window cannot be assumed settled for fulltop. Define a differential transfer from paired+/-small input only after period-averaged outputs/internalstate show consistent multiple latewindows. Vary duration/timestep/amplitude before claiming midbandgain.
No walltime extrapolation is possible from the failed2.54ps run. Seconds-long0.5Hz transients must be separately planned after a valid shortcycle speed measurement. Full0.5–100Hz gain/noise needs DCservo/SC/offset and actualsource/load treatment, not a shortstartup ratio.

## Blocker and next steps
Current official MOSCAP model fails early transient in biasdecap. Previous bias/AFEbenches use moscap_lin approximation; their success does not remove this blocker.
Next isolate the failing biasMOSCAP and initialization/numerical behavior with originalmodel. If using linearizedcaps for a diagnostic, label it explicitly and validateC(V)/operatingpoint sensitivity; do not silently call that fullmodelgain. OriginalPDK/GDS/design unchanged.
Evidence:tb.spice,run.log,wave.csv,status.json. Script../run_afe_current_top_pilot.py. No settled gain or performance pass.
