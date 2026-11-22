// tb_a28_drdy - audit round 28 (A): the chopper phase of DRDY_N's edges in pulse mode (DRDY_MODE 1), at 128 and
// 64 kHz. Each DRDY_N edge is classified by CHOP in the MCLK before it (1 = phase A), as tb_a27_dbg did for RAW.
`timescale 1ns / 1ps
`default_nettype none

module tb_a28_drdy;
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

    logic chop_q = 1'b0, drdy_q = 1'b1;
    integer fall_a = 0, fall_b = 0, rise_a = 0, rise_b = 0, armed = 0;
    always @(posedge MCLK) begin
        #1;
        if (armed && DRDY_N !== drdy_q) begin
            if (DRDY_N === 1'b0) begin if (chop_q) fall_a++; else fall_b++; end
            else                 begin if (chop_q) rise_a++; else rise_b++; end
        end
        drdy_q = DRDY_N; chop_q = CHOP;
    end

    logic [7:0] s; logic [15:0] q; logic [23:0] d; bit ok;
    task automatic run_rate(input logic fast);
        r14_cmd(8'h22); #(40000.0);                       // STOP
        r14_write(7'h26, {7'd0, fast});                    // CHOP_CFG
        r14_cmd(8'h11);                                     // START
        while (dut.u_seq.state !== ST_RUN) @(posedge MCLK);
        fall_a = 0; fall_b = 0; rise_a = 0; rise_b = 0; armed = 1;
        repeat (40) begin                                   // 40 outputs; read each sample once DRDY_N is back high
            @(negedge DRDY_N); @(posedge DRDY_N);
            r14_sample(s, q, d, ok);
        end
        armed = 0;
        $display("%s kHz: DRDY_N falls in phase A %0d, B %0d; rises in phase A %0d, B %0d", fast ? "128" : "64",
                 fall_a, fall_b, rise_a, rise_b);
    endtask
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h55, 8'h02);                            // IF_CFG: DRDY_MODE 1 (pulse), CRC off
        run_rate(1'b1);
        run_rate(1'b0);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
