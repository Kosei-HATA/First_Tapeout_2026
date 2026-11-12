# ADC C2 extraction and mapping probe

## Verified result
Selected the actual Test-2-4 adc_c2 cell (98.83 um square MIM, two placed copies). No original GDS, layout source, or PDK was changed. This is an isolated cell experiment, not full ADC or full-chip PEX.

The existing core LVS database is flat: 88,768 devices and 3,230,452 nets. Reading it peaked at about 4.88 GB RSS. No new full-chip extraction was performed.

Geometry transforms and raw .ext units (0.5 centimicron = 0.005 um) establish:
- C2P TOP -> ADC.I2P; BOT -> O2N. Matched device ADC.C2P.C0.
- C2N TOP -> ADC.I2N; BOT -> O2P. Matched device ADC.C2N.C0.

Mapping is independently checked by the existing LVS cross-reference, using actual core coordinates and l20/l25 metal networks. It agrees with adc_lay.py and eeg_adc.spice. Raw evidence is in mapping_evidence.json and cell_evidence.json. Original cells have stripped labels, so an explicit wrapper was required; no label-based guess was used to assign terminals.

## MIM model, units, multiplicity
PDK stack: gf180mcuD, 5LM, MIM option B, 2 fF class. Magic emits cap_mim_2f0_m4m5_noshield with c_length/c_width=98.82999u. This native simulation model exists in sm141064_mim.spice and is loaded by the official mimcap_typical section. Renaming it to the older cap_mim_2f0ff model is unnecessary.

Ngspice-46 at 25 C, 1 kHz, 1 V AC confirms:
- Schematic dimension 98.83u: 19.531268867 pF analytically.
- Extracted dimension 98.82999u: 19.531264924 pF analytically; AC agrees.
- Native extracted model and older schematic model agree at this nominal condition.
- Deliberately placing two physical instances gives twice the capacitance, so the multiplicity negative control is detected.

Formula: 1.99e-3 F/m2 times area + 2.383e-10 F/m times perimeter. The small dimension-rounding error is about -0.202 ppm. The LVS recognition value, 19.5347378 pF, is simply 2 fF/um2 times area; it is not the simulation value and must not be added to the physical model. The validated device wrapper contains one X device, not an X device plus a duplicate 19.53 pF capacitor.

mim_ac.spice, mim_ac.log, mim_ac.dat reproduce the model check. adc_c2_device_validated.spice is suitable for an isolated device-only check. This does not validate nonlinear behavior across voltage, all corners, or full ADC performance.

## Capacitance-only extraction limitations
Magic 8.3.664, installed gf180mcuD.tech, ngspice() nominal style, 0.001 fF threshold, hierarchy on, merge none. Hierarchical and flat outputs agree to printing precision on the three lumped parasitics:
- TOP-BOT 17.52885 fF
- TOP-SUB 90.27211 fF
- BOT-SUB 13.60770 fF

There is no second dominant physical MIM capacitor in this output. However, detailed fringe overlap and the MIM shield attribution are not qualified. The tech places the MIM type on the metal4 plane, and a large part of its substrate capacitance is associated with the top terminal although the physical bottom plate is beneath it. Old pex.py attempts to relocate such terms with fixed layer names and constants. Its l67 top-plate probe returns no connected net at both tested MIM centers in the current DB, so the old correction cannot be applied without rebuilding and validating its layer/net correspondence. This observation alone does not prove that l67 is geometrically empty.

The isolated cell excludes neighboring wiring, fill, substrate ties, and external routing. SUB remains an explicit boundary, not a fabricated net match. adc_c2_cap_unvalidated.spice is only a debug wrapper; it must not be passed as qualified post-layout performance data. A bottom-plate shielding correction and parasitic/device fringe partition need geometry-aware validation before release.

## Resistance extraction trial
The installed Magic documentation supports extract do resistance and ext2spice extresist on. The small-cell trial completed with threshold 0 mOhm, minres 0.1 mOhm, mindelay 0, simplify off. A bottom-terminal resistor of about 0.193943 Ohm was emitted.

Nominal tech parameters are 90 mOhm/square M1-M4, 40 mOhm/square M5, and 4500 mOhm per intermetal contact. Low/high resistance variants also exist. These values are from the nominal style, not the low-resistance variant.

Qualification FAILED: summed substrate capacitance changes from 103.87981 fF (same extraction with resistor output disabled) to 128.26120 fF with RC output enabled. Substrate node names also change. Raw .res.ext records and both outputs are preserved in rc_trial. Do not assume this is a real increase or silently rescale it; terminal splitting, capacitance redistribution, hierarchical boundaries, and conservation require investigation. No convergence or reliable sheet/contact end-to-end validation has been established. RC output is not approved for performance simulation.

OpenRCX nominal/min/max rule files exist in libs.tech/librelane, but that route needs a matching routed ODB/DEF and LEF technology. It is not a drop-in transistor-level analog GDS-to-RC extractor. The exact final top ODB remains missing.

## Next steps
1. For this same cell, establish a semantic current-deck MIM terminal layer map rather than assuming l67, and independently test shielding with isolated geometry/control structures.
2. Qualify Magic RC on a known straight wire and contact-chain control, then flatten/annotate this small cell with verified port locations and test capacitance conservation at multiple settings.
3. Extract the same C2 window in its actual core surroundings, map all boundary/floating nodes through the saved LVS correspondence, and validate device/fringe partition before ADC post-layout simulation.
4. Extend only after these checks pass; never substitute raw or manually tuned RC for foundry-qualified data.

summary.json includes source hashes, numeric results and readiness flags. All scripts are local to this new subfolder; no full-chip high-memory processing was started beyond reading the already-completed LVS DB.
