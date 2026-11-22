// tb_a33_dlc - audit round 33 (A): eeg_digital_top with DAC_LOAD_CYCLE = 23 (inside eeg_clkgen's documented legal
// range 2..31): where DAC_LOAD and DAC_CLK fall against the tick's analog edge (AFE_RST at the end of WARMUP, e25)
`timescale 1ns / 1ps
`default_nettype none
module tb_a33_dlc;
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
    eeg_digital_top #(.DAC_LOAD_CYCLE(`DLC), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"
    real t_dacclk_rise = 0.0, t_dacclk_fall = 0.0, t_sel = 0.0;
    always @(posedge DAC_CLK) t_dacclk_rise = $realtime;
    always @(negedge DAC_CLK) t_dacclk_fall = $realtime;
    always @(negedge DAC_LOAD) t_sel = $realtime;              // SEL1/SEL2 change at the edge that ends DAC_LOAD
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_cmd(CMD_START);
        @(negedge AFE_RST);
        #0.01;
        $display("DAC_LOAD_CYCLE %0d: AFE_RST released at %0.3f ns; the SEL update (end of DAC_LOAD) %0.3f ns, DAC_CLK rise %0.3f ns and fall %0.3f ns before it (0 = the same MCLK edge)",
                 `DLC, $realtime, $realtime - t_sel, $realtime - t_dacclk_rise, $realtime - t_dacclk_fall);
        $finish;
    end
endmodule
`default_nettype wire
