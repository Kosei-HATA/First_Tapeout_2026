// eeg_chop1 - chopper clock of the ADC's first integrator OTA (OTA1).
//
// CHOP1 = 1 is phase A (straight), 0 phase B (crossed); the analog driver makes
// the input-TG and drain-commutator phases from it.
//
// Each OTA1 chopper edge disturbs the first integrator by a charge proportional
// to the OTA1 output current at that moment, i.e. to the quantization error of
// the frame. Taken once per edge, that error folds the shaped quantization noise
// into the band, and its in-band level grows with the square root of the edge
// rate (documentation/gf180_ota1_chopper_20261022.md). So OTA1 is chopped slowly,
// at a few kHz, where its 1/f noise is still removed.
//
// Rate (chop1_rate, register CHOP1):
//   0     off: CHOP1 = 1 (phase A) all the time
//   1..5  1, 2, 4, 8, 16 kHz: CHOP1 toggles every 512, 256, 128, 64, 32 frames
//   6, 7  as 5 (16 kHz)
// Every period divides the CIC decimation ratio (1024 frames = 1 ms), so the
// chopped OTA1 offset is a zero-mean square wave that the CIC sums to zero.
//
// Timing: CHOP1 changes only at the MCLK edge that starts frame cycle 16 (e16),
// half a frame away from the comparator strobe (e0) and 13 MCLK after the DAC
// update (e3 with DAC_LOAD_CYCLE = 2).
//
// Phase: a frame counter fcnt (10 bits) increments at e0 and reads 0 in the
// first frame after reset release (the clock generator starts frame 0 at the
// first MCLK edge). CHOP1 = ~fcnt[10 - rate] from e16 of each frame, so it rises
// at e16 of every frame with fcnt = 0 at every rate.
//
// Rate changes: chop1_rate is sampled at e0 of the frames with fcnt = 0 (every
// 1024 frames). Every rate has a rising edge at e16 of that frame and a falling
// edge or no edge before it, so the phase before a change is a full half period
// of the old rate and the phase after it a full half period of the new rate.
// From or to off, the high phase is longer (off holds CHOP1 = 1). A new rate
// therefore applies within 1 ms.
//
// Reset: CHOP1 = 1, fcnt = 1023 (0 in frame 0), the sampled rate = 3 (4 kHz,
// the register reset value).
`timescale 1ns / 1ps
`default_nettype none

module eeg_chop1 (
    input  logic       clk,               // MCLK
    input  logic       rst_n,             // synchronized reset, active low
    input  logic [4:0] cycle,             // frame cycle from eeg_clkgen (0..31)
    input  logic [2:0] chop1_rate,        // CHOP1[2:0]
    output logic       chop1              // 1 = phase A
);

    logic [9:0] fcnt;
    logic [2:0] rate_q;
    logic [2:0] r;                        // effective rate 0..5
    logic       wave;

    assign r = (rate_q > 3'd5) ? 3'd5 : rate_q;

    always_comb begin
        case (r)
            3'd1:    wave = ~fcnt[9];
            3'd2:    wave = ~fcnt[8];
            3'd3:    wave = ~fcnt[7];
            3'd4:    wave = ~fcnt[6];
            3'd5:    wave = ~fcnt[5];
            default: wave = 1'b1;
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fcnt   <= 10'h3FF;
            rate_q <= 3'd3;
            chop1  <= 1'b1;
        end else begin
            if (cycle == 5'd31) begin     // this edge is e0 of the next frame
                fcnt <= fcnt + 10'd1;
                if (fcnt == 10'h3FF) begin
                    rate_q <= chop1_rate;
                end
            end
            if (cycle == 5'd15) begin     // this edge is e16
                chop1 <= wave;
            end
        end
    end

endmodule

`default_nettype wire
