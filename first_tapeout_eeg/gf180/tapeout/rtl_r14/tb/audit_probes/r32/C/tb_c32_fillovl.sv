// tb_c32_fillovl - audit round 32, auditor C: an ADC overload (code 31) across the output time that completes FILL.
// SEQ-04 / DAT-01 (fsm_spec FILL/OUT [valid]): the first valid output in FILL is always stored and RUN entered; the
// sample carries OVL and DFLAG.OVL is set. Probe only: drives the pins through the r14 BFM.
`timescale 1ns / 1ps
`default_nettype none
module tb_c32_fillovl;
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
    logic ovl_force = 1'b0;
    always @(posedge MCLK) if (dut.cycle == 5'd1 && RESET_N) CODE <= ovl_force ? 5'd31 : 5'd8 + 5'($urandom_range(0, 16));
    integer errors = 0, nout;
    logic [7:0] v, st; logic [15:0] sq; logic [23:0] d; bit ok;
    logic [15:0] seq3;
    initial begin
        repeat (10) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(posedge MCLK);
        r14_write(7'h06, 8'hFF);                         // ERR cleared
        r14_cmd(8'h11);                                  // START (defaults: T_WARM 5 ms, T_ELEC 0)
        while (dut.seq_state !== 4'd5) @(posedge MCLK);  // FILL (entered at ALIGN's output time, the clear)
        nout = 0;
        while (nout < 2) begin @(posedge MCLK); if (dut.cic_stb) nout++; end   // FILL's two invalid outputs
        repeat (1000 * 32) @(posedge MCLK);              // 24 frames before the third output time
        ovl_force = 1'b1;                                // code 31 from 24 frames before it to 16 frames after it
        while (!dut.cic_stb) @(posedge MCLK);
        seq3 = dut.seq_cnt;
        @(posedge MCLK); #1;
        $display("third FILL output (SEQ %0d): OVL_NOW %b, state after it %0d (6 = RUN), FIFO level %0d", seq3,
                 dut.ovl_now, dut.seq_state, dut.fifo_level);
        if (dut.seq_state !== 4'd6) begin $display("ERROR: FILL's first valid output not stored / RUN not entered under an overload"); errors++; end
        repeat (16 * 32) @(posedge MCLK);
        ovl_force = 1'b0;
        repeat (64 * 32) @(posedge MCLK);
        r14_sample(st, sq, d, ok);
        $display("first sample: status 0x%02h SEQ %0d crc_ok %b", st, sq, ok);
        if (!ok || st[SMP_VALID_LSB] !== 1'b1 || st[SMP_OVL_LSB] !== 1'b1 || sq !== seq3) begin
            $display("ERROR: first sample status 0x%02h SEQ %0d, expected VALID 1, OVL 1, SEQ %0d", st, sq, seq3); errors++;
        end
        r14_read(7'h07, v);
        if (v[DFLAG_OVL_LSB] !== 1'b1) begin $display("ERROR: DFLAG 0x%02h without OVL", v); errors++; end
        if (errors == 0) $display("PASS: tb_c32_fillovl"); else $display("FAIL: tb_c32_fillovl (%0d errors)", errors);
        $finish;
    end
    initial begin #(60.0e6); $display("FAIL: tb_c32_fillovl watchdog"); $finish; end
endmodule
`default_nettype wire
