// tb_chop1 - OTA1 chopper clock (eeg_chop1) driven by the frame timing of eeg_clkgen.
//
// Every MCLK cycle (sampled at the falling edge) chop1 is compared with a reference
// built from a count of MCLK edges since reset release (independent of the DUT
// counters): frame F = n / 32; the rate of frame F is the chop1_rate input at e0 of
// frame 1024 * floor(F / 1024); from e16 of frame F, chop1 = 1 for rate 0 and
// ~bit (10 - r) of (F mod 1024) for rate r = 1..5 (6 and 7 act as 5).
// Independent checks: chop1 = 1 during reset and up to e16 of frame 0; every chop1
// edge is at an e16; every phase with the same nonzero rate at both of its edges
// lasts exactly 32 * 2^(10 - r) MCLK; the rate sampled after a change is the value
// at the 1 ms boundary, also for changes one cycle before or after it.
// Sequence: reset rate 3 (4 kHz), then 5, 1, 0, 6, 7, 2, 4 and 3 again, written at
// unaligned times and once in the cycle right before and right after a boundary.
`timescale 1ns / 1ps

module tb_chop1;

    localparam real TMCLK = 30.5176;           // 32.768 MHz

    logic       clk = 1'b0;
    logic       rst_n = 1'b0;
    logic [2:0] rate = 3'd3;
    logic [4:0] cycle;
    logic       cmp, thc, dl, cic, chop, chop_out, blank, raw;
    logic       chop1;

    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) u_clkgen (
        .clk (clk), .rst_n (rst_n), .chop_fast (1'b1), .chop_dly (8'd0), .blank_len (4'd7),
        .cycle (cycle), .cmp_strobe (cmp), .th_capture (thc), .dac_load (dl), .cic_en (cic),
        .chop (chop), .chop_out (chop_out), .chop_blank (blank), .raw_clk (raw)
    );

    eeg_chop1 dut (
        .clk (clk), .rst_n (rst_n), .cycle (cycle), .chop1_rate (rate), .chop1 (chop1)
    );

    always #(TMCLK / 2.0) clk = ~clk;

    integer errors = 0;
    integer n = 0;                             // rising edges since reset release
    integer rate_blk = 3;                      // rate of the current 1024-frame block (reference)
    logic   exp_chop1 = 1'b1;
    logic   prev = 1'b1;
    integer last_edge = -1;                    // n at the last chop1 edge
    integer last_edge_rate = -1;               // block rate at that edge
    integer phases = 0;
    integer edges = 0;
    integer edges_at_rate [0:5];

    task automatic err(input string msg);
        begin
            errors = errors + 1;
            if (errors <= 20) $display("ERROR t=%0t n=%0d: %s", $time, n, msg);
        end
    endtask

    function automatic integer eff(input integer r);
        eff = (r > 5) ? 5 : r;
    endfunction

    // reference: updated at every rising edge after reset release with the inputs the
    // DUT saw at that edge (the testbench changes rate at falling edges)
    always @(posedge clk) begin
        if (rst_n) begin
            // this edge starts cycle n % 32 of frame n / 32
            if ((n % 32) == 0 && ((n / 32) % 1024) == 0) rate_blk = rate;
            if ((n % 32) == 16) begin
                if (eff(rate_blk) == 0) exp_chop1 = 1'b1;
                else exp_chop1 = ~(((n / 32) % 1024) >> (10 - eff(rate_blk)) & 1);
            end
            n = n + 1;
        end
    end

    always @(negedge clk) begin
        if (!rst_n) begin
            if (chop1 !== 1'b1) err("chop1 not 1 during reset");
        end else begin
            if (chop1 !== exp_chop1) err($sformatf("chop1 %b, expected %b (frame %0d, cycle %0d, rate %0d)",
                                                    chop1, exp_chop1, (n - 1) / 32, (n - 1) % 32, rate_blk));
            if (chop1 !== prev) begin
                edges = edges + 1;
                if (((n - 1) % 32) != 16) err("chop1 edge not at e16");
                if (cycle !== 5'd16) err("chop1 edge while the clkgen cycle is not 16");
                if (last_edge >= 0 && last_edge_rate == rate_blk && eff(rate_blk) != 0) begin
                    phases = phases + 1;
                    if (n - last_edge != 32 * (1 << (10 - eff(rate_blk))))
                        err($sformatf("phase of %0d MCLK at rate %0d", n - last_edge, rate_blk));
                end
                edges_at_rate[eff(rate_blk)] = edges_at_rate[eff(rate_blk)] + 1;
                last_edge = n;
                last_edge_rate = rate_blk;
            end
            prev = chop1;
        end
    end

    // wait until just after the falling edge that precedes the rising edge number m
    // (m counted like n: the first edge after reset release is m = 0)
    task automatic to_edge(input integer m);
        begin
            while (n < m) @(negedge clk);
        end
    endtask

    localparam integer BLK = 1024 * 32;        // MCLK per 1 ms block

    initial begin
        integer i;
        for (i = 0; i <= 5; i = i + 1) edges_at_rate[i] = 0;
        repeat (5) @(negedge clk);
        if (chop1 !== 1'b1) err("chop1 not 1 in reset");
        rst_n = 1'b1;
        // block 0, 1: rate 3 (reset value sampled at frame 0)
        to_edge(BLK + 5000);
        rate = 3'd5;                           // unaligned: applies at block 2
        to_edge(3 * BLK + 777);
        rate = 3'd1;                           // applies at block 4
        to_edge(5 * BLK + 123);
        to_edge(6 * BLK - 1);                  // one cycle before the block-6 boundary edge
        rate = 3'd0;                           // seen at the boundary: block 6 is off
        to_edge(7 * BLK + 1);                  // one cycle after the block-7 boundary edge
        rate = 3'd6;                           // block 7 stays off, block 8 = 16 kHz
        to_edge(9 * BLK + 4321);
        rate = 3'd7;
        to_edge(10 * BLK + 99);
        rate = 3'd2;
        to_edge(12 * BLK + 2500);
        rate = 3'd4;
        to_edge(14 * BLK + 31);
        rate = 3'd3;
        to_edge(17 * BLK);
        $display("chop1: %0d edges (rate 0..5: %0d %0d %0d %0d %0d %0d), %0d full phases checked, %0d cycles",
                 edges, edges_at_rate[0], edges_at_rate[1], edges_at_rate[2], edges_at_rate[3],
                 edges_at_rate[4], edges_at_rate[5], phases, n);
        if (edges_at_rate[1] == 0 || edges_at_rate[2] == 0 || edges_at_rate[3] == 0 ||
            edges_at_rate[4] == 0 || edges_at_rate[5] == 0) err("a rate was never exercised");
        if (errors == 0) $display("PASS: chop1 rates, e16 edges, phase lengths and 1 ms rate changes");
        else $display("FAIL: %0d errors", errors);
        $finish;
    end

endmodule
