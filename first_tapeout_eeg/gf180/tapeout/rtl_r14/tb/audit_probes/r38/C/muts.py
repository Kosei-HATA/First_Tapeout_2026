# audit38 C: RTL mutants (one designer error per copy). Paths relative to gf180/tapeout.
R = "rtl_r14/eeg_regs.sv"
T = "rtl_r14/eeg_digital_top.sv"
S = "rtl_r14/eeg_spi_slave.sv"
Q = "rtl_r14/eeg_seq.sv"
F = "rtl_r14/eeg_fifo.sv"
C = "rtl_r14/eeg_clkgen.sv"
MUTS = {}
# M1: STATUS's CMD_PENDING reads 0 in the cycle the tick takes the command ("pending" = still waiting after this
# cycle). Spec 3.2: STATUS is the value of the copy's cycle; pend is 1 in the acknowledge cycle.
MUTS["m1_pend_ack"] = [(R,
    "        status_byte[STATUS_CMD_PENDING_LSB] = pend;",
    "        status_byte[STATUS_CMD_PENDING_LSB] = pend && !cmd_ack;     // not pending once the tick takes it")]
# M15: the sample's (and the empty word's) OVERRUN from DFLAG.OVERRUN's next value ("the flag as this cycle's update
# leaves it": a W1C committed in the store's own cycle already counts). Spec 3.4 / 3.2: the value of the store's
# (copy's) cycle; flags that change at the writing edge are not included. AD sweeps ERR only.
MUTS["m15_overrun_next"] = [(R,
    "    assign dflag_overrun = dflag[0];",
    "    assign dflag_overrun = (dflag[0] & ~(we && w_ok && addr == A_DFLAG && wdata[DFLAG_OVERRUN_LSB])) | ovr_set;")]
