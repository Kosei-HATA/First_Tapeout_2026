# Stress timestep comparison and clock-supply model reconciliation

## Completed numerical comparison
Exactly one additional simulation used the same 3.6 V TT27 Q-diagnostic circuit and stimulus, reducing maximum timestep from 1 ns to 0.25 ns and stopping at 8 us. The early interval already contains a substantial gate stress excursion. Comparison data are restricted to the identical 0-8 us interval; baseline data at 8 us are interpolated without extending the record.

Worst |VGS| at xa.xoff.xop.xnph.xp: 3.938699003 V (1 ns) versus 3.939193547 V (0.25 ns). Total time above 3.63 V: 0.911182 ns versus 0.912094 ns. Longest interval: 0.827988 ns versus 0.828779 ns. Both records have 64 gate pairs above 3.63 V. Worst |VDS| is 3.786874236 versus 3.786939077 V at xc.xan4.xn. Thus this bench's excursion is not removed by the tested smaller timestep. Two grids are not an asymptotic accuracy proof, and the Q regularization difference is a separate issue.

## Electrical mechanism within this bench
GCLK is the clock driver's explicit local VSS, not a measured voltage-source branch or an incorrectly named output. RCLKN GCLK 0 100 connects it to global ground. RCLKP VDD VCLK 100 feeds the local positive rail, and CCLK VCLK GCLK 150p couples the two rails. No inductor or independent voltage source floats GCLK in this bench. Every clock-driver VSS/body uses GCLK.

At the original full-record worst OFPH excursion, OFPH=-0.355384 V and GCLK=-0.355023 V, while VCLK=3.072506 V and global VDD=3.6 V. The receiver's source/body remain at global VDD. OFPH therefore closely follows the moving local return, producing the large receiver |VGS|. The 100 ohm ground resistor carries GCLK/100=-3.550 mA at that instant (sign defined from GCLK to global ground). The switching driver and capacitive rail network cause this bench's return movement. Individual transistor/capacitor currents were not saved, so a full transient KCL decomposition is unavailable.

The named receiver is an inverter PMOS, not a floating hold device. The SR latch and final inverter chain drive OFPH. The actual inverted signals in the two offset-DAC halves are NPH, not a net named OFNH; at the worst instant both NPH nodes are about 3.599545 V, with full-record ranges approximately -0.07117 to 3.63451 V. Capacitive feedthrough may contribute to these smaller receiver transients, but the main OFPH excursion is consistent with local return movement, not proven floating-node charge accumulation.

## Critical correction: this bench is not the current delivered-GDS supply model
The following source and LVS evidence was inspected, without new simulation:

| Item | Earlier diagnostic bench | Current design/LVS evidence |
|---|---|---|
| Clock return | GCLK to global ground through ideal 100 ohm | Source draws AVSS_CLK separation, but current LVS reference ties AVSS_CLK to AVSS |
| Ground resistor | RCLKN with distinct endpoints | eeg_core_reference.cdl:23305 RRCKN AVSS AVSS AVSS, endpoints identical after substrate convention |
| Clock positive feed | Ideal 100 ohm | ppolyf_u_1k wrapper, L=2 um, W=20 um, substrate AVSS |
| Local decap | Ideal constant 150 pF | Ten cap_nmos_03v3 units, each 28.6 by 92 um, AVDD_CLK to AVSS in current LVS reference |
| Capacitance value | Constant for all startup voltage | About 104.8 pF total at saturated typical C(V), voltage dependent; parasitics not included |
| Package/substrate | Ideal global rails, no substrate extraction | LVS gives connectivity, not substrate/rail/package resistance or inductance |

Evidence chain:
- Test-2-4/source/layout/afe_lay.py:424 maps the driver supplies to AVDD_CLK/AVSS_CLK; 476 draws the ground resistor; 836 explicitly ties AVSS_CLK to AVSS for LVS.
- Test-2-4/source/layout/offdac_lay.py:48-49 specifies 28.6x92 um and rows [6,4]. The guard rings use AVSS.
- Test-2-4/source/layout/chip_lay.py:678 lists AVSS_CLK/AVSS and DVSS/AVSS as substrate-joined nets.
- Test-2-4/verification/prepare_core_lvs.py applies that convention to the delivered-GDS comparison and reference.
- Test-2-4/verification/eeg_core_reference.cdl:23303 connects the clock VSS to AVSS; 23305 shorts the ground-resistor reference endpoints; 23306 onward contains the ten MOSCAPs.
- Test-2-4/verification/core_with_hints/core_lvs_summary.json reports Match under this convention. It does not certify a finite substrate impedance.
- The historical supply_check.py describes sep:100:150pF as its adopted supply-network simulation, which explains the earlier bench assumptions but does not override current LVS connectivity.

Consequently, the 3.955 V result is a reproducible diagnostic-bench stress warning, NOT a confirmed voltage on current Test-2-4 silicon/GDS. The independent 100 ohm ground return is inconsistent with the current LVS reference. This mismatch takes priority over modifying GDS to cure the earlier bench result.

## Proposed next diagnostic, not executed
Use the current LVS-reference connectivity: common AVSS for the clock driver; official ppolyf_u_1k positive-feed wrapper of the actual dimensions; ten exact-size nonlinear MOSCAPs. Preserve references, logic stimulus and all other circuit components. If the integral-Q model is used for the added caps, explicitly identify it as the same unqualified equivalent-form diagnostic, not official-model certification. An explicit ground-resistor device with equal endpoints has no electrical isolation effect.

This can test the source/LVS-consistent ideal-substrate topology. It cannot determine the physical finite substrate impedance, package return or distributed rail parasitics; those require appropriate extracted models and foundry guidance. No new simulation or GDS edit was performed during reconciliation.

## Evidence
common_interval_comparison.json contains both matched-window datasets and all 58 device pairs. summary.json describes the new run. connectivity.json, exact deck/settings, run.log and wave.csv are preserved. Scripts: ../run_afe_q_stress_convergence.py and ../compare_afe_q_stress_grids.py. The original 3.3 V and 3.6 V screens are retained with this scope correction.
