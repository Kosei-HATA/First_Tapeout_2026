// audit round 46, auditor C: DRDY_N (level mode) release after the read that empties the FIFO, from the CS_N pad rise
// (M5's measure), clean RTL vs a copy whose whole CS_N-rise branch is one MCLK later (probe, not part of the suite)
`timescale 1ns / 1ps
`default_nettype none
module tb_c46_pop;
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
    real t_rise, t_dr, mn = 1e9, mx = -1e9;
    always @(posedge CS_N) t_rise = $realtime;
    always @(posedge DRDY_N) t_dr = $realtime;
    initial begin
        logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        r14_write(7'h50, 8'd5); r14_cmd(8'h11);                       // START, T_WARM 5 ms
        for (int k = 0; k < 6; k++) begin
            while (DRDY_N !== 1'b0) @(posedge MCLK);
            repeat (k) @(posedge MCLK); #(k * TMCLK / 6.0);            // vary the CS_N phase
            r14_sample(st, sq, d, ok);
            #(10 * TMCLK);
            if ((t_dr - t_rise) / TMCLK < mn) mn = (t_dr - t_rise) / TMCLK;
            if ((t_dr - t_rise) / TMCLK > mx) mx = (t_dr - t_rise) / TMCLK;
        end
        $display("DRDY_N released %0.2f..%0.2f MCLK after the emptying read's CS_N rise (M5: at most 5)", mn, mx);
        $finish;
    end
endmodule
`default_nettype wire
