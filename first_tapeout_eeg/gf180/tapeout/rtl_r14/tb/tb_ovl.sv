// tb_ovl - eeg_ovl fed with per-frame codes from build/ovl.codes (one per frame); writes ovl_now and ovl_hit per frame
// (build/ovl.out: "ovl_now ovl_hit") and, after every K = 37 frames, an output time with the interval's ovl_seen
// (build/ovl_iv.out); tb/check_ovl.py compares both with regmap.OVL_RULE (the short interval puts many detector tails
// across interval boundaries; audit round 6)
`timescale 1ns / 1ps
`default_nettype none
module tb_ovl;
    logic clk = 0, rst_n = 0, en = 0, out_stb = 0;
    logic [4:0] code = 16;
    logic ovl_now, ovl_hit, ovl_seen;
    eeg_ovl dut (.*);
    always #15.259 clk = ~clk;
    integer fi, fo, fv, c, k, nf;
    logic h;
    initial begin
        fi = $fopen("build/ovl.codes", "r");
        fo = $fopen("build/ovl.out", "w");
        fv = $fopen("build/ovl_iv.out", "w");
        nf = 0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        while (!$feof(fi)) begin
            k = $fscanf(fi, "%d\n", c);
            if (k != 1) break;
            @(negedge clk); code = c[4:0]; en = 1;
            #1 h = ovl_hit;                             // during the frame's input cycle
            @(negedge clk); en = 0;
            #1 $fdisplay(fo, "%0d %0d", ovl_now, h);    // the detector after the frame, and the frame's hit
            nf = nf + 1;
            if (nf % 37 == 0) begin                     // an output time: the interval's flag, then it restarts
                @(negedge clk); out_stb = 1;
                #1 $fdisplay(fv, "%0d", ovl_seen);
                @(negedge clk); out_stb = 0;
            end
        end
        $fclose(fo);
        $fclose(fv);
        $display("tb_ovl: %0d frames", nf);       // the closing line (the mutation runner requires it; audit round 9)
        $finish;
    end
endmodule
`default_nettype wire
