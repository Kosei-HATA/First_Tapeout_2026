#!/usr/bin/env python3
"""Monte Carlo driver for the chopped PGA x32 (internal chopper, full2).

Per run: input-pair offset DVOS ~ N(0, 0.5 mV) injected after the input
chopper (OTA's own offset, chopped to 8 kHz), feedback-cap mismatch
delta ~ N(0, 0.3%). Measures residual input offset, 8 kHz ripple,
CM->diff conversion at 50 Hz (CMRR), and signal gain at 8 Hz.

Usage: python3 scripts/mc_pga.py [N] [parallel]
"""
import numpy as np, subprocess, sys, os, concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XDIR = os.path.join(ROOT, "source/trials/20260902/xschem")
RDIR = os.path.join(ROOT, "source/trials/20260902/results")
os.makedirs(RDIR, exist_ok=True)

TEMPLATE = """* MC run @IDX@: chopped PGA x32, offset+cap mismatch
.lib /Users/noah/.volare/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.tech/ngspice/sky130.lib.spice tt
.include eeg_tg_lowq.spice
.include eeg_fd_ota_core_soft.spice
.include eeg_bias_gen.spice
.include eeg_fd_ota_chopped_full2.spice
.param VDD=1.80 VCM=0.9 TCHOP=1m
VDD_SRC VDD18 0 {VDD}
VREF VCM_REF 0 {VCM}
VPHI PHI 0 PULSE(0 {VDD} 50n 20n 20n 499.85u {TCHOP})
VPHIB PHIB 0 PULSE(0 {VDD} 500.05u 20n 20n 499.85u {TCHOP})
BNPHI NPHI 0 V={VDD}-v(PHI)
BNPHIB NPHIB 0 V={VDD}-v(PHIB)
* CM interference 50 Hz 100 mV on both inputs + differential 8 Hz 100 uV
VSIGP SIGP 0 SIN({VCM} 100m 200)
VSIGN SIGN 0 SIN({VCM} 100m 200)
VDFP SIGP SIGP2 SIN(0 100u 100)
VDFN SIGN SIGN2 SIN(0 -100u 100)
CINP SIGP2 INP 32p
CINN SIGN2 INN 32p
CFP OUTN INP @CFP@
CFN OUTP INN @CFN@
RBIASP INP VCM_REF 10G
RBIASN INN VCM_REF 10G
XAFE INP INN VCM_REF OUTP OUTN PHI NPHI PHIB NPHIB PHI NPHI PHIB NPHIB VDD18 0 eeg_fd_ota_chopped_full2 DVOS=@DVOS@
CLOADP OUTP 0 5p
CLOADN OUTN 0 5p
.nodeset v(OUTP)=0.93 v(OUTN)=0.93 v(INP)=0.9 v(INN)=0.9 v(XAFE.N1P)=0.93 v(XAFE.N1N)=0.93 v(XAFE.N2P)=0.93 v(XAFE.N2N)=0.93 v(XAFE.VBP1)=0.6155 v(XAFE.VBP2)=0.3848 v(XAFE.VBN)=0.614 v(XAFE.VBNRAW)=0.614
.control
set noaskquit
save time v(OUTP) v(OUTN)
tran 50n 145m 100m
let voutd=v(OUTP)-v(OUTN)
let vcmout=(v(OUTP)+v(OUTN))/2
meas tran vout_mean avg voutd from=100m to=140m
meas tran vcm_avg avg vcmout from=100m to=140m
wrdata @OUTCSV@ time voutd vcmout
quit
.endc
.end
"""

def run(idx, dvos, dcfp, dcfn):
    outcsv = os.path.join(RDIR, f"mc_{idx:03d}.csv")
    deck = (TEMPLATE.replace("@IDX@", str(idx))
                    .replace("@DVOS@", f"{dvos:.4e}")
                    .replace("@CFP@", f"{1e-12*(1+dcfp):.4e}")
                    .replace("@CFN@", f"{1e-12*(1+dcfn):.4e}")
                    .replace("@OUTCSV@", outcsv))
    spice = f"/tmp/mc_{idx:03d}.spice"
    with open(spice, "w") as f:
        f.write(deck)
    r = subprocess.run(["ngspice", "-b", spice], cwd=XDIR,
                       capture_output=True, text=True, timeout=600)
    log = r.stdout
    vout_mean = vcm_avg = None
    for line in log.splitlines():
        if line.startswith("vout_mean"): vout_mean = float(line.split()[2])
        if line.startswith("vcm_avg"):   vcm_avg  = float(line.split()[2])
    # FFT of last 125 ms (8 Hz = 1 period, 50 Hz = 6.25 periods -> use 125 ms window: 8Hz x1, 50Hz x6.25 not integer; use 1s? too long. Use last 125ms anyway with Hann)
    d = np.loadtxt(outcsv)
    t = d[:,0]; vo = d[:,3]
    sel = (t >= 100e-3) & (t < 140e-3)
    t = t[sel]; vo = vo[sel]
    N = len(t); dt = np.mean(np.diff(t))
    win = np.hanning(N)
    sp = np.abs(np.fft.rfft(vo*win))*2/np.sum(win)
    fr = np.fft.rfftfreq(N, dt)
    a8  = sp[np.argmin(np.abs(fr-100))]    # differential signal
    a50 = sp[np.argmin(np.abs(fr-200))]   # CM->diff leakage
    a8k = sp[np.argmin(np.abs(fr-8000))] # chop ripple fundamental
    return dict(idx=idx, dvos=dvos, dcfp=dcfp, dcfn=dcfn,
                vout_mean=vout_mean, vcm_avg=vcm_avg,
                a8=a8, a50=a50, a8k=a8k)

def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    PAR = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    rng = np.random.default_rng(20260902)
    dvos = rng.normal(0, 0.5e-3, N)
    dcfp = rng.normal(0, 0.003, N)
    dcfn = rng.normal(0, 0.003, N)
    with cf.ThreadPoolExecutor(PAR) as ex:
        futs = [ex.submit(run, i, dvos[i], dcfp[i], dcfn[i]) for i in range(N)]
        res = [f.result() for f in futs]
    res.sort(key=lambda r: r["idx"])
    print(f"{'idx':>4} {'dvos_uV':>9} {'vos_resid_uV':>13} {'ripple8k_mV':>12} {'gain_err%':>10} {'CMRR_dB':>9} {'vcm':>7}")
    vos_r=[]; cmrr=[]; gerr=[]
    for r in res:
        vos = r["vout_mean"]/32*1e6
        ge  = (r["a8"]/(200e-6*32)-1)*100   # expected = 100u*2*32 = 6.4mV
        cm  = 20*np.log10(0.1/ (r["a50"]/32)) if r["a50"]>0 else float('nan')
        vos_r.append(vos); cmrr.append(cm); gerr.append(ge)
        print(f"{r['idx']:4d} {r['dvos']*1e6:9.1f} {vos:13.2f} {r['a8k']*1e3:12.3f} {ge:10.3f} {cm:9.1f} {r['vcm_avg']:7.4f}")
    print(f"\nresidual offset: mean={np.mean(vos_r):.2f} uV, std={np.std(vos_r):.2f} uV, max|.|={np.max(np.abs(vos_r)):.2f} uV")
    print(f"gain error: mean={np.mean(gerr):.3f}%, std={np.std(gerr):.3f}%, 3sigma worst={np.mean(gerr)+3*np.std(gerr):.3f}%")
    print(f"CMRR@200Hz: min={np.nanmin(cmrr):.1f} dB, mean={np.nanmean(cmrr):.1f} dB")

if __name__ == "__main__":
    main()
