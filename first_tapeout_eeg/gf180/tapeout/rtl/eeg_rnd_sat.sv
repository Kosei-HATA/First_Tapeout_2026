// eeg_rnd_sat - round-half-to-even arithmetic right shift, then saturation.
//
// dout = sat_WO( round_half_even( din / 2^SH ) )
//
// All vectors are two's complement; the arithmetic is written with plain
// (unsigned) vectors and explicit sign extension so that no signed/unsigned
// mixing rules are involved.
//   q  = floor(din / 2^SH)     (= din[WI-1:SH], an arithmetic shift)
//   r  = din mod 2^SH          (= din[SH-1:0], 0 .. 2^SH-1)
//   round up when r > 2^(SH-1), or r == 2^(SH-1) and q is odd (ties to even)
// Saturation: if the rounded value does not fit in WO bits it is replaced by
// the most positive / most negative WO-bit value.
//
// Helper of eeg_cic3 (kept as a separate module so it can be tested
// exhaustively at its boundaries, including saturation, which the CIC itself
// never reaches with legal inputs).
`timescale 1ns / 1ps
`default_nettype none

module eeg_rnd_sat #(
    parameter int WI = 37,                // input width
    parameter int SH = 12,                // right shift
    parameter int WO = 24                 // output width
) (
    input  logic [WI-1:0] din,
    output logic [WO-1:0] dout
);

    localparam int WQ = WI - SH;          // width of the shifted value (25)

    localparam logic [SH-1:0] HALF   = {1'b1, {(SH - 1){1'b0}}};
    localparam logic [WO-1:0] MAXPOS = {1'b0, {(WO - 1){1'b1}}};
    localparam logic [WO-1:0] MAXNEG = {1'b1, {(WO - 1){1'b0}}};

    logic [WQ-1:0]      q;                // floor(din / 2^SH)
    logic [SH-1:0]      r;                // remainder
    logic               up;               // round up by one
    logic [WQ:0]        qr;               // rounded value, one guard bit
    logic [WQ-WO+1:0]   top;              // bits that must be a sign extension
    logic               fits;             // qr fits in WO bits

    assign q    = din[WI-1:SH];
    assign r    = din[SH-1:0];
    assign up   = (r > HALF) || ((r == HALF) && q[0]);
    assign qr   = {q[WQ-1], q} + {{WQ{1'b0}}, up};
    assign top  = qr[WQ:WO-1];
    assign fits = (top == {(WQ - WO + 2){1'b0}}) || (top == {(WQ - WO + 2){1'b1}});
    assign dout = fits ? qr[WO-1:0] : (qr[WQ] ? MAXNEG : MAXPOS);

endmodule

`default_nettype wire
