# CRC-off operation: a host write [a, v] whose header loses/gains one bit (a' = a ^ (1<<b), b = 0..6) is committed
# by eeg_regs at a' with data v. Silent = no flag (a' writable, not RO/undefined/locked, value legal). Model of
# eeg_regs.sv's decode (key locked, no command pending).
RO = {0x00,0x01,0x02,0x03,0x04,0x05,0x0A,0x0B,0x0C,0x40} | set(range(0x30,0x39)) | {0x70,0x71}
LOCKED = {0x60,0x61,0x62}
NAMES = {0x06:"ERR",0x07:"DFLAG",0x08:"ALERT_MASK",0x09:"ALERT_MASK_D",0x10:"COMMAND",0x11:"TEST_KEY",
         0x20:"OFF_M_H",0x21:"OFF_M_L",0x22:"OFF_CTRL",0x23:"AFE_IBIAS",0x24:"CPF_TRIM",0x25:"BOOST_TRIM",
         0x26:"CHOP_CFG",0x27:"ADC_CFG",0x28:"BLANK",0x50:"T_WARM",0x51:"T_ELEC",0x52:"T_REC",0x53:"T_PRE",
         0x54:"T_RST",0x55:"IF_CFG",0x60:"TEST_MUX",0x61:"TEST_CTRL",0x62:"DEBUG"}
CODES = {0x11,0x22,0x33,0x44,0x55}
def commit(a, v):
    if a not in NAMES or a in RO: return "ADDR_ERR"
    if a in LOCKED: return "ADDR_ERR(locked)"
    if a == 0x22 and (v & 7) > 4: return "RANGE_ERR"
    if a == 0x28 and (v & 15) < 1: return "RANGE_ERR"
    if a == 0x27 and (v & 7) > 5: return "RANGE_ERR"
    if a == 0x50 and v < 5: return "RANGE_ERR"
    if a == 0x52 and v < 29: return "RANGE_ERR"
    if a == 0x53 and v < 3: return "RANGE_ERR"
    if a == 0x54 and v < 13: return "RANGE_ERR"
    if a == 0x10:
        return "SOFT_RESET" if v == 0xA5 else ("command" if v in CODES else "CMD_ERR")
    if a == 0x11: return "unlock" if v == 0x3C else ("lock" if v == 0 else "lock+CMD_ERR")
    return "SILENT write %s := 0x%02X" % (NAMES[a], v)
host = [(0x06,0x02,"step 6/8: ERR write-back FRAME_ERR"),(0x06,0x08,"bracket (5): ERR write-back ADDR_ERR"),
        (0x07,0x02,"step 8: DFLAG write-back OVL"),(0x07,0x01,"step 8: DFLAG write-back OVERRUN"),
        (0x11,0x3C,"bracket (1) unlock"),(0x11,0x00,"bracket (4) lock"),(0x61,0x00,"bracket (5) probe"),
        (0x21,0x28,"step 7: OFF_M_L"),(0x22,0x01,"step 7: OFF_CTRL range 1"),(0x51,0x0C,"step 7: T_ELEC 12 ms")]
for a, v, what in host:
    out = []
    for b in range(7):
        r = commit(a ^ (1 << b), v)
        if r.startswith("SILENT"): out.append("0x%02X: %s" % (a ^ (1 << b), r[7:]))
    print("%-40s [0x%02X,0x%02X] -> %s" % (what, a, v, "; ".join(out) if out else "no silent alias"))
