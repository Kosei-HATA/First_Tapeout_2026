// audit38 C: a second top module beside tb_top_r14 (reads the DUT only): every STATUS copy (the header's at cs_start,
// a 0x03 register read's data at its load) taken in a cycle in which the sequencer acknowledges a pending command
// (cmd_ack), with the copied byte; and every apply with its command and state (as round 37's mon_cov)
`timescale 1ns / 1ps
module mon_c38;
    integer f, n_hdr = 0, n_dat = 0, n_dfw = 0, n_dfw_store = 0, n_dfw_snap = 0, n_dfw_near = 0;
    real t_store = -1.0e9;
    initial f = $fopen("build/c38_ack_copies.txt", "w");
    always @(posedge tb_top_r14.MCLK) begin
        // a committed DFLAG write (W1C) and the stores / empty-word copies of the same cycle (spec 3.4, 3.2)
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.push_ok === 1'b1) t_store = $realtime;
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.u_regs.we === 1'b1 && tb_top_r14.dut.u_regs.addr == 7'h07) begin
            n_dfw = n_dfw + 1;
            if ($realtime - t_store < 64.0 * 30.52) n_dfw_near = n_dfw_near + 1;
            if (tb_top_r14.dut.push_ok === 1'b1) begin
                n_dfw_store = n_dfw_store + 1;
                $fdisplay(f, "DFW_STORE t=%0t phase=%0s dflag=%0d wdata=%02h", $time, tb_top_r14.phase,
                          tb_top_r14.dut.u_regs.dflag, tb_top_r14.dut.u_regs.wdata);
            end
            if (tb_top_r14.dut.smp_snap === 1'b1) begin
                n_dfw_snap = n_dfw_snap + 1;
                $fdisplay(f, "DFW_SNAP t=%0t phase=%0s dflag=%0d lvl=%0d", $time, tb_top_r14.phase,
                          tb_top_r14.dut.u_regs.dflag, tb_top_r14.dut.fifo_level);
            end
        end
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.cmd_ack === 1'b1) begin
            if (tb_top_r14.dut.u_spi.cs_start === 1'b1) begin
                n_hdr = n_hdr + 1;
                $fdisplay(f, "HDR t=%0t phase=%0s status=%02h pend=%0d cmd=%02h st=%0d", $time, tb_top_r14.phase,
                          tb_top_r14.dut.status_byte, tb_top_r14.dut.u_regs.pend, tb_top_r14.dut.cmd_code,
                          tb_top_r14.dut.seq_state);
            end
            if (tb_top_r14.dut.u_spi.st == 4'd2 && tb_top_r14.dut.u_spi.reg_addr == 7'h03 &&
                tb_top_r14.dut.u_spi.bit_cnt == 3'd0 && tb_top_r14.dut.u_spi.sclk_fall === 1'b1 &&
                !tb_top_r14.dut.u_spi.cs_start && !tb_top_r14.dut.u_spi.cs_end) begin
                n_dat = n_dat + 1;
                $fdisplay(f, "DAT t=%0t phase=%0s status=%02h pend=%0d cmd=%02h st=%0d", $time, tb_top_r14.phase,
                          tb_top_r14.dut.status_byte, tb_top_r14.dut.u_regs.pend, tb_top_r14.dut.cmd_code,
                          tb_top_r14.dut.seq_state);
            end
        end
    end
    final $fdisplay(f, "TOTAL header copies in an ack cycle %0d, 0x03 data loads in an ack cycle %0d; DFLAG writes committed %0d, in a store's cycle %0d, in an empty-word copy's cycle %0d, within 64 MCLK after a store %0d", n_hdr, n_dat, n_dfw, n_dfw_store, n_dfw_snap, n_dfw_near);
endmodule
