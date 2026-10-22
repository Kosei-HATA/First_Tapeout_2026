// eeg_fifo - sample FIFO between the CIC and the SPI slave.
//
// DEPTH = 8 entries of {status[7:0], seq[15:0], data[23:0]} (48 bits).
//
// Write side:
//   * seq counts every valid CIC output since reset or FILTER_CLEAR
//     (smp_stb), whether it is stored or not (RUN = 0 or FIFO full). The first
//     valid output after a clear gets seq = 0. Gaps in seq show the MCU how
//     many samples were not delivered.
//   * a valid output is written when run = 1. If the FIFO is full the new
//     sample is dropped (old data is never overwritten) and ovr_set pulses
//     (sets the sticky OVERRUN flag in eeg_regs). A write into a full FIFO is
//     accepted only when an entry is popped in the same cycle.
//   * stored status = {VALID=1, OVERRUN flag at write time, SETTLING=0, 5'b0}.
//     OVERRUN in a stored entry therefore marks samples written while the
//     sticky flag was set (i.e. after a drop, until the MCU clears it).
// Read side:
//   * rd_word is the head entry, or, when the FIFO is empty, the empty word
//     {VALID=0, OVERRUN flag, SETTLING, 5'b0, seq=0, data=0}.
//   * pop removes the head entry (ignored when empty).
//   * nonempty is a registered flag (glitch free, drives DRDY_N).
`timescale 1ns / 1ps
`default_nettype none

module eeg_fifo #(
    parameter int DEPTH = 8                    // power of two
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        clear_seq,             // FILTER_CLEAR: restart seq at 0
    // producer side (CIC)
    input  logic        smp_stb,               // valid CIC output (one-cycle pulse)
    input  logic [23:0] smp_data,
    input  logic        run,                   // CONTROL.RUN: store samples
    input  logic        ovr_flag,              // current sticky OVERRUN flag
    input  logic        settling,              // current CIC settling state
    output logic        ovr_set,               // pulse: sample dropped (FIFO full)
    // consumer side (SPI)
    input  logic        pop,
    output logic [47:0] rd_word,               // {status, seq, data}
    output logic        nonempty,              // registered
    output logic [3:0]  level                  // number of stored entries 0..DEPTH
);

    localparam int AW = $clog2(DEPTH);
    localparam logic [3:0] LEVEL_FULL = DEPTH;

    logic [47:0]   mem [0:DEPTH-1];
    logic [AW-1:0] wr_ptr;
    logic [AW-1:0] rd_ptr;
    logic [15:0]   seq;

    logic          push_req;                   // a sample wants to be stored
    logic          pop_ok;                     // an entry is removed
    logic          push_ok;                    // a sample is stored
    logic [3:0]    level_nxt;
    logic [7:0]    wr_status;

    assign push_req  = smp_stb && run;
    assign pop_ok    = pop && (level != 4'd0);
    assign push_ok   = push_req && ((level != LEVEL_FULL) || pop_ok);
    assign level_nxt = level + {3'b000, push_ok} - {3'b000, pop_ok};
    assign wr_status = {1'b1, ovr_flag, 1'b0, 5'b00000};

    // storage (no reset needed: an entry is only read after it was written)
    always_ff @(posedge clk) begin
        if (push_ok) begin
            mem[wr_ptr] <= {wr_status, seq, smp_data};
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr   <= '0;
            rd_ptr   <= '0;
            level    <= '0;
            nonempty <= 1'b0;
            seq      <= '0;
            ovr_set  <= 1'b0;
        end else begin
            if (push_ok) begin
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (pop_ok) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
            level    <= level_nxt;
            nonempty <= (level_nxt != 4'd0);
            ovr_set  <= push_req && !push_ok;
            if (clear_seq) begin
                seq <= '0;
            end else if (smp_stb) begin
                seq <= seq + 1'b1;
            end
        end
    end

    assign rd_word = (level == 4'd0) ? {1'b0, ovr_flag, settling, 5'b00000, 16'h0000, 24'h000000}
                                     : mem[rd_ptr];

endmodule

`default_nettype wire
