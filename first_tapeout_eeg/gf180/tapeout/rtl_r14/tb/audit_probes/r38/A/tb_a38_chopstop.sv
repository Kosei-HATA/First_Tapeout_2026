// audit 38 A probe: a reset that ends the CHOP_STOP test mode (CHOP_EN 0 -> 1) in chopper phase B.
// The AFE clock driver (gf180/tapeout/afe/eeg_afe_clk.spice) makes PH0 = CHOP | ~CHOP_EN (input chopper) and
// COE = CHOP_OUT | ~CHOP_EN, CDA = COE & ~CHOP_BLANK, CDB = ~COE & ~CHOP_BLANK (output chopper). With CHOP_EN 0 both
// choppers are held in phase A; when CHOP_EN returns to 1 while CHOP = CHOP_OUT = 0, both switch A -> B at that
// instant: the input chopper through its own dead time, the output chopper (CDA off, CDB on) with no CHOP_BLANK
// around it. This bench reports every such switch for: (1) SOFT_RESET (soft_req forced for one MCLK) in RUN, phase B,
// outside a blanking window, CHOP_STOP 1; (2) the same with CHOP_STOP 0 (control: no switch); (3) RESET_N in RUN with
// CHOP_STOP 1 in phase B; (4) an APPLY in RUN that clears CHOP_STOP (the tick is in phase A: no switch).
`timescale 1ns / 1ps
`default_nettype none
module tb_a38_chopstop;
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

    // the clock driver's logic (zero delay), and its switches without a blanking window
    wire PH0 = CHOP | ~CHOP_EN;
    wire COE = CHOP_OUT | ~CHOP_EN;
    wire CDA = COE & ~CHOP_BLANK;
    wire CDB = ~COE & ~CHOP_BLANK;
    integer n_unblanked = 0, n_ph0_mid = 0, n_cda_fall_with_cdb_rise = 0;
    string tag = "";
    // an output-chopper phase change (COE) while CHOP_BLANK is low: CDA and CDB swap at once
    always @(COE) if ($time > 100) begin
        if (CHOP_BLANK === 1'b0) begin
            n_unblanked = n_unblanked + 1;
            $display("  [%s] @%0t ns: COE -> %b with CHOP_BLANK 0 (CDA %b, CDB %b), CHOP_OUT %b, CHOP_EN %b, AFE_RST %b, state %0d, frame %0d cycle %0d",
                     tag, $time / 1000, COE, CDA, CDB, CHOP_OUT, CHOP_EN, AFE_RST, dut.seq_state, dut.u_clkgen.cnt[8:5], dut.cycle);
        end
    end
    // an input-chopper phase change (PH0) away from a CHOP edge (CHOP did not change at this time)
    logic chop_q = 1'b0;
    always @(posedge MCLK) chop_q <= CHOP;
    always @(PH0) if ($time > 100 && CHOP === chop_q) begin
        n_ph0_mid = n_ph0_mid + 1;
        $display("  [%s] @%0t ns: PH0 -> %b without a CHOP edge (CHOP %b, CHOP_EN %b, AFE_RST %b)", tag, $time / 1000,
                 PH0, CHOP, CHOP_EN, AFE_RST);
    end

    task automatic wait_state(input logic [3:0] s, input integer max_ms);
        integer n;
        n = 0;
        while (dut.seq_state !== s && n < max_ms * 32768) begin @(posedge MCLK); n = n + 1; end
        if (dut.seq_state !== s) $display("ERROR: state %0d not reached", s);
    endtask
    // the next MCLK edge in 128 kHz phase B outside blanking: frame 5 or 13 of the superperiod, cycle 20
    task automatic to_phase_b;
        do @(posedge MCLK); while (!((dut.u_clkgen.cnt[7:5] == 3'd5) && (dut.cycle == 5'd20)));
    endtask
    task automatic soft_reset_now;
        @(negedge MCLK);
        force dut.soft_req = 1'b1;
        @(negedge MCLK);
        release dut.soft_req;
    endtask
    task automatic setup_run(input logic stop);
        // test bracket: unlock, TEST_CTRL, lock; then START and wait for RUN
        r14_write(7'h11, 8'h3C);
        r14_write(7'h61, stop ? 8'h02 : 8'h00);
        r14_write(7'h11, 8'h00);
        r14_cmd(8'h11);
        wait_state(4'd6, 20);
        $display("[%s] RUN, CHOP_EN %b, CHOP_BLANK %b", tag, CHOP_EN, CHOP_BLANK);
    endtask

    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        // (1) SOFT_RESET in phase B, CHOP_STOP 1
        tag = "1 SOFT_RESET, CHOP_STOP 1";
        setup_run(1'b1);
        to_phase_b;
        $display("[%s] SOFT_RESET at frame %0d cycle %0d, CHOP %b CHOP_OUT %b CHOP_BLANK %b", tag,
                 dut.u_clkgen.cnt[8:5], dut.cycle, CHOP, CHOP_OUT, CHOP_BLANK);
        soft_reset_now;
        repeat (600) @(negedge MCLK);
        // (2) control: CHOP_STOP 0
        tag = "2 SOFT_RESET, CHOP_STOP 0";
        repeat (40) @(negedge MCLK);
        setup_run(1'b0);
        to_phase_b;
        soft_reset_now;
        repeat (600) @(negedge MCLK);
        // (3) RESET_N in phase B, CHOP_STOP 1
        tag = "3 RESET_N, CHOP_STOP 1";
        setup_run(1'b1);
        to_phase_b;
        @(negedge MCLK);
        #3;
        RESET_N = 1'b0;
        #100;
        RESET_N = 1'b1;
        repeat (600) @(negedge MCLK);
        // (4) an APPLY in RUN that clears CHOP_STOP: its tick is in phase A
        tag = "4 APPLY clearing CHOP_STOP";
        setup_run(1'b1);
        r14_write(7'h11, 8'h3C);
        r14_write(7'h61, 8'h00);
        r14_write(7'h11, 8'h00);
        r14_cmd(8'h33);
        wait_state(4'd7, 2);
        $display("[%s] PRE, CHOP_EN %b", tag, CHOP_EN);
        repeat (2000) @(negedge MCLK);
        $display("tb_a38_chopstop: %0d output-chopper switches with CHOP_BLANK low, %0d input-chopper switches away from a CHOP edge",
                 n_unblanked, n_ph0_mid);
        $finish;
    end
endmodule
`default_nettype wire
