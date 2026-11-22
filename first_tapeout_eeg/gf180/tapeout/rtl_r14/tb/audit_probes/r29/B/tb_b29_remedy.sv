// tb_b29_remedy - audit round 29 (B): step 4's round-28 remedy for a CFG_ERR on APPLY_NR ("compare every shadow with
// its active copy, fix the unintended differences, then APPLY") followed literally in round 28 A's scenario (test
// shadows written, not applied, key locked). The fix writes to TEST_MUX / TEST_CTRL are refused (ADDR_ERR) while the
// key is locked; step 3's ERR rule ("bits set: write ERR back, rewrite every setting written, check again") repeats.
`timescale 1ns / 1ps
`default_nettype none
module tb_b29_remedy;
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

    logic [7:0] e, s, a, sh [0:15], ac [0:15];
    logic [6:0] sa [0:10] = '{7'h20, 7'h21, 7'h22, 7'h23, 7'h24, 7'h25, 7'h26, 7'h27, 7'h28, 7'h60, 7'h61};
    integer ndiff, tries;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;
        r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_cmd(8'h11);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        // an evaluation leaves test shadows written, not applied, and locks (round 28, A)
        r14_write(7'h11, 8'h3C); r14_write(7'h60, 8'h1C); r14_write(7'h61, 8'h02); r14_write(7'h11, 8'h00);
        r14_read(7'h06, e); r14_write(7'h06, e);
        // step 7: M 41 by APPLY_NR -> CFG_ERR
        r14_write(7'h21, 8'd41);
        r14_read(7'h06, e); r14_write(7'h06, e);
        r14_cmd(8'h44); #(40000.0);
        r14_read(7'h06, e);
        $display("APPLY_NR: ERR 0x%02h (0x20 = CFG_ERR)", e);
        r14_write(7'h06, e);
        // step 4's remedy, literally: compare every shadow with its active copy, fix the unintended differences
        // (here: make the shadow equal to the active copy; M is the intended difference), then check ERR (step 3)
        for (tries = 1; tries <= 3; tries++) begin
            ndiff = 0;
            for (int i = 0; i < 11; i++) begin
                r14_read(sa[i], s); r14_read(sa[i] + 7'h10, a);
                if (s !== a && sa[i] != 7'h21) begin
                    ndiff++;
                    $display("  try %0d: shadow 0x%02h = 0x%02h, active copy 0x%02h = 0x%02h: unintended, rewrite",
                             tries, sa[i], s, sa[i] + 7'h10, a);
                    r14_write(sa[i], a);
                end
            end
            r14_read(7'h06, e);
            $display("  try %0d: %0d differences fixed by writes; ERR 0x%02h (0x08 = ADDR_ERR); shadows now 0x60 = 0x%02h, 0x61 = 0x%02h",
                     tries, ndiff, e, {3'b000, dut.u_regs.s_atpen, dut.u_regs.s_atpsel}, {6'b0, dut.u_regs.s_cstop, dut.u_regs.s_azero});
            r14_write(7'h06, e);
            if (e == 8'h00) break;
        end
        $display("after %0d tries the rule (d) limit of 3 is %s", tries > 3 ? 3 : tries, tries > 3 ? "reached: RESET_N on every chip" : "not reached");
        // the alternative reading: APPLY anyway
        r14_cmd(8'h33); #(40000.0);
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        r14_read(7'h06, e);
        $display("APPLY anyway: ERR 0x%02h; RUN with CHOP_EN %b, TEST_CFG 0x%02h (ATP_EN %b, ATP_SEL %0d)", e, CHOP_EN,
                 TEST_CFG, TEST_CFG[4], TEST_CFG[3:0]);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
