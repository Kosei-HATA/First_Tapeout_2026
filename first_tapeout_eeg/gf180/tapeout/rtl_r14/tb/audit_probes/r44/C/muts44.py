# audit 44, auditor C: RTL mutants (paths relative to gf180/tapeout/rtl_r14)
MUTS = {
    # DBG_SEL 3 shows the clock generator's blanking instead of the CHOP_BLANK pad signal (eeg_raw's table: RAW_CLK =
    # CHOP_BLANK); differs only while ADC_ZERO holds CHOP_BLANK high
    "c44_dbg3_genblank": dict(desc="DBG_SEL 3: RAW_CLK from the generator's blanking, not the CHOP_BLANK pad",
                              edits=[("eeg_digital_top.sv", ".dbg_clk({CHOP_BLANK, CHOP, CMP_STROBE})",
                                      ".dbg_clk({gen_blank, CHOP, CMP_STROBE})")]),
    # the pop request one MCLK later (a retiming register on smp_pop)
    "c44_pop_late": dict(desc="the FIFO's pop request registered once more (1 MCLK later)",
                         edits=[("eeg_digital_top.sv", ".snap(smp_snap), .pop(smp_pop),", ".snap(smp_snap), .pop(smp_pop_q),"),
                                ("eeg_digital_top.sv", "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (",
                                 "    logic smp_pop_q;\n    always_ff @(posedge MCLK or negedge rst_n) if (!rst_n) smp_pop_q <= 1'b0; else smp_pop_q <= smp_pop;\n    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (")]),
}
# the record's own mutants m223 and m224 (tb/mutate_top_r14.py), to confirm the detection lines quoted in audit 44.4
MUTS["m224"] = dict(desc="record m224: DFLAG.OVL gate as a list of excluded states without PULSE",
                    edits=[("eeg_digital_top.sv", ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),",
                            ".ovl_set(ovl_hit && (seq_state != ST_IDLE) && (seq_state != ST_WARMUP) && (seq_state != ST_RECOVER) &&\n                 (seq_state != ST_WAIT_E) && (seq_state != ST_ALIGN) && (seq_state != ST_PRE)),")])
