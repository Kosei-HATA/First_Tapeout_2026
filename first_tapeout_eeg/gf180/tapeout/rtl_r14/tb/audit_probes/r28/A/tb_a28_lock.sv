// tb_a28_lock - audit round 28, auditor A: a test setting written to its shadow while the key is open and left
// unapplied survives the lock; the next apply (START, APPLY, or APPLY_NR in IDLE / WARMUP) drives it onto TEST_CFG /
// CHOP_EN, the host cannot write it back while locked, and every APPLY_NR in RUN is refused (nr_ok 0).
`timescale 1ns / 1ps
`default_nettype none
module tb_a28_lock;
`include "eeg_regs_defs.svh"
    logic clk = 0, rst_n = 0, we = 0, apply = 0;
    logic [6:0] addr = 0;
    logic [7:0] wdata = 0, rdata, status_byte, cmd_code, t_warm, t_elec, t_rec, t_pre, t_rst;
    logic addr_ok, cmd_valid, soft_reset, cfg_ok, nr_ok, off_sign, chop_fast, dwa_en, atp_en, chop_stop, adc_zero;
    logic raw_en, crc_en, drdy_mode, alert, dflag_overrun;
    logic [9:0] off_mag; logic [3:0] ofen, cpf_trim, blank_len, atp_sel; logic [1:0] afe_ibias, btrim_p, btrim_n, dbg_sel;
    logic [2:0] chop1_rate;
    eeg_regs #(.FIFO_DEPTH(8)) dut (.clk(clk), .rst_n(rst_n), .addr(addr), .rdata(rdata), .addr_ok(addr_ok), .we(we),
        .wdata(wdata), .frame_err_set(1'b0), .crc_err_set(1'b0), .addr_err_set(1'b0), .state(4'd6), .afe_rst(1'b0),
        .fifo_nonempty(1'b0), .fifo_level(4'd0), .ovl_now(1'b0), .ovr_set(1'b0), .ovl_set(1'b0), .seq_state_err(1'b0),
        .seq_cfg_err(1'b0), .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(1'b0), .soft_reset(soft_reset),
        .apply(apply), .cfg_ok(cfg_ok), .nr_ok(nr_ok), .off_mag(off_mag), .off_sign(off_sign), .ofen(ofen),
        .afe_ibias(afe_ibias), .cpf_trim(cpf_trim), .btrim_p(btrim_p), .btrim_n(btrim_n), .chop_fast(chop_fast),
        .dwa_en(dwa_en), .chop1_rate(chop1_rate), .blank_len(blank_len), .atp_en(atp_en), .atp_sel(atp_sel),
        .chop_stop(chop_stop), .adc_zero(adc_zero), .raw_en(raw_en), .dbg_sel(dbg_sel), .crc_en(crc_en),
        .drdy_mode(drdy_mode), .t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst),
        .status_byte(status_byte), .alert(alert), .dflag_overrun(dflag_overrun));
    always #15 clk = ~clk;
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        @(negedge clk); addr = a; wdata = d; we = 1; @(negedge clk); we = 0;
    endtask
    initial begin
        #40 rst_n = 1;
        wr(A_TEST_KEY, 8'h3C);                   // unlock
        wr(A_TEST_MUX, 8'h1C);                   // ATP_EN 1, ATP_SEL 12 (an AFE output to the ATP pad), not applied
        wr(A_TEST_CTRL, 8'h02);                  // CHOP_STOP 1, not applied
        wr(A_TEST_KEY, 8'h00);                   // lock
        wr(A_TEST_MUX, 8'h00);                   // the host tries to undo it: refused while locked
        @(negedge clk);
        $display("after lock: shadow TEST_MUX 0x%02h TEST_CTRL 0x%02h, ERR 0x%02h, nr_ok %b (pins: ATP_EN %b SEL %0d CHOP_STOP %b)",
                 {3'd0, dut.s_atpen, dut.s_atpsel}, {6'd0, dut.s_cstop, dut.s_azero}, dut.err, nr_ok, atp_en, atp_sel, chop_stop);
        @(negedge clk); apply = 1; @(negedge clk); apply = 0;       // the next START / APPLY of the normal flow
        @(negedge clk);
        $display("after the next apply: ATP_EN %b ATP_SEL %0d CHOP_STOP %b (CHOP_EN %b)", atp_en, atp_sel, chop_stop, ~chop_stop);
        $finish;
    end
endmodule
`default_nettype wire
