// audit 41 A probe: which input frames reach which CIC output (window of each output), with and without the
// ALIGN clear. The code is 15 (x = -1) except one frame at 31 (x = +31); the output difference against the
// all-15 reference shows whether that frame is inside the window of each output.
`timescale 1ns / 1ps
`default_nettype none
module tb_a41_cicwin;
    logic clk = 0, rst_n = 0, en = 0, arm = 0;
    logic [4:0] code;
    wire [23:0] dout; wire dstb, dval, settling;
    eeg_cic3 dut (.clk(clk), .rst_n(rst_n), .arm(arm), .en(en), .code(code), .dout(dout), .dout_stb(dstb),
                  .dout_valid(dval), .settling(settling));
    always #1 clk = ~clk;
    integer frame = -1, cyc = 31, imp = -1, clr_out = -1, nout = 0;
    logic signed [23:0] outs [0:15]; logic [12:0] outs2 [0:15], ref2 [0:15];
    // frame counter like eeg_clkgen: cycle 0..31, en at cycle 3
    always @(posedge clk) if (rst_n) begin
        cyc <= (cyc + 1) % 32;
        if (cyc == 31) frame <= frame + 1;
    end
    always @(*) begin en = rst_n && (cyc == 3) && frame >= 0; code = (frame == imp) ? 5'd31 : 5'd15; end
    // arm: in the cycle before the output time of output number clr_out (the output at frame 1024 (n+1) - 1)
    always @(*) arm = (clr_out >= 0) && dut.step[3] && (nout == clr_out);
    always @(posedge clk) if (dut.step[3]) begin outs[nout] = dut.acc[36:13]; outs2[nout] = dut.acc[12:0]; nout = nout + 1; end
    task run(input integer f_imp, input integer clr);
        integer k;
        begin
            rst_n = 0; frame = -1; cyc = 31; nout = 0; imp = f_imp; clr_out = clr;
            repeat (4) @(posedge clk); #0.5 rst_n = 1;
            wait (nout == 8); @(posedge clk);
        end
    endtask
    logic signed [23:0] ref_ [0:15];
    integer f, k, frames[0:11], nf;
    initial begin
        // reference: no impulse
        run(-1, -1); for (k = 0; k < 8; k = k + 1) begin ref_[k] = outs[k]; ref2[k] = outs2[k]; end
        frames[0] = 1024*2 - 1; frames[1] = 1024*2; frames[2] = 1024*2 + 1;
        frames[3] = 1024*4 + 1021; frames[4] = 1024*4 + 1022; frames[5] = 1024*4 + 1023;
        frames[6] = 1024*3 - 2;  frames[7] = 1024*3 - 3; frames[8] = 1024*5; nf = 9;
        for (f = 0; f < nf; f = f + 1) begin
            run(frames[f], -1);
            $write("impulse at frame %0d (= 1024*%0d + %0d): outputs differing:", frames[f], frames[f] / 1024, frames[f] % 1024);
            for (k = 0; k < 8; k = k + 1) if (outs[k] !== ref_[k] || outs2[k] !== ref2[k]) $write(" %0d", k);
            $write("\n");
        end
        // with a clear at output 2 (frame 3071): which outputs see an impulse just after / before the clear
        run(-1, 2); for (k = 0; k < 8; k = k + 1) begin ref_[k] = outs[k]; ref2[k] = outs2[k]; end
        frames[0] = 1024*3 - 1; frames[1] = 1024*3; frames[2] = 1024*3 - 2; frames[3] = 1024*3 - 3; nf = 4;
        for (f = 0; f < nf; f = f + 1) begin
            run(frames[f], 2);
            $write("clear at output 2, impulse at frame %0d: outputs differing:", frames[f]);
            for (k = 0; k < 8; k = k + 1) if (outs[k] !== ref_[k] || outs2[k] !== ref2[k]) $write(" %0d", k);
            $write("   valid of outputs 3..5 after the clear: see dval\n");
        end
        $finish;
    end
endmodule
