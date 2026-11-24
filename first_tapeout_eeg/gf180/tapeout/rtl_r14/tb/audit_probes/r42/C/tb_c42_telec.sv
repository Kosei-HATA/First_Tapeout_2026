// audit42 C probe: T_ELEC taken at the start of its wait (spec 4.2), as phase AG checks T_REC and T_RST: START with
// T_ELEC 0, T_ELEC 2 written in WARMUP (no command pending); RECOVER's expiry must lead to WAIT_E for 2 ms. Then the
// other way: START with T_ELEC 2, T_ELEC 0 written in WARMUP: RECOVER's expiry must lead to ALIGN.
`timescale 1ns / 1ps
`default_nettype none
module tb_c42_telec;
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
    real t_st [0:8];
    logic [3:0] st_q = 0;
    always @(posedge MCLK) if (dut.seq_state !== st_q) begin st_q = dut.seq_state; t_st[st_q] = $realtime; end
    integer nbad = 0;
    initial begin
        logic [7:0] v;
        #(20 * TMCLK); RESET_N = 1'b1; #(50 * TMCLK);
        r14_write(7'h06, 8'hFF);
        // (1) START with T_ELEC 0; T_ELEC 2 written in WARMUP
        r14_cmd(8'h11);
        while (dut.seq_state !== 4'd1) @(posedge MCLK);
        repeat (1000) @(posedge MCLK);
        r14_write(7'h51, 8'd2);
        r14_read(7'h06, v);
        while (dut.seq_state !== 4'd3 && dut.seq_state !== 4'd4) @(posedge MCLK);
        $display("(1) T_ELEC 2 written in WARMUP: RECOVER's expiry -> state %0d (WAIT_E 3 expected), ERR 0x%02h", dut.seq_state, v);
        if (dut.seq_state !== 4'd3) nbad++;
        r14_cmd(8'h22); while (dut.seq_state !== 4'd0) @(posedge MCLK);
        // (2) START with T_ELEC 2; T_ELEC 0 written in WARMUP
        r14_cmd(8'h11);
        while (dut.seq_state !== 4'd1) @(posedge MCLK);
        repeat (1000) @(posedge MCLK);
        r14_write(7'h51, 8'd0);
        while (dut.seq_state !== 4'd3 && dut.seq_state !== 4'd4) @(posedge MCLK);
        $display("(2) T_ELEC 0 written in WARMUP: RECOVER's expiry -> state %0d (ALIGN 4 expected)", dut.seq_state);
        if (dut.seq_state !== 4'd4) nbad++;
        $display("tb_c42_telec: %0d mismatches with spec 4.2 (the timer taken at the start of its wait); SPI errors %0d", nbad, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
