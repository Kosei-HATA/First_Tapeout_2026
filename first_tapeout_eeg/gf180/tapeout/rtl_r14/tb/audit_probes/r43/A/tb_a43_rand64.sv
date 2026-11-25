// audit 39 A probe: random episodes through the SPI pins, with pin-level invariants written from the requirements
// (not from the RTL or fsm_spec):
//   P1  every analog setting pin (OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P/N, DWA_EN, TEST_CFG[5:0], CHOP_EN) and
//       AFE_RST change only at e25 of a tick frame, or inside a reset (ANA-01, SEQ-13)
//   P2  CHOP_EN changes only in chopper phase A (CHOP = CHOP_OUT = 1) unless a reset
//   P3  OFEN is a thermometer, OFM fits the range, OFM = OFS = 0 with OFEN = 0
//   P4  AFE_RST falls only into RECOVER; it falls >= T_WARM ms after the last setting change made while it was high
//       from WARMUP, and >= T_RST x 8 frames after its rise from PULSE; a setting change other than a one-step DAC
//       change while AFE_RST = 0 is followed by an AFE_RST rise >= 20 us later (or by IDLE)
//   S1  every stored output's window (inputs [1024(n-2), 1024n+1021]) lies inside one AFE_RST-low interval that started
//       >= 8 T_REC frames before it; no setting change other than a one-step DAC change, no chopper-rate, BLANK-width
//       or CHOP1-rate switch, falls inside the window or after its release; CHANGED = 1 exactly for the 3 + T_ELEC
//       outputs after a one-step change in RUN (the longer remaining kept, cancelled outside RUN); a window that starts
//       less than T_ELEC ms after a one-step change (any state) carries CHANGED; OVL = a hit (an extreme code with >= 4
//       extremes in the last 32 frames) in frames [1024(n-2), 1024n+1023]
`timescale 1ns / 1ps
`default_nettype none
module tb_a43_rand64;   // audit 43 A: tb_a39_rand with wide timers (T_REC/T_PRE/T_RST up to 255, T_ELEC 0..5) and more rate changes
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
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

    integer seed = 39;
    integer errors = 0, nstores = 0, nchk_ovl = 0, nchg = 0, nnr = 0, nbig = 0, nrel = 0, nsoft = 0, nepis = 0;
    integer n_ovl1 = 0, n_chg_run = 0, n_ticks = 0;
    task automatic err(input string m);
        errors = errors + 1;
        if (errors <= 40) $display("ERROR @%0t ns: %s", $time / 1000, m);
    endtask

    // ---------------------------------------------------------------- frames, codes, overload hits
    integer ovl_rate = 400000;
    integer frame_abs = -1;                   // current frame since the RESET_N release (frame 0 = first)
    logic   ovl_burst_on = 1'b0;
    integer burst_left = 0;
    bit     ext_hist [0:31];
    bit     hit_of [0:(1 << 20) - 1];          // 1 M frames ~ 1.02 s
    integer k_;
    initial for (k_ = 0; k_ < 32; k_ = k_ + 1) ext_hist[k_] = 0;
    always @(posedge MCLK) begin
        if (dut.cycle == 5'd31 && dut.tm_rst_n) frame_abs <= frame_abs + 1;  // this edge starts the next frame
        if (dut.cycle == 5'd1) begin                                         // CODE changes at e2 (as the ADC's)
            if (burst_left > 0) begin
                CODE <= ($urandom(seed) % 2) ? 5'd31 : 5'd0;
                burst_left = burst_left - 1;
            end else if (($urandom(seed) % ovl_rate) == 0) begin
                burst_left = 2 + ($urandom(seed) % 200);
                CODE <= 5'd16;
            end else if (($urandom(seed) % 3000) == 0) begin
                CODE <= ($urandom(seed) % 2) ? 5'd31 : 5'd0;                 // a lone extreme
            end else begin
                CODE <= 5'd12 + 5'($urandom(seed) % 8);
            end
        end
    end
    // the CIC and the detector take CODE in cycle 3
    always @(posedge MCLK) if (dut.cycle == 5'd3 && dut.tm_rst_n && frame_abs >= 0) begin : hits
        integer c, j;
        bit e;
        e = (CODE == 5'd0) || (CODE == 5'd31);
        for (j = 31; j > 0; j = j - 1) ext_hist[j] = ext_hist[j - 1];
        ext_hist[0] = e;
        c = 0;
        for (j = 0; j < 32; j = j + 1) c = c + ext_hist[j];
        hit_of[frame_abs] = e && (c >= 4);
    end

    // ---------------------------------------------------------------- pin history
    logic [9:0] p_ofm; logic p_ofs; logic [3:0] p_ofen, p_cpf; logic [1:0] p_ib, p_bp, p_bn; logic p_dwa, p_cen;
    logic [5:0] p_tc; logic p_afe; logic p_fast; logic [3:0] p_blank; logic [2:0] p_c1;
    logic       prev_tick = 1'b0;
    integer last_big = -100000000, last_nr = -100000000, last_nr_te = 0;
    integer last_rise = -100000000, last_fall = -100000000, last_fall_trec = 0;
    integer last_rise_mclk = 0, mclk_n = 0, big_while_on_mclk = -1;
    bit     dirty = 0;                       // a big change while AFE_RST = 0, not yet followed by an AFE_RST rise
    integer last_chg_hi = -100000000;        // last setting change while AFE_RST = 1 (frame)
    integer last_switch = -100000000;        // chopper rate, BLANK width or CHOP1 rate switch (frame)
    integer chg_until = 0;                   // CHANGED expected for output index < chg_until (current RUN)
    logic [3:0] prev_state = 4'd0;
    integer blank_w_cur = 0, blank_w_prev = -1;
    logic   blank_q = 1'b0;
    logic   init_done = 1'b0;
    // a setting-change classification: 1 = the DAC's signed value moved by one step, the rest equal
    function automatic integer sv(input logic [9:0] m, input logic s, input logic [3:0] en);
        sv = (en == 4'd0) ? 0 : (s ? -m : m);
    endfunction

    always @(posedge MCLK) begin
        mclk_n = mclk_n + 1;
        #1;
        if (!RESET_N || !dut.tm_rst_n) begin
            init_done = 1'b0;
        end else if (!init_done) begin
            p_ofm = OFM; p_ofs = OFS; p_ofen = OFEN; p_cpf = CPF_TRIM; p_ib = AFE_IBIAS; p_bp = BTRIM_P;
            p_bn = BTRIM_N; p_dwa = DWA_EN; p_cen = CHOP_EN; p_tc = TEST_CFG[5:0]; p_afe = AFE_RST;
            p_fast = dut.u_clkgen.fast; p_c1 = dut.u_chop1.rate_q; init_done = 1'b1;
        end else begin : pins
            bit set_ch, dac_ch, in_reset, at_tick;
            integer f;
            f = frame_abs;
            in_reset = !dut.rst_n;
            at_tick = prev_tick && (dut.cycle == 5'd25);
            set_ch = (OFEN !== p_ofen) || (CPF_TRIM !== p_cpf) || (AFE_IBIAS !== p_ib) || (BTRIM_P !== p_bp) ||
                     (BTRIM_N !== p_bn) || (DWA_EN !== p_dwa) || (CHOP_EN !== p_cen) || (TEST_CFG[5:0] !== p_tc);
            dac_ch = (OFM !== p_ofm) || (OFS !== p_ofs);
            // P3
            if (!(OFEN == 4'd0 || OFEN == 4'd1 || OFEN == 4'd3 || OFEN == 4'd7 || OFEN == 4'd15)) err($sformatf("OFEN %b not a thermometer", OFEN));
            if (OFEN == 4'd0 && (OFM != 0 || OFS != 0)) err("OFM/OFS nonzero with the DAC off");
            if (OFEN == 4'd1 && OFM > 127) err($sformatf("OFM %0d beyond range 1", OFM));
            if (OFEN == 4'd3 && OFM > 255) err($sformatf("OFM %0d beyond range 2", OFM));
            if (OFEN == 4'd7 && OFM > 511) err($sformatf("OFM %0d beyond range 3", OFM));
            // P1
            if ((set_ch || dac_ch || AFE_RST !== p_afe) && !at_tick && !in_reset)
                err($sformatf("a setting pin or AFE_RST changed at cycle %0d (not e25 of a tick), state %0d", dut.cycle, dut.seq_state));
            // P2
            if (CHOP_EN !== p_cen && !in_reset && !(CHOP === 1'b1 && CHOP_OUT === 1'b1))
                err("CHOP_EN changed outside chopper phase A");
            // classify the change
            if (set_ch || dac_ch) begin
                integer d;
                d = sv(OFM, OFS, OFEN) - sv(p_ofm, p_ofs, p_ofen);
                if (!set_ch && dac_ch && (OFEN == p_ofen) && (d >= -1) && (d <= 1) && !in_reset) begin
                    last_nr = f; last_nr_te = dut.t_elec; nnr = nnr + 1;
                    if (AFE_RST !== 1'b0 && p_afe !== 1'b0) last_chg_hi = f;
                    // a one-step change in RUN: CHANGED on the next 3 + T_ELEC outputs (the longer kept)
                end else begin
                    last_big = f; nbig = nbig + 1;
                    if (p_afe === 1'b0 && AFE_RST === 1'b0) begin dirty = 1; big_while_on_mclk = mclk_n; end
                    else last_chg_hi = f;
                end
            end
            // P4: AFE_RST edges
            if (AFE_RST === 1'b1 && p_afe === 1'b0) begin
                if (dirty && !in_reset && dut.seq_state != ST_IDLE && (mclk_n - big_while_on_mclk) < 655)
                    err($sformatf("AFE_RST rose %0d MCLK after a pulsed setting change (< 20 us)", mclk_n - big_while_on_mclk));
                dirty = 0; last_rise = f; last_rise_mclk = mclk_n;
            end
            if (AFE_RST === 1'b0 && p_afe === 1'b1) begin
                nrel = nrel + 1;
                if (dut.seq_state != ST_RECOVER) err($sformatf("AFE_RST released into state %0d", dut.seq_state));
                if (prev_state == ST_WARMUP && (f - last_chg_hi) < 1024 * 5)
                    err($sformatf("AFE_RST released %0d frames after a change made in reset (< T_WARM 5 ms)", f - last_chg_hi));
                if (prev_state == ST_PULSE && (mclk_n - last_rise_mclk) < 8 * 32 * 13)
                    err($sformatf("AFE_RST pulse %0d MCLK (< T_RST 13)", mclk_n - last_rise_mclk));
                last_fall = f; last_fall_trec = dut.t_rec;
            end
            // rate, CHOP1 and BLANK-width switches
            if (dut.u_clkgen.fast !== p_fast || dut.u_chop1.rate_q !== p_c1) last_switch = f;
            p_ofm = OFM; p_ofs = OFS; p_ofen = OFEN; p_cpf = CPF_TRIM; p_ib = AFE_IBIAS; p_bp = BTRIM_P;
            p_bn = BTRIM_N; p_dwa = DWA_EN; p_cen = CHOP_EN; p_tc = TEST_CFG[5:0]; p_afe = AFE_RST;
            p_fast = dut.u_clkgen.fast; p_c1 = dut.u_chop1.rate_q;
        end
        // the blanking pulse widths (gen_blank only; ADC_ZERO holds CHOP_BLANK)
        if (dut.gen_blank) blank_w_cur = blank_w_cur + 1;
        if (!dut.gen_blank && blank_q) begin
            if (blank_w_prev >= 0 && blank_w_cur != blank_w_prev) last_switch = frame_abs;
            blank_w_prev = blank_w_cur; blank_w_cur = 0;
        end
        blank_q = dut.gen_blank;
        if (dut.seq_state != ST_RUN) chg_until = 0;
        if (dut.t_elec < last_nr_te) last_nr_te = dut.t_elec;
        if (!dut.rst_n) begin dirty = 0; chg_until = 0; end
        prev_state = dut.seq_state;
        prev_tick = dut.tick;
        if (dut.tick) n_ticks = n_ticks + 1;
    end

    // the marks: every APPLY_NR accepted in RUN (the sequencer's mark, whose decision tb_seq checks against fsm_spec)
    always @(posedge MCLK) if (dut.seq_mark && dut.rst_n && !dut.soft_req) begin
        if (((frame_abs) / 1024) + 3 + dut.t_elec > chg_until) chg_until = (frame_abs / 1024) + 3 + dut.t_elec;
        n_chg_run = n_chg_run + 1;
    end
    // ---------------------------------------------------------------- stores
    always @(posedge MCLK) if (dut.seq_store && dut.cic_stb && !dut.soft_req && dut.rst_n) begin : stores
        integer n, ws, we, j;
        bit ovl_exp, chg_exp, chg_need;
        logic [7:0] st;
        n = dut.seq_cnt;
        st = dut.smp_status;
        ws = 1024 * (n - 2);
        we = 1024 * n + 1021;
        nstores = nstores + 1;
        if (frame_abs != 1024 * n + 1023) err($sformatf("store of output %0d in frame %0d", n, frame_abs));
        // OVL
        ovl_exp = 0;
        for (j = ws; j <= 1024 * n + 1023; j = j + 1) if (j >= 0 && hit_of[j]) ovl_exp = 1;
        nchk_ovl = nchk_ovl + 1;
        if (ovl_exp) n_ovl1 = n_ovl1 + 1;
        if (st[SMP_OVL_LSB] !== ovl_exp) err($sformatf("output %0d: OVL %b, expected %b", n, st[SMP_OVL_LSB], ovl_exp));
        // AFE_RST low through the window and released >= 8 T_REC frames before it
        if (AFE_RST !== 1'b0 || last_rise > last_fall || ws < last_fall + 8 * last_fall_trec)
            err($sformatf("output %0d: window from frame %0d, AFE_RST released at %0d (T_REC %0d), last rise %0d",
                          n, ws, last_fall, last_fall_trec, last_rise));
        // no big change, no rate / BLANK / CHOP1 switch inside the window or since its start
        if (last_big >= ws - 1) err($sformatf("output %0d: a setting change at frame %0d inside its window from %0d", n, last_big, ws));
        if (last_switch > ws) err($sformatf("output %0d: a rate / BLANK / CHOP1 switch at frame %0d inside its window from %0d", n, last_switch, ws));
        if (dirty) err($sformatf("output %0d stored after a pulsed change without AFE_RST", n));
        // CHANGED
        chg_exp = (n < chg_until);
        chg_need = (last_nr >= ws - 1 && last_nr <= we) || (last_nr + 1 + 1024 * last_nr_te > ws && last_nr > -1000000);
        if (st[SMP_CHANGED_LSB]) nchg = nchg + 1;
        if (st[SMP_CHANGED_LSB] !== chg_exp)
            err($sformatf("output %0d: CHANGED %b, expected %b (marks until %0d)", n, st[SMP_CHANGED_LSB], chg_exp, chg_until));
        if (chg_need && !st[SMP_CHANGED_LSB])
            err($sformatf("output %0d: window from %0d, one-step change at frame %0d (T_ELEC %0d), no CHANGED",
                          n, ws, last_nr, last_nr_te));
    end

    // ---------------------------------------------------------------- the random host
    logic [7:0] rv;
    task automatic wait_us(input integer us);
        #(us * 1000.0);
    endtask
    task automatic wait_state(input logic [3:0] s, input integer max_us);
        integer t;
        t = 0;
        while (dut.seq_state !== s && t < max_us) begin #1000.0; t = t + 1; end
    endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        wait_us(20 + ($urandom(seed) % 15));
    endtask
    // random shadow settings (mostly legal and consistent)
    task automatic rand_shadow(input bit allow_rate);
        integer r, m;
        r = $urandom(seed) % 5;
        m = (r == 0) ? ($urandom(seed) % 1024) : ($urandom(seed) % ((r == 1) ? 128 : (r == 2) ? 256 : (r == 3) ? 512 : 1024));
        if (($urandom(seed) % 10) == 0) m = $urandom(seed) % 1024;           // sometimes beyond the range (CFG_ERR)
        r14_write(7'h20, 8'(m >> 8));
        r14_write(7'h21, 8'(m));
        r14_write(7'h22, {3'd0, 1'($urandom(seed) % 2), 1'b0, 3'(r)});
        if (($urandom(seed) % 3) == 0) r14_write(7'h24, 8'($urandom(seed) % 16));
        if (($urandom(seed) % 4) == 0) r14_write(7'h25, 8'($urandom(seed)) & 8'h33);
        if (($urandom(seed) % 5) == 0) r14_write(7'h23, 8'($urandom(seed) % 4));
        if (allow_rate) r14_write(7'h26, 8'h00);   // audit 43 A: 64 kHz throughout
        if (($urandom(seed) % 3) == 0) r14_write(7'h27, {3'd0, 1'($urandom(seed) % 2), 1'b0, 3'($urandom(seed) % 6)});
        if (($urandom(seed) % 3) == 0) r14_write(7'h28, 8'(1 + $urandom(seed) % 15));
    endtask
    task automatic step_shadow;                 // a one-step DAC change from the active value (or a sign flip at 0)
        integer m, s, v, nv, r;
        m = dut.u_regs.a_m; s = dut.u_regs.a_sign; r = dut.u_regs.a_range;
        v = s ? -m : m;
        nv = v + ((($urandom(seed) % 2) == 0) ? 1 : -1);
        if (($urandom(seed) % 8) == 0) nv = v;   // a change of nothing
        if (nv > 1023) nv = 1022;
        if (nv < -1023) nv = -1022;
        r14_write(7'h20, 8'(((nv < 0) ? -nv : nv) >> 8));
        r14_write(7'h21, 8'((nv < 0) ? -nv : nv));
        r14_write(7'h22, {3'd0, 1'(nv < 0), 1'b0, 3'(r)});
    endtask
    task automatic test_bracket;
        r14_write(7'h11, 8'h3C);
        r14_write(7'h60, 8'($urandom(seed)) & 8'h1F);
        r14_write(7'h61, 8'($urandom(seed) % 4));
        r14_write(7'h11, 8'h00);
    endtask
    task automatic test_clear;
        r14_write(7'h11, 8'h3C);
        r14_write(7'h60, 8'h00);
        r14_write(7'h61, 8'h00);
        r14_write(7'h11, 8'h00);
    endtask
    task automatic set_timers;               // audit 43 A: wide timer ranges, written in IDLE or RUN (5.4 step 4)
        if (dut.seq_state == ST_IDLE || dut.seq_state == ST_RUN) begin
            r14_write(7'h51, 8'($urandom(seed) % 6));
            r14_write(7'h52, 8'((($urandom(seed) % 4) == 0) ? (29 + $urandom(seed) % 227) : (29 + $urandom(seed) % 8)));
            r14_write(7'h53, 8'((($urandom(seed) % 4) == 0) ? (3 + $urandom(seed) % 253) : (3 + $urandom(seed) % 3)));
            r14_write(7'h54, 8'((($urandom(seed) % 4) == 0) ? (13 + $urandom(seed) % 243) : (13 + $urandom(seed) % 4)));
            if (dut.seq_state == ST_IDLE) r14_write(7'h50, 8'(5 + $urandom(seed) % 3));
        end
    endtask

    integer ep, i, a, nruns, t_end_us;
    initial begin
        if (!$value$plusargs("seed=%d", seed)) seed = 39;
        if (!$value$plusargs("t_end_us=%d", t_end_us)) t_end_us = 300000;
        if (!$value$plusargs("ovl_rate=%d", ovl_rate)) ovl_rate = 400000;
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(negedge MCLK);
        ep = 0;
        while ($time / 1000 < t_end_us) begin
            ep = ep + 1; nepis = ep;
            a = $urandom(seed) % 100;
            if (dut.seq_state == ST_IDLE) begin
                set_timers;
                rand_shadow(1);
                if (($urandom(seed) % 6) == 0) test_bracket; else if (($urandom(seed) % 3) == 0) test_clear;
                if (($urandom(seed) % 4) == 0) cmd(8'h44);                 // APPLY_NR in IDLE
                if (($urandom(seed) % 4) == 0) cmd(8'h33);                 // APPLY in IDLE
                cmd(8'h11);                                                // START
                // something in WARMUP sometimes
                if (($urandom(seed) % 4) == 0) begin
                    wait_us(500 + $urandom(seed) % 3000);
                    if (dut.seq_state == ST_WARMUP) begin rand_shadow(1); cmd((($urandom(seed) % 2) == 0) ? 8'h33 : 8'h44); end
                end
            end else if (dut.seq_state == ST_WARMUP || dut.seq_state == ST_PRE || dut.seq_state == ST_PULSE) begin
                wait_us(100);
            end else if (dut.seq_state == ST_RECOVER || dut.seq_state == ST_WAIT_E || dut.seq_state == ST_ALIGN || dut.seq_state == ST_FILL) begin
                if (a < 25) begin step_shadow; cmd(8'h44); end                         // APPLY_NR before RUN
                else if (a < 30) begin rand_shadow(0); cmd(8'h33); end                // APPLY before RUN
                else if (a < 35) cmd(8'h55);                                          // FLUSH
                wait_us(50 + $urandom(seed) % 1500);
            end else if (dut.seq_state == ST_RUN) begin
                if (a < 45) begin step_shadow; cmd(8'h44); wait_us(200 + $urandom(seed) % 6000); end
                else if (a < 55) begin rand_shadow(($urandom(seed) % 2) == 0); cmd(8'h33); end
                else if (a < 62) begin cmd(8'h55); wait_us($urandom(seed) % 3000); end
                else if (a < 66) begin set_timers; wait_us(1000); end
                else if (a < 70) cmd(8'h22);                                          // STOP
                else if (a < 74) begin r14_cmd(8'hA5); nsoft = nsoft + 1; wait_us(5); end   // SOFT_RESET
                else if (a < 75) begin test_bracket; rand_shadow(0); cmd(8'h33); end
                else wait_us(1000 + $urandom(seed) % 8000);
            end else begin
                wait_us(100);
            end
            // keep the FIFO from filling (the checks look at every store attempt anyway)
            if (dut.u_fifo.level > 5) begin
                logic [7:0] s_; logic [15:0] q_; logic [23:0] d_; bit ok_;
                r14_sample(s_, q_, d_, ok_);
            end
        end
        $display("tb_a43_rand seed %0d: %0d episodes, %0d ticks, %0d stores (%0d with OVL, %0d CHANGED; %0d RUN steps), %0d one-step and %0d other setting changes, %0d AFE_RST releases, %0d SOFT_RESETs; %0d errors",
                 seed, nepis, n_ticks, nstores, n_ovl1, nchg, n_chg_run, nnr, nbig, nrel, nsoft, errors);
        if (errors == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end
endmodule
`default_nettype wire
