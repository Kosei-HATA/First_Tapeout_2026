# Audit 35, auditor C: plausible RTL errors, one per copy (file under rtl_r14 or rtl, old text (exactly once), new)
MUTANTS = {
    # the empty word's status byte registered one MCLK before the copy (the pipelining of m193, for the empty word):
    # OVERRUN, OVL (OVL_NOW) and ERR (ALERT) as in the cycle before the header's copy (spec 3.2 / 3.4: at the copy)
    "empty_q": [("eeg_digital_top.sv",
                 "        .empty_status(empty_status), .rd_word(smp_word),",
                 "        .empty_status(empty_status_q), .rd_word(smp_word),"),
                ("eeg_digital_top.sv",
                 "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (",
                 "    logic [7:0] empty_status_q;\n"
                 "    always_ff @(posedge MCLK or negedge rst_n) if (!rst_n) empty_status_q <= 8'h00; else empty_status_q <= empty_status;\n"
                 "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (")],
    # DFLAG (OVERRUN, OVL) cleared when a configuration is applied (START, APPLY, APPLY_NR): "a new setting starts with
    # clean data flags" (DFLAG is W1C only: FLG-03, spec 2.2)
    "dflag_apply": [("eeg_regs.sv",
                     "            dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n"
                     "                                                                : 2'b00)) | {ovl_set, ovr_set};",
                     "            dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n"
                     "                                                                : {2{apply}})) | {ovl_set, ovr_set};")],
}
# checker experiments (no RTL change): a bench instantiation the DAC_LOAD_CYCLE check misses
MUTANTS["param_space"] = [("../rtl/tb/tb_chop1.sv", "    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) u_clkgen (",
                           "    eeg_clkgen #(.DAC_LOAD_CYCLE (7)) u_clkgen (")]
MUTANTS["param_pos"] = [("../rtl/tb/tb_chop1.sv", "    eeg_clkgen #(.DAC_LOAD_CYCLE(2)) u_clkgen (",
                         "    eeg_clkgen #(7) u_clkgen (")]
# RESET_FLAG (ERR bit 0) cleared when a configuration is applied (START, APPLY, APPLY_NR): "the host has set the chip
# up, the power-on flag is acknowledged" (ERR is W1C only; rule (c) and step 4 rely on RESET_FLAG to see a reset)
MUTANTS["rflag_apply"] = [("eeg_regs.sv",
    "            err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;",
    "            err   <= (err & ~(((we && w_ok && addr == A_ERR) ? wdata : 8'h00) | {7'd0, apply})) | ev_err;")]
# STATUS registered one MCLK before the header's copy (spec 3.2: "値は CS_N の立ち下がりの時点で写す"; the pipelining of
# m193 for the header): the SPI's status port from a register of status_byte (the STATUS register read stays live)
MUTANTS["status_hdr_q"] = [("eeg_digital_top.sv",
    "        .status_byte(status_byte), .reg_addr(reg_addr), .reg_rdata(reg_rdata), .reg_addr_ok(reg_addr_ok),",
    "        .status_byte(status_hdr_q), .reg_addr(reg_addr), .reg_rdata(reg_rdata), .reg_addr_ok(reg_addr_ok),"),
    ("eeg_digital_top.sv",
    "    eeg_spi_slave u_spi (",
    "    logic [7:0] status_hdr_q;\n"
    "    always_ff @(posedge MCLK or negedge rst_n) if (!rst_n) status_hdr_q <= 8'h81; else status_hdr_q <= status_byte;\n"
    "    eeg_spi_slave u_spi (")]
