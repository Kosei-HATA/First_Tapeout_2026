#!/usr/bin/env python3
"""Run the ideal / PEX-v1(broken) / PEX-v2(fixed) simulations of
1samp_opamp_adc and produce a 3-way comparison plot.

Steps:
  1. netlist xschem/1samp_opamp_adc.sch (ideal) and xschem/1samp_opamp_adc_pex.sch
     via the headless xschem CLI
  2. derive a v1 deck by pointing the PEX testbench at the archived v1 PEX
     netlist (xschem/opamp_adc_pex_v1_l015.spice, all devices L=0.15um)
  3. run ngspice (ac + tran) for the three variants
  4. write xschem/1samp_opamp_adc_pex_vs_ideal.png and print a metric table

Usage: python3 lvs_work/run_pex_compare.py
"""
import os
import re
import subprocess
import sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = os.path.join(ROOT, "lvs_work", "run")
os.makedirs(RUN, exist_ok=True)

XSCHEM = "/Users/noah/xschem/src/xschem"
RCFILE = os.path.join(ROOT, "xschem", "xschemrc")
XSCH_DIR = os.path.join(ROOT, "xschem")


def netlist(sch):
    """Headless xschem netlisting (src-tree build skips ./xschemrc -> --rcfile;
    Tcl_Main reads stdin without X, so pipe 'exit')."""
    subprocess.run(
        f"echo 'exit' | {XSCHEM} --no_x --rcfile {RCFILE} --netlist "
        f"--netlist_path {RUN} {sch}",
        shell=True, cwd=XSCH_DIR, check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.join(RUN, os.path.splitext(sch)[0] + ".spice")


CONTROL = {
    "ac": ".control\nop\nac dec 20 1 1GHz\nwrite {stem}_ac.raw\n.endc\n",
    "tran": ".control\nop\ntran 10u 30m\nwrite {stem}_tran.raw\n.endc\n",
}


def make_decks():
    decks = {}
    ideal = netlist("1samp_opamp_adc.sch")
    decks["ideal"] = open(ideal).read()
    pex = netlist("1samp_opamp_adc_pex.sch")
    pex_text = open(pex).read()
    decks["pex_v2"] = pex_text
    decks["pex_v1"] = pex_text.replace(
        "opamp_adc_pex.spice", "opamp_adc_pex_v1_l015.spice")
    for stem, text in decks.items():
        body = re.sub(r"\.control.*?\.endc", "", text, flags=re.S)
        for kind, ctl in CONTROL.items():
            path = os.path.join(RUN, f"{stem}_{kind}.spice")
            with open(path, "w") as f:
                f.write(body + "\n" + ctl.format(stem=stem))
    return list(decks)


def run_ngspice(stems):
    for stem in stems:
        for kind in CONTROL:
            tag = f"{stem}_{kind}"
            r = subprocess.run(["ngspice", "-b", tag + ".spice"], cwd=RUN,
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"{tag} FAILED:\n{r.stdout[-2000:]}", file=sys.stderr)
                sys.exit(1)
    print("ngspice runs OK:", ", ".join(stems))


# ---------------- raw parsing ----------------

def read_raw(path):
    plots = []
    data = open(path, "rb").read()
    pos = 0
    while pos < len(data):
        hdr_end = data.index(b"Binary:\n", pos)
        header = data[pos:hdr_end].decode("ascii", "replace")
        plotname, flags = "", ""
        nvars = npts = 0
        varnames = []
        in_vars = False
        for ln in header.splitlines():
            if ln.startswith("Plotname:"):
                plotname = ln.split(":", 1)[1].strip()
            elif ln.startswith("Flags:"):
                flags = ln.split(":", 1)[1].strip()
            elif ln.startswith("No. Variables:"):
                nvars = int(ln.split(":", 1)[1])
            elif ln.startswith("No. Points:"):
                npts = int(ln.split(":", 1)[1])
            elif ln.startswith("Variables:"):
                in_vars = True
            elif in_vars and ln.strip():
                parts = ln.split()
                if len(parts) >= 2:
                    varnames.append(parts[1])
        start = hdr_end + 8
        cplx = "complex" in flags
        rec = 2 if cplx else 1
        count = nvars * npts * rec
        arr = np.frombuffer(data[start:start + 8 * count], dtype="<f8")
        arr = arr.reshape(npts, nvars, rec) if cplx else arr.reshape(npts, nvars)
        out = {}
        for i, v in enumerate(varnames):
            out[v] = (arr[:, i, 0] + 1j * arr[:, i, 1]) if cplx else arr[:, i]
        plots.append((plotname, out))
        pos = start + 8 * count
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
    return dict(plots)


def metrics(stem):
    ac = read_raw(os.path.join(RUN, f"{stem}_ac.raw"))["AC Analysis"]
    tr = read_raw(os.path.join(RUN, f"{stem}_tran.raw"))["Transient Analysis"]
    f = np.real(ac["frequency"])
    mag = 20 * np.log10(np.abs(ac["v(vout)"]))
    g0 = float(mag[0])
    g = 10 ** (g0 / 20)
    a0db = 20 * np.log10(g / (1 - g / 100)) if g < 100 else float("inf")
    below = np.where(mag < g0 - 3)[0]
    f3 = float(f[below[0]]) if len(below) else float(f[-1])
    t, vo, do = tr["time"], tr["v(vout)"], tr["v(dout)"]
    m = t > t[-1] - 20e-3
    vpp = float(vo[m].max() - vo[m].min())
    vdc = float(vo[m].mean())
    sw = int(np.sum(np.abs(np.diff(do[m])) > 0.2))
    return dict(f=f, mag=mag, t=t[m], vo=vo[m], do=do[m],
                g0=g0, a0db=a0db, f3=f3, vpp=vpp, vdc=vdc, sw=sw)


def main():
    stems = make_decks()
    run_ngspice(stems)
    res = {s: metrics(s) for s in stems}

    labels = {"ideal": "IDEAL (schematic, L=0.5um)",
              "pex_v1": "PEX v1 (layout, all L=0.15um)",
              "pex_v2": "PEX v2 (layout, stack=3 -> L=0.45um)"}
    print(f"\n{'variant':<34} {'A0[dB]':>7} {'Gcl[dB]':>8} {'BW[Hz]':>10} "
          f"{'Vpp[mV]':>8} {'Vdc[V]':>7} {'Dout sw':>8}")
    for s in stems:
        r = res[s]
        print(f"{labels[s]:<34} {r['a0db']:7.1f} {r['g0']:8.1f} {r['f3']:10.2e} "
              f"{r['vpp'] * 1e3:8.1f} {r['vdc']:7.3f} {r['sw']:8d}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(9, 11))
    for s in stems:
        r = res[s]
        ax[0].semilogx(r["f"], r["mag"],
                       label=f"{labels[s]} (G={r['g0']:.0f} dB)")
    ax[0].set_ylabel("|Vout/Vi| [dB]")
    ax[0].set_xlabel("Frequency [Hz]")
    ax[0].set_title("Closed-loop AC response")
    ax[0].grid(True, which="both", alpha=0.3)
    ax[0].legend()
    for s in stems:
        r = res[s]
        ax[1].plot(r["t"] * 1e3, r["vo"], label=labels[s])
    ax[1].axhline(0.9, color="k", ls="--", lw=0.8, label="comparator threshold 0.9V")
    ax[1].set_ylabel("Vout [V]")
    ax[1].set_xlabel("time [ms]")
    ax[1].set_title("Op-amp output (last 2 periods, 100 Hz input)")
    ax[1].grid(True, alpha=0.3)
    ax[1].legend()
    for i, s in enumerate(stems):
        r = res[s]
        ax[2].plot(r["t"] * 1e3, r["do"] + 0.05 * i, label=labels[s],
                   drawstyle="steps-post")
    ax[2].set_ylabel("Dout [V]")
    ax[2].set_xlabel("time [ms]")
    ax[2].set_title("1-bit ADC output")
    ax[2].set_ylim(-0.2, 2.2)
    ax[2].grid(True, alpha=0.3)
    ax[2].legend()
    fig.tight_layout()
    out_png = os.path.join(XSCH_DIR, "1samp_opamp_adc_pex_vs_ideal.png")
    fig.savefig(out_png, dpi=110)
    print("wrote", out_png)


if __name__ == "__main__":
    main()
