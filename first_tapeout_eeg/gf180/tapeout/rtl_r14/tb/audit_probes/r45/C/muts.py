# Audit 45, auditor C: candidate RTL errors (one per copy). (file under gf180/tapeout, old, new)
TOP = "rtl_r14/eeg_digital_top.sv"
REGS = "rtl_r14/eeg_regs.sv"
SPI = "rtl_r14/eeg_spi_slave.sv"
MUTS = {
    # the sequencer's refusal strobes registered on their way to the flag register (a designer registering a block's
    # outputs): STATE_ERR / CFG_ERR of a tick set one MCLK after e25, the state, AFE_RST and CMD_PENDING's clear
    "c1_seqflag_q": [
        (TOP, "    logic        seq_afe_rst, seq_flush, seq_store, seq_mark, seq_serr, seq_cerr;\n",
              "    logic        seq_afe_rst, seq_flush, seq_store, seq_mark, seq_serr, seq_cerr;\n"
              "    logic        seq_serr_q, seq_cerr_q;                   // (mutant) the refusal strobes, registered\n"),
        (TOP, ".seq_state_err(seq_serr), .seq_cfg_err(seq_cerr),",
              ".seq_state_err(seq_serr_q), .seq_cfg_err(seq_cerr_q),"),
        (TOP, "    assign AFE_RST = seq_afe_rst;\n",
              "    assign AFE_RST = seq_afe_rst;\n"
              "    always_ff @(posedge MCLK or negedge rst_n) begin\n"
              "        if (!rst_n) begin seq_serr_q <= 1'b0; seq_cerr_q <= 1'b0; end\n"
              "        else        begin seq_serr_q <= seq_serr; seq_cerr_q <= seq_cerr; end\n"
              "    end\n"),
    ],
    # the SPI's frame-error strobes registered on their way to the flag register: FRAME_ERR, CRC_ERR and the read
    # header's ADDR_ERR one MCLK later
    "c2_spiflag_q": [
        (TOP, "    logic        reg_addr_ok, reg_we, frame_err, crc_err, addr_err, cmd_valid, cmd_ack;\n",
              "    logic        reg_addr_ok, reg_we, frame_err, crc_err, addr_err, cmd_valid, cmd_ack;\n"
              "    logic        frame_err_q, crc_err_q, addr_err_q;      // (mutant) the SPI's error strobes, registered\n"),
        (TOP, ".frame_err_set(frame_err), .crc_err_set(crc_err), .addr_err_set(addr_err),",
              ".frame_err_set(frame_err_q), .crc_err_set(crc_err_q), .addr_err_set(addr_err_q),"),
        (TOP, "    assign AFE_RST = seq_afe_rst;\n",
              "    assign AFE_RST = seq_afe_rst;\n"
              "    always_ff @(posedge MCLK or negedge rst_n) begin\n"
              "        if (!rst_n) begin frame_err_q <= 1'b0; crc_err_q <= 1'b0; addr_err_q <= 1'b0; end\n"
              "        else        begin frame_err_q <= frame_err; crc_err_q <= crc_err; addr_err_q <= addr_err; end\n"
              "    end\n"),
    ],
    # DFLAG's set strobes registered on their way to the flag register: OVL (a hit in FILL / RUN) and OVERRUN (the
    # FIFO's dropped push) one MCLK later
    "c3_dflag_q": [
        (TOP, "    logic        fifo_nonempty, ovr_set, push_ok, smp_snap, smp_pop;\n",
              "    logic        fifo_nonempty, ovr_set, push_ok, smp_snap, smp_pop;\n"
              "    logic        ovl_set_q, ovr_set_q;                    // (mutant) DFLAG's set strobes, registered\n"),
        (TOP, "        .ovl_now(ovl_now), .ovr_set(ovr_set),\n"
              "        .ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),\n",
              "        .ovl_now(ovl_now), .ovr_set(ovr_set_q),\n"
              "        .ovl_set(ovl_set_q),\n"),
        (TOP, "    assign AFE_RST = seq_afe_rst;\n",
              "    assign AFE_RST = seq_afe_rst;\n"
              "    always_ff @(posedge MCLK or negedge rst_n) begin\n"
              "        if (!rst_n) begin ovl_set_q <= 1'b0; ovr_set_q <= 1'b0; end\n"
              "        else begin ovl_set_q <= ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN));\n"
              "                   ovr_set_q <= ovr_set; end\n"
              "    end\n"),
    ],
}
