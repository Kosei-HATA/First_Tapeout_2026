// eeg_fifo - sample FIFO between the CIC and the SPI slave (r14).
//
// DEPTH entries of {status[7:0], seq[15:0], data[23:0]} (48 bits); the status byte and SEQ are built by the top
// (gf180/tapeout/rtl/spec/regmap.py SAMPLE_STATUS; SEQ = the output's number since reset release).
// One MCLK cycle: flush, then pop, then push (gf180/tapeout/rtl/spec/fsm_spec.py fifo_step: a new sample is never
// lost to a flush or a pop in the same cycle). A push into a full FIFO without a pop in the same cycle drops the
// new sample and pulses ovr_set. Empty: rd_word = {empty_status, 16'h0, 24'h0}.
`timescale 1ns / 1ps
`default_nettype none

module eeg_fifo #(
    parameter int DEPTH = 8                       // power of two, 4 or 8
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        flush,                    // START / FLUSH (sequencer, at a tick)
    input  logic        push,                     // store this output (sequencer, at a CIC output time)
    input  logic [7:0]  status_in,
    input  logic [15:0] seq_in,
    input  logic [23:0] data_in,
    output logic        ovr_set,                  // the pushed sample was dropped (FIFO full)
    output logic        push_ok,                  // the pushed sample was stored
    input  logic        pop,                      // the SPI read the head entry (exactly 8 bytes)
    input  logic [7:0]  empty_status,             // status byte for an empty FIFO (VALID = 0)
    output logic [47:0] rd_word,
    output logic        nonempty,                 // registered
    output logic [3:0]  level
);

    localparam int AW = $clog2(DEPTH);
    localparam logic [3:0] LEVEL_FULL = DEPTH;

    logic [47:0]   mem [0:DEPTH-1];
    logic [AW-1:0] wr_ptr, rd_ptr;
    logic          pop_ok;
    logic [3:0]    lvl0, level_nxt;

    assign pop_ok    = pop && (level != 4'd0) && !flush;
    assign lvl0      = flush ? 4'd0 : (level - {3'd0, pop_ok});
    assign push_ok   = push && (lvl0 != LEVEL_FULL);
    assign level_nxt = lvl0 + {3'd0, push_ok};

    always_ff @(posedge clk) begin
        if (push_ok) begin
            mem[wr_ptr] <= {status_in, seq_in, data_in};
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr   <= '0;
            rd_ptr   <= '0;
            level    <= '0;
            nonempty <= 1'b0;
            ovr_set  <= 1'b0;
        end else begin
            wr_ptr   <= wr_ptr + {{(AW-1){1'b0}}, push_ok};
            rd_ptr   <= flush ? wr_ptr : (rd_ptr + {{(AW-1){1'b0}}, pop_ok});
            level    <= level_nxt;
            nonempty <= (level_nxt != 4'd0);
            ovr_set  <= push && !push_ok;
        end
    end

    assign rd_word = (level == 4'd0) ? {empty_status, 16'h0000, 24'h000000} : mem[rd_ptr];

endmodule

`default_nettype wire
