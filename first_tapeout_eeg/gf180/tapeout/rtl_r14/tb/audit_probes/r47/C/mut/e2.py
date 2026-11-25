# top: DBG_SEL 3's RAW_CLK wired from the clock generator's blanking (gen_blank) instead of the CHOP_BLANK pad
# (which ADC_ZERO holds high)
EDITS = [("eeg_digital_top.sv", ".dbg_clk({CHOP_BLANK, CHOP, CMP_STROBE})", ".dbg_clk({gen_blank, CHOP, CMP_STROBE})")]
