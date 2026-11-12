set ::env(CLOCK_PERIOD) 30.517578125
set ::env(IO_DELAY_CONSTRAINT) 20
set ::env(MAX_FANOUT_CONSTRAINT) 10
set ::env(MAX_TRANSITION_CONSTRAINT) 1.5
set ::env(MAX_CAPACITANCE_CONSTRAINT) 0.5
set ::env(OUTPUT_CAP_LOAD) 20
set ::env(CLOCK_UNCERTAINTY_CONSTRAINT) 0.25
set ::env(CLOCK_TRANSITION_CONSTRAINT) 0.15
set ::env(TIME_DERATING_CONSTRAINT) 5
set ::env(SYNTH_DRIVING_CELL) gf180mcu_fd_sc_mcu7t5v0__buf_4/Z
set ::env(SYNTH_CLK_DRIVING_CELL) gf180mcu_fd_sc_mcu7t5v0__buf_4/Z
read_liberty /foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
read_verilog /work/gf180/tapeout/layout/gds/eeg_adc_dig.nl.v
link_design eeg_adc_dig
read_sdc /work/gf180/tapeout/digital/eeg_adc_dig/eeg_adc_dig.sdc
report_units
check_setup -verbose
report_checks -path_delay max -group_path_count 10 -format full_clock_expanded -fields {slew cap fanout input_pins} -digits 6 > /work/Test-2-4/manufacturing_preflight/digital_timing/eeg_adc_dig/tt_025C_3v30/setup.rpt
report_checks -path_delay min -group_path_count 10 -format full_clock_expanded -fields {slew cap fanout input_pins} -digits 6 > /work/Test-2-4/manufacturing_preflight/digital_timing/eeg_adc_dig/tt_025C_3v30/hold.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > /work/Test-2-4/manufacturing_preflight/digital_timing/eeg_adc_dig/tt_025C_3v30/design_rule.rpt
report_checks -unconstrained -group_path_count 10 > /work/Test-2-4/manufacturing_preflight/digital_timing/eeg_adc_dig/tt_025C_3v30/unconstrained.rpt
puts "SUMMARY_SETUP [sta::worst_slack -max]"
puts "SUMMARY_HOLD [sta::worst_slack -min]"
report_tns
exit
