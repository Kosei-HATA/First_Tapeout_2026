// tb_top_r14 - eeg_digital_top (r14) through its pins, with an SPI master on its own time base.
//
// CODE is driven once per frame (it changes at e2, after the TH capture, as eeg_adc_dig's code; audit round 9) from
// build/top_r14.codes (the CT loop model's stream); every CIC input
// and every output time are logged (build/top_r14_cic.log) and every sample read over SPI (build/top_r14_samples.log)
// so that tb/check_top_r14.py compares the samples bit-exactly with the golden CIC (rtl/model/cic_golden.py); every
// store is logged with ERR, ALERT_MASK, DFLAG and ALERT_MASK_D of its cycle, and the checker models each sample's
// VALID, OVERRUN and ERR (ALERT at the store) and its reserved bits (audit round 19, auditor C).
// Phases (each reports its checks; errors counted):
//   A  registers: the generated tests (build/reg_tests.svh, from regmap.py), CRC, frame errors, unknown command,
//      a wrong key, a burst read (address incrementing, CRC off); audit round 15 (auditor C): every illegal value of
//      every field (RANGE_ERR, nothing written), the write-only COMMAND and TEST_KEY read 0x00 while unlocked and
//      after a committed FLUSH (alone and in a burst); audit round 28 (auditor C): 2c, rounds of random legal bytes in
//      both address orders until every single-bit alias between writable registers is visible (IF_CFG included);
//      2d, the command codes and the key written as data to every address but COMMAND (ERR exact, never
//      RESET_FLAG; no SOFT_RESET commit and no pending command counted; IDLE at the end)
//   B  START: WARMUP exactly T_WARM, RECOVER T_REC, ALIGN to the next output time, FILL three outputs, RUN;
//      samples (VALID, SEQ, CRC); a sample read stopped after 4 bytes neither pops nor flags an error
//   C  APPLY in RUN: the settings at the tick, AFE_RST high after T_PRE for exactly T_RST, the re-settling, samples
//      again with the SEQ gap of the outputs not stored
//   D  APPLY_NR with T_ELEC = 2: one step accepted, CHANGED on the next 3 + T_ELEC samples; two steps rejected;
//      D2: leaving RUN (an APPLY) cancels the rest of a long CHANGED mark (T_ELEC = 30): no CHANGED in the next RUN;
//      D3: a second APPLY_NR with T_ELEC = 0 keeps the longer remaining mark of the first (T_ELEC = 10)
//   E  START with an inconsistent configuration (CFG_ERR), STOP, START in RUN (STATE_ERR)
//   F  one pending command: at 64 kHz a second command before the tick gets STATE_ERR, an unknown code CMD_ERR only
//   G  FLUSH, overrun (OVERRUN in DFLAG and in the next sample's status); a sample read across a FLUSH: the sample
//      stored after the flush is not popped by the read of the old head; DRDY_N pulse mode (128 MCLK per store)
//   H  SOFT_RESET: ERR (RESET_FLAG), CPF_TRIM, FIFO_LEVEL and the pins back to their reset values (every register
//      and flag: Y); SEQ, the frame counter and the choppers keep running
//   I  SOFT_RESET while a command is pending (64 kHz): taken at once, no STATE_ERR; the pending START goes with it
//      (CMD_PENDING 0 at once, IDLE two ticks on; audit round 16)
//   J  audit round 1 (11/20): every STATUS bit; at 64 kHz a write to a shadow or a timer while a command is pending
//      gets STATE_ERR (other registers are written); CRC on: a header-only read is legal, a read without its CRC
//      byte and a short sample read are FRAME_ERR; APPLY in WARMUP restarts T_WARM (AFE_RST released T_WARM after
//      the change); APPLY empties the FIFO; an injected overload sets OVL_NOW, DFLAG.OVL (only in FILL / RUN) and
//      the OVL bit of exactly the three samples whose window contains it
//   V  audit rounds 9, 10: APPLY_NR in IDLE, APPLY and APPLY_NR in RECOVER, WAIT_E, ALIGN and FILL (T_ELEC > 0 and
//      = 0), APPLY_NR in PRE and APPLY in PULSE refused (the end-to-end
//      replay had none of them), each with its effect (pins, STATE) and no flag. Also: CODE changes at e2 as the ADC's;
//      the RESET_N release reaches the first CMP_STROBE in 3 MCLK (2 synchronizer flops); the control reset of a
//      SOFT_RESET lasts 5 MCLK (H); RAW's bits change at e1, e5, ... and RAW_CLK rises at e3, e7, ... (O); T12 an
//      overload ending at the interval's last input; U3 / U4 CRC-off read flips. V13 (audit round 15, auditor A): an
//      APPLY changing the chopper to 64 kHz, then a STOP in PRE, taken at the next 128 kHz tick before the rate's wrap
//      (the active copy already 64 kHz) and at the first 64 kHz tick after it: AFE_RST 256 and 320 MCLK after the
//      APPLY's tick, its edge where the monitor expects it at the rate the clock generator runs, held into WARMUP
//   K  SEQ wraps from 0xFFFF to 0 (forced; after every phase whose samples are compared with the golden CIC: audit
//      round 8, the comparison had stopped at K, in the middle of the bench)
//   W  audit round 10: a reset released inside a frame (RESET_N at 48 points of a CRC write and of a CRC FLUSH, a
//      SOFT_RESET whose control reset ends inside the next frame): the frame is ignored up to its CS_N rise, MISO_OE
//      stays off, nothing is committed, the registers keep their reset values (after K: the golden log is off)
//   X  audit round 12 (auditor C): RESET_N resets asynchronously (RST-01): every control pin set away from its
//      reset value in RUN (a sample stored, a frame open), MCLK stopped, RESET_N low: without any MCLK edge every
//      pin is at its reset value (a register block with a synchronous reset passed every test); audit round 29
//      (auditor C): with
//      the frame strobes, DAC_CLK, CHOP, CHOP_OUT, CHOP1 and MISO too (check_reset_timing), also before the first
//      release (a DAC_CLK reset to 1 passed all 16 groups)
//   Z  audit round 30 (auditor C): an OFF_M_L write swept across the tick that takes a pending APPLY (IDLE) and
//      APPLY_NR (RUN), 64 kHz: STATE_ERR before the acknowledge cycle, written in it and after, the judged value applied;
//      audit round 31 (auditor C): ERR exactly, alternating targets, racing values above the range, and Z3, an APPLY
//      whose judged shadow is illegal (exactly CFG_ERR, nothing applied, whatever the racing write)
//   AA audit round 32 (auditor C): an overload (code 31) from 24 frames before FILL's third output, its first valid one,
//      to 16 frames after it: RUN entered at that output, the first sample that output's, VALID with OVL, DFLAG.OVL set
//      (SEQ-04, DAT-01; no phase had OVL_NOW = 1 at FILL's completing output, and a sequencer taking out_valid as
//      cic_valid & ~ovl_now passed all 16 groups)
//   AB audit round 33 (auditor C): an APPLY_NR (T_ELEC 0) or an APPLY in FILL, 40, 1,070 and 2,100 us after its entry,
//      each followed into RUN: ALIGN's output is the 1st, 2nd or 3rd after the clear before; with the FILL monitor
//      (every ALIGN output: the CIC's registers zero; every FILL store: the third output after the clear) a CIC taking
//      ALIGN's clear only at a valid output, which passed all 16 groups, fails
//   AC audit round 33 (auditor C): T_WARM 128 and 255, T_ELEC 255 from eeg_regs into eeg_seq (WARMUP and WAIT_E held;
//      the trace's timer model on every load, the values taken at eeg_regs' registers): a 7-bit t_warm port fails
//   AD audit round 34 (auditor C): the sample's ERR bit (ALERT at the store, spec 3.4) when ERR changes at the store's
//      own edge: in RUN an ADDR_ERR and its W1C clear, each committed near a store in 1/4-MCLK steps from 2 MCLK
//      before to 2 MCLK after the start of the store's cycle; every sample read carries the ALERT of its store's
//      cycle as the registers give it, and each sweep changes ERR before that cycle, at its start and at or after the
//      store's edge (a copy writing the FIFO the sample status registered one MCLK earlier passed all 16 groups)
//   AE audit round 35 (auditor C): ERR and DFLAG through every accepted command (REG-02, FLG-02: only their W1C
//      clears them): RESET_FLAG and ADDR_ERR standing, both DFLAG bits set in RUN, then START, APPLY in RUN,
//      APPLY_NR, FLUSH, STOP and APPLY in IDLE, ERR and DFLAG read exactly after each (copies clearing RESET_FLAG
//      or DFLAG when a configuration is applied passed all 16 groups)
//   AF audit round 35 (auditor C): the copy instants of the header's STATUS (cs_start) and of the empty word
//      (smp_snap): at 64 kHz in IDLE an APPLY refused with CFG_ERR at its tick, a register read's and an empty-FIFO
//      sample read's copy swept in 1/4-MCLK steps across that edge; STATUS's ALERT and the empty word's ERR against
//      the ALERT of the copy's cycle as the registers give it (copies taking either one MCLK early passed all 16
//      groups)
//      audit round 36 (auditor C): AE also takes a START with DFLAG standing (a copy clearing DFLAG at START passed)
//   AG audit round 36 (auditor C): T_REC and T_RST taken at the start of their waits (spec 4.2, SPI-12): T_REC
//      written in WARMUP sets RECOVER's length, T_RST written in PRE the AFE_RST pulse at the pin (a copy taking both
//      with the command passed all 16 groups)
//   AH audit round 36 (auditor C): an APPLY_NR in IDLE and in WARMUP applies the trims and TEST_MUX (table 5.1-2,
//      REG-08): AFE_IBIAS, CPF_TRIM and TEST_MUX at the pins and in the active copies (a copy applying only the
//      offset DAC's fields passed all 16 groups; every apply field: AJ. Audit round 37, auditor C: this line said
//      "every setting")
//   AI audit round 36 (auditor C): the read header's ADDR_ERR is raised within its frame: a CRC-off burst from the
//      undefined 0x7F through ERR reads STATUS with ALERT and ERR = ADDR_ERR (a copy raising it at CS_N's rise passed
//      all 16 groups)
//      audit round 37 (auditor C): AE stands all eight ERR bits (a short frame, a wrong CRC, an undefined address, an
//      illegal value, an unknown code, a refused APPLY, a START refused in WARMUP, RESET_FLAG); a copy clearing
//      CFG_ERR at an apply passed all 16 groups
//   AJ audit round 37 (auditor C): the apply matrix (build/pin_tests.svh's run_apply_matrix, generated from
//      regmap.pins_from_active): START, APPLY and APPLY_NR in IDLE and WARMUP and APPLY in RUN, each with two settings
//      that change every apply field and then the reset values; the active copies before (the case's previous
//      settings) and after, the pins, the CHOP, CHOP_BLANK and CHOP1 widths (copies leaving the chopper settings or
//      TEST_CTRL out of an APPLY_NR, or applying the test settings only while AFE_RST is high, passed all 16 groups)
//   Y  audit round 15 (auditor C): SOFT_RESET returns every register and flag (RST-02), written with CRC off and on:
//      every writable register away from its reset value (soft_set_all, generated), START, both DFLAG bits set,
//      samples in the FIFO, ERR holding ADDR_ERR; after it the generated burst over the whole map (ERR exactly 0x01,
//      DFLAG 0x00, STATUS 0xA1, the timers, masks, settings and active copies), the pins, DRDY_N high, the test
//      registers locked (a register block keeping the timers, the ALERT masks, DFLAG or DRDY_MODE through a SOFT_RESET
//      passed every test). On the way, STATUS with READY and DATA apart: RUN with the FIFO empty (READY 1, DATA 0),
//      IDLE with samples left (READY 0, DATA 1); no check had told them apart
//      Audit round 16 (auditor B): in Y0, a sample read in which the chip misses one SCLK pulse (an 8 ns runt), then
//      one extra byte of SCLK (the host's re-read rule, 5.4 step 6): FRAME_ERR and no pop
//   M  audit round 2 (11/20): the sample's ERR bit (ALERT at the store) and reserved bits, ALERT_MASK and
//      ALERT_MASK_D, the empty word (VALID 0, OVERRUN, OVL_NOW, ERR = ALERT, SEQ 0, DATA 0, CRC), the DRDY_N release in
//      level mode (at most 5 MCLK after the CS_N rise of the read that emptied the FIFO)
//   L  SPI at the specification's limits (VER-02): 2 MHz with the minimum high (4 MCLK) or the minimum low (5 MCLK),
//      and 1 MHz; CS_N setup 5 MCLK, hold 3 MCLK, high 4 MCLK; MISO through the 15 ns pad delay; CRC off and on
//   A also (audit round 3): a burst read of the whole map at reset against the map's reset values (generated), MISO
//      0x00 after a completed frame, an illegal SPI state value -> FRAME_ERR and nothing written (inside a frame;
//      between frames the next frame is processed normally and nothing is flagged, audit round 15); H: SOFT_RESET with
//      samples in the FIFO empties it (level 0, DRDY_N high, the next read is the empty word)
//   N  audit round 2 (auditor C): every analog control pin against the specification (build/pin_tests.svh, generated
//      from regmap.pins_from_active: OFM / OFS / OFEN per range, trims, CHOP_EN, DWA_EN, TEST_CFG, the CHOP_BLANK
//      length or hold, the chopper's and CHOP1's half periods, the active copies; M above the range's top -> CFG_ERR
//      and nothing applied), DFLAG.OVL not set by an overload in WARMUP, RECOVER, PRE and PULSE but set in FILL, an
//      APPLY_NR across a range -> CFG_ERR
//   P  audit round 4: a command refused because another is pending leaves the pending one (64 kHz: FLUSH pending in
//      RUN + START refused -> the FIFO is emptied, RUN stays; START pending in IDLE + FLUSH refused -> WARMUP)
//   S  audit round 4: the host's SOFT_RESET check (requirements 5.4 step 9) in both CRC modes: the mode probe (a 3-byte
//      read of IF_CFG, legal in both), RESET_FLAG, and the recovery from a spoiled SOFT_RESET frame. Audit round 5
//      (one-bit header errors against the host procedure): S3 a sample read whose header lost bit 7 (a write to the
//      window) fails the sample CRC, which covers the header 0xC0 (CRC off and on); S4 the step-9 check repeated until
//      RESET_FLAG = 1 in a probe-confirmed mode converges after a corrupted probe (0xD5 -> 0x55) and a spoiled
//      SOFT_RESET; S5 step 3 undoes an enabling IF_CFG write that landed on T_ELEC (0x55 -> 0x51)
//   R  audit round 4: SOFT_RESET committed in the cycle of a tick that releases AFE_RST (WARMUP's end), of a tick that
//      applies (APPLY in RUN: CPF_TRIM, OFM, OFEN), of an output time, and in the cycle after a store into an empty
//      FIFO (DRDY_N): no runt on any register-driven pin (soft_req forced for that one cycle); R5: a SOFT_RESET over
//      frame cycles 1..5 leaves the frame strobes (DAC_CLK in cycle 4); R6: an overload that ends just before a
//      SOFT_RESET is still in the detector's window after it (the detector runs from RESET_N: RST-02); R3 also: SEQ
//      counts the output time of the commit cycle (DAT-03); R7: a SOFT_RESET in the cycle where the CIC decides
//      ALIGN's clear (its step 3) cancels the clear; R8: one in the output-time cycle of ALIGN comes after the clear
//      (audit round 5)
//   T  audit round 5 (auditor C: RTL copies that passed every test): T1 ALERT from every ERR bit, T2 from DFLAG's
//      OVERRUN and OVL; T3 a CRC read of ERR while STATE_ERR is set in the frame (the CRC covers the byte sent);
//      T4 CHANGED for T_ELEC 255 (258 outputs, past 8 bits; the empty word while the mark runs: CHANGED 0, audit
//      round 8); T5 an overload in WAIT_E leaves DFLAG.OVL; T6 APPLY_NR
//      in RUN keeps the FIFO, a FLUSH keeps the CHANGED marks; T7 a command committed in the very cycle the tick takes
//      the pending one (its acknowledge cycle, 64 kHz, the frame start swept in half-MCLK steps) is the new pending
//      command. Always: CHOP_OUT == CHOP (CHOP_DLY 0). Audit round 6: T8 an overload in RUN that ends 8 frames before
//      an output time marks exactly the three samples whose window holds it (the detector's tail marks no fourth);
//      T9 an overload in ALIGN ending 12 frames before its clear sets neither DFLAG.OVL nor the first sample's OVL;
//      T10 an overload in the first FILL interval marks the first stored sample (its window is FILL's) and not the
//      next, and sets DFLAG.OVL; T11 CHANGED counts output times, not stored samples (marks spent on outputs dropped
//      by a full FIFO); T1 / T2 also mask each flag from ALERT; T2 reads OVL_NOW in STATUS and in the empty word
//      60 frames after an overload in the same output interval (they follow the detector); T4 the 258 marks as a
//      count; N4 STATUS in FILL; R4 also in pulse mode; R9 RAW's word runs on through a SOFT_RESET (RST-02).
//      Audit round 7: J2 writes every guarded register (regmap.guarded_addrs, run_guard_tests from gen_reg_tests.py)
//      while a FLUSH waits; G and T11 read FIFO_LEVEL = the depth while full; C and D: out of RUN for at least
//      T_PRE + T_RST + T_REC + T_ELEC + 3 ms after an APPLY (host procedure step 4)
// Also (audit round 4): every applied pin (OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM, DWA_EN, CHOP_EN, TEST_CFG[5:0])
// equals regmap.pins_from_active of the active copies at every MCLK in every state (CHOP_EN was seen only in IDLE and
// RUN); STATUS's READY and AFE_RST bits in WARMUP, PRE, PULSE, RECOVER and ALIGN (N4); APPLY_NR across M's byte
// boundary (N5); a wrong key after the right one locks (A).
//   N5 audit round 3: APPLY_NR's step rule (regmap.nr_ok, generated): every other applied setting changed -> CFG_ERR,
//      the sign walk; O: RAW_DATA / RAW_CLK (the code stream, the three timing pairs)
// Also (audit round 3): shadow writes alone leave the chopper, CHOP1 and CHOP_BLANK; STATE read in WARMUP, RUN, PRE,
// PULSE, RECOVER; the empty word with OVERRUN; no DRDY_N pulse for an output dropped by a full FIFO; the frame strobes
// at the pins (CMP_STROBE every 32 MCLK; TH_CAPTURE in frame cycle 1, DAC_LOAD in 2, DAC_CLK in 4 (rises at e4), each
// one MCLK)
// Also: RECOVER lasts T_REC (B) and WAIT_E T_ELEC (D); through a SOFT_RESET (H) CHOP1 keeps its phase and ADC_RST_N
// stays high; every sequencer event of the run is written to build/top_seq_trace.txt and replayed through
// fsm_spec.seq_tick by check_seq_trace.py --no-cover (VER-09 end to end).
// Define FIFO4 for the 4-deep FIFO (CAPS and the overrun test follow).
// Monitors: every analog control pin (AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM, TEST_CFG[5:0],
// CHOP_EN, DWA_EN) changes only at the MCLK edge right after a tick (or in reset); no register-driven pin (those and
// DRDY_N, TEST_CFG[7:6]) changes twice at one simulation time (a runt: NFR-06); the SPI timing (spi_bfm_r14.svh).
// Audit round 17 (auditor C: RTL copies that passed every test): at every CHOP_OUT edge CHOP_BLANK was high in the MCLK
// before it and stays high for the blanking length after it (BLANK_LEN, 15 with the offset DAC on), rising only in
// the MCLK before an edge unless ADC_ZERO holds it; CHOP1 changes only at e16; O compares each DBG_SEL pair until both
// of its signals changed twice (CHOP1's half period is 1,024 MCLK or more) and TEST_CFG[7:6] after each DBG_SEL write
// (audit round 19); the RAW pads against a model of the frame boundary (8 RAW_CLK rises in every frame of the stream,
// the DBG_SEL pair in every MCLK without it; O2 with RAW_EN 1 and DBG_SEL 1..3, and RAW_EN switched at 8 frame
// cycles; audit round 20); Y0 asserts that the chip missed the
// runt (71 bits); V13 runs at 2 MHz (SPI-01), the STOP written right after the APPLY; after RESET_N (A, X) and
// SOFT_RESET (Y) CHOP_BLANK's width, CHOP's half period and (after RESET_N) CHOP1's half period are REG-05's.
// Audit round 18 (auditor B): in Y one SCLK slip (an extra or a missed pulse) in a sample read gives FRAME_ERR and no
// pop, and in a CRC read of STATUS or STATE FRAME_ERR (the host procedure's slip rules rest on it). Audit round 18
// (auditor C): every SOFT_RESET commit raises soft_req in its own cycle (R forces soft_req at the cycles it tests).
// Audit round 19 (auditor B): after each slipped frame in Y the very next header (CS_N high 4 MCLK) shows ALERT
// (FRAME_ERR alone in ALERT_MASK), which the host procedure uses to find the frame that slipped.
// A watchdog ends the run as FAIL if it has not finished by 1,200 ms of simulated time (the run ends near 0.82 s; audit
// round 15, auditor C: the 600 ms, written as about 1.6 times the run, had become 1.13 times it; audit round 31,
// auditor C: the 800 ms had become 1.17 times it; audit round 35: the 1,000 ms had become 1.22 times it),
// so that an RTL error that leaves the bench waiting for an event fails instead of hanging.
`timescale 1ns / 1ps
`default_nettype none

module tb_top_r14;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;

`ifdef FIFO4
    localparam int FD = 4;
`else
    localparam int FD = 8;
`endif
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(FD)) dut (.*);

    bit mclk_run = 1'b1;                          // X: MCLK stopped to see RESET_N's asynchronous reset (RST-01)
    always #(TMCLK / 2.0) if (mclk_run) MCLK = ~MCLK;

    `define R14_SAMPLE_HOOK                       // r14_sample logs every sample it reads (audit round 8)
    `include "spi_bfm_r14.svh"
    `include "reg_tests.svh"
    `include "pin_tests.svh"

    integer errors = 0;
    // the SPI's state codes from the compiled RTL (audit round 27, auditor C: the illegal values 11..15 were written
    // here by hand, so a copy whose S_OVF was 11 left 10 unused, unflagged by st > S_OVF, and passed all 16 groups)
    logic [15:0] spi_defd;
    integer      n_spi_illegal;
    string       spi_illegal_txt;
    task spi_codes;
        spi_defd = 16'd0;
        spi_defd[dut.u_spi.S_IDLE] = 1'b1;  spi_defd[dut.u_spi.S_HDR] = 1'b1;   spi_defd[dut.u_spi.S_RREG] = 1'b1;
        spi_defd[dut.u_spi.S_RCRC] = 1'b1;  spi_defd[dut.u_spi.S_RDONE] = 1'b1; spi_defd[dut.u_spi.S_RSMP] = 1'b1;
        spi_defd[dut.u_spi.S_SDONE] = 1'b1; spi_defd[dut.u_spi.S_WDAT] = 1'b1;  spi_defd[dut.u_spi.S_WCRC] = 1'b1;
        spi_defd[dut.u_spi.S_WDONE] = 1'b1; spi_defd[dut.u_spi.S_OVF] = 1'b1;
        n_spi_illegal = 0;
        spi_illegal_txt = "";
        for (int b = 0; b < 16; b++)
            if (!spi_defd[b]) begin
                n_spi_illegal++;
                spi_illegal_txt = {spi_illegal_txt, $sformatf(" %0d", b)};
            end
    endtask
    // a constant force of each value (Icarus evaluates a forced expression only once)
    task force_spi_st(input integer v);
        case (v)
            0: force dut.u_spi.st = 4'd0;    1: force dut.u_spi.st = 4'd1;    2: force dut.u_spi.st = 4'd2;
            3: force dut.u_spi.st = 4'd3;    4: force dut.u_spi.st = 4'd4;    5: force dut.u_spi.st = 4'd5;
            6: force dut.u_spi.st = 4'd6;    7: force dut.u_spi.st = 4'd7;    8: force dut.u_spi.st = 4'd8;
            9: force dut.u_spi.st = 4'd9;    10: force dut.u_spi.st = 4'd10;  11: force dut.u_spi.st = 4'd11;
            12: force dut.u_spi.st = 4'd12;  13: force dut.u_spi.st = 4'd13;  14: force dut.u_spi.st = 4'd14;
            default: force dut.u_spi.st = 4'd15;
        endcase
    endtask

    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 40) $display("ERROR @%0t: %s", $time, msg);
    endtask

    // ------------------------------------------------------------------ register test helpers
    task automatic rt_read_expect(input logic [6:0] a, input logic [7:0] exp, input string name);
        logic [7:0] v;
        r14_read(a, v);
        if (v !== exp) fail($sformatf("read 0x%02h (%s): 0x%02h, expected 0x%02h", a, name, v, exp));
    endtask
    task automatic rt_burst_expect(input integer k, input logic [7:0] exp, input string name);
        if (spi_rx[k] !== exp) fail($sformatf("%s: 0x%02h, expected 0x%02h", name, spi_rx[k], exp));
    endtask
    task automatic rt_write(input logic [6:0] a, input logic [7:0] v);
        r14_write(a, v);
    endtask
    task automatic rt_expect_err(input logic [7:0] mask, input string name);
        logic [7:0] v;
        r14_read(7'h06, v);
        if ((v & mask) !== mask) fail($sformatf("%s: ERR 0x%02h without 0x%02h", name, v, mask));
        r14_write(7'h06, 8'hFF);
    endtask
    // a read-only register whose value moves (STATUS): the write's error only, no read-back (audit round 26, auditor C:
    // no fixed test wrote STATUS, and an eeg_regs taking STATUS writes silently passed tb_top_r14)
    task automatic rt_write_err(input logic [6:0] a, input logic [7:0] wv, input logic [7:0] emask, input string name);
        logic [7:0] e;
        r14_write(a, wv);
        r14_read(7'h06, e);
        if ((e & emask) !== emask) fail($sformatf("%s: ERR 0x%02h without 0x%02h", name, e, emask));
        r14_write(7'h06, 8'hFF);
    endtask
    task automatic rt_write_check(input logic [6:0] a, input logic [7:0] wv, input logic [7:0] rv,
                                  input logic [7:0] emask, input string name);
        logic [7:0] v, e;
        r14_write(a, wv);
        r14_read(a, v);
        if (v !== rv) fail($sformatf("%s: 0x%02h after writing 0x%02h, expected 0x%02h", name, v, wv, rv));
        r14_read(7'h06, e);
        if (emask != 8'h00) begin
            if ((e & emask) !== emask) fail($sformatf("%s: ERR 0x%02h without 0x%02h", name, e, emask));
            r14_write(7'h06, 8'hFF);
        end else if (e !== 8'h00) begin
            fail($sformatf("%s: unexpected ERR 0x%02h", name, e));
            r14_write(7'h06, 8'hFF);
        end
    endtask
`ifdef FIFO4
    localparam logic [7:0] FDEPTH = 8'd4;
`else
    localparam logic [7:0] FDEPTH = 8'd8;
`endif
    // J2 (audit round 7): a write of a guarded register while FLUSH waits for its tick (64 kHz) gets STATE_ERR and
    // leaves the register as it was; w1 unless the register holds it, else w2 (both legal, from gen_reg_tests.py)
    task automatic guard_one(input logic [6:0] a, input logic [7:0] w1, input logic [7:0] w2, input string name);
        logic [7:0] v0, w;
        r14_read(a, v0);
        w = (v0 === w1) ? w2 : w1;
        @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);                                 // FLUSH: pending until the next tick
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_now(8'h40, $sformatf("J2 STATE_ERR for %s written while a command is pending", name));
        rt_read_expect(a, v0, $sformatf("J2 %s not written while a command is pending", name));
    endtask
    task automatic expect_err_exact(input logic [7:0] val, input string name);
        logic [7:0] e;
        r14_read(7'h06, e);
        if (e !== val) fail($sformatf("%s: ERR 0x%02h, expected exactly 0x%02h", name, e, val));
        r14_write(7'h06, 8'hFF);
    endtask
    // J2 (audit round 8): an out-of-range write of a guarded register while FLUSH waits: exactly STATE_ERR (the guard
    // is decided before the range); nothing written
    task automatic guard_range(input logic [6:0] a, input logic [7:0] wbad, input string name);
        logic [7:0] v0;
        r14_read(a, v0);
        @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);
        r14_write(a, wbad);
        spi_tidle = 600.0;
        expect_err_exact(8'h40, $sformatf("J2 %s out of range while a command is pending", name));
        rt_read_expect(a, v0, $sformatf("J2 %s not written (out of range, a command pending)", name));
    endtask
    // ... and a locked test register written while FLUSH waits: exactly ADDR_ERR (the lock is decided before the guard)
    task automatic guard_locked(input logic [6:0] a, input logic [7:0] w, input string name);
        logic [7:0] v0;
        r14_read(a, v0);
        @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_exact(8'h08, $sformatf("J2 %s locked while a command is pending", name));
        rt_read_expect(a, v0, $sformatf("J2 %s not written (locked, a command pending)", name));
    endtask
    // J2 (audit round 13, auditor C): a register the guard does not cover, written while FLUSH waits for its tick
    // (64 kHz): exactly no flag (ERR 0x00) and written; restored after (only ALERT_MASK had been tried, and a guard
    // widened to IF_CFG and DEBUG, or to the test key, passed every test)
    task automatic free_wait_flush();
        @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);                                 // FLUSH: pending until the next tick
    endtask
    task automatic free_one(input logic [6:0] a, input logic [7:0] w, input string name);
        logic [7:0] v0;
        r14_read(a, v0);
        free_wait_flush();
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_exact(8'h00, $sformatf("J2 %s written while a command is pending (not guarded)", name));
        rt_read_expect(a, w, $sformatf("J2 %s written while a command is pending", name));
        r14_write(a, v0);
    endtask
    task automatic free_w1c(input logic [6:0] a, input logic [7:0] w, input string name);
        r14_write(7'h7F, 8'h00);                        // undefined: ADDR_ERR standing (audit round 28, auditor C: ERR
        free_wait_flush();                              // was 0 here, so a W1C enable shared with ERR passed)
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_exact(8'h08, $sformatf("J2 %s (W1C) written while a command is pending (not guarded): ADDR_ERR kept, no other flag", name));
    endtask
    task automatic free_err();                          // ERR: an ADDR_ERR made first, then cleared by its W1C
        r14_write(7'h7F, 8'h00);                        // undefined: ADDR_ERR
        free_wait_flush();
        r14_write(7'h06, 8'h08);
        spi_tidle = 600.0;
        expect_err_exact(8'h00, "J2 ERR's W1C while a command is pending (not guarded): ADDR_ERR cleared, no STATE_ERR");
    endtask
    task automatic free_key(input logic [7:0] w, input logic [7:0] e, input string name);
        free_wait_flush();
        r14_write(7'h11, w);
        spi_tidle = 600.0;
        expect_err_exact(e, $sformatf("J2 %s while a command is pending", name));
    endtask
    task automatic free_ifcfg();                        // IF_CFG: DRDY_MODE toggled, CRC_EN kept
        logic [7:0] v0;
        r14_read(7'h55, v0);
        free_wait_flush();
        r14_write(7'h55, v0 ^ 8'h02);
        spi_tidle = 600.0;
        expect_err_exact(8'h00, "J2 IF_CFG written while a command is pending (not guarded)");
        rt_read_expect(7'h55, v0 ^ 8'h02, "J2 IF_CFG written while a command is pending");
        r14_write(7'h55, v0);
    endtask
    // 2d and J2 (audit round 28, auditor C): the command codes and the key written as data. rt_write_exact: the
    // read-back and ERR exactly (ERR cleared when not 0); code_ifcfg: an IF_CFG write whose CRC_EN the BFM follows,
    // read back with DEBUG (a reserved bit loading RAW_EN), ERR exact, then IF_CFG 0x00 and CRC off again;
    // guard_code: a guarded register written while FLUSH waits: exactly STATE_ERR (no RESET_FLAG), not written
    task automatic rt_write_exact(input logic [6:0] a, input logic [7:0] wv, input logic [7:0] rv,
                                  input logic [7:0] eexp, input string name);
        logic [7:0] v;
        r14_write(a, wv);
        r14_read(a, v);
        if (v !== rv) fail($sformatf("%s: 0x%02h after writing 0x%02h, expected 0x%02h", name, v, wv, rv));
        expect_err_exact(eexp, name);
    endtask
    task automatic code_ifcfg(input logic [7:0] c, input logic [7:0] rv, input logic [7:0] dbg, input string name);
        logic [7:0] v;
        r14_write(7'h55, c);
        bfm_crc_en = c[0];
        r14_read(7'h55, v);
        if (v !== rv) fail($sformatf("%s: IF_CFG 0x%02h after writing 0x%02h, expected 0x%02h", name, v, c, rv));
        r14_read(7'h62, v);
        if (v !== dbg) fail($sformatf("%s: DEBUG 0x%02h after an IF_CFG write of 0x%02h, expected 0x%02h", name, v, c, dbg));
        expect_err_exact(8'h00, name);
        r14_write(7'h55, 8'h00);
        bfm_crc_en = 1'b0;
    endtask
    task automatic guard_code(input logic [6:0] a, input logic [7:0] w, input string name);
        logic [7:0] v0;
        r14_read(a, v0);
        @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
        r14_cmd(8'h55);
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_exact(8'h40, $sformatf("J2 %s: 0x%02h written while a command is pending (exactly STATE_ERR)", name, w));
        rt_read_expect(a, v0, $sformatf("J2 %s not written (0x%02h, a command pending)", name, w));
    endtask
    integer n_soft_req = 0, n_cmd_valid = 0, code_soft0 = 0, code_cmd0 = 0;
    always @(posedge dut.soft_req) n_soft_req = n_soft_req + 1;      // SOFT_RESET commits (and R's forced ones)
    always @(posedge dut.cmd_valid) n_cmd_valid = n_cmd_valid + 1;  // a command became pending
    task automatic code_begin();
        code_soft0 = n_soft_req;
        code_cmd0 = n_cmd_valid;
    endtask
    task automatic code_end(input string name);
        logic [7:0] st, s;
        r14_read(7'h03, st);
        r14_read(7'h04, s);
        if (n_soft_req != code_soft0 || n_cmd_valid != code_cmd0 || st[4] !== 1'b0 || s !== 8'h00)
            fail($sformatf("%s: %0d SOFT_RESET commits, %0d commands pending, CMD_PENDING %b, STATE %0d (expected none, none, 0, IDLE)",
                           name, n_soft_req - code_soft0, n_cmd_valid - code_cmd0, st[4], s));
        expect_err_exact(8'h00, name);
    endtask
    task automatic expect_err_now(input logic [7:0] mask, input string name);
        logic [7:0] e;
        r14_read(7'h06, e);
        if ((e & mask) !== mask) fail($sformatf("%s: ERR 0x%02h without 0x%02h", name, e, mask));
        r14_write(7'h06, 8'hFF);
    endtask
    task automatic expect_noerr(input string name);
        logic [7:0] e;
        r14_read(7'h06, e);
        if (e !== 8'h00) fail($sformatf("%s: unexpected ERR 0x%02h", name, e));
        if (e !== 8'h00) r14_write(7'h06, 8'hFF);
    endtask
    // ------------------------------------------------------------------ watchdog (every wait in the bench ends)
    string phase = "start";
    initial begin
        #(1200.0e6);
        fail($sformatf("watchdog: not finished after 1,200 ms of simulated time (phase %s)", phase));
        $display("FAIL: tb_top_r14");
        $finish;
    end

    task automatic wait_state(input logic [3:0] s, input real timeout_us, input string name);
        real t0;
        t0 = $realtime;
        while (dut.seq_state !== s && ($realtime - t0) < timeout_us * 1000.0) @(posedge MCLK);
        if (dut.seq_state !== s) fail($sformatf("%s: state %0d, expected %0d", name, dut.seq_state, s));
    endtask

    // ------------------------------------------------------------------ CODE stream and logs
    integer fcodes, flog, fsmp, ncodes, cidx;
    logic [4:0] codes [0:262143];
    initial begin
        fcodes = $fopen("build/top_r14.codes", "r");
        ncodes = 0;
        while (!$feof(fcodes) && ncodes < 262144) begin
            if ($fscanf(fcodes, "%d\n", codes[ncodes]) == 1) ncodes = ncodes + 1;
        end
        $fclose(fcodes);
        cidx = 0;
        flog = $fopen("build/top_r14_cic.log", "w");
        fsmp = $fopen("build/top_r14_samples.log", "w");
    end
    logic ovl_force = 1'b0;                       // J: drive the extreme code 31 (an ADC overload)
    logic log_on = 1'b1;                          // K: no logging once SEQ is forced
    logic cic_clear_taken = 1'b0;                 // the CIC's clear at this output (its arm input at step 3; audit
    always @(posedge MCLK) if (dut.u_cic.step[3]) cic_clear_taken <= dut.u_cic.arm;   // round 8: a SOFT_RESET can cancel it)
    always @(posedge MCLK) begin
        if (dut.cycle == 5'd1 && RESET_N) begin      // changes at e2, as eeg_adc_dig's code (audit round 9: at e17 a
            CODE <= ovl_force ? 5'd31 : codes[cidx % ncodes];   // block sampling at cycle 1 instead of 3 saw the same code)
            cidx <= cidx + 1;
        end
        if (log_on && dut.cic_en) $fdisplay(flog, "I %0d", CODE);
        if (log_on && dut.cic_stb) $fdisplay(flog, "O %0d %0d", dut.seq_cnt, cic_clear_taken);
        // every store with the flags of its cycle as the host reads them (SEQ, ERR, ALERT_MASK, DFLAG, ALERT_MASK_D):
        // check_top_r14 models the stored status byte (audit round 19, auditor C: ERR = ALERT at the store was
        // checked only with ADDR_ERR, and an ALERT without DFLAG in the samples passed all 16 groups)
        if (log_on && dut.push_ok) $fdisplay(flog, "S %0d %0d %0d %0d %0d", dut.seq_cnt, dut.u_regs.err,
                                             dut.u_regs.r_mask, dut.u_regs.dflag_byte, dut.u_regs.mask_d_byte);
    end

    // ------------------------------------------------------------------ analog control pins change only after a tick
    // 1 + 10 + 1 + 4 + 4 + 2 + 2 + 2 + 6 + 1 + 1 = 34 bits (checked against $bits of the concatenation at time 0)
    logic        prev_tick = 1'b0;
    logic [33:0] ana, ana_q;
    assign ana = {AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, TEST_CFG[5:0], CHOP_EN, DWA_EN};
    initial if ($bits({AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, TEST_CFG[5:0], CHOP_EN, DWA_EN})
                != $bits(ana)) begin
        $display("FAIL: the analog pin monitor is %0d bits wide for %0d bits of pins", $bits(ana),
                 $bits({AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, TEST_CFG[5:0], CHOP_EN, DWA_EN}));
        $finish;
    end
    integer ana_changes = 0, ana_afe_rst = 0;
    always @(posedge MCLK) begin
        #0.1;
        if (RESET_N && dut.rst_n && ana !== ana_q && !prev_tick)
            fail($sformatf("analog control pins changed without a tick: %h -> %h", ana_q, ana));
        if (ana !== ana_q) ana_changes = ana_changes + 1;
        if (ana[33] !== ana_q[33]) ana_afe_rst = ana_afe_rst + 1;
        ana_q     = ana;
        prev_tick = dut.tick;
    end

    // ------------------------------------------------------------------ no runt on a register-driven pin (NFR-06)
    // Each of these pins is one register (or one register's inverse): a value change at an edge is one event. Two
    // changes at one simulation time are an update at the edge taken back by the asynchronous reset right after it,
    // a zero-width runt in RTL and one of the reset tree's delay on the pad (phase R forces the cases)
    integer n_runt = 0;
    task automatic runt(input string pin);
        n_runt = n_runt + 1;
        fail($sformatf("runt on %s: two changes at one time", pin));
    endtask
    real rt_afe = -1.0, rt_ofm = -1.0, rt_ofs = -1.0, rt_ofen = -1.0, rt_cpf = -1.0, rt_ib = -1.0, rt_btp = -1.0,
         rt_btn = -1.0, rt_dbg = -1.0, rt_az = -1.0, rt_atpen = -1.0, rt_atpsel = -1.0, rt_chen = -1.0, rt_dwa = -1.0,
         rt_drdy = -1.0;
    always @(AFE_RST)        begin if ($realtime == rt_afe)    runt("AFE_RST");      rt_afe    = $realtime; end
    always @(OFM)            begin if ($realtime == rt_ofm)    runt("OFM");          rt_ofm    = $realtime; end
    always @(OFS)            begin if ($realtime == rt_ofs)    runt("OFS");          rt_ofs    = $realtime; end
    always @(OFEN)           begin if ($realtime == rt_ofen)   runt("OFEN");         rt_ofen   = $realtime; end
    always @(CPF_TRIM)       begin if ($realtime == rt_cpf)    runt("CPF_TRIM");     rt_cpf    = $realtime; end
    always @(AFE_IBIAS)      begin if ($realtime == rt_ib)     runt("AFE_IBIAS");    rt_ib     = $realtime; end
    always @(BTRIM_P)        begin if ($realtime == rt_btp)    runt("BTRIM_P");      rt_btp    = $realtime; end
    always @(BTRIM_N)        begin if ($realtime == rt_btn)    runt("BTRIM_N");      rt_btn    = $realtime; end
    always @(TEST_CFG[7:6])  begin if ($realtime == rt_dbg)    runt("TEST_CFG[7:6]"); rt_dbg   = $realtime; end
    always @(TEST_CFG[5])    begin if ($realtime == rt_az)     runt("TEST_CFG[5]");  rt_az     = $realtime; end
    always @(TEST_CFG[4])    begin if ($realtime == rt_atpen)  runt("TEST_CFG[4]");  rt_atpen  = $realtime; end
    always @(TEST_CFG[3:0])  begin if ($realtime == rt_atpsel) runt("TEST_CFG[3:0]"); rt_atpsel = $realtime; end
    always @(CHOP_EN)        begin if ($realtime == rt_chen)   runt("CHOP_EN");      rt_chen   = $realtime; end
    always @(DWA_EN)         begin if ($realtime == rt_dwa)    runt("DWA_EN");       rt_dwa    = $realtime; end
    always @(DRDY_N)         begin if ($realtime == rt_drdy)   runt("DRDY_N");       rt_drdy   = $realtime; end

    // ------------------------------------------------------------------ every applied pin follows its active copy
    // At every MCLK in every state (audit round 4: CHOP_EN was observed only in IDLE and RUN, so a copy that dropped it
    // in PULSE passed every test): the applied pins are regmap.pins_from_active of the active copies (OFM and OFS 0 in
    // range 0, OFEN = exp_ofen (generated from regmap.ofen_of_range), CHOP_EN = not CHOP_STOP). The active copies are
    // the register block's (read back over SPI at address + 0x10 by the generated register tests)
    integer n_pinrule = 0;
    always @(posedge MCLK) begin
        #0.1;
        if (RESET_N === 1'b1 &&
            (OFM !== ((dut.u_regs.a_range == 3'd0) ? 10'd0 : dut.u_regs.a_m) ||
             OFS !== ((dut.u_regs.a_range == 3'd0) ? 1'b0 : dut.u_regs.a_sign) ||
             OFEN !== exp_ofen(dut.u_regs.a_range) || CPF_TRIM !== dut.u_regs.a_cpf ||
             AFE_IBIAS !== dut.u_regs.a_ibias || BTRIM_P !== dut.u_regs.a_bp || BTRIM_N !== dut.u_regs.a_bn ||
             DWA_EN !== dut.u_regs.a_dwa || CHOP_EN !== ~dut.u_regs.a_cstop ||
             TEST_CFG[5:0] !== {dut.u_regs.a_azero, dut.u_regs.a_atpen, dut.u_regs.a_atpsel})) begin
            n_pinrule = n_pinrule + 1;
            if (n_pinrule <= 5)
                fail($sformatf("applied pins differ from regmap.pins_from_active of the active copies in state %0d: OFM %0d OFS %b OFEN %b CPF %0d IB %0d BT %0d/%0d DWA %b CHOP_EN %b TEST_CFG %02h",
                               dut.seq_state, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, DWA_EN, CHOP_EN,
                               TEST_CFG));
        end
    end

    // ------------------------------------------------------------------ CHOP_OUT == CHOP (CHOP_DLY fixed to 0)
    // audit round 5: a top that passed a nonzero delay to the clock generator passed every test (REG-06, section 4.10)
    integer n_chopout = 0;
    always @(posedge MCLK) begin
        #0.1;
        if (RESET_N === 1'b1 && CHOP_OUT !== CHOP) n_chopout = n_chopout + 1;
    end
    // T7: a command written in the cycle the tick acknowledges the pending one; T3: when STATE_ERR is set
    integer n_ack_commit = 0;
    always @(posedge MCLK)
        if (dut.reg_we === 1'b1 && dut.reg_addr === 7'h10 && dut.cmd_ack === 1'b1) n_ack_commit = n_ack_commit + 1;
    real t_serr = 0.0;
    always @(posedge dut.u_regs.err[6]) t_serr = $realtime;

    // ------------------------------------------------------------------ AFE_RST pin edges
    real t_afe_fall = 0.0, t_afe_rise = 0.0;
    integer afe_falls = 0, afe_rises = 0;
    always @(negedge AFE_RST) begin t_afe_fall = $realtime; afe_falls = afe_falls + 1; end
    always @(posedge AFE_RST) begin t_afe_rise = $realtime; afe_rises = afe_rises + 1; end
    real t_chop_rise = 0.0;
    always @(posedge CHOP) t_chop_rise = $realtime;
    real t_cpf = 0.0;                             // J4: the time of the last CPF_TRIM pin change
    always @(CPF_TRIM) t_cpf = $realtime;
    // every AFE_RST edge: one MCLK after the tick, TICK_FRAME * 32 + TICK_CYCLE + 1 MCLK after a rising CHOP edge (57 at
    // 128 kHz, 121 at 64 kHz; the constants generated from fsm_spec.TIMING, which the analog decks also use: audit
    // round 13, only 128 kHz and a hand-written 57 had been checked)
    real afe_edge_exp;
    always @(negedge AFE_RST or posedge AFE_RST) begin
        afe_edge_exp = dut.u_clkgen.fast ? 32.0 * TICK_FRAME_128K + TICK_CYCLE + 1.0 : 32.0 * TICK_FRAME_64K + TICK_CYCLE + 1.0;
        // (the rate the clock generator runs at: a CHOP_FAST change waits for its 512-MCLK wrap; audit round 14)
        if (RESET_N && dut.rst_n &&
            ((($realtime - t_chop_rise) / TMCLK) < afe_edge_exp - 0.5 || (($realtime - t_chop_rise) / TMCLK) > afe_edge_exp + 0.5))
            fail($sformatf("AFE_RST edge %0.2f MCLK after the CHOP rising edge (expected %0.0f)",
                           ($realtime - t_chop_rise) / TMCLK, afe_edge_exp));
    end

    logic afe_rise_fast = 1'b1, afe_rise_act = 1'b1;   // V13: at each AFE_RST rise, the rate the clock generator runs
    always @(posedge AFE_RST) begin afe_rise_fast = dut.u_clkgen.fast; afe_rise_act = dut.a_chop_fast; end  // and the copy's
    integer n_coinc13 = 0;                        // T13: sample copies taken in the cycle of a store into the FIFO
    always @(posedge MCLK) if (dut.smp_snap === 1'b1 && dut.push_ok === 1'b1) n_coinc13 = n_coinc13 + 1;

    // ------------------------------------------------------------------ G2 and I: event times
    real t_snap = 0.0, t_flush = 0.0, t_store = 0.0, t_csr = 0.0;
    logic soft_pend = 1'b0;
    always @(posedge MCLK) begin
        if (dut.smp_snap)  t_snap  = $realtime;
        if (dut.seq_flush) t_flush = $realtime;
        if (dut.push_ok)   t_store = $realtime;
        if (dut.soft_req)  soft_pend = dut.cmd_valid;
    end
    always @(posedge CS_N) t_csr = $realtime;
    real t_drdy_rise = 0.0;                       // M5: the DRDY_N release
    always @(posedge DRDY_N) t_drdy_rise = $realtime;

    // ------------------------------------------------------------------ state entry times, CHOP1, ADC_RST_N
    real t_state [0:15];
    initial for (int i = 0; i < 16; i++) t_state[i] = 0.0;
    always @(dut.seq_state) t_state[dut.seq_state] = $realtime;
    integer mclk_count = 0;
    always @(posedge MCLK) mclk_count = mclk_count + 1;
    real t_chop1_edge = 0.0;
    integer n_chop1_edge = 0;                     // the MCLK count at the last CHOP1 edge (exact over long spans)
    always @(CHOP1) begin t_chop1_edge = $realtime; n_chop1_edge = mclk_count; end
    always @(negedge ADC_RST_N)                   // the ADC's reset follows RESET_N only (RST-02), never SOFT_RESET
        if (RESET_N === 1'b1) fail("ADC_RST_N fell while RESET_N is high");

    // ------------------------------------------------------------------ VER-09 end to end: the sequencer's events
    // the same trace format as tb_seq (check_seq_trace.py): before each edge the state, the pending command, the
    // timer and the conditions with the actions; after it the next state and the timer. The pending command, cfg_ok,
    // nr_ok, the timer values (eeg_regs' registers r_tw .. r_trst: audit round 33, auditor C, as an eeg_regs whose
    // t_warm port was 7 bits passed all 16 groups) and the CIC's valid (eeg_cic3) are taken at their sources, not at eeg_seq's
    // ports: a wrong connection into the sequencer is then a mismatch (audit round 32, auditor C: a sequencer taking
    // out_valid as cic_valid & ~ovl_now was replayed as the specification's input)
    integer fseq, seq_frames = 0;
    logic       q_tick, q_out, q_fs, q_cv, q_cfg, q_nr, q_valid, q_te0, q_rst = 1'b1, q_inrst = 1'b1;
    logic [3:0] q_st;
    logic [7:0] q_cc, q_acts, q_tw, q_te, q_tr, q_tp, q_tq;
    logic [17:0] q_tb;
    initial fseq = $fopen("build/top_seq_trace.txt", "w");
    always @(negedge MCLK) begin
        q_rst  = dut.u_seq.rst_n;
        q_tick = dut.u_seq.tick;       q_out = dut.u_seq.out_stb;     q_fs = dut.u_seq.frame_stb;
        q_st   = dut.u_seq.state;      q_cv  = dut.u_regs.cmd_valid;  q_cc = dut.u_regs.cmd_code;
        q_cfg  = dut.u_regs.cfg_ok;    q_nr  = dut.u_regs.nr_ok;      q_valid = dut.u_cic.dout_valid;
        q_tb   = dut.u_seq.timer;      q_te0 = (dut.u_regs.r_te == 8'd0);
        q_acts = {dut.u_seq.apply, dut.u_seq.flush, dut.u_seq.store, dut.u_seq.mark, dut.u_seq.state_err,
                  dut.u_seq.cfg_err, dut.u_seq.cic_arm && dut.u_seq.out_stb, dut.u_seq.a_restart};
        q_tw = dut.u_regs.r_tw;  q_te = dut.u_regs.r_te;  q_tr = dut.u_regs.r_trec;  q_tp = dut.u_regs.r_tpre;
        q_tq = dut.u_regs.r_trst;
    end
    always @(posedge MCLK) begin
        #0.2;
        if (!q_rst) begin
            if (!q_inrst) $fdisplay(fseq, "R");
            q_inrst = 1'b1;
            seq_frames = 0;
        end else if (q_inrst) begin
            q_inrst = 1'b0;                           // the first edge after the release: IDLE, timer 0
        end else if (q_tick || q_out) begin
            $fdisplay(fseq, "%s %0d %0d %0d %0d %0d %0d %0d %0d %0d %b %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                      q_tick ? "T" : "O", q_st, q_cv, q_cc, (q_tb == 18'd0), q_cfg, q_nr, q_te0, q_valid,
                      dut.u_seq.state, q_acts, q_tb, dut.u_seq.timer, seq_frames, q_fs, q_tw, q_te, q_tr, q_tp, q_tq);
            seq_frames = 0;
        end else if (q_fs) begin
            seq_frames = seq_frames + 1;
        end
    end

    // ------------------------------------------------------------------ FILL: ALIGN's clear and FILL's first store
    // (audit round 33, auditor C: a CIC that took ALIGN's clear only at an output that was itself valid passed all 16
    // groups, as no group cleared a settling filter, V's commands in FILL never ran on to RUN, and the golden log takes
    // the CIC's arm input): at every ALIGN output time the CIC's registers are zero (the clear taken), and FILL's store
    // (the sequencer's store, fsm_spec FILL/OUT [valid]) is the third output after it (SEQ-04, SEQ-15). n_align_early
    // counts the clears at an output the CIC had not yet made valid (a settling filter cleared again; AB makes them)
    integer n_since_clr = -1, n_align_clr = 0, n_align_early = 0, n_fill_store = 0, n_fill_bad = 0;
    always @(negedge MCLK) begin
        if (dut.rst_n !== 1'b1) begin
            n_since_clr = -1;
        end else if (dut.cic_stb === 1'b1) begin
            if (dut.seq_state === 4'd4) begin                       // ALIGN's output time: the clear
                n_align_clr++;
                if (dut.u_cic.dout_valid !== 1'b1) n_align_early++;
                if (dut.u_cic.nstb !== 0 || dut.u_cic.i1 !== 0 || dut.u_cic.i2 !== 0 || dut.u_cic.i3 !== 0 ||
                    dut.u_cic.d1 !== 0 || dut.u_cic.d2 !== 0 || dut.u_cic.d3 !== 0) begin
                    n_fill_bad++;
                    if (n_fill_bad < 5) fail($sformatf("ALIGN's output time (SEQ %0d): the CIC not cleared (nstb %0d)",
                                                       dut.seq_cnt, dut.u_cic.nstb));
                end
                n_since_clr = 0;
            end else if (n_since_clr >= 0) begin
                n_since_clr++;
            end
            if (dut.seq_store === 1'b1 && dut.seq_state === 4'd5) begin     // FILL's store: on to RUN
                n_fill_store++;
                if (n_since_clr != 3) begin
                    n_fill_bad++;
                    if (n_fill_bad < 5) fail($sformatf("FILL stored SEQ %0d, output %0d after ALIGN's clear (expected the third)",
                                                       dut.seq_cnt, n_since_clr));
                end
                n_since_clr = -1;
            end
        end
    end

    // ------------------------------------------------------------------ the frame strobes at the pins
    integer fcyc = -1, nstrobe_err = 0;
    always @(posedge MCLK) begin
        #0.2;
        if (!RESET_N) begin
            fcyc = -1;
        end else begin
            if (CMP_STROBE === 1'b1) begin
                if (fcyc != -1 && fcyc != 31) begin nstrobe_err++; if (nstrobe_err < 5) fail($sformatf("CMP_STROBE after %0d MCLK, expected 32", fcyc + 1)); end
                fcyc = 0;
            end else if (fcyc >= 0) begin
                fcyc = fcyc + 1;
            end
            if (fcyc >= 0 && (TH_CAPTURE !== (fcyc == 1) || DAC_LOAD !== (fcyc == 2) || DAC_CLK !== (fcyc == 4) || fcyc > 31)) begin
                nstrobe_err++;
                if (nstrobe_err < 5) fail($sformatf("frame strobes at cycle %0d: TH_CAPTURE %b DAC_LOAD %b DAC_CLK %b", fcyc, TH_CAPTURE, DAC_LOAD, DAC_CLK));
            end
        end
    end
    integer n_drdy_fall = 0;
    integer n_y_slip_smp = 0;                            // Y1: a slipped FIFO_LEVEL read, then a sample read (round 23)
    always @(negedge DRDY_N) n_drdy_fall = n_drdy_fall + 1;
    // DRDY_N in pulse mode (audit round 22, auditor C: DAT-04 was checked on three RUN stores of G3 only, and RTL copies
    // with no pulse for FILL's store (the first sample after START and APPLY) or with the pulse ended when the FIFO
    // empties passed all 16 groups): while DRDY_MODE is 1, every store makes DRDY_N fall at the next MCLK edge (2 MCLK
    // after the store cycle; audit round 26, auditor C: "1 to 2 MCLK later" let a pulse one MCLK late pass) and stay low
    // exactly 128 MCLK unless RESET_N, a SOFT_RESET or level mode cuts it, and DRDY_N never falls without a store; the
    // stores in FILL are counted (exercised)
    real    pm_t_push = -1.0e9, pm_t_fall = -1.0;
    bit     pm_owed = 1'b0, pm_cut = 1'b0;
    integer n_pm_pulses = 0, n_pm_fill = 0, n_pm_bad = 0;
    always @(posedge MCLK) begin                         // at the edge, before its updates
        if (dut.rst_n !== 1'b1 || dut.soft_req === 1'b1 || dut.drdy_mode !== 1'b1) begin
            pm_owed = 1'b0;
            pm_cut  = 1'b1;
        end else if (dut.push_ok === 1'b1) begin
            pm_t_push = $realtime;
            pm_owed   = 1'b1;
            if (dut.seq_state === 4'd5) n_pm_fill = n_pm_fill + 1;      // FILL's store: the first sample of a RUN
        end else if (pm_owed && $realtime - pm_t_push > 1.5 * TMCLK) begin
            n_pm_bad = n_pm_bad + 1;
            if (n_pm_bad <= 3) fail("DRDY_N pulse mode: a store without a DRDY_N fall at the next MCLK edge (DAT-04)");
            pm_owed = 1'b0;
        end
    end
    always @(negedge DRDY_N) if (dut.drdy_mode === 1'b1 && dut.rst_n === 1'b1) begin
        if (!pm_owed) begin
            n_pm_bad = n_pm_bad + 1;
            if (n_pm_bad <= 3) fail("DRDY_N pulse mode: DRDY_N fell without a store");
        end else if ($realtime - pm_t_push < 0.5 * TMCLK) begin          // at the store's own edge (audit round 26)
            n_pm_bad = n_pm_bad + 1;
            if (n_pm_bad <= 3) fail("DRDY_N pulse mode: DRDY_N fell at the store's own MCLK edge, expected the next one");
        end
        pm_owed     = 1'b0;
        pm_t_fall   = $realtime;
        pm_cut      = 1'b0;
        n_pm_pulses = n_pm_pulses + 1;
    end
    always @(posedge DRDY_N) begin
        if (pm_t_fall >= 0.0 && !pm_cut && dut.drdy_mode === 1'b1 && dut.rst_n === 1'b1 &&
                (($realtime - pm_t_fall) / TMCLK < 127.5 || ($realtime - pm_t_fall) / TMCLK > 128.5)) begin
            n_pm_bad = n_pm_bad + 1;
            if (n_pm_bad <= 3) fail($sformatf("DRDY_N pulse mode: a pulse of %0.2f MCLK, expected 128 whatever the FIFO holds (DAT-04)",
                                              ($realtime - pm_t_fall) / TMCLK));
        end
        pm_t_fall = -1.0;
    end
    // DRDY_N in level mode (audit round 25, auditor C: only pulse mode was monitored, and an RTL copy whose DRDY_N fell
    // only at frame cycle 0, up to 23 MCLK late with a sample stored, passed all 16 groups): while DRDY_MODE is 0, after
    // every MCLK edge DRDY_N is the negation of the FIFO's "not empty" before that edge (a register, spec 3.3), high
    // after the commit edge of a SOFT_RESET; a store while DRDY_N is high makes it fall at the next edge (requirements
    // 5.4 step 5 (ii): 2 MCLK after the store cycle, as in pulse mode); every edge is checked and the falls counted
    bit     lm_armed = 1'b0, lm_exp = 1'b1, lm_due = 1'b0, lm_due_now = 1'b0;
    integer n_lm_checks = 0, n_lm_first = 0, n_lm_falls = 0, n_lm_bad = 0;
    always @(posedge MCLK) begin                         // at the edge, before its updates: what DRDY_N must become
        lm_armed   = dut.rst_n === 1'b1 && dut.drdy_mode === 1'b0;
        lm_exp     = dut.soft_req === 1'b1 || dut.fifo_nonempty !== 1'b1;
        lm_due_now = lm_due && lm_armed && dut.soft_req !== 1'b1;     // a store at the previous edge, not cut
        lm_due     = 1'b0;
        if (lm_armed && dut.soft_req !== 1'b1 && dut.push_ok === 1'b1 && DRDY_N === 1'b1) begin
            lm_due     = 1'b1;
            n_lm_first = n_lm_first + 1;
        end
    end
    always @(negedge MCLK) if (lm_armed && dut.rst_n === 1'b1) begin
        n_lm_checks = n_lm_checks + 1;
        if (DRDY_N !== lm_exp) begin
            n_lm_bad = n_lm_bad + 1;
            if (n_lm_bad <= 3) fail($sformatf("DRDY_N level mode: %b after the MCLK edge, expected %b (FIFO not empty %b before it; DAT-04)",
                                              DRDY_N, lm_exp, !lm_exp));
        end
        if (lm_due_now) begin
            if (DRDY_N !== 1'b0) begin
                n_lm_bad = n_lm_bad + 1;
                if (n_lm_bad <= 3) fail("DRDY_N level mode: a store with DRDY_N high, and no fall at the next MCLK edge");
            end else
                n_lm_falls = n_lm_falls + 1;
        end
    end
    integer n_rawclk = 0;
    always @(posedge RAW_CLK) n_rawclk = n_rawclk + 1;

    // ------------------------------------------------------------------ R: SOFT_RESET committed in this cycle
    // called 1 ns after a rising MCLK edge (before the falling edge where the sequencer trace samples its inputs):
    // soft_req (the register block's commit of 0xA5) is forced high until just after the next rising edge, where
    // rst_n falls
    logic soft_forced = 1'b0;                       // R forces soft_req (the monitor below skips those cycles)
    task automatic soft_now();
        soft_forced = 1'b1;
        force dut.soft_req = 1'b1;
        @(posedge MCLK); #1;
        release dut.soft_req;
        soft_forced = 1'b0;
        repeat (8) @(posedge MCLK);                     // the soft reset (rst_n low for 5 MCLK) is over
    endtask

    // ------------------------------------------------------------------ T1: an ERR bit sets ALERT, its clear removes it
    task automatic alert_bit(input logic [7:0] bitmask, input string name);
        logic [7:0] st, e;
        r14_read(7'h03, st);
        r14_read(7'h06, e);
        if (st[5] !== 1'b1 || (e & bitmask) !== bitmask)
            fail($sformatf("T1 %s: STATUS 0x%02h ERR 0x%02h, expected ALERT with 0x%02h", name, st, e, bitmask));
        r14_write(7'h08, ~bitmask);                     // this flag masked: no ALERT (audit round 6)
        r14_read(7'h03, st);
        if (st[5] !== 1'b0) fail($sformatf("T1 %s: STATUS 0x%02h, ALERT with its mask bit 0", name, st));
        r14_write(7'h08, 8'hFF);
        r14_write(7'h06, 8'hFF);
        r14_read(7'h03, st);
        if (st[5] !== 1'b0) fail($sformatf("T1 %s: STATUS 0x%02h, ALERT still set after clearing ERR", name, st));
    endtask

    // ------------------------------------------------------------------ S: the CRC-mode probe (requirements step 9)
    // a 3-byte read of IF_CFG (header 0xD5, MOSI 0x00): with CRC on it is the read with its CRC (byte 2 = CRC-8 of the
    // header and byte 1); with CRC off a burst (byte 2 = the undefined 0x56 = 0x00, while CRC-8 of 0xD5 and any byte is
    // never 0). Legal, no error, in both modes.
    task automatic soft_reset_probe(output bit crc_on, input string name);
        bit known;
        probe_hdr(8'hD5, crc_on, known);
        if (!known) fail($sformatf("%s: the probe read %02h %02h (neither mode)", name, spi_rx[1], spi_rx[2]));
    endtask
    // the probe as the host judges it (it means the header 0xD5); hdr is what reaches the chip (a bit error)
    task automatic probe_hdr(input logic [7:0] hdr, output bit crc_on, output bit known);
        logic [7:0] c;
        bit save;
        save = bfm_crc_en;
        bfm_crc_en = 1'b0;                              // the raw 3-byte frame, checked here
        spi_tx[0] = hdr; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
        spi_xfer(3, 0);
        bfm_crc_en = save;
        c = tb_crc8_update(tb_crc8_update(8'h00, 8'hD5), spi_rx[1]);
        known = 1'b1;
        if (spi_rx[2] === c && spi_rx[1][0] === 1'b1)      crc_on = 1'b1;
        else if (spi_rx[2] === 8'h00 && spi_rx[1][0] === 1'b0) crc_on = 1'b0;
        else begin known = 1'b0; crc_on = 1'b0; end
    endtask
    // requirements 5.4 step 9 as the host runs it: probe, ERR in the probed mode, and while RESET_FLAG is 0: clear
    // ERR and send SOFT_RESET again in that mode, then repeat the whole check (audit round 5). bad_hdr: the header
    // of the first probe as it reaches the chip. Returns the number of checks (0 if it did not converge in 6)
    task automatic host_soft_reset_check(input logic [7:0] bad_hdr, output integer rounds);
        bit crc_on, known, done;
        logic [7:0] e;
        integer n;
        done = 1'b0; n = 0;
        while (!done && n < 6) begin
            n = n + 1;
            #(1000.0);                                  // CS_N high for 1 us after a SOFT_RESET
            probe_hdr((n == 1) ? bad_hdr : 8'hD5, crc_on, known);
            if (known) begin
                bfm_crc_en = crc_on;
                r14_read(7'h06, e);
                if (e[0] === 1'b1) done = 1'b1;
                else begin
                    r14_write(7'h06, e);
                    r14_cmd(8'hA5);
                end
            end
        end
        rounds = done ? n : 0;
    endtask

    // ------------------------------------------------------------------ N5: one generated nr_ok case (pin_tests.svh)
    task automatic nr_base(input logic [7:0] s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62);
        logic [6:0] A [0:11];
        logic [7:0] sh [0:11];
        A = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h60, 7'h61, 7'h62};
        sh = '{s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62};
        r14_write(7'h11, 8'h3C);
        for (int i = 0; i < 12; i++) r14_write(A[i], sh[i]);
        r14_write(7'h11, 8'h00);
        r14_cmd(8'h33);                                 // APPLY (with its pulse) to the base
        wait_state(4'd7, 50.0, "N5 PRE (base)");
        wait_state(4'd6, 6000.0, "N5 RUN (base)");
        expect_noerr("N5 base");
    endtask
    task automatic nr_case(input logic [7:0] s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62,
                           input logic ok, input logic [9:0] e_ofm, input logic e_ofs, input logic [3:0] e_ofen,
                           input logic [3:0] e_cpf, input logic [1:0] e_ib, input logic e_dwa, input logic e_chen,
                           input logic [7:0] e_tcfg, input string name);
        logic [6:0] A [0:11];
        logic [7:0] sh [0:11];
        logic [7:0] e;
        A = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h60, 7'h61, 7'h62};
        sh = '{s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62};
        r14_write(7'h11, 8'h3C);
        for (int i = 0; i < 12; i++) r14_write(A[i], sh[i]);
        r14_write(7'h11, 8'h00);
        r14_cmd(8'h44);                                 // APPLY_NR in RUN
        repeat (700) @(posedge MCLK);
        r14_read(7'h06, e);
        if (ok && e !== 8'h00) fail($sformatf("%s: ERR 0x%02h, expected none (accepted)", name, e));
        if (!ok && e !== 8'h20) fail($sformatf("%s: ERR 0x%02h, expected CFG_ERR (rejected)", name, e));
        if (e !== 8'h00) r14_write(7'h06, 8'hFF);
        if (dut.seq_state !== 4'd6) fail($sformatf("%s: state %0d, expected RUN (no pulse)", name, dut.seq_state));
        if (OFM !== e_ofm || OFS !== e_ofs || OFEN !== e_ofen || CPF_TRIM !== e_cpf || AFE_IBIAS !== e_ib ||
            DWA_EN !== e_dwa || CHOP_EN !== e_chen || TEST_CFG !== e_tcfg)
            fail($sformatf("%s: pins OFM %0d OFS %b OFEN %b CPF %0d IBIAS %0d DWA %b CHOP_EN %b TEST_CFG %02h; expected %0d %b %b %0d %0d %b %b %02h",
                           name, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, DWA_EN, CHOP_EN, TEST_CFG,
                           e_ofm, e_ofs, e_ofen, e_cpf, e_ib, e_dwa, e_chen, e_tcfg));
    endtask

    // ------------------------------------------------------------------ N: one generated pin case (pin_tests.svh)
    task automatic pin_case(input logic [7:0] s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62,
                            input logic ok, input logic [9:0] e_ofm, input logic e_ofs,
                            input logic [3:0] e_ofen, input logic [1:0] e_ib, input logic [3:0] e_cpf,
                            input logic [1:0] e_bp, input logic [1:0] e_bn, input logic e_dwa, input logic e_chen,
                            input logic [7:0] e_tcfg, input integer e_bw, input logic e_bheld, input integer e_chalf,
                            input integer e_c1half, input logic meas_c1, input string name);
        logic [7:0] v, e;
        logic [6:0] A [0:11];
        logic [7:0] sh [0:11];
        real t0, t1, w;
        A = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h60, 7'h61, 7'h62};
        sh = '{s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61, s62};
        r14_write(7'h11, 8'h3C);                        // TEST_KEY: the test registers
        for (int i = 0; i < 12; i++) r14_write(A[i], sh[i]);
        r14_write(7'h11, 8'h00);
        expect_noerr($sformatf("%s: the writes", name));
        r14_cmd(8'h33);                                 // APPLY in IDLE: no pulse
        repeat (700) @(posedge MCLK);                   // the next tick (at most 15.6 us)
        r14_read(7'h06, e);
        if (ok && e !== 8'h00) fail($sformatf("%s: ERR 0x%02h after APPLY", name, e));
        if (!ok && e !== 8'h20) fail($sformatf("%s: ERR 0x%02h, expected CFG_ERR only", name, e));
        if (e !== 8'h00) r14_write(7'h06, 8'hFF);
        if (OFM !== e_ofm || OFS !== e_ofs || OFEN !== e_ofen || AFE_IBIAS !== e_ib || CPF_TRIM !== e_cpf ||
            BTRIM_P !== e_bp || BTRIM_N !== e_bn || DWA_EN !== e_dwa || CHOP_EN !== e_chen || TEST_CFG !== e_tcfg)
            fail($sformatf("%s: pins OFM %0d OFS %b OFEN %b IBIAS %0d CPF %0d BTRIM P %0d N %0d DWA %b CHOP_EN %b TEST_CFG %02h; expected %0d %b %b %0d %0d %0d %0d %b %b %02h",
                           name, OFM, OFS, OFEN, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, DWA_EN, CHOP_EN, TEST_CFG,
                           e_ofm, e_ofs, e_ofen, e_ib, e_cpf, e_bp, e_bn, e_dwa, e_chen, e_tcfg));
        if (ok)                                         // the active copies (addr + 0x10) equal the shadows
            for (int i = 0; i < 11; i++) begin
                r14_read(A[i] + 7'h10, v);
                if (v !== sh[i]) fail($sformatf("%s: active 0x%02h = 0x%02h, shadow 0x%02h", name, A[i] + 7'h10, v, sh[i]));
            end
        repeat (1100) @(posedge MCLK);                  // a new chopper rate applies at the 512-MCLK wrap
        measure_chop(e_bw, e_bheld, e_chalf, e_c1half, meas_c1, name);
        // shadow writes alone (no APPLY) must leave the chopper's rate, CHOP1 and CHOP_BLANK: other rate, CHOP1 rate,
        // length and range in the shadows, then the same measurements
        r14_write(7'h26, sh[6] ^ 8'h01);
        r14_write(7'h27, (sh[7] & 8'hF8) | 8'(((sh[7] & 8'h07) + 1) % 6));
        r14_write(7'h28, 8'(((sh[8] & 8'h0F) % 15) + 1));
        r14_write(7'h22, (sh[2] & 8'hF8) | 8'(((sh[2] & 8'h07) + 1) % 5));
        repeat (1100) @(posedge MCLK);
        measure_chop(e_bw, e_bheld, e_chalf, e_c1half, meas_c1, {name, " after shadow writes alone"});
        r14_write(7'h22, sh[2]);                        // the case's shadows again (a later START applies them)
        r14_write(7'h26, sh[6]);
        r14_write(7'h27, sh[7]);
        r14_write(7'h28, sh[8]);
    endtask

    task automatic measure_chop(input integer e_bw, input logic e_bheld, input integer e_chalf, input integer e_c1half,
                                input logic meas_c1, input string name);
        real t0, t1, w;
        // CHOP_BLANK: held by ADC_ZERO, or high for its length + 1 MCLK at each output-chopper edge
        t0 = $realtime;
        if (e_bheld) begin
            repeat (2 * e_chalf) begin
                @(posedge MCLK);
                if (CHOP_BLANK !== 1'b1) begin fail($sformatf("%s: CHOP_BLANK not held", name)); break; end
            end
        end else begin
            while (CHOP_BLANK !== 1'b0 && $realtime - t0 < 4000.0 * TMCLK) @(posedge MCLK);
            while (CHOP_BLANK !== 1'b1 && $realtime - t0 < 4000.0 * TMCLK) @(posedge MCLK);
            t1 = $realtime;
            while (CHOP_BLANK !== 1'b0 && $realtime - t1 < 100.0 * TMCLK) @(posedge MCLK);
            w = ($realtime - t1) / TMCLK;
            if (w < e_bw - 0.5 || w > e_bw + 0.5) fail($sformatf("%s: CHOP_BLANK high %0.1f MCLK, expected %0d", name, w, e_bw));
        end
        // the chopper's half period
        t0 = $realtime;
        @(CHOP);
        t1 = $realtime;
        @(CHOP);
        w = ($realtime - t1) / TMCLK;
        if (w < e_chalf - 0.5 || w > e_chalf + 0.5) fail($sformatf("%s: CHOP half period %0.1f MCLK, expected %0d", name, w, e_chalf));
        // CHOP1 (once per rate): its new rate applies at the next 1 ms boundary
        if (meas_c1) begin
            repeat (34000) @(posedge MCLK);
            if (e_c1half == 0) begin
                t0 = t_chop1_edge;
                repeat (34000) @(posedge MCLK);
                if (CHOP1 !== 1'b1 || t_chop1_edge != t0) fail($sformatf("%s: CHOP1 not off (held 1)", name));
            end else begin
                t0 = $realtime;
                while (t_chop1_edge < t0 && $realtime - t0 < 3.0 * e_c1half * TMCLK) @(posedge MCLK);
                t1 = t_chop1_edge;
                while (t_chop1_edge == t1 && $realtime - t1 < 3.0 * e_c1half * TMCLK) @(posedge MCLK);
                w = (t_chop1_edge - t1) / TMCLK;
                if (w < e_c1half - 0.5 || w > e_c1half + 0.5)
                    fail($sformatf("%s: CHOP1 half period %0.1f MCLK, expected %0d", name, w, e_c1half));
            end
        end
    endtask

    // N: an overload of about 20 us, then the flag must be as expected (DFLAG.OVL only in FILL and RUN)
    task automatic ovl_burst(input logic expect_flag, input string name);
        logic [7:0] f;
        r14_write(7'h07, 8'hFF);
        ovl_force = 1'b1;
        repeat (20 * 32) @(posedge MCLK);
        ovl_force = 1'b0;
        repeat (40 * 32) @(posedge MCLK);
        r14_read(7'h07, f);
        if (f[1] !== expect_flag) fail($sformatf("%s: DFLAG.OVL %b after an overload, expected %b", name, f[1], expect_flag));
        r14_write(7'h07, 8'hFF);
    endtask


    logic [7:0] bad_codes [0:5] = '{8'h91, 8'hA2, 8'hB3, 8'hC4, 8'hD5, 8'h25};   // A: whole-byte codes (round 16)
    // ------------------------------------------------------------------ STATUS against what the pins and state show
    task automatic check_status(input logic [7:0] exp, input logic [7:0] mask, input string name);
        logic [7:0] st;
        r14_read(7'h03, st);
        if ((st & mask) !== (exp & mask))
            fail($sformatf("%s: STATUS 0x%02h, expected 0x%02h under mask 0x%02h", name, st, exp, mask));
    endtask

    // ------------------------------------------------------------------ samples
    integer nsamples = 0;
    logic [15:0] last_seq;
    bit          have_last = 1'b0;
    // nchg: the first nchg samples must carry CHANGED and the others not; -1: not checked
    task automatic read_samples(input integer n, input integer nchg, input string name);
        logic [7:0] st;
        logic [15:0] sq;
        logic [23:0] d;
        bit ok;
        for (int i = 0; i < n; i++) begin
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (!ok) fail($sformatf("%s: sample CRC", name));
            if (st[7] !== 1'b1) fail($sformatf("%s: sample not VALID (status 0x%02h)", name, st));
            if (nchg >= 0 && i < nchg && st[4] !== 1'b1) fail($sformatf("%s: sample %0d without CHANGED", name, i));
            if (nchg >= 0 && i >= nchg && st[4] !== 1'b0) fail($sformatf("%s: sample %0d with CHANGED", name, i));
            if (have_last && sq <= last_seq) fail($sformatf("%s: SEQ %0d after %0d", name, sq, last_seq));
            last_seq  = sq;
            have_last = 1'b1;
        end
    endtask
    // every sample read with a good CRC and VALID goes to the golden comparison while the log runs (audit round 8:
    // only read_samples' samples were logged, and the log stopped at K)
    // RAW words (O, O2): one per frame, bits at RAW_CLK's rises, MSB first, {101, the code of the frame that ends}
    task automatic o_words(input integer n, input string tag);
        logic [7:0] word;
        logic [4:0] want;
        integer nw, nbad, fo;
        fo = n_rawclk;
        repeat (64) @(posedge MCLK);
        if (n_rawclk - fo != 16) begin                  // no decoding: it would wait for RAW_CLK
            fail($sformatf("%s: %0d RAW_CLK rises in 2 frames, expected 16 (the stream has priority)", tag, n_rawclk - fo));
            nw = n;
        end else nw = 0;
        nbad = 0;
        while (nw < n) begin
            @(posedge CMP_STROBE);
            want = CODE;                                // the code of the frame that ends here
            word = 8'h00;
            for (int b = 0; b < 8; b++) begin
                @(posedge RAW_CLK);
                word = {word[6:0], RAW_DATA};
            end
            if (word !== {3'b101, want}) begin
                nbad = nbad + 1;
                if (nbad < 4) fail($sformatf("%s: RAW word 0x%02h, expected 0x%02h (code %0d)", tag, word, {3'b101, want}, want));
            end
            nw = nw + 1;
        end
    endtask
    task automatic r14_sample_hook(input logic [7:0] st, input logic [15:0] sq, input logic [23:0] d, input bit ok);
        if (log_on && ok && st[7] === 1'b1) begin
            $fdisplay(fsmp, "%0d %0d %0d", sq, $signed(d), st);
            nsamples = nsamples + 1;
        end
    endtask

    // the RESET_N release reaches the first CMP_STROBE after exactly 3 MCLK: 2 synchronizer flops and the strobe's
    // register (audit round 9: a single-flop release passed every test); the control reset of a SOFT_RESET lasts 5 MCLK
    integer n_release = -1;
    initial begin
        @(posedge RESET_N);
        n_release = 0;
        while (CMP_STROBE !== 1'b1 && n_release < 40) begin @(posedge MCLK); n_release = n_release + 1; #1; end
    end
    real t_rstn_fall = 0.0, rstn_low = 0.0;
    always @(negedge dut.rst_n) t_rstn_fall = $realtime;
    always @(posedge dut.rst_n) rstn_low = $realtime - t_rstn_fall;
    // RAW's frames (audit round 20, auditor C): RAW_EN is taken from its register at the frame boundary (o_on_m, at the
    // edge that ends cycle 31) and the pads change mode one MCLK later (o_on, from e1): modelled here from the register,
    // not taken from eeg_raw's own `on` (a copy that kept the stream off with DBG_SEL != 0 kept `on` at 0, so the
    // monitors gated by it saw nothing, and it passed all 16 groups). In every frame of the stream RAW_CLK rises exactly
    // 8 times (a word is never cut); in every MCLK without the stream and with DBG_SEL s != 0, the pads are s's pair one
    // MCLK later (a pair is never cut, nor replaced before the boundary)
    //
    // DEBUG as written (audit round 28, auditor C: the monitors took RAW_EN and DBG_SEL from eeg_regs' outputs, so a
    // copy whose IF_CFG write loaded RAW_EN from the reserved bit 2 drove the pads as its wrong register said and
    // passed every group that compiles eeg_regs): the test key and DEBUG modelled from the committed writes at the
    // register block's port (the SPI slave's reg_we, reg_addr, reg_wdata: every write to TEST_KEY sets the lock, a
    // DEBUG write is taken while unlocked, as it has no guard and no illegal value), reset with the control domain
    // (RESET_N, SOFT_RESET); the monitors below use the model, and eeg_regs' RAW_EN and DBG_SEL must equal it
    logic       m_unl = 1'b0, m_raw = 1'b0;
    logic [1:0] m_dbg = 2'b00;
    always @(posedge MCLK or negedge dut.rst_n)
        if (!dut.rst_n) begin m_unl <= 1'b0; m_raw <= 1'b0; m_dbg <= 2'b00; end
        else if (dut.reg_we === 1'b1) begin
            if (dut.reg_addr === 7'h11) m_unl <= (dut.reg_wdata === 8'h3C);
            else if (dut.reg_addr === 7'h62 && m_unl) begin m_raw <= dut.reg_wdata[0]; m_dbg <= dut.reg_wdata[2:1]; end
        end
    integer n_dbg_model = 0;
    always @(negedge MCLK)
        if (dut.rst_n === 1'b1 && (dut.raw_en !== m_raw || dut.dbg_sel !== m_dbg)) begin
            n_dbg_model = n_dbg_model + 1;
            if (n_dbg_model <= 3) fail($sformatf("DEBUG: RAW_EN %b DBG_SEL %0d in eeg_regs, the committed writes give %b %0d",
                                                 dut.raw_en, dut.dbg_sel, m_raw, m_dbg));
        end
    // and the lock itself (audit round 30, auditor C: an unlock decoded from the data alone passed all 16 groups): eeg_regs'
    // lock equals the model of the TEST_KEY writes at every MCLK
    integer n_lock_model = 0;
    always @(negedge MCLK)
        if (dut.rst_n === 1'b1 && dut.u_regs.unlocked !== m_unl) begin
            n_lock_model = n_lock_model + 1;
            if (n_lock_model <= 3) fail($sformatf("TEST_KEY: eeg_regs unlocked %b, the committed TEST_KEY writes give unlocked %b",
                                                  dut.u_regs.unlocked, m_unl));
        end
    // phase Z's commit and acknowledge edges (audit round 30)
    real z_t_ack = 0.0, z_t_c = 0.0;
    always @(posedge MCLK) if (dut.cmd_ack) z_t_ack = $realtime;
    always @(posedge MCLK) if (dut.reg_we && dut.reg_addr == 7'h21) z_t_c = $realtime;
    // phase AD's store and flag edges (audit round 34, auditor C): at every store, ALERT as the specification gives it
    // from the registers of the store's own cycle (|(ERR & ALERT_MASK) | |(DFLAG & ALERT_MASK_D); spec 3.4: a sample's
    // ERR bit is ALERT at the store), by SEQ; the edges of the last store and of the last change of ERR
    logic        ad_exp [0:255];
    real         ad_t_store = 0.0, ad_t_pos = 0.0, ad_t_err = 0.0;
    integer      ad_n_store = 0, ad_nchk = 0;
    logic [15:0] ad_seq_store = 16'd0;
    logic [7:0]  ad_err_q = 8'h00;
    real         ad_lat [0:1];                       // AD: a write's start to the edge that changes ERR
    integer      ad_nb [0:1], ad_ns [0:1], ad_na [0:1];   // AD: changes before / at the start of / after a store's cycle
    always @(posedge MCLK) begin
        ad_t_pos = $realtime;
        if (dut.push_ok === 1'b1) begin
            ad_exp[dut.seq_cnt[7:0]] = (|(dut.u_regs.err & dut.u_regs.r_mask)) |
                                       (|(dut.u_regs.dflag_byte & dut.u_regs.mask_d_byte));
            ad_seq_store = dut.seq_cnt;
            ad_t_store   = $realtime;
            ad_n_store   = ad_n_store + 1;
        end
    end
    always @(negedge MCLK) begin
        if (dut.u_regs.err !== ad_err_q) ad_t_err = ad_t_pos;     // ERR changed at the last rising edge
        ad_err_q = dut.u_regs.err;
    end
    // phase AF's copy edges (audit round 35, auditor C): ALERT as the registers give it in the cycle of each copy of the
    // header's STATUS (the SPI's cs_start) and of the sample word (smp_snap; FIFO level 0: the empty word)
    real         af_t_hdr = 0.0, af_t_snap = 0.0;
    logic        af_hdr_exp = 1'b0, af_snap_exp = 1'b0;
    logic [3:0]  af_snap_lvl = 4'd0;
    real         af_lat [0:1];                       // AF: a frame's start to its copy edge (0: header, 1: sample word)
    integer      af_nb [0:1], af_ns [0:1], af_na [0:1];   // AF: changes before / at the start of / after the copy's cycle
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start === 1'b1) begin
            af_hdr_exp = (|(dut.u_regs.err & dut.u_regs.r_mask)) | (|(dut.u_regs.dflag_byte & dut.u_regs.mask_d_byte));
            af_t_hdr   = $realtime;
        end
        if (dut.smp_snap === 1'b1) begin
            af_snap_exp = (|(dut.u_regs.err & dut.u_regs.r_mask)) | (|(dut.u_regs.dflag_byte & dut.u_regs.mask_d_byte));
            af_snap_lvl = dut.fifo_level;
            af_t_snap   = $realtime;
        end
    end
    // phase AJ: the apply matrix (audit round 37, auditor C); run_apply_matrix() in build/pin_tests.svh calls it
    integer      aj_all [0:5];
    integer      aj_n = 0;
    initial for (int i = 0; i < 6; i++) aj_all[i] = 0;
    task automatic apply_case(input integer k,
                              input logic [7:0] s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61,
                              input logic [7:0] p20, p21, p22, p23, p24, p25, p26, p27, p28, p60, p61,
                              input logic [9:0] e_ofm, input logic e_ofs, input logic [3:0] e_ofen,
                              input logic [1:0] e_ib, input logic [3:0] e_cpf, input logic [1:0] e_bp,
                              input logic [1:0] e_bn, input logic e_dwa, input logic e_chen, input logic [7:0] e_tcfg,
                              input integer e_bw, input logic e_bheld, input integer e_chalf, input integer e_c1half,
                              input logic all_changed, input string name);
        // k: 0 START in IDLE (checked in WARMUP), 1 APPLY in IDLE, 2 APPLY_NR in IDLE, 3 APPLY in WARMUP, 4 APPLY_NR
        // in WARMUP, 5 APPLY in RUN (checked when RUN is back). s: the shadows 0x20..0x28, 0x60, 0x61; p: the active
        // copies before the command (the case's previous settings; the generator asserts that every apply field
        // differs from them when all_changed)
        logic [7:0] v, e, cmd;
        logic [3:0] st;
        logic [6:0] A [0:10];
        logic [7:0] sh [0:10];
        logic [7:0] pv [0:10];
        real t0;
        A  = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h60, 7'h61};
        sh = '{s20, s21, s22, s23, s24, s25, s26, s27, s28, s60, s61};
        pv = '{p20, p21, p22, p23, p24, p25, p26, p27, p28, p60, p61};
        cmd = (k == 0) ? 8'h11 : ((k == 2 || k == 4) ? 8'h44 : 8'h33);
        st  = (k == 1 || k == 2) ? 4'd0 : ((k == 5) ? 4'd6 : 4'd1);
        if (k == 3 || k == 4) begin                     // into WARMUP: the START applies the shadows as they are
            r14_cmd(8'h11);
            wait_state(4'd1, 50.0, {name, ": WARMUP"});
        end
        if (k == 5 && dut.seq_state !== 4'd6) begin     // into RUN (before the first RUN case)
            r14_cmd(8'h11);
            wait_state(4'd6, 15000.0, {name, ": RUN"});
        end
        if (k <= 2 && dut.seq_state !== 4'd0)
            fail($sformatf("%s: state %0d before the command, expected IDLE", name, dut.seq_state));
        for (int i = 0; i < 11; i++) begin              // the active copies before it
            r14_read(A[i] + 7'h10, v);
            if (v !== pv[i])
                fail($sformatf("%s: active 0x%02h = 0x%02h before the command, expected 0x%02h", name, A[i] + 7'h10, v, pv[i]));
        end
        r14_write(7'h11, 8'h3C);                        // TEST_KEY: the test shadows too
        for (int i = 0; i < 11; i++) r14_write(A[i], sh[i]);
        r14_write(7'h11, 8'h00);
        expect_noerr({name, ": the writes"});
        r14_cmd(cmd);
        if (k == 5) begin                               // PRE, PULSE, RECOVER, ALIGN, FILL, then RUN again
            t0 = $realtime;
            while (dut.seq_state === 4'd6 && $realtime - t0 < 50000.0) @(posedge MCLK);
            if (dut.seq_state === 4'd6) fail($sformatf("%s: the APPLY in RUN not taken", name));
            wait_state(4'd6, 15000.0, {name, ": RUN again"});
        end
        repeat (700) @(posedge MCLK);                   // the tick (at most 15.6 us)
        r14_read(7'h06, e);
        if (e !== 8'h00) fail($sformatf("%s: ERR 0x%02h after the command, expected none (accepted)", name, e));
        if (e !== 8'h00) r14_write(7'h06, 8'hFF);
        if (dut.seq_state !== st) fail($sformatf("%s: state %0d after the command, expected %0d", name, dut.seq_state, st));
        if (OFM !== e_ofm || OFS !== e_ofs || OFEN !== e_ofen || AFE_IBIAS !== e_ib || CPF_TRIM !== e_cpf ||
            BTRIM_P !== e_bp || BTRIM_N !== e_bn || DWA_EN !== e_dwa || CHOP_EN !== e_chen || TEST_CFG !== e_tcfg)
            fail($sformatf("%s: pins OFM %0d OFS %b OFEN %b IBIAS %0d CPF %0d BTRIM P %0d N %0d DWA %b CHOP_EN %b TEST_CFG %02h; expected %0d %b %b %0d %0d %0d %0d %b %b %02h",
                           name, OFM, OFS, OFEN, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, DWA_EN, CHOP_EN, TEST_CFG,
                           e_ofm, e_ofs, e_ofen, e_ib, e_cpf, e_bp, e_bn, e_dwa, e_chen, e_tcfg));
        for (int i = 0; i < 11; i++) begin              // every active copy took its shadow
            r14_read(A[i] + 7'h10, v);
            if (v !== sh[i]) fail($sformatf("%s: active 0x%02h = 0x%02h, shadow 0x%02h", name, A[i] + 7'h10, v, sh[i]));
        end
        repeat (1100) @(posedge MCLK);                  // a new chopper rate applies at the 512-MCLK wrap
        measure_chop(e_bw, e_bheld, e_chalf, e_c1half, 1'b1, name);
        if (dut.seq_state !== st) fail($sformatf("%s: state %0d after the measurement, expected %0d", name, dut.seq_state, st));
        if (k == 0 || k == 3 || k == 4) begin           // back to IDLE
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, {name, ": IDLE"});
        end
        if (all_changed) aj_all[k] = aj_all[k] + 1;
        aj_n = aj_n + 1;
    endtask
    // phase AE: ERR and DFLAG read exactly after each accepted command (audit round 35, auditor C)
    integer      ae_n = 0;
    task automatic ae_check(input string what, input logic [7:0] ew, input logic [7:0] fw);
        logic [7:0] e, f;
        repeat (700) @(posedge MCLK);                   // the command taken at its tick (two ticks at 128 kHz)
        r14_read(7'h06, e);
        r14_read(7'h07, f);
        if (e !== ew || f !== fw)
            fail($sformatf("AE: after %s, ERR 0x%02h and DFLAG 0x%02h, expected exactly 0x%02h and 0x%02h (REG-02, FLG-02: only their W1C clears them)",
                           what, e, f, ew, fw));
        ae_n = ae_n + 1;
    endtask
    // every sample in the FIFO read; each one's ERR bit must be the ALERT of its store's cycle
    task automatic ad_read_all();
        logic [7:0] st_;
        logic [15:0] sq_;
        logic [23:0] d_;
        bit ok_;
        st_ = 8'h80;
        while (st_[SMP_VALID_LSB] === 1'b1) begin
            r14_sample(st_, sq_, d_, ok_);
            if (!ok_) begin
                fail("AD: a sample read without a valid CRC");
                st_ = 8'h00;
            end else if (st_[SMP_VALID_LSB] === 1'b1) begin
                ad_nchk = ad_nchk + 1;
                if (st_[SMP_ERR_LSB] !== ad_exp[sq_[7:0]])
                    fail($sformatf("AD: sample SEQ %0d, status 0x%02h with ERR %b; ALERT in its store's cycle %b (spec 3.4)",
                                   sq_, st_, st_[SMP_ERR_LSB], ad_exp[sq_[7:0]]));
            end
        end
    endtask
    logic o_on_m = 1'b0, o_on = 1'b0;
    always @(posedge MCLK or negedge dut.tm_rst_n)
        if (!dut.tm_rst_n) begin o_on_m <= 1'b0; o_on <= 1'b0; end
        else begin
            if (dut.cycle == 5'd31) o_on_m <= m_raw;
            o_on <= o_on_m;
        end
    integer o_rises = 0, n_raw_cut = 0, n_raw_pair = 0, n_raw_frames = 0, n_raw_pairs = 0;
    bit     o_fr_on = 1'b0, o_fr_ok = 1'b0;           // the mode of the pads' frame now running; a whole one
    always @(posedge RAW_CLK) o_rises = o_rises + 1;
    always @(posedge MCLK) begin                        // at the edge, before its updates (RAW_CLK's rise at this edge
        if (dut.tm_rst_n !== 1'b1) begin                // counts for the frame it starts)
            o_fr_ok = 1'b0;
            o_rises = 0;
        end else if (dut.cycle == 5'd0) begin           // this edge is e1: the pads' frame e1 .. e1 ends here
            if (o_fr_ok && o_fr_on) begin
                n_raw_frames = n_raw_frames + 1;
                if (o_rises != 8) begin
                    n_raw_cut = n_raw_cut + 1;
                    if (n_raw_cut <= 3) fail($sformatf("RAW: %0d RAW_CLK rises in a frame of the stream, expected 8 (a word is never cut)", o_rises));
                end
            end
            o_rises = 0;
            o_fr_on = o_on_m;                           // the mode from this edge on
            o_fr_ok = 1'b1;
        end
    end
    logic [1:0] o_ps = 2'b00;                           // DBG_SEL before this edge (taken just after the previous one)
    logic       o_pc = 1'b0, o_pd = 1'b0, o_pv = 1'b0;
    always @(posedge MCLK) begin
        #0.2;                                           // the pads set at this edge from `on` (o_on now) and DBG_SEL
        if (o_pv && dut.tm_rst_n === 1'b1 && o_on === 1'b0 && o_ps != 2'b00) begin   // and the pair before it
            n_raw_pairs = n_raw_pairs + 1;
            if (RAW_CLK !== o_pc || RAW_DATA !== o_pd) begin
                n_raw_pair = n_raw_pair + 1;
                if (n_raw_pair <= 3) fail($sformatf("RAW: DBG_SEL %0d without the stream: RAW_CLK / RAW_DATA %b / %b, its pair one MCLK before %b / %b", o_ps, RAW_CLK, RAW_DATA, o_pc, o_pd));
            end
        end
        o_ps = m_dbg;
        case (m_dbg)
            2'd1:    begin o_pc = CMP_STROBE; o_pd = DAC_CLK;  end
            2'd2:    begin o_pc = CHOP;       o_pd = CHOP_OUT; end
            2'd3:    begin o_pc = CHOP_BLANK; o_pd = CHOP1;    end
            default: begin o_pc = 1'b0;       o_pd = 1'b0;     end
        endcase
        o_pv = (dut.tm_rst_n === 1'b1);
    end
    integer o_commit_cycle = -1;                        // the frame cycle of the last change of RAW_EN (O2)
    always @(m_raw) o_commit_cycle = dut.cycle;
    // RAW's bit timing while the stream runs (audit round 9: a word loaded at cycle 0 instead of 31 passed): RAW_DATA
    // changes only at e1, e5, ..., e29 and RAW_CLK rises only at e3, e7, ..., e31 (the stream's frames from the
    // model above since round 20)
    integer n_raw_t = 0;
    always @(RAW_DATA) begin
        #1;
        if (o_on === 1'b1 && dut.rst_n === 1'b1 && dut.cycle[1:0] !== 2'd1) begin
            n_raw_t = n_raw_t + 1;
            if (n_raw_t <= 3) fail($sformatf("RAW_DATA changed in frame cycle %0d (only at e1, e5, ...)", dut.cycle));
        end
    end
    always @(posedge RAW_CLK) begin
        #1;
        if (o_on === 1'b1 && dut.rst_n === 1'b1 && dut.cycle[1:0] !== 2'd3) begin
            n_raw_t = n_raw_t + 1;
            if (n_raw_t <= 3) fail($sformatf("RAW_CLK rose in frame cycle %0d (only at e3, e7, ...)", dut.cycle));
        end
    end

    // a SOFT_RESET reaches soft_req in its commit cycle (audit round 18, auditor C: R forces dut.soft_req at the cycles
    // it tests, so a register between the commit and soft_req, a natural timing fix, passed every group while moving
    // the coincidences R checks (NFR-06, spec 3.3) by one MCLK): in every MCLK cycle in which the SPI commits a write of
    // CMD_SOFT_RESET to COMMAND (eeg_regs' write strobe, address and data from the SPI), soft_req is high, and soft_req
    // is high in no other cycle (the forced ones aside)
    integer n_soft_commits = 0, n_soft_bad = 0;
    always @(posedge MCLK) begin
        logic c5;
        c5 = (dut.u_regs.we === 1'b1) && (dut.u_regs.addr === A_COMMAND) && (dut.u_regs.wdata === CMD_SOFT_RESET);
        if (dut.rst_n === 1'b1 && !soft_forced) begin
            if (c5) n_soft_commits = n_soft_commits + 1;
            if (c5 !== (dut.soft_req === 1'b1)) begin
                n_soft_bad = n_soft_bad + 1;
                if (n_soft_bad <= 3)
                    fail($sformatf("soft_req %b in a cycle where a SOFT_RESET commit is %b (it must be the commit cycle)",
                                   dut.soft_req, c5));
            end
        end
    end

    // CHOP_BLANK against CHOP_OUT at the pads (audit round 17, auditor C: a register on the CHOP_BLANK pad, the obvious
    // NFR-06 clean-up, moved its rise from the MCLK before the CHOP_OUT edge to the edge itself and passed every group;
    // the AFE makes CDA and CDB "... and not CHOP_BLANK" (afe/eeg_afe_clk.spice), so the break-before-make that REG-06
    // and the requirements' 4.10 rely on rests on this order): at every CHOP_OUT edge CHOP_BLANK was high in the MCLK
    // before it and stays high for the blanking length after it, then falls (the pulse lasts the length + 1 MCLK; the
    // length is BLANK_LEN of the active copy, or BLANK_WITH_DAC while the OFEN pads show the offset DAC on: REG-07,
    // pins_from_active); it rises only in the MCLK before an edge. ADC_ZERO (TEST_CFG[5]) holds it high. The edge at
    // the first MCLK after the timing reset's release is not blanked (eeg_clkgen's header). Sampled mid-cycle.
    logic   cb_q = 1'b0, co_q = 1'b0, cb_rise = 1'b0, cb_rise_az = 1'b0, cb_az = 1'b0, cb_first = 1'b1;
    integer cb_len = 0, cb_want = 0, n_cb_edges = 0, n_cb_bad = 0;
    integer n_cb_w [0:1] = '{0, 0};                    // pulses measured with the offset DAC off / on
    task automatic cb_bad(input string m);
        n_cb_bad = n_cb_bad + 1;
        if (n_cb_bad <= 3) fail(m);
    endtask
    always @(negedge MCLK) begin
        logic co, cb, az, ed;
        co = CHOP_OUT; cb = CHOP_BLANK; az = TEST_CFG[5];
        if (dut.tm_rst_n !== 1'b1) begin
            cb_first = 1'b1; cb_len = 0; cb_rise = 1'b0; cb_az = 1'b0;
        end else begin
            ed = (co !== co_q);
            if (cb_rise && !cb_rise_az && !ed)
                cb_bad($sformatf("CHOP_BLANK rose in frame cycle %0d without a CHOP_OUT edge at the next MCLK", (dut.cycle + 31) % 32));
            if (ed) begin
                if (cb_first) cb_first = 1'b0;           // the edge right after the release: not blanked
                else begin
                    n_cb_edges = n_cb_edges + 1;
                    if (cb_q !== 1'b1 || cb !== 1'b1)
                        cb_bad($sformatf("CHOP_OUT edge with CHOP_BLANK %b in the MCLK before it and %b after it", cb_q, cb));
                end
            end
            cb_rise = (cb === 1'b1 && cb_q === 1'b0);
            if (cb_rise) begin                          // the pulse's length, as the clock generator latches it
                cb_rise_az = az;
                cb_want = 1 + ((OFEN !== 4'd0) ? int'(BLANK_WITH_DAC) : int'(dut.u_regs.a_blank));
            end
            if (cb === 1'b1) begin
                cb_len = cb_len + 1;
                if (az) cb_az = 1'b1;
            end else begin
                if (cb_q === 1'b1 && !cb_az && !az) begin
                    n_cb_w[cb_want == 1 + int'(BLANK_WITH_DAC)] = n_cb_w[cb_want == 1 + int'(BLANK_WITH_DAC)] + 1;
                    if (cb_len != cb_want)
                        cb_bad($sformatf("CHOP_BLANK high %0d MCLK, expected %0d (the blanking length + 1)", cb_len, cb_want));
                end
                cb_len = 0; cb_az = 1'b0;
            end
        end
        co_q = co; cb_q = cb;
    end
    // CHOP1 changes only at e16 (spec 4.1; audit round 17, auditor C: a register on the CHOP1 pad moved its edges to
    // e17 and passed every group)
    integer n_c1_edges = 0, n_c1_bad = 0;
    always @(CHOP1) begin
        #1;
        if (dut.tm_rst_n === 1'b1 && RESET_N === 1'b1) begin
            n_c1_edges = n_c1_edges + 1;
            if (dut.cycle !== 5'd16) begin
                n_c1_bad = n_c1_bad + 1;
                if (n_c1_bad <= 3) fail($sformatf("CHOP1 changed in frame cycle %0d (only at e16)", dut.cycle));
            end
        end
    end

    // RAW (audit round 8): with the stream off (eeg_raw's `on` 0, RAW_EN taken at the frame boundary) and DBG_SEL 0,
    // both pads stay low (RST-02, the eeg_raw header; the pad coupling is rated for RAW on only). The pads are
    // registered, so the condition must have held for 2 MCLK.
    logic [1:0] raw_quiet_q = 2'b00;
    integer     n_raw_noisy = 0;
    always @(posedge MCLK) begin
        raw_quiet_q <= {raw_quiet_q[0], o_on_m === 1'b0 && m_dbg === 2'b00};   // the model's latch, read at the
                                                // edge as eeg_raw reads its `on` (round 20)
        if (raw_quiet_q == 2'b11 && (RAW_DATA !== 1'b0 || RAW_CLK !== 1'b0)) begin
            n_raw_noisy = n_raw_noisy + 1;
            if (n_raw_noisy <= 3) fail($sformatf("RAW pads not quiet with the stream off and DBG_SEL 0 (RAW_DATA %b, RAW_CLK %b)", RAW_DATA, RAW_CLK));
        end
    end

    // W (audit round 10): commits and MISO_OE while a frame that was running at a reset's release goes on
    bit w_on = 1'b0;
    integer w_we = 0, w_oe = 0;
    always @(posedge MCLK) if (w_on) begin
        if (dut.reg_we === 1'b1 && dut.reg_addr !== 7'h10) w_we = w_we + 1;   // W3's own SOFT_RESET is a commit to 0x10
        if (MISO_OE === 1'b1) w_oe = w_oe + 1;
    end

    // the analog control pins at their reset values, written here from the requirements and not from regmap (audit
    // round 10, auditor C: a test control's reset value edited in regmap passed every test, the generated tests and the
    // pin monitor following the map): test settings off (ANA-05, REG-08), the offset DAC off, REG-05's operating values
    task automatic check_reset_pins(input string tag);
        if (CHOP_EN !== 1'b1) fail($sformatf("%s: CHOP_EN %b, the chopper must run from the reset (ANA-05)", tag, CHOP_EN));
        if (TEST_CFG[5:0] !== 6'd0) fail($sformatf("%s: TEST_CFG[5:0] 0x%02h, the test settings must be off", tag, TEST_CFG[5:0]));
        if (OFEN !== 4'd0 || OFM !== 10'd0 || OFS !== 1'b0) fail($sformatf("%s: the offset DAC on (OFEN %b, OFM %0d, OFS %b)", tag, OFEN, OFM, OFS));
        if (AFE_IBIAS !== 2'd3 || CPF_TRIM !== 4'd8 || BTRIM_P !== 2'd1 || BTRIM_N !== 2'd0 || DWA_EN !== 1'b1)
            fail($sformatf("%s: AFE_IBIAS %0d, CPF_TRIM %0d, BTRIM_P %0d, BTRIM_N %0d, DWA_EN %b; REG-05 gives 3, 8, 1, 0, 1",
                           tag, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, DWA_EN));
        if (AFE_RST !== 1'b1) fail($sformatf("%s: AFE_RST %b, held after a reset", tag, AFE_RST));
    endtask
    // the timing pins and MISO while RESET_N is low (audit round 29, auditor C: no test read DAC_CLK's reset value, and
    // a copy resetting it to 1 passed all 16 groups; the structural check proves that a reset exists, not its value):
    // CMP_STROBE, TH_CAPTURE, DAC_LOAD, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK and MISO 0, CHOP1 1 (eeg_chop1's phase A)
    task automatic check_reset_timing(input string tag);
        if (CMP_STROBE !== 1'b0 || TH_CAPTURE !== 1'b0 || DAC_LOAD !== 1'b0 || DAC_CLK !== 1'b0 || CHOP !== 1'b0 ||
            CHOP_OUT !== 1'b0 || CHOP_BLANK !== 1'b0 || MISO !== 1'b0 || CHOP1 !== 1'b1)
            fail($sformatf("%s: CMP_STROBE %b TH_CAPTURE %b DAC_LOAD %b DAC_CLK %b CHOP %b CHOP_OUT %b CHOP_BLANK %b MISO %b CHOP1 %b; reset values 0 0 0 0 0 0 0 0 1",
                           tag, CMP_STROBE, TH_CAPTURE, DAC_LOAD, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, MISO, CHOP1));
    endtask
    // the reset values of REG-05 that show only as waveforms (audit round 17, auditor C: check_reset_pins left them out,
    // where the documents said "REG-05's values"): BLANK 7 (CHOP_BLANK high 8 MCLK), CHOP_FAST 1 (CHOP's half period
    // 128 MCLK) and CHOP1 4 kHz (half period 4,096 MCLK). Written from the requirements, not generated from regmap, as
    // check_reset_pins. The clock generator takes CHOP_FAST at its next wrap (512 MCLK) and CHOP1 its rate at the next
    // 1,024-frame boundary, so CHOP1 only after RESET_N
    // one SCLK slip in a transfer (audit round 18, auditor B): kind 1 an extra pulse the chip counts after host pulse
    // `at` (100 ns inside the low phase), kind 2 host pulse `at` 8 ns long just after an MCLK edge (the chip misses it).
    // bits8: the chip's bit count past whole bytes just before CS_N rises (1 for an extra pulse, 7 for a missed one)
    task automatic xfer_slip(input integer nbytes, input integer kind, input integer at, output logic [2:0] bits8);
        integer total;
        total = 8 * nbytes;
        CS_N = 1'b0;
        MOSI = spi_bit(0, nbytes);
        #(spi_tcss);
        for (int n = 0; n < total; n++) begin
            if (kind == 2 && n == at) begin
                @(posedge MCLK); #2.0;
                SCLK = 1'b1; spi_rx[n / 8][7 - (n % 8)] = miso_pad; #8.0; SCLK = 1'b0;
                MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0;
                if (n + 1 < total) #(spi_low);
            end else begin
                SCLK = 1'b1;
                spi_rx[n / 8][7 - (n % 8)] = miso_pad;
                #(spi_high);
                SCLK = 1'b0;
                MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0;
                // the extra pulse 150 ns into the low phase, after the chip's MISO update for the last fall
                if (kind == 1 && n == at) begin #(150.0); SCLK = 1'b1; #(100.0); SCLK = 1'b0; #(spi_low); end
                else if (n + 1 < total) #(spi_low);
            end
        end
        #(spi_tcsh);
        bits8 = dut.u_spi.bit_cnt;
        CS_N = 1'b1;
        #(spi_tidle);
    endtask
    task automatic check_reset_waves(input string tag, input logic with_c1);
        repeat (600) @(posedge MCLK);
        measure_chop(8, 1'b0, 128, 4096, with_c1, {tag, ": the reset waveforms (REG-05)"});
    endtask

    // ------------------------------------------------------------------ the test
    logic [7:0] v;
    real t_start_tick, t0, t1;
    integer seq_before;
    initial begin
        repeat (5) @(negedge MCLK);
        check_reset_timing("RESET_N low at the start");   // audit round 29
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        if (n_release != 3) fail($sformatf("the first CMP_STROBE %0d MCLK after the RESET_N release, expected 3 (two synchronizer flops and the strobe's register)", n_release));
        prev_tick = 1'b0;
        ana_q = ana;
        check_reset_pins("after RESET_N");
        check_reset_waves("after RESET_N", 1'b1);

        // ---------------- A: registers
        phase = "A";
        run_reg_tests();
        $display("A1 register tests done (errors so far %0d)", errors);
        // CRC
        r14_write(7'h55, 8'h01);                        // CRC_EN on (this write itself without CRC)
        bfm_crc_en = 1'b1;
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM with CRC");
        r14_write(7'h24, 8'h05);
        rt_read_expect(7'h24, 8'h05, "CPF_TRIM written with CRC");
        r14_write(7'h40, 8'h5A);                        // the sample window, CRC on (audit round 13, auditor C: no bench
        expect_err_exact(8'h08, "A: a CRC-on write to the sample window (read only): exactly ADDR_ERR");   // sent one)
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h09; spi_tx[2] = 8'h00;   // wrong CRC
        spi_xfer(3, 0);
        rt_read_expect(7'h24, 8'h05, "CPF_TRIM not written with a wrong CRC");
        expect_err_now(8'h04, "CRC_ERR");
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h09;           // CRC on, frame without the CRC byte
        spi_xfer(2, 0);
        expect_err_now(8'h02, "FRAME_ERR (write without its CRC byte)");
        r14_write(7'h24, 8'h08);
        r14_write(7'h55, 8'h00);
        bfm_crc_en = 1'b0;
        expect_noerr("CRC off");
        // frame errors
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_xfer(2, 3);       // three extra bits
        expect_err_now(8'h02, "FRAME_ERR (partial byte)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM unchanged after a partial byte");
        spi_tx[0] = 8'h24; spi_xfer(1, 0);                           // header only
        expect_err_now(8'h02, "FRAME_ERR (header only)");
        spi_tx[0] = 8'hA4; spi_xfer(1, 4);                           // a read stopped inside its data byte
        expect_err_now(8'h02, "FRAME_ERR (read stopped inside a byte)");
        spi_tx[0] = 8'hA4; spi_xfer(0, 5);                           // five bits of a header
        expect_err_now(8'h02, "FRAME_ERR (partial header)");
        spi_tx[0] = SMP_HDR; spi_xfer(3, 2);                         // a sample read stopped inside a byte
        expect_err_now(8'h02, "FRAME_ERR (sample read stopped inside a byte)");
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // too long
        if (spi_rx[1] !== 8'h00 || spi_rx[2] !== 8'h00)
            fail($sformatf("MISO after the header of an overlong write: %02h %02h, expected 00 00", spi_rx[1], spi_rx[2]));
        expect_err_now(8'h02, "FRAME_ERR (overlong write)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM unchanged after an overlong write");
        CS_N = 1'b0; #500; CS_N = 1'b1; #600;                        // empty frame
        expect_noerr("empty frame");
        // every illegal state value of the SPI state machine (NFR-05): FRAME_ERR at CS_N rising, nothing written; the
        // values not among eeg_spi_slave's S_* codes, read from the compiled RTL (audit round 27, auditor C)
        spi_codes();
        $display("SPI illegal state values (not among eeg_spi_slave's 11 S_* codes):%s", spi_illegal_txt);
        if (n_spi_illegal != 16 - 11)
            fail($sformatf("the SPI's 11 state names have %0d distinct codes, expected 11", 16 - n_spi_illegal));
        for (int bad = 0; bad < 16; bad++) if (!spi_defd[bad]) begin
            fork
                begin
                    spi_tx[0] = 8'h24; spi_tx[1] = 8'h0E; spi_xfer(2, 0);
                end
                begin
                    #(6000.0);                          // inside the data byte
                    force_spi_st(bad);
                    @(posedge MCLK);
                    release dut.u_spi.st;
                end
            join
            expect_err_now(8'h02, $sformatf("FRAME_ERR for the illegal SPI state value %0d", bad));
            rt_read_expect(7'h24, 8'h08, $sformatf("CPF_TRIM not written by a frame with the illegal SPI state %0d", bad));
        end
        // ... and between frames (CS_N high; audit round 15, auditor B): the value stays until the next CS_N fall, which
        // starts that frame in the header state; the frame is processed normally and nothing is flagged (NFR-05)
        for (int bad = 0; bad < 16; bad++) if (!spi_defd[bad]) begin
            @(posedge MCLK); #1;
            force_spi_st(bad);                          // constant forces (Icarus)
            @(posedge MCLK);
            release dut.u_spi.st;
            #(4.0 * TMCLK);
            if (dut.u_spi.st !== bad[3:0])
                fail($sformatf("SPI state value %0d forced between frames was %0d before the next frame", bad, dut.u_spi.st));
            spi_tx[0] = 8'h24; spi_tx[1] = 8'h0E; spi_xfer(2, 0);
            expect_noerr($sformatf("the frame after the illegal SPI state value %0d between frames", bad));
            rt_read_expect(7'h24, 8'h0E, $sformatf("CPF_TRIM written by the frame after the illegal SPI state %0d between frames", bad));
            spi_tx[0] = 8'h24; spi_tx[1] = 8'h08; spi_xfer(2, 0);
            expect_noerr($sformatf("CPF_TRIM restored after the illegal SPI state %0d between frames", bad));
        end
        r14_cmd(8'h77);
        expect_err_now(8'h80, "CMD_ERR (unknown code)");
        r14_write(7'h11, 8'h3D);                        // TEST_KEY one bit off: locks and flags CMD_ERR
        expect_err_now(8'h80, "CMD_ERR for a wrong key");
        // the codes and the key are whole bytes (REG-01; audit round 16, auditor C: a 7-bit compare of the key passed
        // every test, and those of the codes were caught only by chance random bytes): the key with bit 7 set, and
        // each code (SOFT_RESET's too) with bit 7 flipped, are unknown: CMD_ERR alone, nothing unlocked or done
        r14_write(7'h11, 8'hBC);
        expect_err_exact(8'h80, "CMD_ERR for the key with bit 7 set (0xBC)");
        rt_write_check(7'h60, 8'h05, 8'h00, 8'h08, "TEST_MUX locked after the key with bit 7 set");
        foreach (bad_codes[k]) begin
            r14_cmd(bad_codes[k]);
            repeat (600) @(posedge MCLK);               // past a tick at either rate
            expect_err_exact(8'h80, $sformatf("CMD_ERR alone for the code 0x%02h (a command's with bit 7 flipped)", bad_codes[k]));
            if (dut.seq_state !== 4'd0) fail($sformatf("the code 0x%02h moved the sequencer to %0d", bad_codes[k], dut.seq_state));
        end
        r14_write(7'h60, 8'h05);
        expect_err_now(8'h08, "TEST_MUX locked after a wrong key");
        rt_read_expect(7'h60, 8'h00, "TEST_MUX unchanged after a wrong key");
        r14_write(7'h11, 8'h3C);
        r14_write(7'h11, 8'h00);                        // unlock, then lock with 0x00: no error
        expect_noerr("TEST_KEY 0x3C, then 0x00");
        r14_write(7'h11, 8'h3C);                        // unlocked, then a wrong key: locks (audit round 4)
        r14_write(7'h11, 8'h3D);
        expect_err_now(8'h80, "CMD_ERR for a wrong key after the right one");
        r14_write(7'h60, 8'h05);
        expect_err_now(8'h08, "TEST_MUX locked by a wrong key after the right one");
        rt_read_expect(7'h60, 8'h00, "TEST_MUX unchanged after the wrong key");
        // burst read 0x20..0x27 in one frame (CRC off): the same bytes as eight single reads
        begin
            logic [7:0] single [0:7];
            r14_write(7'h21, 8'h5A);  r14_write(7'h24, 8'h0C);       // shadows away from their reset values
            for (int i = 0; i < 8; i++) r14_read(7'h20 + i, single[i]);
            spi_tx[0] = 8'hA0;
            for (int i = 1; i <= 8; i++) spi_tx[i] = 8'h00;
            spi_xfer(9, 0);
            for (int i = 0; i < 8; i++)
                if (spi_rx[1 + i] !== single[i])
                    fail($sformatf("burst read of 0x%02h: 0x%02h, single read 0x%02h", 7'h20 + i, spi_rx[1 + i], single[i]));
            expect_noerr("burst read");
            r14_write(7'h21, 8'h00);  r14_write(7'h24, 8'h08);
        end
        $display("A  registers, CRC and frame errors done (errors %0d)", errors);

        // ---------------- B: START
        phase = "B";
        r14_cmd(8'h11);
        wait_state(4'd1, 50.0, "WARMUP after START");
        t_start_tick = t_state[1];                      // the state changed at e25 of the tick (its recorded time,
                                                        // audit round 25, auditor C: not when the bench saw it)
        rt_read_expect(7'h04, 8'd1, "STATE in WARMUP");
        wait_state(4'd2, 5100.0, "RECOVER after T_WARM");
        t0 = (t_afe_fall - t_start_tick) / 1000.0;
        if (t0 < 4999.0 || t0 > 5001.0) fail($sformatf("T_WARM %0.3f us, expected 5000", t0));
        wait_state(4'd4, 300.0, "ALIGN after T_REC");
        if ((t_state[4] - t_afe_fall) / 1000.0 < 249.95 || (t_state[4] - t_afe_fall) / 1000.0 > 250.05)
            fail($sformatf("RECOVER lasted %0.3f us, expected T_REC = 250", (t_state[4] - t_afe_fall) / 1000.0));
        wait_state(4'd5, 1100.0, "FILL at the next output time");
        wait_state(4'd6, 3100.0, "RUN after three outputs");
        r14_read(7'h03, v);
        if (v[3] !== 1'b1) fail("STATUS.READY not set in RUN");
        rt_read_expect(7'h04, 8'd6, "STATE in RUN");
        read_samples(6, -1, "B samples");
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            spi_tx[0] = SMP_HDR; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00; spi_tx[3] = 8'h00;
            spi_xfer(4, 0);                             // header, STATUS, SEQ: stopped on a byte boundary
            expect_noerr("a sample read stopped after 4 bytes");
            r14_sample(st, sq, d, ok);
            if (sq !== {spi_rx[2], spi_rx[3]}) fail($sformatf("partial sample read popped: SEQ %0d, then %0d",
                                                             {spi_rx[2], spi_rx[3]}, sq));
            if (!ok || st[7] !== 1'b1) fail("sample after a partial read");
            last_seq = sq;
        end
        $display("B  START to RUN, T_WARM %0.3f us, 6 samples (errors %0d)", t0, errors);

        // ---------------- C: APPLY in RUN
        phase = "C";
        r14_write(7'h24, 8'h0B);                        // CPF_TRIM shadow
        seq_before = last_seq;
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "PRE after APPLY");
        t0 = t_state[7];                                // PRE's entry at the APPLY's tick (audit round 25, auditor C:
        // $realtime is when the bench saw PRE, never before r14_cmd returns, CS_N's rise + 600 ns; an APPLY whose tick
        // fell in those 600 ns made a correct chip measure T_PRE 22.99 us, and the runner called a mutant detected)
        if (CPF_TRIM !== 4'hB) fail("CPF_TRIM pin not applied at the tick");
        wait_state(4'd8, 100.0, "PULSE after T_PRE");
        wait_state(4'd2, 200.0, "RECOVER after T_RST");
        t1 = (t_afe_fall - t_afe_rise) / 1000.0;
        if (t1 < 101.55 || t1 > 101.58) fail($sformatf("AFE_RST pulse %0.4f us, expected 101.5625", t1));
        if ((t_afe_rise - t0) / 1000.0 < 23.40 || (t_afe_rise - t0) / 1000.0 > 23.47)
            fail($sformatf("T_PRE %0.4f us, expected 23.4375", (t_afe_rise - t0) / 1000.0));
        wait_state(4'd6, 5000.0, "RUN again");
        // host procedure step 4 (audit round 7): an executed APPLY keeps STATE out of RUN for at least
        // T_PRE + T_RST + T_REC + T_ELEC + 3 ms from its tick (T_ELEC 0 here)
        if ((t_state[6] - t_state[7]) / 1000.0 < 23.4375 + 101.5625 + 250.0 + 3000.0)
            fail($sformatf("C: RUN %0.1f us after the APPLY's tick, expected at least 3375", (t_state[6] - t_state[7]) / 1000.0));
        read_samples(1, -1, "C first sample after the APPLY");
        if (last_seq < seq_before + 16'd4)              // audit round 8 (host procedure step 4): the FIFO is emptied and
            fail($sformatf("C: SEQ %0d after %0d, an executed APPLY gives at least 4 more", last_seq, seq_before));   // FILL stores its third output
        read_samples(3, -1, "C samples");
        $display("C  APPLY: pulse %0.4f us, SEQ %0d -> %0d (errors %0d)", t1, seq_before, last_seq, errors);

        // ---------------- D: APPLY_NR
        phase = "D";
        r14_write(7'h51, 8'd2);                         // T_ELEC = 2 ms
        r14_write(7'h22, 8'h01);                        // range 1 (needs APPLY with a pulse)
        r14_write(7'h21, 8'h0A);                        // M = 10
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "PRE after APPLY of range 1");     // RUN until the tick
        if (OFEN !== 4'b0001 || OFM !== 10'd10 || OFS !== 1'b0) fail("offset DAC pins after APPLY");
        wait_state(4'd3, 400.0, "WAIT_E after RECOVER (T_ELEC = 2)");
        wait_state(4'd6, 9000.0, "RUN after APPLY of range 1");
        if ((t_state[6] - t_state[7]) / 1000.0 < 23.4375 + 101.5625 + 250.0 + 2000.0 + 3000.0)
            fail($sformatf("D: RUN %0.1f us after the APPLY's tick, expected at least 5375 (T_ELEC 2 ms)", (t_state[6] - t_state[7]) / 1000.0));
        if ((t_state[3] - t_state[2]) / 1000.0 < 249.95 || (t_state[3] - t_state[2]) / 1000.0 > 250.05)
            fail($sformatf("D RECOVER lasted %0.3f us, expected 250", (t_state[3] - t_state[2]) / 1000.0));
        if ((t_state[4] - t_state[3]) / 1000.0 < 1999.95 || (t_state[4] - t_state[3]) / 1000.0 > 2000.05)
            fail($sformatf("D WAIT_E lasted %0.3f us, expected T_ELEC = 2000", (t_state[4] - t_state[3]) / 1000.0));
        while (DRDY_N === 1'b0) read_samples(1, -1, "D drain");
        read_samples(1, -1, "D sync");                // right after an output: the next one is 1 ms away
        r14_write(7'h21, 8'h0B);                        // M = 11: one step
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (dut.seq_state !== 4'd6 || OFM !== 10'd11) fail("APPLY_NR of one step");
        read_samples(7, 5, "D CHANGED (3 + T_ELEC)");
        r14_write(7'h21, 8'h0D);                        // M = 13: two steps
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        expect_err_now(8'h20, "CFG_ERR for an APPLY_NR of two steps");
        if (OFM !== 10'd11) fail("two-step APPLY_NR applied");
        r14_write(7'h21, 8'h0B);
        // D2: a long mark (T_ELEC = 30: 33 outputs), then an APPLY: leaving RUN cancels the rest of the mark, so the
        // samples of the next RUN (a cleared CIC, after the waits) carry no CHANGED
        phase = "D2";
        r14_write(7'h51, 8'd30);                        // T_ELEC = 30 ms
        r14_write(7'h21, 8'h0C);                        // M = 12: one step
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (dut.seq_state !== 4'd6 || OFM !== 10'd12) fail("D2 APPLY_NR of one step");
        while (DRDY_N === 1'b0) read_samples(1, -1, "D2 drain");
        read_samples(2, 2, "D2 CHANGED of the long mark");
        r14_write(7'h51, 8'd0);                         // T_ELEC = 0: the APPLY's path is short (about 4.4 ms)
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "D2 PRE after APPLY");
        wait_state(4'd6, 6000.0, "D2 RUN after APPLY");
        if (dut.chg_cnt !== 9'd0) fail($sformatf("D2 CHANGED count %0d in the new RUN, expected 0", dut.chg_cnt));
        read_samples(3, 0, "D2 no CHANGED after leaving RUN");
        r14_write(7'h21, 8'h0B);
        r14_cmd(8'h44);                                 // back to M = 11 (one step)
        repeat (300) @(posedge MCLK);
        if (OFM !== 10'd11) fail("D2 APPLY_NR back to M = 11");
        // D3: a mark of 13 outputs (T_ELEC = 10); two samples later a second step with T_ELEC = 0 (a mark of 3 alone)
        // must keep the 11 that remain: the first step's electrode is still settling
        phase = "D3";
        r14_write(7'h51, 8'd10);                        // T_ELEC = 10 ms
        r14_write(7'h21, 8'h0C);                        // M = 12: one step
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (OFM !== 10'd12) fail("D3 first APPLY_NR");
        while (DRDY_N === 1'b0) read_samples(1, -1, "D3 drain");
        read_samples(2, 2, "D3 CHANGED of the first mark");
        r14_write(7'h51, 8'd0);                         // T_ELEC = 0
        r14_write(7'h21, 8'h0B);                        // M = 11: one step back
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (OFM !== 10'd11) fail("D3 second APPLY_NR");
        if (dut.chg_cnt !== 9'd11) fail($sformatf("D3 CHANGED count %0d after the second mark, expected 11", dut.chg_cnt));
        read_samples(12, 11, "D3 the longer mark kept (11 more samples, then none)");
        // D4 (audit round 22, auditor C: a longer new mark extending a running short one was caught only through the 3
        // marks D2 left running): right after an output, a step with T_ELEC = 0 (a mark of 3), then, before the next
        // output, a step with T_ELEC = 10 (13): the longer mark wins and 13 samples carry CHANGED
        phase = "D4";
        if (dut.chg_cnt !== 9'd0) fail($sformatf("D4 starts with %0d marks left", dut.chg_cnt));
        while (DRDY_N === 1'b0) read_samples(1, -1, "D4 drain");
        while (dut.push_ok !== 1'b1) @(posedge MCLK);   // an output: the next one is 1 ms away
        repeat (64) @(posedge MCLK);
        r14_write(7'h51, 8'd0);                         // T_ELEC = 0
        r14_write(7'h21, 8'h0C);                        // M = 12: one step, a mark of 3
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (OFM !== 10'd12) fail("D4 first APPLY_NR");
        if (dut.chg_cnt !== 9'd3) fail($sformatf("D4 CHANGED count %0d after the short mark, expected 3", dut.chg_cnt));
        r14_write(7'h51, 8'd10);                        // T_ELEC = 10
        r14_write(7'h21, 8'h0B);                        // M = 11: one step back, a mark of 13
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (OFM !== 10'd11) fail("D4 second APPLY_NR");
        if (dut.chg_cnt !== 9'd13) fail($sformatf("D4 CHANGED count %0d after the longer second mark, expected 13", dut.chg_cnt));
        while (DRDY_N === 1'b0) read_samples(1, -1, "D4 drain");
        read_samples(14, 13, "D4 the longer mark (13 samples, then none)");
        r14_write(7'h51, 8'd0);
        $display("D  APPLY_NR, CHANGED cancelled on leaving RUN, the longer mark kept, either order (errors %0d)", errors);

        // ---------------- E: START in RUN, STOP, START with an inconsistent configuration
        phase = "E";
        r14_cmd(8'h11);
        repeat (300) @(posedge MCLK);
        expect_err_now(8'h40, "STATE_ERR for START in RUN");
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "IDLE after STOP");
        if (AFE_RST !== 1'b1) fail("AFE_RST not 1 in IDLE");
        r14_write(7'h21, 8'hC8);                        // M = 200 > 127 (range 1)
        r14_cmd(8'h11);
        repeat (300) @(posedge MCLK);
        expect_err_now(8'h20, "CFG_ERR for START with M above the range");
        if (dut.seq_state !== 4'd0) fail("START with an inconsistent configuration left IDLE");
        r14_write(7'h21, 8'h0A);
        $display("E  STATE_ERR, STOP, CFG_ERR (errors %0d)", errors);

        // ---------------- F: one pending command (64 kHz)
        phase = "F";
        r14_write(7'h26, 8'h00);                        // CHOP_FAST 0
        r14_cmd(8'h33);                                 // APPLY in IDLE: no pulse
        repeat (2000) @(posedge MCLK);
        if (dut.a_chop_fast !== 1'b0) fail("64 kHz not applied");
        expect_noerr("APPLY in IDLE");
        @(posedge dut.tick);
        #(8000.0);
        spi_tidle = 125.0;
        r14_cmd(8'h55);                                 // FLUSH
        r14_cmd(8'h55);                                 // before the next tick (15.6 us)
        spi_tidle = 600.0;
        expect_err_now(8'h40, "STATE_ERR for a second command before the tick (64 kHz)");
        @(posedge dut.tick);
        #(8000.0);
        spi_tidle = 125.0;
        r14_cmd(8'h55);                                 // FLUSH
        r14_cmd(8'h77);                                 // an unknown code while FLUSH is pending
        spi_tidle = 600.0;
        r14_read(7'h06, v);
        if (v !== 8'h80) fail($sformatf("unknown code while a command is pending: ERR 0x%02h, expected 0x80", v));
        r14_write(7'h06, 8'hFF);
        r14_write(7'h26, 8'h01);
        r14_cmd(8'h33);
        repeat (2000) @(posedge MCLK);
        $display("F  pending command (errors %0d)", errors);

        // ---------------- G: FLUSH and overrun
        phase = "G";
        r14_cmd(8'h11);
        wait_state(4'd6, 10000.0, "RUN for G");
        have_last = 1'b0;
        repeat (3 * 32768) @(posedge MCLK);              // 3 ms: three samples stored
        r14_read(7'h05, v);
        if (v < 8'd2) fail($sformatf("FIFO level %0d before FLUSH", v));
        r14_cmd(8'h55);
        repeat (400) @(posedge MCLK);
        r14_read(7'h05, v);
        if (v !== 8'd0) fail($sformatf("FIFO level %0d after FLUSH", v));
        repeat (11 * 32768) @(posedge MCLK);             // 11 ms: more than 8 samples -> overrun
        r14_read(7'h07, v);
        if (v[0] !== 1'b1) fail("DFLAG.OVERRUN after the FIFO overflowed");
        rt_read_expect(7'h05, FDEPTH, "G FIFO_LEVEL of a full FIFO (audit round 7: the level's top bit)");
        r14_cmd(8'h55);
        repeat (400) @(posedge MCLK);
        begin                                           // the empty word carries DFLAG.OVERRUN too
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            r14_sample(st, sq, d, ok);
            if (st[7] !== 1'b0 || st[6] !== 1'b1 || st[3] !== 1'b1 || !ok)    // ERR = ALERT: DFLAG.OVERRUN (audit
                fail($sformatf("the empty word after an overrun: status 0x%02h, expected VALID 0, OVERRUN 1 and ERR 1 (ALERT from DFLAG.OVERRUN)", st));   // round 19)
        end
        for (int i = 0; i < 2; i++) begin             // two samples (audit round 14, auditor C: OVERRUN kept only
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;   // until the next store passed every test)
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (st[6] !== 1'b1 || st[3] !== 1'b1)     // and ERR: ALERT from DFLAG.OVERRUN (audit round 19, auditor C)
                fail($sformatf("sample %0d status 0x%02h while DFLAG.OVERRUN is set: OVERRUN 1 and ERR 1 (ALERT) expected", i, st));
        end
        r14_write(7'h07, 8'hFF);
        r14_read(7'h07, v);
        if (v !== 8'h00) fail($sformatf("DFLAG 0x%02h after writing 0xFF (W1C)", v));
        begin                                           // a sample stored after the clear: OVERRUN 0 (audit round 14,
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;   // auditor C: never checked; an OVERRUN tied to 1
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);          // passed every test)
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (!ok || st[7] !== 1'b1 || st[6] !== 1'b0)
                fail($sformatf("G: a sample stored after DFLAG.OVERRUN was cleared: status 0x%02h, expected VALID 1 and OVERRUN 0", st));
        end
        r14_write(7'h06, 8'hFF);
        // G2: a sample read whose header copies the old head, a FLUSH taken during the read, a sample stored after
        // the flush and before CS_N rises: the read must not pop the new sample
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok; real t_out;
            @(posedge dut.cic_stb);
            t_out = $realtime + 1.0e6;                  // the next output time (1024 frames = 1 ms)
            @(posedge dut.tick);
            while (t_out - $realtime > 31000.0) @(posedge dut.tick);    // a tick 23.2..31 us before it
            #(500.0);
            spi_tidle = 125.0;
            r14_cmd(8'h55);                             // FLUSH: committed ~8.9 us after that tick
            r14_sample(st, sq, d, ok);                  // header ~12.8 us, CS_N rising ~41 us after that tick
            spi_tidle = 600.0;
            if (!(t_snap < t_flush && t_flush < t_store && t_store < t_csr && t_csr - t_snap < 40000.0))
                fail($sformatf("G2 not exercised: copy %0.1f, flush %0.1f, store %0.1f, CS_N %0.1f us",
                               t_snap / 1000.0, t_flush / 1000.0, t_store / 1000.0, t_csr / 1000.0));
            if (st[7] !== 1'b1 || !ok) fail("G2: the copy of the old head is not a valid sample");
            r14_read(7'h05, v);
            if (v !== 8'd1) fail($sformatf("G2: FIFO level %0d after the read, expected 1 (the sample stored after the flush)", v));
            have_last = 1'b0;
            read_samples(1, -1, "G2 next");
            if (last_seq <= sq) fail($sformatf("G2: the next sample has SEQ %0d after %0d", last_seq, sq));
        end
        // G3: DRDY_N pulse mode: low for exactly 128 MCLK from each stored sample, whatever the FIFO holds
        begin
            real tf, tr;
            r14_write(7'h55, 8'h02);                    // DRDY_MODE 1
            for (int k = 0; k < 3; k++) begin
                @(negedge DRDY_N);
                tf = $realtime;
                if (t_store < tf - 1.5 * TMCLK || t_store > tf) fail("G3: DRDY_N pulse not started by a store");
                @(posedge DRDY_N);
                tr = $realtime;
                if ((tr - tf) / TMCLK < 127.5 || (tr - tf) / TMCLK > 128.5)
                    fail($sformatf("G3: DRDY_N pulse %0.2f MCLK, expected 128", (tr - tf) / TMCLK));
                r14_read(7'h05, v);
                if (v < 8'd1) fail("G3: no sample in the FIFO after the pulse");
                if (k == 2 && DRDY_N !== 1'b1) fail("G3: DRDY_N low between pulses with a non-empty FIFO");
            end
            // G3b (audit round 22, auditor C): a FLUSH that runs at the tick 80 MCLK after a store, inside its pulse: the
            // pulse still lasts 128 MCLK (the monitor above; a copy that ends the pulse when the FIFO empties passed all
            // 16 groups). The FLUSH is written to commit about 100 MCLK before the next store, so that it is pending at
            // the store and runs at the next tick (128 kHz: frame 1, 80 MCLK after the store of frame 15)
            begin
                real t0, d_wr;
                r14_cmd(8'h55);                             // room in the FIFO first (4 deep, it may be full by now)
                repeat (600) @(posedge MCLK);
                t0 = $realtime;
                r14_write(7'h08, 8'hFF);                    // one register write here (its length schedules the FLUSH)
                d_wr = $realtime - t0;
                while (dut.push_ok !== 1'b1) @(posedge MCLK);
                #((32768.0 - 100.0) * TMCLK - d_wr);
                r14_cmd(8'h55);                             // FLUSH, pending at the next store
                repeat (600) @(posedge MCLK);
                if (!(t_flush > t_store && t_flush - t_store < 128.0 * TMCLK))
                    fail($sformatf("G3b not exercised: the FLUSH ran %0.1f MCLK after the store, not inside its pulse",
                                   (t_flush - t_store) / TMCLK));
            end
            while (dut.fifo_level != 4'(FD)) @(posedge MCLK);   // full: the next outputs are dropped
            repeat (200) @(posedge MCLK);               // past the pulse of the sample that filled it
            begin
                integer nf0;
                nf0 = n_drdy_fall;
                repeat (3 * 32768) @(posedge MCLK);
                if (n_drdy_fall != nf0) fail($sformatf("G3: %0d DRDY_N pulses for outputs dropped by a full FIFO", n_drdy_fall - nf0));
            end
            r14_write(7'h07, 8'hFF);                    // the overrun of this test
            r14_write(7'h55, 8'h00);                    // level mode again
            r14_cmd(8'h55);                             // empty the FIFO
            repeat (400) @(posedge MCLK);
            have_last = 1'b0;
        end
        $display("G  FLUSH, overrun, a read across a FLUSH, DRDY_N pulses (errors %0d)", errors);

        // ---------------- H: SOFT_RESET (the control side only)
        phase = "H";
        begin
            integer seq0, cnt0, n0;
            integer tc0;
            tc0 = n_chop1_edge;                         // CHOP1 at 4 kHz (half period 4096 MCLK) since START
            while (dut.fifo_level < 4'd2) @(posedge MCLK);  // samples in the FIFO (RUN since G)
            r14_write(7'h24, 8'h03);
            @(posedge MCLK); #1;
            seq0 = dut.seq_cnt;  cnt0 = dut.u_clkgen.cnt;  n0 = mclk_count;
            r14_cmd(8'hA5);
            repeat (50) @(posedge MCLK);
            #1;
            if (dut.seq_state !== 4'd0 || AFE_RST !== 1'b1) fail("SOFT_RESET: not IDLE");
            if (rstn_low < 5.0 * TMCLK - 0.1 || rstn_low > 5.0 * TMCLK + 0.1)      // audit round 9
                fail($sformatf("SOFT_RESET: the control reset lasted %0.2f ns, expected 5 MCLK (%0.2f ns)", rstn_low, 5.0 * TMCLK));
            if (dut.u_clkgen.cnt !== 9'((cnt0 + mclk_count - n0) % 512))
                fail($sformatf("SOFT_RESET moved the frame counter: %0d, expected %0d", dut.u_clkgen.cnt,
                               (cnt0 + mclk_count - n0) % 512));
            if (dut.seq_cnt < seq0) fail($sformatf("SOFT_RESET reset SEQ: %0d after %0d", dut.seq_cnt, seq0));
            repeat (9000) @(posedge MCLK);              // past the next CHOP1 edges
            if (n_chop1_edge <= tc0 || ((n_chop1_edge - tc0) % 4096) != 0)
                fail($sformatf("SOFT_RESET moved CHOP1: an edge %0d MCLK after the one before it", n_chop1_edge - tc0));
        end
        check_reset_pins("after SOFT_RESET");
        rt_read_expect(7'h06, 8'h01, "ERR after SOFT_RESET (RESET_FLAG)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM after SOFT_RESET");
        rt_read_expect(7'h05, 8'h00, "FIFO level after SOFT_RESET");
        if (DRDY_N !== 1'b1) fail("DRDY_N low after SOFT_RESET");
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            r14_sample(st, sq, d, ok);
            if (st[7] !== 1'b0 || sq !== 16'd0 || d !== 24'd0 || !ok)
                fail($sformatf("sample read after SOFT_RESET: status 0x%02h SEQ %0d (the empty word expected)", st, sq));
        end
        $display("H  SOFT_RESET (errors %0d)", errors);

        // ---------------- I: SOFT_RESET while a command is pending (64 kHz)
        phase = "I";
        r14_write(7'h06, 8'hFF);
        r14_write(7'h26, 8'h00);                        // CHOP_FAST 0
        r14_cmd(8'h33);                                 // APPLY in IDLE
        repeat (2000) @(posedge MCLK);
        if (dut.a_chop_fast !== 1'b0) fail("I: 64 kHz not applied");
        @(posedge dut.tick);
        #(8000.0);
        spi_tidle = 125.0;
        r14_cmd(8'h11);                                 // START, pending until the next tick (audit round 16: a FLUSH
        r14_cmd(8'hA5);                                 // run late in IDLE showed nothing); SOFT_RESET while it waits
        spi_tidle = 600.0;
        repeat (50) @(posedge MCLK);
        if (soft_pend !== 1'b1) fail("I not exercised: no command pending when SOFT_RESET was taken");
        if (dut.seq_state !== 4'd0 || dut.a_chop_fast !== 1'b1) fail("I: SOFT_RESET with a pending command not taken");
        // the pending command goes with the SOFT_RESET (RST-02; audit round 16, auditor C: a pending command kept
        // through it passed every test, and the next tick started the chip with the reset values): CMD_PENDING 0 at
        // once, IDLE with AFE_RST high two ticks on
        check_status(8'h80 | (8'h01 << STATUS_AFE_RST_LSB),
                     8'hC0 | (8'h01 << STATUS_CMD_PENDING_LSB) | (8'h01 << STATUS_READY_LSB) | (8'h01 << STATUS_AFE_RST_LSB),
                     "I: STATUS right after the SOFT_RESET (no command pending)");
        repeat (2) @(posedge dut.tick);
        repeat (3) @(posedge MCLK);
        if (dut.seq_state !== 4'd0 || AFE_RST !== 1'b1)
            fail($sformatf("I: two ticks after the SOFT_RESET: state %0d, AFE_RST %b (the START pending at the reset ran)",
                           dut.seq_state, AFE_RST));
        rt_read_expect(7'h04, 8'h00, "I: STATE two ticks after the SOFT_RESET");
        rt_read_expect(7'h06, 8'h01, "I: ERR after SOFT_RESET with a pending command (RESET_FLAG only)");
        $display("I  SOFT_RESET with a pending command (errors %0d)", errors);

        // ---------------- J: audit round 1 (11/20)
        phase = "J";
        // J1: STATUS in IDLE right after phase I's SOFT_RESET (RESET_FLAG and the default mask give ALERT)
        check_status(8'hA1, 8'hFF, "J1 STATUS in IDLE after SOFT_RESET");
        r14_write(7'h06, 8'hFF);
        check_status(8'h81, 8'hFF, "J1 STATUS in IDLE, errors cleared");
        // J2: at 64 kHz a frame fits between two ticks: CMD_PENDING, and the writes guarded while a command waits
        begin
            logic [7:0] mask0;
            r14_write(7'h26, 8'h00);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            if (dut.a_chop_fast !== 1'b0) fail("J2: 64 kHz not applied");
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h55);                             // FLUSH: pending until the next tick
            check_status(8'h91, 8'hD9, "J2 CMD_PENDING after a command, before its tick");
            spi_tidle = 600.0;
            repeat (700) @(posedge MCLK);
            check_status(8'h81, 8'hD9, "J2 CMD_PENDING cleared by the tick");
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h55);
            r14_write(7'h24, 8'h0D);                    // CPF_TRIM shadow while FLUSH waits
            spi_tidle = 600.0;
            expect_err_now(8'h40, "J2 STATE_ERR for a shadow write while a command is pending");
            rt_read_expect(7'h24, 8'h08, "J2 CPF_TRIM shadow not written");
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h55);
            r14_write(7'h52, 8'd40);                    // T_REC while FLUSH waits
            spi_tidle = 600.0;
            expect_err_now(8'h40, "J2 STATE_ERR for a timer write while a command is pending");
            rt_read_expect(7'h52, 8'd32, "J2 T_REC not written");
            r14_read(7'h08, mask0);
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h55);
            r14_write(7'h08, 8'hFD);                    // ALERT_MASK: not guarded
            spi_tidle = 600.0;
            expect_noerr("J2 ALERT_MASK written while a command is pending");
            rt_read_expect(7'h08, 8'hFD, "J2 ALERT_MASK written");
            r14_write(7'h08, mask0);
            run_guard_tests();                          // every guarded register (audit round 7)
            run_free_tests();                           // every other writable register (audit round 13)
            r14_write(7'h26, 8'h01);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
        end
        // J3: CRC on: a header-only read (the status poll) is legal; a read without its CRC byte and a sample read
        // shorter than 8 bytes are frame errors
        r14_write(7'h55, 8'h01);
        bfm_crc_en = 1'b1;
        spi_tx[0] = 8'h83; spi_xfer(1, 0);
        expect_noerr("J3 header-only read with CRC on");
        spi_tx[0] = 8'h84; spi_tx[1] = 8'h00; spi_xfer(2, 0);
        expect_err_now(8'h02, "J3 FRAME_ERR for a read without its CRC byte");
        spi_tx[0] = SMP_HDR;
        for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00;
        spi_xfer(4, 0);
        expect_err_now(8'h02, "J3 FRAME_ERR for a sample read of 4 bytes with CRC on");
        begin                                           // through r14_sample (audit round 13: the sample it popped was
            logic [7:0] st3; logic [15:0] sq3; logic [23:0] d3; bit ok3;   // not checked): its CRC, and a VALID one goes
            r14_sample(st3, sq3, d3, ok3);              // to the golden comparison by the hook
            if (!ok3) fail("J3 complete sample read with CRC on: the sample's CRC");
        end
        expect_noerr("J3 complete sample read with CRC on");
        spi_tx[0] = 8'h84; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00; spi_tx[3] = 8'h00; spi_xfer(4, 0);
        if (spi_rx[3] !== 8'h00) fail($sformatf("J3 MISO after a completed CRC read: %02h, expected 00", spi_rx[3]));
        expect_err_now(8'h02, "J3 FRAME_ERR for a CRC read with an extra byte");
        r14_write(7'h55, 8'h00);
        bfm_crc_en = 1'b0;
        // J4: APPLY in WARMUP restarts the wait: AFE_RST is released T_WARM after the change
        r14_cmd(8'h11);
        wait_state(4'd1, 50.0, "J4 WARMUP");
        repeat (4 * 32768) @(posedge MCLK);
        r14_write(7'h24, 8'h0E);
        r14_cmd(8'h33);
        t0 = $realtime;
        while (CPF_TRIM !== 4'hE && ($realtime - t0) < 100000.0) @(posedge MCLK);
        if (CPF_TRIM !== 4'hE) fail("J4 CPF_TRIM not applied by the APPLY in WARMUP");
        t0 = t_cpf;                                     // the tick that applied it
        if (dut.seq_state !== 4'd1) fail("J4 APPLY in WARMUP left WARMUP");
        wait_state(4'd2, 5100.0, "J4 RECOVER after the restarted T_WARM");
        t1 = (t_afe_fall - t0) / 1000.0;
        if (t1 < 4999.0 || t1 > 5001.0)
            fail($sformatf("J4 AFE_RST released %0.3f us after the change in WARMUP, expected 5000", t1));
        // J5: APPLY in RUN empties the FIFO; J6: STATUS in RUN
        wait_state(4'd6, 10000.0, "J5 RUN");
        repeat (3 * 32768) @(posedge MCLK);
        r14_read(7'h05, v);
        if (v < 8'd2) fail($sformatf("J5 FIFO level %0d before APPLY", v));
        check_status(8'h8C, 8'hDF, "J6 STATUS in RUN (READY, DATA, AFE_RST 0)");
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "J5 PRE");
        r14_read(7'h05, v);
        if (v !== 8'd0) fail($sformatf("J5 FIFO level %0d after APPLY, expected 0", v));
        wait_state(4'd6, 10000.0, "J5 RUN again");
        // J7: an overload of about 40 us in RUN: OVL_NOW, DFLAG.OVL, and OVL on exactly the three samples whose window
        // contains it
        have_last = 1'b0;
        while (DRDY_N === 1'b0) read_samples(1, -1, "J7 drain");
        @(posedge dut.cic_stb);
        repeat (300 * 33) @(posedge MCLK);
        begin
            integer k;
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            k = dut.seq_cnt;                            // the SEQ of the next output
            ovl_force = 1'b1;
            repeat (20 * 32) @(posedge MCLK);
            check_status(8'h02, 8'h02, "J7 OVL_NOW during the overload");
            repeat (20 * 32) @(posedge MCLK);
            ovl_force = 1'b0;
            r14_read(7'h07, v);
            if (v[1] !== 1'b1) fail("J7 DFLAG.OVL after an overload in RUN");
            for (int i = 0; i < 5; i++) begin
                while (DRDY_N !== 1'b0) @(posedge MCLK);
                r14_sample(st, sq, d, ok);
                if (!ok || st[7] !== 1'b1) fail("J7 sample CRC or VALID");
                if (st[5] !== (16'(sq - 16'(k)) < 16'd3))
                    fail($sformatf("J7 sample SEQ %0d (overload before SEQ %0d): OVL %b", sq, k, st[5]));
            end                                         // (logged by r14_sample's hook; audit round 13: logged twice)
        end
        r14_write(7'h07, 8'hFF);
        r14_write(7'h06, 8'hFF);
        // J8: an overload in IDLE shows in OVL_NOW but does not set DFLAG.OVL (only FILL and RUN)
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "J8 IDLE");
        r14_write(7'h07, 8'hFF);
        ovl_force = 1'b1;
        repeat (20 * 32) @(posedge MCLK);
        check_status(8'h03, 8'h03, "J8 OVL_NOW and AFE_RST in IDLE during an overload");
        repeat (20 * 32) @(posedge MCLK);
        ovl_force = 1'b0;
        repeat (64 * 32) @(posedge MCLK);
        r14_read(7'h07, v);
        if (v[1] !== 1'b0) fail("J8 DFLAG.OVL set by an overload in IDLE");
        $display("J  STATUS bits, guarded writes, CRC frames, WARMUP restart, APPLY flush, overload (errors %0d)", errors);


        // ---------------- M: status bits no other phase checks (audit round 2, 11/20); RUN, outside the golden log
        phase = "M";
        r14_cmd(8'h11);                                 // RUN (K, which left it running, is the last phase now)
        wait_state(4'd6, 10000.0, "M RUN");
        begin
            logic [7:0] st, e; logic [15:0] sq; logic [23:0] d; bit ok; real tcs, tdr;
            r14_write(7'h06, 8'hFF);
            r14_write(7'h07, 8'hFF);
            check_status(8'h00, 8'h20, "M1 ALERT clear");
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);
            for (int i = 0; i < 2; i++) begin           // M1: no flag: ERR 0, reserved bits 0
                while (DRDY_N !== 1'b0) @(posedge MCLK);
                r14_sample(st, sq, d, ok);
                if (!ok || st[7] !== 1'b1 || st[3] !== 1'b0 || st[2:0] !== 3'b000)
                    fail($sformatf("M1 sample status 0x%02h: VALID, ERR 0 and reserved bits 0 expected", st));
            end
            r14_read(7'h7E, v);                         // M2: an undefined address: ADDR_ERR -> ALERT -> ERR in samples
            check_status(8'h20, 8'h20, "M2 ALERT after ADDR_ERR");
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);
            for (int i = 0; i < 2; i++) begin
                while (DRDY_N !== 1'b0) @(posedge MCLK);
                r14_sample(st, sq, d, ok);
                if (!ok || st[7] !== 1'b1 || st[3] !== 1'b1 || st[2:0] !== 3'b000)
                    fail($sformatf("M2 sample status 0x%02h: ERR 1 (ALERT at the store) expected", st));
            end
            r14_write(7'h08, 8'hF7);                    // M3: ADDR_ERR masked: ALERT 0, ERR 0, the flag stays
            check_status(8'h00, 8'h20, "M3 ALERT with ADDR_ERR masked");
            r14_read(7'h06, e);
            if (e[3] !== 1'b1) fail($sformatf("M3 ERR 0x%02h: ADDR_ERR lost under the mask", e));
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (!ok || st[3] !== 1'b0) fail($sformatf("M3 sample status 0x%02h: ERR 0 with the error masked", st));
            r14_write(7'h08, 8'hFF);
            r14_write(7'h06, 8'hFF);
            r14_write(7'h09, 8'h01);                    // M4: DFLAG.OVL masked (ALERT_MASK_D = OVERRUN only)
            ovl_force = 1'b1;
            repeat (20 * 32) @(posedge MCLK);
            ovl_force = 1'b0;
            repeat (40 * 32) @(posedge MCLK);
            r14_read(7'h07, v);
            if (v[1] !== 1'b1) fail("M4 DFLAG.OVL after an overload in RUN");
            check_status(8'h00, 8'h20, "M4 ALERT with DFLAG.OVL masked");
            r14_write(7'h09, 8'h03);
            check_status(8'h20, 8'h20, "M4 ALERT with DFLAG.OVL unmasked");
            r14_write(7'h07, 8'hFF);
            check_status(8'h00, 8'h20, "M4 ALERT after DFLAG cleared");
            // M5: the DRDY_N release (level mode) after the read that empties the FIFO, then the empty word: drain,
            // wait for the next store (a fresh 1 ms interval), read that single sample
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);                  // the only sample: its read empties the FIFO
            tcs = t_csr;
            tdr = t_drdy_rise;
            if (DRDY_N !== 1'b1 || tdr < tcs || (tdr - tcs) / TMCLK > 5.0)
                fail($sformatf("M5 DRDY_N released %0.2f MCLK after CS_N rose (at most 5; DRDY_N %b)",
                               (tdr - tcs) / TMCLK, DRDY_N));
            r14_read(7'h7E, v);                         // ALERT = 1 for the empty word's ERR
            ovl_force = 1'b1;                           // and OVL_NOW = 1 for its OVL
            repeat (20 * 32) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            e = {1'b0, 1'b0, spi_rx[0][1], 1'b0, spi_rx[0][5], 3'b000};   // DFLAG.OVERRUN is 0 here
            if (!ok || st !== e || sq !== 16'd0 || d !== 24'd0)
                fail($sformatf("M5 empty word: status 0x%02h (expected 0x%02h from STATUS 0x%02h), SEQ %0d, DATA %0d, CRC %0b",
                               st, e, spi_rx[0], sq, d, ok));
            if (spi_rx[0][1] !== 1'b1 || spi_rx[0][5] !== 1'b1) fail("M5 not exercised: OVL_NOW and ALERT expected");
            ovl_force = 1'b0;
            repeat (40 * 32) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
            r14_write(7'h07, 8'hFF);
        end
        $display("M  sample ERR and reserved bits, ALERT masks, DRDY_N release, the empty word (errors %0d)", errors);

        // ---------------- L: SPI at the specification's limits and at 1 MHz (VER-02; audit round 2)
        phase = "L";
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            for (int c = 0; c < 3; c++) begin
                case (c)
                    0: begin spi_high = 4.0 * TMCLK + 0.3; spi_low = 500.0 - spi_high; end   // 2 MHz, minimum high
                    1: begin spi_low = 5.0 * TMCLK + 0.3; spi_high = 500.0 - spi_low; end    // 2 MHz, minimum low
                    default: begin spi_high = 500.0; spi_low = 500.0; end                    // 1 MHz
                endcase
                spi_tcss  = 5.0 * TMCLK + 0.3;
                spi_tcsh  = 3.0 * TMCLK + 0.3;
                spi_tidle = 4.0 * TMCLK + 0.3;
                for (int crc = 0; crc < 2; crc++) begin
                    r14_write(7'h55, crc ? 8'h01 : 8'h00);
                    bfm_crc_en = (crc != 0);
                    for (int k = 0; k < 8; k++) begin
                        r14_write(7'h24, 8'((2 * k + 1 + c) % 16));
                        rt_read_expect(7'h24, 8'((2 * k + 1 + c) % 16), $sformatf("L%0d CPF_TRIM (CRC %0d)", c, crc));
                    end
                    rt_read_expect(7'h00, 8'hE6, $sformatf("L%0d ID (CRC %0d)", c, crc));
                    for (int i = 0; i < 2; i++) begin
                        repeat (6) @(posedge MCLK);             // DRDY_N is released up to 5 MCLK after CS_N
                        while (DRDY_N !== 1'b0) @(posedge MCLK);
                        r14_sample(st, sq, d, ok);
                        if (!ok || st[7] !== 1'b1)
                            fail($sformatf("L%0d sample %0d (CRC %0d): status 0x%02h, SEQ %0d, DATA %0d, CRC ok %0b, MISO %h %h %h %h %h %h %h %h",
                                           c, i, crc, st, sq, d, ok, spi_rx[0], spi_rx[1], spi_rx[2], spi_rx[3],
                                           spi_rx[4], spi_rx[5], spi_rx[6], spi_rx[7]));
                    end
                    expect_noerr($sformatf("L%0d no error (CRC %0d)", c, crc));
                end
            end
            r14_write(7'h55, 8'h00);
            bfm_crc_en = 1'b0;
            r14_write(7'h24, 8'h08);
            spi_high = 250.0; spi_low = 250.0; spi_tcss = 300.0; spi_tcsh = 200.0; spi_tidle = 600.0;
        end
        $display("L  SPI at the timing limits and at 1 MHz (errors %0d)", errors);

        // ---------------- N: the analog pins against the specification, DFLAG.OVL gating, APPLY_NR across a range
        phase = "N";
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 50.0, "N IDLE");
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        run_pin_tests();                                // generated: ends with the reset values applied
        r14_cmd(8'h11);                                 // START: WARMUP, RECOVER, FILL, then PRE and PULSE
        wait_state(4'd1, 50.0, "N WARMUP");
        check_status(8'h01, 8'h09, "N STATUS in WARMUP (READY 0, AFE_RST 1)");
        ovl_burst(1'b0, "N overload in WARMUP");
        wait_state(4'd2, 5100.0, "N RECOVER");
        ovl_burst(1'b0, "N overload in RECOVER");
        wait_state(4'd5, 1400.0, "N FILL");
        ovl_burst(1'b1, "N overload in FILL");
        wait_state(4'd6, 3100.0, "N RUN");
        r14_cmd(8'h33);                                 // APPLY: PRE (24 frames), PULSE (104 frames)
        wait_state(4'd7, 50.0, "N PRE");
        ovl_force = 1'b1;
        repeat (12 * 32) @(posedge MCLK);               // OVL_NOW from 4 frames in, gone 31 frames after (in PULSE)
        ovl_force = 1'b0;
        wait_state(4'd2, 200.0, "N RECOVER after the pulse");
        r14_read(7'h07, v);
        if (v[1] !== 1'b0) fail("N overload in PRE and PULSE set DFLAG.OVL");
        wait_state(4'd6, 5000.0, "N RUN again");
        r14_write(7'h22, 8'h01);                        // RANGE 1, M 0: only the range differs from the active 0
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        expect_err_now(8'h20, "N CFG_ERR for an APPLY_NR across a range");
        if (OFEN !== 4'b0000) fail("N APPLY_NR changed the range");
        r14_write(7'h22, 8'h00);
        // N4: the pulse timers at their limits (VER-03): T_PRE, T_RST, T_REC = 255 (2040 frames = 1992.2 us each),
        // then T_REC at its minimum 29 (226.6 us); T_WARM and T_ELEC up to 255 ms: tb_seq's timer model, every value
        r14_write(7'h53, 8'd255);
        r14_write(7'h54, 8'd255);
        r14_write(7'h52, 8'd255);
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "N4 PRE");
        rt_read_expect(7'h04, 8'd7, "STATE in PRE");
        check_status(8'h00, 8'h09, "N4 STATUS in PRE (READY 0, AFE_RST 0)");
        wait_state(4'd8, 2100.0, "N4 PULSE");
        rt_read_expect(7'h04, 8'd8, "STATE in PULSE");
        check_status(8'h01, 8'h09, "N4 STATUS in PULSE (READY 0, AFE_RST 1)");
        wait_state(4'd2, 2100.0, "N4 RECOVER");
        rt_read_expect(7'h04, 8'd2, "STATE in RECOVER");
        check_status(8'h00, 8'h09, "N4 STATUS in RECOVER (READY 0, AFE_RST 0)");
        wait_state(4'd4, 2100.0, "N4 ALIGN");
        check_status(8'h00, 8'h09, "N4 STATUS in ALIGN or FILL (READY 0, AFE_RST 0)");
        wait_state(4'd5, 1100.0, "N4 FILL");
        check_status(8'h00, 8'h09, "N4 STATUS in FILL (READY 0, AFE_RST 0)");
        if ((t_state[8] - t_state[7]) / 1000.0 < 1992.13 || (t_state[8] - t_state[7]) / 1000.0 > 1992.25 ||
            (t_afe_fall - t_afe_rise) / 1000.0 < 1992.13 || (t_afe_fall - t_afe_rise) / 1000.0 > 1992.25 ||
            (t_state[4] - t_state[2]) / 1000.0 < 1992.13 || (t_state[4] - t_state[2]) / 1000.0 > 1992.25)
            fail($sformatf("N4 PRE %0.3f, AFE_RST pulse %0.3f, RECOVER %0.3f us; expected 1992.188 each",
                           (t_state[8] - t_state[7]) / 1000.0, (t_afe_fall - t_afe_rise) / 1000.0,
                           (t_state[4] - t_state[2]) / 1000.0));
        wait_state(4'd6, 5000.0, "N4 RUN");
        r14_write(7'h52, 8'd29);
        r14_write(7'h53, 8'd3);
        r14_write(7'h54, 8'd13);
        r14_cmd(8'h33);
        wait_state(4'd2, 400.0, "N4 RECOVER (T_REC 29)");
        wait_state(4'd4, 400.0, "N4 ALIGN (T_REC 29)");
        if ((t_state[4] - t_state[2]) / 1000.0 < 226.50 || (t_state[4] - t_state[2]) / 1000.0 > 226.62)
            fail($sformatf("N4 RECOVER %0.3f us at T_REC 29, expected 226.5625", (t_state[4] - t_state[2]) / 1000.0));
        wait_state(4'd6, 5000.0, "N4 RUN again");
        r14_write(7'h52, 8'd32);
        run_nr_tests();                                 // N5: generated from regmap.nr_ok (ends at the reset values)
        $display("N  analog pins (generated cases), DFLAG.OVL gating, APPLY_NR across a range, timer limits, nr_ok cases (errors %0d)", errors);

        // ---------------- O: RAW_DATA / RAW_CLK: the code stream (RAW_EN) and the three timing pairs (DBG_SEL)
        phase = "O";
        begin
            logic [7:0] word;
            logic [4:0] want;
            logic       pc, pd;
            integer nw, nbad, fo;
            r14_write(7'h11, 8'h3C);
            r14_write(7'h62, 8'h01);                    // RAW_EN
            r14_write(7'h11, 8'h00);
            repeat (3 * 32) @(posedge MCLK);
            nw = 0; nbad = 0;
            fo = n_rawclk;
            repeat (64) @(posedge MCLK);                // RAW_CLK runs (8 rises per frame) before decoding
            if (n_rawclk - fo < 14) begin
                fail($sformatf("O RAW_CLK not running with RAW_EN (%0d rises in 2 frames)", n_rawclk - fo));
                nw = 20;                                // no decoding: it would wait for RAW_CLK forever
            end
            while (nw < 20) begin                       // one word per frame: bits at RAW_CLK's rises, MSB first
                @(posedge CMP_STROBE);
                want = CODE;                            // the code of the frame that ends here
                word = 8'h00;
                for (int b = 0; b < 8; b++) begin
                    @(posedge RAW_CLK);
                    word = {word[6:0], RAW_DATA};
                end
                if (word !== {3'b101, want}) begin
                    nbad = nbad + 1;
                    if (nbad < 4) fail($sformatf("O RAW word 0x%02h, expected 0x%02h (code %0d)", word, {3'b101, want}, want));
                end
                nw = nw + 1;
            end
            for (int s = 1; s < 4; s++) begin           // RAW_EN 0, DBG_SEL s: the pads follow a pair one MCLK later
                integer nc, nd, no;
                logic   qc, qd;
                r14_write(7'h11, 8'h3C);
                r14_write(7'h62, 8'(s << 1));
                repeat (8) @(posedge MCLK);             // TEST_CFG[7:6] is DBG_SEL from the write (ANA-01; audit round
                if (TEST_CFG[7:6] !== 2'(s))            // 19, auditor C: a copy taken at APPLY passed every test)
                    fail($sformatf("O TEST_CFG[7:6] %0d 8 MCLK after writing DBG_SEL %0d (ANA-01: at the write)", TEST_CFG[7:6], s));
                r14_write(7'h11, 8'h00);
                repeat (3 * 32) @(posedge MCLK);
                fo = 0;
                pc = 1'bx; pd = 1'bx;
                nc = 0; nd = 0; no = 0;
                // until both signals of the pair changed twice (audit round 17, auditor C: 600 MCLK never saw a CHOP1
                // edge, whose half period is 1,024 MCLK or more, so a CHOP1 retimed late on RAW_DATA passed)
                while (no < 600 || ((nc < 2 || nd < 2) && no < 20000)) begin
                    @(posedge MCLK); #0.2;
                    if (pc !== 1'bx && (RAW_CLK !== pc || RAW_DATA !== pd)) fo = fo + 1;
                    qc = pc; qd = pd;
                    case (s)
                        1: begin pc = CMP_STROBE; pd = DAC_CLK; end
                        2: begin pc = CHOP;       pd = CHOP_OUT; end
                        default: begin pc = CHOP_BLANK; pd = CHOP1; end
                    endcase
                    if (qc !== 1'bx && pc !== qc) nc = nc + 1;
                    if (qd !== 1'bx && pd !== qd) nd = nd + 1;
                    no = no + 1;
                end
                if (nc < 2 || nd < 2)
                    fail($sformatf("O DBG_SEL %0d not exercised: its pair changed %0d and %0d times in %0d MCLK", s, nc, nd, no));
                if (fo != 0) fail($sformatf("O DBG_SEL %0d: RAW_CLK / RAW_DATA differ from their pair in %0d cycles", s, fo));
            end
            // O2 (audit round 20, auditor C: a copy that kept the stream off with DBG_SEL != 0 passed all 16 groups, and one
            // that switched at the write was caught only by chance): RAW_EN 1 with DBG_SEL 1..3, the stream has
            // priority (its words decoded); then RAW_EN written 0 / 1 alternately with DBG_SEL 1 (its pair changes in
            // every frame) from 8 points of the frame, so that the writes commit at 8 frame cycles: the monitors (8
            // RAW_CLK rises in every frame of the stream, the pair in every MCLK without it) see the word in progress
            // end and the pair kept until the boundary
            begin
                integer cyc[8], nd;
                r14_write(7'h11, 8'h3C);
                for (int s = 1; s < 4; s++) begin
                    r14_write(7'h62, 8'((s << 1) | 1));
                    repeat (3 * 32) @(posedge MCLK);
                    o_words(4, $sformatf("O2 RAW_EN 1 with DBG_SEL %0d", s));
                end
                for (int k = 0; k < 8; k++) begin
                    while (dut.cycle !== 5'(4 * k + 1)) @(posedge MCLK);
                    r14_write(7'h62, 8'(2 | (k & 1)));      // DBG_SEL 1; RAW_EN 0 (k even) or 1 (k odd)
                    repeat (8) @(posedge MCLK);
                    cyc[k] = o_commit_cycle;
                    repeat (3 * 32) @(posedge MCLK);
                end
                nd = 0;
                for (int k = 0; k < 8; k++) begin
                    bit seen;
                    seen = 1'b0;
                    for (int j = 0; j < k; j++) if (cyc[j] == cyc[k]) seen = 1'b1;
                    if (!seen) nd = nd + 1;
                end
                if (nd < 6) fail($sformatf("O2 not exercised: the RAW_EN writes committed at %0d distinct frame cycles", nd));
                $display("O2 RAW_EN 1 with DBG_SEL 1..3 (words decoded); RAW_EN 0 / 1 with DBG_SEL 1 committed at cycles %0d %0d %0d %0d %0d %0d %0d %0d",
                         cyc[0], cyc[1], cyc[2], cyc[3], cyc[4], cyc[5], cyc[6], cyc[7]);
            end
            r14_write(7'h11, 8'h3C);
            r14_write(7'h62, 8'h00);
            repeat (8) @(posedge MCLK);
            if (TEST_CFG[7:6] !== 2'd0) fail($sformatf("O TEST_CFG[7:6] %0d 8 MCLK after writing DBG_SEL 0", TEST_CFG[7:6]));
            r14_write(7'h11, 8'h00);
        end
        $display("O  RAW stream and timing pairs, TEST_CFG[7:6] at each DBG_SEL write (errors %0d)", errors);

        // ---------------- P: a refused command leaves the pending one (64 kHz, where two frames fit between ticks)
        phase = "P";
        begin
            logic [7:0] lv0;
            r14_cmd(8'h22);                             // STOP
            wait_state(4'd0, 50.0, "P IDLE");
            r14_write(7'h26, 8'h00);                    // CHOP_FAST 0 (64 kHz), APPLY in IDLE
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            if (dut.a_chop_fast !== 1'b0) fail("P: 64 kHz not applied");
            r14_write(7'h06, 8'hFF);
            // START pending in IDLE, a FLUSH refused before the tick: START must still be taken (WARMUP)
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h11);
            r14_cmd(8'h55);
            spi_tidle = 600.0;
            repeat (1500) @(posedge MCLK);
            expect_err_now(8'h40, "P STATE_ERR for a FLUSH refused while START is pending");
            if (dut.seq_state !== 4'd1) fail($sformatf("P: the pending START was not taken (state %0d)", dut.seq_state));
            wait_state(4'd6, 12000.0, "P RUN at 64 kHz");
            while (dut.fifo_level < 4'd3) @(posedge MCLK);
            r14_read(7'h05, lv0);
            // FLUSH pending in RUN, a START refused before the tick: the FLUSH must still empty the FIFO, RUN stays
            @(posedge dut.tick); #(8000.0); spi_tidle = 125.0;
            r14_cmd(8'h55);
            r14_cmd(8'h11);
            spi_tidle = 600.0;
            repeat (1500) @(posedge MCLK);
            expect_err_now(8'h40, "P STATE_ERR for a START refused while FLUSH is pending");
            r14_read(7'h05, v);
            if (lv0 < 8'd3 || v > 8'd1) fail($sformatf("P: FIFO %0d -> %0d, the pending FLUSH was not executed", lv0, v));
            if (dut.seq_state !== 4'd6) fail($sformatf("P: state %0d after the refused START, expected RUN", dut.seq_state));
            r14_cmd(8'h22);                             // back to 128 kHz
            wait_state(4'd0, 50.0, "P IDLE again");
            r14_write(7'h26, 8'h01);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
        end
        $display("P  a refused command leaves the pending one (errors %0d)", errors);

        // ---------------- S: the host's SOFT_RESET check (requirements 5.4 step 9) in both CRC modes
        phase = "S";
        begin
            logic [7:0] e;
            bit crc_on;
            // case 1: CRC on, a spoiled SOFT_RESET frame (wrong CRC): the probe says CRC on, ERR has CRC_ERR and no
            // RESET_FLAG -> clear with a CRC frame and send SOFT_RESET again; then the probe says CRC off and RESET_FLAG
            r14_write(7'h55, 8'h01);
            bfm_crc_en = 1'b1;
            r14_write(7'h06, 8'hFF);
            spi_tx[0] = 8'h10; spi_tx[1] = 8'hA5; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // SOFT_RESET, wrong CRC
            #(1000.0);
            soft_reset_probe(crc_on, "S1 after a spoiled SOFT_RESET");
            if (!crc_on) fail("S1: the probe says CRC off after a SOFT_RESET frame that must have been refused");
            r14_read(7'h06, e);
            if (e[0] !== 1'b0 || e[2] !== 1'b1) fail($sformatf("S1: ERR 0x%02h, expected CRC_ERR without RESET_FLAG", e));
            r14_write(7'h06, e);
            r14_cmd(8'hA5);                             // SOFT_RESET again, with its CRC
            bfm_crc_en = 1'b0;                          // the host does not yet know whether it was executed
            #(1500.0);
            soft_reset_probe(crc_on, "S1 after the SOFT_RESET");
            if (crc_on) fail("S1: the probe says CRC on after an executed SOFT_RESET");
            r14_read(7'h06, e);
            if (e !== 8'h01) fail($sformatf("S1: ERR 0x%02h after the SOFT_RESET, expected RESET_FLAG only", e));
            r14_write(7'h06, e);
            // case 2: CRC off, a spoiled SOFT_RESET frame (a partial byte): the probe says CRC off, ERR has FRAME_ERR and
            // no RESET_FLAG -> clear without CRC and send SOFT_RESET again
            spi_tx[0] = 8'h10; spi_tx[1] = 8'hA5; spi_xfer(1, 5);                      // 13 bits: refused
            #(1000.0);
            soft_reset_probe(crc_on, "S2 after a spoiled SOFT_RESET");
            if (crc_on) fail("S2: the probe says CRC on with CRC off");
            r14_read(7'h06, e);
            if (e[0] !== 1'b0 || e[1] !== 1'b1) fail($sformatf("S2: ERR 0x%02h, expected FRAME_ERR without RESET_FLAG", e));
            r14_write(7'h06, e);
            r14_cmd(8'hA5);
            #(1500.0);
            r14_read(7'h06, e);
            if (e !== 8'h01) fail($sformatf("S2: ERR 0x%02h after the SOFT_RESET, expected RESET_FLAG only", e));
            r14_write(7'h06, e);
        end
        begin
            logic [7:0] c, e;
            integer rounds;
            bit crc_on;
            // S3: a sample read whose header lost bit 7 (0xC0 -> 0x40, a write to the read-only window) returns STATUS
            // and zeros; its sample CRC (over the header 0xC0 and the six bytes) does not match, so the host cannot
            // take it for an empty word (an all-zero response matched the CRC of the six bytes alone)
            for (int crc = 0; crc < 2; crc++) begin
                if (crc) begin r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1; end
                r14_write(7'h06, 8'hFF);
                bfm_crc_en = 1'b0;
                spi_tx[0] = {1'b0, A_SAMPLE};               // SMP_HDR with its R/W bit lost
                for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00;
                spi_xfer(8, 0);
                bfm_crc_en = crc[0];
                c = tb_crc8_update(8'h00, SMP_HDR);
                for (int i = 1; i <= 6; i++) c = tb_crc8_update(c, spi_rx[i]);
                if (c === spi_rx[7])
                    fail($sformatf("S3: a sample read with its header turned into a write passes the sample CRC (CRC %0d)", crc));
                r14_read(7'h06, e);
                if (e[1] !== 1'b1) fail($sformatf("S3: ERR 0x%02h without FRAME_ERR for the corrupted sample read", e));
                r14_write(7'h06, 8'hFF);
                if (crc) begin r14_write(7'h55, 8'h00); bfm_crc_en = 1'b0; end
            end
            // S4: CRC on, a spoiled SOFT_RESET frame (wrong CRC), and the first probe's header loses its R/W bit
            // (0xD5 -> 0x55: a write of IF_CFG with a wrong CRC; the probe reads "CRC off"): the repeated check
            // converges (the second probe reads "CRC on", the SOFT_RESET is sent again with its CRC)
            r14_write(7'h55, 8'h01);
            bfm_crc_en = 1'b1;
            r14_write(7'h06, 8'hFF);
            spi_tx[0] = 8'h10; spi_tx[1] = 8'hA5; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // SOFT_RESET, wrong CRC
            host_soft_reset_check(8'h55, rounds);
            if (rounds == 0) fail("S4: the repeated SOFT_RESET check did not converge");
            soft_reset_probe(crc_on, "S4 after the check");
            if (crc_on || bfm_crc_en) fail("S4: CRC still on after the check (the SOFT_RESET not executed)");
            r14_read(7'h06, e);
            if (e[0] !== 1'b1) fail($sformatf("S4: ERR 0x%02h after the check, expected RESET_FLAG", e));
            r14_write(7'h06, 8'hFF);
            // S5 (step 3): the unprotected enabling write lands on T_ELEC (header 0x55 -> 0x51; a legal value, no
            // flag, MISO 0x00). The CRC read-back of IF_CFG shows CRC off, IF_CFG is written again in that mode, and
            // T_ELEC is written explicitly once CRC is on: T_ELEC ends at the host's value (0)
            spi_tx[0] = 8'h51; spi_tx[1] = 8'h01; spi_xfer(2, 0);
            if (spi_rx[1] !== 8'h00) fail("S5: MISO of the corrupted enabling write not 0x00");
            soft_reset_probe(crc_on, "S5 read-back");
            if (crc_on) fail("S5: CRC on although the enabling write went to T_ELEC");
            r14_write(7'h55, 8'h01);
            bfm_crc_en = 1'b1;
            soft_reset_probe(crc_on, "S5 read-back after the rewrite");
            if (!crc_on) fail("S5: CRC not on after the rewrite");
            r14_write(7'h51, 8'h00);                    // T_ELEC written explicitly (step 3)
            r14_read(7'h06, e);
            if (e !== 8'h00) fail($sformatf("S5: ERR 0x%02h after step 3", e));
            rt_read_expect(7'h51, 8'h00, "S5 T_ELEC after step 3");
            r14_write(7'h55, 8'h00);
            bfm_crc_en = 1'b0;
            r14_write(7'h06, 8'hFF);
        end
        $display("S  the SOFT_RESET check in both CRC modes; host checks under one-bit header errors (errors %0d)", errors);

        // ---------------- R: SOFT_RESET in the cycle of a tick, of an output time, after a store (NFR-06)
        phase = "R";
        begin
            integer k, runt0, falls0;
            logic [15:0] seq_r;
            logic [7:0] e;
            runt0 = n_runt;
            // R1: the tick that ends WARMUP (AFE_RST would be released at its edge; T_WARM 5 ms, its minimum)
            r14_cmd(8'h11);
            wait_state(4'd1, 50.0, "R1 WARMUP");
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.tick === 1'b1 && dut.seq_state === 4'd1 && dut.u_seq.timer === 18'd0 && !dut.cmd_valid) &&
                   k < 200000) begin @(posedge MCLK); #1; k++; end
            if (k >= 200000 || AFE_RST !== 1'b1) fail("R1 not exercised: no WARMUP-ending tick found");
            soft_now();
            if (dut.seq_state !== 4'd0 || AFE_RST !== 1'b1) fail($sformatf("R1: state %0d, AFE_RST %b after the SOFT_RESET",
                                                                         dut.seq_state, AFE_RST));
            r14_read(7'h06, e);
            if (e !== 8'h01) fail($sformatf("R1: ERR 0x%02h after the SOFT_RESET, expected RESET_FLAG only", e));
            r14_write(7'h06, 8'hFF);
            // R2: the tick of an APPLY in RUN (CPF_TRIM, OFM and OFEN would take the new shadow at its edge)
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "R2 RUN");
            r14_write(7'h24, 8'h0C);                    // CPF_TRIM 0x0C, range 1, M 10 (the reset values: 0x08, 0, 0)
            r14_write(7'h22, 8'h01);
            r14_write(7'h21, 8'h0A);
            @(posedge dut.tick); #(100.0);
            r14_cmd(8'h33);                             // pending until the tick after the next (the frame is longer)
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.tick === 1'b1 && dut.cmd_valid === 1'b1 && dut.cmd_code === 8'h33) && k < 2000) begin
                @(posedge MCLK); #1; k++;
            end
            if (k >= 2000 || CPF_TRIM !== 4'h8 || OFM !== 10'd0) fail("R2 not exercised: no APPLY tick found");
            soft_now();
            if (dut.seq_state !== 4'd0 || CPF_TRIM !== 4'h8 || OFM !== 10'd0 || OFEN !== 4'b0000 || AFE_RST !== 1'b1)
                fail($sformatf("R2: state %0d CPF_TRIM %h OFM %0d OFEN %b AFE_RST %b after the SOFT_RESET",
                               dut.seq_state, CPF_TRIM, OFM, OFEN, AFE_RST));
            r14_write(7'h06, 8'hFF);
            // R3: an output time in RUN (the sequencer would store it); R4: the cycle after a store into an empty
            // FIFO (DRDY_N would fall at its edge)
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "R3 RUN");
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.cic_stb === 1'b1 && dut.seq_state === 4'd6) && k < 40000) begin @(posedge MCLK); #1; k++; end
            if (k >= 40000) fail("R3 not exercised: no output time in RUN found");
            seq_r = dut.seq_cnt;
            soft_forced = 1'b1;
            force dut.soft_req = 1'b1;
            #1;
            if (dut.seq_store !== 1'b0 || dut.push_ok !== 1'b0) fail("R3: the sequencer stores in the commit cycle of SOFT_RESET");
            soft_now();                                 // still in that cycle: forced until just after its end
            if (dut.seq_cnt !== seq_r + 16'd1)          // the data path runs on: the output time is counted (DAT-03)
                fail($sformatf("R3: SEQ %0d -> %0d over a SOFT_RESET at an output time, expected one more", seq_r, dut.seq_cnt));
            r14_write(7'h06, 8'hFF);
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "R4 RUN");
            r14_cmd(8'h55);                             // FLUSH: the FIFO is empty until the next output
            repeat (600) @(posedge MCLK);
            falls0 = n_drdy_fall;
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.push_ok === 1'b1 && dut.fifo_level === 4'd0) && k < 40000) begin @(posedge MCLK); #1; k++; end
            @(posedge MCLK); #1;                        // the cycle after the store: not empty, DRDY_N still high
            if (k >= 40000 || dut.fifo_nonempty !== 1'b1 || DRDY_N !== 1'b1) fail("R4 not exercised: no store into an empty FIFO");
            soft_now();
            if (DRDY_N !== 1'b1 || n_drdy_fall != falls0) fail($sformatf("R4: DRDY_N fell (%0d falls) at the SOFT_RESET",
                                                                        n_drdy_fall - falls0));
            r14_write(7'h06, 8'hFF);
            // R4b: the same in pulse mode (IF_CFG.DRDY_MODE 1; audit round 6: R4 ran in level mode only)
            r14_write(7'h55, 8'h02);
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "R4b RUN");
            r14_cmd(8'h55);
            repeat (600) @(posedge MCLK);
            falls0 = n_drdy_fall;
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.push_ok === 1'b1 && dut.fifo_level === 4'd0) && k < 40000) begin @(posedge MCLK); #1; k++; end
            @(posedge MCLK); #1;
            if (k >= 40000 || DRDY_N !== 1'b1) fail("R4b not exercised: no store into an empty FIFO");
            soft_now();
            if (DRDY_N !== 1'b1 || n_drdy_fall != falls0) fail($sformatf("R4b: DRDY_N fell (%0d falls) at the SOFT_RESET (pulse mode)",
                                                                        n_drdy_fall - falls0));
            r14_write(7'h06, 8'hFF);
            // R9: RAW's timing runs from RESET_N alone (RST-02): a SOFT_RESET in the middle of a RAW word lets the word
            // end (8 RAW_CLK rises in that frame); RAW_EN is then 0 (no rise in the next frame)
            begin
                integer r0;
                r14_write(7'h11, 8'h3C); r14_write(7'h62, 8'h01); r14_write(7'h11, 8'h00);
                repeat (3 * 32) @(posedge MCLK);
                @(posedge CMP_STROBE);
                r0 = n_rawclk;
                repeat (10) @(posedge MCLK); #1;
                soft_now();
                @(posedge CMP_STROBE);
                if (n_rawclk - r0 != 8) fail($sformatf("R9: %0d RAW_CLK rises in the frame of the SOFT_RESET, expected 8", n_rawclk - r0));
                r0 = n_rawclk;
                @(posedge CMP_STROBE);
                if (n_rawclk != r0) fail("R9: RAW_CLK runs after the SOFT_RESET (RAW_EN is reset)");
                r14_write(7'h06, 8'hFF);
            end
            // R5: a SOFT_RESET over frame cycles 1..5 (committed in cycle 0): the frame strobes run from RESET_N alone
            // (TH_CAPTURE 1, DAC_LOAD 2, DAC_CLK 4: the strobe monitor checks every frame; RST-02)
            k = 0;
            @(posedge MCLK); #1;
            while (dut.cycle !== 5'd0 && k < 64) begin @(posedge MCLK); #1; k++; end
            if (k >= 64) fail("R5 not exercised: no frame cycle 0");
            soft_now();
            r14_write(7'h06, 8'hFF);
            // R6: the overload detector runs from RESET_N alone (RST-02): an overload that ends just before a
            // SOFT_RESET is still in its 32-frame window after it (OVL_NOW in the next STATUS)
            ovl_force = 1'b1;
            repeat (20 * 32) @(posedge MCLK);
            fork
                r14_cmd(8'hA5);                         // SOFT_RESET: committed about 8.6 us after its start
                begin #(7000.0); ovl_force = 1'b0; end  // the last overloaded frame about 2 us before the commit
            join
            #(1000.0);                                  // CS_N high for 1 us after a SOFT_RESET
            spi_tx[0] = 8'h83; spi_xfer(1, 0);          // the header only: STATUS
            if (spi_rx[0][1] !== 1'b1)
                fail($sformatf("R6: STATUS 0x%02h without OVL_NOW right after a SOFT_RESET (the overload detector must run on RESET_N)", spi_rx[0]));
            r14_read(7'h06, e);
            if (e !== 8'h01) fail($sformatf("R6: ERR 0x%02h after the SOFT_RESET, expected RESET_FLAG only", e));
            r14_write(7'h06, 8'hFF);
            // R7: SOFT_RESET in the cycle where the CIC decides ALIGN's clear (its step 3, the cycle before the output
            // time): the clear is not taken (fsm_spec: the sequencer is in RESET at that output time)
            r14_cmd(8'h11);
            wait_state(4'd4, 7000.0, "R7 ALIGN");
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.u_cic.step[3] === 1'b1 && dut.seq_state === 4'd4) && k < 40000) begin @(posedge MCLK); #1; k++; end
            if (k >= 40000 || dut.u_cic.nstb === '0) fail("R7 not exercised: no CIC decision cycle in ALIGN (or the CIC already cleared)");
            soft_now();
            if (dut.u_cic.nstb === '0) fail("R7: the CIC cleared by ALIGN although SOFT_RESET was committed in its decision cycle");
            if (dut.seq_state !== 4'd0) fail($sformatf("R7: state %0d after the SOFT_RESET", dut.seq_state));
            r14_write(7'h06, 8'hFF);
            // R8: SOFT_RESET in the output-time cycle of ALIGN: the clear was taken at the edge that started the cycle
            // (fsm_spec: cic_clear with the reset), the state goes to RESET, not FILL; SEQ counts the output time
            r14_cmd(8'h11);
            wait_state(4'd4, 7000.0, "R8 ALIGN");
            k = 0;
            @(posedge MCLK); #1;
            while (!(dut.cic_stb === 1'b1 && dut.seq_state === 4'd4) && k < 40000) begin @(posedge MCLK); #1; k++; end
            if (k >= 40000) fail("R8 not exercised: no output time in ALIGN");
            seq_r = dut.seq_cnt;
            soft_now();
            if (dut.u_cic.nstb !== '0 && dut.u_cic.nstb !== 1) fail($sformatf("R8: the CIC not cleared at the output time of ALIGN (nstb %0d)", dut.u_cic.nstb));
            if (dut.seq_state !== 4'd0) fail($sformatf("R8: state %0d after the SOFT_RESET, expected IDLE (not FILL)", dut.seq_state));
            if (dut.seq_cnt !== seq_r + 16'd1) fail($sformatf("R8: SEQ %0d -> %0d, expected one more", seq_r, dut.seq_cnt));
            r14_write(7'h06, 8'hFF);
            if (n_runt != runt0) fail($sformatf("R: %0d runts", n_runt - runt0));
        end
        $display("R  SOFT_RESET in the cycle of a tick, an output time, after a store: no runt; strobes and the overload detector through it (errors %0d)", errors);

        // ---------------- T: audit round 5, auditor C
        phase = "T";
        begin
            logic [7:0] e, st, f, lv0, v1;
            logic [15:0] seq2;
            integer k;
            bit found;
            real t0f;
            have_last = 1'b0;
            r14_write(7'h06, 8'hFF);
            r14_write(7'h07, 8'hFF);
            // T1: ALERT (STATUS bit 5, the default masks) from every ERR bit, each made through the pins
            check_status(8'h00, 8'h20, "T1 ALERT clear");
            r14_cmd(8'h77);                                                       alert_bit(8'h80, "CMD_ERR");
            spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_xfer(2, 3);                 alert_bit(8'h02, "FRAME_ERR");
            r14_write(7'h57, 8'h01);                                              alert_bit(8'h08, "ADDR_ERR");
            r14_write(7'h50, 8'h01);                                              alert_bit(8'h10, "RANGE_ERR");
            r14_write(7'h55, 8'h01);
            bfm_crc_en = 1'b1;
            spi_tx[0] = 8'h24; spi_tx[1] = 8'h09; spi_tx[2] = 8'h00; spi_xfer(3, 0); alert_bit(8'h04, "CRC_ERR");
            r14_write(7'h55, 8'h00);
            bfm_crc_en = 1'b0;
            r14_write(7'h22, 8'h01); r14_write(7'h21, 8'hC8);                    // M 200 above range 1
            r14_cmd(8'h11); repeat (600) @(posedge MCLK);                         alert_bit(8'h20, "CFG_ERR");
            r14_write(7'h21, 8'h00); r14_write(7'h22, 8'h00);
            r14_cmd(8'h11);
            wait_state(4'd1, 50.0, "T1 WARMUP");
            r14_cmd(8'h11); repeat (600) @(posedge MCLK);                         alert_bit(8'h40, "STATE_ERR");
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "T1 IDLE");
            r14_cmd(8'hA5); #(1500.0);                                            alert_bit(8'h01, "RESET_FLAG");
            // T2: ALERT from DFLAG.OVERRUN and DFLAG.OVL (ALERT_MASK_D 0x3)
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "T2 RUN");
            f = 8'h00; k = 0;
            while (f[0] !== 1'b1 && k < 40) begin repeat (16384) @(posedge MCLK); r14_read(7'h07, f); k++; end
            if (f[0] !== 1'b1) fail("T2: no OVERRUN with the FIFO left unread");
            r14_cmd(8'h55);                                                       // FLUSH: room again
            repeat (600) @(posedge MCLK);
            r14_read(7'h03, st);
            if (st[5] !== 1'b1) fail($sformatf("T2: STATUS 0x%02h, ALERT not set by DFLAG.OVERRUN", st));
            r14_write(7'h09, 8'h02);                    // OVERRUN masked
            r14_read(7'h03, st);
            if (st[5] !== 1'b0) fail($sformatf("T2: STATUS 0x%02h, ALERT with OVERRUN masked", st));
            r14_write(7'h09, 8'h03);
            r14_write(7'h07, 8'h01);
            r14_read(7'h03, st);
            if (st[5] !== 1'b0) fail($sformatf("T2: STATUS 0x%02h, ALERT after clearing OVERRUN", st));
            // an overload from the input 100 of an output interval to the input 120 or the end of the STATUS read in it,
            // whichever is later: OVL_NOW in STATUS and in the empty word is the detector's (1 during, 0 sixty frames
            // after, in the same interval), DFLAG.OVL is set (audit round 10: the release waited for the input 120
            // exactly, and a 3-byte read ending at about the input 123 pushed the checks into the next interval)
            k = 0;
            while (!(dut.u_cic.dcnt == 10'd100 && dut.cycle > 5'd3 && dut.cycle < 5'd16) && k < 80000) begin @(posedge MCLK); k++; end
            seq2 = dut.seq_cnt;                         // the checks below lie in this output interval
            ovl_force = 1'b1;
            repeat (10 * 32) @(posedge MCLK);
            r14_read(7'h03, st);
            if (st[1] !== 1'b1) fail($sformatf("T2: STATUS 0x%02h without OVL_NOW during an overload", st));
            while (!(dut.u_cic.dcnt >= 10'd120 && dut.u_cic.dcnt < 10'd900 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
            ovl_force = 1'b0;
            repeat (60 * 32) @(posedge MCLK);
            r14_read(7'h03, st);
            if (st[1] !== 1'b0 || st[5] !== 1'b1)
                fail($sformatf("T2: STATUS 0x%02h 60 frames after the overload: OVL_NOW must be 0, ALERT 1 (DFLAG.OVL)", st));
            while (DRDY_N === 1'b0) read_samples(1, -1, "T2 drain");            // samples of earlier intervals
            begin
                logic [7:0] es;
                logic [15:0] eq;
                logic [23:0] ed;
                bit eok;
                r14_sample(es, eq, ed, eok);
                if (!eok || es[7] !== 1'b0 || es[5] !== 1'b0 || es[3] !== 1'b1)    // ERR = ALERT: DFLAG.OVL (round 19)
                    fail($sformatf("T2: empty word status 0x%02h 60 frames after the overload (OVL is OVL_NOW, 0; ERR is ALERT, 1 from DFLAG.OVL)", es));
            end
            if (dut.seq_cnt !== seq2) fail("T2 not exercised: an output time came during the checks");
            r14_read(7'h07, f);
            if (f[1] !== 1'b1) fail("T2: no DFLAG.OVL after an overload in RUN");
            r14_write(7'h09, 8'h01);                    // OVL masked
            r14_read(7'h03, st);
            if (st[5] !== 1'b0) fail($sformatf("T2: STATUS 0x%02h, ALERT with DFLAG.OVL masked", st));
            r14_write(7'h09, 8'h03);
            r14_write(7'h07, 8'h02);
            r14_read(7'h03, st);
            if (st[5] !== 1'b0) fail($sformatf("T2: STATUS 0x%02h, ALERT after clearing OVL", st));
            // T3: a CRC read of ERR during which STATE_ERR is set (a START in RUN, refused at the tick that falls in
            // the read's data byte): the read CRC covers the byte sent, not the register's later value
            r14_write(7'h55, 8'h01);
            bfm_crc_en = 1'b1;
            r14_write(7'h06, 8'hFF);
            // 128 kHz: the 3-byte command frame (CRC on) started 4.5 us after a tick commits after the next tick
            // (+7.8 us), so the START is refused at the tick after that (+23.4 us), about 5.9 us into the read frame
            // that follows at once, inside its data byte (4.4..8.2 us)
            @(posedge dut.tick); #(4500.0);
            r14_cmd(8'h11);
            t0f = $realtime;
            r14_read(7'h06, e);                                                   // the BFM checks its CRC
            if (e !== 8'h00 || t_serr < t0f + 4400.0 || t_serr > t0f + 8200.0)
                fail($sformatf("T3 not exercised: ERR read 0x%02h, STATE_ERR set %0.0f ns into the frame", e, t_serr - t0f));
            r14_read(7'h06, e);
            if (e[6] !== 1'b1) fail($sformatf("T3: ERR 0x%02h without the STATE_ERR of the refused START", e));
            r14_write(7'h06, 8'hFF);
            r14_write(7'h55, 8'h00);
            bfm_crc_en = 1'b0;
            // T4: CHANGED for T_ELEC 255: 3 + 255 = 258 outputs (past 8 bits): the next 3 samples all marked
            r14_write(7'h51, 8'd255);
            while (DRDY_N === 1'b0) read_samples(1, -1, "T4 drain");
            read_samples(1, -1, "T4 sync");
            r14_write(7'h21, 8'h01);                                              // M 0 -> 1: one step
            r14_cmd(8'h44);
            repeat (600) @(posedge MCLK);
            if (dut.chg_cnt !== 9'd258) fail($sformatf("T4: CHANGED count %0d after a step with T_ELEC 255, expected 258", dut.chg_cnt));
            read_samples(3, 3, "T4 CHANGED of a 258-output mark");
            while (DRDY_N === 1'b0) read_samples(1, -1, "T4 drain");       // the empty word while the mark runs
            read_samples(1, -1, "T4 just after an output");                // (audit round 8: CHANGED 0 in it)
            begin
                logic [7:0] es; logic [15:0] eq; logic [23:0] ed; bit eok;
                r14_write(7'h06, 8'hFF); r14_write(7'h07, 8'hFF);       // no flag: the empty word's ERR (= ALERT) is 0
                r14_sample(es, eq, ed, eok);
                if (es[SMP_ERR_LSB] !== 1'b0 || spi_status[STATUS_ALERT_LSB] !== 1'b0)            // (audit round 14, auditor C: ERR tied to 1 passed)
                    fail($sformatf("T4: the empty word's ERR %b with STATUS.ALERT %b, both 0 expected (no flag set)", es[SMP_ERR_LSB], spi_status[STATUS_ALERT_LSB]));
                if (dut.chg_cnt == 9'd0) fail("T4 not exercised: no mark left at the empty word");
                if (!eok || es[7] !== 1'b0 || es[4] !== 1'b0 || es[2:0] !== 3'b000 || eq !== 16'd0 || ed !== 24'd0)
                    fail($sformatf("T4: the empty word while a mark runs: status 0x%02h SEQ %0d DATA %0d (VALID 0, CHANGED 0, reserved 0, SEQ 0, DATA 0 expected)", es, eq, ed));
            end
            r14_cmd(8'h22);                                                       // leaving RUN ends the mark
            wait_state(4'd0, 50.0, "T4 IDLE");
            repeat (2) @(posedge MCLK);                       // the count clears at the edge after IDLE begins
            if (dut.chg_cnt !== 9'd0)                        // (audit round 22, auditor C: checked only through
                fail($sformatf("T4: %0d CHANGED marks left after STOP (leaving RUN cancels them)", dut.chg_cnt));   // T6 / T11)
            // T5: an overload in WAIT_E does not set DFLAG.OVL (only FILL and RUN)
            r14_write(7'h51, 8'd2);
            r14_cmd(8'h11);
            wait_state(4'd3, 6000.0, "T5 WAIT_E");
            ovl_burst(1'b0, "T5 overload in WAIT_E");
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "T5 IDLE");
            r14_write(7'h51, 8'd0);
            // T6: APPLY_NR in RUN keeps the FIFO's samples; a FLUSH keeps the CHANGED marks still to come
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "T6 RUN");
            k = 0;
            while (dut.fifo_level < 4'd3 && k < 200000) begin @(posedge MCLK); k++; end
            r14_read(7'h05, lv0);
            r14_write(7'h21, 8'h02);                                              // M 1 -> 2: one step
            r14_cmd(8'h44);
            repeat (600) @(posedge MCLK);
            r14_read(7'h05, v1);
            if (lv0 < 8'd3 || v1 < lv0) fail($sformatf("T6: FIFO %0d -> %0d over an APPLY_NR in RUN", lv0, v1));
            while (DRDY_N === 1'b0) read_samples(1, -1, "T6 drain");
            read_samples(4, -1, "T6 past the first mark");
            r14_write(7'h51, 8'd10);
            read_samples(1, -1, "T6 sync");
            r14_write(7'h21, 8'h03);                                              // M 2 -> 3: 13 marks
            r14_cmd(8'h44);
            repeat (600) @(posedge MCLK);
            read_samples(2, 2, "T6 the mark before FLUSH");
            r14_cmd(8'h55);
            repeat (600) @(posedge MCLK);
            read_samples(12, 11, "T6 the 11 marks left after FLUSH");
            r14_write(7'h51, 8'd0);
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "T6 IDLE");
            r14_write(7'h21, 8'h00);
            // T7: 64 kHz; FLUSH then START back to back, the first frame started 13.8 us + k half-MCLK after a tick,
            // until START's commit falls in the cycle the tick takes FLUSH: START is then the new pending command,
            // executed at the next tick (WARMUP), without STATE_ERR
            r14_write(7'h26, 8'h00);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
            found = 1'b0;
            for (k = 0; k < 70 && !found; k++) begin
                integer nack0;
                nack0 = n_ack_commit;
                @(posedge dut.tick); #(13800.0 + k * TMCLK / 2.0);
                spi_tidle = 125.0;
                r14_cmd(8'h55);
                r14_cmd(8'h11);
                spi_tidle = 600.0;
                repeat (1200) @(posedge MCLK);
                if (n_ack_commit != nack0) begin
                    found = 1'b1;
                    if (dut.seq_state !== 4'd1)
                        fail($sformatf("T7: START committed in FLUSH's acknowledge cycle not executed (state %0d)", dut.seq_state));
                    r14_read(7'h06, e);
                    if (e[6] !== 1'b0) fail($sformatf("T7: ERR 0x%02h, STATE_ERR for START committed in the acknowledge cycle", e));
                end
                if (dut.seq_state !== 4'd0) begin r14_cmd(8'h22); wait_state(4'd0, 50.0, "T7 IDLE"); end
                r14_write(7'h06, 8'hFF);
            end
            if (!found) fail("T7 not exercised: no START committed in FLUSH's acknowledge cycle");
            // T8: RUN; extreme codes for the inputs 996..1015 of an output interval (the last 8 inputs normal): the
            // samples of that interval and the next two carry OVL, the third after it none (the detector's count
            // stays high 31 frames into the next interval, which holds no extreme code)
            r14_write(7'h26, 8'h01);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
            r14_write(7'h07, 8'hFF);
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "T8 RUN");
            while (DRDY_N === 1'b0) read_samples(1, -1, "T8 drain");
            begin
                logic [15:0] k8, sq;
                logic [7:0] st8;
                logic [23:0] d8;
                bit ok8;
                integer got;
                k = 0;
                while (!(dut.u_cic.dcnt == 10'd996 && dut.cycle > 5'd3 && dut.cycle < 5'd16) && k < 80000) begin @(posedge MCLK); k++; end
                k8 = dut.seq_cnt;                       // the SEQ of this interval's output
                ovl_force = 1'b1;
                while (!(dut.u_cic.dcnt == 10'd1016 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
                ovl_force = 1'b0;
                got = 0;
                while (got < 5) begin
                    while (DRDY_N !== 1'b0) @(posedge MCLK);
                    r14_sample(st8, sq, d8, ok8);
                    if (!ok8 || st8[7] !== 1'b1) fail($sformatf("T8: sample SEQ %0d not valid", sq));
                    if (sq >= k8) begin
                        if (st8[5] !== ((sq - k8) < 16'd3)) fail($sformatf("T8: sample SEQ %0d (interval +%0d) OVL %b, expected %b",
                                                                         sq, sq - k8, st8[5], (sq - k8) < 16'd3));
                        got = got + 1;
                    end
                end
            end
            // T12 (audit round 9): extreme codes for the inputs 1004..1023, the interval's last: OVL on that interval's
            // sample and the next two, not the third (a detector taking its code one frame late marks the third)
            while (DRDY_N === 1'b0) read_samples(1, -1, "T12 drain");
            begin
                logic [15:0] k12, sq;
                logic [7:0] st12;
                logic [23:0] d12;
                bit ok12;
                integer got;
                k = 0;
                while (!(dut.u_cic.dcnt == 10'd1004 && dut.cycle > 5'd3 && dut.cycle < 5'd16) && k < 80000) begin @(posedge MCLK); k++; end
                k12 = dut.seq_cnt;
                ovl_force = 1'b1;
                while (!(dut.u_cic.dcnt == 10'd0 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
                ovl_force = 1'b0;
                got = 0;
                while (got < 5) begin
                    while (DRDY_N !== 1'b0) @(posedge MCLK);
                    r14_sample(st12, sq, d12, ok12);
                    if (!ok12 || st12[7] !== 1'b1) fail($sformatf("T12: sample SEQ %0d not valid", sq));
                    if (sq >= k12) begin
                        if (st12[5] !== ((sq - k12) < 16'd3)) fail($sformatf("T12: sample SEQ %0d (interval +%0d) OVL %b, expected %b",
                                                                           sq, sq - k12, st12[5], (sq - k12) < 16'd3));
                        got = got + 1;
                    end
                end
            end
            // T13 (audit round 14, auditor B): a sample read whose header's copy falls in the very cycle of a store into
            // the empty FIFO. The CS_N fall stepped by a quarter MCLK over 6 MCLK around the store, one point per output
            // time; every stored sample reaches the host (SEQ without a gap). A copy the FIFO saw one MCLK late lost the
            // sample silently and passed every test
            begin
                logic [15:0] sq13, last13;
                logic [7:0] st13;
                logic [23:0] d13;
                bit ok13, have13;
                int nd13;                               // drain reads (bounded: audit round 15)
                integer gap13, coinc0;
                real t0_13, t_fall13, tm13;
                have13 = 1'b0; gap13 = 0; coinc0 = n_coinc13;
                @(posedge MCLK); tm13 = $realtime; @(posedge MCLK); tm13 = $realtime - tm13;   // the simulated MCLK period
                @(posedge dut.push_ok);                 // (its half period rounds to 1 ps: 32768 MCLK are 1.0000138 ms)
                t0_13 = $realtime;
                for (int p = 0; p < 24; p++) begin
                    nd13 = 0;
                    do begin                                // drain: the FIFO empty before the next store
                        r14_sample(st13, sq13, d13, ok13);
                        nd13 = nd13 + 1;
                        if (ok13 && st13[SMP_VALID_LSB] === 1'b1) begin
                            if (have13 && sq13 !== last13 + 16'd1) begin
                                gap13 = gap13 + 1;
                                fail($sformatf("T13 point %0d: SEQ %0d after %0d (a sample lost)", p, sq13, last13));
                            end
                            last13 = sq13; have13 = 1'b1;
                        end
                    end while (!(ok13 && st13[SMP_VALID_LSB] === 1'b0 && spi_status[STATUS_DATA_LSB] === 1'b0) && nd13 < 3 * FD);
                    if (nd13 >= 3 * FD)                     // (audit round 15: READY and DATA crosswise hung here until the watchdog)
                        fail($sformatf("T13 point %0d: no empty word with STATUS.DATA 0 in %0d reads (the FIFO holds %0d)", p, nd13, FD));
                    t_fall13 = t0_13 + (p + 1) * 32768.0 * tm13 - (spi_tcss + 7.0 * (spi_high + spi_low))
                               - 3.0 * tm13 + 0.25 * tm13 * p;
                    #(t_fall13 - $realtime);
                    r14_sample(st13, sq13, d13, ok13);
                    if (ok13 && st13[SMP_VALID_LSB] === 1'b1) begin
                        if (have13 && sq13 !== last13 + 16'd1) begin
                            gap13 = gap13 + 1;
                            fail($sformatf("T13 point %0d: SEQ %0d after %0d (a sample lost)", p, sq13, last13));
                        end
                        last13 = sq13; have13 = 1'b1;
                    end
                end
                if (n_coinc13 == coinc0) fail("T13 not exercised: no copy in the cycle of a store");
            end
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "T8 IDLE");
            // T9: an overload in ALIGN ending 12 frames before its clear (inputs 992..1011): no DFLAG.OVL (FILL and RUN
            // only, and the tail holds no extreme code) and no OVL on the first stored sample (its window is after
            // the clear). ALIGN must have 40 inputs left when it starts (else START again)
            found = 1'b0;
            for (k = 0; k < 4 && !found; k++) begin
                r14_write(7'h06, 8'hFF);
                r14_write(7'h07, 8'hFF);
                r14_cmd(8'h11);
                wait_state(4'd4, 7000.0, "T9 ALIGN");
                if (dut.u_cic.dcnt <= 10'd984) begin
                    found = 1'b1;
                    while (!(dut.u_cic.dcnt == 10'd992 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
                    ovl_force = 1'b1;
                    while (!(dut.u_cic.dcnt == 10'd1012 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
                    ovl_force = 1'b0;
                    if (dut.seq_state !== 4'd4) fail("T9 not exercised: the overload left ALIGN");
                    wait_state(4'd6, 4000.0, "T9 RUN");
                    begin
                        logic [7:0] st9;
                        logic [15:0] sq9;
                        logic [23:0] d9;
                        bit ok9;
                        while (DRDY_N !== 1'b0) @(posedge MCLK);
                        r14_sample(st9, sq9, d9, ok9);
                        if (!ok9 || st9[7] !== 1'b1 || st9[5] !== 1'b0)
                            fail($sformatf("T9: the first stored sample status 0x%02h (OVL from an overload before the clear)", st9));
                    end
                    r14_read(7'h07, f);
                    if (f[1] !== 1'b0) fail($sformatf("T9: DFLAG 0x%02h, OVL set by an overload that ended in ALIGN", f));
                end
                r14_cmd(8'h22);
                wait_state(4'd0, 50.0, "T9 IDLE");
            end
            if (!found) fail("T9 not exercised: ALIGN never had 40 inputs left");
            // T10: an overload on the inputs 100..119 of the first FILL interval: the first stored sample (its window is
            // FILL's three intervals) carries OVL, the next one not; DFLAG.OVL is set (FILL)
            r14_write(7'h06, 8'hFF);
            r14_write(7'h07, 8'hFF);
            r14_cmd(8'h11);
            wait_state(4'd5, 7000.0, "T10 FILL");
            while (!(dut.u_cic.dcnt == 10'd100 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
            if (dut.seq_state !== 4'd5) fail("T10 not exercised: not in FILL");
            ovl_force = 1'b1;
            while (!(dut.u_cic.dcnt == 10'd120 && dut.cycle > 5'd3 && dut.cycle < 5'd16)) @(posedge MCLK);
            ovl_force = 1'b0;
            wait_state(4'd6, 4000.0, "T10 RUN");
            begin
                logic [7:0] s10;
                logic [15:0] q10;
                logic [23:0] d10;
                bit ok10;
                for (int i = 0; i < 2; i++) begin
                    while (DRDY_N !== 1'b0) @(posedge MCLK);
                    r14_sample(s10, q10, d10, ok10);
                    if (!ok10 || s10[7] !== 1'b1 || s10[5] !== (i == 0))
                        fail($sformatf("T10: stored sample %0d after FILL: status 0x%02h, OVL expected %0d", i, s10, i == 0));
                end
            end
            r14_read(7'h07, f);
            if (f[1] !== 1'b1) fail($sformatf("T10: DFLAG 0x%02h without OVL after an overload in FILL", f));
            r14_write(7'h07, 8'hFF);
            // T11: CHANGED counts output times: with the FIFO full, a step with T_ELEC 3 marks the next 6 output times,
            // all dropped (OVERRUN); the samples stored after them carry no CHANGED
            r14_write(7'h51, 8'd3);
            f = 8'h00; k = 0;
            while (f[0] !== 1'b1 && k < 40) begin repeat (16384) @(posedge MCLK); r14_read(7'h07, f); k++; end
            if (f[0] !== 1'b1) fail("T11 not exercised: the FIFO never full");
            rt_read_expect(7'h05, FDEPTH, "T11 FIFO_LEVEL of a full FIFO");
            r14_write(7'h21, 8'h01);                    // M 0 -> 1: one step, 3 + 3 marks
            r14_cmd(8'h44);
            repeat (600) @(posedge MCLK);
            if (dut.chg_cnt !== 9'd6) fail($sformatf("T11: CHANGED count %0d, expected 6", dut.chg_cnt));
            repeat (7 * 32768) @(posedge MCLK);         // 7 output times, all dropped
            if (dut.chg_cnt !== 9'd0) fail($sformatf("T11: CHANGED count %0d after 7 dropped output times, expected 0", dut.chg_cnt));
            r14_write(7'h07, 8'hFF);
            while (DRDY_N === 1'b0) read_samples(1, -1, "T11 drain");
            read_samples(3, 0, "T11 no CHANGED after the marks were spent on dropped outputs");
            r14_write(7'h51, 8'd0);
            r14_write(7'h21, 8'h00);
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "T11 IDLE");
            r14_write(7'h26, 8'h01);
            r14_cmd(8'h33);
            repeat (2000) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
        end
        $display("T  ALERT from every flag, a read CRC across a change, CHANGED 258, OVL in WAIT_E, FIFO and marks over APPLY_NR and FLUSH, a command in the ack cycle (errors %0d)", errors);

        // ---------------- U: a command frame turned into a read by an R/W flip (audit round 8, host procedure step 4):
        // the host's frame check (rule (a)) sees MISO after the header that is not 0x00; the chip neither executes the
        // command nor flags anything (ERR 0x00, CMD_PENDING 0), so its execution must be judged by its effect
        phase = "U";
        r14_write(7'h55, 8'h01);
        bfm_crc_en = 1'b1;
        r14_write(7'h06, 8'hFF);
        begin
            logic [7:0] st, a0, a1;
            spi_tx[0] = 8'h90; spi_tx[1] = 8'h11; spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, 8'h10), 8'h11);
            spi_xfer(3, 0);                             // START with its R/W bit flipped: a CRC read of COMMAND
            if (spi_rx[1] === 8'h00 && spi_rx[2] === 8'h00) fail("U1: MISO after a flipped START all 0x00 (rule (a) cannot see it)");
            repeat (1200) @(posedge MCLK);              // more than one tick period
            expect_err_exact(8'h00, "U1 a flipped START flags nothing");
            check_status(8'h00, 8'h10, "U1 no command pending");
            if (dut.seq_state !== 4'd0) fail($sformatf("U1: state %0d after a flipped START, expected IDLE", dut.seq_state));
            r14_cmd(8'h11);
            wait_state(4'd6, 10000.0, "U2 RUN");
            r14_read(7'h34, a0);                        // CPF_TRIM active
            r14_write(7'h24, a0 ^ 8'h01);               // a new shadow
            spi_tx[0] = 8'h90; spi_tx[1] = 8'h33; spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, 8'h10), 8'h33);
            spi_xfer(3, 0);                             // APPLY with its R/W bit flipped
            if (spi_rx[1] === 8'h00 && spi_rx[2] === 8'h00) fail("U2: MISO after a flipped APPLY all 0x00");
            repeat (3 * 32768 + 16384) @(posedge MCLK); // 3.5 ms: an executed APPLY would still be out of RUN
            expect_err_exact(8'h00, "U2 a flipped APPLY flags nothing");
            if (dut.seq_state !== 4'd6) fail($sformatf("U2: state %0d after a flipped APPLY in RUN, expected RUN", dut.seq_state));
            r14_read(7'h34, a1);
            if (a1 !== a0) fail($sformatf("U2: CPF_TRIM active 0x%02h after a flipped APPLY, expected 0x%02h", a1, a0));
            r14_write(7'h24, a0);
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "U IDLE");
        end
        r14_write(7'h55, 8'h00);
        bfm_crc_en = 1'b0;
        // U3 / U4 (audit round 9, auditor B): CRC off, a 2-byte read of AFE_IBIAS (0xA3) whose R/W bit flips is a legal
        // write of 0x00 and commits silently (the host procedure therefore reads 3 bytes or more with CRC off); made 3
        // bytes long, the same flip is an overlong write: FRAME_ERR and nothing written
        r14_write(7'h06, 8'hFF);
        spi_tx[0] = 8'h23; spi_tx[1] = 8'h00; spi_xfer(2, 0);
        rt_read_expect(7'h23, 8'h00, "U3 a flipped 2-byte read of AFE_IBIAS wrote 0x00 (the CRC-off exposure)");
        expect_err_exact(8'h00, "U3 the flipped 2-byte read flags nothing");
        r14_write(7'h23, 8'h03);
        spi_tx[0] = 8'h23; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00; spi_xfer(3, 0);
        expect_err_exact(8'h02, "U4 a flipped 3-byte read is an overlong write: FRAME_ERR");
        rt_read_expect(7'h23, 8'h03, "U4 AFE_IBIAS not written by the flipped 3-byte read");
        $display("U  command frames turned into reads: not executed, nothing flagged (errors %0d)", errors);

        // ---------------- V: APPLY_NR in IDLE, and APPLY and APPLY_NR in RECOVER, WAIT_E, ALIGN and FILL (audit round 9,
        // auditor C: none was in the end-to-end replay); range 1, T_ELEC 2 ms; each taken at its tick, with its effect at
        // the pins (OFM) or in STATE, and no flag
        phase = "V";
        begin
            integer tries;
            logic [9:0] m;
            r14_write(7'h51, 8'd2);
            r14_write(7'h22, 8'h01);
            r14_write(7'h21, 8'd10);
            r14_cmd(8'h33);                             // range 1, M 10 (IDLE)
            repeat (600) @(posedge MCLK);
            m = 10'd10;
            // V1: APPLY_NR in IDLE
            m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
            expect_err_exact(8'h00, "V1 APPLY_NR in IDLE");
            if (OFM !== m || dut.seq_state !== 4'd0) fail($sformatf("V1: OFM %0d state %0d after APPLY_NR in IDLE", OFM, dut.seq_state));
            r14_cmd(8'h11);
            // V2: APPLY_NR in RECOVER (applied, stays)
            wait_state(4'd2, 7000.0, "V2 RECOVER");
            m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
            expect_err_exact(8'h00, "V2 APPLY_NR in RECOVER");
            if (OFM !== m) fail($sformatf("V2: OFM %0d after APPLY_NR in RECOVER, expected %0d", OFM, m));
            // V3: APPLY_NR in WAIT_E (applied, the wait starts again)
            wait_state(4'd3, 400.0, "V3 WAIT_E");
            m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
            expect_err_exact(8'h00, "V3 APPLY_NR in WAIT_E");
            if (OFM !== m || dut.seq_state !== 4'd3) fail($sformatf("V3: OFM %0d state %0d after APPLY_NR in WAIT_E", OFM, dut.seq_state));
            // V4: APPLY_NR in ALIGN (applied; T_ELEC > 0: back to WAIT_E). ALIGN may end too soon: then into FILL,
            // where an APPLY_NR also returns to WAIT_E, and again (up to 4 tries)
            tries = 0;
            begin
                bit done4, done5;
                done4 = 1'b0; done5 = 1'b0;
                while (!(done4 && done5) && tries < 8) begin
                    tries = tries + 1;
                    while (!(dut.seq_state === 4'd4 || dut.seq_state === 4'd5)) @(posedge MCLK);
                    if (dut.seq_state === 4'd4 && !done4 && dut.u_cic.dcnt < 10'd960) begin
                        m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
                        expect_err_exact(8'h00, "V4 APPLY_NR in ALIGN");
                        if (OFM !== m || dut.seq_state !== 4'd3) fail($sformatf("V4: OFM %0d state %0d after APPLY_NR in ALIGN (WAIT_E expected)", OFM, dut.seq_state));
                        done4 = 1'b1;
                    end else begin
                        wait_state(4'd5, 1100.0, "V5 FILL");
                        m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
                        expect_err_exact(8'h00, "V5 APPLY_NR in FILL");
                        if (OFM !== m || dut.seq_state !== 4'd3) fail($sformatf("V5: OFM %0d state %0d after APPLY_NR in FILL (WAIT_E expected)", OFM, dut.seq_state));
                        done5 = 1'b1;
                    end
                end
                if (!(done4 && done5)) fail("V4 / V5 not exercised: ALIGN never long enough");
            end
            // V6..V9: APPLY in WAIT_E, RECOVER, ALIGN, FILL: each goes to PRE (with its pulse)
            r14_cmd(8'h33); wait_state(4'd7, 50.0, "V6 PRE after APPLY in WAIT_E");   // in WAIT_E now
            expect_err_exact(8'h00, "V6 APPLY in WAIT_E");
            wait_state(4'd2, 400.0, "V7 RECOVER");
            r14_cmd(8'h33); wait_state(4'd7, 50.0, "V7 PRE after APPLY in RECOVER");
            expect_err_exact(8'h00, "V7 APPLY in RECOVER");
            r14_write(7'h51, 8'd0);                     // T_ELEC 0 (immediate): RECOVER -> ALIGN from now
            wait_state(4'd2, 400.0, "V8 RECOVER");      // V7's pulse over (an APPLY in PRE or PULSE is refused)
            r14_cmd(8'h33); wait_state(4'd7, 50.0, "V8 PRE after APPLY in RECOVER (T_ELEC 0)");
            expect_err_exact(8'h00, "V8 APPLY in RECOVER (T_ELEC 0)");
            tries = 0;
            begin
                bit done8;
                done8 = 1'b0;
                while (!done8 && tries < 6) begin
                    tries = tries + 1;
                    wait_state(4'd4, 2000.0, "V8 ALIGN");
                    if (dut.u_cic.dcnt < 10'd960) begin
                        r14_cmd(8'h33); wait_state(4'd7, 50.0, "V8 PRE after APPLY in ALIGN");
                        expect_err_exact(8'h00, "V8 APPLY in ALIGN");
                        done8 = 1'b1;
                    end else begin
                        wait_state(4'd5, 1100.0, "V8 FILL");
                        r14_cmd(8'h33); wait_state(4'd7, 50.0, "V9 PRE after APPLY in FILL");   // and APPLY in FILL
                        expect_err_exact(8'h00, "V9 APPLY in FILL");
                    end
                end
                if (!done8) fail("V8 not exercised: ALIGN never long enough");
            end
            wait_state(4'd5, 3000.0, "V9 FILL");
            r14_cmd(8'h33); wait_state(4'd7, 50.0, "V9 PRE after APPLY in FILL");
            expect_err_exact(8'h00, "V9 APPLY in FILL");
            // V10 (audit round 10, auditor C: V took ALIGN's and FILL's APPLY_NR with T_ELEC > 0 only, and no refusal
            // in PRE or PULSE): with T_ELEC = 0, APPLY_NR in ALIGN applies and stays in ALIGN (its clear still to come),
            // in FILL applies and returns to ALIGN (the CIC cleared again); APPLY_NR in PRE and APPLY in PULSE are refused
            // with STATE_ERR only, the state going on (T_PRE 10, 78 us, so that a command written after PRE began is
            // taken in PRE)
            begin
                bit done_a, done_f;
                done_a = 1'b0; done_f = 1'b0; tries = 0;
                while (!(done_a && done_f) && tries < 8) begin
                    tries = tries + 1;
                    while (!(dut.seq_state === 4'd4 || dut.seq_state === 4'd5)) @(posedge MCLK);
                    if (dut.seq_state === 4'd4 && !done_a && dut.u_cic.dcnt < 10'd960) begin
                        m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
                        expect_err_exact(8'h00, "V10 APPLY_NR in ALIGN (T_ELEC 0)");
                        if (OFM !== m) fail($sformatf("V10: OFM %0d after APPLY_NR in ALIGN, expected %0d", OFM, m));
                        if (dut.seq_state !== 4'd4 && dut.seq_state !== 4'd5)
                            fail($sformatf("V10: state %0d after APPLY_NR in ALIGN with T_ELEC 0 (ALIGN stays)", dut.seq_state));
                        done_a = 1'b1;
                    end else begin
                        wait_state(4'd5, 1100.0, "V10 FILL");
                        m = m + 10'd1; r14_write(7'h21, m[7:0]); r14_cmd(8'h44); repeat (600) @(posedge MCLK);
                        expect_err_exact(8'h00, "V10 APPLY_NR in FILL (T_ELEC 0)");
                        if (OFM !== m) fail($sformatf("V10: OFM %0d after APPLY_NR in FILL, expected %0d", OFM, m));
                        if (dut.seq_state !== 4'd4 && dut.seq_state !== 4'd5)
                            fail($sformatf("V10: state %0d after APPLY_NR in FILL with T_ELEC 0 (back to ALIGN)", dut.seq_state));
                        done_f = 1'b1;
                    end
                end
                if (!(done_a && done_f)) fail("V10 not exercised: ALIGN never long enough");
            end
            r14_write(7'h53, 8'd10);                    // T_PRE 78 us
            r14_cmd(8'h33); wait_state(4'd7, 50.0, "V10 PRE");
            expect_err_exact(8'h00, "V10 APPLY into PRE");
            r14_cmd(8'h44); repeat (300) @(posedge MCLK);
            expect_err_exact(8'h40, "V10 APPLY_NR in PRE: STATE_ERR only");
            if (dut.seq_state !== 4'd7) fail($sformatf("V10: state %0d after the APPLY_NR refused in PRE (PRE goes on)", dut.seq_state));
            wait_state(4'd8, 200.0, "V10 PULSE");
            r14_cmd(8'h33); repeat (300) @(posedge MCLK);
            expect_err_exact(8'h40, "V10 APPLY in PULSE: STATE_ERR only");
            if (dut.seq_state !== 4'd8) fail($sformatf("V10: state %0d after the APPLY refused in PULSE (PULSE goes on)", dut.seq_state));
            r14_write(7'h53, 8'd3);
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "V IDLE");
            r14_write(7'h21, 8'h00); r14_write(7'h22, 8'h00); r14_cmd(8'h33);
            repeat (600) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
            // V11 (audit round 14, auditors A and B: the host procedure's step 4): an APPLY executed in FILL and issued
            // again by the host at 1 MHz once CMD_PENDING is 0: the second is refused with STATE_ERR alone (the chip is
            // in PRE or PULSE, which only an APPLY enters), and the active copy holds the setting; STATE is not read
            begin
                logic [7:0] v11;
                r14_cmd(8'h11);
                wait_state(4'd5, 12000.0, "V11 FILL");
                r14_write(7'h24, 8'h06);                // CPF_TRIM shadow 6
                spi_high = 500.0; spi_low = 500.0;      // 1 MHz
                r14_cmd(8'h33);
                do r14_read(7'h03, v11); while (v11[STATUS_CMD_PENDING_LSB] === 1'b1);    // CMD_PENDING
                r14_cmd(8'h33);                         // the host's re-issue
                do r14_read(7'h03, v11); while (v11[STATUS_CMD_PENDING_LSB] === 1'b1);
                expect_err_exact(8'h40, "V11 the re-issued APPLY after an executed one: STATE_ERR alone");
                rt_read_expect(7'h34, 8'h06, "V11 the active CPF_TRIM after the APPLY");
                spi_high = 250.0; spi_low = 250.0;
                r14_cmd(8'h22);
                wait_state(4'd0, 50.0, "V11 IDLE");
                r14_write(7'h24, 8'h08); r14_cmd(8'h33);
                repeat (600) @(posedge MCLK);
                r14_write(7'h06, 8'hFF);
            end
            // V12 (audit round 14, auditor C: REG-03 was not checked, and a STOP that applied the shadows in WARMUP or
            // PULSE passed every test, every STOP there being sent with the shadows equal to the active copies): STOP in
            // WARMUP and in PULSE with a shadow differing from its active copy applies nothing
            r14_write(7'h24, 8'h05); r14_cmd(8'h11);   // START: CPF_TRIM 5 applied
            wait_state(4'd1, 50.0, "V12 WARMUP");
            r14_write(7'h24, 8'h09);                    // the shadow differs from the active copy
            r14_cmd(8'h22);
            wait_state(4'd0, 50.0, "V12 IDLE after a STOP in WARMUP");
            repeat (300) @(posedge MCLK);
            if (CPF_TRIM !== 4'd5) fail($sformatf("V12: CPF_TRIM %0d after a STOP in WARMUP, expected 5 (REG-03)", CPF_TRIM));
            rt_read_expect(7'h34, 8'h05, "V12 the active CPF_TRIM after a STOP in WARMUP");
            r14_write(7'h24, 8'h06); r14_cmd(8'h11);
            wait_state(4'd6, 12000.0, "V12 RUN");
            r14_write(7'h24, 8'h07); r14_cmd(8'h33);   // APPLY: CPF_TRIM 7, PRE, PULSE
            wait_state(4'd8, 300.0, "V12 PULSE");
            r14_write(7'h24, 8'h0A);                    // the shadow differs
            r14_cmd(8'h22);
            wait_state(4'd0, 300.0, "V12 IDLE after a STOP in PULSE");
            repeat (300) @(posedge MCLK);
            if (CPF_TRIM !== 4'd7) fail($sformatf("V12: CPF_TRIM %0d after a STOP in PULSE, expected 7 (REG-03)", CPF_TRIM));
            rt_read_expect(7'h34, 8'h07, "V12 the active CPF_TRIM after a STOP in PULSE");
            r14_write(7'h24, 8'h08); r14_cmd(8'h33);
            repeat (600) @(posedge MCLK);
            r14_write(7'h06, 8'hFF);
            // V13 (audit round 15, auditor A: round 14's AFE_RST edge monitor, its rate taken from the clock generator,
            // was exercised by no phase): in RUN at 128 kHz an APPLY that changes the chopper to 64 kHz, then a STOP
            // taken in PRE at the next tick (the host's SPI at 2 MHz, SPI-01: the APPLY written 100 MCLK after a tick of
            // the target's half of the 512-MCLK superperiod commits about 140 MCLK before the tick after next, which takes
            // it, and the STOP written right after it commits about 150 MCLK after that tick; audit round 17, auditor C:
            // round 15 drove a 3.6 MHz SCLK, outside SPI-01; a STOP written after PRE begins commits at least 262 MCLK
            // later at 2 MHz and misses the first tick in PRE). The APPLY taken in frame 1 (k 0): the STOP's tick is the next
            // 128 kHz one, before the rate's wrap, with the active copy already at 64 kHz; in frame 9 (k 1): the first
            // 64 kHz tick after the wrap. AFE_RST rises 256 or 320 MCLK after the APPLY's tick (7.8 and 9.8 us after the
            // DAC change, requirements 4.10), its edge where the monitor expects it, nothing flagged, and it stays high
            // into the next START's WARMUP
            for (int k = 0; k < 2; k++) begin
                real t_dac;
                r14_write(7'h26, 8'h01); r14_cmd(8'h11);           // START at 128 kHz
                wait_state(4'd6, 12000.0, "V13 RUN");
                if (dut.u_clkgen.fast !== 1'b1) fail("V13: not at 128 kHz in RUN");
                r14_write(7'h26, 8'h00);                            // the shadow: 64 kHz
                do @(posedge dut.tick); while (dut.u_clkgen.cnt[8] !== (k == 0 ? 1'b0 : 1'b1));   // the target's half
                repeat (100) @(posedge MCLK);
                r14_cmd(8'h33);                                     // APPLY: taken at the tick after next, frame 1 or 9
                r14_cmd(8'h22);                                     // STOP: taken at the first tick in PRE
                wait_state(4'd0, 100.0, "V13 IDLE after a STOP in PRE");
                t_dac = t_state[4'd7];                              // PRE entered at the APPLY's tick (the DAC change)
                if (AFE_RST !== 1'b1) fail("V13: AFE_RST low after the STOP in PRE");
                if (afe_rise_fast !== (k == 0) || afe_rise_act !== 1'b0)
                    fail($sformatf("V13 case %0d not exercised as designed: at the AFE_RST rise the clock generator ran at %s kHz, the active copy at %s kHz",
                                   k, afe_rise_fast ? "128" : "64", afe_rise_act ? "128" : "64"));
                if ((t_afe_rise - t_dac) / TMCLK < (k == 0 ? 255.5 : 319.5) || (t_afe_rise - t_dac) / TMCLK > (k == 0 ? 256.5 : 320.5))
                    fail($sformatf("V13 case %0d: AFE_RST rose %0.1f MCLK after the APPLY's tick, expected %0d", k,
                                   (t_afe_rise - t_dac) / TMCLK, k == 0 ? 256 : 320));
                expect_err_exact(8'h00, $sformatf("V13 case %0d: the APPLY and the STOP in PRE", k));
                r14_cmd(8'h11);                                     // START: AFE_RST stays high into WARMUP
                wait_state(4'd1, 50.0, "V13 WARMUP");
                if (AFE_RST !== 1'b1 || t_afe_fall > t_afe_rise) fail("V13: AFE_RST released between the STOP in PRE and WARMUP");
                r14_cmd(8'h22);
                wait_state(4'd0, 50.0, "V13 IDLE");
            end
            r14_write(7'h26, 8'h01); r14_cmd(8'h33);                // 128 kHz again (APPLY in IDLE): its tick (up to
            repeat (1200) @(posedge MCLK);                          // 512 MCLK at 64 kHz), then the wrap (512 more)
            if (dut.u_clkgen.fast !== 1'b1) fail("V13: 128 kHz not back");
            r14_write(7'h06, 8'hFF);
        end
        $display("V  APPLY and APPLY_NR in IDLE, RECOVER, WAIT_E, ALIGN, FILL; a re-issued APPLY; STOP applies nothing; STOP in PRE across a rate change (errors %0d)", errors);

        // ---------------- K: SEQ wraps from 0xFFFF to 0 (forced; the last phase, outside the golden comparison)
        phase = "K";
        log_on = 1'b0;
        r14_cmd(8'h11);
        wait_state(4'd6, 10000.0, "K RUN");
        begin
            logic [7:0] st; logic [15:0] sq, prev; logic [23:0] d; bit ok;
            @(posedge dut.cic_stb);
            @(posedge MCLK); #1;                        // after the edge that stored this output and counted it
            dut.seq_cnt = 16'hFFFE;                     // deposit: the next output takes 0xFFFE
            while (DRDY_N === 1'b0) r14_sample(st, sq, d, ok);
            for (int i = 0; i < 4; i++) begin
                while (DRDY_N !== 1'b0) @(posedge MCLK);
                r14_sample(st, sq, d, ok);
                if (i == 0 && sq !== 16'hFFFE) fail($sformatf("K first SEQ %0d, expected 65534", sq));
                if (i > 0 && sq !== 16'(prev + 16'd1)) fail($sformatf("K SEQ %0d after %0d", sq, prev));
                prev = sq;
            end
        end
        $display("K  SEQ wraps (errors %0d)", errors);

        // ---------------- W: a reset released inside a frame (audit round 10, auditor B). The frame is ignored up to
        // its CS_N rise: MISO_OE stays off, nothing is committed, the chip keeps its reset values. With CRC on, the write
        // [0x21, 0x23, crc] taken from its second byte is [0x23, crc]: with CRC off (every reset clears CRC_EN) a 2-byte
        // write of AFE_IBIAS; the FLUSH [0x10, 0x55, crc] so taken is a write of IF_CFG (CRC_EN without a CRC). RESET_N
        // falls with CS_N and is released at 48 points, every half SCLK period of the 24 bits (W1, W2). W3: a SOFT_RESET
        // whose control reset ends inside the next frame (the host's 1 us rule broken on purpose). After K: the golden
        // log is off, and RESET_N restarts SEQ.
        phase = "W";
        begin
            logic [7:0] fr [0:1][0:2];
            logic [7:0] rv;
            real t_rel, save_idle;
            fr[0][0] = 8'h21; fr[0][1] = 8'h23; fr[1][0] = 8'h10; fr[1][1] = 8'h55;
            for (int f = 0; f < 2; f++) fr[f][2] = tb_crc8_update(tb_crc8_update(8'h00, fr[f][0]), fr[f][1]);
            for (int f = 0; f < 3; f++) begin
                for (int k = 0; k < (f < 2 ? 48 : 1); k++) begin
                    bfm_crc_en = 1'b0;
                    r14_write(7'h55, 8'h01);
                    bfm_crc_en = 1'b1;
                    for (int i = 0; i < 3; i++) spi_tx[i] = fr[f < 2 ? f : 0][i];
                    if (f == 2) begin                   // W3: SOFT_RESET, the next frame 150 ns after its CS_N rise
                        save_idle = spi_tidle;
                        spi_tidle = 150.0;
                        r14_cmd(8'hA5);
                        spi_tidle = save_idle;
                        for (int i = 0; i < 3; i++) spi_tx[i] = fr[0][i];
                    end
                    w_we = 0; w_oe = 0; w_on = 1'b1;
                    spi_chk_hdr = 1'b0;                 // the chip ignores this frame: no STATUS
                    t_rel = spi_tcss + (spi_high + spi_low) * k / 2.0 + 10.0;
                    CS_N = 1'b0;
                    MOSI = spi_bit(0, 3);
                    if (f < 2) begin
                        RESET_N = 1'b0;
                        fork begin #(t_rel); RESET_N = 1'b1; end join_none
                    end
                    #(spi_tcss);
                    for (int n = 0; n < 24; n++) begin
                        SCLK = 1'b1;
                        #(spi_high);
                        SCLK = 1'b0;
                        MOSI = (n + 1 < 24) ? spi_bit(n + 1, 3) : 1'b0;
                        if (n + 1 < 24) #(spi_low);
                    end
                    #(spi_tcsh);
                    CS_N = 1'b1;
                    repeat (12) @(posedge MCLK);
                    w_on = 1'b0;
                    spi_chk_hdr = 1'b1;
                    check_reset_pins($sformatf("W%0d release %0d", f + 1, k));
                    if (w_we != 0 || w_oe != 0)
                        fail($sformatf("W%0d release %0d: %0d commits, MISO_OE on in %0d MCLK of a frame running at the release",
                                       f + 1, k, w_we, w_oe));
                    bfm_crc_en = 1'b0;                  // the reset cleared CRC_EN
                    r14_read(7'h23, rv);
                    if (rv !== 8'h03) fail($sformatf("W%0d release %0d: AFE_IBIAS 0x%02h, expected its reset value 0x03", f + 1, k, rv));
                    r14_read(7'h21, rv);
                    if (rv !== 8'h00) fail($sformatf("W%0d release %0d: OFF_M_L 0x%02h, expected 0x00", f + 1, k, rv));
                    r14_read(7'h55, rv);
                    if (rv !== 8'h00) fail($sformatf("W%0d release %0d: IF_CFG 0x%02h, expected 0x00", f + 1, k, rv));
                    r14_read(7'h06, rv);
                    if (rv !== 8'h01) fail($sformatf("W%0d release %0d: ERR 0x%02h, expected RESET_FLAG only", f + 1, k, rv));
                    r14_write(7'h06, rv);
                end
            end
        end
        $display("W  a reset released inside a frame: the frame ignored, nothing committed (errors %0d)", errors);

        // ---------------- X (audit round 12, auditor C): RESET_N resets asynchronously (RST-01). Every control pin
        // away from its reset value (the settings applied by START, RUN with a sample stored, a frame open), then
        // MCLK stopped and RESET_N low: with no MCLK edge, every pin must be at its reset value (an eeg_regs whose
        // reset was synchronous passed all 16 groups: every bench held RESET_N across MCLK edges)
        phase = "X";
        r14_write(7'h21, 8'h05);                        // OFF_M_L: M 5
        r14_write(7'h22, 8'h11);                        // OFF_CTRL: range 1, sign 1
        r14_write(7'h23, 8'h02);                        // AFE_IBIAS 2
        r14_write(7'h24, 8'h03);                        // CPF_TRIM 3
        r14_write(7'h25, 8'h12);                        // BOOST_TRIM: BTRIM_P 2, BTRIM_N 1
        r14_write(7'h27, 8'h04);                        // ADC_CFG: CHOP1 rate 4, DWA_EN 0
        r14_write(7'h11, 8'h3C);                        // TEST_KEY: the test registers
        r14_write(7'h60, 8'h15);                        // TEST_MUX: ATP_EN 1, ATP_SEL 5
        r14_write(7'h61, 8'h03);                        // TEST_CTRL: ADC_ZERO 1, CHOP_STOP 1
        r14_write(7'h62, 8'h03);                        // DEBUG: RAW_EN 1, DBG_SEL 1
        r14_write(7'h11, 8'h00);                        // lock
        r14_cmd(8'h11);                                 // START: the shadows applied at its tick
        wait_state(4'd6, 12000.0, "X RUN");
        t0 = $realtime;
        while (DRDY_N !== 1'b0 && $realtime - t0 < 3.0e6) @(posedge MCLK);
        CS_N = 1'b0;                                    // a frame open: MISO_OE on
        repeat (5) @(posedge MCLK);
        #1;
        if (OFEN !== 4'b0001 || OFM !== 10'd5 || OFS !== 1'b1 || AFE_IBIAS !== 2'd2 || CPF_TRIM !== 4'd3 ||
            BTRIM_P !== 2'd2 || BTRIM_N !== 2'd1 || DWA_EN !== 1'b0 || CHOP_EN !== 1'b0 || TEST_CFG !== 8'h75 ||
            CHOP_BLANK !== 1'b1 || AFE_RST !== 1'b0 || DRDY_N !== 1'b0 || MISO_OE !== 1'b1 || ADC_RST_N !== 1'b1)
            fail($sformatf("X: the pins before the reset are not all away from their reset values (OFEN %b OFM %0d OFS %b IBIAS %0d CPF %0d BTRIM %0d/%0d DWA %b CHOP_EN %b TEST_CFG 0x%02h CHOP_BLANK %b AFE_RST %b DRDY_N %b MISO_OE %b)",
                           OFEN, OFM, OFS, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, DWA_EN, CHOP_EN, TEST_CFG, CHOP_BLANK, AFE_RST, DRDY_N, MISO_OE));
        mclk_run = 1'b0;                                // MCLK stops (at whichever level)
        #(2.0 * TMCLK);
        seq_before = mclk_count;
        RESET_N = 1'b0;
        #1000.0;                                        // 1 us without an MCLK edge
        if (mclk_count != seq_before) fail("X: MCLK was not stopped");
        check_reset_pins("X: RESET_N low, MCLK stopped");
        check_reset_timing("X: RESET_N low, MCLK stopped");   // audit round 29
        if (TEST_CFG[7:6] !== 2'd0 || DRDY_N !== 1'b1 || MISO_OE !== 1'b0 || CHOP_BLANK !== 1'b0 || ADC_RST_N !== 1'b0 ||
            RAW_DATA !== 1'b0 || RAW_CLK !== 1'b0)
            fail($sformatf("X: RESET_N low, MCLK stopped: TEST_CFG[7:6] %b, DRDY_N %b, MISO_OE %b, CHOP_BLANK %b, ADC_RST_N %b, RAW %b/%b; reset values 0, 1, 0, 0, 0, 0/0",
                           TEST_CFG[7:6], DRDY_N, MISO_OE, CHOP_BLANK, ADC_RST_N, RAW_DATA, RAW_CLK));
        CS_N = 1'b1;
        mclk_run = 1'b1;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        check_reset_pins("X: after the release");
        check_reset_waves("X: after the release", 1'b1);
        if (DRDY_N !== 1'b1 || TEST_CFG[7:6] !== 2'd0) fail($sformatf("X: after the release: DRDY_N %b, TEST_CFG[7:6] %b", DRDY_N, TEST_CFG[7:6]));
        r14_read(7'h06, v);
        if (v !== 8'h01) fail($sformatf("X: ERR 0x%02h after the release, expected RESET_FLAG only", v));
        r14_write(7'h06, v);
        $display("X  RESET_N with MCLK stopped: every pin at its reset value at once (errors %0d)", errors);

        // ---------------- Y: SOFT_RESET returns every register and flag (RST-02; audit round 15, auditor C: after a
        // SOFT_RESET only ERR, CPF_TRIM, FIFO_LEVEL, IF_CFG, AFE_IBIAS, OFF_M_L and the applied pins were read, and an
        // eeg_regs keeping the timers, the ALERT masks, DFLAG or DRDY_MODE through a SOFT_RESET passed all 16 groups).
        // The SOFT_RESET written with CRC off, then on: before it every writable register away from its reset value
        // (soft_set_all, generated; START applies the shadows), both DFLAG bits set (an overload forced on the code
        // stream, the FIFO overflowed), samples in the FIFO, ERR holding ADDR_ERR without RESET_FLAG, the test key open;
        // after it the generated burst over the whole map (as A0), every pin at its reset value, DRDY_N high, the test
        // registers locked. On the way, STATUS with READY and DATA apart (audit round 15, auditor C: no check told them
        // apart, and the two wired crosswise passed): RUN with the FIFO empty, IDLE with samples left
        phase = "Y";
        for (int pass = 0; pass < 2; pass++) begin
            logic [7:0] ys, smask, am_y, amd_y; logic [15:0] yq; logic [23:0] yd; bit yok;
            smask = 8'hFF & ~((8'h01 << STATUS_ALERT_LSB) | (8'h01 << STATUS_OVL_NOW_LSB));
            soft_set_all(pass[0]);
            r14_cmd(8'h11);                                     // START: the settings applied
            wait_state(4'd6, 15000.0, "Y RUN");
            @(posedge dut.push_ok);                             // just after a store: the next one is 1 ms away
            @(posedge MCLK);
            do r14_sample(ys, yq, yd, yok); while (!(yok && ys[SMP_VALID_LSB] === 1'b0));
            check_status(8'h80 | (8'h01 << STATUS_READY_LSB), smask, $sformatf("Y%0d: STATUS in RUN with the FIFO empty (READY 1, DATA 0)", pass));
            if (pass == 0) begin
                // audit round 16, auditor B: the host's re-read after a failed sample CRC (requirements 5.4 step 6) when
                // the chip missed one SCLK pulse (an 8 ns runt as pulse 20): one extra byte of SCLK makes the frame
                // overlong for the chip (71 bits): FRAME_ERR, no pop (one extra edge would make it 64 bits: popped)
                // audit round 21, auditor C: 1 to 7 missed pulses (runts at pulses 20, 22, ...), each its own frame: the
                // chip counts 72 - m bits, never a whole frame (step 6: the extra byte covers up to 7 missed pulses)
                for (int m = 1; m <= 7; m++) begin
                    logic [3:0] lvl0;
                    logic [7:0] yer, ys0;
                    logic [15:0] yq0;
                    logic [23:0] yd0;
                    bit yok0;
                    @(posedge dut.push_ok);
                    @(posedge MCLK); #1;
                    lvl0 = dut.fifo_level;
                    spi_tx[0] = SMP_HDR;
                    for (int i = 1; i < 9; i++) spi_tx[i] = 8'h00;
                    CS_N = 1'b0;
                    MOSI = spi_bit(0, 9);
                    #(spi_tcss);
                    for (int n = 0; n < 72; n++) begin
                        bit runt;
                        runt = (n >= 20 && n < 20 + 2 * m && ((n - 20) % 2) == 0);
                        if (runt) begin @(posedge MCLK); #2; end   // each runt between two MCLK edges: the 2-flop
                        SCLK = 1'b1;                              // synchronizer never sees it (an 8 ns pulse at a
                        #(runt ? 8.0 : spi_high);                 // random phase is sampled 1 time in 4)
                        SCLK = 1'b0;
                        MOSI = spi_bit(n + 1, 9);
                        if (n + 1 < 72) #(spi_low);
                    end
                    #(spi_tcsh);
                    // 72 - m bits: the runts missed (audit round 17, auditor C: a sampled runt gives 72 bits, the same
                    // verdicts)
                    if (dut.u_spi.bit_cnt !== 3'(8 - m))
                        fail($sformatf("Y0 not exercised: %0d bits past whole bytes with %0d runts, expected %0d (%0d bits: the 8 ns pulses missed)",
                                       dut.u_spi.bit_cnt, m, 8 - m, 72 - m));
                    CS_N = 1'b1;
                    #(spi_tidle);
                    if (dut.fifo_level !== lvl0)
                        fail($sformatf("Y: a sample read with %0d missed SCLK and one extra byte popped (level %0d -> %0d)", m, lvl0, dut.fifo_level));
                    r14_read(7'h06, yer);
                    if (yer !== 8'h02) fail($sformatf("Y: ERR 0x%02h after a sample read with %0d missed SCLK and one extra byte, expected FRAME_ERR", yer, m));
                    r14_write(7'h06, 8'h02);
                    r14_sample(ys0, yq0, yd0, yok0);          // the sample the slipped read left, popped now: the
                end                                           // FIFO does not fill over the seven frames
            end
            // audit round 18, auditor B: one SCLK slip (the chip misses a pulse, or counts an extra one) always gives
            // FRAME_ERR and changes nothing, which the host procedure's slip rules rely on: a sample read is not popped
            // (step 6: the host's shifted copy can pass the sample CRC, and the next read returns the same SEQ, which
            // the host compares byte by byte), and in CRC mode a STATUS or STATE read flags its frame (rule (b): the
            // CRC read of STATUS can pass with another value, so READY comes from STATE)
            // audit round 19, auditor B: the host finds the slipped frame by ALERT (step 6): FRAME_ERR is set before
            // the next frame's header copies STATUS, also with CS_N high for the minimum 4 MCLK. ALERT is made
            // FRAME_ERR's alone for these frames (the masks Y set are put back after)
            r14_read(7'h08, am_y); r14_read(7'h09, amd_y);
            r14_write(7'h08, 8'h02); r14_write(7'h09, 8'h00); r14_write(7'h06, 8'hFF);
            for (int k = 0; k < 2; k++) begin
                logic [3:0] lvl1;
                logic [7:0] yer1;
                logic [2:0] b8;
                @(posedge dut.push_ok);
                @(posedge MCLK); #1;
                lvl1 = dut.fifo_level;
                spi_tx[0] = SMP_HDR;
                for (int i = 1; i < SMP_FRAME_LEN; i++) spi_tx[i] = 8'h00;
                spi_tidle = 4.0 * TMCLK + 0.3;                     // the next frame 4 MCLK after the CS_N rise
                xfer_slip(SMP_FRAME_LEN, k + 1, 52, b8);
                spi_tidle = 600.0;
                if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b0) fail($sformatf("Y%0d slip %0d: ALERT set before the slipped frame", pass, k));
                if (b8 !== (k == 0 ? 3'd1 : 3'd7))
                    fail($sformatf("Y%0d slip %0d not exercised: %0d bits past whole bytes", pass, k, b8));
                if (dut.fifo_level !== lvl1)
                    fail($sformatf("Y%0d: a sample read with %s SCLK pulse popped (level %0d -> %0d)", pass,
                                   k == 0 ? "an extra" : "a missed", lvl1, dut.fifo_level));
                r14_read(7'h06, yer1);
                if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b1)
                    fail($sformatf("Y%0d slip %0d: no ALERT in the header right after the slipped sample read (CS_N high 4 MCLK)", pass, k));
                if (yer1 !== 8'h02)
                    fail($sformatf("Y%0d: ERR 0x%02h after a sample read with %s SCLK pulse, expected FRAME_ERR", pass, yer1,
                                   k == 0 ? "an extra" : "a missed"));
                r14_write(7'h06, 8'h02);
            end
            if (pass == 1) begin                                // CRC on: STATUS (0x83) and STATE (0x84) reads
                for (int k = 0; k < 4; k++) begin
                    logic [7:0] yer2;
                    logic [3:0] st0;
                    logic [2:0] b8;
                    st0 = dut.seq_state;
                    spi_tx[0] = (k < 2) ? 8'h83 : 8'h84; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
                    spi_tidle = 4.0 * TMCLK + 0.3;
                    xfer_slip(3, (k % 2) + 1, 9, b8);
                    spi_tidle = 600.0;
                    if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b0) fail($sformatf("Y1 read slip %0d: ALERT set before the slipped frame", k));
                    if (b8 !== ((k % 2) == 0 ? 3'd1 : 3'd7))
                        fail($sformatf("Y1 read slip %0d not exercised: %0d bits past whole bytes", k, b8));
                    r14_read(7'h06, yer2);
                    if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b1)
                        fail($sformatf("Y1 read slip %0d: no ALERT in the header right after the slipped read (CS_N high 4 MCLK)", k));
                    if (yer2 !== 8'h02)
                        fail($sformatf("Y1: ERR 0x%02h after a CRC read of %s with %s SCLK pulse, expected FRAME_ERR", yer2,
                                       k < 2 ? "STATUS" : "STATE", (k % 2) == 0 ? "an extra" : "a missed"));
                    r14_write(7'h06, 8'h02);
                    if (dut.seq_state !== st0) fail("Y1: the state changed across a slipped read");
                end
                // audit round 23, auditor B: a slip in a frame that is not a sample read (a CRC read of FIFO_LEVEL with an
                // extra SCLK pulse) followed at once by a sample read (CS_N high 4 MCLK): that read's header shows ALERT
                // (the slipped frame's FRAME_ERR), and its word is the next sample, CRC-valid and popped. Step 6 uses it
                // (the frame before the 0 -> 1 header was not a sample read); round 22's rule withheld it
                begin
                    logic [7:0] ys3, yer3;
                    logic [15:0] yq3, ylast;
                    logic [23:0] yd3;
                    bit yok3;
                    logic [2:0] b8;
                    logic [3:0] lvl3;
                    ylast = 16'hxxxx;
                    do begin                                    // drained: a CRC-valid empty word
                        r14_sample(ys3, yq3, yd3, yok3);
                        if (yok3 && ys3[7] === 1'b1) ylast = yq3;
                    end while (!(yok3 && ys3[7] === 1'b0));
                    if ($isunknown(ylast)) fail("Y1 FIFO_LEVEL slip: no sample before the empty word");
                    @(posedge dut.push_ok);                     // one new sample, SEQ ylast + 1
                    @(posedge MCLK); #1;
                    lvl3 = dut.fifo_level;
                    spi_tx[0] = 8'h85; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
                    spi_tidle = 4.0 * TMCLK + 0.3;
                    xfer_slip(3, 1, 9, b8);
                    spi_tidle = 600.0;
                    if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b0) fail("Y1 FIFO_LEVEL slip: ALERT set before the slipped frame");
                    if (b8 !== 3'd1) fail($sformatf("Y1 FIFO_LEVEL slip not exercised: %0d bits past whole bytes", b8));
                    r14_sample(ys3, yq3, yd3, yok3);
                    if (spi_rx[0][STATUS_ALERT_LSB] !== 1'b1)
                        fail("Y1: no ALERT in the header of the sample read right after a slipped FIFO_LEVEL read (CS_N high 4 MCLK)");
                    if (!yok3 || ys3[7] !== 1'b1 || yq3 !== ylast + 16'd1)
                        fail($sformatf("Y1: the sample read after a slipped FIFO_LEVEL read gave CRC %0d VALID %b SEQ %0d, expected a CRC-valid SEQ %0d",
                                       yok3, ys3[7], yq3, ylast + 16'd1));
                    if (dut.fifo_level !== lvl3 - 4'd1)
                        fail($sformatf("Y1: the sample read after a slipped FIFO_LEVEL read did not pop (level %0d -> %0d)", lvl3, dut.fifo_level));
                    r14_read(7'h06, yer3);
                    if (yer3 !== 8'h02) fail($sformatf("Y1: ERR 0x%02h after a slipped FIFO_LEVEL read, expected FRAME_ERR", yer3));
                    r14_write(7'h06, 8'h02);
                    n_y_slip_smp = n_y_slip_smp + 1;
                end
            end
            r14_write(7'h08, am_y); r14_write(7'h09, amd_y);    // Y's masks back
            ovl_force = 1'b1;                                   // DFLAG.OVL
            repeat (40 * 32) @(posedge MCLK);
            ovl_force = 1'b0;
            repeat ((FD + 2) * 32768) @(posedge MCLK);          // the FIFO overflows: DFLAG.OVERRUN
            rt_read_expect(7'h07, 8'h03, $sformatf("Y%0d: DFLAG with an overload and an overrun", pass));
            r14_cmd(8'h22);                                     // STOP: IDLE, the samples kept
            wait_state(4'd0, 50.0, "Y IDLE");
            check_status(8'h80 | (8'h01 << STATUS_DATA_LSB) | (8'h01 << STATUS_AFE_RST_LSB), smask,
                         $sformatf("Y%0d: STATUS in IDLE with samples left (READY 0, DATA 1)", pass));
            r14_write(7'h7F, 8'h00);                            // undefined: ADDR_ERR
            r14_write(7'h06, 8'h01);                            // RESET_FLAG cleared: the SOFT_RESET must set it
            rt_read_expect(7'h06, 8'h08, $sformatf("Y%0d: ERR before the SOFT_RESET", pass));
            r14_cmd(8'hA5);                                     // SOFT_RESET, in the chip's CRC mode
            bfm_crc_en = 1'b0;
            #(1000.0);
            run_reset_burst($sformatf("Y%0d after SOFT_RESET", pass));
            check_reset_pins($sformatf("Y%0d: after SOFT_RESET", pass));
            check_reset_waves($sformatf("Y%0d: after SOFT_RESET", pass), 1'b0);
            if (DRDY_N !== 1'b1) fail($sformatf("Y%0d: DRDY_N %b after SOFT_RESET (level mode, FIFO empty)", pass, DRDY_N));
            r14_write(7'h06, 8'h01);
            rt_write_check(7'h60, 8'h11, 8'h00, 8'h08, $sformatf("Y%0d: TEST_MUX locked after SOFT_RESET", pass));
        end
        $display("Y  SOFT_RESET returns every register and flag, CRC off and on; STATUS's READY and DATA apart; a sample read after a slipped FIFO_LEVEL read used (errors %0d)", errors);
        // ---------------- Z (audit round 30, auditor C): a register write committed in the acknowledge cycle of an
        // applying command. No test committed one in the cycle where a tick takes a pending START, APPLY or APPLY_NR, and
        // a copy whose apply copied the shadows' next state (the racing value applied, unjudged by cfg_ok / nr_ok) and one
        // whose apply dropped the write passed all 16 groups. At 64 kHz, range 1, an OFF_M_L write is swept in 1/4-MCLK
        // steps across the tick that takes the command: committed before that cycle, STATE_ERR and not written; in it or
        // after, written (no STATE_ERR); the tick applies the shadow before the write, judged by cfg_ok / nr_ok on that
        // shadow. Audit round 31 (auditor C: a copy computing cfg_ok from the shadow after the write of its own cycle passed
        // all 16 groups, as Z1's target was the value applied before and Z2's racing value was legal): ERR is checked
        // exactly, the targets alternate (M 5 <-> 6, one step), the racing value of Z1 and Z2 is M_L 200 (above range 1's
        // 127), and Z3 pends an APPLY whose judged shadow is M 200 against a legal racing value: CFG_ERR, nothing applied.
        // Z1: APPLY in IDLE. Z3: APPLY in IDLE, the judged shadow illegal. Z2: APPLY_NR in RUN. Each sweep must commit at
        // least once before the acknowledge cycle, once in it and once after it.
        phase = "Z";
        spi_tidle = 600.0;
        r14_cmd(8'hA5);                                 // SOFT_RESET: a known start
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h26, 8'h00);                        // CHOP_FAST 0: 64 kHz (a tick every 512 MCLK)
        r14_write(7'h22, 8'h01);                        // range 1
        r14_write(7'h21, 8'd5);                         // M 5
        r14_cmd(8'h33);                                 // APPLY in IDLE
        #(40000.0);
        if (OFM !== 10'd5 || OFEN !== 4'b0001 || dut.a_chop_fast !== 1'b0) fail($sformatf("Z: setup not applied (OFM %0d OFEN %b fast %b)", OFM, OFEN, dut.a_chop_fast));
        begin
            integer cur;
            cur = 5;
            for (int zi = 0; zi < 3; zi++) begin
                real zl, zt0;
                integer zs, nb, ns, na, tgt, pend_v, racer, appl;
                logic [7:0] ze, zsh, zac, e_before, e_after;
                zs = (zi == 0) ? 1 : ((zi == 1) ? 3 : 2);    // the order Z1, Z3 (both IDLE), Z2 (RUN)
                if (zs == 2) begin                      // Z2: RUN
                    r14_write(7'h21, 8'(cur));          // a legal shadow: START judges it
                    r14_write(7'h06, 8'hFF);
                    r14_cmd(8'h11);
                    wait_state(4'd6, 20000.0, "Z2 RUN");
                end
                zt0 = $realtime; r14_write(7'h21, 8'(cur)); zl = z_t_c - zt0;   // a 2-byte write: start to its commit edge
                nb = 0; ns = 0; na = 0;
                e_before = (zs == 3) ? 8'h60 : 8'h40;   // STATE_ERR for the refused write (and CFG_ERR at the tick in Z3)
                e_after  = (zs == 3) ? 8'h20 : 8'h00;
                for (int k = -12; k <= 12; k++) begin
                    tgt = (cur == 5) ? 6 : 5;
                    pend_v = (zs == 3) ? 200 : tgt;     // the shadow the tick judges
                    racer  = (zs == 3) ? tgt : 200;     // the racing write
                    appl   = (zs == 3) ? cur : tgt;     // what the tick must apply (Z3: nothing, the APPLY refused)
                    r14_write(7'h21, 8'(pend_v));
                    r14_write(7'h06, 8'hFF);
                    @(posedge dut.u_clkgen.tick); zt0 = $realtime;
                    #(512.0 * TMCLK - zl + 6.0 * TMCLK);
                    if (dut.seq_state !== ((zs == 2) ? 4'd6 : 4'd0))
                        fail($sformatf("Z%0d k %0d: state %0d at the command, expected %s", zs, k, dut.seq_state, (zs == 2) ? "RUN" : "IDLE"));
                    r14_cmd((zs == 2) ? 8'h44 : 8'h33);     // pending from just after the next tick to the one after it
                    #(zt0 + 1024.0 * TMCLK + k * TMCLK / 4.0 - zl - $realtime);
                    r14_write(7'h21, 8'(racer));
                    repeat (700) @(posedge MCLK);
                    r14_read(7'h06, ze);
                    r14_read(7'h21, zsh);
                    r14_read(7'h31, zac);
                    if (z_t_c < z_t_ack) begin
                        nb++;
                        if (ze !== e_before || zsh !== 8'(pend_v))
                            fail($sformatf("Z%0d k %0d: committed %0.2f MCLK before the ack edge: ERR 0x%02h, shadow M_L %0d (expected exactly 0x%02h, %0d kept)",
                                           zs, k, (z_t_ack - z_t_c) / TMCLK, ze, zsh, e_before, pend_v));
                    end else begin
                        if (z_t_c == z_t_ack) ns++; else na++;
                        if (ze !== e_after || zsh !== 8'(racer))
                            fail($sformatf("Z%0d k %0d: committed %0.2f MCLK after the ack edge: ERR 0x%02h, shadow M_L %0d (expected exactly 0x%02h, %0d written)",
                                           zs, k, (z_t_c - z_t_ack) / TMCLK, ze, zsh, e_after, racer));
                    end
                    if (zac !== 8'(appl) || OFM !== 10'(appl))
                        fail($sformatf("Z%0d k %0d: active M_L %0d, OFM %0d after the tick (expected %0d: the shadow before the write, as judged; the racing %0d never applied)",
                                       zs, k, zac, OFM, appl, racer));
                    cur = appl;
                end
                if (nb < 1 || ns < 1 || na < 1)
                    fail($sformatf("Z%0d not exercised: %0d commits before the ack cycle, %0d in it, %0d after it", zs, nb, ns, na));
                begin
                    string zname, zres;                 // string variables: a ternary of literals pads the shorter one
                    if (zs == 1)      zname = "APPLY in IDLE";
                    else if (zs == 3) zname = "APPLY in IDLE, the judged shadow M 200";
                    else              zname = "APPLY_NR in RUN";
                    if (zs == 3) zres = "refused with CFG_ERR every time, nothing applied";
                    else         zres = "the judged value applied every time";
                    $display("Z%0d %s: OFF_M_L committed across the acknowledging tick: %0d before it (STATE_ERR), %0d in its cycle, %0d after (written); %s",
                             zs, zname, nb, ns, na, zres);
                end
            end
        end
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 20000.0, "Z IDLE");
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults back
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        $display("Z  a register write in the acknowledge cycle of APPLY and APPLY_NR: written, the shadow before it judged and applied (errors %0d)", errors);
        // ---------------- AA (audit round 32, auditor C): an overload across the output time that completes FILL.
        // SEQ-04 / DAT-01 (fsm_spec FILL/OUT [valid]): the first valid output in FILL is stored and RUN entered whatever
        // the overload; the sample carries OVL and DFLAG.OVL is set. No phase had OVL_NOW = 1 at FILL's completing output
        // (N's burst is the 20 frames right after FILL's entry, T10 the first interval's inputs 100-119, T8 and T12 are
        // in RUN), and a sequencer taking out_valid as cic_valid & ~ovl_now (in FILL with READY 0 and no samples while
        // the overload lasts) passed all 16 groups. Code 31 from 24 frames before FILL's third output (its first valid
        // one) to 16 frames after it, at the defaults (128 kHz, T_ELEC 0).
        phase = "AA";
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        r14_cmd(8'h11);                                 // START
        wait_state(4'd5, 7000.0, "AA FILL");            // entered at ALIGN's output time (the CIC's clear)
        begin
            integer aa_n;
            logic [15:0] aa_seq, aa_sq;
            logic [7:0] aa_st, aa_f;
            logic [23:0] aa_d;
            bit aa_ok;
            aa_n = 0;
            while (aa_n < 2) begin @(posedge MCLK); if (dut.cic_stb === 1'b1) aa_n++; end   // FILL's two invalid outputs
            repeat (1000 * 32) @(posedge MCLK);         // 24 frames before the third
            ovl_force = 1'b1;
            while (dut.cic_stb !== 1'b1) @(posedge MCLK);
            aa_seq = dut.seq_cnt;                       // the SEQ the store of this output carries
            if (dut.seq_state !== 4'd5 || dut.ovl_now !== 1'b1)
                fail($sformatf("AA not exercised: state %0d, OVL_NOW %b at FILL's third output", dut.seq_state, dut.ovl_now));
            @(posedge MCLK); #1;
            if (dut.seq_state !== 4'd6)
                fail($sformatf("AA: state %0d after FILL's first valid output under an overload, expected RUN (SEQ-04, DAT-01)",
                               dut.seq_state));
            repeat (16 * 32) @(posedge MCLK);
            ovl_force = 1'b0;
            repeat (64 * 32) @(posedge MCLK);
            r14_sample(aa_st, aa_sq, aa_d, aa_ok);
            if (!aa_ok || aa_st[SMP_VALID_LSB] !== 1'b1 || aa_st[SMP_OVL_LSB] !== 1'b1 || aa_sq !== aa_seq)
                fail($sformatf("AA: the first sample's status 0x%02h, SEQ %0d, CRC %b; expected VALID and OVL, SEQ %0d (FILL's third output)",
                               aa_st, aa_sq, aa_ok, aa_seq));
            r14_read(7'h07, aa_f);
            if (aa_f[DFLAG_OVL_LSB] !== 1'b1) fail($sformatf("AA: DFLAG 0x%02h without OVL", aa_f));
            $display("AA an overload across FILL's completing output (SEQ %0d): RUN entered at it, the first sample VALID with OVL (status 0x%02h), DFLAG.OVL set (errors %0d)",
                     aa_seq, aa_st, errors);
        end
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 50.0, "AA IDLE");
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        // ---------------- AB (audit round 33, auditor C): an APPLY_NR (T_ELEC 0) or an APPLY in FILL, 40, 1,070 and
        // 2,100 us after its entry, each followed into RUN: ALIGN's output time is then the first, second or third output
        // after the clear before (the CIC not yet valid at the first two). The FILL monitor checks the clear and FILL's
        // store; AB makes the early clears, which no phase made (V's commands in FILL never run on to RUN). Range 0, M 0
        // <-> 1, T_ELEC 0, 128 kHz; outside the golden comparison (after K)
        phase = "AB";
        r14_write(7'h06, 8'hFF);
        r14_cmd(8'h11);                                 // START
        wait_state(4'd6, 12000.0, "AB RUN");
        begin
            integer ab_e0, ab_s0, ab_t;
            logic [7:0] ab_m;
            ab_m = 8'd0; ab_e0 = n_align_early; ab_s0 = n_fill_store; ab_t = 0;
            for (int cmd = 0; cmd < 2; cmd++) begin     // 0: APPLY_NR (T_ELEC 0) in FILL, 1: APPLY in FILL
                for (int k = 0; k < 3; k++) begin
                    real d;
                    d = 40.0 + 1030.0 * k;              // us after FILL's entry
                    r14_cmd(8'h33);                     // APPLY in RUN: to FILL through PRE .. ALIGN
                    wait_state(4'd5, 3000.0, "AB FILL");
                    #(d * 1000.0);
                    if (dut.seq_state !== 4'd5) fail($sformatf("AB: FILL over %0.0f us after its entry", d));
                    if (cmd == 0) begin
                        ab_m = ab_m ^ 8'd1;
                        r14_write(7'h21, ab_m);         // M 0 <-> 1: one step in range 0
                        r14_cmd(8'h44);
                    end else begin
                        r14_cmd(8'h33);
                    end
                    wait_state(4'd4, 1000.0, "AB ALIGN after the command in FILL");
                    wait_state(4'd6, 6000.0, "AB RUN after the command in FILL");
                    ab_t++;
                end
            end
            $display("AB %0d commands in FILL (APPLY_NR and APPLY, 40 / 1,070 / 2,100 us after its entry), each into RUN: %0d of the clears at an output not yet valid, %0d first stores (errors %0d)",
                     ab_t, n_align_early - ab_e0, n_fill_store - ab_s0, errors);
            if (n_align_early - ab_e0 < 4 || n_fill_store - ab_s0 < 6)
                fail($sformatf("AB not exercised: %0d early clears, %0d stores", n_align_early - ab_e0, n_fill_store - ab_s0));
        end
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "AB IDLE");
        r14_write(7'h21, 8'h00); r14_cmd(8'h33);        // M 0 applied in IDLE
        repeat (600) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);
        // ---------------- AC (audit round 33, auditor C): T_WARM and T_ELEC of 128 and more from eeg_regs into eeg_seq.
        // No group carried T_WARM >= 128, or T_ELEC >= 128 into WAIT_E, from the registers to the sequencer (tb_seq
        // drives eeg_seq alone; this bench's largest T_WARM at a START was 6 and T_ELEC into WAIT_E 2), and an eeg_regs
        // whose t_warm port was 7 bits passed all 16 groups. START with T_WARM 128 (WARMUP still on 2 ms later) and 255,
        // START with T_ELEC 255 into WAIT_E (still there 2 ms later), each stopped; the trace's timer model (VER-09)
        // compares every load with the registers' values
        phase = "AC";
        r14_write(7'h50, 8'd128);                       // T_WARM 128 ms
        r14_cmd(8'h11);
        wait_state(4'd1, 50.0, "AC WARMUP (T_WARM 128)");
        repeat (2 * 32768) @(posedge MCLK);
        if (dut.seq_state !== 4'd1) fail($sformatf("AC: state %0d 2 ms after a START with T_WARM 128 (WARMUP lasts 128 ms)", dut.seq_state));
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "AC IDLE");
        r14_write(7'h50, 8'd255);                       // T_WARM 255 ms: its load in the trace
        r14_cmd(8'h11);
        wait_state(4'd1, 50.0, "AC WARMUP (T_WARM 255)");
        repeat (4 * 512) @(posedge MCLK);
        if (dut.seq_state !== 4'd1) fail($sformatf("AC: state %0d after a START with T_WARM 255", dut.seq_state));
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "AC IDLE");
        r14_write(7'h50, 8'd5);
        r14_write(7'h51, 8'd255);                       // T_ELEC 255 ms
        r14_cmd(8'h11);
        wait_state(4'd3, 6000.0, "AC WAIT_E (T_ELEC 255)");
        repeat (2 * 32768) @(posedge MCLK);
        if (dut.seq_state !== 4'd3) fail($sformatf("AC: state %0d 2 ms into WAIT_E with T_ELEC 255", dut.seq_state));
        r14_cmd(8'h22);
        wait_state(4'd0, 50.0, "AC IDLE");
        r14_write(7'h51, 8'd0);
        r14_write(7'h06, 8'hFF);
        $display("AC T_WARM 128 and 255, T_ELEC 255 from the registers into the sequencer: WARMUP and WAIT_E held, every load in the trace (errors %0d)", errors);
        // ---------------- AD (audit round 34, auditor C): the sample's ERR bit when ERR changes at the store's own edge.
        // Spec 3.4: a sample's ERR is ALERT at the store. No phase put a flag change on a store edge (the stores come at
        // frame cycle 8 once a ms, the commits at random cycles; only STATUS's header copy had a same-edge test, round
        // 19), and a copy writing the FIFO the sample status registered one MCLK earlier passed all 16 groups. In RUN
        // (128 kHz, the defaults, ALERT_MASK 0xFF, ALERT_MASK_D 0), an ADDR_ERR (a write to the undefined 0x7F) and its
        // W1C clear are aimed at a store's own cycle in 1/4-MCLK steps, from 2 MCLK before its start to 2 MCLK after it;
        // every sample read in AD must carry the ALERT of its store's cycle as the registers give it (the monitor
        // above), and each sweep must change ERR before the store's cycle, at its start (in the store's own cycle) and
        // at or after the store's edge. Outside the golden comparison (after K)
        phase = "AD";
        spi_tidle = 600.0;
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        r14_write(7'h09, 8'h00);                        // ALERT_MASK_D 0: ALERT from ERR alone
        r14_cmd(8'h11);                                 // START
        wait_state(4'd6, 12000.0, "AD RUN");
        begin
            real    ad_t0, ad_tgt, ad_dt;
            integer ad_n0, ad_c0;
            logic [7:0] ad_e;
            logic   ad_want;
            string  ad_nm;
            ad_c0 = ad_nchk;
            ad_read_all();
            r14_read(7'h06, ad_e);
            if (ad_e !== 8'h00) fail($sformatf("AD: ERR 0x%02h before the sweeps, expected 0x00", ad_e));
            // the time from a write's start to the edge that changes ERR: an ADDR_ERR, then its W1C
            ad_t0 = $realtime; r14_write(7'h7F, 8'h00); repeat (8) @(posedge MCLK); ad_lat[0] = ad_t_err - ad_t0;
            r14_read(7'h06, ad_e);
            if (ad_e !== 8'h08) fail($sformatf("AD: ERR 0x%02h after a write to 0x7F, expected ADDR_ERR (0x08)", ad_e));
            ad_t0 = $realtime; r14_write(7'h06, 8'h08); repeat (8) @(posedge MCLK); ad_lat[1] = ad_t_err - ad_t0;
            r14_read(7'h06, ad_e);
            if (ad_e !== 8'h00) fail($sformatf("AD: ERR 0x%02h after its W1C, expected 0x00", ad_e));
            for (int s = 0; s < 2; s++) begin ad_nb[s] = 0; ad_ns[s] = 0; ad_na[s] = 0; end
            ad_n0 = ad_n_store;
            while (ad_n_store == ad_n0) @(negedge MCLK);    // a store, then its sample read
            ad_read_all();
            for (int k = -8; k <= 8; k++) begin
                for (int s = 0; s < 2; s++) begin           // 0: the ADDR_ERR, 1: its W1C clear
                    // aimed at the next store: ERR changing at the start of its cycle (one MCLK before its edge)
                    ad_tgt = ad_t_store + 32768.0 * TMCLK - TMCLK + k * TMCLK / 4.0 - ad_lat[s];
                    if (ad_tgt > $realtime) #(ad_tgt - $realtime);
                    else fail($sformatf("AD k %0d: the aimed write was due %0.1f ns ago", k, $realtime - ad_tgt));
                    ad_n0 = ad_n_store;
                    if (s == 0) r14_write(7'h7F, 8'h00);
                    else        r14_write(7'h06, 8'h08);
                    while (ad_n_store == ad_n0) @(negedge MCLK);
                    repeat (8) @(posedge MCLK);
                    ad_dt = ad_t_err - (ad_t_store - TMCLK);     // the change against the start of the store's cycle
                    if (ad_dt < -TMCLK / 2.0)     ad_nb[s] = ad_nb[s] + 1;
                    else if (ad_dt < TMCLK / 2.0) ad_ns[s] = ad_ns[s] + 1;
                    else                          ad_na[s] = ad_na[s] + 1;
                    ad_want = (ad_dt < TMCLK / 2.0) ? (s == 0) : (s == 1);     // ALERT in the store's cycle
                    if (ad_exp[ad_seq_store[7:0]] !== ad_want)
                        fail($sformatf("AD k %0d: ALERT %b modelled at the store (SEQ %0d), but ERR changed %0.2f MCLK from its cycle's start, which gives %b",
                                       k, ad_exp[ad_seq_store[7:0]], ad_seq_store, ad_dt / TMCLK, ad_want));
                    ad_read_all();
                end
            end
            for (int s = 0; s < 2; s++) begin
                if (s == 0) ad_nm = "the ADDR_ERR";
                else        ad_nm = "its W1C";
                if (ad_nb[s] < 1 || ad_ns[s] < 1 || ad_na[s] < 1)
                    fail($sformatf("AD not exercised (%s): ERR changed %0d times before the store's cycle, %0d at its start, %0d at or after the store's edge",
                                   ad_nm, ad_nb[s], ad_ns[s], ad_na[s]));
            end
            $display("AD ERR changed across a store's own cycle: the ADDR_ERR %0d / %0d / %0d, its W1C %0d / %0d / %0d (before the cycle / at its start / at or after the store's edge); %0d samples, each with the ALERT of its store's cycle (errors %0d)",
                     ad_nb[0], ad_ns[0], ad_na[0], ad_nb[1], ad_ns[1], ad_na[1], ad_nchk - ad_c0, errors);
        end
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 50.0, "AD IDLE");
        r14_write(7'h09, 8'h03);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        // ---------------- AE (audit round 35, auditor C): ERR and DFLAG through every accepted command. REG-02 and
        // FLG-02: only their W1C clears them. No phase read them after an accepted command with a bit standing from
        // before it (check_top_r14's status check and AD's model take them from the registers, which follow a wrong
        // clear), and copies clearing RESET_FLAG or DFLAG when a configuration is applied (START, APPLY, APPLY_NR)
        // passed all 16 groups. RESET_FLAG (a SOFT_RESET) and ADDR_ERR stand, both DFLAG bits are set in RUN (an
        // overload, then a full FIFO); START, APPLY in RUN, APPLY_NR (M 0 -> 1, range 0), FLUSH, STOP and APPLY in
        // IDLE, each accepted, and ERR and DFLAG read exactly after each, then their W1C. Outside the golden comparison
        phase = "AE";
        spi_tidle = 600.0;
        r14_cmd(8'hA5);                                 // SOFT_RESET: RESET_FLAG
        #(1000.0);
        r14_write(7'h7F, 8'h00);                        // undefined: ADDR_ERR
        // audit round 37, auditor C: every ERR bit stands (only RESET_FLAG and ADDR_ERR did, and a copy clearing
        // CFG_ERR at an apply passed all 16 groups); STATE_ERR comes from a START refused in WARMUP below
        spi_tx[0] = 8'h24; spi_xfer(1, 0);              // a header-only write: FRAME_ERR
        r14_write(7'h55, 8'h01);                        // CRC on
        bfm_crc_en = 1'b1;
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h09; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // a wrong CRC: CRC_ERR
        r14_write(7'h55, 8'h00);                        // CRC off
        bfm_crc_en = 1'b0;
        r14_write(7'h50, 8'd4);                         // T_WARM 4 (legal 5..255): RANGE_ERR
        r14_write(7'h10, 8'h99);                        // an undefined command code: CMD_ERR
        r14_write(7'h22, 8'h01);                        // range 1 with M 200, above its top
        r14_write(7'h21, 8'd200);
        r14_cmd(8'h33);                                 // APPLY in IDLE, refused: CFG_ERR
        repeat (700) @(posedge MCLK);
        r14_write(7'h21, 8'h00);                        // the defaults again (range 0, M 0)
        r14_write(7'h22, 8'h00);
        ae_n = 0;
        ae_check("seven ERR bits standing (RESET_FLAG, FRAME_ERR, CRC_ERR, ADDR_ERR, RANGE_ERR, CFG_ERR, CMD_ERR)", 8'hBF, 8'h00);
        r14_cmd(8'h11);                                 // START (the defaults)
        ae_check("START", 8'hBF, 8'h00);
        r14_cmd(8'h11);                                 // a START in WARMUP, refused: STATE_ERR
        ae_check("a START refused in WARMUP", 8'hFF, 8'h00);
        wait_state(4'd6, 12000.0, "AE RUN");
        ovl_force = 1'b1;                               // an overload in RUN: DFLAG.OVL
        repeat (64 * 32) @(posedge MCLK);
        ovl_force = 1'b0;
        repeat ((FD + 3) * 32768) @(posedge MCLK);      // no reads: the FIFO fills, DFLAG.OVERRUN
        ae_check("an overload and a full FIFO in RUN", 8'hFF, 8'h03);
        r14_cmd(8'h33);                                 // APPLY in RUN
        ae_check("APPLY in RUN", 8'hFF, 8'h03);
        wait_state(4'd6, 12000.0, "AE RUN after the APPLY");
        r14_write(7'h21, 8'h01);                        // M 0 -> 1: one step in range 0
        r14_cmd(8'h44);                                 // APPLY_NR in RUN
        ae_check("APPLY_NR in RUN", 8'hFF, 8'h03);
        r14_cmd(8'h55);                                 // FLUSH
        ae_check("FLUSH", 8'hFF, 8'h03);
        r14_cmd(8'h22);                                 // STOP
        ae_check("STOP", 8'hFF, 8'h03);
        if (dut.seq_state !== 4'd0) fail($sformatf("AE: state %0d after the STOP, expected IDLE", dut.seq_state));
        r14_write(7'h21, 8'h00);
        r14_cmd(8'h33);                                 // APPLY in IDLE
        ae_check("APPLY in IDLE", 8'hFF, 8'h03);
        r14_cmd(8'h11);                                 // START with DFLAG standing (audit round 36, auditor C: AE's first
        ae_check("START with DFLAG standing", 8'hFF, 8'h03);   // START came before DFLAG was set)
        r14_cmd(8'h22);                                 // STOP in WARMUP
        ae_check("the STOP in WARMUP", 8'hFF, 8'h03);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        ae_check("their W1C", 8'h00, 8'h00);
        if (ae_n != 12) fail($sformatf("AE not exercised: %0d reads", ae_n));
        $display("AE all eight ERR bits and DFLAG (OVL, OVERRUN) through START, APPLY in RUN, APPLY_NR, FLUSH, STOP, APPLY in IDLE and a START with DFLAG standing: kept exactly until their W1C (%0d reads, errors %0d)",
                 ae_n, errors);
        // ---------------- AF (audit round 35, auditor C): the copy instants of the header's STATUS and of the empty
        // word. Spec 3.2: STATUS is copied in the cycle the SPI takes CS_N's fall (cs_start), the sample word (the empty
        // word when the FIFO is empty) in the cycle it takes the header's last SCLK rise (smp_snap), with the flags of
        // that cycle. AD pins the store's; no phase put a flag change on these copies (round 19's STATUS check has the
        // flag 3-4 MCLK before the copy), and copies taking the empty word's status or STATUS one MCLK early passed all
        // 16 groups. At 64 kHz in IDLE an APPLY whose judged shadow is illegal (range 1, M 200) is refused with CFG_ERR
        // at its tick; a register read (kind 0) or an empty-FIFO sample read (kind 1) starts so that its copy's cycle
        // begins from 2 MCLK before that edge to 2 MCLK after it in 1/4-MCLK steps. STATUS's ALERT and the empty word's
        // ERR must be the ALERT of the copy's cycle as the registers give it, and each sweep must change ERR before the
        // copy's cycle, at its start and at or after the copy's edge. Outside the golden comparison (after K)
        phase = "AF";
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        r14_write(7'h09, 8'h00);                        // ALERT_MASK_D 0: ALERT from ERR alone
        r14_write(7'h26, 8'h00);                        // CHOP_FAST 0: 64 kHz, a tick every 512 MCLK
        r14_write(7'h22, 8'h01);                        // range 1
        r14_write(7'h21, 8'd5);
        r14_cmd(8'h33);                                 // APPLY in IDLE: 64 kHz applied
        #(40000.0);
        if (dut.a_chop_fast !== 1'b0) fail("AF: 64 kHz not applied");
        r14_write(7'h21, 8'd200);                       // the shadow the next APPLYs are judged by: above range 1's 127
        begin
            real af_t0, af_tgt, af_dt, af_tc, af_derr;
            logic [7:0] af_v, af_st;
            logic [15:0] af_sq;
            logic [23:0] af_d;
            bit af_ok;
            logic af_exp, af_got, af_want;
            string af_nm;
            // a frame's start to its copy edge: a register read's header, an empty-FIFO sample read's header end
            af_t0 = $realtime; r14_read(7'h03, af_v); af_lat[0] = af_t_hdr - af_t0;
            af_t0 = $realtime; r14_sample(af_st, af_sq, af_d, af_ok); af_lat[1] = af_t_snap - af_t0;
            // the edge at which CFG_ERR is set after the tick before the one that takes a pending APPLY
            @(posedge dut.u_clkgen.tick); af_t0 = $realtime;
            r14_cmd(8'h33);
            repeat (600) @(posedge MCLK);
            af_derr = ad_t_err - af_t0;
            r14_read(7'h06, af_v);
            if (af_v !== 8'h20) fail($sformatf("AF: ERR 0x%02h after the APPLY judged on M 200 in range 1, expected exactly CFG_ERR (0x20)", af_v));
            r14_write(7'h06, 8'hFF);
            for (int s = 0; s < 2; s++) begin af_nb[s] = 0; af_ns[s] = 0; af_na[s] = 0; end
            for (int k = -8; k <= 8; k++) begin
                for (int s = 0; s < 2; s++) begin
                    @(posedge dut.u_clkgen.tick); af_t0 = $realtime;
                    r14_cmd(8'h33);                     // pending to the next tick: CFG_ERR at af_t0 + af_derr
                    af_tgt = af_t0 + af_derr + TMCLK + k * TMCLK / 4.0 - af_lat[s];   // the copy's cycle starting there
                    if (af_tgt > $realtime) #(af_tgt - $realtime);
                    else fail($sformatf("AF k %0d: the aimed read was due %0.1f ns ago", k, $realtime - af_tgt));
                    if (s == 0) begin
                        r14_read(7'h03, af_v);
                        af_tc = af_t_hdr; af_exp = af_hdr_exp; af_got = spi_status[STATUS_ALERT_LSB];
                        af_nm = "a register read's STATUS, ALERT";
                    end else begin
                        r14_sample(af_st, af_sq, af_d, af_ok);
                        af_tc = af_t_snap; af_exp = af_snap_exp; af_got = af_st[SMP_ERR_LSB];
                        af_nm = "an empty-FIFO sample read's word, ERR";
                        if (!af_ok || af_st[SMP_VALID_LSB] !== 1'b0 || af_snap_lvl !== 4'd0)
                            fail($sformatf("AF k %0d: the sample read copied no empty word (status 0x%02h, CRC %b, level %0d at the copy)",
                                           k, af_st, af_ok, af_snap_lvl));
                    end
                    repeat (8) @(posedge MCLK);
                    af_dt = ad_t_err - (af_tc - TMCLK);         // the change against the start of the copy's cycle
                    if (af_dt < -TMCLK / 2.0)     af_nb[s] = af_nb[s] + 1;
                    else if (af_dt < TMCLK / 2.0) af_ns[s] = af_ns[s] + 1;
                    else                          af_na[s] = af_na[s] + 1;
                    af_want = (af_dt < TMCLK / 2.0);            // ERR 0 -> CFG_ERR: ALERT 1 from that edge on
                    if (af_exp !== af_want)
                        fail($sformatf("AF k %0d: ALERT %b modelled at the copy, but ERR changed %0.2f MCLK from its cycle's start, which gives %b",
                                       k, af_exp, af_dt / TMCLK, af_want));
                    if (af_got !== af_exp)
                        fail($sformatf("AF k %0d: %s %b; ALERT in the copy's cycle %b (spec 3.2)", k, af_nm, af_got, af_exp));
                    r14_write(7'h06, 8'hFF);            // CFG_ERR cleared
                end
            end
            for (int s = 0; s < 2; s++) begin
                if (s == 0) af_nm = "STATUS";
                else        af_nm = "the empty word";
                if (af_nb[s] < 1 || af_ns[s] < 1 || af_na[s] < 1)
                    fail($sformatf("AF not exercised (%s): ERR changed %0d times before the copy's cycle, %0d at its start, %0d at or after the copy's edge",
                                   af_nm, af_nb[s], af_ns[s], af_na[s]));
            end
            $display("AF ERR changed across the copy's cycle: a register read's STATUS %0d / %0d / %0d, an empty-FIFO sample read's word %0d / %0d / %0d (before the cycle / at its start / at or after the copy's edge), each with the ALERT of its copy's cycle (errors %0d)",
                     af_nb[0], af_ns[0], af_na[0], af_nb[1], af_ns[1], af_na[1], errors);
        end
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults back
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        // ---------------- AG (audit round 36, auditor C): T_REC and T_RST taken at the start of their waits. Spec 4.2
        // and SPI-12: a write after the guard ends acts on the running START or APPLY. Every accepted T_REC or T_RST write
        // had been made in IDLE or RUN, before the command, and a copy taking both with the command (as the analog
        // settings) passed all 16 groups. START with T_REC 32, then T_REC 200 written in WARMUP: RECOVER lasts 200 x 256
        // MCLK; in RUN with T_PRE 20, APPLY with T_RST 13, then T_RST 64 written in PRE: the AFE_RST pulse at the pin
        // lasts 64 x 256 MCLK. Outside the golden comparison (after K)
        phase = "AG";
        r14_write(7'h07, 8'hFF);
        r14_cmd(8'h11);                                 // START (T_REC 32, T_WARM 5 ms)
        wait_state(4'd1, 50.0, "AG WARMUP");
        #(20000.0);
        r14_write(7'h52, 8'd200);                       // T_REC 200 written in WARMUP (the START is taken: no guard)
        begin
            real ag_t0, ag_rec, ag_pulse;
            logic [7:0] ag_e;
            r14_read(7'h06, ag_e);
            if (ag_e !== 8'h00) fail($sformatf("AG: ERR 0x%02h after the T_REC write in WARMUP, expected 0x00 (no guard)", ag_e));
            wait_state(4'd2, 8000.0, "AG RECOVER");
            ag_t0 = $realtime;
            while (dut.seq_state === 4'd2) @(posedge MCLK);
            ag_rec = $realtime - ag_t0;
            if (ag_rec < (200.0 * 256.0 - 2.0) * TMCLK || ag_rec > (200.0 * 256.0 + 2.0) * TMCLK)
                fail($sformatf("AG: RECOVER lasted %0.1f us after T_REC 200 was written in WARMUP, expected %0.1f us (spec 4.2: taken at the wait's start)",
                               ag_rec / 1000.0, 200.0 * 256.0 * TMCLK / 1000.0));
            wait_state(4'd6, 6000.0, "AG RUN");
            r14_write(7'h53, 8'd20);                    // T_PRE 20 (156.25 us): room to write in PRE
            r14_cmd(8'h33);                             // APPLY in RUN with T_RST 13
            wait_state(4'd7, 50.0, "AG PRE");
            #(5000.0);
            r14_write(7'h54, 8'd64);                    // T_RST 64 written in PRE
            r14_read(7'h06, ag_e);
            if (ag_e !== 8'h00) fail($sformatf("AG: ERR 0x%02h after the T_RST write in PRE, expected 0x00 (no guard)", ag_e));
            @(posedge AFE_RST); ag_t0 = $realtime;
            @(negedge AFE_RST); ag_pulse = $realtime - ag_t0;
            if (ag_pulse < (64.0 * 256.0 - 2.0) * TMCLK || ag_pulse > (64.0 * 256.0 + 2.0) * TMCLK)
                fail($sformatf("AG: the AFE_RST pulse lasted %0.1f us after T_RST 64 was written in PRE, expected %0.1f us (spec 4.2)",
                               ag_pulse / 1000.0, 64.0 * 256.0 * TMCLK / 1000.0));
            wait_state(4'd6, 8000.0, "AG RUN after the APPLY");
            $display("AG T_REC 200 written in WARMUP: RECOVER %0.1f us; T_RST 64 written in PRE: the AFE_RST pulse %0.1f us at the pin (both taken at the start of their waits, spec 4.2; errors %0d)",
                     ag_rec / 1000.0, ag_pulse / 1000.0, errors);
        end
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 50.0, "AG IDLE");
        r14_cmd(8'hA5);                                 // SOFT_RESET: the timers back
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        // ---------------- AH (audit round 36, auditor C): an APPLY_NR in IDLE or WARMUP applies every setting, as
        // START and APPLY do (table 5.1-2: IDLE / WARMUP APPLY_NR [cfg_ok] -> apply; REG-08: the test shadows too; 4.10's
        // rows). Every APPLY_NR in the benches changed M only or ran with the AFE on (nr_ok makes the other settings
        // equal), and a copy whose APPLY_NR applied only the offset DAC's fields passed all 16 groups. AFE_IBIAS, CPF_TRIM
        // and TEST_MUX (through the key) changed in IDLE, then again in WARMUP, each followed by an APPLY_NR: the pins and
        // the active copies take them. Outside the golden comparison (after K)
        phase = "AH";
        for (int ah = 0; ah < 2; ah++) begin            // 0: in IDLE, 1: in WARMUP (after a START)
            logic [7:0] ah_ib, ah_cpf, ah_tm, ah_e, ah_r0, ah_r1, ah_r2;
            logic [3:0] ah_st;
            string ah_nm;
            if (ah == 0) begin ah_ib = 8'h01; ah_cpf = 8'h05; ah_tm = 8'h15; ah_st = 4'd0; ah_nm = "IDLE"; end
            else         begin ah_ib = 8'h02; ah_cpf = 8'h09; ah_tm = 8'h0A; ah_st = 4'd1; ah_nm = "WARMUP"; end
            if (ah == 1) begin
                r14_cmd(8'h11);                         // START: into WARMUP
                wait_state(4'd1, 50.0, "AH WARMUP");
            end
            r14_write(7'h23, ah_ib);                    // AFE_IBIAS
            r14_write(7'h24, ah_cpf);                   // CPF_TRIM
            r14_write(7'h11, 8'h3C);                    // TEST_KEY: unlocked
            r14_write(7'h60, ah_tm);                    // TEST_MUX, a test shadow (ATP_EN, ATP_SEL)
            r14_write(7'h11, 8'h00);                    // locked
            r14_cmd(8'h44);                             // APPLY_NR: here a full apply without a pulse
            repeat (700) @(posedge MCLK);
            r14_read(7'h06, ah_e);
            r14_read(7'h33, ah_r0);                     // the active copies
            r14_read(7'h34, ah_r1);
            r14_read(7'h70, ah_r2);
            if (ah_e !== 8'h00 || AFE_IBIAS !== ah_ib[1:0] || CPF_TRIM !== ah_cpf[3:0] || TEST_CFG[4:0] !== ah_tm[4:0] ||
                ah_r0 !== ah_ib || ah_r1 !== ah_cpf || ah_r2 !== ah_tm || dut.seq_state !== ah_st)
                fail($sformatf("AH: APPLY_NR in %s: ERR 0x%02h, pins AFE_IBIAS %0d CPF_TRIM %0d TEST_CFG[4:0] 0x%02h, active copies 0x%02h 0x%02h 0x%02h, state %0d; expected 0x00 and %0d %0d 0x%02h at the pins and in the copies (table 5.1-2, REG-08)",
                               ah_nm, ah_e, AFE_IBIAS, CPF_TRIM, TEST_CFG[4:0], ah_r0, ah_r1, ah_r2, dut.seq_state, ah_ib, ah_cpf, ah_tm));
        end
        r14_cmd(8'h22);                                 // STOP
        wait_state(4'd0, 50.0, "AH IDLE");
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults back
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        $display("AH APPLY_NR in IDLE and in WARMUP: AFE_IBIAS, CPF_TRIM and TEST_MUX at the pins and in the active copies (errors %0d)", errors);
        // ---------------- AI (audit round 36, auditor C): the read header's ADDR_ERR is raised after the header byte
        // (table 5.2-2: HDR / BYTE with an undefined read address), within its frame. tb_spi_r14's trace compares the
        // number of flag pulses per frame, not where they fall, and 1b's bursts stop before STATUS and ERR, so a copy
        // raising it at CS_N's rise with the frame's other errors passed all 16 groups. CRC off, ERR cleared: a burst from
        // the undefined 0x7F through ERR (0x06); the header's STATUS (copied at CS_N's fall) without ALERT, the burst's
        // STATUS (0x03) with ALERT and its ERR (0x06) exactly ADDR_ERR. Outside the golden comparison (after K)
        phase = "AI";
        begin
            logic [7:0] ai_e, ai_h, ai_s, ai_r;          // the burst's bytes, kept before r14_read reuses spi_rx
            spi_tx[0] = 8'hFF;                          // a read of 0x7F (undefined)
            for (int i = 1; i < 9; i++) spi_tx[i] = 8'h00;
            spi_xfer(9, 0);                             // 0x7F, 0x00 .. 0x06
            ai_h = spi_rx[0]; ai_s = spi_rx[5]; ai_r = spi_rx[8];
            if (ai_h[STATUS_ALERT_LSB] !== 1'b0 || ai_s[STATUS_ALERT_LSB] !== 1'b1 || ai_r !== 8'h08)
                fail($sformatf("AI: a burst from 0x7F: header STATUS 0x%02h, STATUS in the burst 0x%02h, ERR in the burst 0x%02h; expected ALERT only in the burst's STATUS and ERR exactly ADDR_ERR (0x08) within the frame",
                               ai_h, ai_s, ai_r));
            r14_read(7'h06, ai_e);
            if (ai_e !== 8'h08) fail($sformatf("AI: ERR 0x%02h after the burst, expected exactly ADDR_ERR", ai_e));
            $display("AI a CRC-off burst from the undefined 0x7F through ERR: ADDR_ERR and ALERT within its frame (STATUS 0x%02h in the header, 0x%02h in the burst, ERR 0x%02h; errors %0d)",
                     ai_h, ai_s, ai_r, errors);
            r14_write(7'h06, 8'hFF);
        end
        // ---------------- AJ (audit round 37, auditor C): every apply field through every command and state class
        // (table 5.1-2: START, APPLY and APPLY_NR in IDLE and WARMUP, APPLY while the AFE runs; REG-08; 4.10's rows).
        // AH changed three fields and the APPLYs in RUN four, and copies leaving the chopper settings or TEST_CTRL out
        // of an APPLY_NR, or applying the test settings only while AFE_RST is high, passed all 16 groups. The generated
        // run_apply_matrix: per class two settings that change every apply field, then the reset values; the active
        // copies before the command, then the pins, the active copies and the CHOP, CHOP_BLANK and CHOP1 widths after
        // it. Outside the golden comparison (after K)
        phase = "AJ";
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults (shadows and active copies)
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h07, 8'hFF);
        run_apply_matrix();
        for (int i = 0; i < 6; i++)
            if (aj_all[i] < 2) fail($sformatf("AJ not exercised: class %0d had %0d settings that change every apply field", i, aj_all[i]));
        if (aj_n != 18) fail($sformatf("AJ not exercised: %0d cases", aj_n));
        $display("AJ START, APPLY and APPLY_NR in IDLE and WARMUP, APPLY in RUN: every apply field at the pins, in the active copies and in the CHOP, CHOP_BLANK and CHOP1 widths (%0d cases; settings changing every field %0d / %0d / %0d / %0d / %0d / %0d; errors %0d)",
                 aj_n, aj_all[0], aj_all[1], aj_all[2], aj_all[3], aj_all[4], aj_all[5], errors);
        r14_cmd(8'hA5);                                 // SOFT_RESET: the defaults
        #(1000.0);
        r14_write(7'h06, 8'hFF);
        if (n_y_slip_smp != 1) fail($sformatf("Y1: the sample read after a slipped FIFO_LEVEL read ran %0d times, expected 1", n_y_slip_smp));
        if (n_chopout != 0) fail($sformatf("CHOP_OUT differed from CHOP in %0d cycles (CHOP_DLY must be 0)", n_chopout));
        if (n_cb_edges < 1000 || n_cb_w[0] == 0 || n_cb_w[1] == 0)
            fail($sformatf("the CHOP_BLANK monitor not exercised: %0d CHOP_OUT edges, %0d / %0d pulses measured with the DAC off / on",
                           n_cb_edges, n_cb_w[0], n_cb_w[1]));
        if (n_c1_edges < 20) fail($sformatf("the CHOP1 monitor not exercised: %0d edges", n_c1_edges));
        if (n_soft_commits < 5) fail($sformatf("the SOFT_RESET commit monitor not exercised: %0d commits", n_soft_commits));
        $display("pads: %0d CHOP_OUT edges blanked (%0d / %0d pulses measured, DAC off / on), %0d CHOP1 edges at e16 (errors %0d)",
                 n_cb_edges, n_cb_w[0], n_cb_w[1], n_c1_edges, n_cb_bad + n_c1_bad);
        $display("SOFT_RESET: %0d commits, each with soft_req in its own cycle (errors %0d)", n_soft_commits, n_soft_bad);
        $display("FILL: %0d clears at ALIGN's output time (%0d at an output not yet valid), %0d stores in FILL, each the third output after the clear (errors %0d)",
                 n_align_clr, n_align_early, n_fill_store, n_fill_bad);
        if (n_align_clr < 20 || n_align_early < 4 || n_fill_store < 20)
            fail($sformatf("the FILL monitor not exercised: %0d clears (%0d early), %0d stores", n_align_clr, n_align_early, n_fill_store));
        $display("DRDY_N pulse mode: %0d pulses, %0d of them for FILL's store (errors %0d)", n_pm_pulses, n_pm_fill, n_pm_bad);
        if (n_pm_pulses < 5 || n_pm_fill < 1) fail("DRDY_N pulse-mode monitor not exercised");
        $display("DRDY_N level mode: %0d MCLK edges checked, %0d stores with DRDY_N high, %0d falls at the next edge (errors %0d)",
                 n_lm_checks, n_lm_first, n_lm_falls, n_lm_bad);
        if (n_lm_checks < 100000 || n_lm_falls < 20) fail("DRDY_N level-mode monitor not exercised");
        $display("RAW: %0d frames of the stream with 8 RAW_CLK rises, %0d MCLK of a timing pair one MCLK later (errors %0d)",
                 n_raw_frames, n_raw_pairs, n_raw_cut + n_raw_pair);
        if (n_raw_frames < 20 || n_raw_pairs < 1000) fail("RAW monitors not exercised");

        $fclose(flog);
        $fclose(fsmp);
        $fclose(fseq);
        if (ana_afe_rst !== afe_falls + afe_rises) fail($sformatf("monitor saw %0d AFE_RST changes, the pin %0d edges",
                                                                  ana_afe_rst, afe_falls + afe_rises));
        if (n_pinrule != 0) fail($sformatf("applied pins differed from their active copies in %0d cycles", n_pinrule));
        $display("tb_top_r14: %0d SPI transfers, %0d samples, %0d analog pin changes (%0d of AFE_RST), %0d SPI errors, %0d errors, ended at %0.3f ms",
                 spi_xfers, nsamples, ana_changes, ana_afe_rst, spi_errors, errors, $realtime / 1.0e6);
        if (errors == 0 && spi_errors == 0) $display("PASS: tb_top_r14");
        else                                $display("FAIL: tb_top_r14");
        $finish;
    end
endmodule

`default_nettype wire
