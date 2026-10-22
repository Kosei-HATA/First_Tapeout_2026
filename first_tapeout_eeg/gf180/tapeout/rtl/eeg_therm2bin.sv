// eeg_therm2bin - thermometer-to-binary conversion for the 5-bit flash quantizer.
//
// code = popcount(th). Counting ones instead of locating the 0/1 boundary makes
// the conversion bubble tolerant by construction: a bubble (an isolated wrong
// comparator) changes the code by at most one LSB per wrong bit.
//
// The count is built as a balanced adder tree (31 -> 16 x 2b -> 8 x 3b ->
// 4 x 4b -> 2 x 5b -> 5b) to keep the logic depth low; this block is part of
// the th_q -> SEL path that must settle within one MCLK cycle when
// DAC_LOAD_CYCLE = 2. Each tree level is a flat vector of equal-width fields.
`timescale 1ns / 1ps
`default_nettype none

module eeg_therm2bin (
    input  logic [30:0] th,       // comparator outputs, th[i] = 1 above threshold i
    output logic [4:0]  code      // number of ones, 0..31
);

    logic [31:0] t;               // th padded to 32 bits (t[31] = 0)
    logic [31:0] l1;              // 16 fields of 2 bits: sums of 2 bits
    logic [23:0] l2;              // 8 fields of 3 bits: sums of 4 bits
    logic [15:0] l3;              // 4 fields of 4 bits: sums of 8 bits
    logic [9:0]  l4;              // 2 fields of 5 bits: sums of 16 bits

    assign t = {1'b0, th};

    // The left-hand side width sets the addition width, so carries are kept.
    genvar i;
    for (i = 0; i < 16; i = i + 1) begin : g_l1
        assign l1[2*i +: 2] = t[2*i] + t[2*i+1];
    end
    for (i = 0; i < 8; i = i + 1) begin : g_l2
        assign l2[3*i +: 3] = l1[4*i +: 2] + l1[4*i+2 +: 2];
    end
    for (i = 0; i < 4; i = i + 1) begin : g_l3
        assign l3[4*i +: 4] = l2[6*i +: 3] + l2[6*i+3 +: 3];
    end
    for (i = 0; i < 2; i = i + 1) begin : g_l4
        assign l4[5*i +: 5] = l3[8*i +: 4] + l3[8*i+4 +: 4];
    end

    // At most 31 ones, so the final sum fits in 5 bits.
    assign code = l4[4:0] + l4[9:5];

endmodule

`default_nettype wire
