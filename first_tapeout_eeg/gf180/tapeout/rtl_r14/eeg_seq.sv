// eeg_seq - the sequencer of the digital control (r14).
//
// Specification: gf180/tapeout/rtl/spec/fsm_spec.py (SEQ: states, transition table, tick semantics) and
// documentation/gf180_digital_control_spec_20261119.md. tb/tb_seq.sv checks this module against fsm_spec.seq_tick
// on random event streams (every cell of the transition table).
//
// Events
//   tick     once per chopper period, frame cycle 24 of the frame in the middle of chopper phase A (eeg_clkgen):
//            the pending command (cmd_valid, cmd_code; at most one) and the state's timer are resolved here,
//            in the order of fsm_spec.SEQ_PRIORITY (the requirements' section 5.0 is generated from it; tb_seq
//            replays every tick against it). Registered outputs change at e25.
//   out_stb  a CIC output time (frame cycle 8); never in the same MCLK cycle as tick.
//   rst_n    asynchronous (RESET_N or SOFT_RESET): the reset state is IDLE with AFE_RST = 1.
// Timer: one down-counter in frames, loaded on entering a timed state and on a restart (APPLY or APPLY_NR in
// WARMUP: AFE_RST is never released sooner than T_WARM after a change; APPLY_NR in WAIT_E: the electrode settles
// T_ELEC after the step) (T_WARM, T_ELEC in 1024-frame units of 1 ms,
// T_REC, T_PRE, T_RST in 8-frame units of 7.8125 us), decremented once per frame (frame_stb); TMR = 0. The expiry is
// taken at the first tick after it, so every duration is a whole number of chopper periods at 128 kHz.
// An illegal state value returns to IDLE (AFE_RST = 1) with STATE_ERR.
`timescale 1ns / 1ps
`default_nettype none

module eeg_seq (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       tick,
    input  logic       frame_stb,         // once per frame (timer clock)
    input  logic       out_stb,           // CIC output time
    input  logic       out_valid,         // that output is valid (CIC NSKIP)
    input  logic       cmd_valid,         // a command is pending
    input  logic [7:0] cmd_code,
    output logic       cmd_ack,           // the pending command was taken at this tick
    input  logic       cfg_ok,            // shadow offset DAC: M within the range
    input  logic       nr_ok,             // shadow - active: one offset-DAC step only
    input  logic [7:0] t_warm,
    input  logic [7:0] t_elec,
    input  logic [7:0] t_rec,
    input  logic [7:0] t_pre,
    input  logic [7:0] t_rst,
    (* fsm_encoding = "none" *)                // NFR-05: no recoding, so that codes 9..15 stay decoded (audit round 14)
    output logic [3:0] state,
    output logic       afe_rst,           // registered, changes only at a tick (or reset)
    // the following are combinational during the event's cycle, so every register they drive (active settings,
    // FIFO, flags) changes at the same edge as state and afe_rst (e25 for a tick)
    output logic       apply,             // copy shadow -> active
    output logic       flush,             // empty the FIFO
    output logic       cic_arm,           // ALIGN: the CIC clears at this output time
    output logic       store,             // store this output (with out_stb; the FIFO decides OVERRUN)
    output logic       mark,              // APPLY_NR in RUN: CHANGED on the next 3 + T_ELEC outputs (eeg_digital_top)
    output logic       state_err,
    output logic       cfg_err
);

`include "eeg_regs_defs.svh"

    localparam logic [3:0] S_IDLE = 4'd0, S_WARMUP = 4'd1, S_RECOVER = 4'd2, S_WAIT_E = 4'd3, S_ALIGN = 4'd4,
                           S_FILL = 4'd5, S_RUN = 4'd6, S_PRE = 4'd7, S_PULSE = 4'd8;

    logic [17:0] timer;
    logic        tmr;
    logic [3:0]  nxt;
    logic        a_apply, a_flush, a_store, a_mark, a_serr, a_cerr, a_ack, a_restart;
    logic        is_start, is_stop, is_apply, is_nr, is_flush;

    assign tmr      = (timer == 18'd0);
    assign is_start = cmd_valid && (cmd_code == CMD_START);
    assign is_stop  = cmd_valid && (cmd_code == CMD_STOP);
    assign is_apply = cmd_valid && (cmd_code == CMD_APPLY);
    assign is_nr    = cmd_valid && (cmd_code == CMD_APPLY_NR);
    assign is_flush = cmd_valid && (cmd_code == CMD_FLUSH);
    assign cic_arm  = (state == S_ALIGN);

    function automatic logic afe_rst_of(input logic [3:0] s);
        afe_rst_of = (s == S_IDLE) || (s == S_WARMUP) || (s == S_PULSE) || (s > S_PULSE);
    endfunction

    function automatic logic timed(input logic [3:0] s);
        timed = (s == S_WARMUP) || (s == S_RECOVER) || (s == S_WAIT_E) || (s == S_PRE) || (s == S_PULSE);
    endfunction

    always_comb begin
        nxt       = state;
        a_apply   = 1'b0;
        a_restart = 1'b0;
        a_flush   = 1'b0;
        a_store = 1'b0;
        a_mark  = 1'b0;
        a_serr  = 1'b0;
        a_cerr  = 1'b0;
        a_ack   = 1'b0;
        if (state > S_PULSE) begin                          // illegal value: safe side
            nxt    = S_IDLE;
            a_serr = 1'b1;
        end else if (tick) begin
            a_ack = cmd_valid;
            // the command (highest priority; at most one)
            if (is_stop) begin
                if (state != S_IDLE) nxt = S_IDLE;          // IDLE: accepted, does nothing (IGN)
            end else if (is_start) begin
                if (state == S_IDLE) begin
                    if (cfg_ok) begin
                        a_apply = 1'b1;
                        a_flush = 1'b1;
                        nxt     = S_WARMUP;
                    end else begin
                        a_cerr = 1'b1;
                    end
                end else begin
                    a_serr = 1'b1;
                end
            end else if (is_apply || is_nr) begin
                case (state)
                    S_IDLE, S_WARMUP: begin                 // AFE held in reset: any consistent change, no pulse
                        if (cfg_ok) begin
                            a_apply   = 1'b1;
                            a_restart = (state == S_WARMUP);    // WARMUP: the wait before the release starts again
                        end else begin
                            a_cerr = 1'b1;
                        end
                    end
                    S_PRE, S_PULSE: a_serr = 1'b1;          // a further change waits for READY
                    default: begin                          // RECOVER, WAIT_E, ALIGN, FILL, RUN: the AFE runs
                        if (is_apply) begin
                            if (cfg_ok) begin
                                a_apply = 1'b1;
                                a_flush = 1'b1;                 // the data restart: no sample of the old setting
                                nxt     = S_PRE;
                            end else begin
                                a_cerr = 1'b1;
                            end
                        end else begin                      // APPLY_NR: one offset-DAC step only
                            if (cfg_ok && nr_ok) begin
                                a_apply = 1'b1;
                                // before RUN the electrode settles again (T_ELEC) before the clear
                                case (state)
                                    S_WAIT_E: a_restart = 1'b1;
                                    S_ALIGN:  if (t_elec != 8'd0) nxt = S_WAIT_E;
                                    S_FILL:   nxt = (t_elec != 8'd0) ? S_WAIT_E : S_ALIGN;   // restart the clear
                                    S_RUN:    a_mark = 1'b1;    // CHANGED on the next 3 + T_ELEC outputs
                                    default:  ;                 // RECOVER: the electrode wait (T_ELEC > 0)
                                                                // and the clear follow anyway
                                endcase
                            end else begin
                                a_cerr = 1'b1;
                            end
                        end
                    end
                endcase
            end else if (is_flush) begin
                a_flush = 1'b1;
            end
            // the timer (lower priority): only if the command left the state unchanged and did not restart it
            if (nxt == state && timed(state) && tmr && !a_restart) begin
                case (state)
                    S_WARMUP:  nxt = S_RECOVER;
                    S_RECOVER: nxt = (t_elec == 8'd0) ? S_ALIGN : S_WAIT_E;
                    S_WAIT_E:  nxt = S_ALIGN;
                    S_PRE:     nxt = S_PULSE;
                    S_PULSE:   nxt = S_RECOVER;
                    default:   ;
                endcase
            end
        end else if (out_stb) begin
            case (state)
                S_ALIGN: nxt = S_FILL;                      // the CIC clears at this output time (cic_arm)
                S_FILL: begin
                    if (out_valid) begin
                        a_store = 1'b1;
                        nxt     = S_RUN;
                    end
                end
                S_RUN:   a_store = 1'b1;
                default: ;
            endcase
        end
    end

    // timer value on entering a timed state, in frames
    function automatic logic [17:0] load_of(input logic [3:0] s);
        case (s)
            S_WARMUP:  load_of = {t_warm, 10'd0};          // x 1024 frames (1 ms)
            S_WAIT_E:  load_of = {t_elec, 10'd0};
            S_RECOVER: load_of = {7'd0, t_rec, 3'd0};       // x 8 frames (7.8125 us)
            S_PRE:     load_of = {7'd0, t_pre, 3'd0};
            S_PULSE:   load_of = {7'd0, t_rst, 3'd0};
            default:   load_of = 18'd0;
        endcase
    endfunction

    assign apply     = a_apply;
    assign flush     = a_flush;
    assign store     = a_store;
    assign mark      = a_mark;
    assign state_err = a_serr;
    assign cfg_err   = a_cerr;
    assign cmd_ack   = a_ack;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state   <= S_IDLE;
            afe_rst <= 1'b1;
            timer   <= 18'd0;
        end else begin
            state   <= nxt;
            afe_rst <= afe_rst_of(nxt);
            if (nxt != state || a_restart) begin
                timer <= load_of(nxt);
            end else if (frame_stb && timer != 18'd0) begin
                timer <= timer - 18'd1;
            end
        end
    end

endmodule

`default_nettype wire
