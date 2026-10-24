# eeg_digital_top timing constraints, candidate d1 (C3, 2026-10-24): eeg_digital_top.sdc
# plus the chip-level loads of the outputs that drive long nets, so that the resizer
# sizes their output buffers (documentation/gf180_digital_verification_20261024.md).
# Run d1 (gf180/tapeout/digital/eeg_digital_top/runs/d1) was made with this file:
#   cd /Users/noah/Codings/ws_gf180/eeg_padring && nix-shell --run "librelane <repo>/gf180/tapeout/
#   digital/eeg_digital_top/config.yaml --pdk gf180mcuD --pdk-root gf180mcu --manual-pdk
#   --scl gf180mcu_fd_sc_mcu9t5v0 --run-tag d1 -c PNR_SDC_FILE=<this file>
#   -c SIGNOFF_SDC_FILE=<this file>"
# If d1 is adopted, these set_load lines go into eeg_digital_top.sdc.
#
# eeg_digital_top timing constraints (PnR and signoff). Based on LibreLane's base.sdc,
# with CODE[4:0] as a 2-cycle path.
#
# CODE comes from eeg_adc_dig, where it is a register loaded at e2 (TH_CAPTURE =
# frame cycle 1). Its only consumers here sample it under clock enables at e4 (the
# CIC input, cic_en = frame cycle 3) and at e0 (the raw serializer loads it in frame
# cycle 31), so a 2-cycle setup check is exact for the e4 capture and conservative
# for e0. No hold check: CODE changes only at e2, where neither consumer is enabled.
# SCLK, CS_N and MOSI are asynchronous to MCLK and enter 2-FF synchronizers; the
# default input delay is kept for them, which only adds margin. CS_N also drives
# MISO_OE through a combinational path (released at once when CS_N rises).

create_clock [get_ports MCLK] -name MCLK -period $::env(CLOCK_PERIOD)
set clocks [get_clocks MCLK]

set io_delay [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]

set pad_inputs [get_ports {RESET_N SCLK CS_N MOSI}]
set_input_delay $io_delay -clock $clocks $pad_inputs
# CODE: eeg_adc_dig register (about 3 ns of clock tree there, clock-to-output, an
# output buffer and the route back: up to about 10 ns at ss/125 C), 2-cycle path
set code_inputs [get_ports {CODE[*]}]
set_input_delay -max 10.0 -clock $clocks $code_inputs
set_input_delay -min 1.0 -clock $clocks $code_inputs
set_multicycle_path -setup 2 -from $code_inputs
set_false_path -hold -from $code_inputs
set data_inputs [concat $pad_inputs $code_inputs]

set_output_delay $io_delay -clock $clocks [all_outputs]

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    $data_inputs
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

# candidate d1 (C3, 10/24): the chip-level loads of the long nets (chip_sta/chip_nets.py,
# wire + twice the coupling + the receiving gates), so that the resizer sizes their output
# buffers; the other outputs keep OUTPUT_CAP_LOAD
set_load 0.428 [get_ports CMP_STROBE]
set_load 0.159 [get_ports DAC_CLK]
set_load 1.018 [get_ports CHOP]
set_load 1.227 [get_ports CHOP_OUT]
set_load 1.257 [get_ports CHOP_BLANK]
set_load 0.746 [get_ports CHOP1]
set_load 1.251 [get_ports CHOP_EN]
set_load 1.676 [get_ports AFE_RST]
set_load 0.624 [get_ports {TEST_CFG[5]}]
set_load 0.198 [get_ports TH_CAPTURE]
set_load 0.174 [get_ports DAC_LOAD]
set_load 0.149 [get_ports DWA_EN]
set_load 0.136 [get_ports ADC_RST_N]
