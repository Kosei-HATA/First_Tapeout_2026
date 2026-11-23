// Audit 36, auditor C: the read header's ADDR_ERR (table 5.2-2: HDR / BYTE, rw and not addr_ok -> ADDR_ERR) seen later
// in the same CRC-off burst: a read from the undefined 0x7F through STATUS (0x03) and ERR (0x06).
`timescale 1ns / 1ps
`default_nettype none
module tb_c36_aerr;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN, CMP_STROBE, DAC_CLK;
    wire  CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, CHOP1, OFS;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    logic [4:0] CODE = 5'd15;
    localparam real TMCLK = 1000.0 / 32.768;
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    eeg_digital_top dut (.*);
    `include "eeg_regs_defs.svh"
    `include "spi_bfm_r14.svh"
    logic [7:0] e;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(2000.0);
        r14_write(7'h06, 8'hFF);                         // RESET_FLAG cleared: ERR 0, ALERT 0
        for (int i = 0; i < 9; i++) spi_tx[i] = 8'h00;
        spi_tx[0] = 8'hFF;                               // read from 0x7F (undefined), then 0x00 .. 0x06
        spi_xfer(9, 0);
        r14_read(7'h06, e);
        $display("burst 0x7F..0x06: STATUS byte (0x03) 0x%02h ALERT %b, ERR byte (0x06) 0x%02h ADDR_ERR %b; ERR read after the frame 0x%02h -> %s",
                 spi_rx[5], spi_rx[5][5], spi_rx[8], spi_rx[8][3], e,
                 (spi_rx[8][3] === 1'b1) ? "flagged at the header" : "flagged after the frame only");
        $finish;
    end
endmodule
`default_nettype wire
