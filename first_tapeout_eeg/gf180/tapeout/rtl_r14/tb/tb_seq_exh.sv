// tb_seq_exh - exhaustive one-step check of eeg_seq (audit round 22, auditor A; the bench of round 21's auditor A): every
// state value 0..15 x event (none / tick / output time) x pending command (none, START, STOP, APPLY, APPLY_NR, FLUSH)
// x cfg_ok x nr_ok x t_elec0 x valid x timer (0 / 5) x frame_stb, 18,432 combinations. The state and the timer are
// deposited between clock edges; the combinational outputs (next state, ack, apply, flush, arm, store, mark, the
// refusal flags) before the edge and the registered state, AFE_RST and timer after it are logged for
// tb/check_seq_exh.py, which compares them with fsm_spec.seq_tick (NFR-05 for the values 9..15) and requires every
// branch a tick or an output time can reach to be taken several times. tb_seq's random walk reaches its rarest branch
// once with the suite's seed (and none with seed 101): this pass does not depend on any seed.
// Usage (run_tests_r14.sh's tb_seq group): vvp build/tb_seq_exh.vvp +trace=build/seq_exh.txt
`timescale 1ns / 1ps
module tb_seq_exh;
    logic clk = 0, rst_n = 0, tick = 0, frame_stb = 0, out_stb = 0, out_valid = 0, cmd_valid = 0;
    logic [7:0] cmd_code = 0;
    logic cfg_ok = 0, nr_ok = 0;
    logic [7:0] t_warm = 8'd5, t_elec = 8'd0, t_rec = 8'd29, t_pre = 8'd3, t_rst = 8'd13;
    wire  [3:0] state;
    wire  afe_rst, apply, flush, cic_arm, store, mark, state_err, cfg_err, cmd_ack;
    eeg_seq dut (.clk(clk), .rst_n(rst_n), .tick(tick), .frame_stb(frame_stb), .out_stb(out_stb), .out_valid(out_valid),
                 .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(cmd_ack), .cfg_ok(cfg_ok), .nr_ok(nr_ok),
                 .t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst), .state(state),
                 .afe_rst(afe_rst), .apply(apply), .flush(flush), .cic_arm(cic_arm), .store(store), .mark(mark),
                 .state_err(state_err), .cfg_err(cfg_err));
    integer f, n = 0;
    string fn;
    logic [7:0] codes [0:5];
    initial begin
        codes[0] = 8'h00; codes[1] = 8'h11; codes[2] = 8'h22; codes[3] = 8'h33; codes[4] = 8'h44; codes[5] = 8'h55;
        if (!$value$plusargs("trace=%s", fn)) fn = "build/seq_exh.txt";
        f = $fopen(fn, "w");
        #5 rst_n = 1;
        for (int s = 0; s < 16; s++)
        for (int ev = 0; ev < 3; ev++)              // 0 none, 1 tick, 2 output time
        for (int c = 0; c < 6; c++)
        for (int k = 0; k < 16; k++)                 // cfg_ok, nr_ok, t_elec0, valid
        for (int tz = 0; tz < 2; tz++)
        for (int fs = 0; fs < 2; fs++) begin
            dut.state = s[3:0];                      // deposited between the edges
            dut.timer = tz ? 18'd0 : 18'd5;
            tick = (ev == 1); out_stb = (ev == 2);
            cmd_valid = (c != 0); cmd_code = codes[c];
            cfg_ok = k[0]; nr_ok = k[1]; t_elec = k[2] ? 8'd0 : 8'd7; out_valid = k[3];
            frame_stb = fs[0];
            #1;
            $fwrite(f, "%0d %0d %0d %0d %0d %0d %0d %0d %0d | nxt %0d ack %0d apply %0d flush %0d arm %0d store %0d mark %0d serr %0d cerr %0d",
                    s, ev, c, k[0], k[1], k[2], k[3], tz, fs,
                    dut.nxt, cmd_ack, apply, flush, cic_arm, store, mark, state_err, cfg_err);
            clk = 1; #1; clk = 0;
            $fwrite(f, " | st %0d afe %0d timer %0d\n", state, afe_rst, dut.timer);
            n++;
            #1;
        end
        $fclose(f);
        $display("tb_seq_exh: %0d combinations -> %s", n, fn);
        $finish;
    end
endmodule
