// tb_dwa - eeg_dwa (N = 31) against an independent reference model.
//
// Checks after every load:
//   * popcount(sel) == k
//   * the ones form one contiguous run modulo 31 (DWA mode)
//   * sel equals the run of k elements starting at the reference pointer
//   * ptr == reference pointer, which advances by (p + k) mod 31
//   * dwa_en = 0: sel is the thermometer 0..k-1 and the pointer is held
//   * sel/ptr do not change without load (k is changed between loads)
//   * element usage counts differ by at most 1 (first-order DWA property),
//     checked over the initial DWA-only phase
// Stimulus: reset state, 20 sweeps of k = 0..31, runs of constant k (0, 31,
// 1, 30, 15, 16), 150000 random loads, dwa_en = 0 phases, and random
// toggling of dwa_en.
`timescale 1ns / 1ps

module tb_dwa;

    localparam int N = 31;

    logic        clk = 1'b0;
    logic        rst_n = 1'b0;
    logic        load = 1'b0;
    logic        dwa_en = 1'b1;
    logic [4:0]  k = 5'd0;
    logic [30:0] sel;
    logic [4:0]  ptr;

    eeg_dwa #(.N(N)) dut (
        .clk    (clk),
        .rst_n  (rst_n),
        .load   (load),
        .dwa_en (dwa_en),
        .k      (k),
        .sel    (sel),
        .ptr    (ptr)
    );

    always #5 clk = ~clk;

    integer errors = 0;
    integer nloads = 0;
    integer p_ref = 0;
    integer seed = 5;
    integer kcount [0:31];
    integer use_cnt [0:30];
    bit     track_usage = 1'b1;
    integer usage_checks = 0;

    function automatic integer popc(input logic [30:0] v);
        integer n;
        n = 0;
        for (int i = 0; i < N; i++) n = n + v[i];
        return n;
    endfunction

    function automatic logic [30:0] run_mask(input integer p, input integer kk);
        logic [30:0] m;
        m = '0;
        for (int j = 0; j < kk; j++) m[(p + j) % N] = 1'b1;
        return m;
    endfunction

    // number of 0->1 run starts on the circle (0 for all-zero and all-one)
    function automatic integer run_starts(input logic [30:0] v);
        integer n;
        n = 0;
        for (int j = 0; j < N; j++)
            if (v[j] && !v[(j + N - 1) % N]) n = n + 1;
        return n;
    endfunction

    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 10) $display("ERROR @%0t load %0d: %s", $time, nloads, msg);
    endtask

    // one load with value kk and mode en, followed by a check
    task automatic do_load(input integer kk, input bit en);
        logic [30:0] exp_sel;
        integer      exp_ptr;
        @(negedge clk);
        k      = kk[4:0];
        dwa_en = en;
        load   = 1'b1;
        @(negedge clk);
        load = 1'b0;
        nloads = nloads + 1;
        kcount[kk] = kcount[kk] + 1;
        if (en) begin
            exp_sel = run_mask(p_ref, kk);
            exp_ptr = (p_ref + kk) % N;
        end else begin
            exp_sel = run_mask(0, kk);
            exp_ptr = p_ref;
        end
        if (popc(sel) != kk) err($sformatf("popcount %0d != k %0d", popc(sel), kk));
        if (run_starts(sel) > 1) err($sformatf("not contiguous: sel=%08h", sel));
        if (sel !== exp_sel) err($sformatf("sel=%08h expected %08h (k=%0d p=%0d en=%0d)", sel, exp_sel, kk, p_ref, en));
        if (ptr !== exp_ptr[4:0]) err($sformatf("ptr=%0d expected %0d", ptr, exp_ptr));
        p_ref = exp_ptr;
        if (track_usage) begin
            integer mn, mx;
            mn = 1 << 30;
            mx = -1;
            for (int j = 0; j < N; j++) begin
                use_cnt[j] = use_cnt[j] + sel[j];
                if (use_cnt[j] < mn) mn = use_cnt[j];
                if (use_cnt[j] > mx) mx = use_cnt[j];
            end
            usage_checks = usage_checks + 1;
            if (mx - mn > 1) err($sformatf("element usage spread %0d > 1", mx - mn));
        end
        // change k without load: outputs must hold
        @(negedge clk);
        k = $random(seed);
        @(negedge clk);
        if (sel !== exp_sel || ptr !== exp_ptr[4:0]) err("sel/ptr changed without load");
    endtask

    initial begin
        for (int i = 0; i < 32; i++) kcount[i] = 0;
        for (int j = 0; j < N; j++) use_cnt[j] = 0;

        repeat (3) @(negedge clk);
        if (sel !== 31'h0000_FFFF || ptr !== 5'd0) err($sformatf("reset state sel=%08h ptr=%0d", sel, ptr));
        rst_n = 1'b1;
        // DWA-only phase from the reset pointer 0: the cumulative usage of the
        // elements selected by the loads must never differ by more than one.
        for (int rep = 0; rep < 20; rep++)
            for (int kk = 0; kk <= 31; kk++) do_load(kk, 1'b1);
        for (int i = 0; i < 50000; i++) do_load({$random(seed)} % 32, 1'b1);
        track_usage = 1'b0;

        // runs of constant k
        repeat (40) do_load(0, 1'b1);
        repeat (40) do_load(31, 1'b1);
        repeat (40) do_load(1, 1'b1);
        repeat (40) do_load(30, 1'b1);
        repeat (40) do_load(15, 1'b1);
        repeat (40) do_load(16, 1'b1);

        // thermometer mode, then back to DWA (continues from the held pointer)
        for (int kk = 0; kk <= 31; kk++) do_load(kk, 1'b0);
        for (int i = 0; i < 5000; i++) do_load({$random(seed)} % 32, 1'b0);
        for (int i = 0; i < 5000; i++) do_load({$random(seed)} % 32, 1'b1);

        // random mode toggling
        for (int i = 0; i < 100000; i++) do_load({$random(seed)} % 32, ({$random(seed)} % 4) != 0);

        for (int i = 0; i < 32; i++)
            if (kcount[i] < 100) err($sformatf("k=%0d tested only %0d times", i, kcount[i]));

        if (errors == 0)
            $display("PASS: tb_dwa (%0d loads, every k 0..31 >= %0d times, %0d usage-spread checks)",
                     nloads, 100, usage_checks);
        else
            $display("FAIL: tb_dwa (%0d errors in %0d loads)", errors, nloads);
        $finish;
    end

endmodule
