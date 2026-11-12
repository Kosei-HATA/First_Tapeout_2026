# Via and branch resistance controls

2026-11-11. Limited test, no full-chip qualification.

The active nominal extraction style is ngspice(), confirmed in raw via1.ext. The PDK tech nominal section (variants ()) specifies M1-M4 90 milliohm/square and via1-via4 4500 milliohm per contact. Its high-resistance variants (hrhc/hrlc) specify 104 milliohm/square and 15000 milliohm/contact. Low-resistance variants (lrhc/lrlc) specify 76 milliohm/square and zero contact resistance. These are existing official-deck corner values, not newly invented replacements. An early inspection of only the low-resistance section must not be interpreted as all contact resistance missing.

Single via1 control has 18 squares total route length between port coordinates, with one via contact:
- Nominal: analytic 18*0.09+4.5 = 6.120 ohm; extracted 6.1205 ohm.
- hrhc and hrlc: analytic 18*0.104+15 = 16.872 ohm; extracted 16.8725 ohm.
- lrhc and lrlc: analytic 18*0.076+0 = 1.368 ohm; extracted 1.3685 ohm.
- Missing-via negative: A and B retained, no conductive path. This detects the deliberate open.

Three-terminal M1 branch retains A/B/C and yields a connected three-resistor star. A-B=8.821 ohm vs straight-arm analytic 8.82 ohm. A-C=8.731 ohm; simple centerline estimate 8.775 ohm differs by ~0.5 percent because of junction treatment. This is not an independently calibrated junction/mesh accuracy result. Results are from solving the resistor network, not summing every resistor indiscriminately.

Files: results.json, corner_results.json; subfolders preserve GDS, Tcl, logs, raw ext/res.ext and both SPICE outputs. Reproduction scripts in core_pex_probe: test_resistance_controls.py, test_resistance_corners.py. No PDK edits. No whole-chip jobs.

Limits and next steps: This checks one contact and nominal branch topology, not contact arrays, diffusion/poly contact extraction, multi-via current distribution, frequency accuracy, or mesh convergence. Low-resistance corner's zero contact value follows the existing deck; it is a modeled bound, not evidence that a physical contact has no resistance. The deck references 180MCU_YI-141-EP059-01_10.pdf; its foundry acceptance and process applicability have not been independently checked here. Before applying to an actual clock branch, isolate a small GDS hierarchy and prove port/net/device correspondence from the independent core LVS DB, preserve all loads, select explicit RC corner, and compare nominal/PVT timing. Do not claim clock-tree sign-off from this harness.
