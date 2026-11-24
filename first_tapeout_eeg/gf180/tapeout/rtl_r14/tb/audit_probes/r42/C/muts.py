# audit42 C: RTL mutants (one plausible designer error each), applied by mkmut.py to a full copy of 810a0bc4
R14 = "gf180/tapeout/rtl_r14/"
RTL = "gf180/tapeout/rtl/"
MUTS = {
    # A: a read of STATUS (0x03) returns the header's copy of the same frame (taken at the CS_N fall), so that the
    #    header and the register read agree; spec 3.2: every data byte is the register's value in its load cycle
    "st_hdrcopy": [
        (R14 + "eeg_spi_slave.sv", "logic        chk_addr;",
         "logic        chk_addr;\n    logic [7:0]  st_copy;                         // (mutant) the header's STATUS, also a read of 0x03"),
        (R14 + "eeg_spi_slave.sv", "shadow    <= 48'h0;", "shadow    <= 48'h0;\n            st_copy   <= 8'h00;"),
        (R14 + "eeg_spi_slave.sv", "tx_sh   <= status_byte;                  // STATUS during the header byte",
         "tx_sh   <= status_byte;                  // STATUS during the header byte\n                st_copy <= status_byte;"),
        (R14 + "eeg_spi_slave.sv", "S_RREG:  tx_next = reg_rdata;",
         "S_RREG:  tx_next = (reg_addr == A_STATUS) ? st_copy : reg_rdata;"),
    ],
    # B: the ERR read path registered (one MCLK late), e.g. to cut the flag logic -> MISO path
    "err_rd_q": [
        (R14 + "eeg_regs.sv", "logic [7:0] pcode;",
         "logic [7:0] pcode;\n    logic [7:0] err_rd_q;                    // (mutant) ERR's read path, registered\n"
         "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) err_rd_q <= 8'h01; else err_rd_q <= err;"),
        (R14 + "eeg_regs.sv", "A_ERR:            rdata = err;", "A_ERR:            rdata = err_rd_q;"),
    ],
}
# C: the sequencer's electrode wait taken with the configuration (START, APPLY, APPLY_NR), as m198 takes T_REC and T_RST
#    (spec 4.2: every timer is taken at the start of its wait; phase AG writes T_REC in WARMUP and T_RST in PRE only);
#    CHANGED's count keeps the register (round 41's te_latched, which also changed it, was caught by D3/D4 through it)
MUTS["te_seq_latched"] = [
    (R14 + "eeg_digital_top.sv", "    assign AFE_RST = seq_afe_rst;",
     "    assign AFE_RST = seq_afe_rst;\n"
     "    // (mutant) the electrode wait as applied with the configuration\n"
     "    always_ff @(posedge MCLK or negedge rst_n) begin\n"
     "        if (!rst_n)     t_elec_q <= T_ELEC_T_ELEC_RST;\n"
     "        else if (apply) t_elec_q <= t_elec;\n"
     "    end"),
    (R14 + "eeg_digital_top.sv", "    logic tick_s, out_s;", "    logic tick_s, out_s;\n    logic [7:0] t_elec_q;"),
    (R14 + "eeg_digital_top.sv", ".t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec)", ".t_warm(t_warm), .t_elec(t_elec_q), .t_rec(t_rec)"),
]
