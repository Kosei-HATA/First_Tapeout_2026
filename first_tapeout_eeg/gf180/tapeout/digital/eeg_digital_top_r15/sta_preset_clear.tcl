# Sourced by LibreLane's STA corner script (STA_EXTRA_CORNER_TCL_FILE) after the design, the SDC and the parasitics
# are read and before any report: every STA of the r14 macro (pre-, mid- and post-PnR, all 9 corners) times the
# flip-flops' preset / clear arcs (requirement VER-05; audit round 5 of 11/20). SOFT_RESET clears the control
# domain's flip-flops through their asynchronous clear (RN), and their Q reaches the timing domain (chopper rate,
# BLANK_LEN, CHOP1 rate, the CIC clear, RAW) and eeg_adc_dig (DWA_EN) only through the RN -> Q arc, which OpenSTA
# leaves untimed by default (sta_preset_clear_arcs_enabled 0). Recovery / removal checks stay on (OpenSTA default).
set sta_preset_clear_arcs_enabled 1
puts "\[INFO\] VER-05: sta_preset_clear_arcs_enabled = $sta_preset_clear_arcs_enabled,\
 sta_recovery_removal_checks_enabled = $sta_recovery_removal_checks_enabled"
