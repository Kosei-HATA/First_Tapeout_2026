// Audit round 29 (C): a second top-level module run beside tb_top_r14 / tb_spi_r14 (hierarchical references only,
// no stimulus): every committed write at the register block's port, with the test key's state at that cycle and the
// error events it raised; and DAC_CLK while RESET_N is low. Written to build/mon_lock.txt.
`timescale 1ns / 1ps
module mon_lock;
    integer fd, n = 0, dac_rst_hi = 0, dac_rst_samples = 0;
    initial fd = $fopen("build/mon_lock.txt", "w");
    always @(posedge `TBTOP.MCLK) begin
        if (`TBTOP.dut.reg_we === 1'b1) begin
            $fdisplay(fd, "W %02h %02h %0d %02h", `TBTOP.dut.reg_addr, `TBTOP.dut.reg_wdata, `TBTOP.dut.u_regs.unlocked,
                      `TBTOP.dut.u_regs.ev_err);
            n = n + 1;
        end
        if (`TBTOP.RESET_N === 1'b0) begin
            dac_rst_samples = dac_rst_samples + 1;
            if (`TBTOP.DAC_CLK !== 1'b0) dac_rst_hi = dac_rst_hi + 1;
        end
    end
    final begin
        $fdisplay(fd, "E %0d commits; DAC_CLK sampled %0d times with RESET_N low, %0d of them not 0", n, dac_rst_samples,
                  dac_rst_hi);
        $fclose(fd);
    end
endmodule
