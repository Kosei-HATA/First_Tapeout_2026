v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
F {}
N -400 -560 400 -560 {lab=VDD}
N -400 -200 400 -200 {lab=0}
C {vsource.sym} 300 -600 0 0 {name=V1 value=1.8 savecurrent=false}
C {vdd.sym} 300 -630 0 0 {name=l1 lab=VDD}
C {gnd.sym} 300 -570 0 0 {name=l2 lab=0}
C {vsource.sym} -600 -300 1 0 {name=Vinp value=0.7 savecurrent=false}
C {gnd.sym} -630 -300 0 0 {name=l4 lab=0}
C {lab_pin.sym} -570 -300 0 0 {name=pVinp sig_type=std_logic lab=Vinp}
N -570 -300 -310 -300 {lab=Vinp}
N -310 -300 -310 -490 {lab=Vinp}
N -310 -490 -120 -490 {lab=Vinp}
N -120 -490 -120 -400 {lab=Vinp}
C {vsource.sym} -600 -450 1 0 {name=Vint value=0.9 savecurrent=false}
C {gnd.sym} -630 -450 0 0 {name=l5 lab=0}
C {lab_pin.sym} -570 -450 0 0 {name=pVint sig_type=std_logic lab=Vint}
N -570 -450 -150 -450 {lab=Vint}
N -150 -450 -150 -300 {lab=Vint}
N -150 -300 -220 -300 {lab=Vint}
C {vsource.sym} 500 -600 1 0 {name=Vbias value=0.7 savecurrent=false}
C {gnd.sym} 470 -600 0 0 {name=l6 lab=0}
C {lab_pin.sym} 530 -600 0 0 {name=pVbias sig_type=std_logic lab=Vbias}
N 530 -600 530 -500 {lab=Vbias}
N 530 -500 180 -500 {lab=Vbias}
C {sky130_fd_pr/nfet3_01v8.sym} -300 -400 0 0 {name=M1
W=1
L=0.5
body=GND
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/nfet3_01v8.sym} -100 -400 0 0 {name=M2
W=1
L=0.5
body=GND
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/nfet3_01v8.sym} -200 -300 0 0 {name=M3
W=16
L=0.5
body=GND
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/pfet3_01v8.sym} -300 -500 0 0 {name=M5
W=16
L=0.5
body=VDD
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/pfet3_01v8.sym} -100 -500 0 0 {name=M6
W=16
L=0.5
body=VDD
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/nfet3_01v8.sym} 200 -400 0 0 {name=M7
W=8
L=0.15
body=GND
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=nfet_01v8
spiceprefix=X
}
C {sky130_fd_pr/pfet3_01v8.sym} 200 -500 0 0 {name=M8
W=16
L=0.35
body=VDD
nf=1
mult=1
ad="'int((nf+1)/2) * W/nf * 0.29'"
pd="'2*int((nf+1)/2) * (W/nf + 0.29)'"
as="'int((nf+2)/2) * W/nf * 0.29'"
ps="'2*int((nf+2)/2) * (W/nf + 0.29)'"
nrd="'0.29 / W'" nrs="'0.29 / W'"
sa=0 sb=0 sd=0
model=pfet_01v8
spiceprefix=X
}
N -280 -560 -280 -530 {lab=VDD}
N -80 -560 -80 -530 {lab=VDD}
N 220 -560 220 -530 {lab=VDD}
C {vdd.sym} 0 -560 0 0 {name=l7 lab=VDD}
N -180 -270 -180 -200 {lab=0}
N 220 -370 220 -200 {lab=0}
C {gnd.sym} 0 -200 0 0 {name=l8 lab=0}
C {lab_pin.sym} 220 -370 0 0 {name=pgnd7 sig_type=std_logic lab=0}
C {lab_pin.sym} -280 -530 0 0 {name=pvdd5 sig_type=std_logic lab=VDD}
C {lab_pin.sym} -80 -530 0 0 {name=pvdd6 sig_type=std_logic lab=VDD}
C {lab_pin.sym} 220 -530 0 0 {name=pvdd8 sig_type=std_logic lab=VDD}
N -280 -370 -80 -370 {lab=tail}
N -180 -370 -180 -330 {lab=tail}
C {lab_pin.sym} -180 -370 0 0 {name=ptail sig_type=std_logic lab=tail}
N -280 -470 -280 -430 {lab=d1}
N -320 -500 -280 -500 {lab=d1}
N -280 -500 -280 -470 {lab=d1}
N -280 -500 -120 -500 {lab=d1}
C {lab_pin.sym} -280 -450 0 0 {name=pd1 sig_type=std_logic lab=d1}
N -80 -470 -80 -430 {lab=net6}
N -80 -430 180 -430 {lab=net6}
N 180 -430 180 -400 {lab=net6}
C {lab_pin.sym} -80 -450 0 0 {name=pnet6 sig_type=std_logic lab=net6}
N 220 -470 220 -430 {lab=Vout}
C {lab_pin.sym} 220 -450 0 0 {name=pVout sig_type=std_logic lab=Vout}
C {sky130_fd_pr/cap_mim_m3_1.sym} 170 -440 1 0 {name=C2 model=cap_mim_m3_1 W=1 L=1 MF=1 spiceprefix=X}
N 200 -440 220 -440 {lab=Vout}
N 140 -440 140 -430 {lab=net6}
C {sky130_fd_pr/res_generic_po.sym} 130 -470 0 0 {name=R1
W=1
L=2054
model=res_generic_po
spiceprefix=X
mult=1
}
C {sky130_fd_pr/res_generic_po.sym} -360 -400 1 0 {name=R2
W=1
L=21
model=res_generic_po
spiceprefix=X
mult=1
}
C {vsource.sym} -600 -400 1 0 {name=Vi value="DC 0 AC 1 SIN(0 5m 100)" savecurrent=false}
C {gnd.sym} -630 -400 0 0 {name=l3 lab=0}
C {lab_pin.sym} -570 -400 0 0 {name=pVi sig_type=std_logic lab=Vi_in}
N -570 -400 -500 -400 {lab=Vi_in}
N -500 -400 -500 -430 {lab=Vi_in}
C {capa.sym} -500 -400 0 0 {name=C_in value=1m m=1}
N -500 -370 -400 -370 {lab=N1}
N -400 -370 -400 -400 {lab=N1}
N -400 -400 -390 -400 {lab=N1}
N 220 -450 130 -450 {lab=Vout}
N 130 -450 130 -500 {lab=Vout}
N 130 -440 130 -420 {lab=Vinn}
N 130 -420 -320 -420 {lab=Vinn}
N -320 -420 -320 -400 {lab=Vinn}
C {lab_pin.sym} -320 -400 0 0 {name=pVinn sig_type=std_logic lab=Vinn}
N -330 -400 -320 -400 {lab=Vinn}
C {lab_pin.sym} 400 -450 0 0 {name=pDout sig_type=std_logic lab=Dout}
C {code_shown.sym} -700 -100 0 0 {name=s2 only_toplevel=false format="tcleval( @value )" value=".lib $::SKYWATER_MODELS/sky130.lib.spice tt
* Sky130 1.8V AC-coupled inverting amplifier with 1-bit ADC
* Gain=-99 (R1=99k/R2=1k), Vinp=0.7V virtual ground
* 1-bit ADC comparator: Dout=1.8V when Vout is above VDD/2 (0.9V)
Bcmp Dout 0 V=1.8*(1+tanh(100*(V(Vout)-0.9)))/2
.control
op
ac dec 20 1 1GHz
dc Vinp 0 1.8 0.01
tran 10u 30m
save all
write 1samp_opamp_adc.raw
.endc"}
