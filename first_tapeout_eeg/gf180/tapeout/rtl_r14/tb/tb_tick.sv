// tb_tick - the r14 clock generator's tick: at both chopper rates and across random rate changes, every tick is
// TICK_FRAME * 32 + TICK_CYCLE MCLK cycles after a rising CHOP edge (56 at 128 kHz, 120 at 64 kHz: the middle of
// phase A, CHOP high; the constants generated from fsm_spec.TIMING, audit round 13), and every chopper period has
// exactly one tick. CHOP_OUT equals CHOP (CHOP_DLY tied to 0). At least 700 periods (400,000 MCLK at 512 MCLK a
// period at the slower rate gives 781), 100 at each rate and a tick in each (audit round 28, auditor C: a counter that
// never moved printed "0 ticks in 0 periods; 0 errors" and passed).
`timescale 1ns / 1ps
`default_nettype none
module tb_tick;
`include "eeg_regs_defs.svh"
    logic clk = 0, rst_n = 0, chop_fast = 1;
    logic [4:0] cycle;
    logic cmp_strobe, th_capture, dac_load, cic_en, chop, chop_out, chop_blank, raw_clk, tick;
    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) dut (.clk(clk), .rst_n(rst_n), .chop_fast(chop_fast), .chop_dly(8'd0),
        .blank_len(4'd7), .cycle(cycle), .cmp_strobe(cmp_strobe), .th_capture(th_capture), .dac_load(dac_load),
        .cic_en(cic_en), .chop(chop), .chop_out(chop_out), .chop_blank(chop_blank), .raw_clk(raw_clk), .tick(tick));
    always #15.259 clk = ~clk;
    integer since_rise, ticks_in_period, errors, nticks, nper, i, fast_per, slow_per, seed;
    logic chop_q, rate_of_period;
    initial begin
        errors = 0; nticks = 0; nper = 0; fast_per = 0; slow_per = 0; seed = 3;
        since_rise = -1; ticks_in_period = 0; chop_q = 0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        for (i = 0; i < 400000; i = i + 1) begin
            @(posedge clk);
            #1;
            if (chop_out !== chop) begin $display("ERROR: CHOP_OUT != CHOP"); errors = errors + 1; end
            if (chop && !chop_q) begin                     // a rising CHOP edge: a new period starts here
                if (since_rise >= 0) begin
                    if (ticks_in_period != 1) begin
                        $display("ERROR: %0d ticks in a chopper period", ticks_in_period);
                        errors = errors + 1;
                    end
                    nper = nper + 1;
                end
                since_rise = 0;
                ticks_in_period = 0;
                rate_of_period = dut.fast;
                if (dut.fast) fast_per = fast_per + 1; else slow_per = slow_per + 1;
            end else if (since_rise >= 0) begin
                since_rise = since_rise + 1;
            end
            chop_q = chop;
            if (tick) begin
                nticks = nticks + 1;
                ticks_in_period = ticks_in_period + 1;
                if (cycle !== TICK_CYCLE || chop !== 1'b1 ||
                    since_rise != (rate_of_period ? 32 * TICK_FRAME_128K + TICK_CYCLE : 32 * TICK_FRAME_64K + TICK_CYCLE)) begin
                    $display("ERROR: tick at cycle %0d, %0d MCLK after the rising edge, CHOP %b, rate %0d",
                             cycle, since_rise, chop, rate_of_period);
                    errors = errors + 1;
                end
            end
            if (($urandom(seed) % 3000) == 0) begin       // random rate requests (applied at superperiod wraps)
                seed = seed + 1;
                chop_fast = ~chop_fast;
            end
        end
        if (nper < 700 || fast_per < 100 || slow_per < 100 || nticks < nper) begin
            $display("ERROR: %0d ticks in %0d periods (%0d at 128 kHz, %0d at 64 kHz): at least 700 periods, 100 at each rate, a tick in each",
                     nticks, nper, fast_per, slow_per);
            errors = errors + 1;
        end
        $display("tb_tick: %0d ticks in %0d periods (%0d at 128 kHz, %0d at 64 kHz); %0d errors", nticks, nper,
                 fast_per, slow_per, errors);
        if (errors == 0) $display("PASS: tick in the middle of phase A, once per chopper period, at both rates");
        else $display("FAIL: tb_tick");
        $finish;
    end
endmodule
`default_nettype wire
