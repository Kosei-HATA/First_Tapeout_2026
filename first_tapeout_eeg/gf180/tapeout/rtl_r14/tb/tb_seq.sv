// tb_seq - eeg_seq on random event streams; every tick and output time is written to a trace that
// tb/check_seq_trace.py replays through the specification (gf180/tapeout/rtl/spec/fsm_spec.py, seq_tick) and
// compares: next state and actions, cell by cell, with the coverage of the transition table.
// Every traced line also carries the RTL's timer before and after the event, the frames since the previous traced
// event and the timer settings, so that the checker models every load, decrement and restart of the timer.
// Checked here directly: AFE_RST equals the state's value after every edge and changes only at a tick or reset;
// cmd_ack is the pending command at a tick and nothing else; between events (no tick, no output time) neither the
// state nor any action changes; every illegal state value (9..15) returns to IDLE with STATE_ERR. The timer settings
// are drawn mostly short (so that expiries happen) and sometimes over the full range 0..255 (loads of up to
// 255 x 1024 frames, checked by the timer model).
// Plusargs: +n=<events> +seed=<seed> +trace=<file>
`timescale 1ns / 1ps
`default_nettype none

module tb_seq;
    logic       clk = 1'b0;
    logic       rst_n = 1'b0;
    logic       tick = 1'b0, frame_stb = 1'b0, out_stb = 1'b0, out_valid = 1'b0;
    logic       cmd_valid = 1'b0;
    logic [7:0] cmd_code = 8'h00;
    logic       cmd_ack;
    logic       cfg_ok = 1'b1, nr_ok = 1'b1;
    logic [7:0] t_warm = 8'd1, t_elec = 8'd0, t_rec = 8'd1, t_pre = 8'd1, t_rst = 8'd1;
    logic [3:0] state;
    logic       afe_rst, apply, flush, cic_arm, store, mark, state_err, cfg_err;

    eeg_seq dut (.*);

    always #15.259 clk = ~clk;

    function automatic logic [7:0] code_of(input integer k);   // START x2, STOP, APPLY x2, APPLY_NR x3, FLUSH
        case (k)
            0, 1:    code_of = 8'h11;
            2:       code_of = 8'h22;
            3, 4:    code_of = 8'h33;
            5, 6, 7: code_of = 8'h44;
            default: code_of = 8'h55;
        endcase
    endfunction

    integer fd, n, seed, i, errors, ev, nticks, nouts, nresets, quiet, frames;
    logic [17:0] tmr_before;
    logic        a_rs, fs0;
    logic [7:0]  tw0, te0x, tr0, tp0, tq0;
    logic [3:0] st0;
    logic       tm0, cv0, ev_tick, ev_out, prev_afe, prev_tick, after_reset;
    logic [7:0] cc0;
    logic       ack0;
    logic       a_apply, a_flush, a_store, a_mark, a_serr, a_cerr, a_clr;
    reg [8*256-1:0] trace;

    function automatic logic [7:0] tcode();                    // a timer setting: mostly short, sometimes long
        case ($urandom % 20)                                   // 15 % long, so that every cell is still reached
            0:       tcode = 8'd255;
            1:       tcode = 8'($urandom % 256);
            2:       tcode = 8'd64 + 8'($urandom % 64);
            default: tcode = 8'($urandom % 3);
        endcase
    endfunction

    function automatic logic afe_of(input logic [3:0] s);
        afe_of = (s == 4'd0) || (s == 4'd1) || (s == 4'd8) || (s > 4'd8);
    endfunction

    initial begin
        if (!$value$plusargs("n=%d", n)) n = 200000;
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        if (!$value$plusargs("trace=%s", trace)) trace = "build/seq_trace.txt";
        fd = $fopen(trace, "w");
        errors = 0; nticks = 0; nouts = 0; nresets = 0; quiet = 0;
        frames = 0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        after_reset = 1'b1;
        prev_tick = 1'b0;
        prev_afe = afe_rst;
        for (i = 0; i < n; i = i + 1) begin
            @(negedge clk);
            // stimulus
            ev = $urandom(seed) % 16;
            seed = seed + 1;
            tick      = (ev < 5);
            out_stb   = (ev == 5) || (ev == 6);
            frame_stb = ($urandom % 2) == 0;
            out_valid = ($urandom % 2) == 0;
            cfg_ok    = ($urandom % 6) != 0;
            nr_ok     = ($urandom % 3) != 0;
            // quiet stretches without commands, so that the long timers (x 1024 frames) also expire
            if (quiet > 0) quiet = quiet - 1;
            else if (($urandom % 3000) == 0) quiet = 6000;
            if (!cmd_valid && quiet == 0 && ($urandom % 3) == 0) begin
                cmd_valid = 1'b1;
                cmd_code  = code_of($urandom % 9);
            end
            if (($urandom % 40) == 0) begin
                t_warm = tcode(); t_elec = tcode(); t_rec = tcode();
                t_pre  = tcode(); t_rst  = tcode();
            end
            if (($urandom % 20000) == 0) begin               // asynchronous reset in the middle of anything
                rst_n = 1'b0;
                #3;
                if (state !== 4'd0 || afe_rst !== 1'b1) begin
                    $display("ERROR: reset does not give IDLE with AFE_RST = 1");
                    errors = errors + 1;
                end
                @(negedge clk);
                rst_n = 1'b1;
                $fdisplay(fd, "R");
                frames = 0;
                nresets = nresets + 1;
                cmd_valid = 1'b0;
                tick = 1'b0; out_stb = 1'b0;
                after_reset = 1'b1;
                prev_afe = afe_rst;
                continue;
            end
            #1;
            st0 = state;  tm0 = (dut.timer == 18'd0);  cv0 = cmd_valid;  cc0 = cmd_code;
            tmr_before = dut.timer;  a_rs = dut.a_restart;  fs0 = frame_stb;
            tw0 = t_warm;  te0x = t_elec;  tr0 = t_rec;  tp0 = t_pre;  tq0 = t_rst;
            ev_tick = tick;  ev_out = out_stb;
            a_apply = apply; a_flush = flush; a_store = store; a_mark = mark;
            a_serr = state_err; a_cerr = cfg_err; a_clr = cic_arm && out_stb;
            ack0 = cmd_ack;
            @(posedge clk);
            #1;
            // AFE_RST: the state's value, changing only at a tick
            if (afe_rst !== afe_of(state)) begin
                $display("ERROR: AFE_RST %b in state %0d", afe_rst, state);
                errors = errors + 1;
            end
            if (afe_rst !== prev_afe && !ev_tick && !after_reset) begin
                $display("ERROR: AFE_RST changed without a tick (state %0d -> %0d)", st0, state);
                errors = errors + 1;
            end
            prev_afe = afe_rst;
            after_reset = 1'b0;
            if (ack0 !== (ev_tick && cv0)) begin
                $display("ERROR: cmd_ack %b at a cycle with tick %b and a pending command %b", ack0, ev_tick, cv0);
                errors = errors + 1;
            end
            if (!ev_tick && !ev_out && (state !== st0 || a_apply || a_flush || a_store || a_mark || a_serr || a_cerr ||
                                        a_clr || a_rs)) begin
                $display("ERROR: state %0d -> %0d or an action without a tick or an output time", st0, state);
                errors = errors + 1;
            end
            if (ev_tick || ev_out) begin
                $fdisplay(fd, "%s %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d%0d%0d%0d%0d%0d%0d%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                          ev_tick ? "T" : "O", st0, cv0, cc0, tm0, cfg_ok, nr_ok, (t_elec == 8'd0), out_valid, state,
                          a_apply, a_flush, a_store, a_mark, a_serr, a_cerr, a_clr, a_rs,
                          tmr_before, dut.timer, frames, fs0, tw0, te0x, tr0, tp0, tq0);
                if (ev_tick) nticks = nticks + 1; else nouts = nouts + 1;
                frames = 0;
            end else if (fs0) begin
                frames = frames + 1;                        // frames between traced events (the timer's clock)
            end
            if (ev_tick && cv0) cmd_valid = 1'b0;             // taken at this tick (cmd_ack)
        end
        // every illegal state value: back to IDLE with STATE_ERR (and AFE_RST = 1 while it lasts)
        for (int bad = 9; bad < 16; bad++) begin
            @(negedge clk);
            tick = 1'b0; out_stb = 1'b0;
            force dut.state = 4'(bad);
            #1;
            if (state_err !== 1'b1) begin
                $display("ERROR: illegal state %0d without STATE_ERR", bad);
                errors = errors + 1;
            end
            @(negedge clk);
            release dut.state;
            @(posedge clk);
            #1;
            if (state !== 4'd0 || afe_rst !== 1'b1) begin
                $display("ERROR: illegal state %0d not returned to IDLE (state %0d, AFE_RST %b)", bad, state, afe_rst);
                errors = errors + 1;
            end
        end
        $fclose(fd);
        $display("tb_seq: %0d ticks, %0d output times, %0d resets traced; %0d direct errors", nticks, nouts, nresets,
                 errors);
        if (errors == 0) $display("PASS: tb_seq direct checks (trace in %0s)", trace);
        else             $display("FAIL: tb_seq");
        $finish;
    end
endmodule

`default_nettype wire
