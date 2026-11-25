// gl_sys_sdf_r14 - the r14 control macro and the ADC's digital block (eeg_adc_dig, f3) together at gate level, run with
// the SDF of the 3 corners and without delays (11/25; tracker C3).
//
// Roots: this testbench (dut, the r14 control's RTL), gl_shadow_r14 (the control's netlist in lockstep, with
// +define+GL_CODE_SRC=sys_adc_r14.code_gl: its CODE from the block's netlist) and sys_adc_r14 (the block's RTL on the
// control's outputs and its netlist on the control netlist's outputs, with sys_sys_sdf_r14.svh). The control's RTL gets
// CODE from this testbench at e2 (the code it also gives the block's TH); sys_adc_r14 checks that the block's CODE is the
// same wherever the control takes it, so the RTL pair behaves as the two blocks joined. With the SDF, TH changes
// SYS_TH_LAUNCH (15 ns, the input delay of eeg_adc_dig's constraints) after each CMP_STROBE rise and holds to the next one,
// as the quantizer drives it on the chip; every asynchronous pin changes at an MCLK falling edge (gl_sdf_r14.sv's rule).
//
// The code of frame f: a walk through every code (7 f + 3 mod 32, k = 31 - c from 0 to 31) while `walk` is set, else
// the CT loop model's stream build/top_r14.codes (tb_top_r14's). Sequence (the checks count errors):
//   1  reset; START with the timers at their minimum, DWA_EN 1 (its reset value): RUN, samples; a walk
//   2  ADC_CFG.DWA_EN 0 and APPLY in RUN: DWA_EN 0 at the pin from the APPLY's tick (thermometer selection), RUN again,
//      samples; a walk
//   3  DWA_EN 1 and APPLY: RUN, samples; a walk
//   4  SOFT_RESET in RUN: the control's registers back to their reset values, the block running on (ADC_RST_N follows
//      RESET_N only)
//   5  RESET_N low for 100 MCLK and released: the block's asynchronous reset (pointer 0, k 16) and its restart; a walk
`timescale 1ns / 1ps
`default_nettype none

module gl_sys_sdf_r14;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 2.0 * 15.259;
    logic       MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    logic [4:0] CODE = 5'd16;
    wire        MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    wire        CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, CHOP1, OFS;
    wire [7:0]  TEST_CFG;
    wire [3:0]  CPF_TRIM, OFEN;
    wire [1:0]  AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0]  OFM;

    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;

    // ---------------------------------------------------------------- codes
    integer     fcodes, ncodes = 0, cidx = 0;
    logic [4:0] codes [0:262143];
    bit         walk = 1'b0;
    logic [4:0] next_code = 5'd16;                // the code of the coming e2 (sys_adc_r14 drives TH with it)
    integer     n_walk = 0;
    function automatic logic [4:0] code_at(input integer f, input bit w);
        return w ? 5'((7 * f + 3) % 32) : codes[f % ncodes];
    endfunction
    initial begin
        fcodes = $fopen("build/top_r14.codes", "r");
        while (!$feof(fcodes) && ncodes < 262144)
            if ($fscanf(fcodes, "%d\n", codes[ncodes]) == 1) ncodes = ncodes + 1;
        $fclose(fcodes);
        if (ncodes == 0) $fatal(1, "no codes in build/top_r14.codes");
        next_code = code_at(0, walk);
    end
    always @(posedge MCLK) if (dut.cycle == 5'd1 && RESET_N) begin   // e2, as the block takes TH
        CODE <= next_code;
        if (walk) n_walk = n_walk + 1;
        cidx = cidx + 1;
        next_code <= code_at(cidx, walk);
    end
    task automatic do_walk(input integer frames);
        integer n;
        n = 0;
        walk = 1'b1;
        while (n < frames) begin                   // e2 edges (Icarus 13 has no "iff" in event controls)
            @(posedge MCLK);
            if (dut.cycle == 5'd1 && RESET_N) n = n + 1;
        end
        walk = 1'b0;
    endtask

    `include "spi_bfm_r14.svh"

    integer errors = 0;
    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 40) $display("ERROR @%0t: %s", $time, msg);
    endtask
    task automatic wr(input logic [6:0] a, input logic [7:0] v);
        @(negedge MCLK); r14_write(a, v);
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v);
        @(negedge MCLK); r14_read(a, v);
    endtask
    task automatic rd_expect(input logic [6:0] a, input logic [7:0] e, input string what);
        logic [7:0] v;
        rd(a, v);
        if (v !== e) fail($sformatf("%s: read 0x%02h = 0x%02h, expected 0x%02h", what, a, v, e));
    endtask
    task automatic cmd(input logic [7:0] c);
        wr(A_COMMAND, c);
    endtask
    task automatic wait_state(input logic [3:0] s, input real tmax_us, input string what);
        logic [7:0] v;
        realtime t0;
        t0 = $realtime;
        forever begin
            rd(A_STATE, v);
            if (v[3:0] == s) break;
            if ($realtime - t0 > tmax_us * 1000.0) begin
                fail($sformatf("%s: STATE %0d, not %0d after %0.0f us", what, v[3:0], s, tmax_us));
                break;
            end
            repeat (512) @(negedge MCLK);
        end
    endtask
    integer n_samples = 0;
    task automatic sample(input string what);
        logic [7:0] st; logic [15:0] sq; logic [23:0] d; bit ok;
        while (DRDY_N !== 1'b0) @(negedge MCLK);
        @(negedge MCLK);
        r14_sample(st, sq, d, ok);
        n_samples = n_samples + 1;
        if (!st[SMP_VALID_LSB]) fail($sformatf("%s: sample not VALID (status 0x%02h)", what, st));
        if (!ok) fail($sformatf("%s: sample CRC wrong", what));
    endtask

    initial begin
        spi_high = 9.0 * TMCLK;  spi_low = 9.0 * TMCLK;  spi_tcss = 10.0 * TMCLK;
        spi_tcsh = 7.0 * TMCLK;  spi_tidle = 20.0 * TMCLK;
        repeat (10) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        rd_expect(A_ERR, 8'h01, "1 ERR after reset (RESET_FLAG)");
        wr(A_ERR, 8'h01);
        // ---------------- 1: START, DWA on
        if (DWA_EN !== 1'b1) fail("1 DWA_EN not 1 after reset");
        wr(A_T_WARM, T_WARM_T_WARM_MIN);  wr(A_T_REC, T_REC_T_REC_MIN);
        wr(A_T_PRE, T_PRE_T_PRE_MIN);     wr(A_T_RST, T_RST_T_RST_MIN);
        wr(A_OFF_CTRL, 8'h01);            wr(A_OFF_M_H, 8'h00);   wr(A_OFF_M_L, 8'd10);
        cmd(CMD_START);
        wait_state(ST_RUN, 12000.0, "1 START");
        for (int i = 0; i < 2; i++) sample("1 RUN");
        do_walk(256);
        sample("1 RUN after a walk");
        $display("1  START to RUN with DWA_EN 1, samples, a walk through every code (errors %0d)", errors);
        // ---------------- 2: DWA off
        wr(A_ADC_CFG, 8'(ADC_CFG_CHOP1_RATE_RST));                // DWA_EN 0, CHOP1_RATE at its reset value
        cmd(CMD_APPLY);
        wait_state(ST_RUN, 8000.0, "2 APPLY (DWA_EN 0)");
        if (DWA_EN !== 1'b0) fail("2 DWA_EN not 0 after the APPLY");
        for (int i = 0; i < 2; i++) sample("2 RUN, DWA off");
        do_walk(256);
        sample("2 RUN after a walk");
        rd_expect(A_ERR, 8'h00, "2 ERR");
        $display("2  DWA_EN 0 by APPLY in RUN: thermometer selection, samples, a walk (errors %0d)", errors);
        // ---------------- 3: DWA on again
        wr(A_ADC_CFG, 8'(ADC_CFG_CHOP1_RATE_RST) | 8'(1 << ADC_CFG_DWA_EN_LSB));
        cmd(CMD_APPLY);
        wait_state(ST_RUN, 8000.0, "3 APPLY (DWA_EN 1)");
        if (DWA_EN !== 1'b1) fail("3 DWA_EN not 1 after the APPLY");
        sample("3 RUN, DWA on");
        do_walk(256);
        sample("3 RUN after a walk");
        $display("3  DWA_EN 1 by APPLY: samples, a walk (errors %0d)", errors);
        // ---------------- 4: SOFT_RESET in RUN
        cmd(CMD_SOFT_RESET);
        repeat (20) @(negedge MCLK);
        rd_expect(A_ERR, 8'h01, "4 ERR after SOFT_RESET (RESET_FLAG)");
        rd_expect(A_STATE, {4'h0, ST_IDLE}, "4 STATE after SOFT_RESET");
        if (ADC_RST_N !== 1'b1) fail("4 ADC_RST_N fell with SOFT_RESET");
        repeat (64 * 32) @(negedge MCLK);
        $display("4  SOFT_RESET in RUN: the control back to IDLE, the ADC block running on (errors %0d)", errors);
        // ---------------- 5: RESET_N
        @(negedge MCLK);
        RESET_N = 1'b0;
        repeat (100) @(negedge MCLK);
        if (!sel_at_reset()) fail("5 SEL1 / SEL2 not at their reset value with RESET_N low");
        RESET_N = 1'b1;
        repeat (20) @(negedge MCLK);
        rd_expect(A_ERR, 8'h01, "5 ERR after RESET_N (RESET_FLAG)");
        do_walk(256);
        repeat (64 * 32) @(negedge MCLK);
        $display("5  RESET_N low for 100 MCLK: the ADC block reset and restarted, a walk (errors %0d)", errors);
        if (spi_errors != 0) fail($sformatf("%0d SPI errors", spi_errors));
        if (errors == 0) $display("PASS: gl_sys_sdf_r14 (%0d SPI frames, %0d samples, %0d frames of walks)", spi_xfers, n_samples, n_walk);
        else             $display("FAIL: gl_sys_sdf_r14, %0d errors", errors);
        $finish;
    end
    // the block's reset selection (elements 0..15) on both selectors, read from sys_adc_r14's RTL instance
    function automatic bit sel_at_reset();
        return (sys_adc_r14.sel1_rtl === 31'h0000FFFF && sys_adc_r14.sel2_rtl === 31'h0000FFFF);
    endfunction
endmodule
`default_nettype wire
