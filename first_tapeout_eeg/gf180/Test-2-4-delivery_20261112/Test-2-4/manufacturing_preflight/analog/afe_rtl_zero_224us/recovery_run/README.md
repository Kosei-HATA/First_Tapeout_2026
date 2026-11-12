# Zero-input recovery and offset-separated comparison

The original attempt was interrupted by PC/Docker loss and remains preserved in the parent directory. Installed Docker Desktop and the existing container were normally started, without settings/security changes. This identical-deck recovery completed in 1458.059 seconds, exit 0, to 224 us with finite waveforms. No new external capacitor was introduced.

Both zero and +100 uV cases satisfy all seven adjacent-cycle tests in the predeclared 159.318117-221.818117 us window. Phase-aligned time-weighted cycle means give one-sided sensitivity 298.906967120 V/V (49.510721 dB), range 298.903817142 to 298.909790579 V/V across eight cycles. The zero mean is -1.22096e-11 V, a numerical residual of an ideal nominal symmetric model, NOT physical offset precision or a noise floor.

This establishes only a conditional one-sided finite-difference response in the stated AFE/Q scenario. No negative-input control, full band response, noise, mismatch or ENOB is established. A step can have slower dynamics despite the local periodicity test. Original +100 uV inputs, controls, criteria and 13 RTL source hashes remain unchanged.

No external VCM capacitor is connected, but VCM is not capacitance-free: disabled OFFDAC plate groups park at VCM and contribute roughly 122.76 pF nominal MIM total plus parasitics; output loads and ideal electrode-source returns also connect to VCM. The historical 100 nF CVCMPAD example is not a board requirement. A 50 kohm * C estimate is only the divider-only approximation, not the full circuit time constant.

Files: steady/{tb.spice,.spiceinit,run.log,wave.csv}, steady_summary.json, steady_analysis.json, final_summary.json, offset_comparison.csv, input_manifest.json and recovery_manifest.json. Existing source model/GDS/RTL were not modified.
