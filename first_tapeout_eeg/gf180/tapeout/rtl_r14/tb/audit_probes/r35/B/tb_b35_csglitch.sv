// audit 35 B, probe P1: a CS_N glitch (3 MCLK High in the low phase before host pulse k) during a 3-byte CRC read of
// STATE [0x84, 0, 0]: does the chip end the first part "as a header-only read (no flag)" (requirements SPI-11)?
`timescale 1ns / 1ps
`default_nettype none
module tb_b35_csglitch;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    integer nfr = 0, nferr = 0, nferr1 = 0, nfr_at_glitch = 0, naerr = 0;
    always @(posedge MCLK) begin
        if (dut.u_spi.cs_start) nfr++;
        if (dut.frame_err) begin nferr++; if (nfr == nfr_at_glitch) nferr1++; end
        if (dut.addr_err) naerr++;
    end
    task automatic xfer_break(input logic [23:0] tx, input integer k);
        CS_N = 1'b0; MOSI = tx[23]; #(spi_tcss);
        for (int n = 0; n < 24; n++) begin
            SCLK = 1'b1; #(spi_high); SCLK = 1'b0;
            MOSI = (n + 1 < 24) ? tx[22 - n] : 1'b0;
            if (n + 1 == k - 1) begin                // the glitch in the low phase before pulse k
                #40.0; nfr_at_glitch = nfr; CS_N = 1'b1; #(3.0 * TMCLK); CS_N = 1'b0; #(spi_low - 40.0 - 3.0 * TMCLK);
            end else if (n + 1 < 24) #(spi_low);
        end
        #(spi_tcsh); CS_N = 1'b1; #(spi_tidle);
    endtask
    logic [7:0] v;
    initial begin
        spi_high = 500.0; spi_low = 500.0;
        repeat (5) @(negedge MCLK); RESET_N = 1'b1; repeat (40) @(negedge MCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_read(7'h06, v); r14_write(7'h06, v);
        for (int k = 2; k <= 24; k++) begin
            integer f0, a0;
            f0 = nferr; a0 = naerr;
            xfer_break({8'h84, 8'h00, 8'h00}, k);
            repeat (20) @(posedge MCLK);
            $display("cut before pulse %2d (first part %2d bits): FRAME_ERR from the first part %0d, from both parts %0d, ADDR_ERR %0d",
                     k, k - 1, nferr1, nferr - f0, naerr - a0);
            nferr1 = 0;
            r14_read(7'h06, v); if (v != 0) r14_write(7'h06, v);
        end
        $finish;
    end
endmodule
`default_nettype wire
