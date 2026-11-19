// tb_fifo - eeg_fifo alone against the specification's FIFO model (audit round 2, 11/20; VER-09, DAT-07).
//
// Random flush, pop request, push and SPI copy (snap) in every combination in the same cycle, including a pop and a
// push into a full FIFO and a snap of the empty FIFO, with an identity on every pushed word (SEQ and DATA carry a
// running number). Every cycle is written to the trace (+trace=...): the inputs, the pushed identity, and after the
// edge push_ok, level, the copy-is-head flag (held), the head's identity (or -1 for the empty word, whose status
// must be empty_status), ovr_set and nonempty. tb/check_fifo_trace.py replays the trace through
// gf180/tapeout/rtl/spec/fsm_spec.fifo_step and an independent identity model (which word the SPI copied, which word
// a pop removes) and compares every field. Define DEPTH4 for the 4-deep FIFO.
`timescale 1ns / 1ps
`default_nettype none

module tb_fifo;
`ifdef DEPTH4
    localparam int D = 4;
`else
    localparam int D = 8;
`endif
    logic        clk = 1'b0, rst_n = 1'b0;
    logic        flush = 1'b0, push = 1'b0, pop = 1'b0, snap = 1'b0;
    logic [7:0]  status_in = 8'h80;
    logic [15:0] seq_in = '0;
    logic [23:0] data_in = '0;
    wire         ovr_set, push_ok, nonempty;
    wire  [47:0] rd_word;
    wire  [3:0]  level;
    localparam logic [7:0] EMPTY = 8'h5A;

    eeg_fifo #(.DEPTH(D)) dut (.clk, .rst_n, .flush, .push, .status_in, .seq_in, .data_in, .ovr_set, .push_ok,
                               .snap, .pop, .empty_status(EMPTY), .rd_word, .nonempty, .level);

    always #15.26 clk = ~clk;

    // push_ok is combinational in the cycle of the push: sampled at the edge that ends the cycle
    logic push_ok_q = 1'b0;
    always @(posedge clk) push_ok_q <= push_ok;

    integer fd, n, seed, i, id, errors, pfull_pop_push;
    string  path;
    initial begin
        if (!$value$plusargs("n=%d", n)) n = 400000;
        if (!$value$plusargs("seed=%d", seed)) seed = 3;
        if (!$value$plusargs("trace=%s", path)) path = "build/fifo_trace.txt";
        fd = $fopen(path, "w");
        $fdisplay(fd, "D %0d", D);
        errors = 0;
        pfull_pop_push = 0;
        id = 0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        for (i = 0; i < n; i++) begin
            @(negedge clk);
            // biased draws: long fill phases (push-heavy) and drain phases (pop-heavy), occasional flushes
            push  = ($urandom(seed) % 100) < ((i / 2000) % 2 ? 70 : 25);
            pop   = ($urandom(seed) % 100) < ((i / 2000) % 2 ? 25 : 60);
            flush = ($urandom(seed) % 100) < 3;
            snap  = ($urandom(seed) % 100) < 35;
            id    = id + 1;
            seq_in  = 16'(id);
            data_in = 24'(id >> 16);
            if (pop && push && !flush && dut.held && level == 4'(D)) pfull_pop_push = pfull_pop_push + 1;
            @(posedge clk);
            #0.1;
            // inputs of this cycle, then the state after its edge
            $fdisplay(fd, "%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d", push, pop, flush, snap, id,
                      push_ok_q, level, dut.held, (level == 4'd0) ? -1 : int'({rd_word[23:0], rd_word[39:24]} & 32'hFFFFFFFF),
                      ovr_set, nonempty, (level == 4'd0) ? int'(rd_word[47:40]) : 0);
        end
        $fclose(fd);
        $display("tb_fifo (depth %0d): %0d cycles, %0d pops with a push into a full FIFO", D, n, pfull_pop_push);
        if (pfull_pop_push == 0) begin
            $display("FAIL: a pop with a push into a full FIFO never occurred");
        end else begin
            $display("PASS: tb_fifo stimulus (the trace is checked by check_fifo_trace.py)");
        end
        $finish;
    end

endmodule

`default_nettype wire
