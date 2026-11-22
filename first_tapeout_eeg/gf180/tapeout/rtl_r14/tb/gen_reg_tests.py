#!/usr/bin/env python3
"""Register tests for tb_top_r14, generated from the specification (gf180/tapeout/rtl/spec/regmap.py), not from
the RTL: writes build/reg_tests.svh with the task run_reg_tests(), which uses the testbench's rt_* tasks.

  1. every address 0x00..0x7F read once after reset: defined ones give the reset value of the map (the active
     copies the same as their shadows), undefined ones 0x00 and ADDR_ERR
  2. every writable field: its minimum, maximum and a middle value, written with the other fields at reset
     and the reserved bits set (they must read 0); the active copy unchanged (no APPLY); every value of the field's
     width outside its legal values (audit round 15, auditor C: only the minimum - 1 and the maximum + 1, and a range
     check decoded by hand that let RANGE 6 through passed every test), with every other field changed to another
     legal value -> RANGE_ERR and nothing written (the register still holds the last legal value); the reset value
     restored. The write-only COMMAND and TEST_KEY read 0x00 (alone and in a burst) while unlocked and after a
     committed command, not only at reset (audit round 15, auditor C)
  3. the test registers (every one): without the key ADDR_ERR and nothing written; with the key as 2.; locked again,
     each refused again (audit round 7: only DEBUG before the key and TEST_MUX after were written locked); each
     holding another legal value than its reset value across the lock reads it while locked, and a locked write
     of its reset value is refused (REG-08 locks the writes only; audit round 19, auditor C: the locked reads met
     only the reset value 0x00, so test registers reading 0x00 while locked passed all 16 groups)
  2b. independence (audit round 23, auditor C): every writable register but IF_CFG given a legal byte away from
     its reset value in ascending, descending and a shuffled address order, each round followed by one burst
     read of the whole map: each register as written, the active copies at reset (an OFF_M_H write clearing
     M[7:0] and an OFF_M_L write clearing SIGN passed all 16 groups)
  2c. aliasing (audit round 28, auditor C): rounds of random legal bytes for every writable register (IF_CFG
     included, CRC_EN kept 0; reserved bits random), ascending and descending, a burst read of the map each, drawn
     until every single-bit alias between two writable registers is visible (a write to A loading one of its bits
     into, clearing or setting a bit of B written before it), every bit both 0 and 1
  2d. the command codes and the key as data (audit round 28, auditor C): each of them written to every address but
     COMMAND: written or refused as the map says, ERR exactly (never RESET_FLAG), no SOFT_RESET and no command
  5. also guard_code: SOFT_RESET's code written to every guarded register while FLUSH waits: exactly STATE_ERR
  4. every read-only register and every undefined address: a write gives ADDR_ERR and changes nothing; STATUS by
     its error only, its value moves (audit round 26, auditor C: no fixed test wrote STATUS)
  5. run_guard_tests (tb_top_r14's J2, at 64 kHz): every register of regmap.guarded_addrs(), written while a FLUSH waits
     for its tick, gives STATE_ERR and is not written (audit round 7: J2 wrote 2 of the 16; a guard that skipped
     OFF_M_H passed every test)
  6. run_free_tests (J2): the writable registers outside the guard, written while a FLUSH waits: no flag and written;
     the key and the lock sent while it waits take effect (audit round 15, auditor C: only their flags were checked)
  7. run_reset_burst (A0 and tb_top_r14's Y): one burst over the whole map and its wrap, the reset values;
     soft_set_all (Y): every writable register away from its reset value (a setting START accepts), the key open,
     IF_CFG last (pulse mode, CRC as asked), for a SOFT_RESET that must return all of it (RST-02; audit round 15,
     auditor C: after a SOFT_RESET only a few registers were read, and an eeg_regs keeping the timers, the ALERT masks,
     DFLAG or DRDY_MODE through it passed all 16 groups)

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/gen_reg_tests.py
"""
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "rtl", "spec"))
import regmap as RM  # noqa: E402

OUT = os.path.join(HERE, "..", "build", "reg_tests.svh")
A_ERR, A_KEY = 0x06, 0x11
E_ADDR, E_RANGE = 0x08, 0x10
E_CMD = 1 << next(f["lsb"] for r in RM.REGS if r[1] == "ERR" for f in r[4] if f["name"] == "CMD_ERR")   # the wrong key


def reset_byte(fields):
    v = 0
    for f in fields:
        v |= f["reset"] << f["lsb"]
    return v


def caps4(r):
    """CAPS with a 4-deep FIFO."""
    v = 0
    for f in r[4]:
        v |= (4 if f["name"] == "FIFO_DEPTH" else f["reset"]) << f["lsb"]
    return v


def field_mask(f):
    return ((1 << (f["msb"] - f["lsb"] + 1)) - 1) << f["lsb"]


def legal_other(fields, low=False):
    """A legal byte with every field at a legal value other than its reset value where it has one (low: the smallest
    such value, else the largest); a field with a single legal value keeps it."""
    v = 0
    for f in fields:
        alt = [x for x in f["legal"] if x != f["reset"]]
        v |= ((min(alt) if low else max(alt)) if alt else f["reset"]) << f["lsb"]
    return v


def soft_set_all(regs):
    """tb_top_r14's Y (audit round 15, auditor C): every writable register away from its reset value (each field at
    the smallest legal value other than its reset value, so that the timers stay short; the offset DAC's range the
    smallest one above its reset value that holds M, so that START accepts the setting), the test key open, IF_CFG
    last (DRDY_MODE 1, CRC_EN as asked; the bench's BFM follows)."""
    val = {}
    for a, r in sorted(regs.items()):
        if r[2] == "RW":
            for f in r[4]:
                alt = [x for x in f["legal"] if x != f["reset"]]
                val[f["name"]] = min(alt) if alt else f["reset"]
    m = (val["M_H"] << 8) | val["M_L"]
    rng = next(x for x in sorted(regs[0x22][4][1]["legal"]) if x != regs[0x22][4][1]["reset"] and m <= RM.RANGE_MAX_M[x])
    val["RANGE"] = rng
    assert RM.cfg_ok(dict(M=m, RANGE=rng)), "START must accept the setting"
    out = ["task automatic soft_set_all(input bit crc);",
           f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});       // the key stays open: the SOFT_RESET must close it"]
    for a, r in sorted(regs.items()):
        if r[2] != "RW" or r[1] == "IF_CFG":
            continue
        byte = sum(val[f["name"]] << f["lsb"] for f in r[4])
        assert byte != reset_byte(r[4]), r[1]
        out.append(f"    rt_write(7'h{a:02X}, 8'h{byte:02X});          // {r[1]} " +
                   ", ".join(f"{f['name']} {val[f['name']]}" for f in r[4]))
    ifc = next(r for r in regs.values() if r[1] == "IF_CFG")
    dm = next(f for f in ifc[4] if f["name"] == "DRDY_MODE")
    ce = next(f for f in ifc[4] if f["name"] == "CRC_EN")
    out.append(f"    rt_write(7'h{ifc[0]:02X}, 8'h{1 << dm['lsb']:02X} | ({{7'd0, crc}} << {ce['lsb']}));   // IF_CFG: pulse mode, CRC as asked")
    out.append("    bfm_crc_en = crc;")
    out.append("endtask")
    return out


def main():
    regs = {r[0]: r for r in RM.REGS}
    shadowed = {a for a, r in regs.items() if any(f["cls"] == "apply" for f in r[4])}
    mirrors = {a + RM.SHADOW_MIRROR: a for a in shadowed}
    L = ["// GENERATED by gf180/tapeout/rtl_r14/tb/gen_reg_tests.py from gf180/tapeout/rtl/spec/regmap.py",
         "task automatic run_reset_burst(input string tag);"]
    # 0. one burst read at reset over the whole map and its wrap (header 0x80, CRC off): the reset values, 0x00 for
    #    undefined, write-only and the sample window inside a burst; the address after 0x7F is 0x00
    exp = []
    for k in range(136):
        a = k % 0x80
        if a in regs:
            r = regs[a]
            if r[2] == "WO" or a == 0x40:
                exp.append((a, "8'h00", r[1]))
            elif r[1] == "CAPS":
                exp.append((a, None, "CAPS"))
            else:
                exp.append((a, f"8'h{reset_byte(r[4]):02X}", r[1]))
        elif a in mirrors:
            exp.append((a, f"8'h{reset_byte(regs[mirrors[a]][4]):02X}", regs[mirrors[a]][1] + " active"))
        else:
            exp.append((a, "8'h00", "undefined"))
    L.append("    // 0. a burst read of the whole map at reset and across the 0x7F -> 0x00 wrap")
    L.append("    spi_tx[0] = 8'h80;")
    L.append("    for (int i = 1; i <= 136; i++) spi_tx[i] = 8'h00;")
    L.append("    spi_xfer(137, 0);")
    caps = next(r for r in regs.values() if r[1] == "CAPS")
    for k, (a, e, nm) in enumerate(exp):
        if e is None:
            L += ["`ifdef FIFO4", f"    rt_burst_expect({k + 1}, 8'h{caps4(caps):02X}, $sformatf(\"%s: burst 0x{a:02X} CAPS (FIFO 4)\", tag));",
                  "`else", f"    rt_burst_expect({k + 1}, 8'h{reset_byte(caps[4]):02X}, $sformatf(\"%s: burst 0x{a:02X} CAPS\", tag));", "`endif"]
        else:
            L.append(f"    rt_burst_expect({k + 1}, {e}, $sformatf(\"%s: burst 0x{a:02X} {nm}\", tag));")
    L.append("endtask")
    L.append("task automatic run_reg_tests();")
    L.append("    run_reset_burst(\"A0\");")
    # 1. reset values
    L.append("    // 1. reset values, every address")
    undefined = []
    for a in range(0x80):
        if a == 0x40:
            continue                                           # the sample window (tested by the data phase)
        if a in regs:
            r = regs[a]
            if r[2] == "WO":
                L.append(f"    rt_read_expect(7'h{a:02X}, 8'h00, \"{r[1]} (write only)\");")
            elif r[1] == "CAPS":                               # the FIFO depth is chosen at synthesis (4 or 8)
                L += ["`ifdef FIFO4", f"    rt_read_expect(7'h{a:02X}, 8'h{caps4(r):02X}, \"CAPS (FIFO 4)\");", "`else",
                      f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(r[4]):02X}, \"CAPS\");", "`endif"]
            else:
                L.append(f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(r[4]):02X}, \"{r[1]}\");")
        elif a in mirrors:
            r = regs[mirrors[a]]
            L.append(f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(r[4]):02X}, \"{r[1]} active\");")
        else:
            undefined.append(a)
            L.append(f"    rt_read_expect(7'h{a:02X}, 8'h00, \"undefined\");")
    L.append(f"    rt_expect_err(8'h{E_ADDR:02X}, \"reads of undefined addresses\");")
    # 2./3. writable fields
    L.append("    // 2. writable fields (3. the test registers with the key)")
    locked = [(a, r) for a, r in sorted(regs.items()) if r[3]]
    for a, r in locked:                                        # every test register refused without the key
        wv = legal_other(r[4])
        L.append(f"    rt_write_check(7'h{a:02X}, 8'h{wv:02X}, 8'h{reset_byte(r[4]):02X}, 8'h{E_ADDR:02X}, \"{r[1]} without the key\");")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    # the write-only registers read 0x00 while unlocked and after a committed command (audit round 15, auditor C: read
    # only at reset, so a COMMAND reading back its last code and a TEST_KEY reading the lock passed every test), alone
    # and in a burst from FORMAT across them
    wo = [a for a, r in sorted(regs.items()) if r[2] == "WO"]
    b0 = min(wo) - 4                                   # FORMAT (0x0C): a defined header, then 0x0D..0x12
    assert b0 in regs and regs[b0][2] == "RO", "the burst's header must be a defined read-only register"
    cmd_a = next(a for a, r in regs.items() if r[1] == "COMMAND")

    def wo_reads(when):
        out = [f"    rt_read_expect(7'h{a:02X}, 8'h00, \"{regs[a][1]} (write only) {when}\");" for a in wo]
        n = max(wo) + 2 - b0
        out += [f"    spi_tx[0] = 8'h{0x80 | b0:02X};", f"    for (int i = 1; i <= {n}; i++) spi_tx[i] = 8'h00;",
                f"    spi_xfer({n + 1}, 0);"]
        for k in range(n):
            a = b0 + k
            ev = reset_byte(regs[a][4]) if a in regs and regs[a][2] != "WO" else 0
            out.append(f"    rt_burst_expect({k + 1}, 8'h{ev:02X}, \"burst 0x{a:02X} {when}\");")
        return out
    L += wo_reads("while unlocked")
    L.append(f"    rt_write(7'h{cmd_a:02X}, 8'h{RM.COMMANDS['FLUSH']:02X});     // FLUSH in IDLE: empties the FIFO only")
    L.append("    repeat (600) @(posedge MCLK);                     // past its tick at either chopper rate")
    L += wo_reads("after a committed FLUSH")
    L.append("    expect_err_exact(8'h00, \"the write-only reads, the bursts and the FLUSH: no flag\");")
    for a, r in sorted(regs.items()):
        if r[2] != "RW":
            continue
        fields = r[4]
        base = reset_byte(fields)
        used = 0
        for f in fields:
            used |= field_mask(f)
        reserved = 0xFF & ~used
        for f in fields:
            if r[1] == "IF_CFG" and f["name"] == "CRC_EN":
                continue                                       # changes the frame format: the CRC phase tests it
            lg = f["legal"]
            w = f["msb"] - f["lsb"] + 1
            cur = base                                         # what the register holds (the last legal write)
            for v in sorted({min(lg), max(lg), lg[len(lg) // 2]}):
                wb = (base & ~field_mask(f)) | (v << f["lsb"]) | reserved
                eb = (base & ~field_mask(f)) | (v << f["lsb"])
                L.append(f"    rt_write_check(7'h{a:02X}, 8'h{wb:02X}, 8'h{eb:02X}, 8'h00, \"{r[1]}.{f['name']} = {v}\");")
                cur = eb
                if a in shadowed:
                    L.append(f"    rt_read_expect(7'h{a + RM.SHADOW_MIRROR:02X}, 8'h{base:02X}, \"{r[1]} active before APPLY\");")
            bad = [x for x in range(1 << w) if x not in lg]   # every illegal value (audit round 15, auditor C)
            # the rejected byte carries every other field at a legal value different from what the register holds
            # (and the reserved bits set), so a byte written in part shows on the read-back
            other = cur
            for g in fields:
                if g is f or (r[1] == "IF_CFG" and g["name"] == "CRC_EN"):
                    continue
                cg = (cur & field_mask(g)) >> g["lsb"]
                alt = [x for x in g["legal"] if x != cg]
                if alt:
                    other = (other & ~field_mask(g)) | (max(alt) << g["lsb"])
            for v in bad:
                wb = (other & ~field_mask(f)) | (v << f["lsb"]) | reserved
                L.append(f"    rt_write_check(7'h{a:02X}, 8'h{wb:02X}, 8'h{cur:02X}, 8'h{E_RANGE:02X}, \"{r[1]}.{f['name']} = {v} (illegal)\");")
            L.append(f"    rt_write(7'h{a:02X}, 8'h{base:02X});")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    for a, r in locked:                                        # and refused again once locked
        wv = legal_other(r[4])
        L.append(f"    rt_write_check(7'h{a:02X}, 8'h{wv:02X}, 8'h{reset_byte(r[4]):02X}, 8'h{E_ADDR:02X}, \"{r[1]} locked again\");")
    # read while locked (audit round 19, auditor C): another legal value held across the lock, then the reset values
    # back under the key
    held = {a: legal_other(r[4], low=True) for a, r in locked}
    assert all(held[a] != reset_byte(r[4]) for a, r in locked), "a test register without a second legal value"
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    L += [f"    rt_write(7'h{a:02X}, 8'h{held[a]:02X});" for a, r in locked]
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    for a, r in locked:
        L.append(f"    rt_read_expect(7'h{a:02X}, 8'h{held[a]:02X}, \"{r[1]} read while locked\");")
        L.append(f"    rt_write_check(7'h{a:02X}, 8'h{reset_byte(r[4]):02X}, 8'h{held[a]:02X}, 8'h{E_ADDR:02X}, "
                 f"\"{r[1]} locked: a write refused, the held value kept\");")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    L += [f"    rt_write(7'h{a:02X}, 8'h{reset_byte(r[4]):02X});" for a, r in locked]
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    # 2b. independence (audit round 23, auditor C: every write went in ascending address order with the others at
    #     their reset values and only the written register was read back, so an OFF_M_H write clearing M[7:0] and an
    #     OFF_M_L write clearing SIGN passed all 16 groups): every writable register but IF_CFG (the frame format)
    #     given a legal byte away from its reset value, in ascending, descending and a shuffled address order, each
    #     round followed by one burst read of the whole map (every writable register as written, every active copy at
    #     its reset value: no APPLY); the reset values back after each round; no flag. Since audit round 27 (auditor C:
    #     a W1C gate that cleared ERR's bits on every write passed, as ERR was 0 here): ADDR_ERR and CMD_ERR set
    #     before the writes and ERR read in every burst, the two flags kept and no other
    ind = [a for a, r in sorted(regs.items()) if r[2] == "RW" and r[1] != "IF_CFG"]
    shuffled = sorted(ind)
    random.Random(23).shuffle(shuffled)
    L.append("    // 2b. one write leaves every other register as it was: three address orders, a burst read of the map each")
    flags = E_ADDR | E_CMD
    L.append(f"    rt_write(7'h{A_ERR:02X}, 8'hFF);")
    L.append(f"    rt_write(7'h{undefined[0]:02X}, 8'h5A);")                  # ADDR_ERR
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h5A);")                          # a wrong key: CMD_ERR
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    L.append(f"    rt_read_expect(7'h{A_ERR:02X}, 8'h{flags:02X}, \"2b: ADDR_ERR and CMD_ERR set before the writes\");")
    wrote = 0
    for nm, order, low in (("ascending", sorted(ind), False), ("descending", sorted(ind, reverse=True), True),
                           ("shuffled", shuffled, False)):
        val = {a: legal_other(regs[a][4], low=low) for a in ind}
        assert all(val[a] != reset_byte(regs[a][4]) for a in ind), f"2b {nm}: a register written with its reset value"
        L += [f"    rt_write(7'h{a:02X}, 8'h{val[a]:02X});" for a in order]
        for a in order:
            wrote |= val[a] | reset_byte(regs[a][4])
        L += ["    spi_tx[0] = 8'h80;", "    for (int i = 1; i <= 128; i++) spi_tx[i] = 8'h00;", "    spi_xfer(129, 0);"]
        L.append(f"    rt_burst_expect({A_ERR + 1}, 8'h{flags:02X}, \"2b {nm}: burst 0x{A_ERR:02X} ERR (the flags set before "
                 f"the writes kept, no other)\");")
        for a in range(0x80):
            if a in val:
                L.append(f"    rt_burst_expect({a + 1}, 8'h{val[a]:02X}, \"2b {nm}: burst 0x{a:02X} {regs[a][1]}\");")
            elif a in mirrors:
                L.append(f"    rt_burst_expect({a + 1}, 8'h{reset_byte(regs[mirrors[a]][4]):02X}, "
                         f"\"2b {nm}: burst 0x{a:02X} {regs[mirrors[a]][1]} active\");")
        L += [f"    rt_write(7'h{a:02X}, 8'h{reset_byte(regs[a][4]):02X});" for a in sorted(ind)]
    assert wrote & flags == flags, f"2b: no written byte names bit(s) 0x{flags & ~wrote:02X} of ERR's flags"
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    L.append(f"    expect_err_exact(8'h{flags:02X}, \"2b: the writes in three orders and the bursts: ADDR_ERR and CMD_ERR "
             f"kept, no other flag\");")
    # 2c. aliasing (audit round 28, auditor C: 2b wrote each register one value per round, with the same low bits in
    #     ALERT_MASK and ALERT_MASK_D where it mattered, and left IF_CFG out, so an ALERT_MASK write that also loaded
    #     ALERT_MASK_D and an IF_CFG write whose reserved bit 2 loaded RAW_EN passed all 16 groups): rounds of random
    #     legal bytes for every writable register (the reserved bits random too; IF_CFG's CRC_EN kept 0, the frame
    #     format), written in ascending or descending address order (alternately) and followed by one burst read of
    #     the map. Rounds are drawn (seeded; of 40 candidates the one making the most conditions visible) until every
    #     single-bit alias is visible: for every ordered pair of writable registers A, B and every bit j of A's byte
    #     and k of B's fields, a round where B is written before A and A's bit j differs from B's bit k (a write to A
    #     loading its bit j into B's bit k), rounds where B is written before A with B's bit k 0 and 1 (a write to A
    #     clearing or setting it), a round where bit j of A's byte differs from bit k of A's fields (a write loading
    #     its own bit j into its bit k), and every bit of every byte both 0 and 1 (the active copies, ERR and DFLAG,
    #     which no write here changes, as victims)
    alias_regs = [a for a, r in sorted(regs.items()) if r[2] == "RW"]
    ifcfg_a = next(a for a in alias_regs if regs[a][1] == "IF_CFG")
    crc_bit = next(f["lsb"] for f in regs[ifcfg_a][4] if f["name"] == "CRC_EN")
    fbits = {a: [k for k in range(8) if any(f["lsb"] <= k <= f["msb"] for f in regs[a][4])] for a in alias_regs}
    fixed0 = {(ifcfg_a, crc_bit)}                      # bits held at 0 in every round

    def rand_byte(rng, a):
        v = rng.randrange(256)                         # reserved bits random
        for f in regs[a][4]:
            x = 0 if (a, f["lsb"]) in fixed0 and f["msb"] == f["lsb"] else rng.choice(f["legal"])
            v = (v & ~field_mask(f)) | (x << f["lsb"])
        return v

    def bit(v, k):
        return (v >> k) & 1
    c_data = {(A, j, B, k) for A in alias_regs for B in alias_regs if A != B for j in range(8) for k in fbits[B]
              if (B, k) not in fixed0 or (A, j) not in fixed0}
    c_const = {(A, B, k, x) for A in alias_regs for B in alias_regs if A != B for k in fbits[B] for x in (0, 1)
               if not ((B, k) in fixed0 and x == 1)}
    c_both = {(A, j, x) for A in alias_regs for j in range(8) for x in (0, 1) if not ((A, j) in fixed0 and x == 1)}
    c_self = {(A, j, k) for A in alias_regs for j in range(8) for k in fbits[A] if j != k
              if not ((A, j) in fixed0 and (A, k) in fixed0)}
    n_conds = len(c_data) + len(c_const) + len(c_both) + len(c_self)

    def visible(val, asc):
        before = (lambda b_, a_: b_ < a_) if asc else (lambda b_, a_: b_ > a_)
        d_ = {(A, j, B, k) for (A, j, B, k) in c_data if before(B, A) and bit(val[A], j) != bit(val[B], k)}
        c_ = {(A, B, k, x) for (A, B, k, x) in c_const if before(B, A) and bit(val[B], k) == x}
        b_ = {(A, j, x) for (A, j, x) in c_both if bit(val[A], j) == x}
        s_ = {(A, j, k) for (A, j, k) in c_self if bit(val[A], j) != bit(val[A], k)}
        return d_, c_, b_, s_
    rng = random.Random(28)
    rounds = []
    while (c_data or c_const or c_both or c_self) and len(rounds) < 60:
        asc = len(rounds) % 2 == 0
        best = None
        for _ in range(40):
            val = {a: rand_byte(rng, a) for a in alias_regs}
            vis = visible(val, asc)
            n = sum(len(x) for x in vis)
            if best is None or n > best[0]:
                best = (n, val, vis)
        _, val, (d_, c_, b_, s_) = best
        c_data -= d_
        c_const -= c_
        c_both -= b_
        c_self -= s_
        rounds.append((asc, val))
    assert not (c_data or c_const or c_both or c_self), \
        f"2c: {len(c_data) + len(c_const) + len(c_both) + len(c_self)} alias conditions open"
    L.append(f"    // 2c. aliasing: {len(rounds)} rounds of random legal bytes, ascending and descending, a burst read of the "
             f"map each; {n_conds} alias conditions, every one visible")
    L.append(f"    rt_write(7'h{A_ERR:02X}, 8'hFF);")
    L.append(f"    rt_write(7'h{undefined[0]:02X}, 8'h5A);")                  # ADDR_ERR
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h5A);")                          # a wrong key: CMD_ERR
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    dflag_a = next(a for a, r in regs.items() if r[1] == "DFLAG")
    for n_r, (asc, val) in enumerate(rounds):
        order = sorted(alias_regs, reverse=not asc)
        L += [f"    rt_write(7'h{a:02X}, 8'h{val[a]:02X});" for a in order]
        L += ["    spi_tx[0] = 8'h80;", "    for (int i = 1; i <= 128; i++) spi_tx[i] = 8'h00;", "    spi_xfer(129, 0);"]
        tag = f"2c round {n_r + 1} ({'ascending' if asc else 'descending'})"
        L.append(f"    rt_burst_expect({A_ERR + 1}, 8'h{flags:02X}, \"{tag}: burst 0x{A_ERR:02X} ERR\");")
        L.append(f"    rt_burst_expect({dflag_a + 1}, 8'h00, \"{tag}: burst 0x{dflag_a:02X} DFLAG\");")
        for a in range(0x80):
            if a in val:
                used = sum(field_mask(f) for f in regs[a][4])
                L.append(f"    rt_burst_expect({a + 1}, 8'h{val[a] & used:02X}, \"{tag}: burst 0x{a:02X} {regs[a][1]}\");")
            elif a in mirrors:
                L.append(f"    rt_burst_expect({a + 1}, 8'h{reset_byte(regs[mirrors[a]][4]):02X}, "
                         f"\"{tag}: burst 0x{a:02X} {regs[mirrors[a]][1]} active\");")
    L += [f"    rt_write(7'h{a:02X}, 8'h{reset_byte(regs[a][4]):02X});" for a in sorted(alias_regs)]
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    L.append(f"    expect_err_exact(8'h{flags:02X}, \"2c: the rounds and the bursts: ADDR_ERR and CMD_ERR kept, no other flag\");")
    # 2d. the command codes and the key as data (audit round 28, auditor C: no fixed test wrote 0xA5 anywhere but
    #     COMMAND, so a SOFT_RESET decoded from the data byte alone passed all 16 groups with tb_spi_r14's seed 11):
    #     each command code and the test key written to every address but COMMAND: a writable register (the test
    #     registers with the key) takes a legal byte (read back, reserved bits 0, then its reset value again) and
    #     refuses an illegal one with exactly RANGE_ERR; IF_CFG through code_ifcfg (the BFM follows CRC_EN; DEBUG read
    #     after it); ERR and DFLAG (both 0) stay 0; TEST_KEY: the key opens without a flag, any other byte locks with
    #     exactly CMD_ERR; the read-only registers, the active copies and the undefined addresses: exactly ADDR_ERR
    #     after the seven writes, and the fixed values read back. ERR is checked exactly (never RESET_FLAG); at the end
    #     no SOFT_RESET commit and no pending command counted, CMD_PENDING 0 and STATE IDLE
    codes = sorted(set(RM.COMMANDS.values()) | {RM.TEST_KEY})
    cmd_a2 = next(a for a, r in regs.items() if r[1] == "COMMAND")
    L.append(f"    // 2d. the command codes and the key as data: {', '.join(f'0x{c:02X}' for c in codes)} to every address "
             f"but COMMAND")
    L.append("    code_begin();")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    for a, r in sorted(regs.items()):
        if r[2] != "RW":
            continue
        used = sum(field_mask(f) for f in r[4])
        base = reset_byte(r[4])
        for c in codes:
            ok = all(((c & field_mask(f)) >> f["lsb"]) in f["legal"] for f in r[4])
            nm = f"2d {r[1]} <- 0x{c:02X}"
            if r[1] == "IF_CFG":
                assert ok and base == 0
                L.append(f"    code_ifcfg(8'h{c:02X}, 8'h{c & used:02X}, 8'h{reset_byte(regs[0x62][4]):02X}, \"{nm}\");")
            elif ok:
                L.append(f"    rt_write_exact(7'h{a:02X}, 8'h{c:02X}, 8'h{c & used:02X}, 8'h00, \"{nm}\");")
                L.append(f"    rt_write(7'h{a:02X}, 8'h{base:02X});")
            else:
                L.append(f"    rt_write_exact(7'h{a:02X}, 8'h{c:02X}, 8'h{base:02X}, 8'h{E_RANGE:02X}, \"{nm} (illegal)\");")
    for a, r in sorted(regs.items()):
        if r[2] == "W1C":
            for c in codes:
                L.append(f"    rt_write_exact(7'h{a:02X}, 8'h{c:02X}, 8'h00, 8'h00, \"2d {r[1]} <- 0x{c:02X} (W1C, 0 before)\");")
    for c in codes:
        e = 0 if c == RM.TEST_KEY else E_CMD
        L.append(f"    rt_write_exact(7'h{A_KEY:02X}, 8'h{c:02X}, 8'h00, 8'h{e:02X}, \"2d TEST_KEY <- 0x{c:02X}\");")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    for a in range(0x80):
        if a == cmd_a2 or (a in regs and regs[a][2] in ("RW", "W1C")) or a == A_KEY:
            continue
        L += [f"    rt_write(7'h{a:02X}, 8'h{c:02X});" for c in codes]
        if a in mirrors:
            L.append(f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(regs[mirrors[a]][4]):02X}, "
                     f"\"2d {regs[mirrors[a]][1]} active after the codes\");")
        elif a in regs and regs[a][1] == "CAPS":
            L += ["`ifdef FIFO4", f"    rt_read_expect(7'h{a:02X}, 8'h{caps4(regs[a]):02X}, \"2d CAPS after the codes\");",
                  "`else", f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(regs[a][4]):02X}, \"2d CAPS after the codes\");",
                  "`endif"]
        elif a in regs and regs[a][1] in ("ID", "VERSION", "ODR_H", "ODR_L", "FORMAT", "FIFO_LEVEL"):
            L.append(f"    rt_read_expect(7'h{a:02X}, 8'h{reset_byte(regs[a][4]):02X}, \"2d {regs[a][1]} after the codes\");")
        what = regs[a][1] if a in regs else (regs[mirrors[a]][1] + " active" if a in mirrors else "undefined")
        L.append(f"    expect_err_exact(8'h{E_ADDR:02X}, \"2d 0x{a:02X} {what}: the codes refused (exactly ADDR_ERR)\");")
    L.append("    code_end(\"2d\");")
    # 4. read-only and undefined writes
    L.append("    // 4. read-only registers and undefined addresses")
    assert regs[0x03][1] == "STATUS" and regs[0x03][2] == "RO"
    L.append(f"    rt_write_err(7'h03, 8'h5A, 8'h{E_ADDR:02X}, \"STATUS read only (its value moves: not read back)\");")
    for a, r in sorted(regs.items()):
        if r[2] == "RO" and a not in (0x03, 0x40):
            if r[1] == "CAPS":
                L += ["`ifdef FIFO4", f"    rt_write_check(7'h{a:02X}, 8'h5A, 8'h{caps4(r):02X}, 8'h{E_ADDR:02X}, \"CAPS read only\");",
                      "`else", f"    rt_write_check(7'h{a:02X}, 8'h5A, 8'h{reset_byte(r[4]):02X}, 8'h{E_ADDR:02X}, \"CAPS read only\");",
                      "`endif"]
                continue
            L.append(f"    rt_write_check(7'h{a:02X}, 8'h5A, 8'h{reset_byte(r[4]):02X}, 8'h{E_ADDR:02X}, \"{r[1]} read only\");")
    for a in sorted(mirrors):
        L.append(f"    rt_write_check(7'h{a:02X}, 8'h5A, 8'h{reset_byte(regs[mirrors[a]][4]):02X}, 8'h{E_ADDR:02X}, \"{regs[mirrors[a]][1]} active (read only)\");")
    for a in undefined:
        L.append(f"    rt_write_check(7'h{a:02X}, 8'h5A, 8'h00, 8'h{E_ADDR:02X}, \"undefined 0x{a:02X}\");")
    L.append("endtask")
    # 5. the guarded writes (regmap.guarded_addrs): two legal bytes differing from the reset value and each other;
    #    guard_one (tb_top_r14) uses the first unless the register holds it, sends FLUSH just after a tick at 64 kHz,
    #    writes, and expects STATE_ERR and the register unchanged
    L.append("task automatic run_guard_tests();")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});       // the test registers among them need the key")
    for a in RM.guarded_addrs():
        r = regs[a]
        w1, w2 = legal_other(r[4]), legal_other(r[4], low=True)
        if w2 == w1:                                   # binary fields only: the reset value is the other choice
            w2 = reset_byte(r[4])
        assert w1 != w2 and w1 != reset_byte(r[4]), (r[1], w1, w2)
        L.append(f"    guard_one(7'h{a:02X}, 8'h{w1:02X}, 8'h{w2:02X}, \"{r[1]}\");")
        bad = None                                     # an out-of-range byte, if a field has values beyond its range
        for f in r[4]:
            w_ = f["msb"] - f["lsb"] + 1
            xs = [x for x in (min(f["legal"]) - 1, max(f["legal"]) + 1) if 0 <= x < (1 << w_)]
            if xs:
                bad = (reset_byte(r[4]) & ~field_mask(f)) | (xs[0] << f["lsb"])
                break
        if bad is not None:                            # audit round 8: the guard is decided before the range
            L.append(f"    guard_range(7'h{a:02X}, 8'h{bad:02X}, \"{r[1]}\");")
        # SOFT_RESET's code as the data (audit round 28, auditor C): exactly STATE_ERR, no reset, not written
        L.append(f"    guard_code(7'h{a:02X}, 8'h{RM.COMMANDS['SOFT_RESET']:02X}, \"{r[1]}\");")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    for a in RM.guarded_addrs():                       # audit round 8: the lock is decided before the guard
        if regs[a][3]:
            L.append(f"    guard_locked(7'h{a:02X}, 8'h{legal_other(regs[a][4]):02X}, \"{regs[a][1]}\");")
    L.append("endtask")
    # 6. the writes the guard does not cover (audit round 13, auditor C: only ALERT_MASK had been written while a command
    #    was pending, and a guard widened to IF_CFG and DEBUG, or to the test key, passed every test): every writable
    #    register outside regmap.guarded_addrs() but the command register, written while FLUSH waits: no flag and
    #    written (free_* in tb_top_r14; the test key first, as it unlocks DEBUG)
    free = [r for r in RM.REGS if r[2] in ("RW", "W1C", "WO") and r[0] not in RM.guarded_addrs() and r[1] != "COMMAND"]
    L.append("task automatic run_free_tests();")
    locked_regs = [r for r in RM.REGS if r[3]]
    unguarded_locked = next(r for r in locked_regs if r[0] not in RM.guarded_addrs())   # DEBUG: no guard of its own
    for r in free:
        if r[1] == "TEST_KEY":
            # audit round 15, auditor C: only the flags of the key sent while a command waits were checked, and a key
            # dropped while a command is pending passed every test: the key opens a test register, the lock closes one
            ul, lk = unguarded_locked, locked_regs[0]
            L += [f"    free_key(8'h{RM.TEST_KEY:02X}, 8'h00, \"TEST_KEY: the key\");",
                  f"    rt_write_check(7'h{ul[0]:02X}, 8'h{legal_other(ul[4]):02X}, 8'h{legal_other(ul[4]):02X}, 8'h00, "
                  f"\"J2 {ul[1]} written after the key sent while a command was pending\");",
                  f"    rt_write(7'h{ul[0]:02X}, 8'h{reset_byte(ul[4]):02X});",
                  "    free_key(8'h00, 8'h00, \"TEST_KEY: lock\");",
                  f"    rt_write_check(7'h{lk[0]:02X}, 8'h{legal_other(lk[4]):02X}, 8'h{reset_byte(lk[4]):02X}, 8'h{E_ADDR:02X}, "
                  f"\"J2 {lk[1]} refused after the lock sent while a command was pending\");",
                  f"    free_key(8'h5A, 8'h{E_CMD:02X}, \"TEST_KEY: a wrong key (CMD_ERR, not STATE_ERR)\");"]
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h{RM.TEST_KEY:02X});")
    for r in free:
        if r[1] == "TEST_KEY":
            continue
        if r[1] == "ERR":
            L.append("    free_err();")
        elif r[2] == "W1C":
            L.append(f"    free_w1c(7'h{r[0]:02X}, 8'hFF, \"{r[1]}\");")   # every bit (audit round 28, auditor C)
        elif r[1] == "IF_CFG":
            L.append("    free_ifcfg();")
        else:
            L.append(f"    free_one(7'h{r[0]:02X}, 8'h{legal_other(r[4]):02X}, \"{r[1]}\");")
    L.append(f"    rt_write(7'h{A_KEY:02X}, 8'h00);")
    L.append("endtask")
    L += soft_set_all(regs)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    chk = ("rt_read_expect(", "rt_burst_expect(", "rt_expect_err(", "expect_err_exact(", "rt_write_check(", "rt_write_err(", "guard_one(", "guard_range(",
           "guard_locked(", "free_one(", "free_w1c(", "free_err(", "free_key(", "free_ifcfg(", "rt_write_exact(",
           "code_ifcfg(", "code_end(", "guard_code(")
    total, per, skip = 0, {"": 0, "FIFO4": 0}, None
    for ln in L:                                       # checks in the file, and those each FIFO configuration runs
        t = ln.strip()
        if t == "`ifdef FIFO4":
            skip = ""
            continue
        if t == "`else":
            skip = "FIFO4"
            continue
        if t == "`endif":
            skip = None
            continue
        k = sum(t.count(c) for c in chk)
        total += k
        for cfg in per:
            if skip is None or skip != cfg:
                per[cfg] += k
    print(f"wrote {os.path.relpath(OUT, HERE)}: {total} checks ({per['']} with an 8-deep FIFO, {per['FIFO4']} with "
          f"a 4-deep one; {len(RM.guarded_addrs())} guarded registers)")
    # the counts the spec quotes for these checks (audit round 24, auditor C: "各構成で 601 個" stayed after round 23
    # made it 692; the self-tests check their own counts since round 21, these were checked by nothing)
    doc = os.path.join(HERE, "..", "..", "..", "..", "documentation", "gf180_digital_control_spec_20261119.md")
    try:
        txt = open(doc, encoding="utf-8").read()
    except OSError as ex:
        sys.exit(f"PROBLEM: the spec cannot be read ({ex})")
    assert per[''] == per['FIFO4'], "the quotes assume one count for both FIFO depths"
    stale = []
    for pat, have in ((r"生成した確認 ([\d,]+) 個", total), (r"生成した確認 [\d,]+ 個（各構成 ([\d,]+) 個", per['']),
                      (r"各構成で ([\d,]+) 個を実行", per[''])):   # thousands written 1,658 (round 28)
        got = [int(x.replace(",", "")) for x in re.findall(pat, txt)]
        if not got or any(g != have for g in got):
            stale.append(f"the spec quotes {got} for {pat!r}, the generator made {have}")
    if stale:
        sys.exit("PROBLEM: " + "; ".join(stale))


PIN_OUT = os.path.join(HERE, "..", "build", "pin_tests.svh")
SHADOW_REGS = [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x60, 0x61, 0x62]   # 0x62: DBG_SEL (at once)


def regs_of(ac):
    """The register bytes of the settings ac (field name -> value), from the map's fields."""
    out = {}
    for a in SHADOW_REGS:
        r = next(x for x in RM.REGS if x[0] == a)
        out[a] = sum(ac.get(f["name"], 0) << f["lsb"] for f in r[4])
    return out


def pin_cases():
    """Settings that exercise every analog control's mapping: every range at its largest M with both signs, every
    trim and rate, the blanking lengths, the test controls; and the M one above the range's top (CFG_ERR: nothing
    changes). CHOP1 is measured once per rate. The last case restores the reset values."""
    import random
    rnd = random.Random(20261120)
    fields = {f["name"]: f for *_, f in RM.all_fields()}
    reset = {n: f["reset"] for n, f in fields.items()}
    cases, measured = [], set()
    for k in range(24):
        ac = dict(reset)
        for n in ("AFE_IBIAS", "CPF_TRIM", "BTRIM_P", "BTRIM_N", "CHOP_FAST", "DWA_EN", "BLANK_LEN", "ATP_EN",
                  "ATP_SEL", "CHOP_STOP", "ADC_ZERO", "DBG_SEL", "SIGN"):
            ac[n] = rnd.choice(fields[n]["legal"])
        if k < 10:                                         # every range at its top, with both signs
            ac["RANGE"], ac["SIGN"] = k // 2, k % 2
            m = RM.RANGE_MAX_M[ac["RANGE"]]
        else:
            ac["RANGE"] = k % 5
            m = rnd.randrange(RM.RANGE_MAX_M[ac["RANGE"]] + 1)
        ac["M_H"], ac["M_L"] = m >> 8, m & 0xFF
        ac["CHOP1_RATE"] = k % 6
        ac["BTRIM_P"], ac["BTRIM_N"] = (k % 4, (k + 1) % 4) if k < 8 else (ac["BTRIM_P"], ac["BTRIM_N"])
        # ADC_ZERO and CHOP_STOP apart: (1, 0), (1, 1), (0, 1), otherwise ADC_ZERO 0 and CHOP_STOP drawn
        ac["ADC_ZERO"], ac["CHOP_STOP"] = {3: (1, 0), 6: (1, 1), 8: (0, 1), 13: (1, 0)}.get(k, (0, ac["CHOP_STOP"]))
        c1 = ac["CHOP1_RATE"] not in measured
        measured.add(ac["CHOP1_RATE"])
        cases.append((ac, True, c1))
        if ac["RANGE"] in (1, 2, 3) and k < 10:            # one above the top of the range: CFG_ERR, nothing applied
            bad = dict(ac, CPF_TRIM=(ac["CPF_TRIM"] + 1) % 16)
            m2 = RM.RANGE_MAX_M[ac["RANGE"]] + 1
            bad["M_H"], bad["M_L"] = m2 >> 8, m2 & 0xFF
            cases.append((bad, False, False))
    cases.append((dict(reset), True, False))
    return cases


def gen_nr():
    """tb_top_r14 N5, in RUN: APPLY to a base (range 1, M 1, S 0, the rest at reset); then for every other setting
    applied at the tick a one-step APPLY_NR that also changes that setting (regmap.nr_ok: rejected, CFG_ERR, nothing
    applied); then the sign walk (each step's verdict from regmap.nr_ok against the active settings it reaches); then
    APPLY back to the reset values. nr_case(shadow bytes, accepted, expected OFM, OFS, OFEN, CPF_TRIM, AFE_IBIAS,
    DWA_EN, CHOP_EN, TEST_CFG, name)."""
    fields = {f["name"]: f for *_, f in RM.all_fields()}
    reset = {n: f["reset"] for n, f in fields.items()}
    apply_fields = [f["name"] for *_, f in RM.all_fields() if f["cls"] == "apply"]

    def model(ac):                                      # regmap.nr_ok's view: M instead of M_H / M_L
        d = {n: ac[n] for n in apply_fields if n not in ("M_H", "M_L")}
        d["M"] = (ac["M_H"] << 8) | ac["M_L"]
        return d

    def with_m(ac, m, s):
        return dict(ac, M_H=m >> 8, M_L=m & 0xFF, SIGN=s)

    def regs_text(ac):
        b = regs_of(ac)
        return ", ".join("8'h%02X" % b[a] for a in SHADOW_REGS)

    def line(ac, ok, name, exp):
        p = RM.pins_from_active(exp)
        return (f"    nr_case({regs_text(ac)}, 1'b{int(ok)}, 10'd{p['OFM']}, "
                f"1'b{p['OFS']}, 4'b{p['OFEN']:04b}, 4'd{p['CPF_TRIM']}, 2'd{p['AFE_IBIAS']}, 1'b{p['DWA_EN']}, "
                f"1'b{p['CHOP_EN']}, 8'h{p['TEST_CFG']:02X}, \"{name}\");")
    base = with_m(dict(reset, RANGE=1), 1, 0)
    L = ["// nr_ok cases (regmap.nr_ok), tb_top_r14 N5: run_nr_tests() starts in RUN after nr_base() applied the base",
         "task automatic run_nr_tests();"]
    L.append(f"    nr_base({regs_text(base)});")
    active = dict(base)
    n = 0
    for f in apply_fields:
        if f in ("M_H", "M_L", "SIGN", "RANGE"):
            continue
        alt = next(x for x in fields[f]["legal"] if x != active[f])
        sh = with_m(dict(active, **{f: alt}), 2, 0)        # one M step and this setting changed
        ok = RM.nr_ok(model(sh), model(active))
        assert not ok
        L.append(line(sh, ok, f"nr {n}: {f} changed with one M step", active))
        n += 1
    for m, s in ((1, 1), (0, 1), (1, 1), (2, 0), (0, 0), (1, 0), (3, 0), (2, 0)):
        sh = with_m(active, m, s)
        ok = RM.nr_ok(model(sh), model(active))
        if ok:
            active = sh
        L.append(line(sh, ok, f"nr {n}: M {m} S {s} ({'accepted' if ok else 'rejected'})", active))
        n += 1
    # the high bits of M (OFF_M_H = M[9:8]) at the pins (audit round 4): one step across 255/256 and 511/512 is
    # accepted; M_H or M_L changed alone, and a step with the sign across a high M, are rejected
    for rng_, m0, walk in ((3, 255, ((256, 0), (255, 0), (256, 0), (0, 0), (512, 0), (257, 0), (256, 0), (255, 0))),
                           (4, 511, ((512, 0), (511, 0), (512, 0), (768, 0), (256, 0), (513, 0), (512, 0), (512, 1),
                                     (511, 0)))):
        hb = with_m(dict(reset, RANGE=rng_), m0, 0)
        L.append(f"    nr_base({regs_text(hb)});   // range {rng_}, M {m0}")
        active = dict(hb)
        for m, s in walk:
            sh = with_m(active, m, s)
            ok = RM.nr_ok(model(sh), model(active))
            if ok:
                active = sh
            L.append(line(sh, ok, f"nr {n}: range {rng_}, M {m} S {s} ({'accepted' if ok else 'rejected'})", active))
            n += 1
    L.append(f"    nr_base({regs_text(dict(reset))});   // back to the reset values")
    L.append("endtask")
    return L


def gen_pins():
    L = ["// GENERATED by gf180/tapeout/rtl_r14/tb/gen_reg_tests.py from gf180/tapeout/rtl/spec/regmap.py",
         "// (pins_from_active, RANGE_MAX_M): pin_case(shadow bytes 0x20..0x28, 0x60, 0x61, 0x62, accepted, expected",
         "// OFM, OFS, OFEN, AFE_IBIAS, CPF_TRIM, BTRIM_P, BTRIM_N, DWA_EN, CHOP_EN, TEST_CFG, CHOP_BLANK high time,",
         "// CHOP_BLANK held, CHOP half period, CHOP1 half period (0 = off), measure CHOP1, name)",
         "task automatic run_pin_tests();"]
    last = None
    for k, (ac, ok, c1) in enumerate(pin_cases()):
        b = regs_of(ac)
        exp = RM.pins_from_active(ac) if ok else last
        if ok:
            last = exp
        regs = ", ".join(f"8'h{b[a]:02X}" for a in SHADOW_REGS)
        L.append(f"    pin_case({regs}, 1'b{int(ok)}, 10'd{exp['OFM']}, 1'b{exp['OFS']}, 4'b{exp['OFEN']:04b}, "
                 f"2'd{exp['AFE_IBIAS']}, 4'd{exp['CPF_TRIM']}, 2'd{exp['BTRIM_P']}, 2'd{exp['BTRIM_N']}, "
                 f"1'b{exp['DWA_EN']}, 1'b{exp['CHOP_EN']}, 8'h{exp['TEST_CFG']:02X}, {exp['BLANK_W']}, "
                 f"1'b{exp['BLANK_HELD']}, {exp['CHOP_HALF']}, {exp['CHOP1_HALF']}, 1'b{int(c1)}, "
                 f"\"pin case {k}{'' if ok else ' (M above the range: CFG_ERR)'}\");")
    L.append("endtask")
    L += gen_nr()
    # regmap.ofen_of_range for the bench's continuous check of the applied pins against the active copies
    L += ["function automatic logic [3:0] exp_ofen(input logic [2:0] r);   // regmap.ofen_of_range",
          "    case (r)"]
    L += [f"        3'd{r}: exp_ofen = 4'b{RM.ofen_of_range(r):04b};" for r in sorted(RM.RANGE_MAX_M)]
    L += ["        default: exp_ofen = 4'bxxxx;", "    endcase", "endfunction"]
    with open(PIN_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"wrote {os.path.relpath(PIN_OUT, HERE)}: {len(pin_cases())} pin cases")


if __name__ == "__main__":
    main()
    gen_pins()
