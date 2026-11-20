// eeg_ovl - ADC overload detection (r14; gf180/tapeout/rtl/spec/regmap.py OVL_RULE, spec section 5).
//
// The quantizer code of each frame (taken with the CIC input, en = cic_en) is an extreme when it is 0 or 31. A
// 32-frame window of those flags and its count give ovl_now = (count >= OVL_THRESHOLD). The full-scale behavioural
// streams never reach an extreme (codes 3..27); an AFE or ADC overload pins the integrators and the codes at the
// extremes. ovl_seen: a hit (an extreme code taken while the rule holds, counting it) since the previous output
// time (for the sample's status byte; audit round 8: the meaning since round 6).
`timescale 1ns / 1ps
`default_nettype none

module eeg_ovl (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       en,            // one per frame, with the CIC input
    input  logic [4:0] code,
    input  logic       out_stb,       // a CIC output time: ovl_seen restarts after it
    output logic       ovl_now,       // the detector: >= OVL_THRESHOLD extreme codes among the last OVL_WINDOW frames
    output logic       ovl_hit,       // this frame (en) is an extreme code taken while the detector holds (counting it)
    output logic       ovl_seen       // a hit since the last output time (this output interval)
);

`include "eeg_regs_defs.svh"

    logic [OVL_WINDOW-1:0] win;
    logic [5:0]            cnt, cnt_nxt;
    logic                  ext;

    // An interval (and DFLAG.OVL) is marked only for an extreme code taken during a detected overload: the window's
    // count stays high up to OVL_WINDOW - OVL_THRESHOLD frames (28) after the last extreme code (until the last
    // OVL_THRESHOLD of them leave the window; audit round 8: was 'OVL_WINDOW - 1'), and an interval that starts in that
    // tail holds no overloaded frame (audit round 6, 11/20: it marked a fourth sample, and a tail from ALIGN set
    // DFLAG.OVL in FILL). The first OVL_THRESHOLD - 1 codes of an overload are not hits (the detection lag, as before)
    assign ext     = (code == 5'd0) || (code == 5'd31);
    assign cnt_nxt = cnt + {5'd0, ext} - {5'd0, win[OVL_WINDOW-1]};
    assign ovl_now = (cnt >= OVL_THRESHOLD);
    assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            win      <= '0;
            cnt      <= '0;
            ovl_seen <= 1'b0;
        end else begin
            if (en) begin
                win <= {win[OVL_WINDOW-2:0], ext};
                cnt <= cnt_nxt;
            end
            if (out_stb)      ovl_seen <= 1'b0;        // en (cycle 3) and out_stb (cycle 8) never share a cycle
            else if (ovl_hit) ovl_seen <= 1'b1;
        end
    end

endmodule

`default_nettype wire
