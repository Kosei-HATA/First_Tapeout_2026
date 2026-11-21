// tb_a25_m1024 - audit round 25 (A): the host procedure's one-step tracking at range 4's top (|M| = 1023), which
// step 7 does not cover (round 24's rule names ranges 1..3 only). RUN with range 4, M 1023; the host's next step
// M 1024 written as M_H = M >> 8 = 4, M_L = 0 (CRC on): what the chip does with the write, the read-back of step 3,
// and the APPLY_NR.
`timescale 1ns / 1ps
`default_nettype none

module tb_a25_m1024;
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

    logic [7:0] v, mh, ml, e;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h22, 8'h04); r14_write(7'h20, 8'h03); r14_write(7'h21, 8'hFF);   // range 4, M 1023
        r14_cmd(8'h11);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        r14_read(7'h06, e); r14_write(7'h06, e);
        $display("RUN, range 4, M 1023: OFM %0d OFEN %b", OFM, OFEN);
        // the next outward step, M = 1024 = {M_H 4, M_L 0}
        r14_write(7'h20, 8'h04); r14_write(7'h21, 8'h00);
        r14_read(7'h06, e);
        r14_read(7'h20, mh); r14_read(7'h21, ml);
        $display("wrote M_H 0x04, M_L 0x00: ERR 0x%02h, read back M_H 0x%02h M_L 0x%02h (shadow M = %0d)",
                 e, mh, ml, {mh[1:0], ml});
        r14_write(7'h06, e);
        #(20000.0);
        r14_cmd(8'h44);
        #(40000.0);
        r14_read(7'h06, e);
        r14_read(7'h30, mh); r14_read(7'h31, ml);
        $display("APPLY_NR: ERR 0x%02h, active M %0d, OFM %0d, state %0d", e, {mh[1:0], ml}, OFM, dut.u_seq.state);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule

`default_nettype wire
