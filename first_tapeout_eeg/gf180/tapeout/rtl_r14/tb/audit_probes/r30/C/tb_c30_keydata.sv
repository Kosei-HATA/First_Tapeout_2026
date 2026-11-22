// tb_c30_keydata - audit round 30 (C): the key's value 0x3C written as data to each writable register outside the
// lock (key locked), then a write of TEST_MUX: REG-08 expects it refused with exactly ADDR_ERR (only a write of the key
// to TEST_KEY unlocks). Counts the registers after whose 0x3C write the lock was found open.
`timescale 1ns / 1ps
`default_nettype none
module tb_c30_keydata;
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
    logic [6:0] A [0:5];
    logic [7:0] e, v;
    integer nopen;
    initial begin
        A = '{7'h08, 7'h21, 7'h24, 7'h50, 7'h51, 7'h53};   // ALERT_MASK, OFF_M_L, CPF_TRIM, T_WARM, T_ELEC, T_PRE (0x3C legal)
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h06, 8'hFF);
        nopen = 0;
        for (int i = 0; i < 6; i++) begin
            r14_write(7'h11, 8'h00);                                     // locked
            r14_write(A[i], 8'h3C);                                      // the key's value as data
            r14_read(7'h06, e);
            r14_write(7'h60, 8'h15);                                     // TEST_MUX: must be refused (ADDR_ERR)
            r14_read(7'h06, e); r14_read(7'h60, v);
            if (e !== 8'h08 || v !== 8'h00) begin
                nopen++;
                $display("0x3C written to 0x%02h with the key locked: then TEST_MUX <- 0x15 gives ERR 0x%02h, TEST_MUX reads 0x%02h (REG-08: exactly ADDR_ERR, 0x00)", A[i], e, v);
            end
            r14_write(7'h06, 8'hFF); r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h00); r14_write(7'h11, 8'h00);
        end
        $display("lock found open after a 0x3C data write: %0d of 6; SPI errors %0d", nopen, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
