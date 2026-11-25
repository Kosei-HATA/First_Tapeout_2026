// audit43 C: coverage monitor, a second top module beside tb_top_r14 (reads the DUT only; changes nothing).
`timescale 1ns / 1ps
module mon43;
    integer f;
    initial f = $fopen("build/mon43.txt", "w");
    // (b) register-read data bytes whose register changed at the start of the load cycle (a 1-MCLK-late read path
    // differs exactly there), per address
    integer chg_at_load [0:127];
    integer loads [0:127];
    logic [7:0] rd_prev;
    logic [6:0] ad_prev;
    // (a) blanking length changed while a blanking pulse runs
    integer n_blank_chg_mid = 0, n_soft = 0, n_soft_blank = 0, n_soft_dac = 0;
    logic [3:0] bl_prev = 4'd1;
    // (c) DRDY_MODE changed while the pulse counter runs
    integer n_mode_chg_cnt = 0, n_mode_chg = 0;
    logic drdy_mode_prev = 1'b0;
    // (d) ovl_hit per sequencer state; stores per state
    integer ovl_hit_st [0:15];
    // (e) a_fast changes; a_c1 changes
    integer n_fast_chg = 0, n_fast_soft = 0, n_c1_chg = 0;
    logic fast_prev = 1'b1; logic [2:0] c1_prev = 3'd2;
    // (f) soft reset per state
    integer soft_st [0:15];
    // (g) applies per state with which fields changed
    integer n_apply = 0;
    integer i;
    initial begin
        for (i = 0; i < 128; i++) begin chg_at_load[i] = 0; loads[i] = 0; end
        for (i = 0; i < 16; i++) begin ovl_hit_st[i] = 0; soft_st[i] = 0; end
    end
    always @(posedge tb_top_r14.MCLK) begin
        if (tb_top_r14.dut.rst_n === 1'b1) begin
            // the load: the cycle the SPI takes tx_next for a data byte of a register read (S_RREG, bit_cnt 0, sclk_fall)
            if (tb_top_r14.dut.u_spi.sclk_fall === 1'b1 && tb_top_r14.dut.u_spi.bit_cnt === 3'd0 &&
                tb_top_r14.dut.u_spi.st === 4'd2 && !tb_top_r14.dut.u_spi.cs_start && !tb_top_r14.dut.u_spi.cs_end) begin
                loads[tb_top_r14.dut.u_spi.reg_addr] = loads[tb_top_r14.dut.u_spi.reg_addr] + 1;
                if (ad_prev === tb_top_r14.dut.u_spi.reg_addr && rd_prev !== tb_top_r14.dut.u_spi.reg_rdata)
                    chg_at_load[tb_top_r14.dut.u_spi.reg_addr] = chg_at_load[tb_top_r14.dut.u_spi.reg_addr] + 1;
            end
            if (tb_top_r14.dut.u_clkgen.chop_blank === 1'b1 && tb_top_r14.dut.a_blank_len !== bl_prev)
                n_blank_chg_mid = n_blank_chg_mid + 1;
            if (tb_top_r14.dut.drdy_mode !== drdy_mode_prev) begin
                n_mode_chg = n_mode_chg + 1;
                if (tb_top_r14.dut.drdy_cnt !== 3'd0) n_mode_chg_cnt = n_mode_chg_cnt + 1;
            end
            if (tb_top_r14.dut.u_ovl.ovl_hit === 1'b1) ovl_hit_st[tb_top_r14.dut.seq_state] = ovl_hit_st[tb_top_r14.dut.seq_state] + 1;
            if (tb_top_r14.dut.a_chop_fast !== fast_prev) n_fast_chg = n_fast_chg + 1;
            if (tb_top_r14.dut.a_c1 !== c1_prev) n_c1_chg = n_c1_chg + 1;
            if (tb_top_r14.dut.u_regs.apply === 1'b1) n_apply = n_apply + 1;
        end
        if (tb_top_r14.dut.soft_req === 1'b1) begin
            n_soft = n_soft + 1;
            soft_st[tb_top_r14.dut.seq_state] = soft_st[tb_top_r14.dut.seq_state] + 1;
            if (tb_top_r14.dut.u_clkgen.chop_blank === 1'b1) n_soft_blank = n_soft_blank + 1;
            if (tb_top_r14.dut.u_regs.a_range !== 3'd0) n_soft_dac = n_soft_dac + 1;
            if (tb_top_r14.dut.a_chop_fast !== 1'b1) n_fast_soft = n_fast_soft + 1;
        end
        rd_prev = tb_top_r14.dut.u_spi.reg_rdata;
        ad_prev = tb_top_r14.dut.u_spi.reg_addr;
        bl_prev = tb_top_r14.dut.a_blank_len;
        drdy_mode_prev = tb_top_r14.dut.drdy_mode;
        fast_prev = tb_top_r14.dut.a_chop_fast;
        c1_prev = tb_top_r14.dut.a_c1;
    end
    final begin
        $fdisplay(f, "soft resets %0d, during a blanking pulse %0d, with the DAC on %0d, at 64 kHz %0d", n_soft, n_soft_blank, n_soft_dac, n_fast_soft);
        for (i = 0; i < 16; i++) if (soft_st[i]) $fdisplay(f, "  soft reset in state %0d: %0d", i, soft_st[i]);
        $fdisplay(f, "blank_len changed during a blanking pulse: %0d", n_blank_chg_mid);
        $fdisplay(f, "DRDY_MODE changes %0d, with the pulse counter running %0d", n_mode_chg, n_mode_chg_cnt);
        for (i = 0; i < 16; i++) if (ovl_hit_st[i]) $fdisplay(f, "  ovl_hit in state %0d: %0d", i, ovl_hit_st[i]);
        $fdisplay(f, "CHOP_FAST active changes %0d, CHOP1 rate active changes %0d, applies %0d", n_fast_chg, n_c1_chg, n_apply);
        for (i = 0; i < 128; i++) if (loads[i]) $fdisplay(f, "  addr %02h: %0d data-byte loads, %0d with the register changed at the load cycle's start", i, loads[i], chg_at_load[i]);
        $fclose(f);
    end
endmodule
