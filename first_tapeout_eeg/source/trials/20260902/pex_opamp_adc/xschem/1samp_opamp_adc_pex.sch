v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
F {}
C {opamp_adc_pex.sym} 0 -400 0 0 {name=X1}
C {vsource.sym} 300 -600 0 0 {name=V1 value=1.8 savecurrent=false}
C {vdd.sym} 300 -630 0 0 {name=l1 lab=VDD}
C {gnd.sym} 300 -570 0 0 {name=l2 lab=0}
N 0 -480 0 -490 {lab=VDD}
C {vdd.sym} 0 -490 0 0 {name=l7 lab=VDD}
N 0 -320 0 -310 {lab=0}
C {gnd.sym} 0 -310 0 0 {name=l8 lab=0}
C {vsource.sym} -250 -440 1 0 {name=Vinp value=0.7 savecurrent=false}
C {gnd.sym} -280 -440 0 0 {name=l4 lab=0}
C {lab_pin.sym} -220 -440 0 0 {name=pVinp sig_type=std_logic lab=Vinp}
N -220 -440 -60 -440 {lab=Vinp}
C {vsource.sym} -250 -380 1 0 {name=Vbias value=0.7 savecurrent=false}
C {gnd.sym} -280 -380 0 0 {name=l6 lab=0}
C {lab_pin.sym} -220 -380 0 0 {name=pVbias sig_type=std_logic lab=Vbias}
N -220 -380 -60 -380 {lab=Vbias}
C {vsource.sym} -250 -360 1 0 {name=Vref value=0.9 savecurrent=false}
C {gnd.sym} -280 -360 0 0 {name=l5 lab=0}
C {lab_pin.sym} -220 -360 0 0 {name=pVref sig_type=std_logic lab=Vref}
N -220 -360 -60 -360 {lab=Vref}
C {vsource.sym} -600 -420 1 0 {name=Vi value="DC 0 AC 1 SIN(0 5m 100)" savecurrent=false}
C {gnd.sym} -630 -420 0 0 {name=l3 lab=0}
C {lab_pin.sym} -570 -420 0 0 {name=pVi sig_type=std_logic lab=Vi_in}
N -570 -420 -500 -420 {lab=Vi_in}
N -500 -420 -500 -450 {lab=Vi_in}
C {capa.sym} -500 -420 0 0 {name=C_in value=1m m=1}
N -500 -390 -430 -390 {lab=N1}
N -430 -390 -430 -420 {lab=N1}
N -430 -420 -390 -420 {lab=N1}
C {sky130_fd_pr/res_generic_po.sym} -360 -420 1 0 {name=R2
W=1
L=21
model=res_generic_po
spiceprefix=X
mult=1
}
N -330 -420 -60 -420 {lab=Vinn}
C {lab_pin.sym} -330 -420 0 0 {name=pVinn sig_type=std_logic lab=Vinn}
N 60 -420 100 -420 {lab=Vout}
N 100 -420 100 -450 {lab=Vout}
N 100 -450 130 -450 {lab=Vout}
N 130 -450 130 -500 {lab=Vout}
C {sky130_fd_pr/res_generic_po.sym} 130 -470 0 0 {name=R1
W=1
L=2054
model=res_generic_po
spiceprefix=X
mult=1
}
N 130 -440 130 -400 {lab=Vinn}
N 130 -400 -80 -400 {lab=Vinn}
N -80 -400 -80 -420 {lab=Vinn}
C {lab_pin.sym} 100 -450 0 0 {name=pVout sig_type=std_logic lab=Vout}
N 60 -380 100 -380 {lab=Dout}
C {lab_pin.sym} 100 -380 0 0 {name=pDout sig_type=std_logic lab=Dout}
C {code_shown.sym} -700 -100 0 0 {name=s2 only_toplevel=false format="tcleval( @value )" value=".lib $::SKYWATER_MODELS/sky130.lib.spice tt
.include /Users/noah/OSBCIChip/xschem/opamp_adc_pex.spice
* Sky130 1.8V AC-coupled inverting amplifier with 1-bit ADC (POST-LAYOUT / PEX)
* OPAMP_ADC_0 extracted from the redesigned ALIGN layout (opamp: stack=3,
* Leff=0.45um; gds/opamp_adc_v2.gds) with magic and annotated with layout
* parasitic capacitors (lvs_work/ext2pex.py). Same stimulus and R1/R2/C_in
* feedback as the ideal 1samp_opamp_adc.sch for direct comparison.
* Gain=-99 (R1=99k/R2=1k), Vinp=0.7V virtual ground, comparator Vref=0.9V.
.control
op
ac dec 20 1 1GHz
dc Vinp 0 1.8 0.01
tran 10u 30m
save all
write 1samp_opamp_adc_pex.raw
.endc"}
