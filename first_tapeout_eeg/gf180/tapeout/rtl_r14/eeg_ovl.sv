// eeg_ovl - ADC overload detection (r14; gf180/tapeout/rtl/spec/regmap.py OVL_RULE, spec section 5).
//
// The quantizer code of each frame (taken with the CIC input, en = cic_en) is an extreme when it is 0 or 31. A
// 32-frame window of those flags and its count give ovl_now = (count >= OVL_THRESHOLD). The full-scale behavioural
// streams never reach an extreme (codes 3..27); an AFE or ADC overload pins the integrators and the codes at the
// extremes. ovl_seen: ovl_now was 1 at some frame since the previous output time (for the sample's status byte).
`timescale 1ns / 1ps
`default_nettype none

module eeg_ovl (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       en,            // one per frame, with the CIC input
    input  logic [4:0] code,
    input  logic       out_stb,       // a CIC output time: ovl_seen restarts after it
    output logic       ovl_now,
    output logic       ovl_seen
);

`include "eeg_regs_defs.svh"

    logic [OVL_WINDOW-1:0] win;
    logic [5:0]            cnt;
    logic                  ext;

    assign ext     = (code == 5'd0) || (code == 5'd31);
    assign ovl_now = (cnt >= OVL_THRESHOLD);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            win      <= '0;
            cnt      <= '0;
            ovl_seen <= 1'b0;
        end else begin
            if (en) begin
                win <= {win[OVL_WINDOW-2:0], ext};
                cnt <= cnt + {5'd0, ext} - {5'd0, win[OVL_WINDOW-1]};
            end
            if (out_stb)      ovl_seen <= ovl_now;     // the new period starts with the current state
            else if (ovl_now) ovl_seen <= 1'b1;
        end
    end

endmodule

`default_nettype wire
