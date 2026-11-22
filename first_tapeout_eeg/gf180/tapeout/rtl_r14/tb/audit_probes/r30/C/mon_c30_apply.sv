// mon_c30_apply - audit round 30 (C): a second top beside tb_top_r14 (as round 28 A's mon_afeclk): counts the register
// commits that fall in a cycle where the sequencer applies (apply) or acknowledges a command (cmd_ack), by address class.
`timescale 1ns / 1ps
module mon_c30_apply;
    integer n_apply = 0, n_ack = 0, n_we_apply = 0, n_we_apply_ok = 0, n_we_ack = 0, n_we_ack_cmd = 0;
    always @(posedge tb_top_r14.MCLK) begin
        if (tb_top_r14.dut.apply === 1'b1) n_apply = n_apply + 1;
        if (tb_top_r14.dut.cmd_ack === 1'b1) n_ack = n_ack + 1;
        if (tb_top_r14.dut.reg_we === 1'b1 && tb_top_r14.dut.apply === 1'b1) begin
            n_we_apply = n_we_apply + 1;
            if (tb_top_r14.dut.u_regs.w_ok === 1'b1) n_we_apply_ok = n_we_apply_ok + 1;
            $display("MON: write 0x%02h <- 0x%02h committed in an apply cycle (w_ok %b) at %0t", tb_top_r14.dut.reg_addr,
                     tb_top_r14.dut.reg_wdata, tb_top_r14.dut.u_regs.w_ok, $time);
        end
        if (tb_top_r14.dut.reg_we === 1'b1 && tb_top_r14.dut.cmd_ack === 1'b1) begin
            n_we_ack = n_we_ack + 1;
            if (tb_top_r14.dut.reg_addr == 7'h10) n_we_ack_cmd = n_we_ack_cmd + 1;
        end
    end
    final $display("MON: %0d apply cycles, %0d ack cycles; commits in an apply cycle %0d (carried out %0d); commits in an ack cycle %0d (to COMMAND %0d)",
                   n_apply, n_ack, n_we_apply, n_we_apply_ok, n_we_ack, n_we_ack_cmd);
endmodule
