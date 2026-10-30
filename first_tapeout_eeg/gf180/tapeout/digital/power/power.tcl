# OpenSTA: power of one macro (post-route netlist, final SDC and SPEF of its LibreLane run)
# with the switching activity of the gate-level simulation (read_vcd), or with OpenSTA's
# default activity when SCOPE is empty. Environment: LIB NL TOP SDC SPEF SCOPE VCD.
read_liberty $::env(LIB)
read_verilog $::env(NL)
link_design $::env(TOP)
read_sdc $::env(SDC)
read_spef $::env(SPEF)
if {$::env(SCOPE) ne ""} {
    read_vcd -scope $::env(SCOPE) $::env(VCD)
    report_activity_annotation
}
report_power
