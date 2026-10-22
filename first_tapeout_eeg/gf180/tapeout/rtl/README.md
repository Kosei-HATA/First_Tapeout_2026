# GF180 EEG ADC: digital block (RTL)

RTL and simulation testbenches for the digital block of the GF180MCU EEG ADC: a continuous-time 2nd-order sigma-delta modulator with a 5-bit flash quantizer (31 comparators) and two 31-element unit DACs.

Status (2026-10-23): RTL written and verified in simulation with Icarus Verilog 13. Since gate 1 (10/23, `documentation/gf180_gate1_20261023.md`) the digital logic is two blocks: `eeg_digital_top` (clocking, CIC, FIFO, SPI, registers, raw stream) and the ADC-side `eeg_adc_dig` (TH capture, code, DWA), which sits in the ADC next to the quantizer and the DAC drivers. It has not been synthesized; Yosys was not available locally. The code uses a plain synchronous SystemVerilog-2012 subset meant for Yosys/LibreLane: `always_ff`/`always_comb`, no latches, and no `initial` blocks, delays or classes in RTL.

Numbers here supersede `documentation/gf180_digital_spi_proposal_20261008.md` (512 kHz, R = 512): fs = 1.024 MHz, R = 1024, 37-bit CIC, shift by 12.

## Files

| File | Content |
|---|---|
| `eeg_digital_top.sv` | Main digital block: reset synchronizer, frame timing, CIC, FIFO, SPI, registers, raw stream; sends the frame strobes to `eeg_adc_dig` and takes its code |
| `eeg_adc_dig.sv` | ADC-side digital block (in the ADC): TH capture register, thermometer-to-binary, DWA for DAC1 and DAC2 |
| `eeg_digital_sys.sv` | The two blocks connected as on the chip, with the pre-split interface (TH in, SEL1/SEL2 out); used by `tb_spi` and `tb_top` |
| `eeg_clkgen.sv` | Frame counter and strobes, 128/64 kHz chop, chop_out delay, output-chopper blanking, MCLK/4 |
| `eeg_chop1.sv` | OTA1 chopper clock: 1..16 kHz or off, edges at e16 |
| `eeg_therm2bin.sv` | popcount(TH): bubble-tolerant thermometer-to-binary converter (adder tree) |
| `eeg_dwa.sv` | DWA element selection (N = 31), thermometer mode when disabled |
| `eeg_cic3.sv` | sinc^3 decimator, R = 1024, W = 37 |
| `eeg_rnd_sat.sv` | Round-half-even shift by 12 plus 24-bit saturation (helper of `eeg_cic3`) |
| `eeg_fifo.sv` | 8 x 48-bit sample FIFO, SEQ counter, overrun handling |
| `eeg_spi_slave.sv` | SPI mode-0 slave, commands, CRC-8 |
| `eeg_regs.sv` | Register file |
| `eeg_raw.sv` | Raw code debug serializer |
| `tb/` | Testbenches; `spi_bfm.svh` is the SPI master BFM shared by `tb_spi` and `tb_top` |
| `model/sdm2_model.py` | 2nd-order 5-bit sigma-delta behavioral model (code-stream generator) |
| `model/cic_golden.py` | Bit-exact golden model of `eeg_cic3`, plus a CRC-8 reference |
| `model/gen_vectors.py` | Writes all stimulus and golden files to `build/` |
| `run_tests.sh` | Runs everything and prints PASS/FAIL per test |

## Interface of `eeg_digital_top`

| Port | Dir | Description |
|---|---|---|
| `MCLK` | in | 32.768 MHz from an external oscillator. This is the only clock. |
| `RESET_N` | in | Asynchronous assert, deassert synchronized by a 2-FF synchronizer |
| `SCLK`, `CS_N`, `MOSI` | in | SPI slave inputs, asynchronous to MCLK, each with a 2-FF synchronizer |
| `MISO` | out | SPI data; Hi-Z is done by the pad through `MISO_OE` |
| `MISO_OE` | out | MISO pad output enable. High only while CS_N is low (see SPI timing). |
| `DRDY_N` | out | Low while the sample FIFO is not empty (registered) |
| `RAW_DATA`, `RAW_CLK` | out | Raw code debug stream. With RAW_EN = 0 both stay low, or carry a pair of timing signals selected by TEST_CFG[7:6] (DBG_SEL, see RAW debug stream) |
| `ADC_RST_N` | out | Synchronized reset for `eeg_adc_dig` (the internal `rst_n`) |
| `TH_CAPTURE` | out | Frame cycle 1 strobe: `eeg_adc_dig` captures TH at its end (e2) |
| `DAC_LOAD` | out | Frame cycle DAC_LOAD_CYCLE strobe: SEL1/SEL2 update at its end (e3) |
| `DWA_EN` | out | CONTROL.DWA_EN for the two DWA selectors |
| `CODE[4:0]` | in | Quantizer code c = popcount(TH) from `eeg_adc_dig`; used by the CIC (e4) and the raw stream (e0) |
| `CMP_STROBE` | out | Comparator clock: high for frame cycle 0, one MCLK cycle (30.5 ns) per frame |
| `DAC_CLK` | out | DAC1 update clock: high for one MCLK from one MCLK after SEL1/SEL2 change (frame cycle DAC_LOAD_CYCLE + 2 = 4). The DAC1 array opens all switches at its rising edge, latches SEL1 during a ~2 ns pulse and then closes the selected ones (`gf180/tapeout/adc/eeg_dac1.spice`) |
| `CHOP` | out | Chopper clock: 128 kHz (CONTROL.CHOP_FAST = 1, default) or 64 kHz |
| `CHOP_OUT` | out | CHOP delayed by `CHOP_DLY` MCLK cycles |
| `CHOP_BLANK` | out | Output-chopper blanking: high from 1 MCLK before to BLANK_LEN MCLK after every CHOP_OUT edge. The analog clock driver gates the output-chopper phases with ~CHOP_BLANK. Held high while TEST_CFG[5] (ADC_ZERO) = 1 |
| `AFE_RST`, `CHOP_EN` | out | Static control bits from CONTROL |
| `TEST_CFG[7:0]` | out | TEST register: [4:0] analog test multiplexer, [5] ADC_ZERO (the analog side also shorts the ADC input, `eeg_adc.spice`), [7:6] DBG_SEL |
| `CPF_TRIM[3:0]` | out | ANA_TRIM[3:0], impedance-boost capacitor trim (decoded by the analog side) |
| `AFE_IBIAS[1:0]` | out | ANA_TRIM[5:4], AFE bias-current select (decoded by the analog side) |
| `BTRIM_P[1:0]` | out | BOOST_TRIM[1:0], PMOS-cascode booster units: 00 = 2, 01 = 4, 10 = 6, 11 = 8 (decoded by the analog bias block) |
| `BTRIM_N[1:0]` | out | BOOST_TRIM[3:2], NMOS-cascode booster units, same coding |
| `OFM[9:0]` | out | Electrode-offset DAC magnitude (OFF_CTRL[1:0], OFF_CODE_L) |
| `OFS` | out | Electrode-offset DAC sign (OFF_CTRL[3]) |
| `OFEN[3:0]` | out | Electrode-offset DAC range groups: thermometer of OFF_RANGE (1 → 0001 … 4 → 1111; 5..7 act as 4) |
| `CHOP1` | out | Chopper clock of the ADC's first integrator OTA (OTA1): 1 = phase A. 1, 2, 4 (default), 8 or 16 kHz, or held at 1 (CHOP1 register); edges only at e16 |

Parameter: `DAC_LOAD_CYCLE` (default 2, legal 2..31) sets the excess loop delay.

## Interface of `eeg_adc_dig` (ADC-side block)

| Port | Dir | Description |
|---|---|---|
| `MCLK` | in | The same 32.768 MHz clock as `eeg_digital_top` |
| `RST_N` | in | `ADC_RST_N` of `eeg_digital_top` |
| `TH_CAPTURE`, `DAC_LOAD`, `DWA_EN` | in | From `eeg_digital_top` |
| `TH[30:0]` | in | Quantizer thermometer outputs. TH[i] = 1 when the input is above threshold i; thresholds ascend. |
| `CODE[4:0]` | out | popcount of the captured TH, to `eeg_digital_top` |
| `SEL1[30:0]`, `SEL2[30:0]` | out | DAC1/DAC2 element selection; 1 = element to the positive reference |

- The 31 TH lines and the 62 SEL lines stay inside the ADC; between the two blocks run MCLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN and CODE[4:0] (`eeg_digital_sys.sv`).
- The timing is that of the single block before the split: TH is captured at e2, SEL1/SEL2 change at e3.

Size: about 1,005 flip-flops in all, counted from the RTL rather than from synthesis: about 900 in `eeg_digital_top` and about 103 in `eeg_adc_dig` (th_q 31, SEL1/SEL2 62, two 5-bit pointers). The largest parts are the FIFO (412, of which 384 are storage) and the CIC (301). This is within the 800–1200 FF budget of the 10/08 proposal.

Values during reset and right after it:
- SEL1/SEL2 = elements 0..15 (k = 16, code 15), the same reset state as the XSPICE controller model.
- The DWA pointers are 0.
- CMP_STROBE, DAC_CLK, CHOP and CHOP_OUT are 0.
- AFE_RST = 1, CHOP_EN = 1, DRDY_N = 1, MISO_OE = 0, TEST_CFG = 0 (ADC_ZERO off, DBG_SEL 0).
- CPF_TRIM = 8, AFE_IBIAS = 2 (ANA_TRIM = 0x28).
- BTRIM_P = 1, BTRIM_N = 1 (BOOST_TRIM = 0x05, 4 booster units each).
- The chop rate is 128 kHz.
- CHOP_BLANK is 0 during reset; BLANK_LEN = 7 after reset.
- CHOP1 = 1 (phase A) during reset and until e16 of frame 0; then 4 kHz.

## Frame timing

One modulator frame is 32 MCLK cycles (fs = 1.024 MHz). `e<n>` is the rising MCLK edge that starts frame cycle n. All strobes are registered and one MCLK cycle wide. A register that "updates at strobe X" uses X as a clock enable, so it changes at the edge that ends that cycle.

```
edge            e0  e1  e2  e3  e4  e5  e6  e7  e8  e9         e31 e0
frame cycle     | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |  ...     | 31| 0 |
CMP_STROBE      /‾‾‾\_____________________________________________/‾‾‾\
th_capture      ____/‾‾‾\__________________________________________________  TH -> th_q at e2
dac_load (=2)   ________/‾‾‾\______________________________________________  SEL1/SEL2 change at e3
DAC_CLK         ________________/‾‾‾\______________________________________  DAC1 switches at e4
cic_en          ____________/‾‾‾\__________________________________________  CIC integrators at e4
CIC comb steps                  | s1| s2| s3| s4|                            only in decimation frames
CIC dout_stb    ________________________________/‾‾‾\______________________  FIFO write at e9
TH stable       ......[ e2 ]...............................................  setup/hold window around e2
SEL1/SEL2       ===k[n-1]===X============ k[n] = 31 - c[n] ===============X==
raw_clk         ________/‾‾‾‾‾‾‾\_______/‾‾‾‾‾‾‾\___ ...  MCLK/4, high in cycles 2,3 (mod 4)
CHOP            128 kHz (CHOP_FAST = 1): toggles every 128 MCLK, edges at e0 of every 4th frame
                 64 kHz (CHOP_FAST = 0): toggles every 256 MCLK, edges at e0 of every 8th frame
                rate changes take effect at e0 of every 16th frame (see below)
CHOP_OUT        ____X‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾  (an edge, rising or falling, at edge eE)
CHOP_BLANK      /‾‾‾‾‾‾‾ BLANK_LEN ‾‾‾‾‾‾\___  rises at eE-1, falls at eE+BLANK_LEN (BLANK_LEN + 1 cycles)
CHOP1           toggles only at e16, every 512/256/128/64/32 frames (1/2/4/8/16 kHz)
```

- **Excess loop delay.** The time from the CMP_STROBE rising edge to the SEL change is (DAC_LOAD_CYCLE + 1) x T_MCLK = 91.55 ns (9.4 % of Ts) for the default, plus the DAC driver delay. Simulation measured 91.55 ns (DAC_LOAD_CYCLE = 2) and 183.11 ns (5).
  - DAC2 switches with SEL2 (e3). DAC1 switches at the DAC_CLK rising edge one MCLK later (e4, 122.1 ns = 12.5 % of Ts, plus about 0.7 ns in the analog pulse generator), because its common-break drive latches SEL1 during a short pulse from that edge. The behavioral loop gives 196.7 dB with DAC2 at e3 and DAC1 at e4 (`gf180/tapeout/sim/dac1/eld_mixed.py`; 195.7 dB with both at e3).
- **Loop delay.** The code decided at the strobe of frame n drives the DACs from e3 of frame n to e3 of frame n+1. At the comparator strobe of frame n+1, popcount(SEL) = 31 − c[n]. This is the one-frame feedback delay.
- **CIC.** Output strobes come every 1024 frames (1 kSPS), in frame cycle 8.
- **Startup.** After reset release, the first MCLK edge starts frame 0 at cycle 0, and CHOP rises at that edge.
- **Chop rate changes.**
  - CHOP_FAST is sampled only at the e0 where the 9-bit chop counter wraps: every 16th frame, every 512 MCLK (15.6 µs).
  - Both waveforms rise at that edge. The last phase before the switch is a full half period of the old rate and the first phase after it a full half period of the new rate, so there is no runt and no stretched phase.
  - A new CHOP_FAST value therefore takes effect 0..512 MCLK after the register write commits.
  - Why not every 8th frame: at the other 8th-frame point the 64 kHz waveform falls while the 128 kHz waveform rises. Switching there would drop one edge and leave a 384-MCLK phase.
- **CHOP_OUT.**
  - CHOP_OUT is CHOP delayed by CHOP_DLY = 0..255 MCLK, exactly, at both rates and across rate changes.
  - It is computed from the counter and the rate of the current and the previous 512-MCLK superperiod, so no delay line is needed.
  - It stays 0 until CHOP_DLY cycles after the first CHOP edge after reset.
  - A change of CHOP_DLY moves CHOP_OUT to the new delay at once. One short CHOP_OUT phase is possible then, so set CHOP_DLY while AFE_RST = 1 if that matters.
- **CHOP_BLANK.**
  - It rises at the MCLK edge one cycle before each CHOP_OUT edge, rising or falling, at both chop rates, and stays high for BLANK_LEN + 1 cycles. The output-chopper phases gated with ~CHOP_BLANK are therefore already off when CHOP_OUT toggles, and stay off for exactly BLANK_LEN MCLK after it (0..15; 7 = 214 ns after reset). BLANK_LEN = 0 means no pulse at all.
  - The CHOP_OUT edge is known one cycle ahead: the clock generator computes CHOP_OUT one more edge ahead with the same logic. CHOP_OUT uses CHOP_DLY registered once more inside the clock generator, so a new CHOP_DLY applies one MCLK after it reaches the clock generator. The prediction then uses exactly the delay CHOP_OUT will use, and it is exact even for the jump after a CHOP_DLY change. A CHOP_FAST change at a wrap cannot affect it, because CHOP_OUT at counter 0 is the same at both rates.
  - Exception: when CHOP_DLY = 0, CHOP_OUT rises at the first MCLK edge after reset release. That one edge is not blanked, because the cycle before it is still in reset; the AFE is held in reset (AFE_RST = 1) at that time.
  - It follows CHOP_OUT, so CHOP_DLY delays the blanking together with the output chopper.
  - It is a flip-flop output, so it does not glitch.
  - The length is latched when the pulse starts (one cycle before the edge). A BLANK_LEN write takes effect at the next pulse and never shortens or stretches a pulse in progress.
  - With BLANK_LEN = 0 no pulse starts; a pulse already running when BLANK_LEN is set to 0 finishes.
  - A CHOP_OUT edge within a pulse can only happen right after a CHOP_DLY change. It restarts the pulse (again from one cycle before the edge) with the current BLANK_LEN, or lets the running pulse finish if BLANK_LEN = 0.
  - CHOP_BLANK never changes at a CHOP_OUT edge: it rises one cycle before and falls BLANK_LEN cycles after. The flip-flop skew between the two signals therefore cannot make a gated output-chopper phase pulse at the edge.

- **CHOP1 (OTA1 chopper).**
  - It changes only at e16, half a frame from the comparator strobe (e0) and 13 MCLK after the DAC update (e3).
  - It is slow on purpose. Each OTA1 chopper edge disturbs the first integrator by a charge proportional to the OTA1 current, which follows the quantization error. Sampled once per edge, that folds the shaped quantization noise into the band, and the in-band level grows with the square root of the edge rate (`documentation/gf180_ota1_chopper_20261022.md`).
  - Every rate's period divides the CIC decimation (1024 frames), so the chopped OTA1 offset sums to zero in each output sample.

### Timing assumptions

1. **TH (no synchronizer).**
   - TH is the quantizer's answer to CMP_STROBE, so it is launched by edge e0 of the same clock. `eeg_adc_dig` captures it at e2, two MCLK periods later (61 ns), into `th_q`.
   - The analog quantizer must have its decision settled before e2 − t_setup, after clock-to-out, routing and comparator regeneration. It must hold the decision past e2 + t_hold, which needs an output latch (for example an SR latch after the StrongARM) that keeps the result until the next strobe.
   - The transistor quantizer (`gf180/tapeout/adc/eeg_quantizer.spice`) meets this: all TH bits settle within 4.0 ns of the CMP_STROBE edge at ss/−20 °C (2.3 ns typical) with 0.3 pF of routing on each TH, and a NOR SR latch holds them until the next strobe (`documentation/gf180_quantizer_20261022.md`).
   - For STA, constrain TH as a 2-cycle path launched by the CMP_STROBE flip-flop.
   - Each TH bit is registered before the popcount. An unresolved comparator therefore changes the code by at most 1 LSB. It never feeds an inconsistent value into the binary code.
   - `tb_top` drives TH only from mid-cycle 1 to mid-cycle 2 and random bits otherwise, so it would catch a capture at the wrong edge.
2. **Critical path.**
   - With DAC_LOAD_CYCLE = 2 the path th_q → popcount → (31 − c) → DWA rotation → SEL registers must settle in one MCLK period (30.5 ns).
   - If STA fails, use DAC_LOAD_CYCLE = 3. That adds 30.5 ns of ELD and gives the path 2 cycles, which needs a multicycle constraint.
   - The CIC path runs th_q → popcount → CODE (across the block boundary) → 37-bit adder. th_q changes only at e2 and the CIC takes the input at e4, so it can be constrained as a 2-cycle path. Each comb step is a single 37-bit subtractor.
3. **SPI.**
   - SCLK ≤ 2 MHz.
   - SCLK high and low times ≥ 4 MCLK (122 ns).
   - CS_N fall to first SCLK rise ≥ 3 MCLK (92 ns; ≥ 1 µs recommended).
   - Last SCLK fall to CS_N rise ≥ 3 MCLK.
   - CS_N high between transactions ≥ 4 MCLK.
   - MOSI is sampled through the same synchronizer depth as SCLK. It must be stable from about 1 MCLK before to 1 MCLK after the SCLK rising edge; with mode 0 it changes on the falling edge, so this holds easily.
   - MISO changes 2..3 MCLK after the SCLK falling edge (measured max 91.5 ns), leaving ≥ 158 ns of setup at 2 MHz before pad and board delays.
   - MISO_OE turns on 1..2 MCLK after CS_N falls (measured max 60.8 ns). It turns off without delay through a combinational path from the CS_N pad when CS_N rises, and when RESET_N is asserted.
4. **RAW.**
   - RAW_DATA changes at e1, e5, ..., e29. RAW_CLK rises at e3, e7, ..., e31.
   - Both are registered and retimed by one MCLK, giving 2 MCLK of setup and hold at the receiver.
   - RAW_EN is sampled at frame boundaries, so words are never cut.
   - DBG_SEL pairs (TEST_CFG[7:6]) are registered once, so on the pads they lag the signals at the analog blocks by one MCLK.

## Register map

| Addr | Name | Access | Reset | Bits |
|---|---|---|---|---|
| 0x00 | ID | RO | 0xE6 | |
| 0x01 | VERSION | RO | 0x07 | 0x07 since gate 1 (10/23): TEST_CFG[7:5] defined, DWA in `eeg_adc_dig` |
| 0x02 | CONTROL | RW | 0x74 | 0 RUN, 1 FILTER_CLEAR (self-clearing, reads 0), 2 DWA_EN, 3 RAW_EN, 4 AFE_RST, 5 CHOP_EN, 6 CHOP_FAST (1 = 128 kHz, 0 = 64 kHz chop), 7 reads 0 |
| 0x03 | STATUS | RO / W1C | 0x02 | 0 FIFO_NONEMPTY (RO), 1 SETTLING (RO, CIC not yet valid), 2 OVERRUN (W1C), 3 CMD_ERR (W1C) |
| 0x04 | FORMAT | RO | 0x05 | [3:0] quantizer bits = 5 |
| 0x05 | FIFO_LEVEL | RO | 0x00 | 0..8 |
| 0x06 | ODR_H | RO | 0x03 | ODR = 1000 SPS = 0x03E8 |
| 0x07 | ODR_L | RO | 0xE8 | |
| 0x08 | CHOP_DLY | RW | 0x00 | CHOP_OUT delay in MCLK cycles (0..255) |
| 0x09 | TEST | RW | 0x00 | Drives TEST_CFG[7:0]. The analog test multiplexer (`gf180/tapeout/test/eeg_testmux.spice`) uses [4] = ATP enable and [3:0] = node select (0 AVSS, 1 VCM, 2 VREFP, 3 VREFN, 4 VBN, 5 VBCM, 6 VBN1, 7 VNC1, 8 VPC1, 9 VBPC2, 10 VBNC2, 11 reference-current copy, 12/13 AFE OUTP/OUTN, 14/15 ADC O2P/O2N); [5] ADC_ZERO: holds CHOP_BLANK high (AFE output chopper open) and, on the analog side, closes the INP–INN switch of the ADC, for an ADC-only noise test; [7:6] DBG_SEL: with RAW_EN = 0 the RAW pads carry 01 CMP_STROBE / DAC_CLK, 10 CHOP / CHOP_OUT, 11 CHOP_BLANK / CHOP1 (RAW_CLK / RAW_DATA, one MCLK late) |
| 0x0A | ANA_TRIM | RW | 0x28 | [3:0] CPF_TRIM (reset 8), [5:4] AFE_IBIAS (reset 2), [7:6] read 0; drive the CPF_TRIM / AFE_IBIAS ports |
| 0x0B | BLANK | RW | 0x07 | [3:0] BLANK_LEN: blanking after each CHOP_OUT edge in MCLK, 0..15, 0 = no blanking (the pulse also covers 1 MCLK before the edge); [7:4] read 0 |
| 0x0C | BOOST_TRIM | RW | 0x05 | [1:0] BTRIM_P (reset 1), [3:2] BTRIM_N (reset 1): cascode-booster units 00 = 2, 01 = 4, 10 = 6, 11 = 8; [7:4] read 0; drive the BTRIM_P / BTRIM_N ports |
| 0x0D | OFF_CODE_L | RW | 0x00 | Electrode-offset DAC magnitude M[7:0] |
| 0x0E | OFF_CTRL | RW | 0x00 | [1:0] M[9:8], [3] SIGN, [6:4] OFF_RANGE (0 = off, 1..4 = ±39 / 79 / 159 / 318 mV, 5..7 = 4); 2 and 7 read 0. The analog DAC cancels (1 − 2 SIGN) × M × 0.311 mV of ELP − ELN offset; M is limited to the bits of the range (`documentation/gf180_electrode_dc_20261022.md`) |
| 0x0F | CHOP1 | RW | 0x03 | [2:0] CHOP1_RATE: OTA1 chopper 0 = off (CHOP1 = 1), 1..5 = 1 / 2 / 4 / 8 / 16 kHz, 6..7 = 16 kHz; [7:3] read 0. Sampled every 1024 frames (1 ms), at e0 of the frame where all rates rise at e16, so a change never makes a short phase (`eeg_chop1.sv`) |

- Other addresses read 0x00.
- Writes to RO and undefined addresses are ignored.
- W1C: write 1 to clear a bit. If a set event happens in the same cycle as the clear, the set wins.

## SPI protocol

Mode 0 (CPOL = 0, CPHA = 0), MSB first. MOSI is sampled on SCLK rising edges and MISO changes after falling edges. One command per CS_N low period; byte 0 is the command.

### `0x30` READ_SAMPLE (8 bytes)

| Byte | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| MOSI | 0x30 | dummy | dummy | dummy | dummy | dummy | dummy | dummy |
| MISO | 0x00 | STATUS | SEQ[15:8] | SEQ[7:0] | DATA[23:16] | DATA[15:8] | DATA[7:0] | CRC-8 |

- **STATUS** = {VALID, OVERRUN, SETTLING, 5'b0}.
- **CRC-8** covers bytes 1..6: poly 0x07, init 0x00, no reflection, xorout 0x00 (CRC-8/SMBUS; check("123456789") = 0xF4).
- **Shadow copy.** When the command byte completes, the FIFO head is copied into a shadow register, so the frame stays consistent.
- **Consumption.** The entry is removed on CS_N rising only if exactly 8 complete bytes were clocked and the shadow held a valid entry. Shorter frames, longer frames, or extra clocks consume nothing, so the sample can be read again.
- **Empty FIFO.** STATUS = {0, OVERRUN, SETTLING, 0}, SEQ = 0 and DATA = 0, with a correct CRC.
- **Stored entries.** STATUS is {1, OVERRUN at write time, 0, 0}. OVERRUN = 1 in a sample means it was written while the sticky OVERRUN flag was set, that is after a drop and before the MCU cleared the flag.
- **DATA** is the 24-bit two's complement CIC output. Full scale is ±31 · 2^18 = ±8 126 464.

### `0x10` READ_REG (3 bytes)

- MOSI: 0x10, addr, dummy.
- MISO: 0x00, 0x00, value.

### `0x20` WRITE_REG (3 bytes)

- MOSI: 0x20, addr, value.
- The write commits on CS_N rising, and only if exactly 3 complete bytes were clocked.

### Other command bytes

- This includes 0x00 and 0xFF.
- The sticky CMD_ERR flag is set when the command byte completes, and MISO stays 0x00.
- A transaction with fewer than 8 clocks has no command and is ignored.

## Decimation filter (`eeg_cic3`), exact definition

The Python golden model (`model/cic_golden.py`) uses the same integer arithmetic.

- **Input.** x = 2c − 31, with c = popcount(TH) (odd values, −31..31), one input per frame at cic_en.
- **Register width.**
  - All integrator and comb registers are W = 37 bits and wrap modulo 2^37. Nothing saturates inside the filter.
  - The gain is R^3 = 2^30, so the largest output 31 · 2^30 < 2^36 fits.
- **Integrators.** The pipelined Hogenauer form: on every accepted input, `i1 += x; i2 += i1_old; i3 += i2_old`.
- **Combs.**
  - On the 1024th accepted input since reset or clear, and every 1024 inputs after that, the combs run on the updated i3 (differential delay 1): `a = i3 − d1; d1 = i3; b = a − d2; d2 = a; y = b − d3; d3 = b`.
  - In hardware these are 4 MCLK steps sharing one accumulator.
- **Output.** `round_half_to_even(y / 2^12)`, then saturation to signed 24 bits.
  - Saturation cannot be reached with legal inputs. It is tested on its own in `eeg_rnd_sat`.
- **Valid flag.**
  - The first 2 output strobes after reset or FILTER_CLEAR hold partially filled windows. They are flagged invalid and not written to the FIFO.
  - Valid outputs start with the 3rd strobe, at the 3072nd accepted input. SETTLING = 1 until then.
  - The first valid sample appears about 3.0 ms (3072 frames) after FILTER_CLEAR; `tb_spi` checks that DRDY_N falls 2.99..3.06 ms after the write.
- **FILTER_CLEAR.**
  - It synchronously clears all CIC state, the decimation counter, the strobe counter and SEQ.
  - An input in the same cycle is discarded.
  - An output still in the 5-cycle comb pipeline is discarded.
  - The FIFO contents are kept.

## FIFO, SEQ, RUN, DRDY_N

- **FIFO.** 8 entries of {status[7:0], seq[15:0], data[23:0]}.
- **When samples are written.**
  - A valid CIC output is written while RUN = 1.
  - If the FIFO is full, the new sample is dropped, old data is never overwritten, and the sticky OVERRUN flag is set.
  - A write into a full FIFO is accepted only if an entry is popped in the same cycle.
- **SEQ.**
  - SEQ counts every valid CIC output since reset or FILTER_CLEAR. The first valid output after a clear has SEQ = 0.
  - Outputs that are not stored also count: those with RUN = 0 and those dropped because the FIFO was full.
  - A gap in SEQ therefore tells the MCU exactly how many samples it did not get.
- **DRDY_N.** Low while FIFO_LEVEL > 0, driven from a register so it does not glitch.

## RAW debug stream

When RAW_EN = 1, one 8-bit word per frame is sent MSB first at 8.192 Mbit/s (4 MCLK per bit). The word is `{3'b101, c[4:0]}`, where c is the code of the previous frame; the `101` prefix marks word boundaries. RAW_CLK and RAW_DATA stay low when RAW_EN = 0.

Timing debug (TEST_CFG[7:6] = DBG_SEL, gate 1): while the stream is off, DBG_SEL 1..3 puts a pair of frame-timing signals on the pads, each registered once (one MCLK later than at the analog blocks): 01 RAW_CLK = CMP_STROBE, RAW_DATA = DAC_CLK; 10 CHOP, CHOP_OUT; 11 CHOP_BLANK, CHOP1. The stream has priority from the frame boundary where RAW_EN is taken, so neither words nor debug pairs are cut at a stream boundary.

## Verification

Run everything:

```
./run_tests.sh          # about 2 minutes; --quick skips the 20k-output CIC stream
```

The script runs the golden-model self checks and generates vectors into `build/`. It then compiles and runs every testbench with `iverilog -g2012 -Wall`, which compiles without warnings. It prints one PASS/FAIL line per test and keeps one log per test in `build/logs/`. No waveform files are written. `build/` holds about 21 MB, mostly the 20.6 MB CIC stream, and is listed in `rtl/.gitignore`.

| Test | Testbench | What is checked |
|---|---|---|
| golden_selfcheck | `model/cic_golden.py` | CRC check value 0xF4, rounding ties, saturation, DC response = x · 2^18 |
| therm2bin | `tb_therm2bin` | Every clean thermometer code, every single-bit bubble on each code, 100k random patterns |
| dwa | `tb_dwa` | 160k loads covering every k = 0..31. Checks popcount = k, contiguous run mod 31, exact run position against a reference pointer, pointer = (p + k) mod 31, and no change without load. Also checks the dwa_en = 0 thermometer mode with pointer hold, and that element-usage spread stays ≤ 1 (first-order DWA property). |
| clkgen | `tb_clkgen` | Strobe positions in every frame, with DAC_LOAD_CYCLE 2 and 7. Checks CHOP every cycle against a reference at both rates while CHOP_FAST is toggled at random, unaligned times (47 rate changes took effect; shorter requests reverted within one superperiod and correctly had no effect). Every CHOP and CHOP_OUT phase must be a full 128 or 256 MCLK (no runt), and CHOP edges must fall on cmp_strobe. Also checks chop_out against the recorded chop history for delays 0, 1, 37, 127, 128, 129, 200 and 255 at both rates and across rate changes, raw_clk period and phase, and an asynchronous reset in the middle of 64 kHz operation. CHOP_BLANK is compared every cycle with a reference, plus independent checks:<br>• every pulse rises exactly one cycle before a CHOP_OUT edge;<br>• CHOP_BLANK is high in the cycle before every CHOP_OUT edge with BLANK_LEN ≠ 0;<br>• each pulse is exactly BLANK_LEN + 1 cycles long, with BLANK_LEN taken at its start.<br>The CHOP_OUT edge at the first MCLK edge after reset is exempt. These run for BLANK_LEN 0, 1, 7 and 15 at both rates and every delay, a 0..15 sweep, BLANK_LEN changes during a pulse, CHOP_DLY changes, and pulses right after rate changes. |
| rnd_sat | `tb_rnd_sat` | 25k vectors from the golden model: ties to even and odd, around ±2^23, saturation, random 37-bit values |
| cic_impulse | `tb_cic` | Impulses (c = 31 and c = 0 on a ±1 baseline) at 9 phases of the decimation period; every strobe bit-exact |
| cic_step | `tb_cic` | Full-scale and small steps, aligned and not aligned; every strobe bit-exact |
| cic_stream | `tb_cic` | 20.6 M codes from the 2nd-order 5-bit sigma-delta model (sine plus DC plus noise, fixed seed) with a mid-stream clear and a clear in the same cycle as an input. Every strobe is compared, including the start-up strobes after each clear. Covers wrap-around of i2, i3 and all 3 comb stages, and rounding ties. |
| spi_fifo_regs | `tb_spi` | `eeg_digital_sys` with constant TH, master asynchronous to MCLK at 2 MHz and 1 MHz. See the list below. |
| top_dlc2 / top_dlc5 | `tb_top` | Integrated test of `eeg_digital_sys` with DAC_LOAD_CYCLE = 2 and 5. See the list below. |

`tb_spi` checks:
- ID, VERSION, FORMAT, ODR, defaults and undefined addresses.
- CONTROL, CHOP_DLY, TEST, ANA_TRIM, BOOST_TRIM, OFF_CODE_L and OFF_CTRL read-back and pins, including the OFEN range decode (ranges 0..4 and 7); CONTROL bit 7, ANA_TRIM bits 7:6, BOOST_TRIM bits 7:4 and OFF_CTRL bits 2 and 7 read 0.
- CHOP high time and CHOP_OUT delay and high time measured on the pins: 128 kHz with delays 0, 90 and 200, then 64 kHz after CHOP_FAST = 0 with delays 200, 90 and 0, then back to 128 kHz.
- BLANK read-back (bits 7:4 read 0), and CHOP_BLANK on the pins at rising and falling CHOP_OUT edges: it must rise 1 MCLK before the edge, be high at the edge, and fall BLANK_LEN MCLK after it. Covered: BLANK_LEN 7 (reset) and 15 at 128 kHz, 15 and 1 at 64 kHz with CHOP_DLY = 200 and 90, 0 at both rates (no pulse), and 7 again. CHOP_BLANK is also checked to be 0 during reset.
- FILTER_CLEAR self-clearing and RO writes ignored.
- Partial or long WRITE_REG frames ignored.
- CMD_ERR and W1C; writing 0 does not clear.
- Empty frames, settling time, frame contents and CRC.
- Partial, 7-, 9-byte and extra-clock READ_SAMPLE frames do not consume.
- SEQ.
- Overrun: the 8 oldest samples are kept, OVERRUN is stamped in the next sample, and W1C clears it.
- With RUN = 0 nothing is stored while SEQ keeps counting.
- DRDY_N matches the FIFO level on every MCLK.
- MISO only changes while SCLK is low, within 4 MCLK.
- MISO_OE timing.
- TEST_CFG[5] (ADC_ZERO) holds CHOP_BLANK high over several CHOP edges.
- TEST_CFG[7:6] (DBG_SEL) 1, 2 and 3 with RAW_EN = 0: RAW_CLK and RAW_DATA equal the selected pair one MCLK late, at every MCLK (9,000 cycles for DBG_SEL 3, covering a CHOP1 edge); with RAW_EN = 1 the stream takes over (8 RAW_CLK edges per frame), and the pair returns when RAW_EN is cleared; DBG_SEL 0 leaves the pads quiet.

`tb_top` checks:
- TH comes from a 2nd-order sigma-delta code stream. It is valid only around the capture edge and random otherwise.
- Every SPI-read sample is bit-exact against the golden CIC output of the same stream, with STATUS, SEQ and CRC checked.
- SEL1/SEL2 are checked against a reference DWA model at every dac_load, with DWA_EN toggled during the run.
- popcount(SEL) = 31 − c[n] at the CMP_STROBE of frame n+1.
- SEL changes only at the dac_load edge, and the ELD is measured.
- RAW words are checked against the codes, and RAW is quiet when disabled.
- CHOP edges fall on CMP_STROBE edges, and every CHOP phase is 128 MCLK (CHOP_FAST stays at its default, 128 kHz).
- With the default BLANK_LEN = 7, CHOP_BLANK is high from 1 MCLK before to 7 MCLK after every CHOP_OUT edge, and there are no other pulses. The edge at the first MCLK edge after reset is exempt.

The `tb_dwa` element-usage check runs over its first 50,640 loads. A mutation check outside the repository confirmed that the testbenches catch bugs: 12 injected RTL bugs were all detected (rounding, integrator form, NSKIP, DWA pointer, popcount, CRC polynomial, FIFO overwrite, partial-frame pop, capture edge, chop_out delay, RAW bit order, W1C priority). Four more for the chop-rate logic were also detected by `tb_clkgen`: switching every 8th frame, switching immediately, ignoring the previous superperiod's rate for CHOP_OUT, and no post-reset gating of CHOP_OUT. Four more for CHOP_BLANK were detected as well: width off by one, length not latched, rising edges only, and following CHOP instead of CHOP_OUT. Five more for the early start of CHOP_BLANK were also detected: predicting with the old CHOP_DLY, CHOP_OUT without the extra CHOP_DLY register, BLANK_LEN instead of BLANK_LEN + 1 cycles, starting at the edge, and wrong rate bookkeeping at a wrap. Three more for gate 1 (10/23) were detected by `tb_spi`: no ADC_ZERO forcing of CHOP_BLANK, the DBG_SEL pairs swapped, and the debug pair taking priority over the raw stream.

### Results (run of 2026-10-23, Icarus Verilog 13.0, Python 3.13.9)

Output of `./run_tests.sh` (clean `build/`, total about 1 min 40 s):

```
PASS  golden_selfcheck    0s  cic_golden self checks passed
PASS  gen_vectors         7s  top_stream: 60000 frames, codes 3..27, 56 valid outputs, wraps i3 80
PASS  therm2bin           2s  tb_therm2bin (101024 patterns)
PASS  dwa                10s  tb_dwa (160912 loads, every k 0..31 >= 100 times, 50640 usage-spread checks)
PASS  clkgen              1s  tb_clkgen (2697 frames, 47 rate changes, CHOP phases 128/256 MCLK: 373/149, CHOP_OUT phases: 368/131, 86321 chop_out checks [48079 at 128 kHz, 38242 at 64 kHz] with delays 0/1/37/127/128/129/200/255, CHOP_BLANK pulses for BLANK_LEN 1/7/15 (1 MCLK before + BLANK_LEN after the edge): 73/183/139 [303 at 128 kHz, 136 at 64 kHz, 371 with CHOP_DLY != 0, 123 within 512 MCLK after a rate change, 13 blank_len changes during a pulse, all lengths 1..15 seen], 21580 raw_clk periods)
PASS  chop1               2s  chop1 rates, e16 edges, phase lengths and 1 ms rate changes
PASS  rnd_sat             0s  tb_rnd_sat (25156 vectors)
PASS  cic_impulse         0s  tb_cic impulse (41984 operations, 41 output strobes bit-exact, 39 valid)
PASS  cic_step            0s  tb_cic step (29749 operations, 29 output strobes bit-exact, 27 valid)
PASS  cic_stream         56s  tb_cic stream (20600001 operations, 20116 output strobes bit-exact, 20110 valid)
PASS  spi_fifo_regs       6s  tb_spi (163 SPI transfers at 2 and 1 MHz, 25 READ_SAMPLE frames, 994059 DRDY_N checks, 7 CHOP/CHOP_OUT and 14 CHOP_BLANK pin checks at 128 and 64 kHz, 11400 DBG_SEL pin checks, max MISO latency 91.5 ns, max MISO_OE latency 60.8 ns)
PASS  top_dlc2           11s  tb_top DAC_LOAD_CYCLE=2 (40 samples bit-exact vs golden, 43149 SEL checks [29837 DWA, 13312 thermometer], 43148 SEL popcount checks at the next CMP_STROBE, ELD CMP_STROBE->SEL 91.55..91.55 ns, 43149 DAC_CLK pulses 1 MCLK after SEL, 43129 RAW words, 10788 CHOP edges at 128 kHz, 10787 CHOP_BLANK pulses from 1 MCLK before to 7 MCLK after the CHOP_OUT edge, max MISO latency 91.5 ns)
PASS  top_dlc5            4s  tb_top DAC_LOAD_CYCLE=5 (12 samples bit-exact vs golden, 14477 SEL checks [10381 DWA, 4096 thermometer], 14476 SEL popcount checks at the next CMP_STROBE, ELD CMP_STROBE->SEL 183.11..183.11 ns, 14477 DAC_CLK pulses 1 MCLK after SEL, 14458 RAW words, 3620 CHOP edges at 128 kHz, 3619 CHOP_BLANK pulses from 1 MCLK before to 7 MCLK after the CHOP_OUT edge, max MISO latency 91.5 ns)
== summary: 13 passed, 0 failed ==
```

- The `tb_top` results (samples, SEL checks, ELD, RAW words, CHOP and CHOP_BLANK counts) are the same as before the split into `eeg_digital_top` and `eeg_adc_dig`.

The vector generator also reports this coverage for the stream test (`build/vectors.log`):
- 20,599,999 accepted inputs, 2 clears (1 input discarded by a clear in the same cycle), 20,116 strobes, 20,110 valid.
- Wrap events: i1 0, i2 816, i3 5,105,718; combs 5,005 / 5,074 / 2,624.
- 6 exact rounding ties (3 to even, 3 rounded up from odd).

The rounding test adds 25,156 vectors with 10,077 saturating cases.

## Design decisions on points the specification left open

- **SEQ.** It counts valid CIC outputs whether or not they are stored (RUN = 0 or FIFO full). It restarts at 0 on reset and on FILTER_CLEAR.
- **STATUS byte of a READ_SAMPLE frame.**
  - For a stored sample: VALID = 1, OVERRUN as stored at write time, SETTLING = 0.
  - For an empty FIFO: the current OVERRUN and SETTLING flags.
  - SEQ and DATA are 0 in an empty frame.
- **Frame-length rules.** Only exact-length frames act: 8 bytes for the READ_SAMPLE pop and 3 bytes for a WRITE_REG commit. Partial frames, longer frames and extra clock bits are ignored.
- **Command byte.** 0x00 and 0xFF also set CMD_ERR. Undefined register addresses read 0 and do not set CMD_ERR.
- **FILTER_CLEAR scope.** It resets the CIC and SEQ but does not flush the FIFO.
- **Chopper outputs.** CHOP and CHOP_OUT run regardless of CHOP_EN; CHOP_EN is only routed to its pin.
- **Chop rate switch point.** CHOP_FAST takes effect at every 16th frame, where both rates rise, not at every 8th frame (see Frame timing).
- **CHOP_BLANK timing.** It rises one MCLK before each CHOP_OUT edge and lasts BLANK_LEN + 1 cycles. The length is latched at the pulse start, so a BLANK_LEN change takes effect at the next pulse with no partial pulse. A pulse in progress when BLANK_LEN is set to 0 finishes.
- **CHOP_DLY latency.** CHOP_OUT applies a new CHOP_DLY one MCLK later than before, through the extra register that makes the blanking prediction exact.
- **First edge after reset.** The CHOP_OUT edge at the first MCLK edge after reset release (CHOP_DLY = 0) is not blanked.
- **RAW_CLK gating.** RAW_CLK is gated by RAW_EN so the 8 MHz pad stays quiet in normal operation (DBG_SEL = 0). RAW words carry the previous frame's code.
- **ADC_ZERO.** CHOP_BLANK = (clock-generator blanking) OR TEST_CFG[5]. Both are flip-flop outputs and TEST_CFG only changes on a register write, so the OR does not glitch in operation.
- **Reset state.**
  - SEL = elements 0..15 (k = 16) and pointer 0, matching the XSPICE controller model.
  - `th_q` resets to code 15.
  - The clkgen counter resets so that frame 0 starts at the first edge after reset.
- **MISO_OE.** It is released through a combinational path from the CS_N pad, so it drops at once when CS_N rises.

## Open items

- **Synthesis and STA have not been run.** The critical path at DAC_LOAD_CYCLE = 2 is th_q → popcount → DWA → SEL in 30.5 ns, now inside `eeg_adc_dig`. The TH input needs a 2-cycle constraint, CODE (th_q → CIC) can take a 2-cycle constraint across the two blocks, and the CS_N → MISO_OE path is combinational.
- **ELD in the loop design.** The XSPICE reference loop updates the DACs at the comparator clock, with almost no ELD. The RTL adds (DAC_LOAD_CYCLE + 1) MCLK = 91.6 ns, which the CT loop design must include or compensate.
- **DWA on DAC2.**
  - The XSPICE controller applies DWA only to DAC1 and drives DAC2 with the straight held thermometer code.
  - The RTL applies DWA to both DACs with one DWA_EN bit, as specified.
  - With identical inputs and reset state, SEL2 is always equal to SEL1. A separate enable, or a different start pointer, would be needed to make the two differ.
- **DWA placement (decided at gate 1, 10/23).** The TH capture, the thermometer-to-binary converter and both DWA selectors form `eeg_adc_dig`, placed in the ADC next to the quantizer and the DAC switch drivers, so the TH and SEL lines stay inside the ADC (`documentation/gf180_gate1_20261023.md`). Complementary switch drive is left to the analog switch drivers.
- **Start of CHOP_BLANK (resolved).** Earlier, CHOP_BLANK rose at the same MCLK edge as CHOP_OUT, so flip-flop skew could let a gated output-chopper phase pulse at the edge. CHOP_BLANK now rises one MCLK before the edge, so it never changes together with CHOP_OUT. What remains for the analog side: the gate must settle within the 30.5 ns between the rise of CHOP_BLANK and the CHOP_OUT edge, and the first CHOP_OUT edge after reset is not blanked.
- **Comparator latch.** The comparator needs an output latch, and its regeneration plus latch delay must fit before e2 (about 61 ns minus margins).
- **Not covered in simulation:**
  - Wrap of i1, which needs more than 2·10^9 full-scale inputs.
  - Gate-level and timing simulation.
  - Metastability effects on the synchronizers.
