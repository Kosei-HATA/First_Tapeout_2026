from pathlib import Path
import subprocess,time,json
p=Path('/work/Test-2-4/manufacturing_preflight/analog');o=p/'afe_current_top_pilot';o.mkdir(exist_ok=True)
r=p/'sim_work/gf180/tapeout';T=1/128e3;TM=1/32.768e6;stop=4*T
blank=[(0,0)]
for k in range(10):
 e=50e-9+k*T/2
 blank.extend([(e-TM,0),(e-TM+.5e-9,3.3),(e+7*TM,3.3),(e+7*TM+.5e-9,0)])
bl=' '.join(f'{t:.12g} {v}' for t,v in blank if t>=0)
incs='\n'.join(f'.include {r}/{f}' for f in ['afe/eeg_afe.spice','afe/eeg_afe_clk.spice','bias/eeg_bias.spice'])
load='\n'.join(f'XL{s}{i} OUT{s} VCM 0 ppolyf_u_1k r_length=291.28u r_width=1u' for s in ['P','N'] for i in range(16))
deck=f"""* Current full AFE initialization and speed pilot; NOT settled gain
.include {p}/models/design.ngspice
.lib {p}/models/sm141064.ngspice typical
.lib {p}/models/sm141064.ngspice res_typical
.lib {p}/models/sm141064.ngspice mimcap_typical
.lib {p}/models/sm141064.ngspice cap_mim
.lib {p}/models/sm141064.ngspice moscap_typical
{incs}
.temp 27
.options sparse method=gear maxord=2 reltol=1e-4 abstol=1e-12 vntol=1e-7
VDD VDD 0 3.3
VRP VRP 0 1.9
VRN VRN 0 1.4
VIT ITST 0 1
XB VBN VBCM BLP BLN VBN1 VBCM1 VNC1 VPC1 VBPC2 VBNC2 IDP IDN IQ ITST VCM VRP VRN VDD 0 0 VDD 0 VDD VDD 0 eeg_bias
XDQ IQ IQ 0 0 nfet_03v3 W=4u L=2u nf=1 m=8
RCLKP VDD VCLK 100
RCLKN GCLK 0 100
CCLK VCLK GCLK 150p
VCH CHOP 0 PULSE(0 3.3 50n .5n .5n {T/2-.5e-9:.12g} {T:.12g})
ECO CHOP_OUT 0 CHOP 0 1
VBL BLANK 0 PWL({bl})
VRS AFE_RST 0 PWL(0 3.3 {T:.12g} 3.3 {T+1e-9:.12g} 0)
XC CHOP CHOP_OUT BLANK VDD AFE_RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH RST VCLK GCLK eeg_afe_clk
VS SRC 0 PWL(0 0 {T+100e-9:.12g} 0 {T+101e-9:.12g} 0.0001)
EP ELP VCM SRC 0 0.5
EN ELN VCM SRC 0 -0.5
XA ELP ELN OUTP OUTN VCM VBN VBCM BLP BLN RST CIA NCIA CIB NCIB CDA NCDA CDB NCDB OFPH 0
+ 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 VDD 0 eeg_afe
{load}
.nodeset v(xb.g1)=.85 v(xb.gp)=2.2 v(vbn)=.84 v(vbcm)=.81 v(xb.nt)=.84
+ v(xb.nc)=.81 v(xb.nd)=.8 v(xb.sb)=0 v(bln)=1.1 v(blp)=1.5 v(xb.s2)=.05
.control
set numdgt=15
save v(outp) v(outn) v(vcm) v(vbn) v(vbcm) v(blp) v(bln) v(cia) v(cib) v(cda) v(cdb) v(rst) v(src) v(vclk) v(gclk) v(xa.inp) v(xa.inn)
tran 2n {stop:.12g} 0 2n
wrdata wave.csv v(outp) v(outn) v(vcm) v(vbn) v(vbcm) v(blp) v(bln) v(cia) v(cib) v(cda) v(cdb) v(rst) v(src) v(vclk) v(gclk) v(xa.inp) v(xa.inn)
quit
.endc
.end
"""
(o/'tb.spice').write_text(deck);(o/'.spiceinit').write_text('set ngbehavior=hsa\nset num_threads=1\n')
start=time.time()
with (o/'run.log').open('w') as log:
 try:
  q=subprocess.run(['/foss/tools/bin/ngspice','-b','tb.spice'],cwd=o,stdout=log,stderr=subprocess.STDOUT,timeout=600)
  status={'exitcode':q.returncode,'seconds':time.time()-start,'requested_time_s':stop}
 except subprocess.TimeoutExpired:status={'exitcode':'timeout600s','seconds':time.time()-start,'requested_time_s':stop}
(o/'status.json').write_text(json.dumps(status,indent=2));print(status)
