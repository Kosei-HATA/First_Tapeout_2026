# Chip-level STA of the digital interface for one corner (run_chip_sta.sh).
# Environment: PAD_LIB TOP_LIB ADC_LIB Q_LIB SPEF OUT (directory) HERE (this directory) BUILD (chip_nets.py's outputs)
read_liberty $::env(PAD_LIB)
read_liberty $::env(TOP_LIB)
read_liberty $::env(ADC_LIB)
read_liberty $::env(Q_LIB)
read_verilog $::env(BUILD)/chip_dig.v
link_design chip_dig
read_spef $::env(SPEF)
read_sdc $::env(HERE)/chip_dig.sdc

set out $::env(OUT)
report_checks -path_delay max -group_path_count 3 -format full_clock_expanded \
    -fields {slew cap input_pins} -digits 3 > $out/setup.rpt
report_checks -path_delay min -group_path_count 3 -format full_clock_expanded \
    -fields {slew cap input_pins} -digits 3 > $out/hold.rpt

# clock at the macros' MCLK pins and at the end of the inter-block wires
set f [open $out/summary.txt w]
foreach p {u_pad/Y u_top/MCLK u_adc/MCLK} {
    set pin [get_pins $p]
    puts $f [format "clock %s arrival max %.3f min %.3f slew max %.3f" $p \
        [get_property $pin arrival_max_rise] [get_property $pin arrival_min_rise] [get_property $pin slew_max_rise]]
}
# endpoints between the blocks and from the quantizer: worst setup / hold slack
foreach p [concat [get_pins {u_adc/TH_CAPTURE u_adc/DAC_LOAD u_adc/DWA_EN u_adc/RST_N}] \
               [get_pins {u_top/CODE[*]}] [get_pins {u_adc/TH[*]}]] {
    puts $f [format "endpoint %s setup %.3f hold %.3f arrival max %.3f min %.3f slew max %.3f" \
        [get_full_name $p] [get_property $p slack_max] [get_property $p slack_min] \
        [expr max([get_property $p arrival_max_rise], [get_property $p arrival_max_fall])] \
        [expr min([get_property $p arrival_min_rise], [get_property $p arrival_min_fall])] \
        [expr max([get_property $p slew_max_rise], [get_property $p slew_max_fall])]]
}
# the quantizer's strobe input: arrival and slew
set p [get_pins u_q/CK]
puts $f [format "analog u_q/CK arrival max %.3f min %.3f slew max %.3f min %.3f" \
    [expr max([get_property $p arrival_max_rise], [get_property $p arrival_max_fall])] \
    [expr min([get_property $p arrival_min_rise], [get_property $p arrival_min_fall])] \
    [expr max([get_property $p slew_max_rise], [get_property $p slew_max_fall])] \
    [expr min([get_property $p slew_min_rise], [get_property $p slew_min_fall])]]
# analog receivers (output ports): the full paths, parsed by run_chip_sta.sh
foreach port [all_outputs] {
    report_checks -to $port -path_delay max -fields {slew cap} -digits 3 >> $out/ports_max.rpt
    report_checks -to $port -path_delay min -fields {slew cap} -digits 3 >> $out/ports_min.rpt
}
puts $f [format "worst setup %.3f hold %.3f" [sta::worst_slack -max] [sta::worst_slack -min]]
close $f
# the blanking ports edge by edge (chip_sta_report.py: CHOP_BLANK's rise before either CHOP_OUT edge, its fall after
# them; 11/24: r14's timing model with the preset / clear arcs makes CHOP_BLANK's fall the SOFT_RESET path, so the
# worst of both edges is not the clocked edge there)
set f [open $out/edges.txt w]
foreach port {CHOP_OUT CHOP_BLANK} {
    foreach d {max min} {
        foreach e {rise fall} {
            set pe [lindex [find_timing_paths -${e}_to [get_ports $port] -path_delay $d] 0]
            if {$pe ne ""} {
                puts $f [format "edge %s %s %s %.3f" $port $d $e [get_property [lindex [get_property $pe points] end] arrival]]
            }
        }
    }
}
close $f
exit
