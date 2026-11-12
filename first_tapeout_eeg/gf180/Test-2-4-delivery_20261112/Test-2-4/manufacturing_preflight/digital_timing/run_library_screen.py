from pathlib import Path
import subprocess,json,hashlib,shutil,time
p=Path('/work/Test-2-4/manufacturing_preflight/digital_timing');src=Path('/work/gf180/tapeout');p=p/'library_constraint_screen';p.mkdir(exist_ok=True)
assumptions={'CLOCK_PERIOD':30.517578125,'IO_DELAY_CONSTRAINT':20,'MAX_FANOUT_CONSTRAINT':10,'MAX_TRANSITION_CONSTRAINT':1.5,'MAX_CAPACITANCE_CONSTRAINT':0.5,'OUTPUT_CAP_LOAD':20,'CLOCK_UNCERTAINTY_CONSTRAINT':0.25,'CLOCK_TRANSITION_CONSTRAINT':0.15,'TIME_DERATING_CONSTRAINT':5}
manifest={'scope':'Post-layout netlist, cell delays only. No SPEF or SDF available. Not routed timing signoff.','clock_hz':32768000,'assumptions':assumptions,'io_warning':'20% I/O delay, 20fF load, buf_4 driving cell and 0.15ns clock transition are explicit screening assumptions, not recovered final constraints.','omitted_unavailable_global_constraints':'No invented global fanout/slew/cap limits; retain Liberty pin limits. This is a separate screen, not relaxation of qualified design constraints.', 'exceptions':'Source SDC TH and CODE multicycle setup retained; CODE hold false path retained.','inputs':[],'jobs':[]}
for module,scl in [('eeg_digital_top','gf180mcu_fd_sc_mcu9t5v0'),('eeg_adc_dig','gf180mcu_fd_sc_mcu7t5v0')]:
 nl=src/'layout/gds'/f'{module}.nl.v';sdc=src/'digital'/module/f'{module}.sdc'
 copied=p/f'{module}.sdc';copied.write_text('\n'.join(line for line in sdc.read_text().splitlines() if not line.startswith(('set_max_fanout ','set_max_transition ','set_max_capacitance '))))
 sdc=copied
 for f in [nl,sdc]:manifest['inputs'].append({'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 for corner in ['tt_025C_3v30','ss_125C_3v00','ff_n40C_3v60']:
  out=p/module/corner;out.mkdir(parents=True,exist_ok=True);lib=Path('/foss/pdks/gf180mcuD/libs.ref')/scl/'lib'/f'{scl}__{corner}.lib'
  manifest['inputs'].append({'path':str(lib),'sha256':hashlib.sha256(lib.read_bytes()).hexdigest()})
  pre='\n'.join(f'set ::env({k}) {v}' for k,v in assumptions.items())
  tcl=pre+f'''\nset ::env(SYNTH_DRIVING_CELL) {scl}__buf_4/Z
set ::env(SYNTH_CLK_DRIVING_CELL) {scl}__buf_4/Z
read_liberty {lib}
read_verilog {nl}
link_design {module}
read_sdc {sdc}
report_units
check_setup -verbose
report_checks -path_delay max -group_path_count 10 -format full_clock_expanded -fields {{slew cap fanout input_pins}} -digits 6 > {out}/setup.rpt
report_checks -path_delay min -group_path_count 10 -format full_clock_expanded -fields {{slew cap fanout input_pins}} -digits 6 > {out}/hold.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > {out}/design_rule.rpt
report_checks -unconstrained -group_path_count 10 > {out}/unconstrained.rpt
puts "SUMMARY_SETUP [sta::worst_slack -max]"
puts "SUMMARY_HOLD [sta::worst_slack -min]"
report_tns
exit
'''
  (out/'run.tcl').write_text(tcl);start=time.time()
  with (out/'sta.log').open('w') as f:r=subprocess.run(['/foss/tools/bin/sta','-no_splash','-exit',str(out/'run.tcl')],stdout=f,stderr=subprocess.STDOUT)
  manifest['jobs'].append({'module':module,'corner':corner,'exitcode':r.returncode,'seconds':time.time()-start,'log':str(out/'sta.log')});(p/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest['jobs'],indent=2))
