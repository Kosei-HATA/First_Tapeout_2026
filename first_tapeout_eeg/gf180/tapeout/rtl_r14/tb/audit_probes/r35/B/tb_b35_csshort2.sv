// audit 35 B, probe P2: how short a CS_N High inside a frame still splits it (requirements SPI-11 forbids a High of
// 2 MCLK or more). CRC on, 3-byte read of STATE [0x84, 0, 0], one High of width w (0.25..2.0 MCLK, at 8 phases of MCLK)
// in the low phase before host pulse 5; count the chip's frame starts and FRAME_ERRs.
`timescale 1ps / 1ps
`default_nettype none
module tb_b35_csshort;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK * 500.0) MCLK = ~MCLK;          // ps timescale: half period in ps
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    integer nstart = 0, nferr = 0;
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start) nstart++;
        if (dut.frame_err) nferr++;
    end
    task automatic bitx(input logic b);
        SCLK = 1'b1; #(500000); SCLK = 1'b0; MOSI = b; #(500000);
    endtask
    task automatic frame(input logic [23:0] tx, input real w_mclk, input real ph_mclk);
        CS_N = 1'b0; MOSI = tx[23]; #(1000000);
        for (int n = 0; n < 24; n++) begin
            SCLK = 1'b1; #(500000); SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 == 4) begin                    // before pulse 5: align to MCLK, then the glitch
                #(120000); @(posedge MCLK); #(ph_mclk * TMCLK * 1000.0);
                CS_N = 1'b1; #(w_mclk * TMCLK * 1000.0); CS_N = 1'b0;
                #(250000);
            end else if (n + 1 < 24) #(500000);
        end
        #(300000); CS_N = 1'b1; #(1000000);
    endtask
    initial begin
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        for (int wi = 1; wi <= 8; wi++) begin
            real w; integer splits;
            w = 0.25 * wi; splits = 0;
            for (int p = 0; p < 8; p++) begin
                integer s0;
                s0 = nstart;
                frame({8'h84, 8'h00, 8'h00}, w, 0.125 * p);
                repeat (10) @(posedge MCLK);
                if (nstart - s0 > 1) splits++;
            end
            $display("CS_N High of %0.2f MCLK inside the frame: split at %0d of 8 MCLK phases", w, splits);
        end
        $display("FRAME_ERRs in all: %0d", nferr);
        $finish;
    end
endmodule
`default_nettype wire
