#!/bin/bash
cd /work/Test-2-4/verification/core_with_hints
/foss/tools/klayout/klayout -b -r ../core_lvs.lvs -rd input=/work/Test-2-4/verification/core_with_hints/eeg_core_from_delivered.gds -rd topcell=eeg_core -rd schematic=/work/Test-2-4/verification/eeg_core_reference.cdl -rd report=/work/Test-2-4/verification/core_with_hints/eeg_core.lvsdb -rd target_netlist=/work/Test-2-4/verification/core_with_hints/eeg_core_extracted.cir -rd run_mode=flat -rd metal_level=5LM -rd metal_top=11K -rd mim_option=B -rd mim_cap=2 -rd poly_res=1k -rd combine=true -rd top_lvl_pins=true -rd implicit_connect=false -rd simplify=false -rd purge=false -rd purge_nets=false > core_lvs.log 2>&1
rc=$?
printf '%s\n' "$rc" > core_lvs.exitcode
exit "$rc"

