// eeg_clkgen - frame timing generator for the GF180 EEG ADC digital block.
//
// MCLK = 32.768 MHz. One modulator frame = 32 MCLK cycles (fs = 1.024 MHz).
// A 9-bit free-running counter holds
//     cnt[8:5] : frame index inside a 512-MCLK chop superperiod (0..15)
//     cnt[4:0] : frame cycle (0..31)
//
// Timing convention used in the whole design:
//   * A strobe "at cycle k" is a registered signal that is high during the
//     MCLK cycle in which the frame cycle counter equals k.
//   * A register "updated at strobe X" uses X as clock enable, so it takes its
//     new value at the rising MCLK edge that ENDS cycle k.
//   Example (DAC_LOAD_CYCLE = 2): CMP_STROBE rises at edge e0, TH is captured
//   at edge e2, the DAC selection registers change at edge e3.
//
// Chopper (chop_fast = CONTROL.CHOP_FAST):
//   chop_fast = 1: chop = ~cnt[7], toggles every 128 MCLK (128 kHz),
//                  edges at e0 of every 4th frame
//   chop_fast = 0: chop = ~cnt[8], toggles every 256 MCLK (64 kHz),
//                  edges at e0 of every 8th frame
//   chop_fast is sampled only at the e0 where cnt wraps to 0 (every 16th
//   frame, 512 MCLK = 15.6 us). Both waveforms rise at that edge, so a rate
//   change never produces a runt or a stretched phase: the phase before the
//   switch is a full half period of the old rate and the phase after it a full
//   half period of the new rate. (At cnt = 0x100, the other point where both
//   waveforms have an edge, 64 kHz falls while 128 kHz rises; switching there
//   would drop one edge and leave a 384-MCLK phase.)
//
// chop_out(t) = chop(t - d) with d = chop_dly (0..255), exactly, also across
// a rate change: it is the chop waveform evaluated at counter value (cnt - d)
// with the rate of the superperiod that contained t - d. That is the current
// superperiod if cnt >= d, otherwise the previous one (d < 512), so the rate
// of the previous superperiod is kept. Before reset release chop was 0, and
// chop_out stays 0 until d cycles after the first chop edge. chop_out uses
// chop_dly registered once more (dly_q, reset 0 like the CHOP_DLY register),
// so a new delay applies one MCLK after it appears on chop_dly. Changing the
// delay while running moves chop_out to the new delay at once (one short
// phase is possible); set CHOP_DLY while AFE_RST = 1 if that matters.
//
// chop_blank (output-chopper blanking): rises at the MCLK edge one cycle
// BEFORE each chop_out edge (both directions, both rates) and stays high for
// blank_len + 1 cycles, so the output-chopper phases gated with ~chop_blank
// are already off when chop_out toggles and stay off for exactly blank_len
// cycles after it. The chop_out edge is known one cycle ahead: chop_out_nxt2
// is chop_out one edge after the next, computed with the same counter and
// rate logic and with the delay that dly_q will hold then (chop_dly), so the
// prediction is exact, also for the jump after a CHOP_DLY change. A chop_fast
// change at a wrap cannot spoil it, because chop_out at counter 0 does not
// depend on the new rate. It follows chop_out, so CHOP_DLY delays the
// blanking together with the output chopper. The length is latched when the
// pulse starts: a blank_len change takes effect at the next pulse and never
// shortens or stretches a pulse in progress. blank_len = 0 starts no pulse.
// A predicted chop_out edge during a pulse (only possible right after a
// CHOP_DLY change) restarts it with the current blank_len, or lets it finish
// if blank_len = 0. Exception: the chop_out edge at the first MCLK edge after
// reset release (chop_dly = 0) is not blanked, because the cycle before it is
// still in reset; the AFE is held in reset (AFE_RST = 1) at that time.
//
// Reset: the counter resets to 9'h1FF (cycle 31 of the last frame of a
// superperiod), so the first MCLK edge after reset release starts frame 0 at
// cycle 0 and is also the first chop edge (chop rises there, at the rate set
// by chop_fast). No strobe is active and chop/chop_out/chop_blank are 0
// during reset.
`timescale 1ns / 1ps
`default_nettype none

module eeg_clkgen #(
    parameter int DAC_LOAD_CYCLE = 2      // legal range 2..31 (must be after th_capture)
) (
    input  logic       clk,               // MCLK
    input  logic       rst_n,             // synchronized reset, active low
    input  logic       chop_fast,         // 1: 128 kHz chop, 0: 64 kHz chop
    input  logic [7:0] chop_dly,          // chop_out delay in MCLK cycles (0..255)
    input  logic [3:0] blank_len,         // chop_blank width in MCLK cycles, 0 = off
    output logic [4:0] cycle,             // current frame cycle 0..31
    output logic       cmp_strobe,        // cycle 0: comparator clock for the quantizer
    output logic       th_capture,        // cycle 1: TH[30:0] is sampled at the end of this cycle
    output logic       dac_load,          // cycle DAC_LOAD_CYCLE: DAC selections update at its end
    output logic       cic_en,            // cycle 3: one CIC input sample per frame
    output logic       chop,              // 128 or 64 kHz chopper clock
    output logic       chop_out,          // chop delayed by chop_dly MCLK cycles
    output logic       chop_blank,        // from 1 MCLK before each chop_out edge to blank_len MCLK after it
    output logic       raw_clk            // MCLK/4 = 8.192 MHz, free running
);

    localparam logic [4:0] DLC = DAC_LOAD_CYCLE;

    logic [8:0] cnt;
    logic       fast;                     // chop rate of the current superperiod
    logic       fast_prev;                // chop rate of the previous superperiod
    logic       live;                     // the current superperiod started after reset
    logic       live_prev;                // the previous superperiod started after reset

    logic [8:0] cnt_nxt;
    logic       wrap;                     // the next edge starts a new superperiod
    logic       fast_nxt;
    logic       fast_prev_nxt;
    logic       live_nxt;
    logic       live_prev_nxt;
    logic [8:0] dly_cnt_nxt;              // counter value at (next time - chop_dly)
    logic       dly_in_cur;               // that time lies in the same superperiod
    logic       dly_fast;                 // rate at that time
    logic       dly_live;                 // that time is after reset release
    logic       chop_out_nxt;             // chop_out after the next edge
    logic [7:0] dly_q;                    // chop_dly delayed by one MCLK (used by chop_out)

    // one edge further: chop_out after the edge after the next one
    logic [8:0] cnt_nxt2;
    logic       wrap2;
    logic       fast_nxt2;
    logic       fast_prev_nxt2;
    logic       live_nxt2;
    logic       live_prev_nxt2;
    logic [8:0] dly2_cnt;
    logic       dly2_in_cur;
    logic       dly2_fast;
    logic       dly2_live;
    logic       chop_out_nxt2;
    logic       out_edge_ahead;           // chop_out toggles at the edge after the next one
    logic [3:0] blank_rem;                // chop_blank cycles left after the current one

    // chop waveform from a counter value: high in the first half of each period
    function automatic logic chop_wave(input logic [8:0] c, input logic f);
        chop_wave = f ? ~c[7] : ~c[8];
    endfunction

    assign cnt_nxt       = cnt + 9'd1;
    assign wrap          = (cnt_nxt == 9'd0);
    assign fast_nxt      = wrap ? chop_fast : fast;
    assign fast_prev_nxt = wrap ? fast : fast_prev;
    assign live_nxt      = wrap ? 1'b1 : live;
    assign live_prev_nxt = wrap ? live : live_prev;

    assign dly_cnt_nxt = cnt_nxt - {1'b0, dly_q};
    assign dly_in_cur  = (cnt_nxt >= {1'b0, dly_q});
    assign dly_fast    = dly_in_cur ? fast_nxt : fast_prev_nxt;
    assign dly_live    = dly_in_cur ? live_nxt : live_prev_nxt;

    assign chop_out_nxt = dly_live & chop_wave(dly_cnt_nxt, dly_fast);

    // Same computation one edge later. dly_q takes chop_dly at the next edge,
    // so chop_dly is the delay that will be used then. If the edge after the
    // next one is a wrap, chop_fast is only a guess of the new rate, but the
    // result does not depend on it (both rates give chop = 1 at counter 0, and
    // with a nonzero delay the previous superperiod's rate is used).
    assign cnt_nxt2       = cnt + 9'd2;
    assign wrap2          = (cnt_nxt2 == 9'd0);
    assign fast_nxt2      = wrap2 ? chop_fast : fast_nxt;
    assign fast_prev_nxt2 = wrap2 ? fast_nxt : fast_prev_nxt;
    assign live_nxt2      = wrap2 ? 1'b1 : live_nxt;
    assign live_prev_nxt2 = wrap2 ? live_nxt : live_prev_nxt;

    assign dly2_cnt       = cnt_nxt2 - {1'b0, chop_dly};
    assign dly2_in_cur    = (cnt_nxt2 >= {1'b0, chop_dly});
    assign dly2_fast      = dly2_in_cur ? fast_nxt2 : fast_prev_nxt2;
    assign dly2_live      = dly2_in_cur ? live_nxt2 : live_prev_nxt2;
    assign chop_out_nxt2  = dly2_live & chop_wave(dly2_cnt, dly2_fast);
    assign out_edge_ahead = (chop_out_nxt2 != chop_out_nxt);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cnt        <= 9'h1FF;
            fast       <= 1'b1;
            fast_prev  <= 1'b1;
            live       <= 1'b0;
            live_prev  <= 1'b0;
            cmp_strobe <= 1'b0;
            th_capture <= 1'b0;
            dac_load   <= 1'b0;
            cic_en     <= 1'b0;
            chop       <= 1'b0;
            chop_out   <= 1'b0;
            chop_blank <= 1'b0;
            blank_rem  <= 4'd0;
            dly_q      <= 8'd0;
        end else begin
            cnt        <= cnt_nxt;
            fast       <= fast_nxt;
            fast_prev  <= fast_prev_nxt;
            live       <= live_nxt;
            live_prev  <= live_prev_nxt;
            // strobes and chop outputs are computed from the next state so that
            // each registered output matches the counter value it belongs to
            cmp_strobe <= (cnt_nxt[4:0] == 5'd0);
            th_capture <= (cnt_nxt[4:0] == 5'd1);
            dac_load   <= (cnt_nxt[4:0] == DLC);
            cic_en     <= (cnt_nxt[4:0] == 5'd3);
            chop       <= chop_wave(cnt_nxt, fast_nxt);
            chop_out   <= chop_out_nxt;
            dly_q      <= chop_dly;
            // blanking pulse: starts one cycle before the chop_out edge and
            // lasts blank_len + 1 cycles; length latched at the start
            if (out_edge_ahead && (blank_len != 4'd0)) begin
                chop_blank <= 1'b1;
                blank_rem  <= blank_len;
            end else if (chop_blank) begin
                if (blank_rem == 4'd0) begin
                    chop_blank <= 1'b0;
                end else begin
                    blank_rem <= blank_rem - 4'd1;
                end
            end
        end
    end

    // These outputs are counter flip-flops (registered, glitch free).
    assign cycle   = cnt[4:0];
    assign raw_clk = cnt[1];      // high in cycles 2,3, 6,7, ... ; falls at cycles 0,4,8,...

endmodule

`default_nettype wire
