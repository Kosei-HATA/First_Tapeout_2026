`timescale 1ns / 1ps
`default_nettype none
// probe: a flag in ERR, then a write to another register whose data byte has that flag's bit set; ERR read back
module tb_probe_w1c;
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
    logic [7:0] e;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        r14_read(7'h06, e);  $display("after RESET_N: ERR 0x%02h", e);
        r14_write(7'h24, 8'h09);                         // CPF_TRIM 9 (bit 0 set)
        r14_read(7'h06, e);  $display("after writing CPF_TRIM 0x09: ERR 0x%02h (RESET_FLAG %b)", e, e[0]);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h7F, 8'h00);                         // undefined: ADDR_ERR
        r14_read(7'h06, e);  $display("after a write to 0x7F: ERR 0x%02h", e);
        r14_write(7'h08, 8'hFF);                         // ALERT_MASK 0xFF (its reset value)
        r14_read(7'h06, e);  $display("after writing ALERT_MASK 0xFF: ERR 0x%02h (ADDR_ERR %b)", e, e[3]);
        $finish;
    end
endmodule
`default_nettype wire
