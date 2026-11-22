// tb_a28_lock_top - audit round 28 (A): the whole block. RUN with range 1, M 40; an evaluation writes TEST_MUX (ATP_EN,
// ATP_SEL 12 = AFE OUTP) and TEST_CTRL (CHOP_STOP) with the key open, applies nothing and locks. The host's tracking
// step (M 41, APPLY_NR) is refused with CFG_ERR; following step 4's remedy ("APPLY_NR の代わりに APPLY を使う") the
// APPLY is accepted and confirmed by the active copies, and RUN continues with CHOP_EN 0 and the ATP pad on OUTP.
`timescale 1ns / 1ps
`default_nettype none

module tb_a28_lock_top;
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

    logic [7:0] e, ml, tm, tc;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;                       // CRC on (step 3)
        r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);                  // range 1, M 40
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_cmd(8'h11);                                                     // START
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        $display("RUN: CHOP_EN %b TEST_CFG 0x%02h OFM %0d", CHOP_EN, TEST_CFG, OFM);
        // an evaluation leaves test shadows written but not applied, then locks
        r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h1C); r14_write(7'h61, 8'h02); r14_write(7'h11, 8'h00);
        r14_write(7'h60, 8'h00);                                            // too late: refused while locked
        r14_read(7'h06, e);
        $display("after the lock: ERR 0x%02h (ADDR_ERR from the refused write-back)", e);
        r14_write(7'h06, e);
        // step 7's one-step tracking: M 41 with APPLY_NR
        r14_write(7'h21, 8'd41);
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_cmd(8'h44);
        #(40000.0);
        r14_read(7'h06, e);
        $display("APPLY_NR: ERR 0x%02h (CFG_ERR 0x20), state %0d, OFM %0d", e, dut.u_seq.state, OFM);
        r14_write(7'h06, e);
        // step 4's remedy: APPLY instead of APPLY_NR
        r14_cmd(8'h33);
        #(40000.0);
        r14_read(7'h06, e);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        r14_read(7'h31, ml); r14_read(7'h70, tm); r14_read(7'h71, tc);
        $display("APPLY: ERR 0x%02h; active OFF_M_L %0d, TEST_MUX 0x%02h, TEST_CTRL 0x%02h (= the shadows: confirmed)", e, ml, tm, tc);
        $display("RUN again: CHOP_EN %b, TEST_CFG 0x%02h (ATP_EN %b, ATP_SEL %0d), OFM %0d", CHOP_EN, TEST_CFG,
                 TEST_CFG[4], TEST_CFG[3:0], OFM);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
