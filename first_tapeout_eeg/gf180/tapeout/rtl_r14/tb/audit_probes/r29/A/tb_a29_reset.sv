// tb_a29_reset - audit round 29 (A). P1: after RESET_N and after SOFT_RESET, when do the chopper's half period,
// CHOP1's half period and CHOP_BLANK's width return to the reset values (SEQ-13: "at their boundaries")?
// P2: DRDY_N level mode: the chopper phase of DRDY_N's rising edges for a host that reads a fixed latency after the
// fall, and the rise caused by a FLUSH (the requirements' 4.10 DRDY_N row: "the edges lie in one chopper phase").
`timescale 1ns / 1ps
`default_nettype none
module tb_a29_reset;
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
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"

    // edge logs (MCLK counts)
    integer ncyc = 0;
    always @(posedge MCLK) ncyc = ncyc + 1;
    integer t_chop[$], t_c1[$], w_blank[$], t_blank[$];
    logic chop_q = 0, c1_q = 1, bl_q = 0; integer bl_start = 0;
    always @(posedge MCLK) begin
        #1;
        if (CHOP !== chop_q) t_chop.push_back(ncyc);
        if (CHOP1 !== c1_q) t_c1.push_back(ncyc);
        if (CHOP_BLANK === 1'b1 && bl_q !== 1'b1) bl_start = ncyc;
        if (CHOP_BLANK === 1'b0 && bl_q === 1'b1) begin w_blank.push_back(ncyc - bl_start); t_blank.push_back(ncyc); end
        chop_q = CHOP; c1_q = CHOP1; bl_q = CHOP_BLANK;
    end
    task automatic report(input string tag, input integer t0);
        integer i, k;
        string s;
        s = "";
        k = 0;
        for (i = 1; i < t_chop.size() && k < 6; i++) if (t_chop[i] > t0) begin s = {s, $sformatf(" %0d", t_chop[i] - t_chop[i-1])}; k++; end
        $display("%s CHOP half periods after it (MCLK):%s", tag, s);
        s = ""; k = 0;
        for (i = 1; i < t_c1.size() && k < 4; i++) if (t_c1[i] > t0) begin s = {s, $sformatf(" %0d", t_c1[i] - t_c1[i-1])}; k++; end
        $display("%s CHOP1 half periods after it (MCLK):%s", tag, s);
        s = ""; k = 0;
        for (i = 0; i < w_blank.size() && k < 4; i++) if (t_blank[i] > t0) begin s = {s, $sformatf(" %0d", w_blank[i])}; k++; end
        $display("%s CHOP_BLANK widths after it (MCLK):%s", tag, s);
    endtask

    // P2: DRDY_N rising-edge phase (CHOP in the MCLK before the edge)
    logic chop_p = 0, drdy_p = 1; integer rise_a = 0, rise_b = 0, fall_a = 0, fall_b = 0; bit arm2 = 0;
    always @(posedge MCLK) begin
        #1;
        if (arm2 && DRDY_N !== drdy_p) begin
            if (DRDY_N === 1'b1) begin if (chop_p) rise_a++; else rise_b++; end
            else                 begin if (chop_p) fall_a++; else fall_b++; end
        end
        drdy_p = DRDY_N; chop_p = CHOP;
    end

    integer lat_list[4] = '{1000, 3000, 5000, 7000};
    logic [7:0] v, s8; logic [15:0] q; logic [23:0] d; bit ok; integer t0, i, lat;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        // non-default timing settings: 64 kHz, CHOP1 rate 5 (16 kHz), BLANK 3, applied by START
        r14_write(7'h26, 8'h00);
        r14_write(7'h27, 8'h15);                   // DWA_EN 1, CHOP1_RATE 5
        r14_write(7'h28, 8'h03);
        r14_cmd(CMD_START);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        #(300000.0);
        // P1a: RESET_N at a point that is not a 512-MCLK or 1024-frame boundary
        while (dut.u_clkgen.cnt !== 9'h0A3) @(posedge MCLK);
        #(3.0);
        t0 = ncyc;
        RESET_N = 1'b0; #(5.0 * TMCLK); RESET_N = 1'b1;
        #(70000.0);
        report("P1a RESET_N:", t0);
        // back to the non-default settings
        r14_write(7'h26, 8'h00); r14_write(7'h27, 8'h15); r14_write(7'h28, 8'h03);
        r14_cmd(CMD_START);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        #(300000.0);
        // P1b: SOFT_RESET at a similar point
        while (dut.u_clkgen.cnt !== 9'h0A3) @(posedge MCLK);
        t0 = ncyc;
        r14_cmd(CMD_SOFT_RESET);
        #(1000.0);
        #(70000.0);
        report("P1b SOFT_RESET:", t0);
        // P2: level mode (reset value), 128 kHz: host reads with a fixed latency after each DRDY_N fall
        r14_cmd(CMD_START);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        foreach (lat_list[j]) begin
            lat = lat_list[j];
            rise_a = 0; rise_b = 0; fall_a = 0; fall_b = 0; arm2 = 1;
            for (i = 0; i < 20; i++) begin
                @(negedge DRDY_N); #(lat * 1.0);
                r14_sample(s8, q, d, ok);
            end
            arm2 = 0;
            $display("P2 level mode, read %0d ns after the fall: DRDY_N falls A %0d B %0d, rises A %0d B %0d",
                     lat, fall_a, fall_b, rise_a, rise_b);
        end
        // P2b: a FLUSH with a sample in the FIFO: the rise at the tick
        rise_a = 0; rise_b = 0; fall_a = 0; fall_b = 0; arm2 = 1;
        for (i = 0; i < 5; i++) begin
            @(negedge DRDY_N); #(2000.0);
            r14_cmd(CMD_FLUSH);
            @(posedge DRDY_N);
            $display("P2b FLUSH: DRDY_N rose at frame cycle %0d of frame %0d (mod 16), tick at cycle 24", dut.cycle,
                     dut.u_clkgen.cnt[8:5]);
        end
        arm2 = 0;
        $display("P2b: rises A %0d B %0d", rise_a, rise_b);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
