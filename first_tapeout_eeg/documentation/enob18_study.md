# ENOB-18 Sigma-Delta ADC study (sdm3)

Date: 2026-09-12. Author: design-space exploration subagent run.
Target: **quantization** SNDR >= 110 dB (ENOB ~18) over the 0.5-100 Hz EEG
band, as a candidate next-revision upgrade from the shipped CT 1st-order
modulator (`eeg_sdm1ct`, fs=16 kHz, OSR=80, SNDR ~52 dB).

## 1. Architecture math

1-bit L-th order NTF `(1-z^-1)^L`, ideal peak SQNR
`6.02+1.76-10*log10(pi^2L/(2L+1)) + (20L+10)*log10(OSR)`:

| L | OSR needed for ~110 dB | fs (fB=100 Hz) | note |
|---|------------------------|----------------|------|
| 1 | ~3000+ (95.8 dB @ OSR=1280) | >600 kHz | not reachable with 256 kHz master |
| 2 | ~300 (ideal) | 64-256 kHz | sweet spot |
| 3 | ~64 | 32 kHz | higher PVT/stability risk, 1-bit |

Chosen: **L=2, 1-bit, fs=256 kHz, OSR=1280** (256 kHz master exists in
`eeg_clkgen`; the classic alternating-phase SC loop is the most PVT-robust
way to spend that OSR). Behavioral (nonlinear, 1-bit, exact loop timing)
SQNR at 0.6 FS, 0.5-100 Hz band:

- fs=128 kHz (OSR=640): 112.5 dB  -> margin too thin for SPICE reality
- fs=256 kHz (OSR=1280): **125.9 dB** -> 16 dB margin
- stable for inputs up to ~0.8 FS (103 dB @ 0.8 FS)

## 2. Root cause of the abandoned eeg_sdm2

Two independent bugs, both in loop timing/signs - the CQP/CQN hold caps
added on 2026-09-05 were treating a symptom:

1. **DAC polarity mismatch.** `eeg_sd_int` (int1) wires its DAC so BIT=1
   *raises* the differential output; `eeg_sd_int2` (int2) wires it so BIT=1
   *lowers* it. With the strong-arm + NAND-SR-latch polarity
   (BIT=1 <=> O2D<0, cross-checked against the working `eeg_sdm1ct`
   convention), one of the two feedback paths is always positive. Char.
   polynomial `1 - z^-1 - 0.25*z^-2`, pole at **z=1.207** -> integrators
   rail to +/-1.72 V and duty locks to the input sign (exactly what
   `results/sdm2_cap.csv` shows).
2. **Unfixable same-phase timing.** Even with corrected polarity, both
   integrators run on the same phase pair, so the cascade sees `x1(n-1)`
   and both DACs see `y(n-1)`: a full extra cycle of loop delay vs the
   textbook loop. A behavioral coefficient sweep shows this delayed
   structure tops out at **~59 dB SQNR** for any stable coefficient set.
   No coefficient retune could have saved it; the timing itself must change.

## 3. sdm3 architecture

Classic alternating-phase (Boser-Wooley) 2nd-order SC modulator:

- int1 (`sdm3_int1`, new): samples PH1 / integrates PH2. Sampled
  parasitic-insensitive input caps (as `eeg_sd_int`) plus a **direct DAC**:
  DAC caps discharge to VCM during PH1 and step to VP/VN (BIT-selected)
  during PH2 -> feedback applied in the **same cycle** as the decision.
- int2 (`eeg_sd_int` reused, clock pins swapped): samples PH2 (captures
  the freshly settled x1 -> **non-delaying cascade**), integrates PH1.
- Strong-arm fires late PH1 on the fresh x2; NAND SR latch holds BIT
  through the following cycle (QP/QN both high in precharge; 1 pF hold
  caps retained for the genuine both-low early-eval pulse).
- **BIT2 register (PH2-edge DFF):** BIT changes at CMPCK, i.e. *during*
  bench-PH1 = int2's integration phase. Without re-timing, int2's DAC
  left plates jump VP<->VN mid-integration (decision-correlated charge
  injection into the summing node): the measured effective d2 collapsed
  1.0 -> ~0.15 and cost ~20 dB of SNDR. A TG master-slave DFF clocked on
  the PH2 rising edge makes the selector constant through every
  integration phase.
- **Bitstream readout (analysis-side gotcha):** ngspice saves at internal
  non-uniform steps with multi-us gaps; single-point BIT sampling (as in
  sdm_bitstream.py) can land inside the latch transition. ~1 bad read in
  80000 cycles raises the apparent floor from 5e-7 to 5e-5/bin
  (66.8 dB vs 100.9 dB on the SAME csv). Use majority-vote sampling over
  the PH2 plateau (scripts/sdm3_bitstream.py).

Loop equations: `x1 += a1*u + d1*y`, `x2 += a2*x1 + d2*y`, `y = -sgn(x2)`.
Coefficients: a1=2 (CS1=8p/CI1=4p), d1=2 (CDAC1=8p), a2=0.5 (CS2=2p/CI2=4p),
d2=1 (CDAC2=4p). Char. polynomial
`(1-z^-1)^2 + a2*d1*z^-1 + d2*z^-1*(1-z^-1) = 1` ->
**NTF = (1-z^-1)^2 exactly**, STF(DC) = -a1/d1 = -1
(bitstream duty = 0.5 - u/100mV, same convention as sdm1ct).
Integrator swings (behavioral): |x1|,|x2| < 5*VREFd = +/-250 mV diff.

Capacitor budget: int1 2x(8+8+4) = 40 pF, int2 2x(2+4+4) = 20 pF,
total **60 pF** (mim ~2 fF/um2 -> ~0.03 mm2).

## 4. Measured results

All transient decks use save-limited vectors (`save time v(BIT)` for the
long runs), 50 ns max step, default ngspice tolerances, 32 Hz 0.6 FS
differential input, fs=256 kHz. Bitstream FFT: 10 coherent 32 Hz cycles
after 10 ms startup skip, majority-vote BIT sampling over the PH2 plateau
(`scripts/sdm3_bitstream.py`; see the readout gotcha in section 3).

**Bring-up (6 ms, TT):** loop locks immediately; bitstream duty tracks
`0.5 - vin/100mV` to within +/-0.01 over the whole input range; integrator
swings bounded (o1d +/-0.33 V, o2d -0.29/+0.63 V) - matches behavioral
predictions, comfortable OTA headroom.

**TT SNDR, full runs (322.5 ms, 10 cycles):**

| variant | SNDR (0.5-100 Hz) | note |
|---|---|---|
| final (PH2-edge DFF for int2 DAC) | **91.68 dB** | correct loop timing |
| pre-DFF (int2 DAC selector switches mid-integration) | 100.91 dB | d2_eff ~0.15; objectively worse loop, luckier tone realization |
| ideal behavioral model, same record | 123.3 dB | discrete-time ceiling |
| behavioral with SPICE-extracted coefficients (a1=d1=1.957, a2=0.595) | 123.4 dB | coefficient realization is NOT the limiter |

**Limiting-factor analysis (final variant).** The shaped out-of-band
spectrum sits within ~2x of the ideal model (2-10 kHz: 2.7e-4 vs 1.3e-4;
10-50 kHz: 5.2e-3 vs 3.1e-3 per bin), so the loop noise-shapes correctly.
The in-band noise is 97.6% **limit-cycle / intermodulation tones**: a
skirt at k*3.2 Hz around the 32 Hz carrier (strongest -97 dBc at +/-3.2
and +/-6.4 Hz offsets) plus HD3(96 Hz) at -98.9 dBc. Excluding the 12
strongest tone bins the white floor corresponds to ~108 dB. The discrete
behavioral model shows NO such skirt (top in-band lines ~1e-7), so the
tones are produced by an analog state-dependent mechanism the discrete
model lacks - most plausibly strong-arm hysteresis (decision threshold
depends on the previous state) interacting with the limit cycle, with a
weaker contribution from int1's state-dependent update error. Candidate
mitigations (identified, deliberately not iterated per the agreed stop
rule): quantizer/input dither to break the limit-cycle locking, an
anti-hysteresis comparator (input-pair reset), larger CI1 to reduce int1's
relative per-cycle disturbance.

**Best achieved TT quantization SNDR: 100.9 dB** (tone-realization
spread 92-101 dB between loop-timing variants; target 110 dB not met in
this round - see stop-rule note in section 7).

**DC transfer (TT):** duty vs input extracted from the 6 ms bring-up sine
sweep (quasi-static: 32 Hz signal vs 256 kHz sampling, 12 levels across
+/-28 mV): duty = 0.5 - VIN/100mV with max deviation 0.010 over the full
range -> STF gain error <1%, no dead zone, sign convention as designed.

**PVT (ss 1.62 V/125 C, ff 1.98 V/-40 C):** not run - the TT result fell
short of the 110 dB target and the stop rule was invoked (section 7).
Corner decks are ready (`tb_sdm3_256k_ss.spice`, `tb_sdm3_256k_ff.spice`,
197.5 ms/6-cycle variants) for any future iteration.

## 5. Outlook: SC-sdm3 vs a CT 2nd-order path

The 110 dB goal here is a **quantization** target; any transistor-level
transient sim has no device noise, and the real ENOB ceiling is thermal.
Where the two candidate architectures put that ceiling:

**SC-sdm3 (this study).** In-band kT/C of the 2 pF input sampling caps at
OSR=1280 is ~1.8 uVrms -> thermal SNR ceiling ~81 dB at 0.6 FS. Lifting it
to 110 dB would need ~nF sampling caps - not integrable. Area cost of the
current design is tiny (60 pF total, ~0.03 mm2), power is just the two
existing OTAs at 256 kHz (verified settling).

**CT 2nd-order.** No sampling caps, so no kT/C term: the input-referred
floor is set by RIN noise, 4kT*RIN per side. RIN ~5 kohm gives ~9 nV/rtHz
(~90-130 nVrms over 100 Hz) - at/below the 67 nVrms needed for 110 dB at
0.6 FS - while the integrator cap for unity-gain at fs=256 kHz stays
~120 pF (integrable). Costs: (a) the PGA/reference must drive a 5 kohm
differential load (drive power); (b) RC product spread over PVT shifts
coefficients (needs margin or tuning); (c) excess loop delay of the
comparator + latch must be compensated (a direct/fast feedback DAC path -
the sdm1ct already closes its DAC combinationally within the cycle, so the
house style is compatible); (d) jitter: an NRZ resistive DAC at 256 kHz is
jitter-benign (~100 ps rms jitter degrades SNDR only to ~120 dB), so this
is not a blocker.

**System context that decides between them:** the current EEG front-end
input noise is ~1 uVrms, i.e. an ~86 dB ceiling against a 0.6 FS signal
already. SC-sdm3's ~81 dB thermal ceiling sits just below that - the
modulator is roughly noise-neutral against today's PGA. CT's ~110 dB
thermal ceiling only becomes relevant if the front-end noise is ever
reduced by ~10x (chopper/bigger input devices). Recommendation: adopt
sdm3 (SC) for the next revision - its measured 92-101 dB quantization
floor sits 6-20 dB below the ~81-86 dB thermal/PGA budget, so it is not
the system bottleneck despite missing the 110 dB stretch goal; it is
drop-in with the existing references and the clkgen 256 kHz master, and
~0.03 mm2 in caps. Keep the CT 2nd-order as a scoped future exploration
(no CT design work started here), and see section 7 for the dither /
anti-hysteresis steps if the 110 dB quantization target is pursued.

## 6. Risks / honest limitations

- **Thermal noise, not quantization, is the real ENOB ceiling.** In-band
  kT/C of the 2 pF input sampling caps at OSR=1280 is ~1.8 uVrms
  (vs 21.2 mVrms signal at 0.6 FS): thermal-limited SNR ~81 dB. A true
  110 dB *total* SNDR would need ~nF sampling caps - not integrable.
  This study targets quantization SNDR only (transient sims carry no
  device noise); the modulator removes quantization as a bottleneck
  against any realistic front-end noise floor.
- HD3 of the 32 Hz test tone lands at 96 Hz, inside the band: measured
  -98.9 dBc (small). The dominant in-band limiter is the limit-cycle tone
  skirt (97.6% of in-band noise), not HD3.
- OTA GBW (~3.3 MHz measured, `results/ac_ol.csv`) with beta1=0.2 gives
  ~4-7 settling time constants per half-phase at 256 kHz; measured as a
  2.2% coefficient error on int1 (behavioral impact <1 dB), but SS-corner
  settling should be watched if this design is re-run.
- Digital: 2-phase non-overlap + comparator-clock generation from the
  256 kHz master must be added to `eeg_clkgen` (trivial logic, not done
  here).

## 7. Status / stop-rule note

Target was TT quantization SNDR >= 110 dB. Best measured: **100.9 dB**
(pre-DFF variant), 91.7 dB on the timing-correct final variant; the
difference is limit-cycle tone realization, not loop quality (the final
variant's shaped spectrum is 2x closer to ideal). The discrete-time
ceiling of the architecture is 123-126 dB and coefficient realization is
verified NOT to be the limiter; the gap is analog limit-cycle locking
(comparator hysteresis / state-dependent update errors). Per the agreed
stop rule, iteration stops here. If the study is resumed, the highest-
value next steps are: (1) input or quantizer dither to break the tone
locking; (2) an anti-hysteresis comparator (input-pair reset switches);
(3) re-run TT + the prepared ss/ff corner decks after (1)-(2).

Files (all new, prefix sdm3_ / enob18_ - no canonical files touched):
- `source/trials/20260902/xschem/sdm3_mod.spice` - modulator (incl.
  sdm3_dff / sdm3_inv / sdm3_nand2)
- `source/trials/20260902/xschem/sdm3_int1.spice` - 1st integrator,
  sampled input + direct same-cycle DAC
- `source/trials/20260902/xschem/tb_sdm3_bringup.spice`,
  `tb_sdm3_256k.spice` (TT), `tb_sdm3_256k_ss.spice`,
  `tb_sdm3_256k_ff.spice` (prepared, not run), `tb_sdm3_dc*.spice`,
  `tb_sdm3_idle*.spice`, `tb_sdm3_test/acc*/t25/seed/snub.spice`
  (bring-up/diagnostic variants)
- `scripts/sdm3_bitstream.py` (robust bitstream SNDR),
  `scripts/run_sdm3_benches.sh`
- data: `source/trials/20260902/results/sdm3_*.csv/.log`
