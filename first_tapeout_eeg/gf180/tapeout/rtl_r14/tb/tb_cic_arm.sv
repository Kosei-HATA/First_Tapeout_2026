// tb_cic_arm - the r14 CIC's clear at an output time against the golden model (check_cic_arm.py): codes from
// build/cic_arm.codes, one input per 32-cycle frame (en at cycle 3, as eeg_clkgen), arm held from just after output
// ARM_K - 1 to just after output ARM_K; every output (data, valid) is written to build/cic_arm.out. With +k2=K2, again
// from just after output K2 - 1 to just after output K2 (audit round 33, auditor C: a second clear in the filter's
// settling, K2 = K + 1 or K + 2; a CIC that took a clear only at a valid output passed all 16 groups).
`timescale 1ns / 1ps
`default_nettype none
module tb_cic_arm;
    logic clk = 0, rst_n = 0, en = 0, arm = 0;
    logic [4:0] code = 0;
    logic [23:0] dout;
    logic dout_stb, dout_valid, settling;
    eeg_cic3 dut (.clk(clk), .rst_n(rst_n), .arm(arm), .en(en), .code(code), .dout(dout), .dout_stb(dout_stb),
                  .dout_valid(dout_valid), .settling(settling));
    always #15.259 clk = ~clk;
    integer fi, fo, c, k, nout, arm_k, arm_k2, cyc;
    initial begin
        if (!$value$plusargs("k=%d", arm_k)) arm_k = 5;
        if (!$value$plusargs("k2=%d", arm_k2)) arm_k2 = -10;
        fi = $fopen("build/cic_arm.codes", "r");
        fo = $fopen("build/cic_arm.out", "w");
        nout = 0;
        repeat (3) @(negedge clk);
        rst_n = 1;
        while (!$feof(fi)) begin
            k = $fscanf(fi, "%d\n", c);
            if (k != 1) break;
            for (cyc = 0; cyc < 32; cyc = cyc + 1) begin
                @(negedge clk);
                en = (cyc == 3);
                if (cyc == 0) code = c[4:0];
            end
        end
        @(negedge clk);
        $fclose(fo);
        $display("tb_cic_arm: %0d outputs written", nout);
        $finish;
    end
    always @(posedge clk) begin
        if (dout_stb) begin
            $fdisplay(fo, "%0d %0d", $signed(dout), dout_valid);
            nout = nout + 1;
            if (nout == arm_k || nout == arm_k2) arm <= 1'b0;
            if (nout == arm_k - 1 || nout == arm_k2 - 1) arm <= 1'b1;   // armed during the window of ARM_K (ARM_K2)
        end
    end
endmodule
`default_nettype wire
