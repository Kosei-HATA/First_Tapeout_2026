// eeg_cic3 - sinc^3 (CIC, 3 integrators + 3 combs, differential delay 1)
// decimator, 1.024 MHz -> 1 kSPS.
//
// Input : x = 2c - 31 (signed, odd values -31..31) once per en (cic_en).
// Width : all integrator and comb registers are W = 37 bits and wrap modulo
//         2^W; nothing saturates inside the filter. Gain R^3 = 2^30, so the
//         largest output 31 * 2^30 < 2^36 fits in the 37-bit signed range and
//         the Hogenauer wrap-around argument applies.
// Output: comb output rounded half-to-even after a right shift by SH = 12 and
//         saturated to 24 bits (eeg_rnd_sat). Full scale is +-31 * 2^18.
//
// Arithmetic (this is exactly what the golden model cic_golden.py does):
//   integrators, on every accepted input (all three use OLD register values,
//   i.e. the classic pipelined Hogenauer form; one adder per path):
//       i1 <= i1 + x;   i2 <= i2 + i1;   i3 <= i3 + i2;
//   on the R-th accepted input (counted since reset/clear) a decimation event
//   starts the comb pipeline, which runs one step per MCLK cycle using the
//   updated i3:
//       step 1: acc <= i3  - d1;  d1 <= i3;
//       step 2: acc <= acc - d2;  d2 <= acc;
//       step 3: acc <= acc - d3;  d3 <= acc;
//       step 4: dout <= rnd_sat(acc); dout_stb <= 1
//   dout_stb is therefore high 5 MCLK cycles after the en cycle of the R-th
//   input (frame cycle 8 for cic_en at cycle 3).
//
// Validity: the first NSKIP = 2 output strobes after reset or clear contain
// partially filled windows and are flagged invalid (dout_valid = 0); valid
// outputs start with the 3rd strobe (3072nd accepted input). settling is high
// until that first valid strobe.
//
// clear (FILTER_CLEAR) is synchronous and has priority: it resets every
// register of the filter, the decimation counter, the comb pipeline (an output
// still in the pipeline is discarded) and the strobe counter. An en in the same
// cycle as clear is not accepted.
`timescale 1ns / 1ps
`default_nettype none

module eeg_cic3 #(
    parameter int W     = 37,            // register width (modulo 2^W)
    parameter int R     = 1024,          // decimation ratio
    parameter int SH    = 12,            // output right shift
    parameter int WO    = 24,            // output width
    parameter int NSKIP = 2              // initial strobes flagged invalid
) (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          clear,         // synchronous filter clear (one cycle)
    input  logic          en,            // accept one input sample
    input  logic [4:0]    code,          // quantizer code c, 0..31
    output logic [WO-1:0] dout,          // two's complement output sample
    output logic          dout_stb,      // one-cycle pulse per decimated output
    output logic          dout_valid,    // qualifies dout_stb: output is valid
    output logic          settling       // high until the first valid output
);

    localparam int CW = $clog2(R);               // decimation counter width
    localparam int SW = $clog2(NSKIP + 2);       // strobe counter width
    localparam logic [CW-1:0] CNT_LAST = R - 1;
    localparam logic [SW-1:0] NSKIP_P  = NSKIP;
    localparam logic [SW-1:0] NSTB_MAX = NSKIP + 1;

    // x = 2c - 31 = (2c + 1) - 32, as a 6-bit two's complement value
    logic [5:0]   x6;
    logic [W-1:0] x;

    assign x6 = {1'b0, code, 1'b1} - 6'd32;
    assign x  = {{(W - 6){x6[5]}}, x6};

    logic [W-1:0]  i1, i2, i3;           // integrators
    logic [W-1:0]  d1, d2, d3;           // comb delay registers
    logic [W-1:0]  acc;                  // comb pipeline accumulator
    logic [CW-1:0] dcnt;                 // accepted inputs in the current period
    logic [3:0]    step;                 // one-hot comb pipeline token
    logic [SW-1:0] nstb;                 // output strobes since reset/clear (saturating)
    logic          dec;                  // this en completes a decimation period
    logic [WO-1:0] rounded;

    assign dec = en && (dcnt == CNT_LAST);

    eeg_rnd_sat #(.WI(W), .SH(SH), .WO(WO)) u_rnd_sat (
        .din  (acc),
        .dout (rounded)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            i1         <= '0;
            i2         <= '0;
            i3         <= '0;
            d1         <= '0;
            d2         <= '0;
            d3         <= '0;
            acc        <= '0;
            dcnt       <= '0;
            step       <= '0;
            nstb       <= '0;
            dout       <= '0;
            dout_stb   <= 1'b0;
            dout_valid <= 1'b0;
        end else if (clear) begin
            i1         <= '0;
            i2         <= '0;
            i3         <= '0;
            d1         <= '0;
            d2         <= '0;
            d3         <= '0;
            acc        <= '0;
            dcnt       <= '0;
            step       <= '0;
            nstb       <= '0;
            dout       <= '0;
            dout_stb   <= 1'b0;
            dout_valid <= 1'b0;
        end else begin
            // integrator section (input rate)
            if (en) begin
                i1   <= i1 + x;
                i2   <= i2 + i1;
                i3   <= i3 + i2;
                dcnt <= dec ? '0 : dcnt + 1'b1;
            end

            // comb section (one step per MCLK cycle after a decimation event)
            step <= {step[2:0], dec};
            if (step[0]) begin
                acc <= i3 - d1;
                d1  <= i3;
            end
            if (step[1]) begin
                acc <= acc - d2;
                d2  <= acc;
            end
            if (step[2]) begin
                acc <= acc - d3;
                d3  <= acc;
            end

            // output register
            dout_stb   <= step[3];
            dout_valid <= step[3] && (nstb >= NSKIP_P);
            if (step[3]) begin
                dout <= rounded;
                if (nstb != NSTB_MAX) begin
                    nstb <= nstb + 1'b1;
                end
            end
        end
    end

    assign settling = (nstb != NSTB_MAX);

endmodule

`default_nettype wire
