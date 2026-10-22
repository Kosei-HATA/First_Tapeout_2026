// eeg_raw - debug serializer for the raw quantizer codes.
//
// When RAW_EN = 1, one 8-bit word per modulator frame is shifted out MSB first
// on raw_data, 4 MCLK cycles per bit (8.192 Mbit/s, 32 MCLK = 1 frame):
//     word = {3'b101, c[4:0]}
// The constant 101 prefix lets the receiver find the word boundary.
// c is the code captured in the previous frame (the word is loaded at the
// frame boundary, edge e0, when the code of the frame that is ending is stable).
//
// Output timing (both outputs are registered, retimed by one MCLK cycle from
// the frame grid; e_n = rising MCLK edge that starts frame cycle n):
//   raw_data changes at e1, e5, ..., e29   (bit 7 first)
//   raw_clk_o rises  at e3, e7, ..., e31   (receiver samples on the rising edge)
//   -> 2 MCLK (61 ns) setup and 2 MCLK hold at the receiver.
// RAW_EN is sampled at frame boundaries only, so words are never cut. When
// disabled raw_data = 0 and raw_clk_o = 0 (the 8 MHz pad output is quiet).
`timescale 1ns / 1ps
`default_nettype none

module eeg_raw (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       raw_en,       // CONTROL.RAW_EN
    input  logic [4:0] cycle,        // frame cycle from eeg_clkgen
    input  logic       raw_clk,      // free-running MCLK/4 from eeg_clkgen
    input  logic [4:0] code,         // quantizer code c (stable from cycle 2 to cycle 1 of the next frame)
    output logic       raw_data_o,   // pad RAW_DATA
    output logic       raw_clk_o     // pad RAW_CLK
);

    logic       on;                  // serializer active for the current frame
    logic [7:0] sh;                  // output shift register, MSB first

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            on         <= 1'b0;
            sh         <= 8'h00;
            raw_data_o <= 1'b0;
            raw_clk_o  <= 1'b0;
        end else begin
            if (cycle == 5'd31) begin
                // frame boundary: load the next word (or zeros when disabled)
                on <= raw_en;
                sh <= raw_en ? {3'b101, code} : 8'h00;
            end else if (cycle[1:0] == 2'b11) begin
                // next bit every 4 MCLK cycles (at e4, e8, ..., e28)
                sh <= {sh[6:0], 1'b0};
            end
            raw_data_o <= sh[7];
            raw_clk_o  <= on & raw_clk;
        end
    end

endmodule

`default_nettype wire
