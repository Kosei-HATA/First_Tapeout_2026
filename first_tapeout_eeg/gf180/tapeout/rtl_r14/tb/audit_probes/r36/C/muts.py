# Audit 36, auditor C: plausible RTL errors, one per copy (file relative to rtl_r14, old text (exactly once), new)
MUTANTS = {}

# T_REC and T_RST taken with the configuration at the command (START / APPLY / APPLY_NR apply), like the analog
# settings, instead of at the start of their waits. Spec 4.2: "値はタイマの開始時に取り込む"; SPI-12: "START と APPLY の
# T_RST、T_REC、T_ELEC はそれぞれの待ちの始まりに読むので、ガードの終わったあとの書き込みは進行中の START や APPLY に効く"
MUTANTS["timers_at_apply"] = [
    ("eeg_regs.sv", "    logic [7:0] pcode;\n",
     "    logic [7:0] pcode;\n"
     "    // the AFE pulse's timers taken with the configuration (START, APPLY, APPLY_NR), as the analog settings\n"
     "    logic [7:0] q_trec, q_trst;\n"
     "    always_ff @(posedge clk or negedge rst_n) begin\n"
     "        if (!rst_n) begin q_trec <= T_REC_T_REC_RST; q_trst <= T_RST_T_RST_RST; end\n"
     "        else if (apply) begin q_trec <= r_trec; q_trst <= r_trst; end\n"
     "    end\n"),
    ("eeg_regs.sv", "    assign t_rec      = r_trec;", "    assign t_rec      = q_trec;"),
    ("eeg_regs.sv", "    assign t_rst      = r_trst;", "    assign t_rst      = q_trst;"),
]

# The read header's ADDR_ERR raised with the frame's other errors at CS_N rising (a designer "flagging every SPI error at
# the end of the frame") instead of after the header byte (table 5.2-2: HDR / BYTE with an undefined read address ->
# ADDR_ERR; spec 3.2). Visible only to a read of ERR or STATUS later in the same CRC-off burst.
MUTANTS["aerr_at_end"] = [
    ("eeg_spi_slave.sv", "    logic        chk_addr;\n", "    logic        chk_addr;\n    logic        hdr_bad;\n"),
    ("eeg_spi_slave.sv", "            reg_addr  <= 7'd0;\n            chk_addr  <= 1'b0;\n",
     "            reg_addr  <= 7'd0;\n            chk_addr  <= 1'b0;\n            hdr_bad   <= 1'b0;\n"),
    ("eeg_spi_slave.sv", "            addr_err  <= chk_addr && !reg_addr_ok;       // the read header's address, one cycle later\n",
     "            addr_err  <= 1'b0;\n            if (chk_addr && !reg_addr_ok) hdr_bad <= 1'b1;   // flagged at CS_N rising\n"),
    ("eeg_spi_slave.sv", "                st    <= S_IDLE;\n                tx_sh <= 8'h00;\n",
     "                st    <= S_IDLE;\n                tx_sh <= 8'h00;\n                if (hdr_bad) addr_err <= 1'b1;\n                hdr_bad <= 1'b0;\n"),
]

# DFLAG (OVERRUN, OVL) cleared when a START is taken ("a new acquisition starts with clean data flags"; the FIFO is
# emptied by it). REG-02 / FLG-02: only DFLAG's W1C clears it; REG-02 says phase AE confirms that START keeps ERR and
# DFLAG, but AE's START comes before it sets DFLAG (m195 clears on every apply and fails at AE's APPLY in RUN)
MUTANTS["dflag_at_start"] = [
    ("eeg_regs.sv", "                                                                : 2'b00)) | {ovl_set, ovr_set};",
     "                                                                : {2{apply && (pcode == CMD_START)}})) | {ovl_set, ovr_set};"),
]

# APPLY_NR taken as "the offset-DAC step": it copies only M, SIGN and RANGE (and the DAC pins) to the active side; the
# other shadows only with START and APPLY. Equivalent wherever nr_ok is required (the AFE running), different for an
# APPLY_NR in IDLE or WARMUP, which the table and REG-08 make a full apply without a pulse ("反映していない試験のシャドウ
# （TEST_MUX、TEST_CTRL）は次の START、APPLY、IDLE／WARMUP の APPLY_NR で反映され")
MUTANTS["nr_dac_only"] = [
    ("eeg_regs.sv",
     "                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;\n"
     "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;\n"
     "                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;\n"
     "                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;\n",
     "                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;\n"
     "                if (pcode != CMD_APPLY_NR) begin       // APPLY_NR: the offset-DAC step alone\n"
     "                a_ibias <= s_ibias;\n"
     "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;\n"
     "                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;\n"
     "                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;\n"
     "                end\n"),
]
