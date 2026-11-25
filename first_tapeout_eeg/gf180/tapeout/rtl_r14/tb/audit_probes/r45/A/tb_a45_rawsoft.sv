// audit 45 A probe: RAW_EN 1 (DBG_SEL 0), a SOFT_RESET committed in each frame cycle 0..31 (dut.soft_req forced for one
// MCLK, as tb_top_r14's soft_now): RAW_CLK rises after the commit cycle, and whether a new word starts after it
// (eeg_digital_top's header: "a SOFT_RESET stops the raw stream at the end of the word in progress", RST-02)
`timescale 1ns / 1ps
`default_nettype none
module tb_a45_rawsoft;
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
    integer ncyc = 0, nrise = 0, last_rise = 0;
    always @(posedge MCLK) ncyc = ncyc + 1;
    always @(posedge RAW_CLK) begin nrise = nrise + 1; last_rise = ncyc; end
    integer k, r0, c0, words, extra_words = 0;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(40.0 * TMCLK);
        for (k = 0; k < 32; k = k + 1) begin
            r14_write(7'h11, 8'h3C); r14_write(7'h62, 8'h01); r14_write(7'h11, 8'h00);
            repeat (3 * 32) @(posedge MCLK);
            @(posedge MCLK); #1;
            while (dut.cycle !== k[4:0]) begin @(posedge MCLK); #1; end
            r0 = nrise; c0 = ncyc;                       // now inside cycle k (the commit cycle)
            force dut.soft_req = 1'b1;
            @(posedge MCLK); #1;
            release dut.soft_req;
            repeat (4 * 32) @(posedge MCLK);
            // RAW_CLK rises at e3, e7, .. e31 of each word: the rises after the commit cycle's start, and the frames
            words = (nrise - r0 + 7) / 8;
            $display("commit in cycle %2d: %0d RAW_CLK rises after it, the last %0d MCLK after the commit cycle's start, RAW_EN %b",
                     k, nrise - r0, last_rise - c0, dut.raw_en);
            if (last_rise - c0 > 32 - k) extra_words = extra_words + 1;
            r14_write(7'h06, 8'hFF);
        end
        $display("commit cycles whose stream ran past the end of the word in progress: %0d of 32", extra_words);
        $finish;
    end
endmodule
`default_nettype wire
