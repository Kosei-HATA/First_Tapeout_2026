// tb_a24 - audit round 24, auditor A: an independent end-to-end random bench of the sequencer and the analog side.
// A random host (CRC off) issues START / STOP / APPLY / APPLY_NR / FLUSH / SOFT_RESET / RESET_N pulses and shadow and
// timer writes at random times (so commands land in every state), with 64 kHz, CHOP1, BLANK, range, M, trims and the
// test settings. CODE is a random mid-scale stream with overload bursts. Independent checks (no use of the RTL's
// models): a golden sinc^3 (3070 taps) for every stored sample, the overload rule from the codes, SEQ from the frame
// count, every stored window clean (AFE_RST 0 from T_REC before it, no analog pin change but marked DAC steps, the
// electrode wait, CHOP / BLANK widths / CHOP1 rate constant), pin changes only after a tick or in a reset, AFE_RST
// released only T_RST after the last change and T_WARM after a reset, the pins at reset values during a SOFT_RESET,
// the tick at cycle 24 in the middle of phase A.
`timescale 1ns / 1ps
`default_nettype none

module tb_a24;
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

    integer errors = 0;
    task automatic fail(input string msg);
        errors = errors + 1;
        if (errors <= 80) $display("ERROR @%0.3f us: %s", $realtime / 1000.0, msg);
    endtask

    // ------------------------------------------------------------------ golden sinc^3
    localparam int R = 1024;
    longint h2 [0:2*R-2];
    longint h3 [0:3*R-3];
    initial begin
        longint s;
        for (int n = 0; n < 2*R-1; n++) h2[n] = (n < R) ? n + 1 : 2*R - 1 - n;
        s = 0;
        for (int n = 0; n < 3*R-2; n++) begin
            h3[n] = 0;
            for (int j = ((n - R + 1) > 0 ? (n - R + 1) : 0); j <= ((n < 2*R-2) ? n : 2*R-2); j++) h3[n] += h2[j];
            s += h3[n];
        end
        if (s != 64'd1 << 30) begin $display("ERROR: sum h3 %0d", s); errors++; end
    end

    // ------------------------------------------------------------------ frames, codes, overload model
    integer fr = -1;                              // frame since RESET_N release
    logic [4:0] xh [0:(1<<20)-1];
    logic       blkhit [0:4095];                  // a hit in block b (frames bR .. bR+R-1)
    real        t_blk [0:4095];                   // e0 of frame bR
    logic [31:0] ewin = 0;
    integer burst = 0, sparse = 0;
    logic hit_now = 1'b0;
    integer cnt_now = 0;
    integer n_dflag_set = 0;
    // OVL_NOW and DFLAG.OVL against the rule (checked in the cycle after the CIC input, cycle 4)
    logic p_dovl = 1'b0;
    always @(negedge MCLK) begin
        if (dut.pin_rst_n === 1'b1 && fr >= 0 && dut.cycle == 5'd4) begin
            if (dut.ovl_now !== (cnt_now >= 4)) fail($sformatf("OVL_NOW %b, the rule's count %0d", dut.ovl_now, cnt_now));
        end
        if (dut.rst_n === 1'b1 && p_dovl === 1'b0 && dut.u_regs.dflag[1] === 1'b1) begin
            n_dflag_set++;
            if (!(hit_now && dut.cycle == 5'd4 && (dut.seq_state == ST_FILL || dut.seq_state == ST_RUN)))
                fail($sformatf("DFLAG.OVL set without a hit in FILL or RUN (state %0d cycle %0d)", dut.seq_state, dut.cycle));
        end
        if (dut.cycle == 5'd4 && hit_now && dut.rst_n === 1'b1 && (dut.seq_state == ST_FILL || dut.seq_state == ST_RUN) &&
            dut.u_regs.dflag[1] !== 1'b1)
            fail("a hit in FILL or RUN without DFLAG.OVL");
        p_dovl = dut.u_regs.dflag[1];
    end
    integer n_hits = 0, n_frames = 0;

    function automatic logic [4:0] next_code();
        logic [4:0] c;
        if (burst == 0 && sparse == 0) begin
            if ($urandom % 15000 == 0) burst = 20 + $urandom % 300;
            else if ($urandom % 20000 == 0) sparse = 100 + $urandom % 400;
        end
        if (burst > 0) begin
            burst--;
            c = ($urandom % 10 < 7) ? (($urandom % 2) ? 5'd31 : 5'd0) : 5'(3 + $urandom % 25);
        end else if (sparse > 0) begin
            sparse--;
            c = ($urandom % 9 == 0) ? (($urandom % 2) ? 5'd31 : 5'd0) : 5'(3 + $urandom % 25);
        end else c = 5'(3 + $urandom % 25);
        return c;
    endfunction

    always @(posedge MCLK) begin
        #0.2;
        if (dut.pin_rst_n !== 1'b1) begin
            fr = -1; ewin = 0;
        end else begin
            if (dut.cycle == 5'd0) begin
                fr = fr + 1;
                n_frames++;
                if (fr % R == 0) begin t_blk[fr / R] = $realtime - 0.2; blkhit[fr / R] = 1'b0; end
            end
            if (dut.cycle == 5'd2 && fr >= 0) begin              // the ADC's code changes at e2
                CODE = next_code();
                xh[fr] = CODE;
            end
            if (dut.cycle == 5'd3 && fr >= 0) begin              // the CIC and the detector take it at the end of cycle 3
                logic ext; integer cnt;
                ext = (xh[fr] == 5'd0) || (xh[fr] == 5'd31);
                ewin = {ewin[30:0], ext};
                cnt = $countones(ewin);
                if (ext && cnt >= 4) begin blkhit[fr / R] = 1'b1; n_hits++; end
                hit_now = ext && cnt >= 4;
                cnt_now = cnt;
            end
        end
    end

    function automatic logic [23:0] golden(input integer k);   // output k (1-based) at frame kR - 1
        longint acc, q, r;
        logic up;
        integer f0;
        f0 = k * R - 3;
        acc = 0;
        for (int j = 0; j < 3*R-2; j++) acc += h3[j] * (2 * longint'(xh[f0 - j]) - 31);
        q = acc >>> 12;
        r = acc & 64'hFFF;
        up = (r > 2048) || (r == 2048 && q[0]);
        q = q + up;
        return q[23:0];
    endfunction

    // ------------------------------------------------------------------ pin monitors
    logic [9:0] p_ofm; logic p_ofs; logic [3:0] p_ofen, p_cpf; logic [1:0] p_ib, p_bp, p_bn; logic [5:0] p_tc;
    logic p_chen, p_dwa, p_afe = 1'b1, p_tick = 1'b0, p_init = 1'b0;
    real  t_other = -1e12, t_dac = -1e12, t_afe_rise = 0.0, t_afe_fall = -1e12, t_reset = 0.0;
    integer telec_dac = 0;
    real  t_chop_rise = 0.0, t_chop_edge = 0.0, t_chop_prev = 0.0, h_chop = 0.0, t_chopchg = 0.0;
    real  t_blk_rise = 0.0, w_blank = -1.0, t_blankchg = 0.0;
    logic [2:0] p_c1rate = 3'd3;
    real  t_c1chg = 0.0;
    integer n_pinchg = 0, n_rel = 0, n_ticks = 0, n_soft = 0, n_resetn = 0;
    bit verbose = 0;
    initial verbose = $test$plusargs("verbose");

    always @(negedge MCLK) begin
        real tp;                                  // the time of the posedge just before
        logic chg_other, chg_dac;
        tp = $realtime - TMCLK / 2.0;
        if (p_init) begin
            chg_other = (CPF_TRIM !== p_cpf) || (AFE_IBIAS !== p_ib) || (BTRIM_P !== p_bp) || (BTRIM_N !== p_bn) ||
                        (TEST_CFG[5:0] !== p_tc) || (CHOP_EN !== p_chen) || (DWA_EN !== p_dwa);
            chg_dac   = (OFM !== p_ofm) || (OFS !== p_ofs) || (OFEN !== p_ofen);
            if ((chg_other || chg_dac || AFE_RST !== p_afe) && !(p_tick || dut.rst_n !== 1'b1))
                fail($sformatf("analog pin changed outside a tick edge and a reset (state %0d)", dut.seq_state));
            if (chg_other) begin t_other = tp; n_pinchg++; if (verbose) $display("  pin %0.3f us st %0d other cpf %0d ib %0d bp %0d bn %0d tc %02h chen %b dwa %b", tp/1000.0, dut.seq_state, CPF_TRIM, AFE_IBIAS, BTRIM_P, BTRIM_N, TEST_CFG[5:0], CHOP_EN, DWA_EN); end
            if (chg_dac) begin t_dac = tp; telec_dac = dut.t_elec; n_pinchg++; if (verbose) $display("  pin %0.3f us st %0d dac ofm %0d ofs %b ofen %b telec %0d", tp/1000.0, dut.seq_state, OFM, OFS, OFEN, dut.t_elec); end
            if (AFE_RST === 1'b1 && p_afe === 1'b0) t_afe_rise = tp;
            if (AFE_RST === 1'b0 && p_afe === 1'b1) begin      // a release
                n_rel++;
                t_afe_fall = tp;
                if (tp - t_afe_rise < 100000.0 - 1.0) fail($sformatf("AFE_RST high only %0.2f us", (tp - t_afe_rise) / 1000.0));
                if (tp - t_other < 100000.0 - 1.0 || tp - t_dac < 100000.0 - 1.0)
                    fail($sformatf("AFE_RST released %0.2f / %0.2f us after a setting change (SEQ-16)",
                                   (tp - t_other) / 1000.0, (tp - t_dac) / 1000.0));
                if (tp - t_reset < 5.0e6 - 1.0) fail($sformatf("AFE_RST released %0.2f us after a reset", (tp - t_reset) / 1000.0));
                if (tp - t_chopchg < 80000.0) fail($sformatf("AFE_RST released %0.2f us after a chopper rate change",
                                                             (tp - t_chopchg) / 1000.0));
                if (tp - t_blankchg < 80000.0) fail($sformatf("AFE_RST released %0.2f us after a blanking change",
                                                              (tp - t_blankchg) / 1000.0));
                if (dut.seq_state !== ST_RECOVER) fail("AFE_RST released into a state other than RECOVER");
            end
        end
        // a control reset: every analog pin at its reset value, AFE_RST high
        if (dut.rst_n !== 1'b1) begin
            t_reset = $realtime;
            if (AFE_RST !== 1'b1 || OFM !== 10'd0 || OFS !== 1'b0 || OFEN !== 4'd0 || CPF_TRIM !== 4'd8 ||
                AFE_IBIAS !== 2'd3 || BTRIM_P !== 2'd1 || BTRIM_N !== 2'd0 || TEST_CFG[5:0] !== 6'd0 || CHOP_EN !== 1'b1 ||
                DWA_EN !== 1'b1)
                fail("a pin away from its reset value during a reset");
        end
        // the tick: cycle 24 of a frame in the middle of phase A
        if (dut.u_clkgen.tick === 1'b1) begin
            integer n;
            n_ticks++;
            n = $rtoi((tp - t_chop_rise) / TMCLK + 0.5);
            if (dut.cycle !== 5'd24 || CHOP !== 1'b1 || !((dut.u_clkgen.fast && n == 56) || (!dut.u_clkgen.fast && n == 120)))
                fail($sformatf("tick at cycle %0d, CHOP %b, %0d MCLK after the phase-A edge (fast %b)", dut.cycle, CHOP, n,
                               dut.u_clkgen.fast));
        end
        // CHOP1's sampled rate
        if (dut.u_chop1.rate_q !== p_c1rate) begin t_c1chg = tp; p_c1rate = dut.u_chop1.rate_q; end
        p_ofm = OFM; p_ofs = OFS; p_ofen = OFEN; p_cpf = CPF_TRIM; p_ib = AFE_IBIAS; p_bp = BTRIM_P; p_bn = BTRIM_N;
        p_tc = TEST_CFG[5:0]; p_chen = CHOP_EN; p_dwa = DWA_EN; p_afe = AFE_RST; p_tick = dut.u_clkgen.tick; p_init = 1'b1;
    end
    always @(negedge RESET_N) begin t_reset = $realtime; n_resetn++; end

    // CHOP's half period: a change starts at the edge before the first edge measuring the new length
    always @(CHOP) begin
        real h;
        if (CHOP === 1'b1) t_chop_rise = $realtime;
        h = $realtime - t_chop_edge;
        if (h_chop > 0.0 && (h < h_chop - 2.0 || h > h_chop + 2.0)) t_chopchg = t_chop_edge;
        h_chop = h;
        t_chop_edge = $realtime;
    end
    // CHOP_BLANK's pulse width (held by ADC_ZERO: a TEST_CFG[5] change, checked as such)
    always @(CHOP_BLANK) begin
        real w;
        if (CHOP_BLANK === 1'b1) t_blk_rise = $realtime;
        else if (TEST_CFG[5] === 1'b0) begin
            w = $realtime - t_blk_rise;
            if (w < 40.0 * TMCLK) begin
                if (w_blank > 0.0 && (w < w_blank - 2.0 || w > w_blank + 2.0)) t_blankchg = t_blk_rise;
                w_blank = w;
            end
        end
    end
    always @(posedge RESET_N or posedge dut.rst_n) begin h_chop = 0.0; w_blank = -1.0; end

    // ------------------------------------------------------------------ CHANGED model (mark from the sequencer's
    // accepted APPLY_NR in RUN; count and cancel independently) and the stored samples
    integer rem = 0;
    integer n_store = 0, n_changed = 0, n_ovl = 0, n_store64 = 0, n_cic_ok = 0;
    always @(negedge MCLK) begin
        if (dut.rst_n !== 1'b1) rem = 0;
        else begin
            if (dut.seq_mark === 1'b1 && dut.u_seq.tick === 1'b1) rem = (rem > 3 + dut.t_elec) ? rem : 3 + dut.t_elec;
            if (dut.seq_store === 1'b1) begin
                integer k, b0;
                real t_ws, span;
                logic [7:0] st;
                logic [23:0] g;
                logic ovl_g;
                n_store++;
                if (!dut.u_clkgen.fast) n_store64++;
                st = dut.smp_status;
                k = (fr + 1) / R;
                b0 = k - 3;
                if ((fr + 1) % R != 0 || dut.cycle !== 5'd8) fail($sformatf("store off the output grid: frame %0d cycle %0d", fr, dut.cycle));
                else if (b0 < 0) fail("store before three outputs since RESET_N");
                else begin
                    t_ws = t_blk[b0];
                    span = t_ws - 32.0 * TMCLK;
                    if (dut.seq_cnt !== 16'((k - 1) & 16'hFFFF)) fail($sformatf("SEQ %0d, expected %0d", dut.seq_cnt, k - 1));
                    g = golden(k);
                    if (dut.cic_data !== g) fail($sformatf("output %0d (SEQ %0d): data %06h, golden %06h", k, k - 1, dut.cic_data, g));
                    else n_cic_ok++;
                    ovl_g = blkhit[k - 1] | blkhit[k - 2] | blkhit[k - 3];
                    if (st[SMP_OVL_LSB] !== ovl_g) fail($sformatf("SEQ %0d: OVL %b, the rule gives %b", k - 1, st[SMP_OVL_LSB], ovl_g));
                    if (ovl_g) n_ovl++;
                    if (AFE_RST !== 1'b0 || t_afe_fall > t_ws - 226.5e3)
                        fail($sformatf("SEQ %0d: AFE_RST released %0.2f us before the window", k - 1, (t_ws - t_afe_fall) / 1000.0));
                    if (t_other >= span) fail($sformatf("SEQ %0d: a non-DAC analog pin changed %0.2f us into the window", k - 1,
                                                        (t_other - t_ws) / 1000.0));
                    if (t_chopchg >= span) fail($sformatf("SEQ %0d: CHOP rate changed in the window", k - 1));
                    if (t_blankchg >= span) fail($sformatf("SEQ %0d: blanking width changed in the window", k - 1));
                    if (t_c1chg > t_ws + 0.5 * TMCLK + 0.1) fail($sformatf("SEQ %0d: CHOP1 rate changed %0.2f us into the window",
                                                                           k - 1, (t_c1chg - t_ws) / 1000.0));
                    if (t_dac >= span && st[SMP_CHANGED_LSB] !== 1'b1)
                        fail($sformatf("SEQ %0d: a DAC step in the window, CHANGED 0", k - 1));
                    if (st[SMP_CHANGED_LSB] !== 1'b1 && t_ws < t_dac + telec_dac * 1.0e6 - 1.0)
                        fail($sformatf("SEQ %0d: unmarked window starts %0.2f us after a DAC step with T_ELEC %0d ms", k - 1,
                                       (t_ws - t_dac) / 1000.0, telec_dac));
                    if (st[SMP_CHANGED_LSB] !== (rem > 0)) fail($sformatf("SEQ %0d: CHANGED %b, model %0d", k - 1, st[SMP_CHANGED_LSB], rem));
                    if (st[SMP_CHANGED_LSB]) n_changed++;
                end
            end
            if (dut.cic_stb === 1'b1 && rem > 0 && dut.seq_state == ST_RUN) rem = rem - 1;
            if (dut.seq_state !== ST_RUN && !(dut.seq_mark === 1'b1)) rem = 0;
        end
    end

    // ------------------------------------------------------------------ the host
    function automatic logic [9:0] rmax(input integer r);
        case (r) 0: return 10'd1023; 1: return 10'd127; 2: return 10'd255; 3: return 10'd511; default: return 10'd1023; endcase
    endfunction
    task automatic wait_free();                   // no command pending (the host polls CMD_PENDING)
        while (dut.cmd_valid === 1'b1) #(1000.0);
    endtask
    task automatic set_dac(input integer r, input integer m, input integer s);
        r14_write(7'h22, {3'd0, 1'(s), 1'b0, 3'(r)});
        r14_write(7'h20, 8'((m >> 8) & 3));
        r14_write(7'h21, 8'(m & 255));
    endtask
    task automatic rnd_settings();
        integer r;
        r = ($urandom % 5 == 0) ? 0 : 1 + $urandom % 4;
        if ($urandom % 4 != 0) set_dac(r, $urandom % (rmax(r) + 1), $urandom % 2);
        if ($urandom % 4 == 0) r14_write(7'h23, 8'($urandom % 4));
        if ($urandom % 3 == 0) r14_write(7'h24, 8'($urandom % 16));
        if ($urandom % 3 == 0) r14_write(7'h25, {2'd0, 2'($urandom % 4), 2'd0, 2'($urandom % 4)});
        if ($urandom % 3 == 0) r14_write(7'h26, 8'($urandom % 2));
        if ($urandom % 3 == 0) r14_write(7'h27, {3'd0, 1'($urandom % 2), 1'b0, 3'($urandom % 6)});
        if ($urandom % 3 == 0) r14_write(7'h28, 8'(1 + $urandom % 15));
        if ($urandom % 4 == 0) r14_write(7'h60, 8'($urandom % 32));
        if ($urandom % 6 == 0) r14_write(7'h61, 8'($urandom % 4));
        else if ($urandom % 3 == 0) r14_write(7'h61, 8'h00);
    endtask
    task automatic prep_nr();                     // shadows = actives, M one step away (sometimes no change)
        integer m, s, r, sv, nsv, am;
        r14_write(7'h23, {6'd0, dut.u_regs.a_ibias});
        r14_write(7'h24, {4'd0, dut.u_regs.a_cpf});
        r14_write(7'h25, {2'd0, dut.u_regs.a_bn, 2'd0, dut.u_regs.a_bp});
        r14_write(7'h26, {7'd0, dut.u_regs.a_fast});
        r14_write(7'h27, {3'd0, dut.u_regs.a_dwa, 1'b0, dut.u_regs.a_c1});
        r14_write(7'h28, {4'd0, dut.u_regs.a_blank});
        r14_write(7'h60, {3'd0, dut.u_regs.a_atpen, dut.u_regs.a_atpsel});
        r14_write(7'h61, {6'd0, dut.u_regs.a_cstop, dut.u_regs.a_azero});
        m = dut.u_regs.a_m; s = dut.u_regs.a_sign; r = dut.u_regs.a_range;
        sv = s ? -m : m;
        case ($urandom % 5) 0: nsv = sv; 1, 2: nsv = sv + 1; default: nsv = sv - 1; endcase
        am = nsv < 0 ? -nsv : nsv;
        if (am > rmax(r)) begin nsv = sv; am = m; end
        set_dac(r, am, (nsv < 0) ? 1 : ((nsv == 0) ? $urandom % 2 : 0));
    endtask
    task automatic unlock();
        r14_write(7'h11, 8'h3C);
        if ($urandom % 3 == 0) r14_write(7'h62, 8'($urandom % 8));     // RAW_EN, DBG_SEL
    endtask
    task automatic wait_state(input logic [3:0] s, input real max_us);
        real t0;
        t0 = $realtime;
        while (dut.seq_state !== s && $realtime - t0 < max_us * 1000.0) #(500.0);
    endtask

    integer it, act, nit;
    integer n_cmd [0:5];
    initial begin
        if (!$value$plusargs("nit=%d", nit)) nit = 400;
        if ($value$plusargs("seed=%d", it)) begin void'($urandom(it)); $display("seed %0d", it); end
        for (int i = 0; i < 6; i++) n_cmd[i] = 0;
        #(50.0 * TMCLK);
        RESET_N = 1'b1;
        #(2000.0);
        unlock();
        for (it = 0; it < nit; it++) begin
            wait_free();
            act = $urandom % 100;
            if (dut.seq_state == ST_IDLE && $urandom % 10 < 6) act = 8 + $urandom % 12;   // mostly START from IDLE
            if (act < 8) begin
                rnd_settings();
            end else if (act < 20) begin                                   // START (often from IDLE)
                if (dut.seq_state != ST_IDLE && $urandom % 2) begin wait_free(); r14_cmd(8'h22); n_cmd[1]++; #(20000.0); wait_free(); end
                if ($urandom % 2) rnd_settings();
                wait_free(); r14_cmd(8'h11); n_cmd[0]++;
                if ($urandom % 2) begin wait_state(ST_RUN, 12000.0); #(($urandom % 6000) * 1000.0); end
                else #(($urandom % 7000) * 1000.0);
            end else if (act < 26) begin
                r14_cmd(8'h22); n_cmd[1]++;
                #(($urandom % 2000) * 1000.0);
            end else if (act < 44) begin                                   // APPLY
                if ($urandom % 2) rnd_settings(); else set_dac(dut.u_regs.a_range, dut.u_regs.a_m, dut.u_regs.a_sign);
                wait_free(); r14_cmd(8'h33); n_cmd[2]++;
                case ($urandom % 3)
                    0: begin wait_state(ST_RUN, 12000.0); #(($urandom % 6000) * 1000.0); end
                    1: begin                                               // a follow-up in PRE / PULSE / RECOVER
                        wait_free();
                        #(($urandom % 120) * 1000.0);
                        case ($urandom % 4)
                            0: begin r14_cmd(8'h22); n_cmd[1]++; end
                            1: begin r14_cmd(8'h33); n_cmd[2]++; end
                            2: begin r14_cmd(8'h44); n_cmd[3]++; end
                            default: begin r14_cmd(8'h55); n_cmd[4]++; end
                        endcase
                        #(($urandom % 600) * 1000.0);
                    end
                    default: #(($urandom % 4000) * 1000.0);
                endcase
            end else if (act < 66) begin                                   // APPLY_NR
                prep_nr();
                wait_free(); r14_cmd(8'h44); n_cmd[3]++;
                #(($urandom % 4000) * 1000.0);
            end else if (act < 70) begin
                r14_cmd(8'h55); n_cmd[4]++;
                #(($urandom % 3000) * 1000.0);
            end else if (act < 73) begin                                   // SOFT_RESET
                r14_cmd(8'hA5); n_cmd[5]++; n_soft++;
                #(2000.0);
                unlock();
                #(($urandom % 3000) * 1000.0);
            end else if (act < 74) begin                                   // RESET_N pulse
                #(($urandom % 1000) * 1.0);
                RESET_N = 1'b0; #(($urandom % 20 + 1) * TMCLK); RESET_N = 1'b1;
                #(2000.0);
                unlock();
            end else if (act < 82) begin                                   // timers; T_ELEC only in IDLE or RUN (5.4 step 4)
                if (dut.seq_state == ST_IDLE || dut.seq_state == ST_RUN) r14_write(7'h51, 8'($urandom % 4));
                if ($urandom % 2) r14_write(7'h52, 8'(29 + $urandom % 8));
                if ($urandom % 2) r14_write(7'h53, 8'(3 + $urandom % 4));
                if ($urandom % 2) r14_write(7'h54, 8'(13 + $urandom % 4));
                if ($urandom % 3 == 0) r14_write(7'h50, 8'(5 + $urandom % 2));
            end else begin
                #(($urandom % 6000) * 1000.0);
            end
        end
        #(20.0e6);
        $display("tb_a24: %0d iterations, %0.1f ms simulated, %0d frames; commands START %0d STOP %0d APPLY %0d APPLY_NR %0d FLUSH %0d SOFT_RESET %0d; RESET_N pulses %0d",
                 nit, $realtime / 1.0e6, n_frames, n_cmd[0], n_cmd[1], n_cmd[2], n_cmd[3], n_cmd[4], n_cmd[5], n_resetn);
        $display("  ticks %0d, analog pin changes %0d, AFE_RST releases %0d, stores %0d (64 kHz %0d), golden-equal %0d, CHANGED %0d, OVL %0d, hits %0d",
                 n_ticks, n_pinchg, n_rel, n_store, n_store64, n_cic_ok, n_changed, n_ovl, n_hits);
        $display("  DFLAG.OVL sets %0d; SPI errors %0d (MISO checks), errors %0d", n_dflag_set, spi_errors, errors);
        if (errors == 0) $display("PASS: tb_a24"); else $display("FAIL: tb_a24 (%0d errors)", errors);
        $finish;
    end

    // state coverage of the commands (from the sequencer's acknowledge)
    integer cov [0:8][0:5];
    initial for (int a = 0; a < 9; a++) for (int b = 0; b < 6; b++) cov[a][b] = 0;
    always @(negedge MCLK) if (dut.rst_n === 1'b1 && dut.cmd_ack === 1'b1 && dut.seq_state <= 8) begin
        case (dut.cmd_code)
            8'h11: cov[dut.seq_state][0]++; 8'h22: cov[dut.seq_state][1]++; 8'h33: cov[dut.seq_state][2]++;
            8'h44: cov[dut.seq_state][3]++; 8'h55: cov[dut.seq_state][4]++; default: ;
        endcase
    end
    final begin
        $display("  commands taken per state (START STOP APPLY APPLY_NR FLUSH):");
        for (int a = 0; a < 9; a++) $display("    state %0d: %0d %0d %0d %0d %0d", a, cov[a][0], cov[a][1], cov[a][2], cov[a][3], cov[a][4]);
    end
endmodule

`default_nettype wire
