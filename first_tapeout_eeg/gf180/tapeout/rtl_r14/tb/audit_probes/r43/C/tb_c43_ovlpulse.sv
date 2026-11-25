// audit43 C: an overload (extreme codes) inside the AFE_RST pulse of an APPLY in RUN must not set DFLAG.OVL (SEQ-11:
// OVL only in FILL and RUN); tb_top_r14's N phase forces the codes for 12 frames of PRE only (no extreme code in PULSE)
`timescale 1ns / 1ps
`default_nettype none
module tb_c43_ovlpulse;
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
    bit force31 = 1'b0;
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= force31 ? 5'd31 : 5'd14 + ($random % 4);   // changes at e2
    `include "spi_bfm_r14.svh"
    logic [7:0] v, e;
    integer nhit = 0, nhit_pulse = 0;
    always @(posedge MCLK) if (dut.u_ovl.ovl_hit === 1'b1) begin nhit++; if (dut.seq_state == 4'd8) nhit_pulse++; end
    initial begin
        #(1000.0); RESET_N = 1'b1; #(2000.0);
        r14_cmd(8'h11);                                           // START with the defaults
        wait (dut.seq_state == 4'd6);
        r14_write(7'h07, 8'hFF); r14_write(7'h06, 8'hFF);
        r14_write(7'h24, 8'h05);                                  // CPF_TRIM: an APPLY with its pulse
        r14_cmd(8'h33);
        wait (dut.seq_state == 4'd8);                             // PULSE (AFE_RST high, 104 frames)
        force31 = 1'b1;
        repeat (40 * 32) @(posedge MCLK);                         // 40 frames of extreme codes inside PULSE
        force31 = 1'b0;
        wait (dut.seq_state == 4'd2);                             // RECOVER
        r14_read(7'h07, v);
        r14_read(7'h06, e);
        $display("c43 overload in PULSE: %0d hits, %0d of them in PULSE; DFLAG 0x%02h (OVL %b, expected 0), ERR 0x%02h",
                 nhit, nhit_pulse, v, v[DFLAG_OVL_LSB], e);
        $finish;
    end
endmodule
`default_nettype wire
