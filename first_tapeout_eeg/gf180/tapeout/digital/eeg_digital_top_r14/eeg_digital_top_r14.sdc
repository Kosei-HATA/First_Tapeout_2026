# eeg_digital_top r14 timing constraints (PnR and signoff): the r13 macro's (../eeg_digital_top/eeg_digital_top.sdc,
# whose text is repeated below unchanged) and the exceptions that the STA with the flip-flops' preset / clear arcs
# needs (requirement VER-05: sta_preset_clear_arcs_enabled 1, sta_preset_clear.tcl).
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

# ---------------------------------------------------------------------------------------------------- r14 (VER-05)
# Resets (eeg_digital_top.sv): RESET_N clears the synchronizer rst_sync asynchronously; its output pin_rst_n (=
# tm_rst_n, ADC_RST_N) clears the timing and data path and the SOFT_RESET flip-flops rst_n and soft_cnt; rst_n, a
# flip-flop that a SOFT_RESET drives low for 5 MCLK, clears the control side (registers, sequencer, SPI, FIFO pointers,
# flags). Every reset pin is active low (RN clears, SETN sets): its fall asserts the reset and is the only edge with a
# clear / preset arc (RN fall -> Q fall, SETN fall -> Q rise); its rise releases it (recovery / removal checks).
#
# 1. RESET_N asserts asynchronously into rst_sync and, through pin_rst_n and rst_n, into every flip-flop (RST-01):
#    every path through the clear / preset arcs of rst_sync and of the flip-flops pin_rst_n resets ends while the whole
#    block is in reset (the FIFO's memory, without a reset, is emptied by the reset of its pointers). pin_rst_n falls
#    only then (rst_sync takes 1 at every clock edge while RESET_N is high). The release is timed: from rst_sync's
#    clocked output, the pins' rise (recovery / removal), as without the arcs.
# 2. SOFT_RESET: rst_n falls at a clock edge and clears (sets) the control side through the clear (preset) arcs. Paths
#    into flip-flops that rst_n clears (sets) too end in flip-flops held in reset for 5 MCLK: false. Into everything else
#    but the FIFO's memory (3.) they are timed (VER-05): the timing and data path (chopper rate, BLANK_LEN, CHOP1 rate,
#    the CIC's clear, RAW), rst_n and soft_cnt, and the output ports (DWA_EN to eeg_adc_dig, the analog pins).
# 3. The FIFO's memory (the 8 x 44 flip-flops without a reset, eeg_fifo.sv mem) is read only where it was written
#    (rd_word = the empty word while the level is 0), and every reset empties the FIFO (its pointers and level are
#    control flip-flops): what the memory takes at the edges after a SOFT_RESET's assertion is never read. The SOFT_RESET
#    paths into it are false.
# The flip-flops are found through the buffer trees: from the port RESET_N, from the Q of the flip-flops RESET_N
# clears (rst_sync), and from the net rst_n (the flip-flop's Q keeps the RTL name); the memory as the flip-flops
# without a reset (dffq).
# The arcs are on in every OpenROAD step that reads this file (placement, CTS, timing repair and the STA), so that the
# timing repair sees the SOFT_RESET paths it has to meet (LibreLane's STA steps also source sta_preset_clear.tcl).
set ::sta_preset_clear_arcs_enabled 1
proc eeg_r14_reset_pins {nets} {
    # the reset pins (RN, SETN) the nets reach through buffers: {pin ...}
    set pins [list]
    set todo $nets
    while {[llength $todo]} {
        set net [lindex $todo 0]
        set todo [lrange $todo 1 end]
        foreach p [get_pins -of_objects $net] {
            if {[get_property $p direction] ne "input"} { continue }
            set inst [get_cells -of_objects $p]
            set ref [get_property $inst ref_name]
            set pn [get_property $p lib_pin_name]
            if {$pn eq "RN" || $pn eq "SETN"} {
                lappend pins $p
            } elseif {[regexp {__(clk)?buf_[0-9]+$} $ref]} {
                lappend todo [get_nets -of_objects [get_pins [get_full_name $inst]/Z]]
            }
        }
    }
    return $pins
}
proc eeg_r14_q_nets {pins} {
    set out [list]
    foreach p $pins {
        set q [get_pins -quiet [get_full_name [get_cells -of_objects $p]]/Q]
        if {[llength $q]} { lappend out [get_nets -of_objects $q] }
    }
    return $out
}
# rst_sync (the reset pins RESET_N reaches), then everything pin_rst_n resets (from rst_sync's Q)
set eeg_sync_pins [eeg_r14_reset_pins [list [get_nets RESET_N]]]
set eeg_hard_pins [concat $eeg_sync_pins [eeg_r14_reset_pins [eeg_r14_q_nets $eeg_sync_pins]]]
# the control side (rst_n's pins)
set eeg_soft_pins [eeg_r14_reset_pins [list [get_nets rst_n]]]
set eeg_soft_ffs [list]
foreach p $eeg_soft_pins { lappend eeg_soft_ffs [get_cells -of_objects $p] }
puts "eeg_digital_top_r14.sdc: reset pins: [llength $eeg_sync_pins] from RESET_N (rst_sync), [llength $eeg_hard_pins]\
 with pin_rst_n's, [llength $eeg_soft_pins] from rst_n (SOFT_RESET)"
set_false_path -from [get_ports RESET_N]
set_false_path -fall_through $eeg_hard_pins
set_false_path -fall_through $eeg_soft_pins -to $eeg_soft_ffs
set eeg_mem_ffs [list]
foreach c [get_cells *] {
    if {[regexp {__dffq_[0-9]+$} [get_property $c ref_name]]} { lappend eeg_mem_ffs $c }
}
puts "eeg_digital_top_r14.sdc: [llength $eeg_mem_ffs] flip-flops without a reset (the FIFO's memory)"
if {[llength $eeg_mem_ffs]} {
    set_false_path -fall_through $eeg_soft_pins -to $eeg_mem_ffs
}
