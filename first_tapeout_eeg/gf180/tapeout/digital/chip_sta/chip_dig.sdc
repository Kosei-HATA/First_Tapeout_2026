# Chip-level timing constraints of the digital interface (chip_sta.tcl, chip_dig.v).
#
# MCLK enters through the bidir pad bidir[0] (the external 32.768 MHz oscillator,
# 2 ns edges assumed); the clock reaches both macros' MCLK pins through the pad's input
# buffer and the chip wiring (chip_nets.py), and the macros' timing models contain
# their clock trees. Derate and uncertainty as in the macro SDC files.
create_clock -name MCLK -period 30.5 [get_ports MCLK_PAD]
set_input_transition 2.0 [get_ports MCLK_PAD]
set_clock_uncertainty 0.25 [get_clocks MCLK]
set_propagated_clock [get_clocks MCLK]
set_timing_derate -early 0.95
set_timing_derate -late 1.05

# TH: launched by CMP_STROBE at e0 (u_top), through the quantizer (u_q), captured by
# eeg_adc_dig at e2
set_multicycle_path -setup 2 -to [get_pins {u_adc/TH[*]}]
set_multicycle_path -hold 1 -to [get_pins {u_adc/TH[*]}]

# CODE: register in eeg_adc_dig loaded at e2; eeg_digital_top samples it under enables
# at e4 (CIC) and e0 (raw serializer), never at e2 or e3 (eeg_digital_top.sdc)
set_multicycle_path -setup 2 -to [get_pins {u_top/CODE[*]}]
set_false_path -hold -to [get_pins {u_top/CODE[*]}]

# analog receivers: constrained only to report their arrival times
set_output_delay 0.0 -clock [get_clocks MCLK] [all_outputs]
