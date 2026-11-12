# Physical resistor-noise coverage failure
Eight small-signal runs completed, PDK unchanged. Zero DC bias; .noise 0.5–100Hz. AC low-frequency resistance establishes actual R; comparison uses4kT*R at specified temperature. No flicker qualification.
At27C actual ppolyf_u_1k R=299777.4585ohm. Measured output density1.6951445nV/sqrtHz versus4kTR expected70.4920755nV/sqrtHz. PSD ratio0.00057827294 (about99.942% missing).
Two series/parallel instances show the same fractional deficit. Double-length body keeps approximately the same noise amplitude while R doubles, confirming dominant body contribution is absent.85C test also fails the full-resistor4kTR expectation.
Positive control ideal300kohm gives ratio0.999999652 (minor physical-constant precision difference).
Negative controls ideal B resistor and R noisy=0 both give0.
Expanded model evidence in ../mismatch_seed_audit shows the body represented by behavioral B current source; terminals remain R. Results match terminal-only noise, not complete resistor thermal noise.
This is a tool/model noise-coverage blocker, not evidence that fabricated resistor noise is low. Deterministic transient, static INL, existing electrical function tests remain separate; no claim that this invalidates their measured quantities.
Do not use current .noise results for physical ADC16.5bit qualification. Next work should inspect official ngspice/model translation support, validate an explicitly documented equivalent resistor-noise treatment against4kTR, then rerun the noise ledger. Do not silently modify PDK or equate an uncalibrated behavioral noise source with validated fabrication noise. Flicker at finiteDC also remains unqualified.
Initial collector expected2D AC data but ngspice produced1row. Parsed with atleast_2d without rerunning; script corrected for future independent replay. Full raw evidence preserved.
