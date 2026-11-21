// tb_a24d - audit round 24, auditor A: directed checks of two host-procedure cases.
//   D1: START, then an APPLY in WARMUP 2 ms later (step 4 allows it): time from START's CS_N rise to RUN against
//       rule (d)'s T_WARM + T_REC + T_ELEC + 5 ms.
//   D2: tracking at the top of range 1 (M 127): APPLY_NR to M 128, then APPLY to M 128 (SEQ-15's remedy): ERR and
//       the active M after each.
`timescale 1ns / 1ps
`default_nettype none

module tb_a24d;
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

    always @(posedge MCLK) if (dut.cycle == 5'd1) #0.2 CODE = 5'(3 + $urandom % 25);

    task automatic wait_pending();
        logic [7:0] v;
        do r14_read(7'h03, v); while (v[4]);
    endtask
    task automatic wait_state(input logic [3:0] s);
        logic [7:0] v;
        do begin #(20000.0); r14_read(7'h04, v); end while (v[3:0] != s);
    endtask

    real t_start, t_run, limit;
    logic [7:0] v, e;
    initial begin
        #(50.0 * TMCLK); RESET_N = 1'b1; #(2000.0);
        r14_write(7'h06, 8'hFF);                                   // clear RESET_FLAG
        // D1
        r14_cmd(8'h11); t_start = $realtime; wait_pending();
        #(2.0e6 - ($realtime - t_start));
        r14_read(7'h04, v);
        $display("D1: STATE %0d at %0.3f ms after START; APPLY now", v, ($realtime - t_start) / 1.0e6);
        r14_cmd(8'h33); wait_pending();
        while (dut.seq_state != ST_RUN) #(1000.0);
        t_run = $realtime;
        limit = (5.0 + 32 * 7.8125e-3 + 0.0 + 5.0);                // T_WARM + T_REC + T_ELEC + 5 ms (defaults)
        $display("D1: RUN %0.3f ms after START's CS_N rise; rule (d) limit %0.3f ms -> %s", (t_run - t_start) / 1.0e6, limit,
                 ((t_run - t_start) / 1.0e6 > limit) ? "EXCEEDED" : "within");
        // D2: range 1, M 127 by APPLY, then the step to 128
        r14_write(7'h22, 8'h01); r14_write(7'h20, 8'h00); r14_write(7'h21, 8'd127);
        r14_cmd(8'h33); wait_pending(); wait_state(ST_RUN);
        $display("D2: RUN with range 1, active M %0d, OFM %0d, OFEN %b", dut.u_regs.a_m, OFM, OFEN);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h21, 8'd128 & 8'hFF); r14_write(7'h20, 8'h00);     // M 128: M_L 0x80
        r14_cmd(8'h44); wait_pending(); r14_read(7'h06, e);
        $display("D2: APPLY_NR to M 128: ERR %02h, active M %0d, OFM %0d", e, dut.u_regs.a_m, OFM);
        r14_write(7'h06, 8'hFF);
        r14_cmd(8'h33); wait_pending(); r14_read(7'h06, e);
        $display("D2: APPLY to M 128 (same range): ERR %02h, active M %0d, STATE %0d", e, dut.u_regs.a_m, dut.seq_state);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule

`default_nettype wire
