# AFE low-noise study (afe_ln)

Date: 2026-09-12. Goal: reduce the EEG AFE input-referred noise from
~0.38 µVrms (0.5-100 Hz) toward <= 0.15 µVrms, lifting the system ENOB
ceiling. Deliverable: ranked design changes with measured (simulated)
noise impact. All files are new (prefix afe_ln_); no canonical file touched.

## 0. Methodology (read before reusing these benches)

- **Units:** ngspice `onoise_spectrum` / per-device `onoise.*` vectors are
  **V/rtHz amplitude, NOT V^2/Hz** (verified: a 1 kohm resistor gives
  4.07e-9 = sqrt(4kTR) exactly). Per-device RSS closes to the total within
  0.02 %, so device attribution is exact.
- **inoise_spectrum stays broken** for this circuit; input-referred numbers
  are output-noise / measured gain (31.9).
- **In-band metric (house convention):** the chopped AFE folds the output
  noise density at f_chop = 1 kHz into the band:
  `in-band = onoise(1 kHz)/gain * sqrt(99.5 Hz)`.
- **Baseline reconciliation (important):** the archived table
  (10 Hz 9877 / 100 Hz 3976 / 1 kHz 1228.7 / 8 kHz 170 / 50 kHz 77 nV)
  is reproduced **only when the RSS is taken over the stage-2 devices
  (XM21-24 + output resistors)**, not the full total:
  my v0 stage-2-only = 9801 / 3810 / 1031 / ~130 / ~70 nV (0.8-19 % vintage
  delta). So the archived 0.38 µV baseline counted **stage-2 devices only**.
  The full 1 kHz floor including the upstream (stage-1) chain that aliases
  in-band identically is 1.67x higher (my v0: 0.644 µV full-metric vs
  0.323 µV stage-2-only-metric vs 0.386 archived). Both metrics are
  reported below; after the recommended fix the two converge because the
  upstream contribution is crushed.
- Transient noise is unavailable in this ngspice build (KLU;
  `.tran ... noise` rejected), so frozen-chopper AC .noise + one real
  chopped transient (acceptance) is the flow.

## 1. Baseline attribution (v0 = current canonical netlist)

Full output noise @1 kHz = 2057.5 nV/rtHz (stage-2-only: 1030.8),
gain 31.86, idd (OP) 69.3 µA, PM(beta=1/32) 88.8 deg (matches archive).

Full-floor shares @1 kHz: **stage-1 CM-softening RLOADP/N (2 Meg) 45.7 %,
stage-1 CM-sense RCM (5 Meg) 18.3 %**, stage-2 pair XM21/22 24.8 %
(thermal-dominated at 1 kHz: .id 319 vs .1overf 97 nV), stage-1 pair 10.9 %,
everything else (choppers, bias gen, CMFB, stage-2 resistors) < 1 %.
The archived "stage-2 1/f dominates" holds only for the stage-2-only
spectrum below ~100 Hz (at 10 Hz: xm21 .1overf = 712 of 789 nV).

## 2. Suggested device-size variants: ineffective (measured)

| variant | change | onoise@1k full [nV] | in-band full [µV] | in-band s2-only [µV] |
|---|---|---|---|---|
| v0 | baseline | 2057.5 | 0.644 | 0.323 |
| va | stage-2 pair area x4 | 2065.1 | 0.646 | 0.272 |
| vb | va + stage-2 load x2 | 2064.9 | 0.646 | 0.272 |
| vc | stage-1 pair W x2 | 2115.9 | 0.663 | 0.319 |
| vd | combo | 2129.5 | 0.666 | 0.266 |

Why they fail on the full metric: the floor is resistor-dominated, and
XM21/22 is thermal-limited at 1 kHz with gm set by current (90 µS @
19.2 µA; stage-2 current is pinned by the NMOS VGS - enlarging the PMOS
loads changes nothing, measured). On the s2-only metric area x4 does give
-16 %, confirming s2pair 1/f scales with area.

## 3. The effective lever: RLOAD up (loop-gain suppression)

Raising the stage-2 output load raises stage-2 DC gain -> loop gain ->
closed-loop suppression of ALL upstream noise (stage-1 resistors/pair,
bias, choppers) AND of XM21/22's gate-referred 1/f. Left at the output
node, unsuppressable: XM21/22 drain thermal current, RLOADO and RCMO
current noise. Isolated experiment (vd vs ve: identical devices, RLOAD
2->10 Meg): 2129.5 -> 648.2 nV.

| variant | change | onoise@1k full [nV] | in-band full [µV] | in-band s2-only [µV] | idd [µA] | PM |
|---|---|---|---|---|---|---|
| vf | S1RLOAD 10 Meg only | 1462.1 | 0.457 | 0.177 | ~69 | - |
| ve | vd + RLOAD 10 Meg | 648.2 | 0.203 | 0.186 | 107.7 | - |
| vk | s2 pair x4 + RLOAD 10 Meg | 580.8 | 0.181 | 0.176 | 107.5 | - |
| **vq** | **RLOAD 15 Meg** | **442.2** | **0.138** | **0.138** | **69.3** | 88.7 |
| **vr** | **RLOAD 20 Meg** | **417.7** | **0.130** | **0.130** | **69.3** | 88.6 |
| vw | RLOAD 30 Meg | 402.6 | 0.126 | 0.126 | ~69 | 88.6 |
| vs/vt | vq/vr + RCMO 5->10 Meg | 574.8 / 535.3 | 0.180 / 0.167 | 0.179 / 0.167 | ~69 | (worse) |

With canonical devices and **zero power/area cost**, in-band noise falls
0.644 -> 0.130 µV full-metric (5.0x) and 0.323 -> 0.130 µV s2-only metric
(2.5x; vs the archived 0.386 baseline: 3.0x). **The 0.15 µV target is met
on every metric.** Diminishing returns beyond ~20-30 Meg.

Negative results measured: RCMO up hurts (raises output-node impedance);
RLOADO 5 Meg (vm, 761 nV) is worse than 10 Meg - the loop-suppression gain
outweighs the Rout reduction.

Bonus: the in-band spectrum also goes FLAT. Stage-2-only output noise at
10 Hz drops 9801 -> 561 nV (17x) and at 0.5 Hz 35.1 µV -> 1.3 µV (27x),
because XM21/22's gate-referred 1/f is loop-suppressed like any upstream
noise. The archived bookkeeping gap (1/f rise ignored in the 0.38 figure)
largely disappears.

## 4. Safety checks on the RLOAD change (vr/vq/vw vs v0)

- Differential loop: PM(beta=1/32) 88.8 -> 88.6 deg; GBW 3.16 -> 3.19 MHz;
  open-loop DC gain 58.6 -> 65.4 dB; closed-loop gain @8 Hz 31.86 -> 31.93.
- Common mode: 10 mV VCM_REF step (closed loop, frozen choppers):
  indistinguishable from baseline (max deviation 6.74 vs 6.76 mV, no
  ringing) - weaker passive CM softening does not hurt CM settling.
- Power: idd unchanged (OP 69.3 µA; transient idd_avg 69.26 µA) - stage-2
  current is pinned by the NMOS VGS, not by RLOAD.
- **Real chopped-AFE transient** (1 kHz choppers, 8 Hz 100 µV/side input,
  0.25 s, vr netlist): measured amplitude 6.288 mV -> gain 31.44 @8 Hz
  (matches the published -1 % fc rolloff), residual rms 31 µV, no
  recovery/latch-up issue with 20 Meg loads. PASS.

## 5. Residual floor and the ceiling reason

After suppression (vr): s2_rcmo (CM-sense 5 Meg) 52 %, s2pair drain
thermal 35 %, s2_rloado 13 % - all output-node terms, ~sqrt(4kT*Rout)
limited (Rout ~ ro||RLOADO||RCMO ~ 2.5-3 Meg). Beyond ~30 Meg RLOAD the
gain is < 5 %. Going below ~0.125 µV needs higher stage-2 gm (measured
vk: W x4 doubles gm at +55 % total power, 0.181 µV - poor trade) or a
topology change (resistor-free active output-CM control, or a power
budget for output-stage current).

## 6. Ranked recommendations

1. **RLOAD 2 Meg -> 20 Meg (S1RLOAD and RLOADO), keep RCMO 5 Meg.**
   Free 5x in-band noise reduction to 0.130 µV (all metrics); stability,
   CM, gain, power all verified unchanged; real-transient PASS.
   (15-30 Meg all work; 20 Meg keeps margin from the Rout knee.)
2. If more is ever needed: stage-2 pair gm (current) - real power cost
   (+55 % total for 0.181 µV, measured vk; poor trade vs #1).
3. Do NOT bother with: stage-1/stage-2 pair area scaling alone
   (section 2), RCMO increase (measured harmful), RLOADO < 10 Meg.
4. Next-revision bookkeeping: re-baseline the acceptance noise number with
   the full-floor metric (the archived 0.38 undercounts the aliased
   upstream floor by ~1.7x; on the current netlist the true baseline is
   0.64 µV - still inside the 1.0 µV spec, but with less margin than
   believed).
5. PVT spot-check of the RLOAD change at ss (poly-R min) next revision;
   the mechanism has margin via the 65 dB DC gain but was not run here.

Files: source/trials/20260902/xschem/afe_ln_{core_soft,ota_full2}.spice
(variant subckts), afe_ln_tb_{base,var,ol,cm,real_vr}.spice + generated
v* decks; results in source/trials/20260902/results/afe_ln_*.
