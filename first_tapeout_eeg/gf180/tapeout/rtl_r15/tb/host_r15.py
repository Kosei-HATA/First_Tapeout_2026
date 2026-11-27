#!/usr/bin/env python3
"""host_r15.py - VER-06 (11/28): the model host procedure of the requirements (section 5.4) in Python, driving two r15
chips on the board tb/tb_host_r15.sv (shared MCLK, RESET_N, SCLK, MOSI and MISO line; CS_N and DRDY_N per chip; an
analog model per chip: electrode offset, offset DAC from the pins, AFE gain, a first-order sigma-delta) through named
pipes. The host sees only what a real host sees (MISO, DRDY_N, time); the board's oracle (op 7) is read only by the
checks of this script, never by the procedure's decisions.

Implemented from 5.4 (the rest is listed in the record, gf180_digital_verification_20261024.md section 9.10):
  rule (a) every frame's first MISO byte has STATUS's fixed bits (10); a write's later MISO bytes are 0x00; a frame that
           fails is taken as not arrived (sent again; ERR / DFLAG write-backs only of the bits handled)
  rule (b) CRC on from step 3; register reads and writes 3 bytes; ID and VERSION read twice and compared; CMD_PENDING
           read (STATUS, CRC) only from 17 frames after the command's CS_N rise; READY / DATA never from STATUS
  rule (c) the mode check (IF_CFG 0xD5 00 00) and RESET_FLAG on an unexpected state (here: after SOFT_RESET, step 9)
  rule (d) limits on every wait and repetition (RUN: T_WARM + T_REC + T_ELEC + 5 ms; confirmations 3; step 5: 10)
  rule (e) ERR is written back by steps 6 / 8 only outside a confirmation (settings, command, SOFT_RESET)
  step 2   mode check, ERR read twice, RESET_FLAG, written back, read again
  step 3   IF_CFG.CRC_EN (checked by the 3-byte read), T_ELEC written, ID / VERSION twice, CAPS (FIFO_DEPTH), the
           settings (ALERT_MASK_D 0, the offset DAC if known), ERR has no bit set since the clear
  step 4   commands confirmed by CMD_PENDING 0 and ERR, else by their effect (START: STATE not IDLE; STOP: IDLE; APPLY in
           RUN: a state PRE..FILL within 3 ms; APPLY_NR: the active M and SIGN, two equal reads); CFG_ERR / STATE_ERR
           returned to the caller (sending again gives the same)
  step 5   START, STATE polled to RUN; two chips: (i) the number (read-outs ref, chip, ref to the empty word; SEQ equal;
           counted only with every CRC good, no read-out of FIFO_DEPTH or more samples, DFLAG.OVERRUN 0) and (ii) the
           phase (time-stamping: DRDY_N falls of both chips within 2 MCLK + the resolution)
  step 6   level mode: read while DRDY_N is Low; a sample's CRC checked before CS_N rises: if wrong, 8 more SCLK (no
           pop, FRAME_ERR) and FRAME_ERR (0x02) alone written back; words wait for the next frame's header (ALERT 0) or
           an ERR read without RESET_FLAG; ALERT 0 -> 1: ERR read, FRAME_ERR -> the frame before set it, a sample word
           of that frame dropped; OVL / CHANGED samples left out of averages; SEQ gaps counted
  step 7   coarse: T_ELEC 0, APPLY per probe (binary on the signed M, range 4), sign of the mean (overload: sign only);
           fine once the reading is inside the overload rule's range: estimate from the nominal step, then APPLY_NR to
           the neighbours and the smallest |mean|
  step 8   ALERT -> ERR read, handled bits written back; DFLAG.OVL written back after a sample without OVL
  step 9   SOFT_RESET (ERR clear first), CS_N high >= 1 us, mode check, RESET_FLAG = 1, then steps 2-5 again
  step 10  STOP
Faults injected on the line (VER-06): a MOSI bit of a write's data (CRC_ERR), a cut register read (FRAME_ERR), a MISO
bit of a sample (the host's CRC fails: 8 more SCLK and the same sample again), 8 extra SCLK after a whole sample (no pop
with a good CRC at the host: dropped by the ALERT / FRAME_ERR rule), START in RUN (STATE_ERR, refused: step 4 returns
it), APPLY_NR of two steps (CFG_ERR, nothing applied).

usage: host_r15.py [--vvp build/host_r15/tb_host_r15.vvp] [--out build/host_r15]
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TMCLK = 1000.0 / 32.768                    # ns
FRAME = 32 * TMCLK                         # ns
OUT_NS = 1.0e6                             # the output interval (1 kSPS)


def load_defs(path=os.path.join(ROOT, "spec", "eeg_regs_defs.svh")):
    """The generated constants the RTL reads (regmap): addresses A_*, commands CMD_*, states ST_*, bits *_LSB."""
    d = {}
    for m in re.finditer(r"localparam (?:logic \[\d+:0\]|int) (\w+) = (?:\d+'([hdb]))?([0-9A-Fa-f]+);", open(path).read()):
        name, base, val = m.groups()
        d[name] = int(val, {"h": 16, "d": 10, "b": 2, None: 10}[base])
    return d


D = load_defs()
ST = {D[k]: k[3:] for k in D if k.startswith("ST_") and not k.endswith("_LSB")}
ERR_BITS = {k[4:-4]: D[k] for k in D if k.startswith("ERR_") and k.endswith("_LSB")}
FRAME_ERR = 1 << D["ERR_FRAME_ERR_LSB"]
RESET_FLAG = 1 << D["ERR_RESET_FLAG_LSB"]
CFG_ERR = 1 << D["ERR_CFG_ERR_LSB"]
STATE_ERR = 1 << D["ERR_STATE_ERR_LSB"]
CRC_ERR = 1 << D["ERR_CRC_ERR_LSB"]
ALERT = 1 << D["STATUS_ALERT_LSB"]
CMD_PENDING = 1 << D["STATUS_CMD_PENDING_LSB"]
DATA_BIT = 1 << D["STATUS_DATA_LSB"]
S_VALID, S_OVR, S_OVL, S_CHG, S_ERR = (1 << D[k] for k in ("SMP_VALID_LSB", "SMP_OVERRUN_LSB", "SMP_OVL_LSB",
                                                          "SMP_CHANGED_LSB", "SMP_ERR_LSB"))
DF_OVL = 1 << D["DFLAG_OVL_LSB"]
DF_OVR = 1 << D["DFLAG_OVERRUN_LSB"]
NOMINAL_STEP_LSB = 0.311e-3 * 287.0 / 0.5 * 31 * 2 ** 18      # the host's nominal: 0.311 mV x the AFE gain at the ADC
OVL_RULE_LSB = 0.43 / 0.5 * 31 * 2 ** 18                       # the overload rule's range (+-0.43 V at the ADC)


def crc8(data, c=0):
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def s24(v):
    return v - (1 << 24) if v & (1 << 23) else v


class HostError(Exception):
    pass


class Board:
    """The pipe client of tb_host_r15.sv."""

    def __init__(self, vvp, out):
        self.dir = out
        os.makedirs(out, exist_ok=True)
        self.pin, self.pout = os.path.join(out, "host_in.fifo"), os.path.join(out, "host_out.fifo")
        for p in (self.pin, self.pout):
            if os.path.exists(p):
                os.unlink(p)
            os.mkfifo(p)
        self.vlog = open(os.path.join(out, "board.log"), "w")
        self.proc = subprocess.Popen(["vvp", "-n", vvp, f"+pin={self.pin}", f"+pout={self.pout}"], cwd=ROOT,
                                     stdout=self.vlog, stderr=subprocess.STDOUT)
        self.fin = open(self.pin, "w")
        self.fout = open(self.pout, "r")
        self.t = 0
        self.n_cmd = 0
        self.t_idle = 600

    def cmd(self, *f):
        f = [int(x) for x in f] + [0] * (20 - len(f))
        self.fin.write(" ".join(str(x) for x in f) + "\n")
        self.fin.flush()
        line = self.fout.readline()
        if not line:
            raise HostError("the board stopped (see board.log)")
        a = line.split()
        if a[0] != str(f[0]):
            raise HostError(f"the board answered {line.strip()!r} to op {f[0]}")
        a = [int(x) for x in a]
        self.t = a[1]
        self.n_cmd += 1
        return a

    def xfer(self, chip, tx, nbits=None, keep=False, cont=False):
        nbits = 8 * len(tx) if nbits is None else nbits
        return self.cmd(1, chip + 4 * keep + 8 * cont, nbits, len(tx), *tx)[2:18]

    def wait(self, ns):
        if ns > 0:
            self.cmd(2, int(ns))

    def wait_low(self, chip, timeout_ns):
        a = self.cmd(3, chip, 0, int(timeout_ns))
        return a[2] == 1

    def wait_fall(self, chip, timeout_ns):
        a = self.cmd(3, chip, 1, int(timeout_ns))
        return a[2] == 1, a[3] / 1000.0

    def wait_falls_both(self, timeout_ns):
        a = self.cmd(3, 2, 0, int(timeout_ns))
        return (None if a[2] < 0 else a[2] / 1000.0), (None if a[3] < 0 else a[3] / 1000.0)

    def wait_either_low(self, timeout_ns):
        a = self.cmd(3, 3, 0, int(timeout_ns))
        return a[2] == 0, a[3] == 0

    def drdy(self):
        a = self.cmd(4)
        return a[2], a[3]

    def reset(self, v):
        self.cmd(5, v)

    def analog(self, chip, off_uv, sine_uv=0, sine_mhz=0, noise_uv=0):
        self.cmd(6, chip, off_uv, sine_uv, sine_mhz, noise_uv)

    def oracle(self, chip):
        a = self.cmd(7, chip)
        k = ("t", "state", "seq", "fifo", "err", "dflag", "crc_en", "cfg_gen", "dac_steps", "ofen", "afe_rst",
             "resid_uv", "contention", "frames")
        return dict(zip(k, a[1:]))

    def timing(self, high, low, tcss, tcsh, tidle):
        self.t_idle = tidle
        self.cmd(8, high, low, tcss, tcsh, tidle)

    def quit(self):
        a = self.cmd(9)
        self.proc.wait(timeout=60)
        return a[2]


class Line:
    """The wires between the host and the board, with the faults of VER-06 injected on them."""

    def __init__(self, board, log):
        self.b = board
        self.log = log
        self.faults = []
        self.done = []

    def arm(self, chip, kind, what, **kw):
        self.faults.append(dict(chip=chip, kind=kind, what=what, **kw))

    def xfer(self, chip, tx, nbits=None, keep=False, cont=False, what=""):
        f = next((f for f in self.faults if f["chip"] == chip and f["what"] == what and not cont), None)
        tx = list(tx)
        if f:
            self.faults.remove(f)
            if f["kind"] == "mosi":
                tx[f["byte"]] ^= 1 << f["bit"]
            elif f["kind"] == "cut":
                nbits = f["nbits"]
            elif f["kind"] == "extra":
                nbits = 8 * len(tx) + f["bits"]
        rx = self.b.xfer(chip, tx, nbits, keep, cont)
        if f:
            if f["kind"] == "miso":
                rx = list(rx)
                rx[f["byte"]] ^= 1 << f["bit"]
            self.done.append((self.b.t, chip, f["kind"], what))
            self.log(f"  [line] chip {chip}: fault '{f['kind']}' on a {what} frame")
        return rx


class Chip:
    """The host's view of one chip."""

    def __init__(self, i):
        self.i = i
        self.crc = False
        self.depth = None
        self.run = False                 # the host's belief: the chip is in RUN and its FIFO must be read
        self.words = []                  # used samples: (seq, data, status)
        self.pending = []                # (frame number, seq, data, status) read, not yet used
        self.nframe = 0
        self.alert = 0                   # ALERT of the last frame's header
        self.alert_rise = None           # the frame whose header showed ALERT 0 -> 1
        self.last_kind = {}              # frame number -> kind
        self.bad_hdr = 0
        self.section = False             # rule (e): inside a confirmation
        self.err_seen = 0                # ERR bits the host has seen and not yet written back
        self.m = 0                       # the host's signed M (applied)
        self.t_cmd_rise = -1e18
        self.n_reread = 0
        self.n_drop_frame_err = 0
        self.n_seq_gaps = 0
        self.n_empty = 0
        self.changed_left = 0
        self.need_err = False            # ALERT rose: ERR to be read (step 6)
        self.word_t = []                 # the board time (ns) each used word was read
        self.seq_break = True            # the next used word may jump in SEQ (after START, APPLY, SOFT_RESET)


class Host:
    def __init__(self, board, line, n, log):
        self.b, self.line, self.log = board, line, log
        self.chips = [Chip(i) for i in range(n)]
        self.notes = []
        self.changed_runs = []
        self.ev = []                      # time-stamped events for the record (fig. 62): never read by the procedure
        self.fine_n = 27                  # fine stage: 27 samples (one period of the board's 37 Hz test signal)

    def event(self, chip, kind, **kw):
        self.ev.append(dict(t=self.b.t, chip=chip, kind=kind, **kw))

    # ------------------------------------------------------------------ frames
    def frame(self, c, kind, tx, nbits=None, keep=False, cont=False):
        rx = self.line.xfer(c.i, tx, nbits, keep, cont, what=kind)
        if not cont:
            c.nframe += 1
            c.last_kind[c.nframe] = kind
            self.header(c, rx[0])
        return rx

    def header(self, c, h):
        """Step 6: words wait for the next frame's header: (a) and ALERT 0 -> used; ALERT 0 -> 1 -> ERR decides."""
        if h & 0xC0 != 0x80:
            c.bad_hdr += 1
            if c.bad_hdr >= 2 and c.pending:
                self.log(f"  chip {c.i}: two headers without the fixed bits: {len(c.pending)} waiting words dropped")
                c.pending = []
            return
        c.bad_hdr = 0
        a = 1 if h & ALERT else 0
        if a and not c.alert:
            c.alert_rise = c.nframe
            c.need_err = True
        if not a:
            c.alert_rise = None
            self.use_pending(c)
        c.alert = a

    def use_pending(self, c, drop_frame=None):
        for fr, seq, d, st, t_rd in c.pending:
            if fr == drop_frame:
                c.n_drop_frame_err += 1
                self.log(f"  chip {c.i}: the word SEQ {seq} of frame {fr} dropped (that frame set FRAME_ERR: not popped)")
                continue
            if c.words and not c.seq_break:
                exp = (c.words[-1][0] + 1) % 65536
                if seq != exp:
                    c.n_seq_gaps += 1
                    self.log(f"  chip {c.i}: SEQ {seq} after {c.words[-1][0]}")
            c.seq_break = False
            c.words.append((seq, d, st))
            c.word_t.append(t_rd)
        c.pending = []

    def frame_ok(self, rx, nbytes, write):
        if rx[0] & 0xC0 != 0x80:
            return False
        return not write or all(b == 0 for b in rx[1:nbytes])

    def read(self, c, addr, twice=False, tries=3):
        """A CRC-protected register read (3 bytes); rule (b): ID / VERSION / T_WARM / TEST_MUX twice."""
        if not c.crc:
            raise HostError("read with CRC before step 3")
        vals = []
        for _ in range(tries * (2 if twice else 1) + 2):
            hdr = 0x80 | addr
            rx = self.frame(c, "read", [hdr, 0, 0])
            if self.frame_ok(rx, 3, False) and rx[2] == crc8([hdr, rx[1]]):
                if addr == D["A_ERR"]:
                    self.after_err_read(c, rx[1])
                if not twice:
                    return rx[1]
                vals.append(rx[1])
                if len(vals) >= 2 and vals[-1] == vals[-2]:
                    return rx[1]
        raise HostError(f"chip {c.i}: no good read of 0x{addr:02x} (rule (d))")

    def read_nocrc(self, c, addr):
        """CRC off (step 2, before step 3): a 3-byte read is a two-register burst; the value read twice."""
        vals = []
        for _ in range(6):
            rx = self.frame(c, "read", [0x80 | addr, 0, 0])
            if rx[0] & 0xC0 == 0x80:
                vals.append(rx[1])
                if len(vals) >= 2 and vals[-1] == vals[-2]:
                    return rx[1]
        raise HostError(f"chip {c.i}: no two equal reads of 0x{addr:02x} without CRC")

    def write(self, c, addr, val, kind="write"):
        """Rule (a): a frame that fails is sent again (W1C registers: re-read, handled bits only: the callers)."""
        for _ in range(3):
            tx = [addr & 0x7F, val] + ([crc8([addr & 0x7F, val])] if c.crc else [])
            rx = self.frame(c, kind, tx)
            if self.frame_ok(rx, len(tx), True):
                return rx
        raise HostError(f"chip {c.i}: write of 0x{addr:02x} not taken (rule (d))")

    def after_err_read(self, c, err):
        """Step 6 (ii): a good ERR read without RESET_FLAG decides the waiting words (FRAME_ERR rule)."""
        if err & RESET_FLAG:
            return
        drop = None
        if err & FRAME_ERR and c.alert_rise is not None and c.last_kind.get(c.alert_rise - 1) == "sample":
            drop = c.alert_rise - 1
        self.use_pending(c, drop)
        c.alert_rise = None if not err else c.alert_rise

    def clear_err(self, c, bits):
        """W1C of the bits handled (rule (e): never inside a confirmation unless it is the confirmation's own)."""
        if bits:
            self.write(c, D["A_ERR"], bits)

    def mode_check(self, c):
        """Step 9 / rule (c): IF_CFG 0xD5 00 00, legal with CRC on or off."""
        for _ in range(4):
            rx = self.frame(c, "mode", [0x80 | D["A_IF_CFG"], 0, 0])
            if rx[1] & 1 and rx[2] == crc8([0x80 | D["A_IF_CFG"], rx[1]]):
                return True
            if not rx[1] & 1 and rx[2] == 0x00:
                return False
        raise HostError(f"chip {c.i}: mode check undecided")

    # ------------------------------------------------------------------ waiting while the other chips are read
    def sleep(self, ns, busy=None):
        t_end = self.b.t + ns
        while self.b.t < t_end - 1:
            self.service(busy)
            self.b.wait(min(t_end - self.b.t, 0.2e6))
        self.service(busy)

    def service(self, busy=None):
        """Step 5 / 6: every chip in RUN (but the one inside a command's confirmation) read while DRDY_N is Low."""
        d = self.b.drdy()
        for c in self.chips:
            if c.run and c is not busy and d[c.i] == 0:
                self.drain(c)

    # ------------------------------------------------------------------ step 6
    def sample(self, c, latest=False):
        """One 8-byte sample read, its CRC checked before CS_N rises; wrong CRC: 8 more SCLK (no pop, FRAME_ERR),
        FRAME_ERR alone written back (outside a confirmation), and read again. Returns (seq, data, status) or None
        for an empty word."""
        hdr = D["LAT_HDR"] if latest else D["SMP_HDR"]
        for _ in range(4):
            rx = self.frame(c, "latest" if latest else "sample", [hdr] + [0] * 7, keep=True)
            ok = rx[7] == crc8([hdr] + rx[1:7])
            if ok:
                self.line.xfer(c.i, [], 0, cont=True, what="end")
            else:
                self.line.xfer(c.i, [0], 8, cont=True, what="end")          # 8 more SCLK: too long, no pop
                c.n_reread += 1
                self.log(f"  chip {c.i}: sample CRC wrong at the host: 8 more SCLK, read again")
                if not c.section:
                    self.clear_err(c, FRAME_ERR)
                continue
            st, seq, d = rx[1], (rx[2] << 8) | rx[3], s24((rx[4] << 16) | (rx[5] << 8) | rx[6])
            if not st & S_VALID:
                c.n_empty += 1
                return None, rx[0]
            if not latest:
                c.pending.append((c.nframe, seq, d, st, self.b.t))
            return (seq, d, st), rx[0]
        raise HostError(f"chip {c.i}: no good sample read (rule (d))")

    def drain(self, c, to_empty=False):
        """Level mode: read while DRDY_N is Low (to_empty: until an empty word whose header has DATA 0)."""
        n = 0
        while True:
            w, h = self.sample(c)
            n += 1
            if c.need_err and not c.section:
                self.on_alert(c)
            if w is None:
                if h & 0xC0 == 0x80 and not h & DATA_BIT:
                    return n
                continue
            if not to_empty and self.b.drdy()[c.i] == 1:
                return n
            if n > 3 * (c.depth or 8) + 4:
                raise HostError(f"chip {c.i}: the read-out does not end")

    def on_alert(self, c):
        """Step 6 / 8: ALERT rose: ERR read (the waiting words decided), the handled bits written back."""
        c.need_err = False
        err = self.read(c, D["A_ERR"])
        if err & RESET_FLAG:
            raise HostError(f"chip {c.i}: RESET_FLAG in RUN (rule (c))")
        if err:
            self.log(f"  chip {c.i}: ALERT: ERR 0x{err:02x} read and written back")
            self.write(c, D["A_ERR"], err)

    # ------------------------------------------------------------------ step 4
    def command(self, c, code, shadow=None):
        """Step 4. shadow: the expected active offset DAC (M signed) for APPLY / APPLY_NR effects."""
        name = {D[k]: k[4:] for k in D if k.startswith("CMD_")}[code]
        if self.b.t - c.t_cmd_rise < 17 * FRAME:
            self.b.wait(17 * FRAME - (self.b.t - c.t_cmd_rise))
        st_before = self.read(c, D["A_STATE"])
        c.section = True
        try:
            for attempt in range(3):
                rx = self.write(c, D["A_COMMAND"], code, kind="command")
                c.t_cmd_rise = self.b.t - self.b.t_idle
                arrived = True
                self.b.wait(17 * FRAME - self.b.t_idle + 50)
                for _ in range(3):
                    s = self.read(c, D["A_STATUS"])
                    if not s & CMD_PENDING:
                        break
                else:
                    raise HostError(f"chip {c.i}: CMD_PENDING stays 1 after {name}")
                err = self.read(c, D["A_ERR"])
                new = err & ~RESET_FLAG
                if err & (CFG_ERR | STATE_ERR):
                    self.log(f"  chip {c.i}: {name} refused, ERR 0x{err:02x}")
                    self.write(c, D["A_ERR"], err)
                    self.event(c.i, "cmd", name=name, err=err, done=False)
                    return err
                done = arrived and not new
                if code == D["CMD_START"]:
                    done = done or self.read(c, D["A_STATE"]) != D["ST_IDLE"]
                elif code == D["CMD_STOP"]:
                    done = done or self.read(c, D["A_STATE"]) == D["ST_IDLE"]
                elif code in (D["CMD_APPLY"], D["CMD_APPLY_NR"]) and shadow is not None:
                    if code == D["CMD_APPLY"] and st_before == D["ST_RUN"]:
                        sv = self.read(c, D["A_STATE"])
                        done = sv in (D["ST_PRE"], D["ST_PULSE"], D["ST_RECOVER"], D["ST_WAIT_E"], D["ST_ALIGN"],
                                      D["ST_FILL"])
                    else:
                        done = self.active_m(c) == shadow
                if new:
                    self.write(c, D["A_ERR"], err)
                if done:
                    if new:
                        self.log(f"  chip {c.i}: {name} executed (by its effect; ERR 0x{err:02x} written back)")
                    self.event(c.i, "cmd", name=name, err=err, done=True, attempt=attempt + 1)
                    return 0
                self.log(f"  chip {c.i}: {name} not executed (ERR 0x{err:02x}): sent again")
            raise HostError(f"chip {c.i}: {name} not executed after 3 attempts (rule (d))")
        finally:
            c.section = False

    def active_m(self, c):
        """The active offset DAC as two equal CRC-good reads (step 4)."""
        prev = None
        for _ in range(6):
            mh, ml, ctl = (self.read(c, a) for a in (D["A_OFF_M_H_ACT"], D["A_OFF_M_L_ACT"], D["A_OFF_CTRL_ACT"]))
            v = ((mh & 3) << 8 | ml) * (-1 if ctl & 0x10 else 1)
            if v == prev:
                return v
            prev = v
        raise HostError(f"chip {c.i}: the active copy reads differ")

    def write_settings(self, c, regs):
        """Step 3: settings written, then ERR without a bit set since the clear (else cleared and written again)."""
        c.section = True
        try:
            for _ in range(3):
                for a, v in regs:
                    self.write(c, a, v)
                err = self.read(c, D["A_ERR"])
                if not err:
                    return
                self.log(f"  chip {c.i}: ERR 0x{err:02x} after the settings: cleared, written again")
                self.write(c, D["A_ERR"], err)
            raise HostError(f"chip {c.i}: settings not taken (rule (d))")
        finally:
            c.section = False

    def offset_regs(self, m, rng=4):
        mag = abs(m)
        return [(D["A_OFF_M_H"], mag >> 8), (D["A_OFF_M_L"], mag & 0xFF),
                (D["A_OFF_CTRL"], (0x10 if m < 0 else 0) | rng)]

    # ------------------------------------------------------------------ steps 2, 3, 5
    def bring_up(self, c, m=None):
        """Steps 2-5 for one chip (after the shared RESET_N or a SOFT_RESET)."""
        crc_on = self.mode_check(c)
        if crc_on:
            raise HostError(f"chip {c.i}: CRC on at bring-up (not from reset)")
        c.crc = False
        err = self.read_nocrc(c, D["A_ERR"])
        if not err & RESET_FLAG:
            raise HostError(f"chip {c.i}: RESET_FLAG 0 at bring-up")
        for _ in range(3):
            self.write(c, D["A_ERR"], err)
            err2 = self.read_nocrc(c, D["A_ERR"])
            if not err2 & RESET_FLAG:
                break
        else:
            raise HostError(f"chip {c.i}: RESET_FLAG does not clear")
        # step 3: CRC on, checked by the 3-byte read of IF_CFG
        for _ in range(3):
            self.write(c, D["A_IF_CFG"], 0x01)
            rx = self.frame(c, "read", [0x80 | D["A_IF_CFG"], 0, 0])
            if rx[1] == 0x01 and rx[2] == crc8([0x80 | D["A_IF_CFG"], 0x01]):
                c.crc = True
                break
        else:
            raise HostError(f"chip {c.i}: CRC_EN not confirmed")
        idv, ver = self.read(c, D["A_ID"], twice=True), self.read(c, D["A_VERSION"], twice=True)
        if (idv, ver) != (D["ID_ID_RST"], D["VERSION_VERSION_RST"]):
            raise HostError(f"chip {c.i}: ID 0x{idv:02x} VERSION 0x{ver:02x}")
        c.depth = self.read(c, D["A_CAPS"]) & 0x0F
        regs = [(D["A_T_ELEC"], 0), (D["A_ALERT_MASK_D"], 0)]
        if m is not None:
            regs += self.offset_regs(m)
        self.write_settings(c, regs)
        if self.command(c, D["CMD_START"]):
            raise HostError(f"chip {c.i}: START refused")
        c.seq_break = True
        c.pending = []
        self.wait_run(c)
        if m is not None:
            c.m = m
        return idv, ver

    def wait_run(self, c):
        """Step 5: STATE polled to RUN, limit T_WARM + T_REC + T_ELEC + 5 ms from the command (rule (d))."""
        t_lim = c.t_cmd_rise + (5.0 + 0.25 + 0.0 + 5.0) * 1.0e6
        while True:
            s = self.read(c, D["A_STATE"])
            if s == D["ST_RUN"]:
                c.run = True
                c.changed_left = 0
                self.event(c.i, "RUN")
                return
            if s == D["ST_IDLE"]:
                raise HostError(f"chip {c.i}: IDLE while waiting for RUN (rule (c))")
            if self.b.t > t_lim:
                raise HostError(f"chip {c.i}: no RUN by the limit (rule (d))")
            self.sleep(0.25e6, busy=c)

    # ------------------------------------------------------------------ step 5 (i), (ii)
    def readout(self, c):
        """A read-out to the empty word: (count of samples, all CRC good)."""
        n = 0
        while True:
            w, h = self.sample(c)
            if w is None:
                if h & 0xC0 == 0x80 and not h & DATA_BIT:
                    return n
                continue
            n += 1
            if n > 3 * c.depth:
                raise HostError(f"chip {c.i}: read-out does not end")

    def grid_number(self, ref, other):
        """Step 5 (i): read-outs ref, other, ref right after an output time; SEQ of the last samples equal."""
        for rnd in range(10):
            self.b.wait_fall(ref.i, 2.0e6)
            n1 = self.readout(ref)
            n2 = self.readout(other)
            n3 = self.readout(ref)
            self.use_pending(ref)
            self.use_pending(other)
            df = [self.read(x, D["A_DFLAG"]) for x in (ref, other)]
            if n3 or max(n1, n2) >= ref.depth or any(f & DF_OVR for f in df):
                for x, f in zip((ref, other), df):
                    if f & DF_OVR:
                        self.write(x, D["A_DFLAG"], DF_OVR)
                continue
            if not ref.words or not other.words:
                continue
            ok = ref.words[-1][0] == other.words[-1][0]
            self.event(ref.i, "grid_i", ok=ok, seq_ref=ref.words[-1][0], seq_other=other.words[-1][0], rounds=rnd + 1)
            self.log(f"  step 5 (i) round {rnd + 1}: last SEQ chip {ref.i} {ref.words[-1][0]}, chip {other.i} "
                     f"{other.words[-1][0]} -> {'equal' if ok else 'DIFFERENT'}")
            return ok
        raise HostError("step 5 (i): no round counted in 10 (rule (d))")

    def grid_phase(self, ref, other, resolution_ns=1.0):
        """Step 5 (ii), time-stamping: after a fall of ref, both read out to the empty word, both DRDY_N High before
        the predicted next output time, then the next falls of both stamped: |difference| <= resolution + 2 MCLK."""
        for rnd in range(10):
            ok, t_fall = self.b.wait_fall(ref.i, 2.0e6)
            if not ok:
                continue
            self.readout(ref)
            self.readout(other)
            self.use_pending(ref)
            self.use_pending(other)
            d = self.b.drdy()
            if self.b.t >= t_fall + OUT_NS or d[ref.i] != 1 or d[other.i] != 1:
                continue
            ta, tb = self.b.wait_falls_both(1.2e6)
            if ta is None or tb is None:
                continue
            ta, tb = (ta, tb) if ref.i == 0 else (tb, ta)
            diff = tb - ta
            good = abs(diff) <= resolution_ns + 2 * TMCLK
            self.event(ref.i, "grid_ii", ok=good, diff_ns=diff, rounds=rnd + 1)
            self.log(f"  step 5 (ii) round {rnd + 1}: DRDY_N falls chip {ref.i} {ta:.1f} ns, chip {other.i} {tb:.1f} ns, "
                     f"difference {diff:+.1f} ns -> {'aligned' if good else 'NOT ALIGNED'}")
            self.drain(ref)
            self.drain(other)
            return good, diff
        raise HostError("step 5 (ii): no round counted in 10 (rule (d))")

    # ------------------------------------------------------------------ step 7
    def mean_after(self, c, n, use_ovl=False, after_nr=False):
        """The mean of the next n samples without CHANGED (and without OVL unless use_ovl); (mean, any OVL). After an
        APPLY_NR the words before its first CHANGED word were stored before its tick (old M) and are left out; the run
        of CHANGED words is counted (3 + T_ELEC expected)."""
        got, ovl = [], False
        start = len(c.words)
        seen_chg = not after_nr
        n_chg = 0
        t_lim = self.b.t + (n + 12) * OUT_NS
        while len(got) < n and self.b.t < t_lim:
            if self.b.wait_low(c.i, 1.5e6):
                self.drain(c)
                self.read(c, D["A_STATUS"])               # a later header decides the waiting words
            for seq, d, st in c.words[start:]:
                if st & S_CHG:
                    seen_chg = True
                    n_chg += 1
                    continue
                if not seen_chg:
                    continue
                if st & S_OVL:
                    ovl = True
                    if not use_ovl:
                        continue
                got.append(d)
            start = len(c.words)
            self.service(busy=c)
        if len(got) < n:
            raise HostError(f"chip {c.i}: only {len(got)} usable samples")
        if after_nr:
            self.changed_runs.append(n_chg)
        return sum(got[:n]) / n, ovl

    def apply_and_measure(self, c, m, nr=False, n=3, use_ovl=False):
        self.drain(c)                                     # read out before the command (no reads until its ERR)
        self.use_pending(c)
        if nr:
            self.write_settings(c, self.offset_regs(m))
            r = self.command(c, D["CMD_APPLY_NR"], shadow=m)
            if r:
                return None, r
        else:
            self.write_settings(c, self.offset_regs(m))
            r = self.command(c, D["CMD_APPLY"], shadow=m)
            if r:
                return None, r
            c.run = False
            c.seq_break = True
            c.pending = []
            self.wait_run(c)
        c.m = m
        mean, ovl = self.mean_after(c, n, use_ovl=use_ovl, after_nr=nr)
        return (mean, ovl), 0

    def search(self, c):
        """Step 7 with T_ELEC 0 (an ideal electrode: no settling to wait for)."""
        lo, hi = -1023, 1023
        probes = []
        m = 0
        while True:
            (mean, ovl), _ = self.apply_and_measure(c, m, use_ovl=True)
            probes.append((m, mean, ovl))
            self.event(c.i, "probe", stage="coarse", m=m, mean=mean, ovl=ovl)
            self.log(f"  chip {c.i} coarse: M {m:+5d} -> mean {mean / NOMINAL_STEP_LSB:+8.3f} nominal steps"
                     f"{' (OVL)' if ovl else ''}")
            if abs(mean) < OVL_RULE_LSB and not ovl:
                break
            if mean > 0:
                lo = m
            else:
                hi = m
            if hi - lo <= 1:
                break
            m = (lo + hi) // 2
            if len(probes) > 14:
                raise HostError(f"chip {c.i}: the coarse search does not end")
        est = max(-1023, min(1023, m + round(mean / NOMINAL_STEP_LSB)))
        if est != m:
            (mean, ovl), _ = self.apply_and_measure(c, est, n=self.fine_n)
            m = est
            self.event(c.i, "probe", stage="fine", m=m, mean=mean, ovl=ovl)
            self.log(f"  chip {c.i} fine: APPLY M {m:+5d} -> {mean / NOMINAL_STEP_LSB:+8.3f}")
        else:
            mean, ovl = self.mean_after(c, self.fine_n)
            self.log(f"  chip {c.i} fine: M {m:+5d} -> {mean / NOMINAL_STEP_LSB:+8.3f}")
        best = (abs(mean), m)
        for nb in (m + 1, m - 1):
            if abs(nb) > 1023:
                continue
            # APPLY_NR moves one step from the present M
            cur = c.m
            path = [cur + (1 if nb > cur else -1) * k for k in range(1, abs(nb - cur) + 1)]
            res = None
            for p in path:
                res, r = self.apply_and_measure(c, p, nr=True, n=self.fine_n if p == nb else 1)
                if r:
                    raise HostError(f"chip {c.i}: APPLY_NR to {p} refused (0x{r:02x})")
            self.log(f"  chip {c.i} fine: APPLY_NR M {nb:+5d} -> {res[0] / NOMINAL_STEP_LSB:+8.3f}")
            self.event(c.i, "probe", stage="fine_nr", m=nb, mean=res[0], ovl=res[1])
            best = min(best, (abs(res[0]), nb))
        target = best[1]
        while c.m != target:
            p = c.m + (1 if target > c.m else -1)
            _, r = self.apply_and_measure(c, p, nr=True, n=1)
            if r:
                raise HostError(f"chip {c.i}: APPLY_NR to {p} refused")
        self.handle_alert(c)                              # step 8: DFLAG.OVL of the coarse search written back
        self.log(f"  chip {c.i}: offset search done, M {c.m:+d} ({len(probes)} coarse probes)")
        self.event(c.i, "search_done", m=c.m)
        return c.m

    # ------------------------------------------------------------------ steps 8, 9, 10
    def handle_alert(self, c):
        """Step 8: ERR read and the handled bits written back; DFLAG.OVL written back."""
        c.need_err = False
        err = self.read(c, D["A_ERR"])
        if err:
            self.log(f"  chip {c.i}: step 8: ERR 0x{err:02x} handled and written back")
            self.write(c, D["A_ERR"], err)
        df = self.read(c, D["A_DFLAG"])
        if df:
            self.write(c, D["A_DFLAG"], df)
        return err, df

    def soft_reset(self, c, m):
        """Step 9, then steps 2-5 (the offset DAC written before START: the value found by step 7)."""
        err = self.read(c, D["A_ERR"])
        if err:
            self.write(c, D["A_ERR"], err)
        self.drain(c)
        self.use_pending(c)
        c.section = True
        for _ in range(3):
            self.write(c, D["A_COMMAND"], D["CMD_SOFT_RESET"], kind="command")
            c.run = False
            self.b.wait(1000 - self.b.t_idle + 100)          # CS_N high >= 1 us
            crc_on = self.mode_check(c)
            c.crc = crc_on
            if crc_on:
                e = self.read(c, D["A_ERR"])
            else:
                e = self.read_nocrc(c, D["A_ERR"])
            if e & RESET_FLAG:
                break
            self.log(f"  chip {c.i}: SOFT_RESET not executed (ERR 0x{e:02x}): sent again")
        else:
            raise HostError(f"chip {c.i}: SOFT_RESET not confirmed")
        c.section = False
        c.crc = False
        c.pending = []
        self.log(f"  chip {c.i}: SOFT_RESET confirmed (CRC off, RESET_FLAG 1): steps 2-5 again")
        self.event(c.i, "soft_reset")
        return self.bring_up(c, m=m)

    def stop(self, c):
        r = self.command(c, D["CMD_STOP"])
        c.run = False
        return r


# ====================================================================== the scenario of VER-06
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vvp", default=os.path.join(ROOT, "build", "host_r15", "tb_host_r15.vvp"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "host_r15"))
    ap.add_argument("--off0", type=int, default=87650)
    ap.add_argument("--off1", type=int, default=-45321)
    args = ap.parse_args()
    logf = open(os.path.join(args.out, "host_r15.log"), "w")
    t_wall = time.time()

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n")
        logf.flush()

    checks, fails = [0], []

    def check(cond, what):
        checks[0] += 1
        if not cond:
            fails.append(what)
            log(f"FAIL: {what}")

    b = Board(args.vvp, args.out)
    line = Line(b, log)
    h = Host(b, line, 2, log)
    c0, c1 = h.chips
    try:
        # the electrodes: offsets per chip, a common 37 Hz signal of 40 uV, 2 uV rms noise
        b.analog(0, args.off0, 40, 37000, 2)
        b.analog(1, args.off1, 40, 37000, 2)
        # step 1: RESET_N low, then high; CS_N high >= 10 MCLK after
        b.reset(0)
        b.wait(5000)
        b.reset(1)
        b.wait(20 * TMCLK)
        log("== steps 2-5: both chips from the shared RESET_N")
        for c in (c0, c1):
            idv, ver = h.bring_up(c)
            log(f"  chip {c.i}: ID 0x{idv:02x} VERSION 0x{ver:02x} FIFO_DEPTH {c.depth}, RUN at {b.t / 1e6:.3f} ms")
        log("== step 5: the grids of the two chips")
        check(h.grid_number(c0, c1), "step 5 (i): SEQ equal after the bring-up")
        ok, diff = h.grid_phase(c0, c1)
        check(ok, "step 5 (ii): DRDY_N falls aligned after the bring-up")
        log("== step 7: the offset search on each chip (the other chip read meanwhile)")
        ms = []
        offs = (args.off0, args.off1)
        for c in (c0, c1):
            ms.append(h.search(c))
            o = b.oracle(c.i)
            dc = offs[c.i] - 301.0 * o["dac_steps"]
            log(f"  chip {c.i}: the pins' DAC {o['dac_steps']:+d} steps, DC residual {dc:+.0f} uV (the board's step 301 uV), "
                f"nearest M {round(offs[c.i] / 301.0):+d}")
            check(o["dac_steps"] == c.m, f"chip {c.i}: the pins' DAC equals the host's M")
            check(abs(dc) <= 0.5 * 301.0, f"chip {c.i}: DC residual within half a step after the search")
        log("== step 6: 40 ms of samples on both chips")
        n0 = [len(c.words) for c in (c0, c1)]
        h.sleep(40e6)
        for c in (c0, c1):
            h.read(c, D["A_STATUS"])
            new = c.words[n0[c.i]:]
            check(len(new) >= 38, f"chip {c.i}: {len(new)} samples in 40 ms")
            check(all(st == S_VALID for _, _, st in new), f"chip {c.i}: steady samples carry VALID alone")
            mean = sum(d for _, d, _ in new) / max(1, len(new))
            o = b.oracle(c.i)
            lsb_uv = 31 * 287.02e-6 / 0.5 * 2 ** 18
            exp = (offs[c.i] - 301.0 * o["dac_steps"]) * lsb_uv
            log(f"  chip {c.i}: {len(new)} samples, mean {mean:+.0f} LSB, the DC residual gives {exp:+.0f} LSB "
                f"(difference {(mean - exp) / lsb_uv:+.1f} uV; the 37 Hz 40 uV signal over 40 ms moves it <= 9 uV)")
            check(abs(mean - exp) < 15.0 * lsb_uv, f"chip {c.i}: the mean follows the DC residual within 15 uV")
        log("== faults on chip 0 (VER-06)")
        # a MOSI bit of a write's data: CRC_ERR, the write not done; the confirmation finds it and writes again
        line.arm(0, "mosi", "write", byte=1, bit=3)
        h.write_settings(c0, [(D["A_ALERT_MASK"], 0xFF)])
        check(h.read(c0, D["A_ALERT_MASK"]) == 0xFF, "CRC_ERR: the setting written again")
        # a register read cut after 12 bits: FRAME_ERR; the host's CRC fails, it reads again; step 8 clears
        line.arm(0, "cut", "read", nbits=12)
        v = h.read(c0, D["A_CFG_GEN"])
        check(v == b.oracle(0)["cfg_gen"], "cut read: read again with CRC")
        err, _ = h.handle_alert(c0)
        check(err & FRAME_ERR, "cut read: FRAME_ERR seen by step 8")
        # a MISO bit of a sample: the host's CRC fails before CS_N rises: 8 more SCLK, the same sample read again
        g0 = c0.n_seq_gaps
        rr0 = c0.n_reread
        line.arm(0, "miso", "sample", byte=5, bit=2)
        h.sleep(5e6)
        h.read(c0, D["A_STATUS"])
        check(c0.n_reread == rr0 + 1, "MISO bit of a sample: read again")
        check(c0.n_seq_gaps == g0, "MISO bit of a sample: no SEQ gap")
        # 8 extra SCLK after a whole sample: not popped, CRC good at the host: dropped by the FRAME_ERR rule
        d0 = c0.n_drop_frame_err
        line.arm(0, "extra", "sample", bits=8)
        h.sleep(5e6)
        h.handle_alert(c0)
        h.sleep(3e6)
        h.read(c0, D["A_STATUS"])
        check(c0.n_drop_frame_err == d0 + 1, "extra SCLK: the word of that frame dropped")
        check(c0.n_seq_gaps == g0, "extra SCLK: no SEQ gap, no duplicate")
        # STATE_ERR: START sent in RUN (refused by the table; the host's error on purpose): step 4 returns it, the
        # chip stays in RUN and its samples go on
        gen = b.oracle(0)["cfg_gen"]
        r = h.command(c0, D["CMD_START"])
        check(r & STATE_ERR, f"START in RUN: STATE_ERR (0x{r:02x})")
        check(h.read(c0, D["A_STATE"]) == D["ST_RUN"], "START in RUN: still RUN")
        check(b.oracle(0)["cfg_gen"] == gen, "START in RUN: nothing applied (CFG_GEN unchanged)")
        # APPLY_NR of two steps: CFG_ERR, nothing applied
        h.write_settings(c0, h.offset_regs(c0.m + 2))
        r = h.command(c0, D["CMD_APPLY_NR"], shadow=c0.m + 2)
        check(r & CFG_ERR, f"APPLY_NR of two steps: CFG_ERR (0x{r:02x})")
        check(h.active_m(c0) == c0.m, "APPLY_NR of two steps: the active M unchanged")
        h.write_settings(c0, h.offset_regs(c0.m))
        h.sleep(4e6)
        log("== step 9 on chip 1 (chip 0 read meanwhile), then step 5 again")
        gen_before = b.oracle(1)["cfg_gen"]
        h.soft_reset(c1, ms[1])
        o1 = b.oracle(1)
        check(o1["dac_steps"] == ms[1], "chip 1: the offset DAC restored after SOFT_RESET")
        check(o1["cfg_gen"] == 1, f"chip 1: CFG_GEN 1 after SOFT_RESET and START (was {gen_before})")
        check(h.grid_number(c0, c1), "step 5 (i): SEQ equal after chip 1's SOFT_RESET")
        ok, diff = h.grid_phase(c0, c1)
        check(ok, "step 5 (ii): DRDY_N falls aligned after chip 1's SOFT_RESET")
        h.sleep(10e6)
        log("== step 10: STOP")
        for c in (c0, c1):
            h.read(c, D["A_STATUS"])
            h.stop(c)
            h.handle_alert(c)
        for c in (c0, c1):
            o = b.oracle(c.i)
            check(o["state"] == D["ST_IDLE"], f"chip {c.i}: IDLE at the end")
            check(o["err"] == 0, f"chip {c.i}: ERR 0 at the end (0x{o['err']:02x})")
            seqs = [s for s, _, _ in c.words]
            dup = len(seqs) - len(set(seqs))
            log(f"  chip {c.i}: {len(c.words)} samples used, SEQ gaps {c.n_seq_gaps}, duplicates {dup}, re-reads "
                f"{c.n_reread}, words dropped by FRAME_ERR {c.n_drop_frame_err}, empty words {c.n_empty}")
        check(c0.n_seq_gaps == 0 and c1.n_seq_gaps == 0, "SEQ gaps: none (a jump only after START / APPLY)")
        log(f"  CHANGED runs after each APPLY_NR: {h.changed_runs}")
        check(h.changed_runs and all(n == 3 for n in h.changed_runs), "every APPLY_NR: 3 + T_ELEC = 3 samples with CHANGED")
        check(b.oracle(0)["contention"] == 0, "no MISO contention")
        check(len(line.faults) == 0, f"every armed fault injected ({len(line.done)})")
    except HostError as e:
        fails.append(f"host error: {e}")
        log(f"FAIL: host error: {e}")
    finally:
        try:
            b.quit()
        except Exception:
            b.proc.kill()
    sim_ms = b.t / 1e6
    import json
    with open(os.path.join(args.out, "host_events.json"), "w") as fj:
        json.dump(dict(offsets_uv=[args.off0, args.off1], end_ns=b.t, events=h.ev,
                       faults=[dict(t=t_, chip=ch, kind=k, frame=w) for t_, ch, k, w in line.done],
                       words={str(c.i): [[t_, s, d, st] for t_, (s, d, st) in zip(c.word_t, c.words)] for c in h.chips},
                       changed_runs=h.changed_runs, checks=checks[0], fails=fails), fj)
    log(f"host_r15: {checks[0]} checks, {len(fails)} failures, {b.n_cmd} board commands, {sim_ms:.1f} ms simulated, "
        f"{time.time() - t_wall:.0f} s")
    log("PASS: host_r15 (VER-06)" if not fails else "FAIL: host_r15")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
