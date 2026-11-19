// tb_top_r14 - eeg_digital_top (r14) through its pins, with an SPI master on its own time base.
//
// CODE is driven once per frame (cycle 16) from build/top_r14.codes (the CT loop model's stream); every CIC input
// and every output time are logged (build/top_r14_cic.log) and every sample read over SPI (build/top_r14_samples.log)
// so that tb/check_top_r14.py compares the samples bit-exactly with the golden CIC (rtl/model/cic_golden.py).
// Phases (each reports its checks; errors counted):
//   A  registers: the generated tests (build/reg_tests.svh, from regmap.py), CRC, frame errors, unknown command,
//      a wrong key, a burst read (address incrementing, CRC off)
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
//   H  SOFT_RESET: back to the reset values (RESET_FLAG); SEQ, the frame counter and the choppers keep running
//   I  SOFT_RESET while a command is pending (64 kHz): taken at once, no STATE_ERR
//   J  audit round 1 (11/20): every STATUS bit; at 64 kHz a write to a shadow or a timer while a command is pending
//      gets STATE_ERR (other registers are written); CRC on: a header-only read is legal, a read without its CRC
//      byte and a short sample read are FRAME_ERR; APPLY in WARMUP restarts T_WARM (AFE_RST released T_WARM after
//      the change); APPLY empties the FIFO; an injected overload sets OVL_NOW, DFLAG.OVL (only in FILL / RUN) and
//      the OVL bit of exactly the three samples whose window contains it
//   K  SEQ wraps from 0xFFFF to 0 (forced near the end, samples outside the golden comparison)
//   M  audit round 2 (11/20): the sample's ERR bit (ALERT at the store) and reserved bits, ALERT_MASK and
//      ALERT_MASK_D, the empty word (VALID 0, OVERRUN, OVL_NOW, ERR = ALERT, SEQ 0, DATA 0, CRC), the DRDY_N release in
//      level mode (at most 5 MCLK after the CS_N rise of the read that emptied the FIFO)
//   L  SPI at the specification's limits (VER-02): 2 MHz with the minimum high (4 MCLK) or the minimum low (5 MCLK),
//      and 1 MHz; CS_N setup 5 MCLK, hold 3 MCLK, high 4 MCLK; MISO through the 15 ns pad delay; CRC off and on
//   N  audit round 2 (auditor C): every analog control pin against the specification (build/pin_tests.svh, generated
//      from regmap.pins_from_active: OFM / OFS / OFEN per range, trims, CHOP_EN, DWA_EN, TEST_CFG, the CHOP_BLANK
//      length or hold, the chopper's and CHOP1's half periods, the active copies; M above the range's top -> CFG_ERR
//      and nothing applied), DFLAG.OVL not set by an overload in WARMUP, RECOVER, PRE and PULSE but set in FILL, an
//      APPLY_NR across a range -> CFG_ERR
// Also: RECOVER lasts T_REC (B) and WAIT_E T_ELEC (D); through a SOFT_RESET (H) CHOP1 keeps its phase and ADC_RST_N
// stays high; every sequencer event of the run is written to build/top_seq_trace.txt and replayed through
// fsm_spec.seq_tick by check_seq_trace.py --no-cover (VER-09 end to end).
// Define FIFO4 for the 4-deep FIFO (CAPS and the overrun test follow).
// Monitors: every analog control pin (AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM, TEST_CFG[5:0],
// CHOP_EN, DWA_EN) changes only at the MCLK edge right after a tick (or in reset); the SPI timing (spi_bfm_r14.svh).
// A watchdog ends the run as FAIL if it has not finished by 400 ms of simulated time (about twice the normal length),
// so that an RTL error that leaves the bench waiting for an event fails instead of hanging.
`timescale 1ns / 1ps
`default_nettype none

module tb_top_r14;
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

    always #(TMCLK / 2.0) MCLK = ~MCLK;

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
        #(400.0e6);
        fail($sformatf("watchdog: not finished after 400 ms of simulated time (phase %s)", phase));
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
    always @(posedge MCLK) begin
        if (dut.cycle == 5'd16 && RESET_N) begin
            CODE <= ovl_force ? 5'd31 : codes[cidx % ncodes];
            cidx <= cidx + 1;
        end
        if (log_on && dut.cic_en) $fdisplay(flog, "I %0d", CODE);
        if (log_on && dut.cic_stb) $fdisplay(flog, "O %0d %0d", dut.seq_cnt, dut.cic_arm);
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

    // ------------------------------------------------------------------ AFE_RST pin edges
    real t_afe_fall = 0.0, t_afe_rise = 0.0;
    integer afe_falls = 0, afe_rises = 0;
    always @(negedge AFE_RST) begin t_afe_fall = $realtime; afe_falls = afe_falls + 1; end
    always @(posedge AFE_RST) begin t_afe_rise = $realtime; afe_rises = afe_rises + 1; end
    real t_chop_rise = 0.0;
    always @(posedge CHOP) t_chop_rise = $realtime;
    real t_cpf = 0.0;                             // J4: the time of the last CPF_TRIM pin change
    always @(CPF_TRIM) t_cpf = $realtime;
    always @(negedge AFE_RST or posedge AFE_RST) begin
        // every AFE_RST edge: 57 MCLK after a rising CHOP edge (the tick, outputs at e25) at 128 kHz
        if (RESET_N && dut.rst_n && dut.a_chop_fast &&
            ((($realtime - t_chop_rise) / TMCLK) < 56.5 || (($realtime - t_chop_rise) / TMCLK) > 57.5))
            fail($sformatf("AFE_RST edge %0.2f MCLK after the CHOP rising edge (expected 57)",
                           ($realtime - t_chop_rise) / TMCLK));
    end

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
    real t_chop1_edge = 0.0;
    always @(CHOP1) t_chop1_edge = $realtime;
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

    integer mclk_count = 0;
    always @(posedge MCLK) mclk_count = mclk_count + 1;

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
            $fdisplay(fsmp, "%0d %0d %0d", sq, $signed(d), st);
            nsamples = nsamples + 1;
        end
    endtask

    // ------------------------------------------------------------------ the test
    logic [7:0] v;
    real t_start_tick, t0, t1;
    integer seq_before;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        prev_tick = 1'b0;
        ana_q = ana;

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
        expect_err_now(8'h02, "FRAME_ERR (overlong write)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM unchanged after an overlong write");
        CS_N = 1'b0; #500; CS_N = 1'b1; #600;                        // empty frame
        expect_noerr("empty frame");
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
        read_samples(4, -1, "C samples");
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
        r14_cmd(8'h55);
        repeat (400) @(posedge MCLK);
        while (DRDY_N !== 1'b0) @(posedge MCLK);
        begin
            logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
            r14_sample(st, sq, d, ok);
            if (st[6] !== 1'b1) fail("sample status without OVERRUN while DFLAG.OVERRUN is set");
        end
        r14_write(7'h07, 8'hFF);
        r14_read(7'h07, v);
        if (v !== 8'h00) fail($sformatf("DFLAG 0x%02h after writing 0xFF (W1C)", v));
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
            real tc0;
            tc0 = t_chop1_edge;                         // CHOP1 at 4 kHz (half period 4096 MCLK) since START
            r14_write(7'h24, 8'h03);
            @(posedge MCLK); #1;
            seq0 = dut.seq_cnt;  cnt0 = dut.u_clkgen.cnt;  n0 = mclk_count;
            r14_cmd(8'hA5);
            repeat (50) @(posedge MCLK);
            #1;
            if (dut.seq_state !== 4'd0 || AFE_RST !== 1'b1) fail("SOFT_RESET: not IDLE");
            if (dut.u_clkgen.cnt !== 9'((cnt0 + mclk_count - n0) % 512))
                fail($sformatf("SOFT_RESET moved the frame counter: %0d, expected %0d", dut.u_clkgen.cnt,
                               (cnt0 + mclk_count - n0) % 512));
            if (dut.seq_cnt < seq0) fail($sformatf("SOFT_RESET reset SEQ: %0d after %0d", dut.seq_cnt, seq0));
            repeat (9000) @(posedge MCLK);              // past the next CHOP1 edges
            if (t_chop1_edge <= tc0 || ($rtoi((t_chop1_edge - tc0) / TMCLK + 0.5) % 4096) != 0)
                fail($sformatf("SOFT_RESET moved CHOP1: an edge %0.2f MCLK after the one before it",
                               (t_chop1_edge - tc0) / TMCLK));
        end
        rt_read_expect(7'h06, 8'h01, "ERR after SOFT_RESET (RESET_FLAG)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM after SOFT_RESET");
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
        spi_tx[0] = 8'hC0;
        spi_xfer(8, 0);
        expect_noerr("J3 complete sample read with CRC on");
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
                $fdisplay(fsmp, "%0d %0d %0d", sq, $signed(d), st);
                nsamples = nsamples + 1;
            end
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

        // ---------------- K: SEQ wraps from 0xFFFF to 0 (forced; outside the golden comparison)
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

        // ---------------- M: status bits no other phase checks (audit round 2, 11/20); RUN, outside the golden log
        phase = "M";
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
        wait_state(4'd8, 2100.0, "N4 PULSE");
        wait_state(4'd2, 2100.0, "N4 RECOVER");
        wait_state(4'd4, 2100.0, "N4 ALIGN");
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
        $display("N  analog pins (generated cases), DFLAG.OVL gating, APPLY_NR across a range, timer limits (errors %0d)", errors);

        $fclose(flog);
        $fclose(fsmp);
        $fclose(fseq);
        if (ana_afe_rst !== afe_falls + afe_rises) fail($sformatf("monitor saw %0d AFE_RST changes, the pin %0d edges",
                                                                  ana_afe_rst, afe_falls + afe_rises));
        $display("tb_top_r14: %0d SPI transfers, %0d samples, %0d analog pin changes (%0d of AFE_RST), %0d SPI errors, %0d errors, ended at %0.3f ms",
                 spi_xfers, nsamples, ana_changes, ana_afe_rst, spi_errors, errors, $realtime / 1.0e6);
        if (errors == 0 && spi_errors == 0) $display("PASS: tb_top_r14");
        else                                $display("FAIL: tb_top_r14");
        $finish;
    end
endmodule

`default_nettype wire
