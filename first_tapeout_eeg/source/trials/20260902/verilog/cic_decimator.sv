// CIC sinc^3 decimator (OSR=64, 16 kHz -> 250 SPS) + 24-bit output register
// for the CT 1st-order 1-bit sigma-delta EEG ADC.
// Integrators run on the 16 kHz modulator clock; combs on the decimated clock.
// Output: 24-bit signed (two's complement), validated by data_valid pulse.
module cic_decimator #(
    parameter OSR = 64,
    parameter ACCW = 32           // integrator accumulator width
) (
    input  wire        clk,       // 16 kHz modulator clock
    input  wire        rst_n,
    input  wire        bit_in,    // 1-bit modulator stream
    output reg  [23:0] data_out,  // decimated sample (two's complement)
    output reg         data_valid
);
    // ---- integrators (16 kHz) ----
    reg [ACCW-1:0] i1, i2, i3;
    wire signed [ACCW-1:0] din = bit_in ? 32'sd1 : -32'sd1;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            i1 <= 0; i2 <= 0; i3 <= 0;
        end else begin
            i1 <= i1 + din;
            i2 <= i2 + i1;
            i3 <= i3 + i2;
        end
    end

    // ---- decimation strobe ----
    reg [6:0] dec_cnt;
    wire dec_stb = (dec_cnt == OSR-1);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) dec_cnt <= 0;
        else        dec_cnt <= dec_stb ? 7'd0 : dec_cnt + 7'd1;
    end

    // ---- combs (decimated rate) ----
    reg [ACCW-1:0] c0, c1d, c2d1, c3d1;
    reg [ACCW-1:0] y1, y2, y3;
    function automatic [23:0] scaled24(input [ACCW-1:0] v);
        reg signed [ACCW-1:0] s;
        begin
            s = v <<< 4;              // +-2^18 -> +-2^22
            scaled24 = s[ACCW-1 -: 24];
        end
    endfunction
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            c0 <= 0; c1d <= 0; c2d1 <= 0; c3d1 <= 0;
            y1 <= 0; y2 <= 0; y3 <= 0;
            data_out <= 24'sd0; data_valid <= 1'b0;
        end else begin
            data_valid <= 1'b0;
            if (dec_stb) begin
                c0  <= i3;
                // comb 1: y1 = c0 - c0 delayed
                y1  <= c0 - c1d;  c1d <= c0;
                // comb 2
                y2  <= y1 - c2d1; c2d1 <= y1;
                // comb 3
                y3  <= y2 - c3d1; c3d1 <= y2;
                // scale: |y3| <= OSR^3 = 2^18 at full-scale duty; map to 24-bit
                // with one bit of headroom (x16 -> +-2^22)
                data_out <= scaled24(y3);
                data_valid <= 1'b1;
            end
        end
    end
endmodule
