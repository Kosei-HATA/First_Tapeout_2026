// tb_a31_inv - audit round 31 (A). A random host drives eeg_digital_top (commands at random times and states, shadow
// and timer writes, one-step APPLY_NR, rate changes, SOFT_RESET), and a monitor checks the analog constraints at the
// pins, written apart from fsm_spec:
//   W1 a stored sample's sinc^3 window holds no AFE_RST = 1 and starts >= 0.22 ms after the last release
//   W2 no full setting change (pins, effective chop rate, blank width; CHOP1 rate only at the window's first frame)
//      inside a stored window
//   W3 every stored window that holds a one-step DAC change (or its T_ELEC settling) carries CHANGED, and no other
//   A1 AFE_RST high >= 100 us; a release >= 100 us after the last change while held; a rise < 20 us after a DAC change
//      while running only on the STOP / reset path (held >= 5 ms)
//   A2 every pin change at e25 of a tick frame (128 kHz: frame 1 mod 8, 64 kHz: frame 3 mod 16), or in a reset
`timescale 1ns / 1ps
`default_nettype none
module tb_a31_inv;
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
    integer burst = 0, bstep = 1;
    always @(posedge MCLK) if (dut.cycle == 5'd1) begin
        if (burst == 0 && ($urandom % 3000) == 0) begin burst = 1 + $urandom % 300; bstep = 1 + $urandom % 12; end
        if (burst > 0) begin
            burst = burst - 1;
            CODE <= (burst % bstep == 0) ? (($urandom % 2) ? 5'd31 : 5'd0) : 5'd13 + 5'($urandom % 6);
        end else CODE <= 5'd13 + 5'($urandom % 6);
    end
    // own overload detector (FLG-04: >= 4 extreme codes among the last 32 frames), from CODE at the CIC input (cycle 3)
    logic [31:0] owin = 32'd0;
    integer ohit_fr [0:4095];
    integer nhit = 0, novl_store = 0, ndflag = 0;
    logic hit_now = 1'b0, hit_q = 1'b0, dfl_q = 1'b0;
    logic [3:0] st_at_hit = 4'd0;

    // ------------------------------------------------------------------ monitor
    integer fr = -1, cy = 0;                       // frame since RESET_N release (own count), frame cycle
    integer errs = 0, nstore = 0, nchg = 0, nsteps = 0, nfull_run = 0, nrel = 0, nrise = 0, nextra = 0;
    integer ncmd[0:4];
    localparam integer NEV = 4096;
    integer ev_fr [0:NEV-1];                       // events: frame, kind (1 full, 2 step, 3 chop1), T_ELEC
    integer ev_kind [0:NEV-1];
    integer ev_te [0:NEV-1];
    integer nev = 0, n64 = 0, nall = 0;
    integer afe_rise_fr = -100000, afe_fall_fr = -100000;
    real    afe_rise_t = -1.0e9, afe_fall_t = -1.0e9, t_held_change = -1.0e9, t_dac_run = -1.0e9;
    logic [35:0] pv, pv_q;  // OFM 35:26, OFS 25, OFEN 24:21, the rest 20:0
    logic afe_q = 1'b1, fast_q = 1'b1, rst_seen = 1'b1, in_reset_q = 1'b1;
    logic [2:0] c1_q = 3'd3;
    integer te_q = 0, bw_last = -1, blank_start_fr = 0;
    real    t_blank_rise = 0.0;
    function automatic integer sv_of(input logic [9:0] m, input logic s);
        return s ? -integer'(m) : integer'(m);
    endfunction
    task automatic fail(input string m);
        errs = errs + 1;
        if (errs <= 40) $display("VIOLATION @%0t (frame %0d cycle %0d, state %0d): %s", $time, fr, cy, dut.seq_state, m);
    endtask
    task automatic add_ev(input integer f, input integer k, input integer te);
        ev_fr[nev % NEV] = f; ev_kind[nev % NEV] = k; ev_te[nev % NEV] = te; nev = nev + 1;
    endtask
    always @(negedge RESET_N) begin fr = -1; end
    always @(posedge CHOP_BLANK) begin t_blank_rise = $realtime; blank_start_fr = fr; end
    always @(negedge CHOP_BLANK) if (TEST_CFG[5] === 1'b0 && RESET_N) begin : bw
        integer w;
        w = $rtoi(($realtime - t_blank_rise) / TMCLK + 0.5);
        if (bw_last >= 0 && w != bw_last && fr > 2) add_ev(blank_start_fr, 1, 0);
        bw_last = w;
    end
    always @(negedge MCLK) begin : mon
        integer ws, we, i, f, k, te, aff, chg;
        logic in_reset;
        if (!RESET_N) begin
            rst_seen = 1'b1;
        end else begin
            if (CMP_STROBE) begin fr = fr + 1; cy = 0; nall = nall + 1; if (!dut.u_clkgen.fast) n64 = n64 + 1; end else cy = cy + 1;
            hit_q = hit_now; hit_now = 1'b0;
            if (cy == 3) begin : odet
                logic ext; integer c;
                ext = (CODE == 5'd0 || CODE == 5'd31);
                owin = {owin[30:0], ext};
                c = $countones(owin);
                if (ext && c >= 4) begin
                    hit_now = 1'b1; ohit_fr[nhit % 4096] = fr; nhit = nhit + 1; st_at_hit = dut.seq_state;
                end
            end
            // DFLAG.OVL rises only right after a hit in FILL or RUN
            if (dut.u_regs.dflag[1] === 1'b1 && dfl_q === 1'b0 && !rst_seen) begin
                ndflag = ndflag + 1;
                if (!(hit_q && (st_at_hit == ST_FILL || st_at_hit == ST_RUN)))
                    fail("O1: DFLAG.OVL set without a hit in FILL or RUN");
            end
            if (hit_q && (st_at_hit == ST_FILL || st_at_hit == ST_RUN) && dut.u_regs.dflag[1] !== 1'b1 && !in_reset_q)
                fail("O1: a hit in FILL or RUN did not set DFLAG.OVL");
            in_reset = rst_seen || !dut.rst_n || dut.soft_req;
            pv = {OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, CHOP_EN, DWA_EN, TEST_CFG[5:0], 3'b000};
            // ---- pin changes
            if (pv !== pv_q && !rst_seen) begin
                logic dac_only;
                integer d;
                dac_only = (pv[20:0] === pv_q[20:0]) && (OFEN === pv_q[24:21]);
                d = sv_of(OFM, OFS) - sv_of(pv_q[35:26], pv_q[25]);
                if (!in_reset && !(cy == 25 && ((dut.u_clkgen.fast && fr % 8 == 1) || (!dut.u_clkgen.fast && fr % 16 == 3))))
                    fail($sformatf("A2: pin change outside e25 of a tick frame (0x%09h -> 0x%09h)", pv_q, pv));
                if (dac_only && OFEN !== 4'd0 && (d == 1 || d == -1)) begin
                    add_ev(fr, 2, te_q); nsteps = nsteps + 1;
                end else if (dac_only && d == 0) begin
                    ;                                              // the sign alone with M = 0: the plates stay
                end else begin
                    add_ev(fr, 1, 0);
                    if (AFE_RST === 1'b0 && afe_q === 1'b0) nfull_run = nfull_run + 1;
                end
                if (AFE_RST === 1'b1 && afe_q === 1'b1) t_held_change = $realtime;
                else if (AFE_RST === 1'b1 && afe_q === 1'b0) t_held_change = $realtime;   // with the rise (reset)
                if (AFE_RST === 1'b0 && pv[35:21] !== pv_q[35:21]) t_dac_run = $realtime;
            end
            // ---- effective chop rate and CHOP1 rate
            if (dut.u_clkgen.fast !== fast_q && !rst_seen) add_ev(fr, 1, 0);
            if (dut.u_chop1.rate_q !== c1_q && !rst_seen) add_ev(fr, 3, 0);
            // ---- AFE_RST
            if (AFE_RST !== afe_q && !rst_seen) begin
                if (!in_reset && !(cy == 25 && ((dut.u_clkgen.fast && fr % 8 == 1) || (!dut.u_clkgen.fast && fr % 16 == 3))))
                    fail("A2: AFE_RST edge outside e25 of a tick frame");
                if (AFE_RST === 1'b1) begin
                    afe_rise_fr = fr; afe_rise_t = $realtime; nrise = nrise + 1;
                end else begin
                    afe_fall_fr = fr; afe_fall_t = $realtime; nrel = nrel + 1;
                    if (afe_fall_t - afe_rise_t < 100000.0)
                        fail($sformatf("A1: AFE_RST high %0.1f us (< 100 us)", (afe_fall_t - afe_rise_t) / 1000.0));
                    if (afe_fall_t - t_held_change < 100000.0)
                        fail($sformatf("A1: release %0.1f us after a change while held (< 100 us)", (afe_fall_t - t_held_change) / 1000.0));
                    if (afe_rise_t - t_dac_run < 20000.0 && afe_fall_t - afe_rise_t < 5.0e6)
                        fail($sformatf("A1: AFE_RST rose %0.1f us after a DAC change and was released after %0.1f us",
                                       (afe_rise_t - t_dac_run) / 1000.0, (afe_fall_t - afe_rise_t) / 1000.0));
                end
            end
            // ---- a store: the window checks
            if (dut.seq_store === 1'b1) begin
                nstore = nstore + 1;
                if ((fr + 1) % 1024 != 0 || cy != 8) fail("store not at an output time");
                ws = fr + 1 - 3072; we = fr - 2;
                if (AFE_RST !== 1'b0) fail("W1: store with AFE_RST = 1");
                if ($test$plusargs("dbg") && ws - afe_fall_fr < 1100) $display("DBG store at frame %0d: window starts %0d frames after the release (frame %0d)", fr, ws - afe_fall_fr, afe_fall_fr);
                if (afe_fall_fr > ws - 227) fail($sformatf("W1: window starts %0d frames after the release", ws - afe_fall_fr));
                chg = dut.smp_status[SMP_CHANGED_LSB];
                aff = 0;
                for (i = (nev > NEV ? nev - NEV : 0); i < nev; i++) begin
                    f = ev_fr[i % NEV]; k = ev_kind[i % NEV]; te = ev_te[i % NEV];
                    if (k == 1 && f >= ws - 1 && f <= we) fail($sformatf("W2: full change at frame %0d in the window [%0d, %0d]", f, ws, we));
                    if (k == 3 && f > ws && f <= we) fail($sformatf("W2: CHOP1 rate change at frame %0d in the window [%0d, %0d]", f, ws, we));
                    if (k == 2 && f + 1 <= we && ws <= f + 1024 * te) aff = 1;
                end
                if (aff && !chg) fail("W3: a window holding a one-step change (or its T_ELEC) without CHANGED");
                begin : ovlchk
                    integer h, any;
                    any = 0;
                    for (h = (nhit > 4096 ? nhit - 4096 : 0); h < nhit; h++)
                        if (ohit_fr[h % 4096] > fr - 3072 && ohit_fr[h % 4096] <= fr) any = 1;
                    if (any != dut.smp_status[SMP_OVL_LSB])
                        fail($sformatf("O2: sample OVL %0d, hits in its three intervals %0d", dut.smp_status[SMP_OVL_LSB], any));
                    if (any) novl_store = novl_store + 1;
                end
                if (!aff && chg) nextra = nextra + 1;
                if (chg) nchg = nchg + 1;
            end
            if (dut.rst_n && !rst_seen) ;
            rst_seen = 1'b0;
        end
        pv_q = {OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, CHOP_EN, DWA_EN, TEST_CFG[5:0], 3'b000};
        dfl_q = dut.u_regs.dflag[1]; in_reset_q = !RESET_N || !dut.rst_n || dut.soft_req;
        afe_q = AFE_RST; fast_q = dut.u_clkgen.fast; c1_q = dut.u_chop1.rate_q; te_q = dut.t_elec;
    end

    // ------------------------------------------------------------------ random host
    logic [7:0] v;
    integer seed, seed0, ms_end, a, w, sv, mx, r, n, st;
    task automatic wait_cmd();
        while (dut.cmd_valid === 1'b1) #(500.0);
    endtask
    task automatic cmd(input logic [7:0] c, input integer idx);
        if ($urandom % 8 != 0) wait_cmd();
        r14_cmd(c); ncmd[idx] = ncmd[idx] + 1;
    endtask
    task automatic set_m(input integer svv, input integer rng);
        integer m; logic s;
        s = (svv < 0); m = s ? -svv : svv;
        wait_cmd();
        r14_write(7'h20, 8'(m >> 8)); r14_write(7'h21, 8'(m & 255)); r14_write(7'h22, {3'd0, s, 1'b0, 3'(rng)});
    endtask
    initial begin
        for (int q = 0; q < 5; q++) ncmd[q] = 0;
        if (!$value$plusargs("seed=%d", seed)) seed = 1;
        if (!$value$plusargs("ms=%d", ms_end)) ms_end = 200;
        seed0 = seed; void'($urandom(seed));
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_write(7'h50, 8'd5);
        set_m(40, 1);
        if ($test$plusargs("slow")) r14_write(7'h26, 8'h00);     // start at 64 kHz
        if ($test$plusargs("quiet")) begin                       // one START at frame 880 mod 1024, then wait
            while (fr % 1024 != 880) @(negedge MCLK);
            r14_cmd(CMD_START);
        end
        while (!$test$plusargs("quiet") && $realtime < ms_end * 1.0e6) begin
            a = $urandom % 1000;
            st = dut.seq_state;
            if (st == ST_IDLE) a = (a < 700) ? 0 : 999;
            else if (st == ST_RUN) a = a;
            else if (st == ST_WARMUP) a = (a < 10) ? 100 : (a < 13) ? 400 : 999;
            else a = (a < 150) ? 100 : (a < 180) ? 400 : (a < 200) ? 460 : (a < 250) ? 470 : 999;
            if (a == 0) begin
                wait_cmd(); r14_cmd(CMD_START); ncmd[0] = ncmd[0] + 1;
            end else if (a < 350) begin                    // one step, then APPLY_NR
                mx = (dut.u_regs.a_range == 1) ? 127 : (dut.u_regs.a_range == 2) ? 255 : (dut.u_regs.a_range == 3) ? 511 : 1023;
                sv = sv_of(dut.u_regs.a_m, dut.u_regs.a_sign) + (($urandom % 2) ? 1 : -1);
                if (sv > mx) sv = mx - 1;
                if (sv < -mx) sv = -mx + 1;
                set_m(sv, dut.u_regs.a_range);
                cmd(CMD_APPLY_NR, 3);
            end else if (a < 420) begin                    // a full change, then APPLY
                r = $urandom % 6;
                wait_cmd();
                case (r)
                    0: set_m(($urandom % 200) - 100, 2);
                    1: r14_write(7'h24, 8'($urandom % 16));
                    2: r14_write(7'h26, 8'($urandom % 2));
                    3: r14_write(7'h27, {3'd0, 1'($urandom % 2), 1'b0, 3'($urandom % 6)});
                    4: r14_write(7'h28, 8'(1 + $urandom % 15));
                    5: r14_write(7'h25, 8'({2'd0, 2'($urandom % 4), 2'd0, 2'($urandom % 4)}));
                endcase
                cmd(CMD_APPLY, 2);
            end else if (a < 450) begin
                cmd(CMD_STOP, 1);
            end else if (a < 500) begin
                cmd(CMD_FLUSH, 4);
            end else if (a < 530) begin
                wait_cmd();
                r = $urandom % 3;
                if (r == 0) r14_write(7'h51, 8'($urandom % 4));
                else if (r == 1) r14_write(7'h53, 8'(3 + $urandom % 2));
                else r14_write(7'h54, 8'(13 + $urandom % 2));
            end else if (a < 535) begin
                r14_write(7'h10, CMD_SOFT_RESET); #(1500.0);
                r14_read(7'h06, v); r14_write(7'h06, v); r14_write(7'h50, 8'd5); set_m(40, 1);
            end else if (a < 575) begin
                cmd(($urandom % 2) ? CMD_APPLY_NR : CMD_APPLY, ($urandom % 2) ? 3 : 2);   // unchanged shadows
            end else begin
                w = (st == ST_RUN) ? $urandom % 3000 : (st == ST_WARMUP) ? $urandom % 2000 : $urandom % 400;
                #(w * 1000.0);
            end
            if (dut.u_regs.err != 8'h00) begin
                r14_read(7'h06, v); r14_write(7'h06, v);
            end
            if (dut.u_regs.dflag != 2'b00 && ($urandom % 2)) begin
                r14_read(7'h07, v); r14_write(7'h07, v);
            end
        end
        if ($test$plusargs("quiet")) #(ms_end * 1.0e6 - $realtime);
        $display("frames at 64 kHz: %0d of %0d", n64, nall);
        $display("overload: %0d hits, %0d stored samples with OVL, %0d DFLAG.OVL rises", nhit, novl_store, ndflag);
        $display("tb_a31_inv seed %0d: %0d ms, %0d stores (%0d CHANGED, %0d beyond the required set), %0d steps, %0d full changes in run, %0d releases, %0d rises, cmds START %0d STOP %0d APPLY %0d APPLY_NR %0d FLUSH %0d, SPI errors %0d",
                 seed0, ms_end, nstore, nchg, nextra, nsteps, nfull_run, nrel, nrise, ncmd[0], ncmd[1], ncmd[2], ncmd[3], ncmd[4], spi_errors);
        if (errs == 0) $display("PASS: no violation"); else $display("FAIL: %0d violations", errs);
        $finish;
    end
endmodule
`default_nettype wire
