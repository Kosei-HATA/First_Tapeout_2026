R14 = "gf180/tapeout/rtl_r14"
OLD = "gf180/tapeout/rtl"
MUTANTS = {
    # SPI armed one synchronizer stage later (the edge detector's older stage): RST-01's ~9.75 MCLK becomes ~10.75
    "s_armed_late": [(f"{R14}/eeg_spi_slave.sv", "if (cs_q[1]) armed <= 1'b1;", "if (cs_q[2]) armed <= 1'b1;")],
    # the sample CRC over the live FIFO head instead of the copy taken at the header
    "s_smp_crc_live": [(f"{R14}/eeg_spi_slave.sv", "default: tx_next = crc8_48(CRC_SMP_HDR, shadow);",
                        "default: tx_next = crc8_48(CRC_SMP_HDR, smp_word);")],
    # SOFT_RESET decoded from the data byte alone (the address compare dropped): 0xA5 written anywhere resets
    "r_soft_any_addr": [(f"{R14}/eeg_regs.sv",
                         "assign soft_reset = we && wr_def && !wr_ro && (addr == A_COMMAND) && is_soft;",
                         "assign soft_reset = we && wr_def && !wr_ro && is_soft;")],
    # a command latched from any accepted write of a command code (the address compare replaced by the code test)
    "r_cmd_any_addr": [(f"{R14}/eeg_regs.sv", "            if (w_ok && addr == A_COMMAND) begin",
                        "            if (w_ok && is_cmd_code) begin")],
    # the interval flag of the overload restarted only at valid output times
    "t_ovl_outstb_valid": [(f"{R14}/eeg_digital_top.sv",
                            ".out_stb(cic_stb), .ovl_now(ovl_now),", ".out_stb(cic_stb & cic_valid), .ovl_now(ovl_now),")],
    # the OVL history advanced at valid output times only
    "t_ovlhist_valid": [(f"{R14}/eeg_digital_top.sv", "else if (cic_stb) ovl_hist <= {ovl_hist[0], ovl_iv};",
                         "else if (cic_stb && cic_valid) ovl_hist <= {ovl_hist[0], ovl_iv};")],
}
# a shared W1C decode of the two flag registers: a W1C write to DFLAG also clears ERR's bits of its data (and the reverse)
MUTANTS["r_err_w1c_also_dflag"] = [(f"{R14}/eeg_regs.sv",
    "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;",
    "err   <= (err & ~((we && w_ok && (addr == A_ERR || addr == A_DFLAG)) ? wdata : 8'h00)) | ev_err;")]
MUTANTS["r_dflag_w1c_also_err"] = [(f"{R14}/eeg_regs.sv",
    "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ?",
    "dflag <= (dflag & ~((we && w_ok && (addr == A_DFLAG || addr == A_ERR)) ?")]
