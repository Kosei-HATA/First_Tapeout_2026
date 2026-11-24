# audit41 C: plausible RTL errors, one per copy (file relative to rtl_r14/ or rtl/, text occurring once, replacement)
MUTS = {
    # a register read's data byte from a registered copy of the read mux (one MCLK late): a designer registering the
    # combinational read path for timing; the header STATUS, the empty word and the stored samples have specified and
    # swept copy instants (spec 3.2, 3.4; AF, AK, AD), a register read's data byte not
    "rd_data_late": [
        ("eeg_spi_slave.sv", "    logic        chk_addr;\n",
         "    logic        chk_addr;\n    logic [7:0]  rdata_q;                         // (mutant) the read mux, registered\n"
         "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) rdata_q <= 8'h00; else rdata_q <= reg_rdata;\n"),
        ("eeg_spi_slave.sv", "S_RREG:  tx_next = reg_rdata;", "S_RREG:  tx_next = rdata_q;"),
    ],
}
# T_ELEC taken with the configuration (START, APPLY, APPLY_NR), as m198 takes T_REC and T_RST (spec 4.2: every timer
# is taken at the start of its wait; phase AG writes only T_REC in WARMUP and T_RST in PRE)
MUTS["te_latched"] = [
    ("eeg_regs.sv", "    logic [7:0] pcode;\n",
     "    logic [7:0] pcode;\n    // (mutant) the electrode wait taken with the configuration (START, APPLY, APPLY_NR)\n"
     "    logic [7:0] q_te;\n    always_ff @(posedge clk or negedge rst_n) begin\n"
     "        if (!rst_n) q_te <= T_ELEC_T_ELEC_RST;\n        else if (apply) q_te <= r_te;\n    end\n"),
    ("eeg_regs.sv", "    assign t_elec     = r_te;", "    assign t_elec     = q_te;"),
]
