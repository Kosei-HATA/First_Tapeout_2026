R14 = "gf180/tapeout/rtl_r14"
MUTANTS = {
    "r_blank_byte": [(f"{R14}/eeg_regs.sv",
                      "A_BLANK:     wr_range_bad = (wdata[3:0] < BLANK_BLANK_LEN_MIN);",
                      "A_BLANK:     wr_range_bad = (wdata < {4'd0, BLANK_BLANK_LEN_MIN});")],
}
