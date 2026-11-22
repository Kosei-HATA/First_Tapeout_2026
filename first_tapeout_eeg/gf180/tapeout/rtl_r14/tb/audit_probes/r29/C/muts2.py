R14 = "gf180/tapeout/rtl_r14"
MUTANTS = {
    # DAC_CLK's flip-flop with the reset value 1 (a clock output idling high): high through RESET_N, a rising edge at
    # every reset assertion; the first frame after the release is normal
    "t_dacclk_rst1": [(f"{R14}/eeg_digital_top.sv", "if (!tm_rst_n) DAC_CLK <= 1'b0;", "if (!tm_rst_n) DAC_CLK <= 1'b1;")],
}
# OFF_M_H put in the test key's lock list (one case label in the wrong list): every write to OFF_M_H without the key is
# refused with ADDR_ERR, so M[9:8] cannot be set in operation (ranges 3 and 4 above M 255 unusable)
MUTANTS["r_offmh_locked"] = [
    (f"{R14}/eeg_regs.sv",
     "A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,",
     "A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_L, A_AFE_IBIAS,"),
    (f"{R14}/eeg_regs.sv",
     "A_TEST_MUX, A_TEST_CTRL, A_DEBUG: wr_locked = !unlocked;",
     "A_TEST_MUX, A_TEST_CTRL, A_DEBUG, A_OFF_M_H: wr_locked = !unlocked;")]
