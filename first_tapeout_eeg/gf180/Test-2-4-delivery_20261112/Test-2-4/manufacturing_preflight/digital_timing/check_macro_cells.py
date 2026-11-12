from pathlib import Path
import klayout.db as k,re,collections,json
p=Path('/work/Test-2-4/manufacturing_preflight/digital_timing');l=k.Layout();l.read('/work/Test-2-4/gds/Test-2-4.gds');rows=[]
for name in ['eeg_digital_top','eeg_adc_dig']:
 c=l.cell(name);g=collections.Counter()
 for i in c.each_inst():
  child=i.cell.name
  if child.startswith('gf180mcu_fd_sc_'):g[child]+=i.na*i.nb if i.is_regular_array() else 1
 text=(Path('/work/gf180/tapeout/layout/gds')/(name+'.nl.v')).read_text();v=collections.Counter(re.findall(r'\b(gf180mcu_fd_sc_\w+)\s+\\?\S+\s*\(',text))
 missing=v-g;extra=g-v
 rows.append({'module':name,'netlist_cells':sum(v.values()),'gds_cells':sum(g.values()),'netlist_cells_missing_from_gds':dict(missing),'extra_gds_cell_types':dict(extra),'counts_match_for_every_netlist_cell_type':not bool(missing),'warning':'Cell-type counts are supplemental correspondence evidence, not connectivity equivalence. Core LVS and macro geometry checks remain separate evidence.'})
(p/'macro_cell_counts.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
