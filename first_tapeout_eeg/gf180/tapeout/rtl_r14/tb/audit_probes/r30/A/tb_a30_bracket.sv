// tb_a30_bracket - audit round 30 (A). Host step 3's test-register bracket used to SET a test value (TEST_CTRL =
// 0x02, CHOP_STOP) with the lock write (4) lost: step (5) writes TEST_CTRL's reset value 0x00, which an unlocked chip
// accepts ("harmless" per the text), the host relocks and re-checks (5) as written, then STARTs.
`timescale 1ns / 1ps
`default_nettype none
module tb_a30_bracket;
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
    logic [7:0] v, v2;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);              // clear RESET_FLAG
        // (1) unlock and check ERR
        r14_write(7'h11, 8'h3C); r14_read(7'h06, v); $display("(1) ERR after unlock 0x%02h", v);
        // (2) set TEST_CTRL = 0x02 (CHOP_STOP)
        r14_write(7'h61, 8'h02);
        // (3) read back twice
        r14_read(7'h61, v); r14_read(7'h61, v2); $display("(3) TEST_CTRL read back 0x%02h 0x%02h", v, v2);
        // (4) the lock write is lost (not received by the chip): nothing sent
        // (5) lock check as written: write TEST_CTRL's reset value 0x00, expect exactly ADDR_ERR
        r14_write(7'h61, 8'h00); r14_read(7'h06, v);
        $display("(5) ERR 0x%02h (ADDR_ERR expected if locked) -> lock missing, relock as the text says", v);
        r14_write(7'h11, 8'h00);                                // relock
        r14_write(7'h61, 8'h00); r14_read(7'h06, v);           // (5) again
        $display("(5') ERR 0x%02h (exactly ADDR_ERR: the host accepts the bracket)", v);
        r14_write(7'h06, v);
        r14_read(7'h61, v); $display("TEST_CTRL shadow now 0x%02h (the host verified 0x02 in (3))", v);
        r14_cmd(CMD_START);
        while (dut.u_seq.state !== ST_WARMUP) @(posedge MCLK);
        #(1000.0);
        r14_read(7'h71, v);
        $display("after START: TEST_CTRL active 0x%02h, CHOP_EN pin %b (the host believes CHOP_STOP = 1, CHOP_EN = 0)", v, CHOP_EN);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
