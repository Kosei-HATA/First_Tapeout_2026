# eeg_adc_dig timing constraints (PnR and signoff). Based on LibreLane's base.sdc,
# with the quantizer input TH as a 2-cycle path.
#
# TH[30:0] comes from the analog quantizer: it is launched by the e0 edge (the
# CMP_STROBE flip-flop in eeg_digital_top), settles within about 4 ns of the strobe
# at the comparators (2.3 ns typical), and is sampled at e2 (TH_CAPTURE = frame
# cycle 1). The input delay of 15 ns covers the strobe flip-flop, the route to the
# quantizer, the clock driver, the comparator, the latch and the route back.

create_clock [get_ports MCLK] -name MCLK -period $::env(CLOCK_PERIOD)
set clocks [get_clocks MCLK]

set io_delay [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]

# strobes, enable and reset from eeg_digital_top flip-flops: at ss/125 C about 4 ns
# of clock tree there, 3 ns clock-to-output, an output buffer and the route across
# the isolation band, so up to about 10 ns after the MCLK edge at this pin
set ctrl_inputs [get_ports {RST_N TH_CAPTURE DAC_LOAD DWA_EN}]
set_input_delay -max 10.0 -clock $clocks $ctrl_inputs
set_input_delay -min 2.0 -clock $clocks $ctrl_inputs

# quantizer outputs: launched at e0, captured at e2
set th_inputs [get_ports {TH[*]}]
set_input_delay 15.0 -clock $clocks $th_inputs
set_multicycle_path -setup 2 -from $th_inputs
set_multicycle_path -hold 1 -from $th_inputs

# CODE (to eeg_digital_top, used at e4 and e0) and SEL1/SEL2 (DAC switch drivers)
set_output_delay $io_delay -clock $clocks [all_outputs]

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    [concat $ctrl_inputs $th_inputs]
set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    [get_ports MCLK]

set_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0] [all_outputs]
set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) $clocks
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $clocks
set_timing_derate -early [expr 1 - $::env(TIME_DERATING_CONSTRAINT) / 100.0]
set_timing_derate -late [expr 1 + $::env(TIME_DERATING_CONSTRAINT) / 100.0]
set_propagated_clock [all_clocks]
