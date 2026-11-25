# audit43 C: RTL mutants (one per copy)
MUTS = {
    # C1: the top empties the FIFO also at an APPLY or APPLY_NR applied in IDLE (spec 2.3: "IDLE と WARMUP の APPLY は
    # パルスなしで、FIFO を空にしない（STOP のあとに FIFO に残ったサンプルは、次の START まで読める）"); the sequencer's
    # own flush output is unchanged, so the sequencer trace replays it as the specification
    "c1_flush_idle_apply": [("eeg_digital_top.sv",
        ".clk(MCLK), .rst_n(rst_n), .flush(seq_flush), .push(seq_store),",
        ".clk(MCLK), .rst_n(rst_n), .flush(seq_flush | (apply && (seq_state == ST_IDLE))), .push(seq_store),")],
    # A: the clock generator's blanking length compared live (a counter up to blank_len) instead of latched at the pulse's
    # start (the eeg_clkgen header: "The length is latched when the pulse starts ... never shortens or stretches a pulse
    # in progress"); differs only when blank_len changes inside a pulse (a SOFT_RESET with the offset DAC on)
    "a_blank_live": [("eeg_clkgen.sv",
        """            if (out_edge_ahead && (blank_len != 4'd0)) begin
                chop_blank <= 1'b1;
                blank_rem  <= blank_len;
            end else if (chop_blank) begin
                if (blank_rem == 4'd0) begin
                    chop_blank <= 1'b0;
                end else begin
                    blank_rem <= blank_rem - 4'd1;
                end
            end""",
        """            if (out_edge_ahead && (blank_len != 4'd0)) begin
                chop_blank <= 1'b1;
                blank_rem  <= 4'd0;
            end else if (chop_blank) begin
                if (blank_rem == blank_len) begin
                    chop_blank <= 1'b0;
                end else begin
                    blank_rem <= blank_rem + 4'd1;
                end
            end""")],
    # B: OFF_M_H's active copy read one MCLK late (the class of m221 on another active copy)
    "b_acth_rd_q": [("eeg_regs.sv", "    logic [7:0] pcode;\n",
        "    logic [7:0] pcode;\n    logic [1:0] acth_rd_q;                   // OFF_M_H's active copy's read path, registered\n"
        "    always_ff @(posedge clk or negedge rst_n) if (!rst_n) acth_rd_q <= 2'b00; else acth_rd_q <= a_m[9:8];\n"),
        ("eeg_regs.sv", "A_OFF_M_H_ACT:    rdata = {6'd0, a_m[9:8]};", "A_OFF_M_H_ACT:    rdata = {6'd0, acth_rd_q};")],
    # J: the OVL history and the interval mark advance on the gated output strobe (out_s: not in SOFT_RESET's commit cycle)
    "j_ovl_hist_outs": [("eeg_digital_top.sv", "        else if (cic_stb) ovl_hist <= {ovl_hist[0], ovl_iv};",
                         "        else if (out_s)   ovl_hist <= {ovl_hist[0], ovl_iv};")],
}
# K: DFLAG.OVL gated by a list of the excluded states that forgets PULSE (SEQ-11: OVL only in FILL and RUN; an overload
# in the AFE reset pulse is expected). tb_top_r14 never has an extreme code while the detector holds in PULSE
MUTS["k_ovl_pulse"] = [("eeg_digital_top.sv",
    ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),",
    ".ovl_set(ovl_hit && (seq_state != ST_IDLE) && (seq_state != ST_WARMUP) && (seq_state != ST_RECOVER) &&\n"
    "                 (seq_state != ST_WAIT_E) && (seq_state != ST_ALIGN) && (seq_state != ST_PRE)),")]
