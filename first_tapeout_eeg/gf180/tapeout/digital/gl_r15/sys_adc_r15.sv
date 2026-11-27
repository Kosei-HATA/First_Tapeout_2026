// sys_adc_r15 - the ADC's digital block (eeg_adc_dig: TH capture, CODE, the two DWA selectors; unchanged since the macro
// f3 and the same on the chips r12 .. r15) on the r15 control macro's outputs (gl_r14/sys_adc_r15.sv of 11/25 with the
// r15 names, mk_sys_r15.py, 11/28; tracker C3).
//
// The r14 testbenches give eeg_digital_top's CODE input from a model of this block (CODE changes at e2, audit round 9),
// so no r14 test had the block itself. This module, compiled as a further root with +define+TB=<testbench>, hangs the
// block on the control's outputs (ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN) without changing the testbench, drives its TH
// with the thermometer of the code the testbench gives (+define+SYS_NEXT_CODE=<that code at the coming e2>,
// +define+SYS_NEXT_EVT=<the testbench variables it depends on>) and checks:
//   1. CODE: at every MCLK edge where the control takes CODE (the CIC and the overload detector at cic_en, the raw
//      serializer at frame cycle 31 when RAW is on: eeg_digital_top's only uses of CODE), the block's CODE equals the
//      testbench's. Then the control behaves as with the block itself, and every check of the testbench holds for the
//      two blocks together. Cycles where the two differ but CODE is not taken are counted (the block in reset ...).
//   2. SEL1 / SEL2 against a reference DWA (rtl/tb/tb_top.sv's): at every DAC_LOAD edge k = 31 - the code captured at
//      the frame's TH_CAPTURE edge (16 before a capture since reset), DWA_EN as the block takes it at that edge: the run of
//      k elements from the pointer (DWA) or elements 0..k-1 (thermometer); SEL changes at DAC_LOAD edges only; at every
//      CMP_STROBE rise popcount(SEL) = k of the last update; the excess loop delay CMP_STROBE -> SEL; DAC_CLK rises one
//      MCLK after the update and is one MCLK wide.
//   3. With +define+SYS_GL: the block's final netlist (layout/gds/eeg_adc_dig.nl.v, module eeg_adc_dig_gl; 7-track
//      cells) in lockstep with its RTL, CODE, SEL1 and SEL2 compared like gl_shadow_r15 (1 ps after every falling edge
//      without delays; just before every rising edge with +define+GL_SDF and +define+SYS_SDF_ADC=<its SDF>). Its CODE
//      goes to the control's netlist (gl_shadow_r15 with +define+GL_CODE_SRC=sys_adc_r15.code_gl): the loop closed at
//      gate level. Without delays the netlist's control inputs are the RTL control's outputs (equal to the control
//      netlist's at every compare, gl_shadow_r15; zero-delay netlists would otherwise race through their clock trees);
//      with the SDF they are the control netlist's own outputs.
// TH: without delays it follows the testbench's next code at once (at every falling edge and when SYS_NEXT_EVT changes);
// with +define+SYS_TH_LAUNCH=<ns> it changes that long after each CMP_STROBE rise and holds to the next one (on the chip
// TH is launched by e0 and settles a few ns after it; eeg_adc_dig's constraints take 15 ns and give the logic from TH to
// the capture flip-flops the two MCLK periods to e2).
`timescale 1ns / 1ps

module sys_adc_r15;
    localparam real TMCLK = 1000.0 / 32.768;

    wire        mclk       = `TB.MCLK;
    wire        reset_n    = `TB.RESET_N;
    wire        adc_rst_n  = `TB.dut.ADC_RST_N;
    wire        th_capture = `TB.dut.TH_CAPTURE;
    wire        dac_load   = `TB.dut.DAC_LOAD;
    wire        dwa_en     = `TB.dut.DWA_EN;
    wire        cmp_strobe = `TB.dut.CMP_STROBE;
    wire        dac_clk    = `TB.dut.DAC_CLK;
    wire [4:0]  code_tb    = `TB.CODE;

    function automatic logic [30:0] therm(input integer n);
        logic [30:0] v;
        v = '0;
        for (int i = 0; i < n; i++) v[i] = 1'b1;
        return v;
    endfunction
    function automatic integer popc(input logic [30:0] v);
        integer n;
        n = 0;
        for (int i = 0; i < 31; i++) n = n + v[i];
        return n;
    endfunction
    function automatic logic [30:0] run_mask(input integer p, input integer k);
        logic [30:0] m;
        m = '0;
        for (int j = 0; j < k; j++) m[(p + j) % 31] = 1'b1;
        return m;
    endfunction

    // ---------------------------------------------------------------- TH
    logic [30:0] th = '0;
    logic [4:0]  th_code = 5'd0;
    task automatic set_th;
        th_code = `SYS_NEXT_CODE;
        th = therm(th_code);
    endtask
`ifdef SYS_TH_LAUNCH
    always @(posedge cmp_strobe) begin
        #(`SYS_TH_LAUNCH);
        set_th();
    end
`else
    always @(negedge mclk) set_th();
    always @(`SYS_NEXT_EVT) set_th();
`endif

    // ---------------------------------------------------------------- the block (RTL)
    wire [4:0]  code_rtl;
    wire [30:0] sel1_rtl, sel2_rtl;
    eeg_adc_dig u_rtl (
        .MCLK (mclk), .RST_N (adc_rst_n), .TH_CAPTURE (th_capture), .DAC_LOAD (dac_load), .DWA_EN (dwa_en),
        .TH (th), .CODE (code_rtl), .SEL1 (sel1_rtl), .SEL2 (sel2_rtl)
    );
    wire blk_on = u_rtl.rst_loc_n;                // the block's own reset released

    // +sys_stop_us=<n>: stop the simulation after n us (short trials)
    integer stop_us;
    initial if ($value$plusargs("sys_stop_us=%d", stop_us)) begin
        #(stop_us * 1000.0);
        $display("sys_adc_r15: stopped at %0d us (+sys_stop_us)", stop_us);
        $finish;
    end

    integer errors = 0;
    task automatic err(input string msg);
        errors = errors + 1;
        if (errors <= 20) $display("SYS ERROR @%0t: %s", $time, msg);
    endtask

    // ---------------------------------------------------------------- 1. CODE as the control takes it
    longint n_take = 0, n_take_cic = 0, n_take_raw = 0;
    longint n_diff = 0, n_diff_rst = 0;
    always @(posedge mclk) if (reset_n === 1'b1) begin
        bit t_cic, t_raw;
        t_cic = (`TB.dut.cic_en === 1'b1);
        t_raw = (`TB.dut.cycle === 5'd31 && `TB.dut.raw_en === 1'b1);
        if (t_cic || t_raw) begin
            n_take = n_take + 1;
            if (t_cic) n_take_cic = n_take_cic + 1;
            if (t_raw) n_take_raw = n_take_raw + 1;
            if (code_rtl !== code_tb)
                err($sformatf("CODE taken by the control (%s): the block's %0d, the testbench's %0d",
                              t_cic ? "cic_en" : "raw", code_rtl, code_tb));
        end
    end
    always @(negedge mclk) if (code_rtl !== code_tb) begin
        n_diff = n_diff + 1;
        if (blk_on !== 1'b1) n_diff_rst = n_diff_rst + 1;
    end

    // ---------------------------------------------------------------- 2. SEL against a reference DWA
    integer    p_ref = 0;
    integer    k_cap = 16, k_last = -1;
    bit        cap_seen = 0;
    longint    n_cap = 0, n_load = 0, n_dwa = 0, n_therm = 0, n_pop = 0, n_dacclk = 0, n_dwa_chg = 0;
    real       t_load = -1.0, t_cmp = -1.0, eld_min = 1.0e9, eld_max = 0.0, t_dacclk = -1.0;
    logic      dwa_prev = 1'bx;
    always @(negedge blk_on) begin               // the block's asynchronous reset: pointer 0, k 16
        p_ref = 0; k_cap = 16; cap_seen = 0; k_last = -1;
    end
    always @(posedge mclk) if (blk_on === 1'b1) begin
        if (th_capture === 1'b1) begin
            k_cap = 31 - popc(th);
            cap_seen = 1;
            n_cap = n_cap + 1;
            #0.001;
            if (code_rtl !== 5'(31 - k_cap)) err($sformatf("CODE %0d after a capture of the thermometer of %0d", code_rtl, 31 - k_cap));
        end
    end
    always @(posedge mclk) if (blk_on === 1'b1 && dac_load === 1'b1) begin
        logic [30:0] e;
        logic        en;
        integer      k;
        k  = k_cap;
        en = dwa_en;
        if (en !== dwa_prev && dwa_prev !== 1'bx) n_dwa_chg = n_dwa_chg + 1;
        dwa_prev = en;
        t_load = $realtime;
        if (en === 1'b1) begin
            e = run_mask(p_ref, k);
            p_ref = (p_ref + k) % 31;
            n_dwa = n_dwa + 1;
        end else begin
            e = therm(k);
            n_therm = n_therm + 1;
        end
        k_last = k;
        n_load = n_load + 1;
        #0.001;
        if (sel1_rtl !== e || sel2_rtl !== e)
            err($sformatf("SEL1 %08h SEL2 %08h, expected %08h (k %0d, DWA_EN %b)", sel1_rtl, sel2_rtl, e, k, en));
    end
    // Outside resets only: RESET_N clears the block (SEL to its reset value) and DAC_CLK (eeg_digital_top's DAC_CLK
    // flip-flop on tm_rst_n = ADC_RST_N) at once, mid-pulse too (RST-01); the block's own reset net blk_on falls in the
    // same time step, possibly after DAC_CLK (11/25: tb_top_r14 phase W cut two DAC_CLK pulses to 7.248 ns that way, and
    // checked with blk_on alone they were counted as errors), so RESET_N and ADC_RST_N are required high as well.
    always @(sel1_rtl or sel2_rtl) if (reset_n === 1'b1 && adc_rst_n === 1'b1 && blk_on === 1'b1) begin
        if ($realtime != t_load) err("SEL changed away from a DAC_LOAD edge");
        if (t_cmp >= 0.0) begin
            if ($realtime - t_cmp < eld_min) eld_min = $realtime - t_cmp;
            if ($realtime - t_cmp > eld_max) eld_max = $realtime - t_cmp;
        end
    end
    always @(posedge cmp_strobe) begin
        t_cmp = $realtime;
        if (blk_on === 1'b1 && k_last >= 0) begin
            n_pop = n_pop + 1;
            if (popc(sel1_rtl) != k_last || popc(sel2_rtl) != k_last)
                err($sformatf("popcount(SEL) %0d / %0d at CMP_STROBE, expected %0d", popc(sel1_rtl), popc(sel2_rtl), k_last));
        end
    end
    always @(dac_clk) if (reset_n === 1'b1 && adc_rst_n === 1'b1 && blk_on === 1'b1 && t_load >= 0.0) begin
        if (dac_clk === 1'b1) begin
            n_dacclk = n_dacclk + 1;
            if ($realtime - t_load < TMCLK - 0.002 || $realtime - t_load > TMCLK + 0.002)
                err($sformatf("DAC_CLK rose %0.3f ns after the SEL update, expected one MCLK", $realtime - t_load));
            t_dacclk = $realtime;
        end else if (t_dacclk >= 0.0) begin
            if ($realtime - t_dacclk < TMCLK - 0.002 || $realtime - t_dacclk > TMCLK + 0.002)
                err($sformatf("DAC_CLK pulse of %0.3f ns, expected one MCLK", $realtime - t_dacclk));
        end
    end

    // ---------------------------------------------------------------- 3. the block's netlist
`ifdef SYS_GL
    wire [4:0]  code_gl;
    wire [30:0] sel1_gl, sel2_gl;
`ifdef GL_SDF
    eeg_adc_dig_gl g_adc (
        .MCLK (mclk), .RST_N (gl_shadow_r15.adc_rst_n), .TH_CAPTURE (gl_shadow_r15.th_capture),
        .DAC_LOAD (gl_shadow_r15.dac_load), .DWA_EN (gl_shadow_r15.dwa_en),
        .TH (th), .CODE (code_gl), .SEL1 (sel1_gl), .SEL2 (sel2_gl)
    );
    initial $sdf_annotate(`SYS_SDF_ADC, g_adc);
`else
    eeg_adc_dig_gl g_adc (
        .MCLK (mclk), .RST_N (adc_rst_n), .TH_CAPTURE (th_capture), .DAC_LOAD (dac_load), .DWA_EN (dwa_en),
        .TH (th), .CODE (code_gl), .SEL1 (sel1_gl), .SEL2 (sel2_gl)
    );
`endif
    longint gl_cycles = 0, gl_mismatch = 0;
    integer gl_reported = 0;
    task automatic gl_compare(input bit skip);
        gl_cycles = gl_cycles + 1;
        if (!skip && {code_gl, sel1_gl, sel2_gl} !== {code_rtl, sel1_rtl, sel2_rtl}) begin
            gl_mismatch = gl_mismatch + 1;
            if (gl_reported < 20) begin
                gl_reported = gl_reported + 1;
                $display("GL MISMATCH @%0t: eeg_adc_dig CODE %0d / %0d, SEL1 %08h / %08h, SEL2 %08h / %08h (gate level / RTL)",
                         $time, code_gl, code_rtl, sel1_gl, sel1_rtl, sel2_gl, sel2_rtl);
            end
        end
    endtask
`ifdef GL_SDF
    real t_edge = 0.0, settle_max = 0.0, t_settle_max = 0.0;
    always @({code_gl, sel1_gl, sel2_gl}) if (reset_n === 1'b1 && $realtime - t_edge > settle_max) begin
        settle_max = $realtime - t_edge;
        t_settle_max = $realtime;
    end
    integer since_rel = 0;
    always @(posedge mclk) begin
        t_edge = $realtime;
        since_rel = (reset_n === 1'b1) ? since_rel + 1 : 0;
        gl_compare(since_rel <= 2);
    end
`else
    always @(negedge mclk) begin
        #0.001;
        gl_compare(1'b0);
    end
    always @(negedge reset_n) begin
        #0.001;
        gl_compare(1'b0);
    end
`endif
`endif

    final begin
        $display("ADC block (eeg_adc_dig RTL) on the r15 control: CODE taken by the control %0d times (CIC and overload detector %0d, RAW %0d), always the block's; CODE differed from the testbench's in %0d other cycles (%0d of them with the block in reset); %0d captures, %0d SEL updates (DWA %0d, thermometer %0d, DWA_EN changes %0d), %0d popcount checks at CMP_STROBE, CMP_STROBE -> SEL %0.3f..%0.3f ns, %0d DAC_CLK pulses one MCLK after the update; errors %0d",
                 n_take, n_take_cic, n_take_raw, n_diff, n_diff_rst, n_cap, n_load, n_dwa, n_therm, n_dwa_chg, n_pop,
                 eld_min, eld_max, n_dacclk, errors);
        if (errors == 0 && n_take > 0 && n_load > 0)
            $display("PASS: ADC block on the r15 control (CODE as the control takes it, SEL1 / SEL2 against the reference DWA)");
        else
            $display("FAIL: ADC block on the r15 control (errors %0d)", errors);
`ifdef SYS_GL
`ifdef GL_SDF
        $display("eeg_adc_dig gate level with SDF (%s): latest output change %.3f ns after an MCLK rising edge (at %.3f ns)",
                 `SYS_SDF_ADC, settle_max, t_settle_max);
        if (gl_mismatch == 0)
            $display("PASS: eeg_adc_dig gate level (SDF) == RTL just before every MCLK rising edge (%0d cycles; CODE, SEL1, SEL2)", gl_cycles);
`else
        if (gl_mismatch == 0)
            $display("PASS: eeg_adc_dig gate level == RTL 1 ps after every MCLK falling edge (%0d cycles; CODE, SEL1, SEL2)", gl_cycles);
`endif
        else
            $display("FAIL: eeg_adc_dig gate level != RTL in %0d of %0d cycles", gl_mismatch, gl_cycles);
`endif
    end

endmodule
