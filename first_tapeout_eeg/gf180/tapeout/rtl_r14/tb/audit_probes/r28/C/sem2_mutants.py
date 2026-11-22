R14 = "gf180/tapeout/rtl_r14"
MUTANTS = {
    # a write to ALERT_MASK also loads ALERT_MASK_D from its low bits (a mask decode shared one way)
    "r_mask_alias_d": [(f"{R14}/eeg_regs.sv", "A_ALERT_MASK:   r_mask <= wdata;",
                        "A_ALERT_MASK:   begin r_mask <= wdata; r_mask_d <= wdata[ALERT_MASK_D_ALERT_MASK_D_LSB +: ALERT_MASK_D_ALERT_MASK_D_W]; end")],
    # IF_CFG's decode copied from DEBUG's: bit 2 (reserved in IF_CFG) loads RAW_EN, a locked test register
    "r_ifcfg_raw": [(f"{R14}/eeg_regs.sv", "A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; end",
                     "A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; r_raw <= wdata[2]; end")],
}
