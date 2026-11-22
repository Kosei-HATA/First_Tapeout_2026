R14 = "gf180/tapeout/rtl_r14"
OLD = "gf180/tapeout/rtl"
MUTANTS = {
    # BLANK's lower bound checked on the whole byte, like the timers below it (a full-byte field): a BLANK_LEN of 0 with
    # any reserved bit set (0x10, 0x20, ... 0xF0) is accepted and stored, so the chip runs without blanking (REG-06)
    "r_blank_byte": [(f"{R14}/eeg_regs.sv",
                      "A_BLANK:     wr_range_bad = (wdata[3:0] < BLANK_BLANK_LEN_MIN);",
                      "A_BLANK:     wr_range_bad = (wdata < {4'd0, BLANK_BLANK_LEN_MIN});")],
    # the overload detector's count one bit too narrow (the window holds up to 32 extreme codes)
    "o_cnt5": [(f"{R14}/eeg_ovl.sv", "logic [5:0]            cnt, cnt_nxt;", "logic [4:0]            cnt, cnt_nxt;"),
               (f"{R14}/eeg_ovl.sv", "assign cnt_nxt = cnt + {5'd0, ext} - {5'd0, win[OVL_WINDOW-1]};",
                "assign cnt_nxt = cnt + {4'd0, ext} - {4'd0, win[OVL_WINDOW-1]};"),
               (f"{R14}/eeg_ovl.sv", "assign ovl_now = (cnt >= OVL_THRESHOLD);", "assign ovl_now = ({1'b0, cnt} >= OVL_THRESHOLD);"),
               (f"{R14}/eeg_ovl.sv", "assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);",
                "assign ovl_hit = en && ext && ({1'b0, cnt_nxt} >= OVL_THRESHOLD);")],
}
