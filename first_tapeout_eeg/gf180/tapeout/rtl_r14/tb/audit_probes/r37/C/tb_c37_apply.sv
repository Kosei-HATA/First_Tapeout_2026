// audit 37, auditor C: eeg_regs alone. (1) IDLE: CHOP_CFG 0, BLANK 3, ADC_CFG 0x05, TEST_CTRL 0x02 (unlocked), then an
// APPLY_NR acknowledged with apply (afe_rst 1): the active copies take every setting (table 5.1-2). (2) RUN (afe_rst 0):
// TEST_MUX 0x15, TEST_CTRL 0x01, AFE_IBIAS 1, then an APPLY acknowledged with apply: the copies take them.
// (3) CFG_ERR standing (seq_cfg_err pulse), then an accepted apply: ERR keeps CFG_ERR (REG-02).
`timescale 1ns / 1ps
module tb_c37_apply;
    logic clk = 0, rst_n = 0;
    always #15 clk = ~clk;
    logic [6:0] addr = 0; logic we = 0; logic [7:0] wdata = 0;
    logic cmd_ack = 0, apply = 0, afe_rst = 1, cfg_err = 0;
    logic [7:0] rdata; logic addr_ok, cmd_valid, soft_reset, cfg_ok, nr_ok;
    logic [7:0] cmd_code; logic [9:0] off_mag; logic off_sign; logic [3:0] ofen, cpf, blank, atp_sel;
    logic [1:0] ibias, bp, bn, dbg; logic chop_fast, dwa, atp_en, chop_stop, adc_zero, raw_en, crc_en, drdy_mode;
    logic [2:0] c1; logic [7:0] tw, te, trec, tpre, trst, status; logic alert, dovr;
    eeg_regs u (.clk(clk), .rst_n(rst_n), .addr(addr), .rdata(rdata), .addr_ok(addr_ok), .we(we), .wdata(wdata),
        .frame_err_set(1'b0), .crc_err_set(1'b0), .addr_err_set(1'b0), .state(4'd0), .afe_rst(afe_rst),
        .fifo_nonempty(1'b0), .fifo_level(4'd0), .ovl_now(1'b0), .ovr_set(1'b0), .ovl_set(1'b0),
        .seq_state_err(1'b0), .seq_cfg_err(cfg_err), .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(cmd_ack),
        .soft_reset(soft_reset), .apply(apply), .cfg_ok(cfg_ok), .nr_ok(nr_ok), .off_mag(off_mag), .off_sign(off_sign),
        .ofen(ofen), .afe_ibias(ibias), .cpf_trim(cpf), .btrim_p(bp), .btrim_n(bn), .chop_fast(chop_fast), .dwa_en(dwa),
        .chop1_rate(c1), .blank_len(blank), .atp_en(atp_en), .atp_sel(atp_sel), .chop_stop(chop_stop),
        .adc_zero(adc_zero), .raw_en(raw_en), .dbg_sel(dbg), .crc_en(crc_en), .drdy_mode(drdy_mode), .t_warm(tw),
        .t_elec(te), .t_rec(trec), .t_pre(tpre), .t_rst(trst), .status_byte(status), .alert(alert), .dflag_overrun(dovr));
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        @(negedge clk); addr = a; wdata = d; we = 1; @(negedge clk); we = 0;
    endtask
    task automatic take();                               // the tick takes the pending command and applies
        @(negedge clk); cmd_ack = 1; apply = 1; @(negedge clk); cmd_ack = 0; apply = 0;
    endtask
    logic [7:0] e;
    initial begin
        repeat (3) @(negedge clk); rst_n = 1;
        wr(7'h06, 8'hFF);
        // (1) IDLE (afe_rst 1): APPLY_NR
        wr(7'h26, 8'h00); wr(7'h28, 8'h03); wr(7'h27, 8'h05); wr(7'h11, 8'h3C); wr(7'h61, 8'h02); wr(7'h11, 8'h00);
        wr(7'h10, 8'h44); take();
        $display("(1) APPLY_NR in IDLE: CHOP_FAST %0d (want 0), BLANK %0d (want 3), CHOP1 %0d (want 5), CHOP_STOP %0d (want 1)",
                 chop_fast, blank, c1, chop_stop);
        // (2) RUN (afe_rst 0): APPLY
        afe_rst = 0;
        wr(7'h11, 8'h3C); wr(7'h60, 8'h15); wr(7'h61, 8'h01); wr(7'h11, 8'h00); wr(7'h23, 8'h01);
        wr(7'h10, 8'h33); take();
        $display("(2) APPLY in RUN: ATP_EN %0d ATP_SEL %0d (want 1, 5), ADC_ZERO %0d CHOP_STOP %0d (want 1, 0), AFE_IBIAS %0d (want 1)",
                 atp_en, atp_sel, adc_zero, chop_stop, ibias);
        // (3) CFG_ERR standing, then an accepted APPLY
        wr(7'h06, 8'hFF);
        @(negedge clk); cfg_err = 1; @(negedge clk); cfg_err = 0;
        wr(7'h10, 8'h33); take();
        @(negedge clk); addr = 7'h06; #1 e = rdata;
        $display("(3) ERR after a CFG_ERR and then an accepted APPLY: 0x%02h (want 0x20)", e);
        $finish;
    end
endmodule
