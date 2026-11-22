# Audit 34, auditor C: plausible RTL errors, one per copy (file under rtl_r14 or rtl, old text (exactly once), new)
MUTANTS = {
    # SPI-08: an ADDR_ERR for every undefined address a CRC-off burst passes (the spec flags the header only)
    "aerr_burst": [("eeg_spi_slave.sv",
                    "                                else        reg_addr <= reg_addr + 7'd1;",
                    "                                else        begin reg_addr <= reg_addr + 7'd1; chk_addr <= 1'b1; end")],
    # the guard released by the tick's apply instead of its acknowledge (a write in the ack cycle of a refused or
    # non-applying command gets STATE_ERR)
    "guard_apply": [("eeg_regs.sv",
                     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin",
                     "end else if (pend && !apply && GUARDED_ADDRS[addr]) begin")],
    # the sample's status byte registered one MCLK before the store (a pipelining choice): ERR (ALERT), OVERRUN, OVL,
    # CHANGED as in the cycle before the store
    "status_q": [("eeg_digital_top.sv",
                  "        .status_in(smp_status),",
                  "        .status_in(smp_status_q),"),
                 ("eeg_digital_top.sv",
                  "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (",
                  "    logic [7:0] smp_status_q;\n"
                  "    always_ff @(posedge MCLK or negedge rst_n) if (!rst_n) smp_status_q <= 8'h00; else smp_status_q <= smp_status;\n"
                  "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (")],
}
# the record's m190 (audit 34.4: tb_top_r14 alone fails it with 9 errors, at 545 ms in V and in AB): run top only
MUTANTS["m190"] = [("eeg_cic3.sv", "                if (arm) begin\n", "                if (arm && nstb >= NSKIP_P) begin\n")]
MUTANTS["m190b"] = MUTANTS["m190"]
