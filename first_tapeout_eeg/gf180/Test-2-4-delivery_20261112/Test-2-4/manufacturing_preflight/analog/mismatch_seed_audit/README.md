# Fixed-seed / hierarchy sampling audit
2026-11-11. Ten expansion-only ngspice runs, about1second each. No long transient or Monte Carlo performance test.

- mismatch off: all MOS delvto=0.
- local mismatch on: all659 MOS have distinct delvto values; seed1 repeats identical delvto/mulu0 vectors; seed2 differs.
- Original res_typical section sets statistical coefficients to0. sw_stat_global=1 alone does not enable resistor sampling.
- Explicit res_statistical section: same seed repeat listings identical; different seed changes parameters.
- All124 ppolyf_u_1k terminal models share identical rsh within each seed (78.7888157556 atseed1,79.7353371271 atseed2).
- All31 XRPA body expressions are identical after instance-name normalization. Thus this tested model/engine exhibits common resistor variation, not unit-specific local mismatch.
- Official device table identifies Local Statistical=N for ppolyf_u_1k:
https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_1_4_4.html

summary.json contains machine-readable checks; per-case expanded.log is full evidence. all_parameters.json and global_statistical_parameters.json preserve extracted records. Decks use immutable copied models.

Noise caution:
The body resistor expands into b.INSTANCE.brb, a behavioral current source; terminal resistors remain R devices. Therefore source-model noise=1/kf does not by itself prove body thermal/flicker noise is included by this ngspice compatibility translation. Next priority is a tiny .noise sanity bench of one actual resistor versus 4kTR (plus terminal contributions), with density units and bias checked. Estimate1–3min, oneprocess, no full-loop run. If body noise is omitted, do not declare current benches physical noise-qualified; report a tool/model coverage gap before any documented equivalent-noise correction.
Large-MOS-array par/nf/m statistical area scaling and same chip parameter vector across code changes also remain to audit.
