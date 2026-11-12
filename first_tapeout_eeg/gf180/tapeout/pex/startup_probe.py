#!/usr/bin/env python3
"""The probe rerun of an afe_startup.py start run (figs_perf.su_probe, figure 26 "start-up"):
the run's own deck (runs/startup/<run>/tb.spice) with its control block replaced, to 5.4 ms,
writing every simulator time point of VBN and the supplies of the AFE and the bias block, the
AFE's outputs and VCM (runs/startup/<run>/probe/probe.raw, binary), so that the figure's
chopper-period means are exact (the run's own tr.csv sits on a 100 ns grid, which aliases with
the 7.8125 us chopper period). Waits for the run's deck if the run has only just started.
usage: python startup_probe.py RUN [RUN ...]"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "runs", "startup")
SAVE = ("v(vbn_afe) v(avss_afei) v(avdd_afei) v(vbn_bias) v(avss_bias) v(outp_adc) v(outn_adc) "
        "v(xdut.opi) v(xdut.oni) v(vcm_afe) i(vavdd)")
CONTROL = f""".control
set noaskquit
set filetype=binary
save {SAVE}
tran 9.765625e-08 5.4e-3 0 1.000e-07 uic
write probe.raw
quit
.endc
.end
"""


def probe(run):
    d = os.path.join(RUNS, run)
    src = os.path.join(d, "tb.spice")
    while not os.path.exists(src):
        time.sleep(30)
    deck = open(src).read()
    k = deck.rindex("\n.control\n")
    out = os.path.join(d, "probe")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "tb.spice"), "w").write(deck[:k + 1] + CONTROL)
    t = time.time()
    r = subprocess.run(["ngspice", "-b", "tb.spice"], cwd=out, capture_output=True, text=True)
    open(os.path.join(out, "run.log"), "w").write(r.stdout + r.stderr)
    ok = r.returncode == 0 and os.path.exists(os.path.join(out, "probe.raw"))
    print(f"{run} probe: {'ok' if ok else 'FAILED'} ({time.time() - t:.0f} s)", flush=True)
    return ok


if __name__ == "__main__":
    sys.exit(0 if all([probe(r) for r in sys.argv[1:]]) else 1)
