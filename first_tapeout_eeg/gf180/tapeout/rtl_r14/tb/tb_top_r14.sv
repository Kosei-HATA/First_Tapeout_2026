// tb_top_r14 - eeg_digital_top (r14) through its pins, with an SPI master on its own time base.
//
// CODE is driven once per frame (cycle 16) from build/top_r14.codes (the CT loop model's stream); every CIC input
// and every output time are logged (build/top_r14_cic.log) and every sample read over SPI (build/top_r14_samples.log)
// so that tb/check_top_r14.py compares the samples bit-exactly with the golden CIC (rtl/model/cic_golden.py).
// Phases (each reports its checks; errors counted):
//   A  registers: the generated tests (build/reg_tests.svh, from regmap.py), CRC, frame errors, unknown command
//   B  START: WARMUP exactly T_WARM, RECOVER T_REC, ALIGN to the next output time, FILL three outputs, RUN;
//      samples (VALID, SEQ, CRC)
//   C  APPLY in RUN: the settings at the tick, AFE_RST high after T_PRE for exactly T_RST, the re-settling, samples
//      again with the SEQ gap of the outputs not stored
//   D  APPLY_NR: one step accepted, CHANGED on the next three samples; two steps rejected (CFG_ERR)
//   E  START with an inconsistent configuration (CFG_ERR), STOP, START in RUN (STATE_ERR)
//   F  one pending command: at 64 kHz a second command before the tick gets STATE_ERR
//   G  FLUSH, overrun (OVERRUN in DFLAG and in the next sample's status)
//   H  SOFT_RESET: back to the reset values (RESET_FLAG)
// Monitors: every analog control pin (AFE_RST, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM, TEST_CFG[5:0],
// CHOP_EN, DWA_EN) changes only at the MCLK edge right after a tick (or in reset); the SPI timing (spi_bfm_r14.svh).
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

    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);

    always #(TMCLK / 2.0) MCLK = ~MCLK;

    `include "spi_bfm_r14.svh"
    `include "reg_tests.svh"

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
    always @(posedge MCLK) begin
        if (dut.cycle == 5'd16 && RESET_N) begin
            CODE <= codes[cidx % ncodes];
            cidx <= cidx + 1;
        end
        if (dut.cic_en) $fdisplay(flog, "I %0d", CODE);
        if (dut.cic_stb) $fdisplay(flog, "O %0d %0d", dut.seq_cnt, dut.cic_arm);
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
    always @(negedge AFE_RST or posedge AFE_RST) begin
        // every AFE_RST edge: 57 MCLK after a rising CHOP edge (the tick, outputs at e25) at 128 kHz
        if (RESET_N && dut.rst_n && dut.a_chop_fast &&
            ((($realtime - t_chop_rise) / TMCLK) < 56.5 || (($realtime - t_chop_rise) / TMCLK) > 57.5))
            fail($sformatf("AFE_RST edge %0.2f MCLK after the CHOP rising edge (expected 57)",
                           ($realtime - t_chop_rise) / TMCLK));
    end

    // ------------------------------------------------------------------ samples
    integer nsamples = 0;
    logic [15:0] last_seq;
    bit          have_last = 1'b0;
    task automatic read_samples(input integer n, input logic expect_changed_first3, input string name);
        logic [7:0] st;
        logic [15:0] sq;
        logic [23:0] d;
        bit ok;
        for (int i = 0; i < n; i++) begin
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            r14_sample(st, sq, d, ok);
            if (!ok) fail($sformatf("%s: sample CRC", name));
            if (st[7] !== 1'b1) fail($sformatf("%s: sample not VALID (status 0x%02h)", name, st));
            if (expect_changed_first3 && i < 3 && st[4] !== 1'b1) fail($sformatf("%s: sample %0d without CHANGED", name, i));
            if (expect_changed_first3 && i >= 3 && st[4] !== 1'b0) fail($sformatf("%s: sample %0d with CHANGED", name, i));
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
        spi_tx[0] = 8'h24; spi_tx[1] = 8'h03; spi_tx[2] = 8'h00; spi_xfer(3, 0);   // too long
        expect_err_now(8'h02, "FRAME_ERR (overlong write)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM unchanged after an overlong write");
        CS_N = 1'b0; #500; CS_N = 1'b1; #600;                        // empty frame
        expect_noerr("empty frame");
        r14_cmd(8'h77);
        expect_err_now(8'h80, "CMD_ERR (unknown code)");
        $display("A  registers, CRC and frame errors done (errors %0d)", errors);

        // ---------------- B: START
        r14_cmd(8'h11);
        wait_state(4'd1, 50.0, "WARMUP after START");
        t_start_tick = $realtime - TMCLK;               // the state changed at e25 of the tick
        wait_state(4'd2, 5100.0, "RECOVER after T_WARM");
        t0 = (t_afe_fall - t_start_tick) / 1000.0;
        if (t0 < 4999.0 || t0 > 5001.0) fail($sformatf("T_WARM %0.3f us, expected 5000", t0));
        wait_state(4'd4, 300.0, "ALIGN after T_REC");
        wait_state(4'd5, 1100.0, "FILL at the next output time");
        wait_state(4'd6, 3100.0, "RUN after three outputs");
        r14_read(7'h03, v);
        if (v[3] !== 1'b1) fail("STATUS.READY not set in RUN");
        read_samples(6, 1'b0, "B samples");
        $display("B  START to RUN, T_WARM %0.3f us, 6 samples (errors %0d)", t0, errors);

        // ---------------- C: APPLY in RUN
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
        read_samples(4, 1'b0, "C samples");
        $display("C  APPLY: pulse %0.4f us, SEQ %0d -> %0d (errors %0d)", t1, seq_before, last_seq, errors);

        // ---------------- D: APPLY_NR
        r14_write(7'h22, 8'h01);                        // range 1 (needs APPLY with a pulse)
        r14_write(7'h21, 8'h0A);                        // M = 10
        r14_cmd(8'h33);
        wait_state(4'd7, 50.0, "PRE after APPLY of range 1");     // RUN until the tick
        if (OFEN !== 4'b0001 || OFM !== 10'd10 || OFS !== 1'b0) fail("offset DAC pins after APPLY");
        wait_state(4'd6, 6000.0, "RUN after APPLY of range 1");
        while (DRDY_N === 1'b0) read_samples(1, 1'b0, "D drain");
        read_samples(1, 1'b0, "D sync");                // right after an output: the next one is 1 ms away
        r14_write(7'h21, 8'h0B);                        // M = 11: one step
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        if (dut.seq_state !== 4'd6 || OFM !== 10'd11) fail("APPLY_NR of one step");
        read_samples(5, 1'b1, "D CHANGED");
        r14_write(7'h21, 8'h0D);                        // M = 13: two steps
        r14_cmd(8'h44);
        repeat (300) @(posedge MCLK);
        expect_err_now(8'h20, "CFG_ERR for an APPLY_NR of two steps");
        if (OFM !== 10'd11) fail("two-step APPLY_NR applied");
        r14_write(7'h21, 8'h0B);
        $display("D  APPLY_NR (errors %0d)", errors);

        // ---------------- E: START in RUN, STOP, START with an inconsistent configuration
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
        r14_write(7'h26, 8'h00);                        // CHOP_FAST 0
        r14_cmd(8'h33);                                 // APPLY in IDLE: no pulse
        repeat (2000) @(posedge MCLK);
        if (dut.a_chop_fast !== 1'b0) fail("64 kHz not applied");
        expect_noerr("APPLY in IDLE");
        @(posedge dut.tick);
        #(8000.0);
        spi_tidle = 100.0;
        r14_cmd(8'h55);                                 // FLUSH
        r14_cmd(8'h55);                                 // before the next tick (15.6 us)
        spi_tidle = 600.0;
        expect_err_now(8'h40, "STATE_ERR for a second command before the tick (64 kHz)");
        r14_write(7'h26, 8'h01);
        r14_cmd(8'h33);
        repeat (2000) @(posedge MCLK);
        $display("F  pending command (errors %0d)", errors);

        // ---------------- G: FLUSH and overrun
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
        r14_write(7'h06, 8'hFF);
        $display("G  FLUSH and overrun (errors %0d)", errors);

        // ---------------- H: SOFT_RESET
        r14_write(7'h24, 8'h03);
        r14_cmd(8'hA5);
        repeat (50) @(posedge MCLK);
        if (dut.seq_state !== 4'd0 || AFE_RST !== 1'b1) fail("SOFT_RESET: not IDLE");
        rt_read_expect(7'h06, 8'h01, "ERR after SOFT_RESET (RESET_FLAG)");
        rt_read_expect(7'h24, 8'h08, "CPF_TRIM after SOFT_RESET");
        $display("H  SOFT_RESET (errors %0d)", errors);

        $fclose(flog);
        $fclose(fsmp);
        if (ana_afe_rst !== afe_falls + afe_rises) fail($sformatf("monitor saw %0d AFE_RST changes, the pin %0d edges",
                                                                  ana_afe_rst, afe_falls + afe_rises));
        $display("tb_top_r14: %0d SPI transfers, %0d samples, %0d analog pin changes (%0d of AFE_RST), %0d SPI errors, %0d errors",
                 spi_xfers, nsamples, ana_changes, ana_afe_rst, spi_errors, errors);
        if (errors == 0 && spi_errors == 0) $display("PASS: tb_top_r14");
        else                                $display("FAIL: tb_top_r14");
        $finish;
    end
endmodule

`default_nettype wire
