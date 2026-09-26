#!/usr/bin/env python3
"""GF180MCU macro size outlook: per-component area estimate.
FET footprints measured from PDK pcells (measure_footprints.py output);
MIM at 2.04 fF/um2 (measured on extracted cap_mim_2f0_m4m5, 20x20 -> 815 fF);
resistors: area = R*w^2/rho with ppolyf_u_high_Rs (3k ohm/sq) / ppolyf_u (350).
Run: python3 gf180/size_estimate.py  (prints markdown table)
"""

MIM_F = 2.0e-15  # F/um2, measured 2.04


def mim(cap_pf, n=1):
    area = cap_pf * 1e-12 / MIM_F * n
    return area * 1.12  # array border/tab overhead (measured on 20x20 pcell)


def res(R, n=1, rho=3000.0, w=1.0):
    return R * w * w / rho * n


rows = []


def row(comp, detail, area_um2):
    rows.append((comp, detail, area_um2))


# ---------------- PGA (chopped AFE) ----------------
fet = {
    "s1 input pair nfet 120/4 nf12 x2": 6707.7 * 2,
    "s1 loads pfet 48/4 nf4 x2": 1008.8 * 2,
    "s1 tail nfet 48/4 nf8": 1835.4,
    "s2 pair nfet 4/20 x2": 115.1 * 2,
    "s2 loads pfet 12/4 nf2 x2": 157.2 * 2,
    "bias gen (2x pfet 10/4, nfet 10/4, nfet 40/4)": 135.1 * 3 + 1537.8,
    "CMFB x2 + choppers 8xTG + pseudo-res x2": 2 * 130 + 8 * 30 + 2 * 30,
}
pga_fet = sum(fet.values())
row("PGA FETs", "; ".join(f"{k}" for k in list(fet)[:2]) + " ...", pga_fet)
pga_mim = mim(32, 2) + mim(12) + mim(10, 2) + mim(100) + mim(50)
row("PGA MIM caps", "CIN 32p x2, CFB bank ~12p, CC 10p x2, CFILT 100p, CINT 50p",
    pga_mim)
pga_res = res(20e6, 4) + res(5e6, 4) + res(10e6) + res(80e3, 2, rho=350, w=0.5) \
    + res(40e3)
row("PGA poly resistors", "RLOAD 20Meg x4, RCM(O) 5Meg x4, RFILT 10Meg, RZ, RSET",
    pga_res)

# ---------------- CT SDM ADC ----------------
adc_fet = 20000.0  # second full2-class OTA + strongarm + nand2, same class
row("ADC FETs", "full2-class OTA + strongarm + SR latch + DAC TGs", adc_fet)
adc_mim = mim(20, 2) + mim(1, 2) + mim(150)
row("ADC MIM caps", "CI 20p x2, CQ 1p x2, bias filter/CINT ~150p", adc_mim)
adc_res = res(500e3, 4) + res(20e6, 2) + res(10e6)
row("ADC poly resistors", "RIN/RDAC 500k x4, CM loads, RFILT", adc_res)

# ---------------- support ----------------
sup_fet = 3000.0
row("clkgen analog part + level shifts", "analog buffers/level shifts to pads",
    sup_fet)
sup_mim = mim(60)
row("clkgen/misc MIM", "~60 pF", sup_mim)

analog_total = pga_fet + pga_mim + pga_res + adc_fet + adc_mim + adc_res \
    + sup_fet + sup_mim

# ---------------- digital (SPI + CIC + clkgen) ----------------
# Cell areas measured from gf180mcu_fd_sc_mcu9t5v0 LEF (installed PDK):
#   NAND2_1 = 2.80 x 5.04 = 14.1 um2, DFFQ_1 = 15.68 x 5.04 = 79.0 um2.
FF_AREA = 79.0
GATE_AREA = 14.1  # NAND2_1 equivalent

# CIC sinc3 (cic_decimator.sv, ACCW=32): 3 int + 7 comb regs + 24b out + cnt
#   ~ 351 FF; 6x 32-bit add/sub + scaling ~ 1200 gates
cic_ff, cic_gates = 351, 1200
# clkgen (eeg_clkgen.sv): div1k/div16k counters + phase decode ~ 30 FF, 150 g
clkgen_ff, clkgen_gates = 30, 150
# SPI slave (new RTL, process-independent): 32b shift reg, config regs
# (gain x8/16/32/64, RST, future chop/decimation), CIC readout FSM/mux
#   ~ 120 FF, 400 gates
spi_ff, spi_gates = 120, 400

dig_rows = [
    ("digital: CIC decimator (sinc3, 24b out)", cic_ff, cic_gates),
    ("digital: clkgen (256k->1k chop + 16k SDM)", clkgen_ff, clkgen_gates),
    ("digital: SPI slave (regs + CIC readout, NEW)", spi_ff, spi_gates),
]
UTIL = 0.5  # place-and-route utilization


def dig_area(ff, gates):
    return (ff * FF_AREA + gates * GATE_AREA) / UTIL


dig = 0.0
for name, ff, gates in dig_rows:
    a = dig_area(ff, gates)
    dig += a
    row(name, f"{ff} FF + ~{gates} gates (9t5v0, {UTIL:.0%} util)", a)

print("| block | detail | area (mm2) |")
print("|---|---|---|")
for comp, detail, a in rows:
    print(f"| {comp} | {detail} | {a/1e6:.3f} |")
print(f"| **analog subtotal** | | **{analog_total/1e6:.3f}** |")
print(f"| **digital subtotal (SPI+CIC+clkgen)** | ~{cic_ff+clkgen_ff+spi_ff} FF"
      f" + ~{cic_gates+clkgen_gates+spi_gates} gates | **{dig/1e6:.3f}** |")
core = analog_total + dig
print(f"| **electronics total** | | **{core/1e6:.3f}** |")
for ovh in [2.0, 3.0]:
    print(f"| macro estimate (x{ovh:.0f} routing/whitespace) | | "
          f"{core*ovh/1e6:.2f} |")
