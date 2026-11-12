# Full AFE four-cycle ramp pilot (2026-11-11 UTC)

Two identical-deck runs were performed sequentially, each with a 300 second wall-clock cap. Original PDK MOSCAP models and the complete AFE, bias and clock-driver circuits were retained. Existing version 46 and the isolated development commit 8e03f9570eae8bb11dac18873587f052e7c8d02e were preserved.

## Scenario and scope
VDD ramps from 0 to 3.3 V in 100 ns. Ideal VRP=1.9 V, VRN=1.4 V and VIT=1 V are present from the initial point. Clock and reset sources also have their defined ideal levels independently of the VDD ramp. This is a particular diagnostic scenario, not a realistic or certified power-sequencing specification. The initial operating point therefore has nonzero VCM/output voltages even while VDD=0.

The input chopper frequency is 128 kHz (period 7.8125 us), with the existing blanking waveform. Reset deasserts from 7.8125 to 7.8135 us. Differential input changes from zero to 100 uV from 7.9125 to 7.9135 us. Current full AFE SC feedback, trim/offset settings, reset and hold paths remain present. Each output is loaded by 16 complete explicit parallel ppolyf_u_1k wrappers, about 18736 ohm per side to the circuit VCM. These are load approximations to ADC RIN, not a complete ADC co-simulation. Clock supply impedance remains 100 ohm on each rail and 150 pF decoupling.

The original 0.5 us ramp deck was changed only by extending transient stop to 31.25 us and saving additional terminal waveforms. Maximum timestep remains 1 ns; gear, reltol=1e-4, abstol=1e-12 and vntol=1e-7 are unchanged. Both versions received exactly the same deck (SHA256 in summary.json).

## Results
Version 46 took 31.24 seconds and stopped at 7.813198956 us (1.000089 cycles), with timestep too small at e.xb.xcvbcm1_1.ec_moscap#branch.

The isolated development build took 32.94 seconds and stopped at 7.813171083 us (1.000086 cycles), with timestep too small at eco#branch.

Both failures occur during the first reset deassertion, before the differential input step. All saved values are finite, but neither run reaches the requested four cycles. Process exit code 0 is NOT a successful transient result: both logs explicitly report an aborted analysis. No gain, settling or startup pass is claimed.

Initial saved node values agree within 6.50 nV. At a common pre-edge time of 7.8 us, the maximum difference among VBN/VBCM/VCM/BLP/BLN is 45.12 nV. Selected common-time values at 0, 0.5, 1, 5 and 7.8 us are saved in summary.json. This numerical agreement is not proof of a correct steady-state operating point; VCM is still about 1.398 V at 7.8 us.

The observed runtime before failure is about 4 wall seconds per simulated microsecond, but this cannot predict crossing the problematic reset edge. A long settling run is not justified until that edge failure is isolated. No additional retries or solver modifications were made.

## Reproduction and evidence
Run ../run_afe_ramp_fourcycle.py for the two bounded simulations, then ../summarize_afe_ramp_fourcycle.py for saved-wave comparisons. Each simulator directory contains its exact deck, local initialization, run log and partial wave.csv. summary.json records all metrics and exact diagnostic nodes. Preserve these files when packaging.
