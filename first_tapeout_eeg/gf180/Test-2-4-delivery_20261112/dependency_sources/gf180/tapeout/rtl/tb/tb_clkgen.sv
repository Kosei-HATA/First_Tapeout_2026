// tb_clkgen - frame timing generator.
//
// Two instances: DAC_LOAD_CYCLE = 2 (default) and 7 (parameter check).
// Every MCLK cycle (sampled at the falling edge) it checks against a counter
// of cycles since reset release (independent of the DUT counter):
//   * cycle output, cmp_strobe at cycle 0, th_capture at 1, dac_load at
//     DAC_LOAD_CYCLE, cic_en at 3: each exactly one MCLK cycle per frame
//   * chop at both rates: 128 kHz (chop_fast = 1, toggles every 128 MCLK,
//     edges at e0 of every 4th frame) and 64 kHz (chop_fast = 0, every
//     256 MCLK, every 8th frame). The waveform is compared every cycle with a
//     reference that takes the rate at the start of each 512-MCLK superperiod
//   * chop_fast is changed at unaligned times, also in short pulses; every
//     CHOP and CHOP_OUT phase must be a full 128 or 256 MCLK (no runt, no
//     stretched phase), and every CHOP edge must fall on a cmp_strobe
//   * chop_out == chop delayed by chop_dly cycles (recorded chop history; the
//     DUT applies a new chop_dly one MCLK later), for delays 0, 1, 37, 127,
//     128, 129, 200 and 255, at both rates and across rate changes
//   * chop_blank against a reference (a pulse starts one cycle before each
//     chop_out edge and lasts blank_len + 1 cycles, blank_len taken when the
//     pulse starts), plus independent checks: every pulse rises exactly one
//     cycle before a chop_out edge, every chop_out edge with blank_len != 0
//     has chop_blank high in the cycle before it, and every pulse is exactly
//     blank_len + 1 cycles long (blank_len cycles after the edge). Only the
//     chop_out edge at the first MCLK edge after reset is exempt (the cycle
//     before it is in reset). blank_len 0, 1, 7 and 15 at both rates and every
//     chop_dly, a sweep of 0..15, blank_len changes in the middle of a pulse,
//     pulses across rate changes, and chop_dly changes
//   * raw_clk: MCLK/4, high in cycles 2,3 (mod 4), period 4
//   * outputs quiet during reset
`timescale 1ns / 1ps

module tb_clkgen;

    localparam real TMCLK = 30.5176;           // 32.768 MHz
    localparam int  NHIST = 262144;

    logic       clk = 1'b0;
    logic       rst_n = 1'b0;
    logic       chop_fast = 1'b1;
    logic [7:0] chop_dly = 8'd0;
    logic [3:0] blank_len = 4'd7;

    logic [4:0] cyc_a, cyc_b;
    logic       cmp_a, thc_a, dl_a, cic_a, chop_a, chop_out_a, blank_a, raw_a;
    logic       cmp_b, thc_b, dl_b, cic_b, chop_b, chop_out_b, blank_b, raw_b;

    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) dut_a (
        .clk (clk), .rst_n (rst_n), .chop_fast (chop_fast), .chop_dly (chop_dly),
        .blank_len (blank_len),
        .cycle (cyc_a), .cmp_strobe (cmp_a), .th_capture (thc_a), .dac_load (dl_a),
        .cic_en (cic_a), .chop (chop_a), .chop_out (chop_out_a), .chop_blank (blank_a),
        .raw_clk (raw_a)
    );

    eeg_clkgen #(.DAC_LOAD_CYCLE(7)) dut_b (
        .clk (clk), .rst_n (rst_n), .chop_fast (chop_fast), .chop_dly (chop_dly),
        .blank_len (blank_len),
        .cycle (cyc_b), .cmp_strobe (cmp_b), .th_capture (thc_b), .dac_load (dl_b),
        .cic_en (cic_b), .chop (chop_b), .chop_out (chop_out_b), .chop_blank (blank_b),
        .raw_clk (raw_b)
    );

    always #(TMCLK / 2.0) clk = ~clk;

    integer errors = 0;
    integer ncyc = 0;                          // rising edges since reset release
    logic   chop_hist [0:NHIST-1];             // chop value in cycle n (1-based)
    integer frames_checked = 0;
    integer cnt_cmp = 0, cnt_thc = 0, cnt_dla = 0, cnt_dlb = 0, cnt_cic = 0;
    integer last_raw_rise = -1;
    integer raw_rises = 0;
    logic   prev_chop = 1'b0;
    logic   prev_chop_out = 1'b0;
    logic   prev_raw = 1'b0;

    // values used by the DUT at the last rising edge (the testbench changes
    // its inputs at falling edges)
    integer d_edge = 0;
    integer d_edge_prev = 0;                   // chop_dly one edge earlier (used by chop_out)
    logic   fast_edge = 1'b1;
    integer bl_edge = 7;

    // reference rate: taken at the first cycle of every 512-MCLK superperiod
    logic   rate_ref = 1'b1;
    integer rate_changes = 0;
    integer last_rate_change = -100000;

    // phase-length bookkeeping
    integer last_chop_edge = -1;
    integer last_out_edge = -1;
    integer dly_change_cyc = 0;                // first cycle that used the latest chop_dly value
    integer prev_d_edge = 0;
    integer ph128 = 0, ph256 = 0;              // CHOP phases of each length
    integer out_ph128 = 0, out_ph256 = 0;      // CHOP_OUT phases of each length
    integer dly_checks = 0;
    integer dly_checks_fast = 0, dly_checks_slow = 0;

    // CHOP_BLANK reference and pulse bookkeeping, one cycle behind (cycle m =
    // ncyc - 1): b_m / b_m1 = chop_blank in cycles m / m-1, bl_m / bl_m1 =
    // blank_len used at the edges that started them
    logic   exp_blank = 1'b0;
    integer exp_rem = 0;
    logic   b_m = 1'b0, b_m1 = 1'b0;
    integer bl_m = 7, bl_m1 = 7;
    integer pulse_start = 0;
    integer pulse_len = 0;
    integer pulses_by_len [0:15];
    integer pulses_fast = 0, pulses_slow = 0;
    integer pulses_dly = 0;                    // pulses with chop_dly != 0
    integer pulses_after_switch = 0;           // pulses within 512 MCLK after a rate change
    integer len_changes_in_pulse = 0;          // blank_len changed while a pulse was high

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 15) $display("ERROR @%0t cycle %0d: %s", $time, ncyc, msg);
    endtask

    always @(posedge clk) begin
        if (rst_n) ncyc <= ncyc + 1;
        d_edge_prev <= d_edge;
        d_edge    <= chop_dly;
        fast_edge <= chop_fast;
        bl_edge   <= blank_len;
    end

    // all checks at the falling edge (outputs settled)
    always @(negedge clk) begin
        integer c;
        integer d;
        integer len;
        logic   exp_chop;
        logic   out_tog;
        if (!rst_n) begin
            if (cmp_a || thc_a || dl_a || cic_a || chop_a || chop_out_a || blank_a || blank_b)
                err("strobe, chop or chop_blank active during reset");
        end else if (ncyc >= 1) begin
            c = (ncyc - 1) % 32;
            if (cyc_a !== c[4:0] || cyc_b !== c[4:0]) err($sformatf("cycle %0d expected %0d", cyc_a, c));
            if (cmp_a !== (c == 0) || cmp_b !== (c == 0)) err("cmp_strobe position");
            if (thc_a !== (c == 1) || thc_b !== (c == 1)) err("th_capture position");
            if (dl_a !== (c == 2)) err("dac_load position (DAC_LOAD_CYCLE=2)");
            if (dl_b !== (c == 7)) err("dac_load position (DAC_LOAD_CYCLE=7)");
            if (cic_a !== (c == 3) || cic_b !== (c == 3)) err("cic_en position");
            if (raw_a !== ((c % 4) >= 2) || raw_b !== raw_a) err("raw_clk phase");
            if (chop_b !== chop_a || chop_out_b !== chop_out_a || blank_b !== blank_a)
                err("chop outputs differ between instances");
            cnt_cmp = cnt_cmp + cmp_a;
            cnt_thc = cnt_thc + thc_a;
            cnt_dla = cnt_dla + dl_a;
            cnt_dlb = cnt_dlb + dl_b;
            cnt_cic = cnt_cic + cic_a;
            if (c == 31) begin
                // exactly one pulse of each strobe per frame
                if (cnt_cmp != 1 || cnt_thc != 1 || cnt_dla != 1 || cnt_dlb != 1 || cnt_cic != 1)
                    err("strobe count per frame != 1");
                cnt_cmp = 0; cnt_thc = 0; cnt_dla = 0; cnt_dlb = 0; cnt_cic = 0;
                frames_checked = frames_checked + 1;
            end

            // chop against the reference waveform
            if ((ncyc - 1) % 512 == 0) begin
                if (rate_ref !== fast_edge && ncyc > 1) begin
                    rate_changes = rate_changes + 1;
                    last_rate_change = ncyc;
                end
                rate_ref = fast_edge;
            end
            exp_chop = rate_ref ? (((ncyc - 1) % 256) < 128) : (((ncyc - 1) % 512) < 256);
            if (chop_a !== exp_chop) err($sformatf("chop=%0d expected %0d (rate %0s)", chop_a, exp_chop, rate_ref ? "128k" : "64k"));
            if (ncyc == 1 && chop_a !== 1'b1) err("chop must rise at the first edge after reset");
            chop_hist[ncyc] = chop_a;

            // CHOP: edges only at cmp_strobe, every phase a full 128 or 256 MCLK
            if (ncyc > 1 && chop_a !== prev_chop) begin
                if (!cmp_a) err("chop edge not at frame cycle 0");
                if (last_chop_edge >= 0) begin
                    len = ncyc - last_chop_edge;
                    if (len == 128) ph128 = ph128 + 1;
                    else if (len == 256) ph256 = ph256 + 1;
                    else err($sformatf("CHOP phase of %0d MCLK", len));
                end
                last_chop_edge = ncyc;
            end
            prev_chop = chop_a;

            // chop_out(n) == chop(n - d); chop was 0 before reset release
            d = d_edge_prev;
            if (d != prev_d_edge) dly_change_cyc = ncyc;
            prev_d_edge = d;
            if (ncyc - d >= 1) begin
                if (chop_out_a !== chop_hist[ncyc - d]) err($sformatf("chop_out != chop delayed by %0d", d));
            end else if (chop_out_a !== 1'b0) begin
                err("chop_out before the first delayed edge");
            end
            dly_checks = dly_checks + 1;
            if (rate_ref) dly_checks_fast = dly_checks_fast + 1;
            else          dly_checks_slow = dly_checks_slow + 1;

            out_tog = (chop_out_a !== prev_chop_out);

            // CHOP_OUT phases; a change of chop_dly moves chop_out to the new
            // delay at once, so phases starting before or at that cycle are skipped
            if (ncyc > 1 && out_tog) begin
                if (last_out_edge >= 0 && last_out_edge > dly_change_cyc) begin
                    len = ncyc - last_out_edge;
                    if (len == 128) out_ph128 = out_ph128 + 1;
                    else if (len == 256) out_ph256 = out_ph256 + 1;
                    else err($sformatf("CHOP_OUT phase of %0d MCLK", len));
                end
                last_out_edge = ncyc;
            end
            prev_chop_out = chop_out_a;

            // CHOP_BLANK, checked for cycle m = ncyc - 1: a pulse starts one
            // cycle before the chop_out edge (out_tog = edge at cycle ncyc)
            if (ncyc >= 2) begin
                // reference: start when chop_out toggles in the next cycle
                if (out_tog && bl_m != 0) begin
                    exp_blank = 1'b1;
                    exp_rem   = bl_m;
                end else if (exp_blank) begin
                    if (exp_rem == 0) exp_blank = 1'b0;
                    else              exp_rem = exp_rem - 1;
                end
                if (b_m !== exp_blank)
                    err($sformatf("chop_blank=%0d in cycle %0d, expected %0d (blank_len %0d)", b_m, ncyc - 1, exp_blank, bl_m));

                // independent checks
                if (b_m && !b_m1 && !out_tog) err("chop_blank rose, but chop_out does not toggle one cycle later");
                if (out_tog && bl_m != 0) begin
                    if (!b_m) err("chop_blank low in the cycle before a chop_out edge");
                    pulse_start = ncyc - 1;
                    pulse_len   = bl_m + 1;
                    if (rate_ref) pulses_fast = pulses_fast + 1;
                    else          pulses_slow = pulses_slow + 1;
                    if (d != 0) pulses_dly = pulses_dly + 1;
                    if (ncyc - last_rate_change < 512) pulses_after_switch = pulses_after_switch + 1;
                end
                if (!b_m && b_m1) begin
                    len = (ncyc - 1) - pulse_start;
                    if (len != pulse_len) err($sformatf("chop_blank pulse of %0d MCLK, expected %0d (blank_len + 1)", len, pulse_len));
                    else pulses_by_len[len - 1] = pulses_by_len[len - 1] + 1;
                end
                if (b_m && b_m1 && bl_m != bl_m1) len_changes_in_pulse = len_changes_in_pulse + 1;
            end
            b_m1  = b_m;
            b_m   = blank_a;
            bl_m1 = bl_m;
            bl_m  = bl_edge;

            // raw_clk period
            if (raw_a && !prev_raw) begin
                if (last_raw_rise >= 0 && ncyc - last_raw_rise != 4) err("raw_clk period != 4");
                last_raw_rise = ncyc;
                raw_rises = raw_rises + 1;
            end
            prev_raw = raw_a;
        end
    end

    task automatic set_dly(input integer d);
        chop_dly = d[7:0];
    endtask

    integer seed = 17;
    integer delays [0:7];
    integer lens [0:3];

    function automatic logic [3:0] pick_len();
        integer r;
        r = {$random(seed)} % 5;
        if (r < 4) return lens[r];
        return {$random(seed)} % 16;
    endfunction

    initial begin
        delays[0] = 0;   delays[1] = 1;   delays[2] = 37;  delays[3] = 127;
        delays[4] = 128; delays[5] = 129; delays[6] = 200; delays[7] = 255;
        lens[0] = 0; lens[1] = 1; lens[2] = 7; lens[3] = 15;
        for (int i = 0; i < 16; i++) pulses_by_len[i] = 0;

        repeat (5) @(negedge clk);
        rst_n = 1'b1;

        // 128 kHz (reset default) with blank_len 7, then every delay with
        // blank_len 0, 1, 7, 15 at both rates
        repeat (3000) @(negedge clk);
        for (int i = 0; i < 8; i++) begin
            set_dly(delays[i]);
            for (int j = 0; j < 4; j++) begin
                blank_len = lens[j];
                repeat (300) @(negedge clk);
            end
        end
        chop_fast = 1'b0;                      // switch to 64 kHz at an unaligned time
        repeat (777) @(negedge clk);
        for (int i = 0; i < 8; i++) begin
            set_dly(delays[i]);
            for (int j = 0; j < 4; j++) begin
                blank_len = lens[j];
                repeat (400) @(negedge clk);
            end
        end

        // rate changes at random times with a constant delay, including
        // requests shorter than a superperiod; blank_len changes at random times
        for (int i = 0; i < 8; i++) begin
            set_dly(delays[i]);
            blank_len = pick_len();
            for (int j = 0; j < 8; j++) begin
                chop_fast = ~chop_fast;
                repeat (20 + {$random(seed)} % 1500) @(negedge clk);
                if (({$random(seed)} % 2) == 0) blank_len = pick_len();
            end
        end

        // blank_len changed in the middle of a pulse: the pulse keeps its length
        chop_fast = 1'b1;
        set_dly(37);
        for (int i = 0; i < 12; i++) begin
            blank_len = (i % 2 == 0) ? 4'd15 : 4'd7;
            @(posedge blank_a);
            repeat (2) @(negedge clk);
            blank_len = lens[i % 4];
            repeat (300) @(negedge clk);
        end

        // sweep of every blank_len value
        for (int l = 0; l < 16; l++) begin
            blank_len = l[3:0];
            repeat (300) @(negedge clk);
        end

        // reset in the middle of 64 kHz operation: back to the defaults
        chop_fast = 1'b0;
        set_dly(200);
        blank_len = 4'd15;
        repeat (2000) @(negedge clk);
        #2.0;                                  // asynchronous reset in the middle of a cycle
        rst_n = 1'b0;
        chop_fast = 1'b1;                      // register reset values
        set_dly(0);
        blank_len = 4'd7;
        ncyc = 0;
        dly_change_cyc = 0;
        last_chop_edge = -1;
        last_out_edge = -1;
        last_raw_rise = -1;
        last_rate_change = -100000;
        prev_chop = 1'b0;
        prev_chop_out = 1'b0;
        prev_raw = 1'b0;
        b_m = 1'b0;
        b_m1 = 1'b0;
        exp_blank = 1'b0;
        exp_rem = 0;
        rate_ref = 1'b1;
        cnt_cmp = 0; cnt_thc = 0; cnt_dla = 0; cnt_dlb = 0; cnt_cic = 0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        repeat (2000) @(negedge clk);

        if (rate_changes < 20) err($sformatf("only %0d rate changes", rate_changes));
        if (ph128 < 50 || ph256 < 50) err("too few CHOP phases at one of the rates");
        for (int l = 1; l < 16; l++)
            if (pulses_by_len[l] == 0) err($sformatf("no chop_blank pulse for blank_len %0d", l));
        if (pulses_fast < 50 || pulses_slow < 50 || pulses_dly < 50 || pulses_after_switch < 10 || len_changes_in_pulse < 10)
            err("too few chop_blank pulses in one of the covered cases");
        if (errors == 0)
            $display("PASS: tb_clkgen (%0d frames, %0d rate changes, CHOP phases 128/256 MCLK: %0d/%0d, CHOP_OUT phases: %0d/%0d, %0d chop_out checks [%0d at 128 kHz, %0d at 64 kHz] with delays 0/1/37/127/128/129/200/255, CHOP_BLANK pulses for BLANK_LEN 1/7/15 (1 MCLK before + BLANK_LEN after the edge): %0d/%0d/%0d [%0d at 128 kHz, %0d at 64 kHz, %0d with CHOP_DLY != 0, %0d within 512 MCLK after a rate change, %0d blank_len changes during a pulse, all lengths 1..15 seen], %0d raw_clk periods)",
                     frames_checked, rate_changes, ph128, ph256, out_ph128, out_ph256,
                     dly_checks, dly_checks_fast, dly_checks_slow,
                     pulses_by_len[1], pulses_by_len[7], pulses_by_len[15],
                     pulses_fast, pulses_slow, pulses_dly, pulses_after_switch, len_changes_in_pulse, raw_rises);
        else
            $display("FAIL: tb_clkgen (%0d errors)", errors);
        $finish;
    end

endmodule
