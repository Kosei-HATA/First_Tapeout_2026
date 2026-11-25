#!/usr/bin/env python3
"""VER-09 for the SPI: every frame of tb_spi_r14 replayed through the SPI transition table of
gf180/tapeout/rtl/spec/fsm_spec.py, the register map of regmap.py and CRC-8 (0x07), and compared with what the RTL did.

Per frame the table is walked with the events the master produced: CSF, then one BIT or BYTE per SCLK rising edge
(BYTE on every 8th), then CSR. The conditions come from the frame (rw, smp, addr_ok, last, mid, crc_ok, wr_ok), from a
model kept here (crc_en and the test-key lock, from the committed writes and SOFT_RESET; checked against the RTL),
head from the frame (the copied word is a stored sample, VALID, and no flush came from the copy's cycle to the pop
request's; checked against the FIFO's `held` in the RTL), and busy, which belongs to the registers and the sequencer's
tick, from the RTL at the moment it is used (a command pending when the write commits).
Compared: commit / STATE_ERR / ADDR_ERR / CRC_ERR / FRAME_ERR / the read's ADDR_ERR / the copy / the pop request and
the pop; the outcome of a commit (RANGE_ERR from the legal values, CMD_ERR for an unknown code or a wrong key,
SOFT_RESET, written or not); and every MISO byte (STATUS, data of the expected address, 0x00, CRC, sample bytes;
the bytes after a completed frame, OVF, are 0x00: audit round 43, auditor B, they were compared with nothing).
Also reported: which branches of the SPI table the trace covered (all must be).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/check_spi_trace.py [build/spi_trace.txt]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import fsm_spec as FS  # noqa: E402
import regmap as RM  # noqa: E402

T = FS.SPI["table"]
SMP_BIT = {n: b for n, b, _d in RM.SAMPLE_STATUS if n != "0"}
EMPTY_ZERO = 0xFF & ~sum(1 << SMP_BIT[n] for n in ("OVERRUN", "OVL", "ERR"))   # the empty word's bits that are 0
REGS = {r[0]: r for r in RM.REGS}
SHADOWED = {a for a, r in REGS.items() if any(f["cls"] == "apply" for f in r[4])}
MIRRORS = {a + RM.SHADOW_MIRROR for a in SHADOWED}
DEFINED = set(REGS) | MIRRORS
RO = {a for a, r in REGS.items() if r[2] == "RO"} | MIRRORS
TESTREG = {a for a, r in REGS.items() if r[3]}
ADDR = {r[1]: r[0] for r in RM.REGS}             # from the map (audit round 17, auditor B: they were by hand)
A_CMD, A_KEY, A_IFCFG, A_SAMPLE = (ADDR[n] for n in ("COMMAND", "TEST_KEY", "IF_CFG", "SAMPLE"))
CODES = set(RM.COMMANDS.values())
GUARDED = set(RM.guarded_addrs())             # shadows and timers: refused while a command is pending
SOFT = RM.COMMANDS["SOFT_RESET"]
ST_NAMES = {"IDLE", "HDR", "RREG", "RCRC", "RDONE", "RSMP", "SDONE", "WDAT", "WCRC", "WDONE", "OVF"}
ST = {}                                   # code -> name, from the eeg_spi_slave.sv beside the trace (set in main)


def spi_state_codes(rtl):
    """eeg_spi_slave.sv's S_* codes (audit round 27, auditor C: they were written here by hand, apart from the RTL the
    trace comes from): {code: name}, None unless the 11 names have 11 distinct codes"""
    import re
    got = re.findall(r"\bS_([A-Z]+)\s*=\s*4'd(\d+)", open(rtl, encoding="utf-8").read())
    st = {int(v): n for n, v in got}
    if {n for n, _ in got} != ST_NAMES or len(got) != len(ST_NAMES) or len(st) != len(ST_NAMES):
        return None
    return st


def crc8(bs):
    c = 0
    for b in bs:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def illegal(addr, val):
    for f in REGS[addr][4]:
        if f["legal"] is None:
            continue
        v = (val >> f["lsb"]) & ((1 << (f["msb"] - f["lsb"] + 1)) - 1)
        if v not in f["legal"]:
            return True
    return False


def parse(line):
    """One frame of the trace; a value that is not a number (X or Z from the RTL) goes to d["unknown"]."""
    f = line.split()
    d = {"idx": int(f[1]), "tag": f[2], "unknown": []}
    for kv in f[3:]:
        k, v = kv.split("=", 1)
        d[k] = v
    try:
        d["loads"] = [tuple(x.split(":")) for x in d["loads"].split(",") if x]
        d["loads"] = [(int(s), int(a, 16), int(v, 16)) for s, a, v in d["loads"]]
    except ValueError:
        d["unknown"].append("loads")
        d["loads"] = []
    for k, base in [(k, 10) for k in ("crc", "cls", "nbits", "we", "wok", "soft", "sserr", "busy", "unl", "ferr", "cerr",
                                      "aerr", "snap", "preq", "head", "fl", "pop", "nsoft")] + \
                   [(k, 16) for k in ("st", "wa", "wd", "ev", "sw")]:
        try:
            d[k] = int(d[k], base)
        except ValueError:
            d["unknown"].append(f"{k}={d[k]}")
            d[k] = 0
    for k in ("tx", "rx"):
        try:
            d[k] = bytes.fromhex(d[k])
        except ValueError:
            d["unknown"].append(f"{k}={d[k]}")
            d[k] = b""
    return d


VER02_KINDS = ("write", "command", "read", "burst read", "sample read", "CRC on", "CRC off", "wrong length",
               "CS_N mid-byte", "undefined address", "write to read-only", "wrong key")
VER02_MIN = 3                                        # frames per (kind, timing) pair (audit round 24, auditor C)


def ver02_kinds(rw, addr, data, nbits, acts, state_at_csr, exp_bytes, crc_en, crc_ok):
    """The VER-02 kinds a frame is (requirements VER-02: every kind of frame, burst reads, CRC on and off, wrong
    lengths, CS_N rising mid-byte, undefined addresses, writes to read-only registers, wrong keys), from what the
    table walk made of it. The write-like kinds count only frames that reach WDONE with a valid CRC; CRC on and off,
    CS_N mid-byte (a rise inside the header too) and wrong length count every frame; the others only frames with a
    complete header (audit round 24, auditor C: a frame without a header counted as a write to ID, a read-only
    register, and a key write that failed its CRC as a wrong key; round 26, auditor C: this text said all others)."""
    k = {"CRC on" if crc_en else "CRC off"}
    if nbits % 8:
        k.add("CS_N mid-byte")
    elif "FRAME_ERR" in acts:
        k.add("wrong length")
    if nbits < 8:
        return k
    if addr not in DEFINED:
        k.add("undefined address")
    if not rw and state_at_csr == "WDONE" and (not crc_en or crc_ok):
        k.add("command" if addr == A_CMD else "write")
        if addr in RO:
            k.add("write to read-only")
        if addr == A_KEY and data not in (RM.TEST_KEY, 0):
            k.add("wrong key")
    # the data bytes the host clocked out (with CRC off the chip loads the next address after every byte, a prefetch the
    # host does not read: counted, a two-byte read was a burst; audit round 24)
    ndata = sum(1 for x in exp_bytes[:nbits // 8] if x[0] == "data")
    if rw and addr != A_SAMPLE and "FRAME_ERR" not in acts and ndata:
        k.add("burst read" if ndata > 1 else "read")
    if rw and addr == A_SAMPLE and state_at_csr == "SDONE":
        k.add("sample read")
    return k


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "build", "spi_trace.txt")
    rtl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "eeg_spi_slave.sv")
    if not os.path.exists(rtl):
        rtl = os.path.join(HERE, "..", "eeg_spi_slave.sv")
    st = spi_state_codes(rtl)
    if st is None:
        print(f"checker error: {rtl}: the SPI's 11 state names without 11 distinct 4'd codes")
        return 2
    ST.update(st)
    model = {"crc": 0, "unl": 0}
    bad, nfr, covered, n_ovf = [], 0, set(), 0
    kc = {}                                          # (VER-02 kind, SCLK class) -> frames (audit round 23, C)
    allb = {(s, e, i) for (s, e), cell in T.items() if isinstance(cell, list) for i in range(len(cell))}
    for line in open(path):
        if not line.startswith("F "):
            continue
        fr = parse(line)
        nfr += 1
        errs = []
        if fr["unknown"]:                            # X or Z out of the RTL: a mismatch by itself
            bad.append((fr["idx"], fr["tag"], line.strip()[:160], ["unknown (X/Z) values: " + ", ".join(fr["unknown"])]))
            continue
        tx, rx, nbits = fr["tx"], fr["rx"], fr["nbits"]
        if fr["crc"] != model["crc"]:
            errs.append(f"CRC_EN {fr['crc']} in the RTL, {model['crc']} by the committed writes")
        hdr = tx[0] if tx else 0
        rw, addr = hdr >> 7, hdr & 0x7F
        env = {"rw": rw, "smp": int(addr == A_SAMPLE), "addr_ok": int(addr in DEFINED), "crc_en": model["crc"],
               "last": 0, "mid": int(nbits % 8 != 0), "crc_ok": 0, "wr_ok": 0, "busy": 0,
               "head": int(bool(fr["sw"] >> 47 & 1) and fr["snap"] == 1 and fr["fl"] == 0)}
        if len(tx) >= 3:
            env["crc_ok"] = int(tx[2] == crc8(tx[:2]))
        env["wr_ok"] = int(addr in DEFINED and addr not in RO and (addr not in TESTREG or model["unl"]))
        data = tx[1] if len(tx) >= 2 else None
        if data is not None and ((addr == A_CMD and data in CODES and data != SOFT) or addr in GUARDED):
            env["busy"] = fr["busy"]
        # walk the table
        state, acts, exp_bytes = "IDLE", [], []      # exp_bytes[j]: expectation for MISO byte j
        state_at_csr = None
        nbyte, smp_k, rd_addr = 0, 0, addr
        events = ["CSF"] + ["BYTE" if n % 8 == 0 else "BIT" for n in range(1, nbits + 1)] + ["CSR"]
        for e in events:
            if e == "BYTE" and state == "RSMP":
                env["last"] = int(smp_k == 6)
            if e == "CSR":
                state_at_csr = state
            cell = T[(state, e)]
            if cell == FS.IMP:
                errs.append(f"impossible event {e} in {state}")
                break
            if cell == FS.IGN:
                if e == "BYTE" and state == "OVF":   # a byte after a completed frame: MISO 0x00 (audit round 43,
                    nbyte += 1                          # auditor B: OVF's 0 was checked by nothing; a copy sending
                    exp_bytes.append(("zero", "ovf"))  # 0xA5 there passed tb_spi_r14 and tb_top_r14)
                continue
            b = FS.pick(cell, env)
            covered.add((state, e, cell.index(b)))
            a = b["actions"]
            acts += a
            if e == "CSF":
                exp_bytes.append(("status",))
            if e == "BYTE":
                nbyte += 1
                if "snapshot" in a:
                    exp_bytes.append(("smp", 0))
                elif "load_data" in a:
                    if "addr_inc" in a:
                        rd_addr = (rd_addr + 1) & 0x7F
                    exp_bytes.append(("data", rd_addr))
                elif "load_zero" in a:
                    exp_bytes.append(("zero",))
                elif "load_crc" in a:
                    exp_bytes.append(("crc_rd",))
                elif "next_byte" in a:
                    smp_k += 1
                    exp_bytes.append(("smp", smp_k))
                else:
                    exp_bytes.append(("zero",))
            if b["next"] is not None:
                state = b["next"]
        # --- actions against the RTL
        commit = "commit" in acts
        w_state = "STATE_ERR" in acts
        w_addr = "ADDR_ERR" in acts and not rw
        r_addr = "ADDR_ERR" in acts and rw
        exp_we = commit or w_state or w_addr
        if fr["we"] != int(exp_we):
            errs.append(f"commit pulses {fr['we']}, expected {int(exp_we)} (actions {acts})")
        ev_addr, ev_range, ev_cmd = bool(fr["ev"] & 0x08), bool(fr["ev"] & 0x10), bool(fr["ev"] & 0x80)
        ev_state = bool(fr["ev"] & 0x40) and not fr["sserr"]
        if exp_we and fr["we"] == 1:
            if fr["wa"] != addr or fr["wd"] != data:
                errs.append(f"committed 0x{fr['wa']:02x} = 0x{fr['wd']:02x}, frame 0x{addr:02x} = {data}")
            if w_addr != ev_addr:
                errs.append(f"ADDR_ERR {ev_addr}, expected {w_addr}")
            if w_state != ev_state:
                errs.append(f"STATE_ERR {ev_state}, expected {w_state}")
            if commit:
                e_range = addr in REGS and illegal(addr, data)
                e_cmd = (addr == A_CMD and data not in CODES) or (addr == A_KEY and data not in (RM.TEST_KEY, 0))
                e_soft = addr == A_CMD and data == SOFT
                e_wok = not e_range and not (addr == A_CMD and (data not in CODES or data == SOFT))
                for nm, got, want in (("RANGE_ERR", ev_range, e_range), ("CMD_ERR", ev_cmd, e_cmd),
                                      ("SOFT_RESET", bool(fr["soft"]), e_soft), ("written", bool(fr["wok"]), e_wok)):
                    if got != want:
                        errs.append(f"commit of 0x{addr:02x} = 0x{data:02x}: {nm} {got}, expected {want}")
                if fr["unl"] != model["unl"]:
                    errs.append(f"test key {fr['unl']} in the RTL, {model['unl']} by the committed writes")
                # the model
                if e_soft:
                    model = {"crc": 0, "unl": 0}
                elif e_wok and addr == A_IFCFG:
                    model["crc"] = data & 1
                elif e_wok and addr == A_KEY:
                    model["unl"] = int(data == RM.TEST_KEY)
            elif w_state and fr["wok"]:
                errs.append("written although a command is pending")
        if fr["nsoft"] != int(commit and addr == A_CMD and data == SOFT):
            errs.append(f"SOFT_RESET pulses {fr['nsoft']}")
        exp_req = int(state_at_csr == "SDONE")       # the SPI asks the FIFO at SDONE / CSR; `head` decides
        if exp_req and fr["preq"] == 1 and fr["head"] != env["head"]:
            errs.append(f"the FIFO's held {fr['head']}, head from the frame {env['head']} (VALID "
                        f"{fr['sw'] >> 47 & 1}, flushes after the copy {fr['fl']})")
        if fr["preq"] != exp_req:
            errs.append(f"pop request {fr['preq']}, expected {exp_req}")
        for nm, got, want in (("FRAME_ERR", fr["ferr"], int("FRAME_ERR" in acts)),
                              ("CRC_ERR", fr["cerr"], int("CRC_ERR" in acts)),
                              ("read ADDR_ERR", fr["aerr"], int(r_addr)),
                              ("copy", fr["snap"], int("snapshot" in acts)),
                              ("pop", fr["pop"], int("pop" in acts))):
            if got != want:
                errs.append(f"{nm} {got}, expected {want}")
        # --- MISO bytes
        sbytes = fr["sw"].to_bytes(6, "big")
        if fr["snap"] == 1 and not (sbytes[0] >> SMP_BIT["VALID"]) & 1:   # an empty word (audit round 8): only
            if sbytes[0] & EMPTY_ZERO or any(sbytes[1:]):              # OVERRUN, OVL and ERR may be set
                errs.append(f"empty word {fr['sw']:012x}: VALID, CHANGED and the reserved bits, SEQ and DATA must be 0")
        loads = fr["loads"]
        for j, x in enumerate(exp_bytes[:len(rx)]):
            got = rx[j]
            if x[0] == "status":
                want = fr["st"]
                if (want >> 6) != 0b10:
                    errs.append(f"STATUS 0x{want:02x} without the fixed bits")
            elif x[0] == "zero":
                want = 0
            elif x[0] == "crc_rd":
                want = crc8([tx[0], rx[j - 1]])
            elif x[0] == "smp":
                want = sbytes[x[1]] if x[1] < 6 else crc8([0x80 | A_SAMPLE] + list(sbytes))   # the header 0xC0, 6 bytes
            elif x[0] == "data":
                ld = loads[j - 1] if j - 1 < len(loads) else None
                if ld is None or ST[ld[0]] != "RREG" or ld[1] != x[1]:
                    errs.append(f"byte {j}: loaded {ld}, expected a register read of 0x{x[1]:02x}")
                    continue
                want = ld[2]
            if got != want:
                errs.append(f"MISO byte {j} ({x[0]}): 0x{got:02x}, expected 0x{want:02x}")
            if x == ("zero", "ovf"):
                n_ovf += 1
        for k in ver02_kinds(rw, addr, data, nbits, acts, state_at_csr, exp_bytes, env["crc_en"], env["crc_ok"]):
            kc[(k, fr["cls"])] = kc.get((k, fr["cls"]), 0) + 1
        if errs:
            bad.append((fr["idx"], fr["tag"], line.strip()[:160], errs))
    print(f"{nfr} frames replayed through fsm_spec SPI: {len(bad)} frames with mismatches; "
          f"table branches covered {len(covered & allb)} of {len(allb)}; MISO bytes after a completed frame (OVF) "
          f"compared {n_ovf}")
    for idx, tag, ln, errs in bad[:15]:
        print(f"  frame {idx} ({tag}): {'; '.join(errs[:4])}")
        print(f"    {ln}")
    missing = sorted(allb - covered)
    if missing:
        print("  not covered: " + ", ".join(f"{s}/{e}#{i}" for s, e, i in missing))
    # VER-02 (audit round 23, auditor C): every kind of frame at each of the 4 SCLK timings (2 MHz, 1 MHz, the
    # minimum high, the minimum low); the bench counted draws, and a stimulus change could drop a pair silently
    holes = [(k, c) for k in VER02_KINDS for c in range(4) if kc.get((k, c), 0) < VER02_MIN]
    per_cls = [sum(n for (k, c), n in kc.items() if c == cc and k in ("CRC on", "CRC off")) for cc in range(4)]
    fewest = min((kc.get((k, c), 0), k, c) for k in VER02_KINDS for c in range(4))
    print(f"VER-02: {len(VER02_KINDS)} kinds x 4 SCLK timings, frames per timing {'/'.join(map(str, per_cls))}; "
          f"fewest {fewest[0]} ({fewest[1]} at timing {fewest[2]})")
    if holes:
        print(f"  VER-02 pairs sent fewer than {VER02_MIN} times: " + ", ".join(f"{k} at timing {c} "
              f"({kc.get((k, c), 0)})" for k, c in holes))
    ok = nfr > 0 and not bad and not missing and not holes and n_ovf > 0
    print("PASS: SPI RTL == specification on every frame, every branch covered, every VER-02 kind at every SCLK "
          "timing" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
