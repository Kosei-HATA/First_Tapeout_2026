// tb_spi - SPI slave + registers + FIFO, at the eeg_digital_top level.
//
// TH is held at a constant code, so every valid sample after a FILTER_CLEAR
// is exactly (2c - 31) * 2^18. The SPI master (tb/spi_bfm.svh) runs on its
// own time base, asynchronous to MCLK, at 2 MHz and 1 MHz.
//
// Covered: ID/VERSION/FORMAT/ODR/defaults, undefined addresses, CONTROL /
// CHOP_DLY / TEST / ANA_TRIM / BLANK / BOOST_TRIM / OFF_CODE_L / OFF_CTRL write and read back
// (and their pins, including the OFEN range decode),
// CONTROL bit 7 reads 0, FILTER_CLEAR self clearing, CHOP_FAST (128/64 kHz
// chop measured on the pins, CHOP_OUT delays at both rates), CHOP_BLANK on the
// pins (rise 1 MCLK before each CHOP_OUT edge, fall BLANK_LEN after it, for
// BLANK_LEN 7, 15, 1, 0), RO registers ignore
// writes, partial / over-long WRITE_REG ignored,
// unknown command -> CMD_ERR, W1C of CMD_ERR and OVERRUN (writing 0 does not
// clear), empty READ_SAMPLE, settling time, READ_SAMPLE frame contents and CRC,
// partial and over-long READ_SAMPLE frames do not consume, sequence numbers,
// FIFO overrun keeps the 8 oldest samples and stamps OVERRUN, RUN = 0 stops
// storing while SEQ keeps counting, DRDY_N == (FIFO empty) at every MCLK,
// MISO/MISO_OE timing monitors.
`timescale 1ns / 1ps

module tb_spi;

    localparam real TMCLK = 30.5176;           // 32.768 MHz

    logic        MCLK = 1'b0;
    logic        RESET_N = 1'b0;
    logic        SCLK = 1'b0;
    logic        CS_N = 1'b1;
    logic        MOSI = 1'b0;
    logic [30:0] TH;
    wire         MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK;
    wire  [30:0] SEL1, SEL2;
    wire         CMP_STROBE, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN;
    wire  [7:0]  TEST_CFG;
    wire  [3:0]  CPF_TRIM;
    wire  [1:0]  AFE_IBIAS;
    wire  [1:0]  BTRIM_P;
    wire  [1:0]  BTRIM_N;
    wire  [9:0]  OFM;
    wire         OFS;
    wire  [3:0]  OFEN;

    eeg_digital_top dut (
        .MCLK (MCLK), .RESET_N (RESET_N),
        .SCLK (SCLK), .CS_N (CS_N), .MOSI (MOSI), .MISO (MISO), .MISO_OE (MISO_OE),
        .DRDY_N (DRDY_N), .RAW_DATA (RAW_DATA), .RAW_CLK (RAW_CLK),
        .TH (TH), .SEL1 (SEL1), .SEL2 (SEL2), .CMP_STROBE (CMP_STROBE),
        .CHOP (CHOP), .CHOP_OUT (CHOP_OUT), .CHOP_BLANK (CHOP_BLANK),
        .AFE_RST (AFE_RST), .CHOP_EN (CHOP_EN),
        .TEST_CFG (TEST_CFG), .CPF_TRIM (CPF_TRIM), .AFE_IBIAS (AFE_IBIAS),
        .BTRIM_P (BTRIM_P), .BTRIM_N (BTRIM_N), .OFM (OFM), .OFS (OFS), .OFEN (OFEN)
    );

    always #(TMCLK / 2.0) MCLK = ~MCLK;

    `include "spi_bfm.svh"

    integer errors = 0;
    integer chop_checks = 0;
    integer blank_checks = 0;
    integer fc_pulses = 0;
    integer drdy_checks = 0;

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 20) $display("ERROR @%0t: %s", $time, msg);
    endtask

    function automatic logic [30:0] therm(input integer n);
        logic [30:0] v;
        v = '0;
        for (int i = 0; i < n; i++) v[i] = 1'b1;
        return v;
    endfunction

    // valid CIC output for a constant code c
    function automatic logic [23:0] dc_value(input integer c);
        integer v;
        v = (2 * c - 31) * 262144;
        return v[23:0];
    endfunction

    // DRDY_N must be low exactly while the FIFO holds data
    always @(negedge MCLK) begin
        if (dut.rst_n) begin
            drdy_checks = drdy_checks + 1;
            if (DRDY_N !== (dut.u_fifo.level == 4'd0)) err("DRDY_N does not match the FIFO level");
        end
    end

    always @(posedge MCLK) if (dut.filter_clear) fc_pulses = fc_pulses + 1;

    // last edge times of CHOP and CHOP_OUT
    real t_chop = 0.0;
    real t_chop_fall = 0.0;
    real t_chop_out = 0.0;
    real t_chop_out_fall = 0.0;
    always @(posedge CHOP) t_chop = $realtime;
    always @(negedge CHOP) t_chop_fall = $realtime;
    always @(posedge CHOP_OUT) t_chop_out = $realtime;
    always @(negedge CHOP_OUT) t_chop_out_fall = $realtime;

    // last CHOP_BLANK edges and number of pulses
    real    t_blank_rise = 0.0;
    real    t_blank_fall = 0.0;
    always @(posedge CHOP_BLANK) t_blank_rise = $realtime;
    always @(negedge CHOP_BLANK) t_blank_fall = $realtime;

    // equal within 1e-4 (the simulated MCLK half period is rounded to 1 ps)
    function automatic bit near(input real a, input real b);
        real tol;
        tol = 0.01 + 1.0e-4 * (b < 0.0 ? -b : b);
        return (a - b < tol) && (b - a < tol);
    endfunction

    // On the pins: CHOP high time = half MCLK, CHOP_OUT rises d MCLK after
    // CHOP and stays high for half MCLK. Valid for d + half + 3 < 3 * half.
    task automatic check_chop(input integer half, input integer d);
        real t0;
        @(posedge CHOP);
        t0 = $realtime;
        #((d + half + 3) * TMCLK);
        if (!near(t_chop_fall - t0, half * TMCLK))
            err($sformatf("CHOP high time %0.2f ns, expected %0d MCLK", t_chop_fall - t0, half));
        if (!near(t_chop_out - t0, d * TMCLK))
            err($sformatf("CHOP_OUT delay %0.2f ns, expected %0d MCLK", t_chop_out - t0, d));
        if (!near(t_chop_out_fall - t_chop_out, half * TMCLK))
            err($sformatf("CHOP_OUT high time %0.2f ns, expected %0d MCLK", t_chop_out_fall - t_chop_out, half));
        chop_checks = chop_checks + 1;
    endtask

    // On the pins: CHOP_BLANK rises one MCLK before a rising and before a
    // falling CHOP_OUT edge and falls len MCLK after it; no pulse for len = 0.
    // (CHOP_OUT edges are at least 128 MCLK apart, so edge times identify the pulse.)
    task automatic check_blank(input integer len);
        real t1;
        for (int e = 0; e < 2; e++) begin
            if (e == 0) @(posedge CHOP_OUT);
            else        @(negedge CHOP_OUT);
            t1 = $realtime;
            if (len != 0 && CHOP_BLANK !== 1'b1) err("CHOP_BLANK not high at the CHOP_OUT edge");
            #((len + 3) * TMCLK);
            if (len == 0) begin
                if (t_blank_rise > t1 - 1.5 * TMCLK || CHOP_BLANK !== 1'b0) err("CHOP_BLANK pulse with BLANK_LEN = 0");
            end else begin
                if (!near(t1 - t_blank_rise, TMCLK))
                    err($sformatf("CHOP_BLANK rose %0.3f ns before the CHOP_OUT edge, expected 1 MCLK", t1 - t_blank_rise));
                if (!near(t_blank_fall - t1, len * TMCLK))
                    err($sformatf("CHOP_BLANK fell %0.2f ns after the CHOP_OUT edge, expected %0d MCLK", t_blank_fall - t1, len));
            end
            blank_checks = blank_checks + 1;
        end
    endtask

    task automatic check_reg(input logic [7:0] addr, input logic [7:0] exp);
        logic [7:0] v;
        spi_read_reg(addr, v);
        if (v !== exp) err($sformatf("reg 0x%02h = 0x%02h, expected 0x%02h", addr, v, exp));
    endtask

    task automatic wait_drdy(input real timeout_us);
        real t0;
        t0 = $realtime;
        while (DRDY_N !== 1'b0 && ($realtime - t0) < timeout_us * 1000.0) #(1000.0);
        if (DRDY_N !== 1'b0) err($sformatf("DRDY_N did not go low within %0.0f us", timeout_us));
    endtask

    // full READ_SAMPLE with expected fields
    task automatic expect_sample(input logic [7:0] exp_status, input integer exp_seq,
                                 input logic [23:0] exp_data);
        logic [7:0]  st;
        logic [15:0] sq;
        logic [23:0] dt;
        bit          ok;
        spi_read_sample(st, sq, dt, ok);
        if (!ok) err("CRC mismatch");
        if (st !== exp_status) err($sformatf("STATUS 0x%02h expected 0x%02h", st, exp_status));
        if (exp_seq >= 0 && sq !== exp_seq[15:0]) err($sformatf("SEQ %0d expected %0d", sq, exp_seq));
        if (dt !== exp_data) err($sformatf("DATA 0x%06h expected 0x%06h", dt, exp_data));
    endtask

    logic [7:0]  st;
    logic [15:0] sq, sq_prev;
    logic [23:0] dt;
    bit          ok;
    logic [7:0]  v;
    real         t_clear, t_ready;
    integer      fc_before;

    initial begin
        TH = therm(22);
        #100.0;
        if (CHOP !== 1'b0 || CHOP_OUT !== 1'b0 || CHOP_BLANK !== 1'b0) err("chopper outputs not 0 during reset");
        #100.0;
        RESET_N = 1'b1;
        #2000.0;

        // ---------------- reset values and constant registers (2 MHz) ----------------
        if (DRDY_N !== 1'b1 || MISO_OE !== 1'b0 || AFE_RST !== 1'b1 || CHOP_EN !== 1'b1 ||
            TEST_CFG !== 8'h00 || RAW_CLK !== 1'b0 || RAW_DATA !== 1'b0 ||
            CPF_TRIM !== 4'd8 || AFE_IBIAS !== 2'd2 || BTRIM_P !== 2'd1 || BTRIM_N !== 2'd1 ||
            OFM !== 10'h000 || OFS !== 1'b0 || OFEN !== 4'b0000)
            err("pin values after reset");
        if (tb_crc8_update(tb_crc8_update(tb_crc8_update(tb_crc8_update(tb_crc8_update(tb_crc8_update(
            tb_crc8_update(tb_crc8_update(tb_crc8_update(8'h00, "1"), "2"), "3"), "4"), "5"), "6"), "7"), "8"), "9") !== 8'hF4)
            err("testbench CRC-8 check value");

        spi_half = 250.0;
        check_reg(8'h00, 8'hE6);
        check_reg(8'h01, 8'h05);
        check_reg(8'h02, 8'h74);
        check_reg(8'h03, 8'h02);          // SETTLING after reset
        check_reg(8'h04, 8'h05);
        check_reg(8'h05, 8'h00);
        check_reg(8'h06, 8'h03);
        check_reg(8'h07, 8'hE8);
        check_reg(8'h08, 8'h00);
        check_reg(8'h09, 8'h00);
        check_reg(8'h0A, 8'h28);
        check_reg(8'h0B, 8'h07);
        check_reg(8'h0C, 8'h05);
        check_reg(8'h0D, 8'h00);
        check_reg(8'h0E, 8'h00);
        check_reg(8'h0F, 8'h00);
        check_reg(8'h7F, 8'h00);
        check_reg(8'hFF, 8'h00);

        // empty FIFO: VALID = 0, SETTLING = 1, DATA = 0
        expect_sample(8'h20, 0, 24'h000000);
        check_reg(8'h05, 8'h00);

        // ---------------- register writes ----------------
        fc_before = fc_pulses;
        spi_write_reg(8'h02, 8'h08);      // RAW_EN only
        check_reg(8'h02, 8'h08);
        if (AFE_RST !== 1'b0 || CHOP_EN !== 1'b0) err("AFE_RST/CHOP_EN pins after CONTROL = 0x08");
        if (fc_pulses != fc_before) err("unexpected FILTER_CLEAR pulse");
        spi_write_reg(8'h02, 8'h76);      // CHOP_FAST | FILTER_CLEAR | DWA_EN | AFE_RST | CHOP_EN
        check_reg(8'h02, 8'h74);          // FILTER_CLEAR reads back 0
        if (fc_pulses != fc_before + 1) err("FILTER_CLEAR did not produce exactly one pulse");
        if (AFE_RST !== 1'b1 || CHOP_EN !== 1'b1) err("AFE_RST/CHOP_EN pins after CONTROL = 0x76");
        spi_write_reg(8'h02, 8'hF4);      // bit 7 is not implemented
        check_reg(8'h02, 8'h74);

        // ANA_TRIM: [3:0] CPF_TRIM, [5:4] AFE_IBIAS, [7:6] read 0
        spi_write_reg(8'h0A, 8'hFF);
        check_reg(8'h0A, 8'h3F);
        if (CPF_TRIM !== 4'hF || AFE_IBIAS !== 2'd3) err("ANA_TRIM pins after 0xFF");
        spi_write_reg(8'h0A, 8'h15);
        check_reg(8'h0A, 8'h15);
        if (CPF_TRIM !== 4'h5 || AFE_IBIAS !== 2'd1) err("ANA_TRIM pins after 0x15");
        spi_write_reg(8'h0A, 8'hC0);
        check_reg(8'h0A, 8'h00);
        if (CPF_TRIM !== 4'h0 || AFE_IBIAS !== 2'd0) err("ANA_TRIM pins after 0xC0");
        spi_write_reg(8'h0A, 8'h28);
        check_reg(8'h0A, 8'h28);
        if (CPF_TRIM !== 4'd8 || AFE_IBIAS !== 2'd2) err("ANA_TRIM pins after 0x28");

        // BLANK: [3:0] BLANK_LEN, [7:4] read 0
        spi_write_reg(8'h0B, 8'hFF);
        check_reg(8'h0B, 8'h0F);
        spi_write_reg(8'h0B, 8'hA5);
        check_reg(8'h0B, 8'h05);
        spi_write_reg(8'h0B, 8'h00);
        check_reg(8'h0B, 8'h00);
        spi_write_reg(8'h0B, 8'h07);
        check_reg(8'h0B, 8'h07);

        // BOOST_TRIM: [1:0] BTRIM_P, [3:2] BTRIM_N, [7:4] read 0
        spi_write_reg(8'h0C, 8'hFF);
        check_reg(8'h0C, 8'h0F);
        if (BTRIM_P !== 2'd3 || BTRIM_N !== 2'd3) err("BOOST_TRIM pins after 0xFF");
        spi_write_reg(8'h0C, 8'hA6);
        check_reg(8'h0C, 8'h06);
        if (BTRIM_P !== 2'd2 || BTRIM_N !== 2'd1) err("BOOST_TRIM pins after 0xA6");
        spi_write_reg(8'h0C, 8'h08);
        check_reg(8'h0C, 8'h08);
        if (BTRIM_P !== 2'd0 || BTRIM_N !== 2'd2) err("BOOST_TRIM pins after 0x08");
        spi_write_reg(8'h0C, 8'h05);
        check_reg(8'h0C, 8'h05);
        if (BTRIM_P !== 2'd1 || BTRIM_N !== 2'd1) err("BOOST_TRIM pins after 0x05");

        // OFF_CODE_L / OFF_CTRL: M[7:0], M[9:8], SIGN[3] and OFF_RANGE[6:4]; OFEN is the
        // thermometer of OFF_RANGE (5..7 act as 4); bits 2 and 7 read 0
        spi_write_reg(8'h0D, 8'hA5);
        check_reg(8'h0D, 8'hA5);
        if (OFM !== 10'h0A5 || OFS !== 1'b0) err("OFM/OFS pins after OFF_CODE_L = 0xA5");
        spi_write_reg(8'h0E, 8'hFF);
        check_reg(8'h0E, 8'h7B);
        if (OFM !== 10'h3A5 || OFS !== 1'b1 || OFEN !== 4'b1111) err("OFM/OFS/OFEN pins after OFF_CTRL = 0xFF");
        spi_write_reg(8'h0E, 8'h21);
        check_reg(8'h0E, 8'h21);
        if (OFM !== 10'h1A5 || OFS !== 1'b0 || OFEN !== 4'b0011) err("OFM/OFS/OFEN pins after OFF_CTRL = 0x21");
        spi_write_reg(8'h0E, 8'h18);
        if (OFEN !== 4'b0001 || OFS !== 1'b1) err("OFEN/OFS pins for range 1, sign 1");
        spi_write_reg(8'h0E, 8'h30);
        if (OFEN !== 4'b0111) err("OFEN pins for range 3");
        spi_write_reg(8'h0E, 8'h40);
        if (OFEN !== 4'b1111 || OFM[9:8] !== 2'b00) err("OFM/OFEN pins for range 4");
        spi_write_reg(8'h0E, 8'h00);
        spi_write_reg(8'h0D, 8'h00);
        check_reg(8'h0E, 8'h00);
        check_reg(8'h0D, 8'h00);
        if (OFM !== 10'h000 || OFS !== 1'b0 || OFEN !== 4'b0000) err("OFM/OFS/OFEN pins after restoring the reset values");

        spi_write_reg(8'h09, 8'hA5);
        check_reg(8'h09, 8'hA5);
        if (TEST_CFG !== 8'hA5) err("TEST_CFG pins");
        spi_write_reg(8'h09, 8'h3C);
        check_reg(8'h09, 8'h3C);
        if (TEST_CFG !== 8'h3C) err("TEST_CFG pins");

        // CHOP / CHOP_OUT on the pins: 128 kHz after reset, 64 kHz with
        // CHOP_FAST = 0 (a rate change takes effect within one 512-MCLK superperiod)
        // CHOP_BLANK follows CHOP_OUT (BLANK_LEN 7 after reset, 15, 1, 0)
        check_chop(128, 0);
        check_blank(7);
        spi_write_reg(8'h08, 8'h5A);
        check_reg(8'h08, 8'h5A);
        check_chop(128, 90);
        spi_write_reg(8'h0B, 8'h0F);
        check_blank(15);
        spi_write_reg(8'h08, 8'hC8);      // 200 MCLK, longer than the 128 kHz half period
        check_chop(128, 200);
        spi_write_reg(8'h02, 8'h34);      // CHOP_FAST = 0
        check_reg(8'h02, 8'h34);
        #(600.0 * TMCLK);
        check_chop(256, 200);
        check_blank(15);
        spi_write_reg(8'h0B, 8'h01);
        check_blank(1);
        spi_write_reg(8'h08, 8'h5A);
        check_chop(256, 90);
        spi_write_reg(8'h0B, 8'h00);      // blanking off
        check_blank(0);
        spi_write_reg(8'h08, 8'h00);
        check_chop(256, 0);
        spi_write_reg(8'h02, 8'h74);      // back to CHOP_FAST = 1
        #(600.0 * TMCLK);
        check_chop(128, 0);
        check_blank(0);
        spi_write_reg(8'h0B, 8'h07);      // back to the default
        check_blank(7);
        @(posedge CHOP);
        #(2.0 * TMCLK);
        if (t_chop_out != t_chop) err("CHOP_OUT not aligned with CHOP for CHOP_DLY = 0");

        // read-only registers ignore writes
        spi_write_reg(8'h00, 8'h12);
        spi_write_reg(8'h01, 8'h55);
        spi_write_reg(8'h05, 8'h07);
        spi_write_reg(8'h07, 8'h00);
        check_reg(8'h00, 8'hE6);
        check_reg(8'h01, 8'h05);
        check_reg(8'h05, 8'h00);
        check_reg(8'h07, 8'hE8);

        // incomplete or over-long WRITE_REG frames are ignored
        spi_tx[0] = 8'h20; spi_tx[1] = 8'h09; spi_tx[2] = 8'h77; spi_tx[3] = 8'h00;
        spi_xfer(2, 0);
        spi_xfer(2, 7);
        spi_xfer(3, 1);
        spi_xfer(4, 0);
        check_reg(8'h09, 8'h3C);

        // unknown commands set CMD_ERR (W1C); a partial command byte does not
        spi_tx[0] = 8'h55; spi_tx[1] = 8'h00; spi_tx[2] = 8'h00;
        spi_xfer(3, 0);
        for (int i = 0; i < 3; i++) if (spi_rx[i] !== 8'h00) err("MISO not zero for an unknown command");
        check_reg(8'h03, 8'h0A);          // CMD_ERR | SETTLING
        spi_write_reg(8'h03, 8'h00);      // writing 0 does not clear
        check_reg(8'h03, 8'h0A);
        spi_write_reg(8'h03, 8'h04);      // OVERRUN bit only
        check_reg(8'h03, 8'h0A);
        spi_write_reg(8'h03, 8'h08);      // W1C CMD_ERR
        check_reg(8'h03, 8'h02);
        spi_tx[0] = 8'h00;
        spi_xfer(1, 0);                   // 0x00 is not a command either
        check_reg(8'h03, 8'h0A);
        spi_write_reg(8'h03, 8'h08);
        spi_tx[0] = 8'h55;
        spi_xfer(0, 4);                   // only 4 clocks: no command byte
        check_reg(8'h03, 8'h02);

        // ---------------- samples ----------------
        spi_write_reg(8'h02, 8'h77);      // RUN | FILTER_CLEAR | DWA_EN | AFE_RST | CHOP_EN | CHOP_FAST
        t_clear = $realtime;
        check_reg(8'h03, 8'h02);          // settling again after the clear
        wait_drdy(5000.0);
        t_ready = $realtime;
        // 3 output periods after the clear (+ the frame alignment and pipeline)
        if (t_ready - t_clear < 2990000.0 || t_ready - t_clear > 3060000.0)
            err($sformatf("first valid sample %0.1f us after FILTER_CLEAR", (t_ready - t_clear) / 1000.0));
        check_reg(8'h03, 8'h01);          // FIFO_NONEMPTY, not settling
        check_reg(8'h05, 8'h01);
        expect_sample(8'h80, 0, dc_value(22));
        if (DRDY_N !== 1'b1) err("DRDY_N must be high after the FIFO was emptied");
        expect_sample(8'h00, 0, 24'h000000);    // empty, not settling, no overrun

        // partial / over-long frames do not consume the entry
        wait_drdy(1100.0);
        spi_read_sample_n(5, 0, st, sq, dt, ok);
        if (st !== 8'h80 || sq !== 16'd1) err("partial frame contents");
        spi_read_sample_n(7, 0, st, sq, dt, ok);
        spi_read_sample_n(8, 3, st, sq, dt, ok);
        if (!ok || sq !== 16'd1) err("frame with extra clocks: contents");
        spi_read_sample_n(9, 0, st, sq, dt, ok);
        if (!ok || sq !== 16'd1) err("9-byte frame: contents");
        check_reg(8'h05, 8'h01);
        if (DRDY_N !== 1'b0) err("DRDY_N went high without a complete read");
        expect_sample(8'h80, 1, dc_value(22));
        check_reg(8'h05, 8'h00);

        // overrun: no reads for 11.5 ms -> 8 stored, the rest dropped
        #11500000.0;
        check_reg(8'h05, 8'h08);
        check_reg(8'h03, 8'h05);          // OVERRUN | FIFO_NONEMPTY
        for (int i = 0; i < 8; i++) expect_sample(8'h80, 2 + i, dc_value(22));
        // next frame: either empty (OVERRUN visible) or the first sample after the drop
        spi_read_sample(st, sq, dt, ok);
        if (st[7] == 1'b0) begin
            if (st !== 8'h40 || !ok || dt !== 24'h0) err("empty frame after overrun");
            wait_drdy(1100.0);
            spi_read_sample(st, sq, dt, ok);
        end
        if (st !== 8'hC0 || !ok || dt !== dc_value(22)) err($sformatf("first sample after overrun: status 0x%02h", st));
        if (sq <= 16'd10) err($sformatf("SEQ %0d after overrun shows no gap", sq));
        $display("INFO: first SEQ after the overrun = %0d (samples 10..%0d dropped)", sq, sq - 1);
        sq_prev = sq;
        spi_write_reg(8'h03, 8'h04);      // W1C OVERRUN
        check_reg(8'h03, 8'h00);
        wait_drdy(1100.0);
        expect_sample(8'h80, sq_prev + 1, dc_value(22));

        // RUN = 0: nothing stored, SEQ keeps counting valid outputs
        spi_write_reg(8'h02, 8'h74);
        #3500000.0;
        if (DRDY_N !== 1'b1) err("samples stored while RUN = 0");
        check_reg(8'h05, 8'h00);
        spi_write_reg(8'h02, 8'h75);
        wait_drdy(1100.0);
        spi_read_sample(st, sq, dt, ok);
        if (st !== 8'h80 || !ok || dt !== dc_value(22)) err("sample after RUN = 0 -> 1");
        if (sq < sq_prev + 4) err($sformatf("SEQ %0d after RUN = 0 phase (previous %0d)", sq, sq_prev + 1));
        sq_prev = sq;

        // ---------------- 1 MHz ----------------
        spi_half = 500.0;
        check_reg(8'h00, 8'hE6);
        check_reg(8'h02, 8'h75);
        spi_write_reg(8'h09, 8'h96);
        check_reg(8'h09, 8'h96);
        for (int i = 0; i < 3; i++) begin
            wait_drdy(1100.0);
            expect_sample(8'h80, sq_prev + 1 + i, dc_value(22));
        end

        // negative full-window value after a new FILTER_CLEAR: c = 5 -> x = -21
        spi_write_reg(8'h02, 8'h74);      // RUN = 0
        while (DRDY_N === 1'b0) spi_read_sample(st, sq, dt, ok);
        TH = therm(5);
        #20000.0;
        spi_write_reg(8'h02, 8'h77);      // RUN | FILTER_CLEAR
        wait_drdy(3200.0);
        expect_sample(8'h80, 0, dc_value(5));
        wait_drdy(1100.0);
        spi_half = 250.0;
        expect_sample(8'h80, 1, dc_value(5));

        #5000.0;
        if (errors == 0 && spi_errors == 0)
            $display("PASS: tb_spi (%0d SPI transfers at 2 and 1 MHz, %0d READ_SAMPLE frames, %0d DRDY_N checks, %0d CHOP/CHOP_OUT and %0d CHOP_BLANK pin checks at 128 and 64 kHz, max MISO latency %0.1f ns, max MISO_OE latency %0.1f ns)",
                     spi_xfers, spi_sample_frames, drdy_checks, chop_checks, blank_checks, spi_miso_lat_max, spi_oe_lat_max);
        else
            $display("FAIL: tb_spi (%0d errors, %0d SPI monitor errors)", errors, spi_errors);
        $finish;
    end

    // watchdog
    initial begin
        #60000000.0;
        $display("FAIL: tb_spi (timeout)");
        $finish;
    end

endmodule
