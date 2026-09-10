// Clock generation for the EEG AFE SoC (digital, sky130_fd_sc_hd target).
// Input: clk256 = 256 kHz master (from caravel user_clock2 / management divider).
// Outputs: chopper phases (1 kHz, non-overlap) and SDM clock (16 kHz).
//
// Chop frequency choice (2026-09-05): 1 kHz. The chopped-Cf feedback gives an
// intrinsic high-pass corner fc ~ f_chop/(160xG/32); at 8 kHz fc ~ 5 Hz broke
// the 1-40 Hz optimized band (-22% at 8 Hz). At 1 kHz fc ~ 1.3 Hz, in-band
// noise is ~0.38 uVrms (spec 1.0), stage-2 flicker is better suppressed
// (A1(1k) >> A1(8k)), and the 1 kHz ripple lands on CIC decimator notches
// (integer multiples of the 250/500/1000 SPS output rates).
// The residual 1 Hz rolloff is cancelled by a positive-feedback capacitor
// (PFL) at the PGA input, so no demod phase trim is needed anymore.
module eeg_clkgen #(
    parameter [7:0] DEMOD_DELAY = 8'd0   // legacy; keep 0 (PFL replaced phase trim)
) (
    input  wire clk256,
    input  wire rst_n,
    output reg  phi,      // 1 kHz phase A (input mod chopper)
    output reg  phib,     // 1 kHz phase B
    output reg  phi_d,    // (delayed) phases for the demod chopper
    output reg  phib_d,
    output reg  clk16,    // 16 kHz, 50% duty
    output reg  nclk16
);
    // 1 kHz = 256 kHz / 256; 16 kHz = 256 kHz / 16
    reg [7:0] div1k;
    reg [3:0] div16k;

    always @(posedge clk256 or negedge rst_n) begin
        if (!rst_n) begin
            div1k  <= 8'd0;
            div16k <= 4'd0;
            clk16  <= 1'b0;
        end else begin
            div16k <= div16k + 4'd1;
            if (div16k == 4'd7) clk16 <= ~clk16;   // toggle every 8 -> 16 kHz, 50% duty
            div1k  <= div1k + 8'd1;
        end
    end
    always @(*) nclk16 = ~clk16;

    // 1 kHz phases with non-overlap: phi high while div1k in [2,125],
    // phib high while div1k in [130,253] -> 2 clk256 cycles (~7.8 us) guard
    always @(*) begin
        phi  = (div1k >= 8'd2)   && (div1k <= 8'd125);
        phib = (div1k >= 8'd130) && (div1k <= 8'd253);
    end

    // demod phases: same pattern, DEMOD_DELAY clocks later (wraps mod 256)
    wire [7:0] d1d = div1k + DEMOD_DELAY;   // wraps naturally (8-bit)
    always @(*) begin
        phi_d  = (d1d >= 8'd2)   && (d1d <= 8'd125);
        phib_d = (d1d >= 8'd130) && (d1d <= 8'd253);
    end
endmodule
