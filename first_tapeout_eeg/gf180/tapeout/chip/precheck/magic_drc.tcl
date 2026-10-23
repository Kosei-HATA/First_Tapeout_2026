# Magic DRC as the precheck runs it (LibreLane's scripts/magic/drc.tcl with the precheck's
# MAGIC_GDS_FLATGLOB), for magic_check.py. env: GDS (input), RPT (report), TOP (top cell).
# Exits 1 on a Tcl error; a crash shows as no "DRC Checking DONE" line.
if {[catch {
    crashbackups disable
    locking disable
    units internal
    gds noduplicates true
    gds readonly true
    gds maskhints true
    foreach g {*_CDNS_* COMP_FILL COMP_fill_cell POLY2_FILL Poly2_fill_cell *$$* M1_N* M1_P* M2_M1* M3_M2*
               nmos_5p0* nmos_1p2* pmos_5p0* pmos_1p2* via1_* ypass_gate* G_ring_* dcap_103* din_*
               mux821_* rdummy_* pmoscap_* xdec_* ypredec* xpredec* prexdec_* xdec8_* xdec16_* xdec32_*
               sa_*} {
        gds flatglob $g
    }
    gds read $::env(GDS)
    set fout [open $::env(RPT) w]
    set oscale [cif scale out]
    magic::suspendall
    load $::env(TOP)
    select top cell
    drc euclidean on
    drc style drc(full)
    drc check
    set count 0
    puts $fout "$::env(TOP)"
    puts $fout "----------------------------------------"
    foreach {errtype coordlist} [drc listall why] {
        puts $fout $errtype
        puts $fout "----------------------------------------"
        foreach coord $coordlist {
            puts $fout [format " %.3fum %.3fum %.3fum %.3fum" {*}[lmap v $coord {expr {$oscale * $v}}]]
            incr count
        }
        puts $fout "----------------------------------------"
    }
    puts $fout "\[INFO\] COUNT: $count"
    close $fout
    puts stdout "\[INFO\] COUNT: $count"
    puts stdout "\[INFO\] DRC Checking DONE"
    flush stdout
} err]} {
    puts "Error: $err"
    exit 1
}
exit 0
