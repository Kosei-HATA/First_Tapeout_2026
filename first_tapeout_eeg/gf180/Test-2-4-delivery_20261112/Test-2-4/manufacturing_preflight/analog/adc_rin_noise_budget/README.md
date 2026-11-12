# ADC input-resistor thermal budget pilot: multiplier limitation
Current source: sim_work/gf180/tapeout/adc/eeg_adc.spice XRINP/XRINN, each ppolyf_u_1k L291.28um W1um m16. Real-bias validation reports VCM1.65V; bench uses that CM at zero differentialDC. Original PDK/GDS/source untouched.

Three short small-signal runs, no long transient:
1. Original m16 plus official enable_noisy_r.
2. Explicit16 parallel instances/leg plus same flag, verification-only equivalent topology.
3. Original m16 without flag (negative comparison).

All have R=18736.09116ohm/leg and differential signal gain5.33700771e-5V/V at0.5Hz. Output is a1ohm noiseless transimpedance proxy per leg atVCM; input signal is1V differential AC (±0.5V controlled ideal sources), zeroDC difference.
The differential output density is divided by measured |H(f)|, squared and integrated0.5–100Hz using501 evenly spaced points including exact endpoints, then square-rooted. Independently reported ngspice inoise_spectrum agrees within6e-16relative.
Spectral densities have unitsV/sqrtHz, integrated resultVrms. No amplitude/PSD or single/double differential factor confusion.

Results:
m16 flagged:6.25764139nV/sqrtHz,62.41977685nVrms.
explicit16 flagged:24.92270796nV/sqrtHz,248.6032311nVrms.
analytic differential sqrt(8kTR*99.5Hz):248.6032743nVrms.
m16 unflagged:0.59932410nV/sqrtHz,5.97823910nVrms (incomplete thermal noise, not good performance).

Important new blocker:
m16 electrical conductance is correct but flagged thermal noise is about1/4 of proper amplitude, about1/16 ofbodyPSD. Small remaining deviation from exact1/16 is consistent with retained terminal-resistor noise. The exact translation implementation cause remains to audit; do not assert a proven double-multiplier code defect without expanded noise-source inspection.
Therefore enable_noisy_r alone is insufficient for hierarchical m>1 behavioral-resistor circuits. The previous one-instance thermal validation remains valid; it cannot be generalized to all circuit multiplicities.
Explicit16 is a verification-only representation that passes thermal/electrical identity in this scope, not a PDK modification or foundry-certified substitute. Matching/mismatch correlations, finite-bias flicker and capacitance/noise semantics require separate review before generalizing expansion.

Budget scope:
248.603nVrms is solely input-resistor-pair thermal noise referred to the ADC analog input under an ideal virtual-ground approximation. It excludes OTA, DAC, reference, AFE, source noise, switching/cyclostationary effects, decimator, PEX and flicker. It is not the system noise or a measured full input-chain figure.
Historical5.876768nVrms target is electrode-input total residual, with0.943396mVpk signal and16.5bitSNDR requirements. It cannot be directly compared with ADC-input248.603nVrms. Electrode referral requires actual verified in-band AFE gain/transfer and independent integration of the entire noise ledger. Do not reuse old277/318 gains without reconciliation.
Minimum gain ratio if this component alone used the full target would be42.3, but this is merely unit conversion, not a sufficient design gain or budget approval. No acceptance pass/fail is assigned.

Evidence: summary.json, each case input/gain.csv/noise.csv/run.log, reproducible script ../audit_adc_rin_noise.py.
Next: independently inspect multiplier noise expansion; validate explicit parallel thermal-only flow for all resistor m values actually used; only then reconcile current AFE/ADC gain/noise ledger. System16.5bit remains unqualified.
