// tb_b29_lockrw - audit round 29 (B): step 3 with the round-28 test-register restore ("write them back to their reset
// values while the key is open, confirm by this step's read-back, then lock") and one fault on another setting's write
// (a wrong CRC on BOOST_TRIM, as tb_b28_rewrite). Step 3's rule for a bit in ERR ("write ERR back, rewrite every
// setting written (IF_CFG excepted), check ERR again") replayed literally: TEST_MUX and TEST_CTRL are shadows written in
// this step, and after the lock their rewrite is refused with ADDR_ERR on every pass.
`timescale 1ns / 1ps
`default_nettype none
module tb_b29_lockrw;
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
    logic [7:0] e, v1, v2;
    // the settings this step 3 writes (shadows): BOOST_TRIM, and the test shadows put back to their reset values
    task automatic settings();
        r14_write(7'h25, 8'h12);
        r14_write(7'h60, 8'h00);
        r14_write(7'h61, 8'h00);
    endtask
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        r14_write(7'h06, 8'h01);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h51, 8'h00);
        // an earlier evaluation: key open, test shadows used
        r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h1C); r14_write(7'h61, 8'h02);
        r14_read(7'h06, e); r14_write(7'h06, e);
        // step 3 (round 28): key still open; BOOST_TRIM with one fault (a wrong CRC), the test shadows put back
        spi_tx[0] = 8'h25; spi_tx[1] = 8'h12; spi_tx[2] = 8'h00; spi_xfer(3, 0);       // CRC_ERR, not written
        r14_write(7'h60, 8'h00); r14_write(7'h61, 8'h00);
        r14_read(7'h60, v1); r14_read(7'h60, v2); $display("TEST_MUX read back 0x%02h 0x%02h", v1, v2);
        r14_read(7'h61, v1); r14_read(7'h61, v2); $display("TEST_CTRL read back 0x%02h 0x%02h", v1, v2);
        r14_write(7'h11, 8'h00);                                                       // lock
        r14_read(7'h06, e);
        $display("step 3's check: ERR 0x%02h (a bit: write ERR back, rewrite every setting written but IF_CFG)", e);
        for (int pass = 1; pass <= 3; pass++) begin
            r14_write(7'h06, e);
            settings();                                         // literal: every setting written in this step
            r14_read(7'h06, e);
            $display("rewrite pass %0d: ERR 0x%02h (0x08 ADDR_ERR: TEST_MUX / TEST_CTRL refused, key locked); BOOST_TRIM 0x%02h",
                     pass, e, {2'b00, dut.u_regs.s_bn, 2'b00, dut.u_regs.s_bp});
        end
        $display("SPI errors in the bench's own checks: %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
