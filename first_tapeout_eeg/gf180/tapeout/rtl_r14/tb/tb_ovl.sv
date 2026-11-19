// tb_ovl - eeg_ovl fed with per-frame codes from build/ovl.codes (one per frame); writes ovl_now per frame
`timescale 1ns / 1ps
`default_nettype none
module tb_ovl;
    logic clk = 0, rst_n = 0, en = 0, out_stb = 0;
    logic [4:0] code = 16;
    logic ovl_now, ovl_seen;
    eeg_ovl dut (.*);
    always #15.259 clk = ~clk;
    integer fi, fo, c, k;
    initial begin
        fi = $fopen("build/ovl.codes", "r");
        fo = $fopen("build/ovl.out", "w");
        repeat (3) @(negedge clk);
        rst_n = 1;
        while (!$feof(fi)) begin
            k = $fscanf(fi, "%d\n", c);
            if (k != 1) break;
            @(negedge clk); code = c[4:0]; en = 1;
            @(negedge clk); en = 0;
            #1 $fdisplay(fo, "%0d", ovl_now);
        end
        $fclose(fo);
        $finish;
    end
endmodule
`default_nettype wire
