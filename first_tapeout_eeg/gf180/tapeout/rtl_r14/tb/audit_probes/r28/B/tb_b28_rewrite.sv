// tb_b28_rewrite - audit round 28 (B): step 3's "rewrite every setting written" (round 27) replayed literally, the
// IF_CFG write included in the form step 3 first sent it (2 bytes, CRC off), on a chip with CRC on.
`timescale 1ns / 1ps
`default_nettype none
module tb_b28_rewrite;
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
    always @(posedge MCLK) CODE <= 5'd8 + 5'($urandom_range(0, 16));
    `include "spi_bfm_r14.svh"
    logic [7:0] e, v;
    // step 3's writes in the order and form it sent them: IF_CFG first (CRC off), then T_ELEC and settings (CRC on)
    task automatic step3_writes();
        bfm_crc_en = 1'b0; r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h51, 8'h00);
        r14_write(7'h25, 8'h12);
        r14_write(7'h21, 8'hDA);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);                               // step 2
        step3_writes();                                        // step 3, first pass
        r14_read(7'h55, v); $display("IF_CFG read back 0x%02h (CRC %s)", v, spi_errors == 0 ? "valid" : "BAD");
        // one fault in the pass: a write that the chip did not take (here a wrong CRC on BOOST_TRIM)
        spi_tx[0] = 8'h25; spi_tx[1] = 8'h12; spi_tx[2] = 8'h00; spi_xfer(3, 0);
        r14_read(7'h06, e); $display("step 3's check: ERR 0x%02h (a bit: write ERR back, rewrite every setting written)", e);
        for (int pass = 1; pass <= 3; pass++) begin
            r14_write(7'h06, e);
            step3_writes();                                    // literal replay
            r14_read(7'h06, e);
            $display("rewrite pass %0d: ERR 0x%02h, IF_CFG 0x%02h (CRC_EN %0d)", pass, e, dut.u_regs.r_crc | (dut.u_regs.r_drdy << 1), dut.u_regs.r_crc);
        end
        $display("SPI errors in the bench's own checks: %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
