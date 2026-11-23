// audit 36 A probe: SOFT_RESET (soft_req forced for one MCLK) at every MCLK phase of a 512-MCLK superperiod, from IDLE
// with the active copies at 64 kHz, range 1 (BLANK 15), CHOP1 16 kHz, then the same with range 0 and BLANK 1 (the
// shortest). Monitors over the whole run: every CHOP_OUT edge has CHOP_BLANK high in the MCLK before and the MCLK after
// it (no CDA/CDB overlap); every CHOP_BLANK pulse is 2..16 MCLK wide and equals BLANK_LEN+1 of 1, 7 or 15; every CHOP and
// CHOP_OUT half period is 128 or 256 MCLK; CHOP_OUT == CHOP; CHOP1 half periods are whole multiples of 32 frames' MCLK;
// AFE_RST is 1 from the reset on; the applied pins change at most once per MCLK edge.
`timescale 1ns / 1ps
`default_nettype none
module tb_a36_softsweep;
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
    integer mc = 0, errs = 0, nedge = 0, npulse = 0, nhalf = 0, nc1 = 0;
    always @(posedge MCLK) mc = mc + 1;
    task automatic fail(input string m);
        errs = errs + 1;
        if (errs <= 30) $display("VIOLATION @%0t mc %0d: %s", $time, mc, m);
    endtask
    // CHOP_BLANK around every CHOP_OUT edge: sampled just before each edge (the values of the cycle that ends)
    logic co_q = 1'b0, cb_q = 1'b0, cb_qq = 1'b0, co_qq = 1'b0;
    integer pend_after = 0;
    always @(posedge MCLK) begin
        #0.1;
        if (RESET_N) begin
            if (CHOP_OUT !== co_q) begin                  // CHOP_OUT changed at this edge
                nedge = nedge + 1;
                if (cb_q !== 1'b1 && mc > 40) fail("CHOP_OUT edge without CHOP_BLANK in the MCLK before it");
                pend_after = 1;
            end else if (pend_after) begin
                if (cb_q !== 1'b1) fail("CHOP_BLANK low in the MCLK after a CHOP_OUT edge");
                pend_after = 0;
            end
            if (CHOP_OUT !== CHOP) fail("CHOP_OUT != CHOP");
        end
        co_q = CHOP_OUT; cb_q = CHOP_BLANK;
    end
    // pulse widths and half periods
    integer cb_rise = 0, ch_edge = -1, c1_edge = -1;
    always @(posedge CHOP_BLANK) cb_rise = mc;
    always @(negedge CHOP_BLANK) if (RESET_N && mc > 40) begin
        npulse = npulse + 1;
        if (!((mc - cb_rise) == 2 || (mc - cb_rise) == 8 || (mc - cb_rise) == 16))
            fail($sformatf("CHOP_BLANK pulse %0d MCLK (BLANK_LEN + 1 of 1, 7 or 15 expected)", mc - cb_rise));
    end
    always @(CHOP) if (RESET_N && mc > 40) begin
        if (ch_edge >= 0) begin
            nhalf = nhalf + 1;
            if ((mc - ch_edge) != 128 && (mc - ch_edge) != 256) fail($sformatf("CHOP half period %0d MCLK", mc - ch_edge));
        end
        ch_edge = mc;
    end
    always @(CHOP1) if (RESET_N && mc > 40) begin
        if (c1_edge >= 0) begin
            nc1 = nc1 + 1;
            if ((mc - c1_edge) % 1024 != 0) fail($sformatf("CHOP1 half period %0d MCLK", mc - c1_edge));
        end
        c1_edge = mc;
    end
    // the applied pins: at most one change per MCLK edge (a runt would be two)
    logic [31:0] pins, pins_q;
    assign pins = {AFE_RST, CHOP_EN, OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, DWA_EN, TEST_CFG[5:0]};
    integer nchg_edge = 0, last_chg_t = -1;
    always @(pins) if (RESET_N && mc > 40) begin
        if (last_chg_t == mc) fail("an applied pin changed twice in one MCLK");
        last_chg_t = mc;
    end
    task automatic wait_mc(input integer n); repeat (n) @(posedge MCLK); endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    integer p, pass_, k;
    initial begin
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        for (pass_ = 0; pass_ < 2; pass_ = pass_ + 1)
            for (p = 0; p < 512; p = p + 1) begin
                // settings applied in IDLE (no pulse): 64 kHz, CHOP1 16 kHz, range 1 + M 40 (BLANK 15) or range 0 + BLANK 1,
                // DWA off, AFE_IBIAS 2, CPF 3
                r14_write(7'h26, 8'h00);
                r14_write(7'h27, 8'h05);
                r14_write(7'h23, 8'h02);
                r14_write(7'h24, 8'h03);
                if (pass_ == 0) begin r14_write(7'h21, 8'd40); r14_write(7'h22, 8'h01); end
                else begin r14_write(7'h22, 8'h00); r14_write(7'h28, 8'h01); end
                cmd(8'h33);                               // APPLY in IDLE: applied at the tick, AFE_RST stays 1
                wait_mc(1100);                            // the 64 kHz rate taken at the next wrap; a few blank pulses
                // the phase: p MCLK after a wrap (cnt == 0)
                while (dut.u_clkgen.cnt !== 9'd0) @(posedge MCLK);
                repeat (p) @(posedge MCLK);
                #1 force dut.soft_req = 1'b1;
                @(posedge MCLK); #1 release dut.soft_req;
                wait_mc(1200);                            // the reset, the rate back to 128 kHz, BLANK 7 pulses
                if (AFE_RST !== 1'b1 || OFEN !== 4'd0 || CHOP_EN !== 1'b1 || DWA_EN !== 1'b1 || AFE_IBIAS !== 2'd3)
                    fail("pins not at their reset values after the SOFT_RESET");
                if (dut.u_clkgen.fast !== 1'b1) fail("the chopper not back at 128 kHz");
            end
        $display("tb_a36_softsweep: %0d SOFT_RESET phases x 2, %0d CHOP_OUT edges, %0d blank pulses, %0d CHOP half periods, %0d CHOP1 half periods, %0d violations",
                 512, nedge, npulse, nhalf, nc1, errs);
        $finish;
    end
endmodule
`default_nettype wire
