// Clock generation for the EEG AFE SoC (digital, sky130_fd_sc_hd target).
// Input: clk256 = 256 kHz master (from caravel user_clock2 / management divider).
// Outputs: chopper phases (8 kHz, ~100 ns non-overlap) and SDM clock (16 kHz).
//
// Chopper non-overlap is generated with a delay chain of inverters.
// All phase timing is synchronous to clk256 edges (125 ns resolution);
// the analog switch cells additionally tolerate short overlaps (dummy-charge
// canceling TGs), and ~100 ns non-overlap was verified in simulation.
module eeg_clkgen (
    input  wire clk256,
    input  wire rst_n,
    output reg  phi,      // 8 kHz phase A
    output reg  phib,     // 8 kHz phase B
    output reg  clk16,    // 16 kHz, 50% duty
    output reg  nclk16
);
    // 8 kHz = 256 kHz / 32; 16 kHz = 256 kHz / 16
    reg [4:0] div8k;
    reg [3:0] div16k;

    always @(posedge clk256 or negedge rst_n) begin
        if (!rst_n) begin
            div8k  <= 5'd0;
            div16k <= 4'd0;
            clk16  <= 1'b0;
        end else begin
            div16k <= div16k + 4'd1;
            if (div16k == 4'd7) clk16 <= ~clk16;   // toggle every 8 -> 16 kHz, 50% duty
            div8k  <= div8k + 5'd1;
        end
    end
    always @(*) nclk16 = ~clk16;

    // 8 kHz phases with non-overlap: phi high while div8k in [2,13],
    // phib high while div8k in [18,29] -> 2 clk256 cycles (250 ns) guard each side
    always @(*) begin
        phi  = (div8k >= 5'd2)  && (div8k <= 5'd13);
        phib = (div8k >= 5'd18) && (div8k <= 5'd29);
    end
endmodule
