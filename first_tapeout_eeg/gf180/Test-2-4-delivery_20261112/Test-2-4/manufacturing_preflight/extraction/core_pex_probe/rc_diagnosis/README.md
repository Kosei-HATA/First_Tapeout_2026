# RC capacitance inflation: controlled diagnosis

## Conclusion
The discrepancy is reproducible in a simple two-metal structure without MIM or hierarchy. It is therefore not explained by the main MIM model, its units, or only the ADC hierarchy. In the current Magic 8.3.664 / installed GF180 tech flow, enabling resistor-network output preserves the original coupling capacitor and adds coupling-derived rnode capacitance to substrate. This output is NOT qualified for coupled post-layout RC simulation.

This is an output-path inconsistency demonstrated by controlled inputs; exact source-code defect versus a documented unsupported combination has not been established. No PDK or tool source was modified and no numerical subtraction was used to force a result.

## Original 24.38139 fF increase, traced completely
Original C-only substrate total: 103.87981 fF. RC total: 128.26120 fF. Increase: 24.38139 fF.
- Child MIM bottom network rnodes: 0.731272 + 5.11888 = 5.850152 fF. The unchanged TOP-BOT coupling is 5.85015 fF.
- Parent TOP rnode: 8.55896 fF.
- Parent BOT rnode: 9.97228 fF.
- Total added rnode values: 24.381392 fF, matching the observed delta to printed precision.

The parent raw .ext coupling records sum to 18.5312332 fF: 11.6787084 fF remains between final TOP/BOT nets, while 6.8525248 fF joins names that become the SAME final net after hierarchy aliases. Those same-net terms disappear from ordinary final coupling output but still enter the RC rnode contribution. diagnosis.json preserves all raw records and their final aliases, inferred directly from the existing hierarchy SPICE instance pin map.

Physical association: TOP is the MIM top plate plus its access wiring (Magic mimcap type shares the metal4 extraction plane); BOT is the metal4 bottom plate and its access wire. The substrate anchor is the implicit p-substrate node. The large main MIM remains one 98.82999u square X device in both outputs and is not the source of the delta. All old and new logs remain available.

## Controls using exactly the same tech and settings
Ports were explicitly annotated at known conductor positions in derived test copies. Unlabelled standalone objects do not necessarily generate resistance networks, so an empty .res.ext is not evidence of a successful RC comparison.

- Single M1 wire, 100um x 1um, ports at x=1 and 99um: R=8.8205 Ohm versus 0.09 Ohm/square x 98 squares = 8.82 Ohm. Substrate capacitance remains 10.8955 fF. This validates the simple resistance scale, not an entire RC deck.
- Two aligned wires on M1/M2, no via and no MIM: coupling 5.9027 fF remains in output. Each resistively extracted wire acquires an additional 5.9027 fF to substrate, so substrate total increases by 11.8054 fF. Each wire has R=8.8205 Ohm. This is the decisive non-MIM reproduction.
- Standalone MIM with TOP/BOT ports: coupling 5.85015 fF remains; substrate total increases by exactly 5.85015 fF. Only the bottom terminal is split by resistance.
- Flattened ADC C2: coupling 17.5289 fF remains; substrate total increases by 17.52893 fF (printing precision). Removing hierarchy does not resolve the issue.

The flattened and hierarchical C-only ADC extraction totals differ somewhat because hierarchy-dependent parasitic accounting exists. This is a separate unqualified effect; it does not explain the same-run C-only versus RC comparisons above.

## Options tested, not accepted as fixes
- Raising extresist threshold to 100000 mOhm suppresses the MIM resistance network and removes the discrepancy. It also removes the intended distributed R, so this is not a valid RC fix.
- extract no coupling removes the additional discrepancy while retaining the resistor, but changes the capacitance extraction itself: MIM TOP-substrate rises from 85.7325 to 142.89 fF, and explicit coupling is absent. This cannot be substituted as a validated coupled model.
- Earlier hierarchy-off output on these controls did not emit the detailed resistor network. A zero discrepancy without R is not a pass.
- Tests use threshold 0, minres 0.1 mOhm, mindelay 0, simplify off unless explicitly identified otherwise; same-run C-only/RC outputs share the same raw .ext and substrate names. Threshold or grounding mismatches therefore do not account for the decisive comparisons.

## Status and minimum next step
Stop using this RC output for performance prediction. Retain device-only and C-only experiments with their earlier qualification limits. A supported extractor path or independently reviewed tool fix must pass these wire/MIM controls, capacitance conservation, terminal distribution and convergence checks before use. Do not simply subtract the measured ground excess: hierarchical alias terms and physical coupling location require correct network reconstruction. No full-chip RC has been run or injected into any simulation.

Reproduce with diagnose_rc.py, diagnose_hier.py, diagnose_ports.py, diagnose_coupling.py, and summarize_rc_diagnosis.py in the parent core_pex_probe folder. diagnostic scripts operate only in this derived subtree. diagnosis.json is the numeric evidence summary.
