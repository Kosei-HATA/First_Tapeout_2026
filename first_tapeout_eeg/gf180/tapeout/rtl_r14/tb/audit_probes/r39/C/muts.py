# audit39 C: RTL mutants (one designer error per copy). Paths relative to gf180/tapeout.
R = "rtl_r14/eeg_regs.sv"
T = "rtl_r14/eeg_digital_top.sv"
S = "rtl_r14/eeg_spi_slave.sv"
Q = "rtl_r14/eeg_seq.sv"
F = "rtl_r14/eeg_fifo.sv"
MUTS = {}
# MR1: STATUS.READY from a register (the state decode registered for a glitch-free status bit): one MCLK late.
# Spec 3.2: the header STATUS is the value of the copy's cycle, a flag changed at that cycle's starting edge included.
MUTS["mr1_ready_q"] = [
    (R, "    logic [7:0] pcode;\n",
        "    logic [7:0] pcode;\n    logic       ready_q;                     // READY, registered (glitch-free decode)\n"
        "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) ready_q <= 1'b0; else ready_q <= (state == ST_RUN);\n"),
    (R, "        status_byte[STATUS_READY_LSB]       = (state == ST_RUN);",
        "        status_byte[STATUS_READY_LSB]       = ready_q;")]
# MR5: STATUS.AFE_RST from a register (status inputs registered): one MCLK late.
MUTS["mr5_afersts_q"] = [
    (R, "    logic [7:0] pcode;\n",
        "    logic [7:0] pcode;\n    logic       afe_rst_q;                   // AFE_RST for STATUS, registered\n"
        "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) afe_rst_q <= 1'b1; else afe_rst_q <= afe_rst;\n"),
    (R, "        status_byte[STATUS_AFE_RST_LSB]     = afe_rst;",
        "        status_byte[STATUS_AFE_RST_LSB]     = afe_rst_q;")]
# MR6: the empty word's OVL from a registered OVL_NOW (one MCLK late). Spec 3.4: OVL = OVL_NOW of the copy's cycle.
MUTS["mr6_empty_ovl_q"] = [
    (T, "    logic [7:0]  smp_status, empty_status;       // built below from the generated bit positions (audit round 8)\n",
        "    logic [7:0]  smp_status, empty_status;       // built below from the generated bit positions (audit round 8)\n"
        "    logic        ovl_now_q;                      // OVL_NOW for the empty word, registered\n"
        "    always_ff @(posedge MCLK or negedge tm_rst_n) if (!tm_rst_n) ovl_now_q <= 1'b0; else ovl_now_q <= ovl_now;\n"),
    (T, "        empty_status[SMP_OVL_LSB]     = ovl_now;",
        "        empty_status[SMP_OVL_LSB]     = ovl_now_q;")]
# MR3: STATUS.OVL_NOW from a register (one MCLK late).
MUTS["mr3_ovlnow_q"] = [
    (R, "    logic [7:0] pcode;\n",
        "    logic [7:0] pcode;\n    logic       ovl_now_q;                   // OVL_NOW for STATUS, registered\n"
        "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) ovl_now_q <= 1'b0; else ovl_now_q <= ovl_now;\n"),
    (R, "        status_byte[STATUS_OVL_NOW_LSB]     = ovl_now;",
        "        status_byte[STATUS_OVL_NOW_LSB]     = ovl_now_q;")]
# MR4: STATUS.DATA from a register (one MCLK late).
MUTS["mr4_data_q"] = [
    (R, "    logic [7:0] pcode;\n",
        "    logic [7:0] pcode;\n    logic       data_q;                      // DATA for STATUS, registered\n"
        "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) data_q <= 1'b0; else data_q <= fifo_nonempty;\n"),
    (R, "        status_byte[STATUS_DATA_LSB]        = fifo_nonempty;",
        "        status_byte[STATUS_DATA_LSB]        = data_q;")]
# MR7: the empty word's OVERRUN from a registered DFLAG.OVERRUN (one MCLK late). Spec 3.4: OVERRUN = DFLAG.OVERRUN of
# the copy's cycle.
MUTS["mr7_empty_ovr_q"] = [
    (T, "    logic [7:0]  smp_status, empty_status;       // built below from the generated bit positions (audit round 8)\n",
        "    logic [7:0]  smp_status, empty_status;       // built below from the generated bit positions (audit round 8)\n"
        "    logic        dflag_ovr_q;                    // DFLAG.OVERRUN for the empty word, registered\n"
        "    always_ff @(posedge MCLK or negedge rst_n) if (!rst_n) dflag_ovr_q <= 1'b0; else dflag_ovr_q <= dflag_overrun;\n"),
    (T, "        empty_status[SMP_OVERRUN_LSB] = dflag_overrun;",
        "        empty_status[SMP_OVERRUN_LSB] = dflag_ovr_q;")]
MUTS['m206_list'] = [('rtl_r14/eeg_regs.sv', '        status_byte[STATUS_CMD_PENDING_LSB] = pend;', '        status_byte[STATUS_CMD_PENDING_LSB] = pend && !cmd_ack;     // not pending once the tick takes it')]
MUTS['m207_list'] = [('rtl_r14/eeg_regs.sv', '    assign dflag_overrun = dflag[0];', '    assign dflag_overrun = (dflag[0] & ~(we && w_ok && addr == A_DFLAG && wdata[DFLAG_OVERRUN_LSB])) | ovr_set;')]
