// tb_top_r14 - eeg_digital_top (r14) through its pins, with an SPI master on its own time base.
//
// CODE is driven once per frame (it changes at e2, after the TH capture, as eeg_adc_dig's code; audit round 9) from
// build/top_r14.codes (the CT loop model's stream); every CIC input
// and every output time are logged (build/top_r14_cic.log) and every sample read over SPI (build/top_r14_samples.log)
// so that tb/check_top_r14.py compares the samples bit-exactly with the golden CIC (rtl/model/cic_golden.py).
// Phases (each reports its checks; errors counted):
//   A  registers: the generated tests (build/reg_tests.svh, from regmap.py), CRC, frame errors, unknown command,
//      a wrong key, a burst read (address incrementing, CRC off); audit round 15 (auditor C): every illegal value of
//      every field (RANGE_ERR, nothing written), the write-only COMMAND and TEST_KEY read 0x00 while unlocked and
//      after a committed FLUSH (alone and in a burst)
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
//   I  SOFT_RESET while a command is pending (64 kHz): taken at once, no STATE_ERR
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
//      pin is at its reset value (a register block with a synchronous reset passed every test)
//   Y  audit round 15 (auditor C): SOFT_RESET returns every register and flag (RST-02), written with CRC off and on:
//      every writable register away from its reset value (soft_set_all, generated), START, both DFLAG bits set,
//      samples in the FIFO, ERR holding ADDR_ERR; after it the generated burst over the whole map (ERR exactly 0x01,
//      DFLAG 0x00, STATUS 0xA1, the timers, masks, settings and active copies), the pins, DRDY_N high, the test
//      registers locked (a register block keeping the timers, the ALERT masks, DFLAG or DRDY_MODE through a SOFT_RESET
//      passed every test). On the way, STATUS with READY and DATA apart: RUN with the FIFO empty (READY 1, DATA 0),
//      IDLE with samples left (READY 0, DATA 1); no check had told them apart
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
// A watchdog ends the run as FAIL if it has not finished by 800 ms of simulated time (the run ends near 0.6 s; audit
// round 15, auditor C: the 600 ms, written as about 1.6 times the run, had become 1.13 times it),
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
        free_wait_flush();
        r14_write(a, w);
        spi_tidle = 600.0;
        expect_err_exact(8'h00, $sformatf("J2 %s (W1C) written while a command is pending (not guarded)", name));
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
        #(800.0e6);
        fail($sformatf("watchdog: not finished after 800 ms of simulated time (phase %s)", phase));
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
    // timer and the conditions with the actions; after it the next state and the timer
    integer fseq, seq_frames = 0;
    logic       q_tick, q_out, q_fs, q_cv, q_cfg, q_nr, q_valid, q_te0, q_rst = 1'b1, q_inrst = 1'b1;
    logic [3:0] q_st;
    logic [7:0] q_cc, q_acts, q_tw, q_te, q_tr, q_tp, q_tq;
    logic [17:0] q_tb;
    initial fseq = $fopen("build/top_seq_trace.txt", "w");
    always @(negedge MCLK) begin
        q_rst  = dut.u_seq.rst_n;
        q_tick = dut.u_seq.tick;       q_out = dut.u_seq.out_stb;     q_fs = dut.u_seq.frame_stb;
        q_st   = dut.u_seq.state;      q_cv  = dut.u_seq.cmd_valid;   q_cc = dut.u_seq.cmd_code;
        q_cfg  = dut.u_seq.cfg_ok;     q_nr  = dut.u_seq.nr_ok;       q_valid = dut.u_seq.out_valid;
        q_tb   = dut.u_seq.timer;      q_te0 = (dut.u_seq.t_elec == 8'd0);
        q_acts = {dut.u_seq.apply, dut.u_seq.flush, dut.u_seq.store, dut.u_seq.mark, dut.u_seq.state_err,
                  dut.u_seq.cfg_err, dut.u_seq.cic_arm && dut.u_seq.out_stb, dut.u_seq.a_restart};
        q_tw = dut.u_seq.t_warm;  q_te = dut.u_seq.t_elec;  q_tr = dut.u_seq.t_rec;  q_tp = dut.u_seq.t_pre;
        q_tq = dut.u_seq.t_rst;
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
    always @(negedge DRDY_N) n_drdy_fall = n_drdy_fall + 1;
    integer n_rawclk = 0;
    always @(posedge RAW_CLK) n_rawclk = n_rawclk + 1;

    // ------------------------------------------------------------------ R: SOFT_RESET committed in this cycle
    // called 1 ns after a rising MCLK edge (before the falling edge where the sequencer trace samples its inputs):
    // soft_req (the register block's commit of 0xA5) is forced high until just after the next rising edge, where
    // rst_n falls
    task automatic soft_now();
        force dut.soft_req = 1'b1;
        @(posedge MCLK); #1;
        release dut.soft_req;
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
    // RAW's bit timing while the stream runs (audit round 9: a word loaded at cycle 0 instead of 31 passed): RAW_DATA
    // changes only at e1, e5, ..., e29 and RAW_CLK rises only at e3, e7, ..., e31
    integer n_raw_t = 0;
    always @(RAW_DATA) begin
        #1;
        if (dut.u_raw.on === 1'b1 && dut.rst_n === 1'b1 && dut.cycle[1:0] !== 2'd1) begin
            n_raw_t = n_raw_t + 1;
            if (n_raw_t <= 3) fail($sformatf("RAW_DATA changed in frame cycle %0d (only at e1, e5, ...)", dut.cycle));
        end
    end
    always @(posedge RAW_CLK) begin
        #1;
        if (dut.u_raw.on === 1'b1 && dut.rst_n === 1'b1 && dut.cycle[1:0] !== 2'd3) begin
            n_raw_t = n_raw_t + 1;
            if (n_raw_t <= 3) fail($sformatf("RAW_CLK rose in frame cycle %0d (only at e3, e7, ...)", dut.cycle));
        end
    end

    // RAW (audit round 8): with the stream off (eeg_raw's `on` 0, RAW_EN taken at the frame boundary) and DBG_SEL 0,
    // both pads stay low (RST-02, the eeg_raw header; the pad coupling is rated for RAW on only). The pads are
    // registered, so the condition must have held for 2 MCLK.
    logic [1:0] raw_quiet_q = 2'b00;
    integer     n_raw_noisy = 0;
    always @(posedge MCLK) begin
        raw_quiet_q <= {raw_quiet_q[0], dut.u_raw.on === 1'b0 && dut.u_raw.dbg_sel === 2'b00};
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

    // ------------------------------------------------------------------ the test
    logic [7:0] v;
    real t_start_tick, t0, t1;
    integer seq_before;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        if (n_release != 3) fail($sformatf("the first CMP_STROBE %0d MCLK after the RESET_N release, expected 3 (two synchronizer flops and the strobe's register)", n_release));
        prev_tick = 1'b0;
        ana_q = ana;
        check_reset_pins("after RESET_N");

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
        spi_tx[0] = 8'hC0; spi_xfer(3, 2);                           // a sample read stopped inside a byte
        expect_err_now(8'h02, "FRAME_ERR (sample read stopped inside a byte)");
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // too long
        if (spi_rx[1] !== 8'h00 || spi_rx[2] !== 8'h00)
            fail($sformatf("MISO after the header of an overlong write: %02h %02h, expected 00 00", spi_rx[1], spi_rx[2]));
        expect_err_now(8'h02, "FRAME_ERR (overlong write)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM unchanged after an overlong write");
        CS_N = 1'b0; #500; CS_N = 1'b1; #600;                        // empty frame
        expect_noerr("empty frame");
        // every illegal state value of the SPI state machine (NFR-05): FRAME_ERR at CS_N rising, nothing written
        for (int bad = 11; bad < 16; bad++) begin
            fork
                begin
                    spi_tx[0] = 8'h24; spi_tx[1] = 8'h0E; spi_xfer(2, 0);
                end
                begin
                    #(6000.0);                          // inside the data byte (constant forces: Icarus
                    case (bad)                          // evaluates a forced expression only once)
                        11:      force dut.u_spi.st = 4'd11;
                        12:      force dut.u_spi.st = 4'd12;
                        13:      force dut.u_spi.st = 4'd13;
                        14:      force dut.u_spi.st = 4'd14;
                        default: force dut.u_spi.st = 4'd15;
                    endcase
                    @(posedge MCLK);
                    release dut.u_spi.st;
                end
            join
            expect_err_now(8'h02, $sformatf("FRAME_ERR for the illegal SPI state value %0d", bad));
            rt_read_expect(7'h24, 8'h08, $sformatf("CPF_TRIM not written by a frame with the illegal SPI state %0d", bad));
        end
        // ... and between frames (CS_N high; audit round 15, auditor B): the value stays until the next CS_N fall, which
        // starts that frame in the header state; the frame is processed normally and nothing is flagged (NFR-05)
        for (int bad = 11; bad < 16; bad++) begin
            @(posedge MCLK); #1;
            case (bad)                                  // constant forces (Icarus)
                11:      force dut.u_spi.st = 4'd11;
                12:      force dut.u_spi.st = 4'd12;
                13:      force dut.u_spi.st = 4'd13;
                14:      force dut.u_spi.st = 4'd14;
                default: force dut.u_spi.st = 4'd15;
            endcase
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
        t_start_tick = $realtime - TMCLK;               // the state changed at e25 of the tick
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
            spi_tx[0] = 8'hC0; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00; spi_tx[3] = 8'h00;
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
        t0 = $realtime;
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
        $display("D  APPLY_NR, CHANGED cancelled on leaving RUN, the longer mark kept (errors %0d)", errors);

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
            if (st[7] !== 1'b0 || st[6] !== 1'b1 || !ok)
                fail($sformatf("the empty word after an overrun: status 0x%02h, expected VALID 0 and OVERRUN 1", st));
        end
        for (int i = 0; i < 2; i++) begin             // two samples (audit round 14, auditor C: OVERRUN kept only
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;   // until the next store passed every test)
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (st[6] !== 1'b1) fail($sformatf("sample %0d status without OVERRUN while DFLAG.OVERRUN is set", i));
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
        r14_cmd(8'h55);                                 // FLUSH, pending until the next tick
        r14_cmd(8'hA5);                                 // SOFT_RESET while FLUSH is pending
        spi_tidle = 600.0;
        repeat (50) @(posedge MCLK);
        if (soft_pend !== 1'b1) fail("I not exercised: no command pending when SOFT_RESET was taken");
        if (dut.seq_state !== 4'd0 || dut.a_chop_fast !== 1'b1) fail("I: SOFT_RESET with a pending command not taken");
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
        spi_tx[0] = 8'hC0;
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
                r14_write(7'h11, 8'h3C);
                r14_write(7'h62, 8'(s << 1));
                r14_write(7'h11, 8'h00);
                repeat (3 * 32) @(posedge MCLK);
                fo = 0;
                pc = 1'bx; pd = 1'bx;
                repeat (600) begin
                    @(posedge MCLK); #0.2;
                    if (pc !== 1'bx && (RAW_CLK !== pc || RAW_DATA !== pd)) fo = fo + 1;
                    case (s)
                        1: begin pc = CMP_STROBE; pd = DAC_CLK; end
                        2: begin pc = CHOP;       pd = CHOP_OUT; end
                        default: begin pc = CHOP_BLANK; pd = CHOP1; end
                    endcase
                end
                if (fo != 0) fail($sformatf("O DBG_SEL %0d: RAW_CLK / RAW_DATA differ from their pair in %0d cycles", s, fo));
            end
            r14_write(7'h11, 8'h3C);
            r14_write(7'h62, 8'h00);
            r14_write(7'h11, 8'h00);
        end
        $display("O  RAW stream and timing pairs (errors %0d)", errors);

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
                spi_tx[0] = 8'h40;
                for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00;
                spi_xfer(8, 0);
                bfm_crc_en = crc[0];
                c = tb_crc8_update(8'h00, 8'hC0);
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
                if (!eok || es[7] !== 1'b0 || es[5] !== 1'b0)
                    fail($sformatf("T2: empty word status 0x%02h 60 frames after the overload (OVL is OVL_NOW, 0)", es));
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
            // taken in PRE at the next tick (the host's SPI at its fastest: SCLK high 4, low 5 MCLK; the APPLY written
            // just after a tick of the other half of the 512-MCLK superperiod is taken at the next tick, the STOP written
            // as PRE begins commits about 150 MCLK later). The APPLY taken in frame 1 (k 0): the STOP's tick is the next
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
                spi_high = 4.0 * TMCLK + 0.3; spi_low = 5.0 * TMCLK + 0.3;
                spi_tcss = 5.0 * TMCLK + 0.3; spi_tcsh = 3.0 * TMCLK + 0.3; spi_tidle = 4.0 * TMCLK + 0.3;
                do @(posedge dut.tick); while (dut.u_clkgen.cnt[8] !== (k == 0 ? 1'b1 : 1'b0));   // the other half
                r14_cmd(8'h33);                                     // APPLY: taken at the next tick, frame 1 or 9
                wait_state(4'd7, 50.0, "V13 PRE");
                r14_cmd(8'h22);                                     // STOP: before the next tick
                spi_high = 250.0; spi_low = 250.0; spi_tcss = 300.0; spi_tcsh = 200.0; spi_tidle = 600.0;
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
            logic [7:0] ys, smask; logic [15:0] yq; logic [23:0] yd; bit yok;
            smask = 8'hFF & ~((8'h01 << STATUS_ALERT_LSB) | (8'h01 << STATUS_OVL_NOW_LSB));
            soft_set_all(pass[0]);
            r14_cmd(8'h11);                                     // START: the settings applied
            wait_state(4'd6, 15000.0, "Y RUN");
            @(posedge dut.push_ok);                             // just after a store: the next one is 1 ms away
            @(posedge MCLK);
            do r14_sample(ys, yq, yd, yok); while (!(yok && ys[SMP_VALID_LSB] === 1'b0));
            check_status(8'h80 | (8'h01 << STATUS_READY_LSB), smask, $sformatf("Y%0d: STATUS in RUN with the FIFO empty (READY 1, DATA 0)", pass));
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
            if (DRDY_N !== 1'b1) fail($sformatf("Y%0d: DRDY_N %b after SOFT_RESET (level mode, FIFO empty)", pass, DRDY_N));
            r14_write(7'h06, 8'h01);
            rt_write_check(7'h60, 8'h11, 8'h00, 8'h08, $sformatf("Y%0d: TEST_MUX locked after SOFT_RESET", pass));
        end
        $display("Y  SOFT_RESET returns every register and flag, CRC off and on; STATUS's READY and DATA apart (errors %0d)", errors);
        if (n_chopout != 0) fail($sformatf("CHOP_OUT differed from CHOP in %0d cycles (CHOP_DLY must be 0)", n_chopout));

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
