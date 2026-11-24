# audit40 C: RTL copies (one plausible error each). (file relative to gf180/tapeout, old text, new text)
MUTS = {
    # the first sample after a (re)start (FILL's store) taken without the sticky OVERRUN ("no drop in this run yet")
    "fill_ovr": [("rtl_r14/eeg_digital_top.sv",
                  "smp_status[SMP_OVERRUN_LSB] = dflag_overrun;",
                  "smp_status[SMP_OVERRUN_LSB] = dflag_overrun & (seq_state != ST_FILL);")],
    # the same for ERR (ALERT): FILL's store without ERR
    "fill_err": [("rtl_r14/eeg_digital_top.sv",
                  "smp_status[SMP_ERR_LSB]     = alert;",
                  "smp_status[SMP_ERR_LSB]     = alert & (seq_state != ST_FILL);")],
    # the samples' (and the empty word's) ERR from a "data" alert that leaves RESET_FLAG out (a reset is no error of
    # the data); STATUS's ALERT keeps every flag (as mutant m161 does for DFLAG)
    "smp_err_norf": [
        ("rtl_r14/eeg_regs.sv", "    assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);\n",
         "    assign alert       = |(err & r_mask & ~(8'h01 << ERR_RESET_FLAG_LSB)) || |(dflag_byte & mask_d_byte);\n"),
        ("rtl_r14/eeg_regs.sv", "        status_byte[STATUS_ALERT_LSB]       = alert;\n",
         "        status_byte[STATUS_ALERT_LSB]       = |(err & r_mask) || |(dflag_byte & mask_d_byte);\n"),
    ],
    # the samples' (and the empty word's) ERR from ERR under ALERT_MASK and any DFLAG bit, ALERT_MASK_D left out (a
    # data flag is always worth a sample's ERR); STATUS's ALERT keeps both masks
    "smp_err_nomaskd": [
        ("rtl_r14/eeg_regs.sv", "    assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);\n",
         "    assign alert       = |(err & r_mask) || |dflag_byte;\n"),
        ("rtl_r14/eeg_regs.sv", "        status_byte[STATUS_ALERT_LSB]       = alert;\n",
         "        status_byte[STATUS_ALERT_LSB]       = |(err & r_mask) || |(dflag_byte & mask_d_byte);\n"),
    ],
}
