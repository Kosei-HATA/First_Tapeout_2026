#!/usr/bin/env python3
"""clkcheck.py <dir with the r14 RTL and rtl/ blocks>: yosys as check_outputs_registered.py, then every flip-flop and
memory write port must be clocked by MCLK's rising edge (the proposed RST-05 check)."""
import json, os, subprocess, sys, tempfile
d = sys.argv[1]
SPEC = sys.argv[2]
YOSYS = "/nix/store/0inxmdvzndxxzsiyjrfjzslay6qllx96-yosys-0.69/bin/yosys"
files = [os.path.join(d, f) for f in ("eeg_digital_top.sv", "eeg_seq.sv", "eeg_regs.sv", "eeg_spi_slave.sv", "eeg_fifo.sv",
                                      "eeg_ovl.sv", "eeg_cic3.sv", "eeg_clkgen.sv", "eeg_chop1.sv", "eeg_raw.sv", "eeg_rnd_sat.sv")]
with tempfile.TemporaryDirectory() as t:
    js = os.path.join(t, "top.json")
    subprocess.run([YOSYS, "-q", "-p", f"read_verilog -sv -I{SPEC} {' '.join(files)}; hierarchy -top eeg_digital_top; "
                    f"proc; flatten; opt_clean; opt -purge; write_json {js}"], check=True)
    m = json.load(open(js))["modules"]["eeg_digital_top"]
mclk = m["ports"]["MCLK"]["bits"][0]
names = {b: n for n, v in m["netnames"].items() for b in v["bits"] if isinstance(b, int)}
bad, n = [], 0
for cn, c in m["cells"].items():
    if "dff" in c["type"] or c["type"].startswith("$memwr"):
        n += 1
        clk = c["connections"].get("CLK", [None])[0]
        pol = str(c["parameters"].get("CLK_POLARITY", "1")).lstrip("0") or "0"
        if clk != mclk or pol != "1":
            bad.append(f"{c['type']} {names.get(c['connections'].get('Q', [None])[0], cn)}: clock {names.get(clk, clk)}"
                       f"{'' if pol == '1' else ' (falling edge)'}, not MCLK's rising edge")
print(f"{n} flip-flop / memory-write cells: {len(bad)} not on MCLK's rising edge")
for b in bad:
    print("  " + b)
sys.exit(1 if bad else 0)
