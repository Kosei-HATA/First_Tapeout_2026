// tb_a26_blank (audit round 26, auditor A): CHOP_BLANK = gen_blank | a_azero across a SOFT_RESET in the ADC_ZERO
// test mode. soft_req is forced for one MCLK in frame cycle 28, 29 or 30 of a frame before a CHOP_OUT edge (the
// blanking flip-flop rises at e31); the control reset reaches eeg_regs TREE ns after rst_n's edge (a reset-tree model,
// eeg_digital_top_tree.sv). Every CHOP_BLANK low pulse and every AFE_RST / TEST_CFG[5] edge is printed.
`timescale 1ns / 1ps
`default_nettype none
module tb_a26_blank;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    parameter real TREE = 0.0;
    parameter int  SOFT_CYC = 29;
    logic MCLK = 0, RESET_N = 0, SCLK = 0, CS_N = 1, MOSI = 0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN, CMP_STROBE, DAC_CLK;
    wire  CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, CHOP1, OFS;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    logic [4:0] CODE = 5'd15;
    eeg_digital_top #(.TREE(TREE)) dut (.*);
    always #(TMCLK / 2) MCLK = ~MCLK;
`include "spi_bfm_r14.svh"
    real t_fall = -1.0;
    integer nshort = 0;
    always @(CHOP_BLANK) begin
        if (CHOP_BLANK === 1'b0) t_fall = $realtime;
        else if (t_fall >= 0.0) begin
            $display("  CHOP_BLANK low %8.3f ns (from %0.3f ns, frame cycle at the fall %0d)", $realtime - t_fall,
                     t_fall, dut.cycle);
            if ($realtime - t_fall < TMCLK - 0.01) nshort = nshort + 1;
            t_fall = -1.0;
        end
    end
    always @(AFE_RST)     if ($realtime > 1000.0) $display("  AFE_RST -> %b at %0.3f ns", AFE_RST, $realtime);
    always @(TEST_CFG[5]) if ($realtime > 1000.0) $display("  TEST_CFG[5] (ADC_ZERO) -> %b at %0.3f ns", TEST_CFG[5], $realtime);
    logic [7:0] v;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1;
        repeat (20) @(negedge MCLK);
        r14_write(7'h11, 8'h3C);                 // TEST_KEY
        r14_write(7'h61, 8'h01);                 // TEST_CTRL.ADC_ZERO
        r14_cmd(8'h33);                          // APPLY in IDLE (AFE_RST held)
        repeat (600) @(negedge MCLK);
        r14_read(7'h71, v);
        $display("TREE %0.1f ns, soft_req in cycle %0d: TEST_CTRL active copy 0x%02h, CHOP_BLANK %b", TREE, SOFT_CYC,
                 v, CHOP_BLANK);
        // a frame before a CHOP_OUT edge at 128 kHz: frame 3, 7, 11 or 15 of the superperiod
        do @(posedge MCLK); while (!(dut.u_clkgen.cnt[6:5] == 2'd3 && dut.cycle == 5'(SOFT_CYC)));
        #1 force dut.soft_req = 1'b1;
        @(posedge MCLK);
        #1 release dut.soft_req;
        repeat (100) @(negedge MCLK);
        $display("short (< 1 MCLK) CHOP_BLANK low pulses: %0d", nshort);
        $finish;
    end
endmodule
`default_nettype wire
