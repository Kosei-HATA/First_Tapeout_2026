// audit round 28, auditor C: ERR across W1C writes to DFLAG (eeg_regs alone). After a reset (RESET_FLAG) and a
// FRAME_ERR, the host's write-backs of DFLAG.OVERRUN (0x01) and DFLAG.OVL (0x02) and a 0xFF to DFLAG; ERR read each time.
`timescale 1ns / 1ps
`default_nettype none
module tb_c28_w1c;
    logic clk = 0, rst_n = 0;
    logic [6:0] addr = 0; logic [7:0] rdata, wdata = 0; logic addr_ok, we = 0;
    logic fe = 0;
    logic cmd_valid, cmd_ack = 0, soft_r, apply = 0, cfg_ok, nr_ok, alert, dfo;
    logic [7:0] cmd_code, status_byte, t_warm, t_elec, t_rec, t_pre, t_rst;
    logic [9:0] ofm; logic ofs; logic [3:0] ofen, cpf, atp_sel, blank; logic [1:0] ib, bp, bn, dbg; logic [2:0] c1;
    logic fast, dwa, atp_en, cstop, azero, raw, crc, drdy;
    eeg_regs dut (.clk(clk), .rst_n(rst_n), .addr(addr), .rdata(rdata), .addr_ok(addr_ok), .we(we), .wdata(wdata),
        .frame_err_set(fe), .crc_err_set(1'b0), .addr_err_set(1'b0), .state(4'd0), .afe_rst(1'b1), .fifo_nonempty(1'b0),
        .fifo_level(4'd0), .ovl_now(1'b0), .ovr_set(1'b0), .ovl_set(1'b0), .seq_state_err(1'b0), .seq_cfg_err(1'b0),
        .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(cmd_ack), .soft_reset(soft_r), .apply(apply), .cfg_ok(cfg_ok),
        .nr_ok(nr_ok), .off_mag(ofm), .off_sign(ofs), .ofen(ofen), .afe_ibias(ib), .cpf_trim(cpf), .btrim_p(bp),
        .btrim_n(bn), .chop_fast(fast), .dwa_en(dwa), .chop1_rate(c1), .blank_len(blank), .atp_en(atp_en),
        .atp_sel(atp_sel), .chop_stop(cstop), .adc_zero(azero), .raw_en(raw), .dbg_sel(dbg), .crc_en(crc),
        .drdy_mode(drdy), .t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst),
        .status_byte(status_byte), .alert(alert), .dflag_overrun(dfo));
    always #15 clk = ~clk;
    task automatic wr(input logic [6:0] a, input logic [7:0] d);
        @(negedge clk); addr = a; wdata = d; we = 1; @(negedge clk); we = 0;
    endtask
    task automatic rd(input logic [6:0] a, output logic [7:0] v); @(negedge clk); addr = a; #1 v = rdata; endtask
    logic [7:0] e;
    initial begin
        repeat (3) @(negedge clk); rst_n = 1;
        @(negedge clk); fe = 1; @(negedge clk); fe = 0;             // FRAME_ERR
        rd(7'h06, e); $display("ERR after reset and FRAME_ERR: 0x%02h", e);
        wr(7'h07, 8'h01); rd(7'h06, e); $display("ERR after the W1C 0x01 to DFLAG (OVERRUN write-back): 0x%02h", e);
        wr(7'h07, 8'h02); rd(7'h06, e); $display("ERR after the W1C 0x02 to DFLAG (OVL write-back): 0x%02h", e);
        $finish;
    end
endmodule
`default_nettype wire
