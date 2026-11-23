// audit38 C probe: eeg_regs alone. (1) STATUS's CMD_PENDING in the cycle the tick acknowledges a pending command
// (spec 3.2: STATUS is the value of the copy's cycle; pend is 1 until the edge that ends it). (2) dflag_overrun (the
// sample's and the empty word's OVERRUN) in the cycle a W1C of DFLAG commits (spec 3.4: the value of the store's
// cycle; a flag that changes at the writing edge is not included).
`timescale 1ns / 1ps
module tb_c38_regs;
    logic clk = 0, rst_n = 0;
    logic [6:0] addr = 0; logic we = 0; logic [7:0] wdata = 0;
    logic cmd_ack = 0, apply = 0, ovr_set = 0;
    wire [7:0] rdata, status_byte, cmd_code; wire addr_ok, cmd_valid, soft_reset, cfg_ok, nr_ok, alert, dflag_overrun;
    wire [9:0] off_mag; wire off_sign; wire [3:0] ofen, cpf_trim, atp_sel, blank_len; wire [1:0] afe_ibias, btrim_p, btrim_n, dbg_sel;
    wire chop_fast, dwa_en, atp_en, chop_stop, adc_zero, raw_en, crc_en, drdy_mode; wire [2:0] chop1_rate;
    wire [7:0] t_warm, t_elec, t_rec, t_pre, t_rst;
    eeg_regs #(.FIFO_DEPTH(8)) dut (.clk(clk), .rst_n(rst_n), .addr(addr), .rdata(rdata), .addr_ok(addr_ok), .we(we),
        .wdata(wdata), .frame_err_set(1'b0), .crc_err_set(1'b0), .addr_err_set(1'b0), .state(4'd0), .afe_rst(1'b1),
        .fifo_nonempty(1'b0), .fifo_level(4'd0), .ovl_now(1'b0), .ovr_set(ovr_set), .ovl_set(1'b0), .seq_state_err(1'b0),
        .seq_cfg_err(1'b0), .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(cmd_ack), .soft_reset(soft_reset),
        .apply(apply), .cfg_ok(cfg_ok), .nr_ok(nr_ok), .off_mag(off_mag), .off_sign(off_sign), .ofen(ofen),
        .afe_ibias(afe_ibias), .cpf_trim(cpf_trim), .btrim_p(btrim_p), .btrim_n(btrim_n), .chop_fast(chop_fast),
        .dwa_en(dwa_en), .chop1_rate(chop1_rate), .blank_len(blank_len), .atp_en(atp_en), .atp_sel(atp_sel),
        .chop_stop(chop_stop), .adc_zero(adc_zero), .raw_en(raw_en), .dbg_sel(dbg_sel), .crc_en(crc_en),
        .drdy_mode(drdy_mode), .t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst),
        .status_byte(status_byte), .alert(alert), .dflag_overrun(dflag_overrun));
    always #15.26 clk = ~clk;
    initial begin
        repeat (3) @(posedge clk); #1 rst_n = 1;
        @(negedge clk); addr = 7'h10; wdata = 8'h55; we = 1;            // FLUSH committed: pending
        @(negedge clk); we = 0;
        @(negedge clk); $display("before the tick: pend %b, STATUS 0x%02h (CMD_PENDING %b)", dut.pend, status_byte, status_byte[4]);
        cmd_ack = 1; #1;                                                  // the acknowledge cycle (the tick)
        $display("in the acknowledge cycle: pend %b, STATUS 0x%02h (CMD_PENDING %b) <- a header copied in this cycle", dut.pend, status_byte, status_byte[4]);
        @(negedge clk); cmd_ack = 0; #1;
        $display("after the tick: pend %b, STATUS 0x%02h (CMD_PENDING %b)", dut.pend, status_byte, status_byte[4]);
        ovr_set = 1; @(negedge clk); ovr_set = 0; @(negedge clk);
        $display("DFLAG 0x%0h, dflag_overrun %b", dut.dflag, dflag_overrun);
        addr = 7'h07; wdata = 8'h01; we = 1; #1;                          // DFLAG W1C committed in this cycle
        $display("in the cycle of a DFLAG W1C commit: DFLAG register 0x%0h, dflag_overrun %b <- a store in this cycle writes it", dut.dflag, dflag_overrun);
        @(negedge clk); we = 0; #1;
        $display("after it: DFLAG 0x%0h, dflag_overrun %b", dut.dflag, dflag_overrun);
        $finish;
    end
endmodule
