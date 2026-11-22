// audit 34, A: where every CHOP1 edge falls relative to the output chopper (CHOP_OUT) and its blanking (CHOP_BLANK)
`timescale 1ns / 1ps
`default_nettype none
module tb_a34_c1blank;
    logic clk = 0, rst_n = 0, chop_fast = 1;
    logic [3:0] blank_len = 4'd15;
    logic [2:0] rate = 3'd3;
    logic [4:0] cycle;
    logic cmp, thc, dl, cen, chop, chop_out, chop_blank, rclk, tick, chop1;
    always #15.2587890625 clk = ~clk;
    eeg_clkgen u_c (.clk(clk), .rst_n(rst_n), .chop_fast(chop_fast), .chop_dly(8'd0), .blank_len(blank_len),
                    .cycle(cycle), .cmp_strobe(cmp), .th_capture(thc), .dac_load(dl), .cic_en(cen), .chop(chop),
                    .chop_out(chop_out), .chop_blank(chop_blank), .raw_clk(rclk), .tick(tick));
    eeg_chop1 u_1 (.clk(clk), .rst_n(rst_n), .cycle(cycle), .chop1_rate(rate), .chop1(chop1));
    integer n = 0, last_out_rise = -1000, last_out_edge = -1000, last_blank_fall = -1000;
    integer ne = 0, n_bad = 0, hist_out [0:40], hist_blank [0:40], n_a = 0;
    logic co_q = 0, cb_q = 0, c1_q = 1;
    initial for (int i = 0; i <= 40; i++) begin hist_out[i] = 0; hist_blank[i] = 0; end
    always @(posedge clk) begin
        #0.1;
        n = n + 1;
        if (chop_out !== co_q) begin last_out_edge = n; if (chop_out) last_out_rise = n; end
        if (cb_q && !chop_blank) last_blank_fall = n;
        if (chop1 !== c1_q && rst_n) begin
            ne = ne + 1;
            if (n - last_out_edge <= 40) hist_out[n - last_out_edge]++;
            if (n - last_blank_fall <= 40) hist_blank[n - last_blank_fall]++;
            if (chop_out === 1'b1 && last_out_rise == last_out_edge) n_a++;
        end
        co_q = chop_out; cb_q = chop_blank; c1_q = chop1;
    end
    task automatic run(input logic f, input logic [3:0] bl, input logic [2:0] r, input integer frames);
        chop_fast = f; blank_len = bl; rate = r;
        for (int i = 0; i <= 40; i++) begin hist_out[i] = 0; hist_blank[i] = 0; end
        ne = 0; n_a = 0;
        repeat (frames * 32) @(posedge clk);
        $write("rate %s, BLANK_LEN %0d, CHOP1 rate %0d: %0d CHOP1 edges, %0d in phase A just after its rising CHOP_OUT edge; MCLK after the last CHOP_OUT edge:",
               f ? "128k" : "64k", bl, r, ne, n_a);
        for (int i = 0; i <= 40; i++) if (hist_out[i]) $write(" %0d x%0d", i, hist_out[i]);
        $write("; after the last CHOP_BLANK fall:");
        for (int i = 0; i <= 40; i++) if (hist_blank[i]) $write(" %0d x%0d", i, hist_blank[i]);
        $display("");
    endtask
    initial begin
        repeat (5) @(posedge clk);
        rst_n = 1;
        repeat (2048 * 32) @(posedge clk);                   // settle the rate pipeline (CHOP1 takes its rate per 1 ms)
        for (int f = 1; f >= 0; f--)
            for (int r = 1; r <= 5; r++) begin
                run(f[0], 4'd15, r[2:0], 1024);              // rate taken at the next 1 ms boundary: discard
                run(f[0], 4'd15, r[2:0], 4096);
            end
        run(1'b1, 4'd7, 3'd3, 1024);
        run(1'b1, 4'd7, 3'd3, 4096);
        $finish;
    end
endmodule
`default_nettype wire
