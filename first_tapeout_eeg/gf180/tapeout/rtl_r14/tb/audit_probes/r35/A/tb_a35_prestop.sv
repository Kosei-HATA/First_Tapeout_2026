// audit 35 A probe: STOP taken in PRE of an APPLY that switches the chopper rate (both directions, T_PRE 3),
// committed so that each of the PRE ticks takes it; AFE_RST rise minus the OFM (DAC) change, in MCLK and us.
`timescale 1ns / 1ps
`default_nettype none
module tb_a35_prestop;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd13 + 5'($urandom % 6);
    integer mc = 0;
    always @(posedge MCLK) mc = mc + 1;
    integer ofm_mc = 0, afe_rise_mc = 0, pre_mc = 0;
    always @(OFM) ofm_mc = mc;
    always @(posedge AFE_RST) afe_rise_mc = mc;
    always @(dut.seq_state) if (dut.seq_state == ST_PRE) pre_mc = mc;
    task automatic wait_state(input logic [3:0] s);
        integer n; n = 0;
        while (dut.seq_state !== s && n < 8000000) begin @(posedge MCLK); n = n + 1; end
        if (n >= 8000000) begin $display("TIMEOUT state %0d", s); $finish; end
    endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    integer dir, k, m;
    real dly [0:2];
    initial begin
        dly[0] = 1000.0; dly[1] = 6500.0; dly[2] = 14500.0;
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);
        m = 40;
        for (dir = 0; dir < 2; dir++) begin
            for (k = 0; k < 3; k++) begin
                // start from the rate the APPLY leaves: dir 0 = 64 -> 128 kHz, dir 1 = 128 -> 64 kHz
                r14_write(7'h26, dir == 0 ? 8'h00 : 8'h01);
                cmd(8'h11); wait_state(ST_RUN);
                m = (m == 40) ? 41 : 40;
                r14_write(7'h21, m[7:0]);
                r14_write(7'h26, dir == 0 ? 8'h01 : 8'h00);
                r14_cmd(8'h33);
                wait_state(ST_PRE);
                #(dly[k]);
                r14_cmd(8'h22);                       // STOP
                wait_state(ST_IDLE);
                $display("%s APPLY tick in frame %0d (mod 16); STOP taken %0d MCLK after it; AFE_RST up %0d MCLK = %0.2f us after the OFM change (state before IDLE: PRE)",
                         dir == 0 ? "64->128k" : "128->64k", (pre_mc / 32) % 16, mc - pre_mc, afe_rise_mc - ofm_mc,
                         (afe_rise_mc - ofm_mc) * TMCLK / 1000.0);
            end
        end
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
