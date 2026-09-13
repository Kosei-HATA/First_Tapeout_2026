# rev2 macro integration: LN-AFE (RLOAD 20Meg) + sdm3 ADC

Date: 2026-09-12. Scope: rev2 macro netlist + E2E simulation. Layout and
caravel integration are out of scope (layout agent picks up from here).

## Netlist files (all new, prefix rev2_; no canonical files modified)

- `source/trials/20260902/xschem/rev2_afe_chopped_full2.spice`
  - `rev2_afe_core_soft`: verbatim copy of `eeg_fd_ota_core_soft`, default
    RLOAD 2Meg -> **20Meg** (still parameter-overridable).
  - `rev2_afe_chopped_full2`: canonical `eeg_fd_ota_chopped_full2` (nodsl,
    layout-verified) with RLOAD default 2Meg -> **20Meg** for both stages
    (S1RLOAD + RLOADO). Shares the canonical `eeg_cmfb_amp_dl2` and
    `eeg_cmos_chopper_lowq` cells.
- `source/trials/20260902/xschem/rev2_afe_pga.spice` — canonical
  `eeg_afe_pga` structure (input caps, x8/16/32/64 feedback bank,
  pseudo-R bias, RST) with the rev2 OTA.
- `source/trials/20260902/xschem/rev2_top.spice` — mirrors `eeg_afe_top`
  pin style. `CLK16/NCLK16` replaced by the sdm3 clock set
  `PH1 NPH1 PH2 NPH2 CMPCK`. ADC = `sdm3_mod` (ENOB18 study, includes the
  PH2-edge DFF DAC-retiming fix). RST tied to VSS internally (as v1).
- `source/trials/20260902/xschem/rev2_tb_e2e.spice` — E2E bench (below).
- `source/trials/20260902/xschem/rev2_tb_noise.spice`,
  `rev2_tb_noise_ss.spice` — frozen-chopper noise/gain checks.

Include order for benches (verified working):
eeg_tg_lowq, eeg_bias_gen, eeg_fd_ota_chopped_full2 (for eeg_cmfb_amp_dl2),
eeg_pseudo_res, rev2_afe_chopped_full2, rev2_afe_pga,
eeg_fd_ota_core_soft, eeg_fd_ota_full2_nc, eeg_sd_int, sdm3_int1,
eeg_strongarm, sdm3_mod, rev2_top.

## Interfaces / notes for the layout agent

- **Clocks:** sdm3 needs PH1/PH2 (256 kHz, 2-phase non-overlap ~300 ns,
  30 ns edges) + CMPCK (fires 1.30-1.68 µs into each 3.90625 µs cycle,
  i.e. late PH1). Generated behaviorally in the bench from the 256 kHz
  master timing; **eeg_clkgen RTL needs a 256k->2-phase+comparator-clock
  generator added (separate task, not done here)**. Chopper phases stay
  1 kHz as v1.
- **References:** VP/VN external, VCMA+/-25 mV (VCMA~0.927), VCM_REF=0.9 V
  external — unchanged from v1. SDM full scale = VP-VN = 50 mV diff.
- **PGA->ADC coupling:** direct (PGA_OUTP/N into sdm3 VINP/VINN). sdm3
  input sampling caps are 2x2 pF per integrator input side (CS1=8p total
  diff structure) — the PGA drives them; verified in E2E below.
- **sdm3 internal structure for layout:** int1 = `sdm3_int1` (sampled
  input + direct same-cycle DAC, CS=8p CDAC=8p CI=4p per side), int2 =
  `eeg_sd_int` (CS=2p CDAC=4p CI=4p, CLOCK PINS SWAPPED vs int1),
  strong-arm + NAND SR latch + 1 pF hold caps + PH2-edge DFF (`sdm3_dff`,
  TG master-slave) + `sdm3_inv`/`sdm3_nand2` + BIT RC filter (1k/2p).
- **Bitstream readout quirk:** always majority-vote BIT over the PH2
  plateau (scripts/sdm3_bitstream.py); single-point sampling on the
  ngspice internal grid fakes a noise floor.

## Measured results

**rev2 AFE (frozen-chopper .noise, rev2_tb_noise*.spice):**

| corner | onoise@1kHz | gain@8Hz | in-band (0.5-100 Hz) |
|---|---|---|---|
| TT 1.80 V 27 C | 417.7 nV/rtHz | 31.93 | **0.130 µVrms** |
| SS 1.62 V 125 C | 857.9 nV/rtHz | 31.91 | 0.268 µVrms |

Canonical (RLOAD 2Meg) references: TT 0.644, SS 0.691 µVrms -> the LN
change improves TT 5.0x and SS 2.6x. Gain is corner-flat (31.9 both).

**sdm3 ADC standalone (scripts/sdm3_bitstream.py, 32 Hz 0.6 FS input,
fs=256 kHz):**

| corner | duty | bitstream amp | SNDR (0.5-100 Hz) |
|---|---|---|---|
| TT (ENOB18 study) | 0.5000 | 0.6001 | 91.68 dB |
| SS 1.62 V 125 C | 0.5000 | 0.6003 | 82.62 dB |
| FF 1.98 V -40 C | 0.5000 | 0.6000 | 64.63 dB |

Note: the first SS run failed catastrophically (duty 0.70, SNDR 12.6 dB)
- root cause was a hardcoded 1.8 V normalization in sdm3_int1's direct-DAC
gate drive; fixed by normalizing to v(VDD18) (see sdm3_int1.spice header).
Any re-use of the pre-fix sdm3_int1.spice at non-1.8 V supplies is invalid.

**Corner-degradation comment (SS 82.6 / FF 64.6 vs TT 91.7):** the shaped
out-of-band bands rise only ~30 % at both corners (2-10 kHz: 2.7e-4 ->
3.4-3.6e-4; 10-50 kHz: 5.2e-3 -> 6.8e-3), so NTF shaping and integrator
settling are essentially intact - the ~9 dB SS drop is NOT settling-
limited (the study's risk note overestimated that path). Bring-up
diagnostics (tb_sdm3_bringup[_ss/_ff].spice, current DFF modulator) show
integrator swings and quantizer-input rms are corner-INVARIANT
(x2@decision rms 0.061-0.064 V at TT/SS/FF), ruling out swing/headroom
and readout artifacts (FF floor is sample-window independent). The
degradation is dominated by the in-band limit-cycle floor (1.8e-6 TT ->
1.1e-5 SS -> 8.5e-5 FF, flat to ~2 kHz at FF): the known tone-locking
weakness of the 1-bit loop shifting regime with corner-dependent
per-edge disturbance energy (charge injection ~ VDD, comparator/latch
memory dynamics at FF speed). FF 64.6 dB sits BELOW the SC thermal budget
(~81 dB) and is the ADC's main PVT risk; the study's mitigations
(input/quantizer dither, anti-hysteresis comparator) target exactly this
and should be scheduled before relying on >80 dB ADC SNDR at FF.

**rev2 E2E (rev2_tb_e2e.spice: 300 mV electrode offset + 200 µV 50 Hz CM +
100 µV 8 Hz EEG, PGA x32, 0.55 s tran):**

- PGA gain @8 Hz (LS-fit, post-startup): **31.73** (expect 31.4-31.9 with
  the fc~1.3 Hz rolloff) - PASS.
- PGA_OUT DC -0.17 mV, CM 0.9216 V: no offset latch-up with 300 mV
  electrode offset - PASS.
- Bitstream duty 0.5018 (input-referred offset ~0.18 mV), 8 Hz amplitude
  **0.1308 FS** vs 0.126 expected (100 µV*31.73/50 mV) - PASS.
- 50 Hz CM line in the bitstream: 3e-5 FS (~1.5 µV output-referred) -
  CM rejection PASS.
- Analog output linearity (joint harmonic LS-fit, 0.35-0.55 s): HD2(16 Hz)
  -60 dBc, all other in-band harmonics <= -66 dBc; 50 Hz CM -70 dBc.
  The bitstream's top in-band line (16 Hz, 1.8e-4 FS ~ 9 µV) is consistent
  with this analog HD2, not a modulator artifact.
- Bitstream SNDR (0.5-100 Hz, 2 cycles of 8 Hz): 51.4 dB; cycle-by-cycle
  54.7 -> 62.5 dB as startup residue fades. NOT comparable to the
  standalone 91.7 dB: only 2 cycles (4 Hz bins, time-varying content) and
  0.126 FS vs 0.6 FS signal (-13.6 dB from level alone). A 32 Hz-stimulus
  rerun for an 8-cycle apples-to-apples number is in progress (below).

**rev2 E2E, 32 Hz stimulus (rev2_tb_e2e_32hz.spice, 8 coherent cycles,
0.3-0.55 s analysis window):**

- PGA gain @32 Hz: **31.71**, DC -0.08 mV - PASS.
- Bitstream duty 0.5008, 32 Hz amplitude **0.1307 FS** (expect 0.126) -
  PASS. 50 Hz CM line 3e-5 FS - PASS.
- **Bitstream SNDR(0.5-100 Hz) = 54.88 dB** at 0.126 FS (100 µV input).
- Decomposition: the AFE-noise bound at this signal level is
  20*log10(141.4 µVrms / 0.13 µVrms) = 60.7 dB (LN-AFE in-band noise
  0.13 µVrms from the frozen-bench metric; measured electrode-referred
  in-band noise from the bitstream = 0.22 µVrms incl. the AFE's sub-25 Hz
  excess). The ~6 dB gap to 54.88 dB is ADC limit-cycle content (strongest
  lines 4-20 Hz, partly startup residue - it fades cycle-to-cycle in the
  8 Hz run) and the 8-vs-10 cycle record. The ADC's quantization shaping
  itself is intact in situ (shaped bands match the standalone within 2x).
- System reading: at the realistic 100 µV EEG level the macro is
  AFE-noise-bound by design; quantization does not limit the channel. At
  0.6 FS the AFE-noise bound is ~74 dB SNR while the ADC measures 91.7 dB
  (TT), so the ENOB ceiling is set by the front end, not the modulator -
  exactly the intent of the LN-AFE + sdm3 pairing.

## Summary / acceptance snapshot

| block | metric | result | status |
|---|---|---|---|
| LN-AFE | in-band noise TT (SS) | 0.130 (0.268) µVrms | PASS (goal <=0.15 TT) |
| LN-AFE | gain @8 Hz | 31.9 (noise bench) / 31.73, 31.71 (E2E) | PASS |
| sdm3 | SNDR TT / SS / FF (0.6 FS) | 91.7 / 82.6 / 64.6 dB | TT/SS ok; FF below thermal budget - risk |
| macro E2E | gain, offset, CM rejection | 31.7x, duty 0.500x, CM line 3e-5 FS | PASS |
| macro E2E | SNDR @100 µV 32 Hz | 54.9 dB (AFE-noise-bound; bound ~60.7 dB) | as designed |
| macro idd | E2E OP | ~350 µA (AFE ~69 + ADC ~280) | report |

## Leftovers for the layout agent / next tasks

1. `eeg_clkgen.sv` needs a 256 kHz -> PH1/NPH1/PH2/NPH2 (non-overlap
   ~300 ns) + CMPCK generator; the bench models it behaviorally.
2. ADC FF-corner SNDR (64.6 dB) is the top analog risk: schedule
   dither / anti-hysteresis comparator evaluation (see ENOB18 study
   section 7) before final sign-off.
3. RLOAD=20Meg is a plain resistor change in two cells (core RLOADP/N,
   stage-2 RLOADO1/2) - layout can reuse the v1 structure with resized
   resistors; re-verify DRC/LVS after edit.
4. The rev2 AFE SS noise (0.268 µV) is 2.1x the TT value - if the full
   temperature range matters, this is the first thing to re-measure after
   layout (parasitics shift Rout).
5. `sdm3_int1.spice` MUST be the v(VDD18)-normalized version (see the SS
   bug note above); do not resurrect pre-fix copies.
