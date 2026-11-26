// audit 48 A probe 1: a random procedure-compliant host (CRC off, perfect knowledge of the chip's state) driving
// eeg_digital_top through its pins, with requirement-level monitors written from requirements 4.10, SEQ-03, SEQ-06,
// SEQ-13, SEQ-16, ANA-01, ANA-04 (independent of fsm_spec and of the RTL's internals, which only give the timing
// reference: the frame index and the tick):
//   M1  every analog setting pin (AFE_RST, OFM, OFS, OFEN, AFE_IBIAS, CPF_TRIM, BTRIM_P/N, CHOP_EN, TEST_CFG[5:0],
//       DWA_EN) changes only at the edge ending a tick cycle, or in a control reset, or with RESET_N low
//   M2  AFE_RST: each high period lasts >= 100 us; every non-step setting change is >= 100 us before the next
//       release (SEQ-16); one made while the AFE runs is followed by a pulse (PULSE) >= 20 us later
//   M3  every stored sample: its window's analog span starts >= 0.22 ms after the last release, no AFE_RST since,
//       no non-step setting change since the span's start; every one-step change (APPLY_NR while the AFE runs)
//       whose new inputs are in the window, or whose electrode wait T_ELEC is not over at the window's start, gives
//       CHANGED = 1 (SEQ-06, SEQ-03)
//   M4  no stored window straddles a CHOP1 rate boundary, a chopper rate switch or a blanking-width change
`timescale 1ns / 1ps
`default_nettype none
module tb_a48_rand;
`include "eeg_regs_defs.svh"
    localparam real TMCLK  = 1000.0 / 32.768;
    localparam real TFRAME = 32.0 * TMCLK;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"

    integer errors = 0;
    task automatic err(input string m);
        errors = errors + 1;
        if (errors <= 60) $display("ERROR @%0t: %s", $time, m);
    endtask

    // ---------------------------------------------------------------- CODE: random, with overload bursts
    integer ovl_left = 0;
    logic   ovl_val = 1'b1;
    always @(posedge MCLK) if (dut.cycle == 5'd1) begin          // changes at e2, as eeg_adc_dig's CODE
        if (ovl_left > 0) begin CODE <= ovl_val ? 5'd31 : 5'd0; ovl_left <= ovl_left - 1; end
        else CODE <= 5'd6 + 5'($urandom % 20);
    end

    // ---------------------------------------------------------------- frame index (frame 0 starts at the release)
    integer fr = -1;
    real    t_f0 = 0.0;
    always @(posedge MCLK) begin
        #0.01;
        if (dut.tm_rst_n === 1'b1 && dut.cycle == 5'd0) begin
            fr = fr + 1;
            if (fr == 0) t_f0 = $realtime - 0.01;
        end
    end
    function automatic real t_of_frame(input integer f);
        return t_f0 + f * TFRAME;
    endfunction

    // ---------------------------------------------------------------- M1, M2: the setting pins
    function automatic logic [33:0] pins();
        return {AFE_RST, OFM, OFS, OFEN, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, CHOP_EN, TEST_CFG[5:0], DWA_EN};
    endfunction
    logic [33:0] P, Pq;
    logic        tick_q = 1'b0, started = 1'b0;
    logic [3:0]  st_q = 4'd0;
    logic [7:0]  te_q = 8'd0;
    real  t_rise = 0.0, t_rel = -1.0e12, t_last_change = 0.0, t_pend = 0.0;
    integer te_rel = 0;
    bit   pend_pulse = 1'b0;
    integer n_changes = 0, n_steps = 0, n_rel = 0, n_pulses = 0;
    // one-step changes: frame of the tick and T_ELEC read at it
    integer step_fr [0:63];
    integer step_te [0:63];
    integer n_step_rec = 0;
    // CHOP1 rate boundaries, chopper rate switches, blanking-width changes (frame of the change)
    integer c1_fr [0:255];   integer n_c1 = 0;
    integer cf_fr [0:255];   integer n_cf = 0;
    integer bw_fr [0:255];   integer n_bw = 0;
    logic [2:0] c1_rate_q = 3'd3;
    logic       fast_q = 1'b1;
    integer     bw_q = 8, bw_cnt = 0;

    function automatic integer sv_of(input logic [33:0] p);   // signed offset-DAC value from the pins
        integer m;
        m = p[32:23];
        return p[22] ? -m : m;
    endfunction

    always @(negedge MCLK) begin
        P = pins();
        if (started && RESET_N === 1'b1 && P !== Pq) begin
            logic legal, others, nr;
            integer dsv;
            legal = tick_q || dut.rst_n !== 1'b1 || st_q > 4'd8;
            if (!legal) err($sformatf("M1: setting pins changed outside a tick and a reset: %h -> %h (cycle %0d)",
                                      Pq, P, dut.cycle));
            // classify (AFE_RST is bit 33; OFM 32:23, OFS 22)
            if (P[32:0] !== Pq[32:0]) begin
                others = (P[21:0] !== Pq[21:0]);
                dsv = sv_of(P) - sv_of(Pq);
                nr = !others && (dsv >= -1) && (dsv <= 1) && !P[33] && !Pq[33] && dut.rst_n === 1'b1;
                n_changes = n_changes + 1;
                if (nr) begin
                    n_steps = n_steps + 1;
                    step_fr[n_step_rec % 64] = fr;
                    step_te[n_step_rec % 64] = te_q;
                    n_step_rec = n_step_rec + 1;
                end else begin
                    t_last_change = $realtime;
                    if (!P[33]) begin pend_pulse = 1'b1; t_pend = $realtime; end
                end
            end
            if (P[33] && !Pq[33]) begin                       // AFE_RST rises
                n_pulses = n_pulses + 1;
                t_rise = $realtime;
                if (pend_pulse && dut.seq_state == ST_PULSE && $realtime - t_pend < 20000.0)
                    err($sformatf("M2: AFE_RST pulse %0.2f us after a setting change made while the AFE ran (>= 20 us)",
                                  ($realtime - t_pend) / 1000.0));
                pend_pulse = 1'b0;
            end
            if (!P[33] && Pq[33]) begin                       // AFE_RST falls: the release
                n_rel = n_rel + 1;
                if ($realtime - t_rise < 100000.0)
                    err($sformatf("M2: AFE_RST high for only %0.2f us", ($realtime - t_rise) / 1000.0));
                if ($realtime - t_last_change < 100000.0)
                    err($sformatf("M2: release %0.2f us after a setting change (SEQ-16: >= T_RST)",
                                  ($realtime - t_last_change) / 1000.0));
                if (pend_pulse) err("M2: release with a setting change still awaiting its pulse");
                t_rel = $realtime;
                te_rel = dut.t_elec;                          // the host writes T_ELEC only in IDLE and RUN
            end
        end
        if (RESET_N === 1'b1) started = 1'b1;
        if (dut.rst_n !== 1'b1 && !P[33]) err("M2: AFE_RST low in a control reset");
        Pq = P;
        tick_q = dut.tick;
        st_q = dut.seq_state;
        te_q = dut.t_elec;
        // M4's events
        if (dut.u_chop1.rate_q !== c1_rate_q) begin c1_fr[n_c1 % 256] = fr; n_c1 = n_c1 + 1; c1_rate_q = dut.u_chop1.rate_q; end
        if (dut.u_clkgen.fast !== fast_q) begin cf_fr[n_cf % 256] = fr; n_cf = n_cf + 1; fast_q = dut.u_clkgen.fast; end
    end
    // blanking widths (CHOP_BLANK pulses that are not held by ADC_ZERO)
    always @(negedge MCLK) begin
        if (dut.gen_blank === 1'b1) bw_cnt = bw_cnt + 1;
        else if (bw_cnt != 0) begin
            if (bw_cnt != bw_q) begin bw_fr[n_bw % 256] = fr; n_bw = n_bw + 1; bw_q = bw_cnt; end
            bw_cnt = 0;
        end
    end

    // ---------------------------------------------------------------- M3, M4: every stored sample
    integer n_stored = 0, n_changed = 0, n_need = 0;
    always @(negedge MCLK) begin
        if (dut.u_fifo.push_ok === 1'b1) begin
            integer n, k, lo, hi;
            real t_ws;
            logic chg, need;
            n = fr;                                           // the output's frame (cycle 8)
            lo = n - 3071; hi = n - 2;                        // the window's inputs; input k integrates frame k - 1
            t_ws = t_of_frame(lo - 1);
            chg = dut.smp_status[SMP_CHANGED_LSB];
            n_stored = n_stored + 1;
            if (chg) n_changed = n_changed + 1;
            if (AFE_RST !== 1'b0) err("M3: stored with AFE_RST = 1");
            if (t_ws - t_rel < 220000.0 + te_rel * 1.0e6)
                err($sformatf("M3: stored window starts %0.1f us after the release (>= 0.22 ms + T_ELEC %0d ms)",
                              (t_ws - t_rel) / 1000.0, te_rel));
            if (t_rise > t_rel) err("M3: AFE_RST rose after the last release");
            if (t_last_change >= t_ws)
                err($sformatf("M3: a setting change %0.1f us after the window's start (frame %0d)",
                              (t_last_change - t_ws) / 1000.0, n));
            need = 1'b0;
            for (k = 0; k < 64 && k < n_step_rec; k++) begin
                integer x, te;
                x = step_fr[k]; te = step_te[k];
                if (hi >= x + 1 && lo < x + 1 + te * 1024) need = 1'b1;
            end
            if (need) n_need = n_need + 1;
            if (need && !chg) err($sformatf("M3: window [%0d, %0d] has a one-step change or its electrode wait, but no CHANGED", lo, hi));
            for (k = 0; k < 256 && k < n_c1; k++) if (lo < c1_fr[k] && c1_fr[k] <= hi)
                err($sformatf("M4: window [%0d, %0d] straddles the CHOP1 rate boundary at frame %0d", lo, hi, c1_fr[k]));
            for (k = 0; k < 256 && k < n_cf; k++) if (lo - 1 < cf_fr[k] && cf_fr[k] <= hi - 1)
                err($sformatf("M4: window [%0d, %0d] straddles the chopper rate switch at frame %0d", lo, hi, cf_fr[k]));
            for (k = 0; k < 256 && k < n_bw; k++) if (lo - 1 < bw_fr[k] && bw_fr[k] <= hi - 1)
                err($sformatf("M4: window [%0d, %0d] straddles a blanking-width change at frame %0d", lo, hi, bw_fr[k]));
        end
    end

    // ---------------------------------------------------------------- the host
    // the configuration the host applies (shadows == the last applied after every accepted apply)
    integer c_m = 0, c_sign = 0, c_range = 0, c_ibias = 3, c_cpf = 8, c_bp = 1, c_bn = 0, c_fast = 1, c_dwa = 1,
            c_c1 = 3, c_blank = 7, c_atp = 0, c_tctl = 0;
    integer seed = 1;
    integer fast_mode = 2;                            // +fast=0: 64 kHz only, 1: 128 kHz only, 2: mixed
    integer tel_max = 4;
    function automatic integer rmax(input integer r);
        case (r) 0: return 1023; 1: return 127; 2: return 255; 3: return 511; default: return 1023; endcase
    endfunction
    task automatic wait_nopend();
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    task automatic drain();
        logic [7:0] s; logic [15:0] q; logic [23:0] d; bit ok;
        while (DRDY_N === 1'b0) r14_sample(s, q, d, ok);
    endtask
    task automatic idle_for(input real us);
        real t_end;
        t_end = $realtime + us * 1000.0;
        while ($realtime < t_end) begin
            if (DRDY_N === 1'b0) drain(); else #500;
        end
    endtask
    task automatic wr(input logic [6:0] a, input logic [7:0] v);
        wait_nopend();
        r14_write(a, v);
    endtask
    task automatic write_cfg();
        wr(7'h20, 8'(c_m >> 8)); wr(7'h21, 8'(c_m & 255)); wr(7'h22, 8'((c_sign << 4) | c_range));
        wr(7'h23, 8'(c_ibias)); wr(7'h24, 8'(c_cpf)); wr(7'h25, 8'((c_bn << 4) | c_bp)); wr(7'h26, 8'(c_fast));
        wr(7'h27, 8'((c_dwa << 4) | c_c1)); wr(7'h28, 8'(c_blank));
    endtask
    task automatic write_test();                      // the test bracket (unlocked only around the writes)
        wr(7'h11, 8'h3C); wr(7'h60, 8'(c_atp)); wr(7'h61, 8'(c_tctl)); wr(7'h11, 8'h00);
    endtask
    task automatic rand_cfg();
        c_range = $urandom % 5;
        c_m = $urandom % (rmax(c_range) + 1);
        c_sign = $urandom % 2;
        c_ibias = ($urandom % 4 == 0) ? 2 : 3;
        c_cpf = $urandom % 16; c_bp = $urandom % 4; c_bn = $urandom % 4;
        c_fast = ($urandom % 3 == 0) ? 0 : 1;
        if (fast_mode == 0) c_fast = 0;
        if (fast_mode == 1) c_fast = 1;
        c_dwa = $urandom % 2; c_c1 = $urandom % 6; c_blank = 1 + $urandom % 15;
    endtask
    task automatic rand_timers();                     // only in IDLE or RUN (5.4 step 4)
        wr(7'h51, 8'($urandom % tel_max));            // T_ELEC 0..tel_max-1 ms
        wr(7'h52, 8'(29 + $urandom % 8));             // T_REC
        wr(7'h53, 8'(3 + $urandom % 4));              // T_PRE
        wr(7'h54, 8'(13 + $urandom % 4));             // T_RST
        wr(7'h50, 8'(5 + $urandom % 2));              // T_WARM
    endtask
    task automatic cmd(input logic [7:0] c);
        wait_nopend();
        r14_cmd(c);
        wait_nopend();
    endtask
    task automatic nr_step();                         // one step of the signed value, everything else unchanged
        integer sv, mx;
        sv = c_sign ? -c_m : c_m;
        mx = rmax(c_range);
        sv = sv + (($urandom % 2) ? 1 : -1);
        if (sv > mx) sv = mx - 1;
        if (sv < -mx) sv = -mx + 1;
        c_sign = (sv < 0) ? 1 : (($urandom % 2 && sv == 0) ? 1 : 0);
        if (sv == 0) c_sign = (c_sign);               // M = 0: either sign (a sign-only change is accepted)
        c_m = (sv < 0) ? -sv : sv;
        wr(7'h20, 8'(c_m >> 8)); wr(7'h21, 8'(c_m & 255)); wr(7'h22, 8'((c_sign << 4) | c_range));
        cmd(8'h44);
    endtask
    task automatic soft_reset();
        wait_nopend();
        r14_cmd(8'hA5);
        #2000;
        c_m = 0; c_sign = 0; c_range = 0; c_ibias = 3; c_cpf = 8; c_bp = 1; c_bn = 0; c_fast = 1; c_dwa = 1;
        c_c1 = 3; c_blank = 7; c_atp = 0; c_tctl = 0;
        r14_write(7'h06, 8'hFF);
    endtask

    integer it, st, r, n_ops = 0;
    real tmax;
    integer n_cmd [0:15];
    initial begin
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        if (!$value$plusargs("fast=%d", fast_mode)) fast_mode = 2;
        if (!$value$plusargs("telmax=%d", tel_max)) tel_max = 4;
        r = $urandom(seed);
        for (it = 0; it < 16; it++) n_cmd[it] = 0;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        #3000;
        r14_write(7'h06, 8'hFF);
        rand_cfg(); write_cfg(); rand_timers();
        cmd(8'h11);
        if (!$value$plusargs("tmax=%f", tmax)) tmax = 400.0;
        for (it = 0; it < 4000 && $realtime < tmax * 1.0e6; it++) begin
            idle_for((dut.seq_state == ST_RUN) ? (20.0 + ($urandom % 4000)) : (20.0 + ($urandom % 800)));
            st = dut.seq_state;
            r = $urandom % 100;
            n_ops = n_ops + 1;
            if ($urandom % 40 == 0) begin ovl_val = $urandom % 2; ovl_left = 5 + $urandom % 300; end
            case (st)
                ST_IDLE: begin
                    if (r < 15) begin rand_cfg(); write_cfg(); cmd(8'h33); n_cmd[0]++; end          // APPLY in IDLE
                    else if (r < 25) begin rand_cfg(); write_cfg(); cmd(8'h44); n_cmd[1]++; end     // APPLY_NR in IDLE
                    else if (r < 30) begin c_atp = $urandom % 32; c_tctl = ($urandom % 3 == 0) ? ($urandom % 4) : 0;
                                           write_test(); end
                    else begin rand_timers(); rand_cfg(); write_cfg(); cmd(8'h11); n_cmd[2]++; end    // START
                end
                ST_WARMUP: begin
                    if (r < 4) begin rand_cfg(); write_cfg(); cmd(($urandom % 2) ? 8'h33 : 8'h44); n_cmd[3]++; end
                    else if (r < 5) begin cmd(8'h22); n_cmd[4]++; end
                end
                ST_RECOVER, ST_WAIT_E, ST_ALIGN, ST_FILL: begin
                    if (r < 6) begin nr_step(); n_cmd[5]++; end
                    else if (r < 8) begin rand_cfg(); write_cfg(); cmd(8'h33); n_cmd[6]++; end
                    else if (r < 9) begin cmd(8'h22); n_cmd[7]++; end
                    else if (r < 10) begin cmd(8'h55); end
                end
                ST_RUN: begin
                    if (r < 35) begin nr_step(); n_cmd[8]++; end
                    else if (r < 47) begin rand_cfg(); write_cfg(); cmd(8'h33); n_cmd[9]++; end
                    else if (r < 52) begin rand_timers(); end
                    else if (r < 55) begin cmd(8'h22); n_cmd[10]++; end
                    else if (r < 58) begin cmd(8'h55); end
                    else if (r < 60) begin soft_reset(); n_cmd[11]++; end
                    else if (r < 63) begin c_atp = $urandom % 32; c_tctl = ($urandom % 3 == 0) ? ($urandom % 4) : 0;
                                           write_test(); cmd(8'h33); n_cmd[12]++; end
                end
                default: ;                                // PRE, PULSE: wait
            endcase
        end
        $display("tb_a48_rand seed %0d: %0d ops, %0.1f ms; setting changes %0d (one-step %0d), pulses %0d, releases %0d, stored %0d (CHANGED %0d, required %0d); CHOP1 boundaries %0d, rate switches %0d, blank-width changes %0d; cmds IDLE APPLY %0d NR %0d START %0d, WARMUP A/NR %0d STOP %0d, pre-RUN NR %0d APPLY %0d STOP %0d, RUN NR %0d APPLY %0d STOP %0d SOFT %0d TEST %0d; SPI errors %0d; errors %0d",
                 seed, n_ops, $realtime / 1e6, n_changes, n_steps, n_pulses, n_rel, n_stored, n_changed, n_need,
                 n_c1, n_cf, n_bw, n_cmd[0], n_cmd[1], n_cmd[2], n_cmd[3], n_cmd[4], n_cmd[5], n_cmd[6], n_cmd[7],
                 n_cmd[8], n_cmd[9], n_cmd[10], n_cmd[11], n_cmd[12], spi_errors, errors);
        $finish;
    end
endmodule
`default_nettype wire
