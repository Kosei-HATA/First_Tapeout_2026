.include eeg_fd_ota_core_highgain.spice
.include eeg_cmfb_amp.spice
.include eeg_fd_ota_twostage_highgain.spice
VDD_SRC VDD18 0 {VDD}
VREF VCM_REF 0 {VCM}
VBN_SRC VBN 0 {VBN}
VINP INP 0 DC {VCM} AC 0.5 0
VINN INN 0 DC {VCM} AC 0.5 180
XAFE INP INN VCM_REF VBN OUTP OUTN VDD18 0 eeg_fd_ota_twostage_highgain
CLOADP OUTP 0 5p
CLOADN OUTN 0 5p
.control
set noaskquit
op
let idd=-i(VDD_SRC)
let vcmout=(v(OUTP)+v(OUTN))/2
print v(OUTP) v(OUTN) vcmout idd
ac dec 100 0.1 10Meg
let vdiff=v(OUTP)-v(OUTN)
let gain_db=db(vdiff)
let phase_deg=180/pi*ph(vdiff)
meas ac gain_10hz_db find gain_db at=10
meas ac gain_100hz_db find gain_db at=100
meas ac gain32_xover when gain_db=30.103 fall=1
meas ac phase_at_gain32 find phase_deg when gain_db=30.103 fall=1
quit
.endc
.end
