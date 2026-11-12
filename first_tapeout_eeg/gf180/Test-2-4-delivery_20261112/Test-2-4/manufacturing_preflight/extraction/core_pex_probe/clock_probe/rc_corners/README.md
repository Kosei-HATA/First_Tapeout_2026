# Actual clock flat PEX: four official RC corners

2026-11-11 UTC. Limited internal-clock extraction. Qualified_for_full_chip = false.

All four corners hrhc/hrlc/lrhc/lrlc pass the same connection/capacitance/MOS checks as nominal. The extraction is from exactly the same flattened small GDS as nominal (SHA256 d99ed4b5d676006ad9995cecf9c7bdb12c5f9e5af9dff75770949fabe0ce8cc7). Neither geometry nor PDK was changed. Complete isolated Magic8.3.697 at commit e400017fdfb221a410cce9e1674910fe70a14e7d performed extraction and SPICE conversion.

Each directory contains the explicit `extract style ngspice(corner)` command, raw .ext style/resistclasses, raw .res.ext, C-only/RC outputs, validation scripts/results, independent Netgen logs and negative controls. Only each corner's rc.spice is intended for the comparison worker. The parent clock_probe/rc.spice is the earlier FAILED hierarchical experiment, not an alternative deck.

## Audits

- All eleven ports retained in the same order: CHOP1 CIA NCIA CIB NCIB CDA NCDA CDB NCDB VDD VSS.
- 486 individual MOS devices preserved through RC extraction. Independent source-CDL comparison merges these to 96 equivalent MOS and matches uniquely with no property errors for every corner.
- Every RC connected component maps to its original C-only net; no disconnection or ambiguous correspondence.
- Collapsed pairwise capacitance matches within calculated decimal-output rounding bounds, not an arbitrary relaxed percentage.
- Explicit MOS W/L/AD/AS/PD/PS remain in original SPICE units; no multiplier, name-forcing or correction was introduced. Simulations use native MOS X wrappers; MOS-only M conversion is solely an independent LVS projection.
- Each corner's missing-resistor and added-1fF controls fail as expected (eight negative outcomes).
- C-corner-only changes leave the entire resistor network identical: hrhc=hrlc for R, lrhc=lrlc for R.
- All emitted resistances are positive.

High-R corners contain 7330 R and 4077 C. Low-R corners contain 3295 R and 2641 C because the official low-R contact values are zero and corresponding subdivisions collapse. Raw resistclasses confirm high-R M1-M4=104 mOhm/square, M5=49 mOhm/square; low-R M1-M4=76, M5=31. Previous same-tech single-via controls independently matched high-R 18*0.104+15=16.872 Ohm and low-R 18*0.076+0=1.368 Ohm within 0.0005 Ohm. The zero-contact low corner is a deck model bound, not a claim of zero physical via resistance or foundry qualification. Diffusion/poly/contact-array and distributed-mesh accuracy are not independently calibrated by these checks.

## Handoff hashes (SHA256 of rc.spice)

- hrhc: 392f8d47c92b55fa3b62bbb862f3985de55dc97113b480c05fdf37d01294e0f2
- hrlc: c4fff44712f33dde1ee4101056dcbfa9f997f0aff0e60373644121018cd1383e
- lrhc: 9c8d31eca57ce43ab232f54997eefa2987d9581f3c96c12ee42d8ce48db40cfa
- lrlc: 6d3cd1ec3135371ff57276a300955990b6aa0983f263fb70ec5fe83edc1d632f

summary.json records hashes, active styles, counts, positive checks and elapsed times (about 2.4 seconds per generation plus audit). negative_and_resistance_checks.json records negative tests and resistance invariance. manifest.json hashes evidence files, excluding this later README. Reproduction scripts in core_pex_probe: extract_clock_corners.py and negative_clock_corners.py. Original nominal results remain unchanged.

## Scope

These are internal clock-block RC corners, not device-PVT corners. The functional worker separately applies FF/3.6V/-20C to compare against the previous minimum nominal-RC margin. This report does not pre-judge those simulation results. External 24 TG loads, their analog operating trajectories, upper-level output routes, neighboring coupling, power-distribution mesh, package and manufacturing limits remain outside this isolated extraction; the loaded testbench must explicitly retain the independent actual load circuit as already agreed. Passing these audits does not certify absolute parasitic accuracy, all-chip timing or manufacturability.
