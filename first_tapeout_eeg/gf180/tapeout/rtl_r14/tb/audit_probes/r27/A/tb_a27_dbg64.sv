// audit 27 A: DBG_SEL 1..3 pad edges against the AFE chopper phase (CHOP level one MCLK before the pad edge)
`timescale 1ns / 1ps
`default_nettype none
module tb_a27_dbg64;
    logic clk = 0, rst_n = 0, chop_fast = 0;
    logic [4:0] cycle;
    logic cmp_strobe, th_capture, dac_load, cic_en, chop, chop_out, chop_blank, raw_clk, tick, chop1, dac_clk;
    logic [2:0] rate = 3'd1;
    logic [1:0] dbg_sel = 2'd3;
    logic raw_data_o, raw_clk_o;
    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) u_clk (.clk(clk), .rst_n(rst_n), .chop_fast(chop_fast), .chop_dly(8'd0),
        .blank_len(4'd15), .cycle(cycle), .cmp_strobe(cmp_strobe), .th_capture(th_capture), .dac_load(dac_load),
        .cic_en(cic_en), .chop(chop), .chop_out(chop_out), .chop_blank(chop_blank), .raw_clk(raw_clk), .tick(tick));
    eeg_chop1 u_c1 (.clk(clk), .rst_n(rst_n), .cycle(cycle), .chop1_rate(rate), .chop1(chop1));
    always_ff @(posedge clk or negedge rst_n) if (!rst_n) dac_clk <= 0; else dac_clk <= (cycle == 5'd3);
    eeg_raw u_raw (.clk(clk), .rst_n(rst_n), .raw_en(1'b0), .cycle(cycle), .raw_clk(raw_clk), .code(5'd9),
                   .dbg_sel(dbg_sel), .dbg_clk({chop_blank, chop, cmp_strobe}), .dbg_data({chop1, chop_out, dac_clk}),
                   .raw_data_o(raw_data_o), .raw_clk_o(raw_clk_o));
    always #15.259 clk = ~clk;
    integer s, n;
    integer d_rise[0:1], d_fall[0:1], c_rise[0:1], c_fall[0:1];   // [phase B, phase A] counts of pad edges
    logic pd, pc, chop_q;
    initial begin
        for (s = 1; s <= 3; s++) begin
            for (n = 0; n < 2; n++) begin d_rise[n] = 0; d_fall[n] = 0; c_rise[n] = 0; c_fall[n] = 0; end
            dbg_sel = s[1:0]; rst_n = 0; repeat (3) @(negedge clk); rst_n = 1;
            repeat (64) @(posedge clk);
            pd = raw_data_o; pc = raw_clk_o; chop_q = chop;
            repeat (2048 * 32) begin
                @(posedge clk); #1;
                // the phase the AFE is in when the pad moves: CHOP as it was during the MCLK before the edge
                if (raw_data_o && !pd) d_rise[chop_q]++;  if (!raw_data_o && pd) d_fall[chop_q]++;
                if (raw_clk_o && !pc) c_rise[chop_q]++;   if (!raw_clk_o && pc) c_fall[chop_q]++;
                pd = raw_data_o; pc = raw_clk_o; chop_q = chop;
            end
            $display("DBG_SEL %0d: RAW_DATA rises A/B %0d/%0d falls A/B %0d/%0d | RAW_CLK rises A/B %0d/%0d falls A/B %0d/%0d",
                     s, d_rise[1], d_rise[0], d_fall[1], d_fall[0], c_rise[1], c_rise[0], c_fall[1], c_fall[0]);
        end
        $finish;
    end
endmodule
`default_nettype wire
