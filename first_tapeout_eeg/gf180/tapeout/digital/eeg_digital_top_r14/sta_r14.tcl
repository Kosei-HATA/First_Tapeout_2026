# OpenSTA of the r14 macro for one corner, outside LibreLane (run_sta_r14.sh): the final netlist and SPEF of a run,
# eeg_digital_top_r14.sdc, with the flip-flops' preset / clear arcs on (PRESET 1, VER-05) or off (PRESET 0, OpenSTA's
# default and the r13 macro's signoff). Reports: worst setup / hold (recovery / removal included), the design rules,
# and the SOFT_RESET paths alone (through the clear / preset pins of the flip-flops rst_n drives).
# Environment: LIB NL SPEF SDC OUT CORNER PRESET, and the SDC's variables (set here as LibreLane resolved them).
foreach {k v} {CLOCK_PERIOD 30.5 IO_DELAY_CONSTRAINT 20 MAX_FANOUT_CONSTRAINT 10 MAX_TRANSITION_CONSTRAINT 3
               MAX_CAPACITANCE_CONSTRAINT 0.2 OUTPUT_CAP_LOAD 72.91 CLOCK_UNCERTAINTY_CONSTRAINT 0.25
               CLOCK_TRANSITION_CONSTRAINT 0.15 TIME_DERATING_CONSTRAINT 5
               SYNTH_DRIVING_CELL gf180mcu_fd_sc_mcu9t5v0__inv_1/ZN SYNTH_CLK_DRIVING_CELL gf180mcu_fd_sc_mcu9t5v0__inv_4/ZN} {
    set ::env($k) $v
}
set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um
read_liberty $::env(LIB)
read_verilog $::env(NL)
link_design eeg_digital_top
read_spef $::env(SPEF)
read_sdc $::env(SDC)
# after the SDC, which turns the arcs on itself (eeg_digital_top_r14.sdc)
set sta_preset_clear_arcs_enabled $::env(PRESET)
set out $::env(OUT)
set c $::env(CORNER)
report_checks -path_delay max -group_path_count 5 -format full_clock_expanded -fields {slew cap input_pins} -digits 3 > $out/setup.rpt
report_checks -path_delay min -group_path_count 5 -format full_clock_expanded -fields {slew cap input_pins} -digits 3 > $out/hold.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > $out/drv.rpt
set f [open $out/summary.txt w]
puts $f [format "%s preset_clear %d setup %.3f hold %.3f tns %.3f slew_vio %d cap_vio %d fanout_vio %d soft_ffs %d" $c \
    $sta_preset_clear_arcs_enabled [sta::worst_slack -max] [sta::worst_slack -min] [sta::total_negative_slack -max] \
    [sta::max_slew_violation_count] [sta::max_capacitance_violation_count] [sta::max_fanout_violation_count] \
    [llength $eeg_soft_ffs]]
# the SOFT_RESET paths: through the clear / preset arcs of the flip-flops rst_n drives, its assertion (the pins fall);
# only with PRESET 1 do they exist
if {$sta_preset_clear_arcs_enabled} {
    report_checks -fall_through $eeg_soft_pins -path_delay max -group_path_count 20 -endpoint_path_count 1 \
        -format full_clock_expanded -fields {slew cap input_pins} -digits 3 > $out/soft_setup.rpt
    report_checks -fall_through $eeg_soft_pins -path_delay min -group_path_count 5 -endpoint_path_count 1 \
        -format full_clock_expanded -digits 3 > $out/soft_hold.rpt
    report_checks -fall_through $eeg_soft_pins -path_delay max -group_path_count 100000 -endpoint_path_count 1 \
        -format end > $out/soft_ends.rpt
}
close $f
exit
