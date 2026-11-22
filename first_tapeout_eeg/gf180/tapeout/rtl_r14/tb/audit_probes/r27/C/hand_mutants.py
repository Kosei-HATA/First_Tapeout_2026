R14 = "gf180/tapeout/rtl_r14"
OLD = "gf180/tapeout/rtl"
MUTANTS = {
    # CHOP1 taken by a clock derived from the frame counter (cycle[4] rises at e16), not MCLK: a slow divider
    # clocked by a counter bit (RST-05 asks for the single clock MCLK)
    "hc_chop1_derived_clock": [
        (f"{OLD}/eeg_chop1.sv",
         "            if (cycle == 5'd15) begin     // this edge is e16\n                chop1 <= wave;\n            end\n",
         ""),
        (f"{OLD}/eeg_chop1.sv",
         "            chop1  <= 1'b1;\n        end else begin",
         "        end else begin"),
        (f"{OLD}/eeg_chop1.sv",
         "endmodule",
         "    always_ff @(posedge cycle[4] or negedge rst_n) begin   // (mutant) e16: cycle 15 -> 16 sets cycle[4]\n"
         "        if (!rst_n) chop1 <= 1'b1;\n        else        chop1 <= wave;\n    end\n\nendmodule")],
    # SEQ counted on the falling edge of the CIC's output strobe (a ripple-clocked counter), not on MCLK
    "hc_seq_cnt_strobe_clock": [
        (f"{R14}/eeg_digital_top.sv",
         "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n)    seq_cnt <= 16'd0;\n        else if (cic_stb) seq_cnt <= seq_cnt + 16'd1;\n    end",
         "    always_ff @(negedge cic_stb or negedge tm_rst_n) begin   // (mutant) clocked by the strobe's fall (e9)\n        if (!tm_rst_n)    seq_cnt <= 16'd0;\n        else              seq_cnt <= seq_cnt + 16'd1;\n    end")],
    # the OVL history clocked by the strobe's fall as well
    "hc_ovl_hist_strobe_clock": [
        (f"{R14}/eeg_digital_top.sv",
         "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n)    ovl_hist <= 2'b00;\n        else if (cic_stb) ovl_hist <= {ovl_hist[0], ovl_iv};\n    end",
         "    always_ff @(negedge cic_stb or negedge tm_rst_n) begin   // (mutant)\n        if (!tm_rst_n)    ovl_hist <= 2'b00;\n        else              ovl_hist <= {ovl_hist[0], ovl_iv};\n    end")],
}
