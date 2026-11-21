R = "gf180/tapeout/rtl_r14/"
O = "gf180/tapeout/rtl/"
MUTANTS = {
    "u1_cic_soft": ("CIC reset by SOFT_RESET (RST-02 says it runs from RESET_N)",
        [(R + "eeg_digital_top.sv", "eeg_cic3 u_cic (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_cic3 u_cic (.clk(MCLK), .rst_n(rst_n),")]),
    "u6_miso_stale": ("SPI: the shift register is not cleared at CS_N rising (MISO's first MCLK of the next frame is the "
                      "previous frame's last bit, not the documented 1-MCLK Low)",
        [(R + "eeg_spi_slave.sv", "                st    <= S_IDLE;\n                tx_sh <= 8'h00;", "                st    <= S_IDLE;")]),
    "u2_ofs_r0": ("regs: OFS pin register takes the sign also in range 0",
        [(R + "eeg_regs.sv", "o_ofs  <= (s_range == 3'd0) ? 1'b0  : s_sign;", "o_ofs  <= s_sign;")]),
    "u3_armed_pin": ("SPI: armed from the unsynchronized CS_N pin",
        [(R + "eeg_spi_slave.sv", "if (cs_q[1]) armed <= 1'b1;", "if (cs_n) armed <= 1'b1;")]),
    "u4_drdy_late": ("top: DRDY pulse register from drdy_cnt (pulse one MCLK later, same width)",
        [(R + "eeg_digital_top.sv", "drdy_pulse <= (drdy_nxt != 3'd0);", "drdy_pulse <= (drdy_cnt != 3'd0);")]),
    "u5_rawclk_live": ("raw: RAW_CLK gated by the live RAW_EN register instead of the frame-latched `on`",
        [(O + "eeg_raw.sv", "raw_clk_o  <= on & raw_clk;", "raw_clk_o  <= raw_en & raw_clk;")]),
}
