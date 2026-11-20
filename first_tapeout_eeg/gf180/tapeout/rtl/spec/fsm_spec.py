#!/usr/bin/env python3
"""The digital control's state machines as one machine-readable specification (11/19, requirements draft r3).

The transition tables below are the specification; the diagrams (Mermaid) and the tables in
documentation/gf180_digital_control_requirements_20261119.md are generated from them, and `check` proves the
properties listed in CHECKS on them, so the drawings, the tables and the checked logic cannot drift apart.

Machines:
  SEQ   the sequencer (start-up, data start, applying settings, AFE_RST). Its tick is once per chopper period, at
        frame cycle 24 (outputs change at e25) of the frame in the middle of chopper phase A (frame 1 of 8 at
        128 kHz, 3 of 16 at 64 kHz),
        so AFE_RST and every analog setting change at one fixed chopper phase, away from every ADC and chopper edge.
        At most one command is pending (a second one is rejected at the SPI write); a tick resolves that command
        and the state's timer by SEQ_PRIORITY. OUT (a CIC output time, frame cycle 8) is handled at its own MCLK
        cycle, which never coincides with a tick. RST is asynchronous (RESET_N) or SOFT_RESET's commit cycle, after
        which the reset follows at the next edge: in that cycle the tick and the output time change no state and take
        no control action (no output takes a value that the reset withdraws right after). The data path runs on
        RESET_N alone: that output time is still counted (SEQ) and discarded, and in ALIGN the CIC's clear, which the
        CIC takes at the edge that starts the output-time cycle (from cic_arm in the cycle before, where a commit
        cancels it), has already been taken (audit round 5).
  SPI   one SPI transaction at byte level (CS_N low ... CS_N high).
  FIFO  the sample FIFO's occupancy with push, pop and flush in the same MCLK cycle (depth DEPTH).

Cell notation in a table (state, event):
  IMP   the event cannot occur in that state (checked against POSSIBLE: it is an error to mark a possible event IMP)
  IGN   the event can occur and is accepted without any effect
  [B(guard, actions, next), ...]   guarded branches: the guards must be mutually exclusive and exhaustive over their
        condition variables (checked by enumeration); next None = stay in the state.

Usage:
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/fsm_spec.py check    (exit 1 on any violation)
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/fsm_spec.py gen      (check, then write the generated files)
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/fsm_spec.py selftest (each listed specification error, put
                                                                              in on purpose, must be detected)
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/fsm_spec.py render   (PNG of the generated diagrams; needs
                                                                              Google Chrome)
"""
import itertools
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
DOC = os.path.join(REPO, "documentation", "gf180_digital_control_requirements_20261119.md")

IMP, IGN = "IMP", "IGN"


def B(guard, actions=(), nxt=None):
    return dict(guard=guard, actions=list(actions), next=nxt)


ALWAYS = "1"
FLAGS = {"CFG_ERR", "STATE_ERR", "OVERRUN", "FRAME_ERR", "CRC_ERR", "ADDR_ERR"}   # error flags: always executed
DATA = {"seq_inc", "discard"}                                                     # data-path bookkeeping: always

# =====================================================================================================================
# Sequencer
# =====================================================================================================================
SEQ_STATES = [
    # name, STATE code, parent composite, AFE_RST, timer, meaning
    ("RESET", None, None, 1, None, "リセット中（RESET_N = 0、またはソフトウェアリセット）。全レジスタは既定値、SPI は応答しない"),
    ("IDLE", 0, None, 1, None, "待機。設定をシャドウへ書く。変換の出力は捨てる"),
    ("WARMUP", 1, "ACTIVE", 1, "T_WARM", "バイアスと VCM の整定を待つ"),
    ("RECOVER", 2, "AFE_ON", 0, "T_REC", "AFE_RST の解除後、ADC が過負荷から戻るのを待つ"),
    ("WAIT_E", 3, "AFE_ON", 0, "T_ELEC", "電極の整定を待つ（T_ELEC > 0 のときのみ）"),
    ("ALIGN", 4, "AFE_ON", 0, None, "次の出力の時刻を待ち、その時刻に CIC をクリアする"),
    ("FILL", 5, "AFE_ON", 0, None, "CIC の充填。最初の有効な出力を待つ"),
    ("RUN", 6, "AFE_ON", 0, None, "変換。有効な出力ごとに FIFO へ格納する"),
    ("PRE", 7, "ACTIVE", 0, "T_PRE", "一括反映の直後、AFE_RST の前の待ち"),
    ("PULSE", 8, "ACTIVE", 1, "T_RST", "AFE_RST のワンショット"),
]
SEQ_COMPOSITES = {           # name: (parent, initial substate, meaning)
    "ACTIVE": (None, "WARMUP", "START 後の動作中（STOP で IDLE へ）"),
    "AFE_ON": ("ACTIVE", "RECOVER", "AFE が動作している状態（APPLY で PRE へ）"),
}
SEQ_EVENTS = [
    ("RST", "RESET_N = 0、または SOFT_RESET（どの時点でも。SOFT_RESET の確定のサイクルでは、tick と出力の時刻による状態の変化と制御の動作を取らない。その出力の時刻もデータの経路として数えて捨て、ALIGN の CIC のクリアは出力の時刻のサイクルの始まりの縁で済んでいる）"),
    ("REL", "リセットの解除"),
    ("STOP", "命令 STOP"),
    ("START", "命令 START"),
    ("APPLY", "命令 APPLY（AFE_RST のパルスを伴う一括反映）"),
    ("APPLY_NR", "命令 APPLY_NR（パルスなしの一括反映）"),
    ("FLUSH", "命令 FLUSH（FIFO を空にする）"),
    ("TMR", "その状態のタイマの満了"),
    ("OUT", "CIC の出力の時刻（1 ms ごと）"),
]
SEQ_PRIORITY = ["STOP", "START", "APPLY", "APPLY_NR", "FLUSH", "TMR"]                  # within one tick, high first
SEQ_COMMANDS = ["START", "STOP", "APPLY", "APPLY_NR", "FLUSH"]                        # at most one per tick
SEQ_CONDS = {
    "cfg_ok": "シャドウの設定が整合（オフセット DAC の M が、選んだ範囲の上限以下）",
    "nr_ok": "シャドウとアクティブの違いが、オフセット DAC の符号付きの値 (1 − 2 S) × M の ±1 段のみ（範囲は同じ）",
    "t_elec0": "T_ELEC = 0",
    "valid": "CIC の出力が有効（クリアのあと 3 個目以降）",
}
SEQ_ACTIONS = {
    "apply": "シャドウからアクティブへ一括反映（オフセット DAC、トリム、チョッパ、BLANK、試験の設定）",
    "flush": "FIFO を空にする",
    "cic_clear": "CIC をクリアする（出力の時刻に合わせて行うので、格子は変わらない）",
    "store": "出力を FIFO へ格納する（DRDY）。満杯なら FIFO が新しいサンプルを捨てて OVERRUN を立てる（第 5.3 節、fifo_step）",
    "discard": "出力を捨てる",
    "seq_inc": "SEQ に 1 を加える（SEQ は RESET_N の解除からの出力の時刻の番号。SOFT_RESET でも変えない）",
    "mark": "このあとの 3 ＋ T_ELEC 個の出力に CHANGED を付ける（反映をまたぐ sinc³ の窓 3 個と、電極の整定 T_ELEC（1 ms ＝ 出力 1 個の単位））。残っている印のほうが長ければ、その長さを保つ（前の 1 段の電極の整定が続いている）。RUN を出ると残りは取り消す（次の RUN はクリアした CIC から始まり、その窓は反映をまたがない）",
    "CFG_ERR": "エラー CFG_ERR を立てる（命令は実行しない）",
    "STATE_ERR": "エラー STATE_ERR を立てる（命令は実行しない）",
    "restart": "その状態のタイマを最初から数え直す（同じ tick のタイマの満了は取り消す）",
}


def _seq_table():
    t = {}
    names = [s[0] for s in SEQ_STATES]
    timed = {s[0] for s in SEQ_STATES if s[4]}
    for s in names:
        # defaults for every state but RESET; overridden below
        t[(s, "RST")] = [B(ALWAYS, [], "RESET")]
        t[(s, "REL")] = IMP
        t[(s, "START")] = [B(ALWAYS, ["STATE_ERR"])]
        t[(s, "STOP")] = [B(ALWAYS, [], "IDLE")]
        # with a pulse: the data restart (like START), so the FIFO is emptied of the samples of the old setting
        t[(s, "APPLY")] = [B("cfg_ok", ["apply", "flush"], "PRE"), B("not cfg_ok", ["CFG_ERR"])]
        # AFE running: without a pulse only a one-step change of the offset DAC (the operating 1-step tracking)
        t[(s, "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
        t[(s, "FLUSH")] = [B(ALWAYS, ["flush"])]
        t[(s, "TMR")] = IMP if s not in timed else None
        t[(s, "OUT")] = [B(ALWAYS, ["discard", "seq_inc"])]
    # RESET: nothing is served; only the release leaves it. An output time can fall inside a SOFT_RESET (the CIC
    # and SEQ run from RESET_N alone): it is counted like in IDLE
    for e, _ in SEQ_EVENTS:
        t[("RESET", e)] = IGN
    t[("RESET", "REL")] = [B(ALWAYS, [], "IDLE")]
    t[("RESET", "TMR")] = IMP
    t[("RESET", "OUT")] = [B(ALWAYS, ["discard", "seq_inc"])]
    # IDLE
    t[("IDLE", "START")] = [B("cfg_ok", ["apply", "flush"], "WARMUP"), B("not cfg_ok", ["CFG_ERR"])]
    t[("IDLE", "STOP")] = IGN
    # IDLE and WARMUP hold the AFE in reset: any consistent change is applied without a pulse. In WARMUP the wait
    # starts again, so that AFE_RST is never released less than T_WARM (>= T_RST) after a change
    for st in ("IDLE", "WARMUP"):
        acts = ["apply"] if st == "IDLE" else ["apply", "restart"]
        t[(st, "APPLY")] = [B("cfg_ok", acts), B("not cfg_ok", ["CFG_ERR"])]
        t[(st, "APPLY_NR")] = [B("cfg_ok", acts), B("not cfg_ok", ["CFG_ERR"])]
    t[("WARMUP", "TMR")] = [B(ALWAYS, [], "RECOVER")]
    # RECOVER / WAIT_E
    t[("RECOVER", "TMR")] = [B("t_elec0", [], "ALIGN"), B("not t_elec0", [], "WAIT_E")]
    t[("WAIT_E", "TMR")] = [B(ALWAYS, [], "ALIGN")]
    # an offset step before RUN: the electrode settles again (T_ELEC) before the clear (one step at a high-impedance
    # electrode is about 3 mV at the input and settles with Re x Ce; gf180_electrode_dc_20261022.md)
    t[("WAIT_E", "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply", "restart"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    t[("ALIGN", "APPLY_NR")] = [B("cfg_ok and nr_ok and t_elec0", ["apply"]),
                                B("cfg_ok and nr_ok and not t_elec0", ["apply"], "WAIT_E"),
                                B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    # ALIGN: the CIC is cleared at the next output time, keeping the output grid
    t[("ALIGN", "OUT")] = [B(ALWAYS, ["cic_clear", "discard", "seq_inc"], "FILL")]
    # FILL: an unpulsed APPLY_NR restarts the clear, so no stored window ever straddles a change
    t[("FILL", "APPLY_NR")] = [B("cfg_ok and nr_ok and t_elec0", ["apply"], "ALIGN"),
                               B("cfg_ok and nr_ok and not t_elec0", ["apply"], "WAIT_E"),
                               B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    t[("FILL", "OUT")] = [B("valid", ["store", "seq_inc"], "RUN"), B("not valid", ["discard", "seq_inc"])]
    # RUN
    t[("RUN", "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply", "mark"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    t[("RUN", "OUT")] = [B(ALWAYS, ["store", "seq_inc"])]
    # PRE / PULSE: a further APPLY waits for READY (rejected), the pulse is not stretched
    for s, nxt in (("PRE", "PULSE"), ("PULSE", "RECOVER")):
        t[(s, "APPLY")] = [B(ALWAYS, ["STATE_ERR"])]
        t[(s, "APPLY_NR")] = [B(ALWAYS, ["STATE_ERR"])]
        t[(s, "TMR")] = [B(ALWAYS, [], nxt)]
    return t


def seq_possible(s, e):
    timed = {x[0] for x in SEQ_STATES if x[4]}
    if e == "REL":
        return s == "RESET"
    if e == "TMR":
        return s in timed
    if e == "OUT":
        return True                   # also in RESET: during a SOFT_RESET the CIC and SEQ keep running (RESET_N)
    return True                       # RST and commands can arrive at any time


SEQ = dict(name="SEQ", states=SEQ_STATES, composites=SEQ_COMPOSITES, events=SEQ_EVENTS, conds=SEQ_CONDS,
           actions=SEQ_ACTIONS, table=_seq_table(), possible=seq_possible, constraint=lambda env: True,
           initial="RESET")

# =====================================================================================================================
# SPI transaction (byte level)
# =====================================================================================================================
SPI_STATES = [
    ("IDLE", None, None, None, None, "CS_N = 1。MISO は高インピーダンス"),
    ("HDR", None, "FRAME", None, None, "先頭バイト。MOSI は R/W とアドレス、MISO は STATUS"),
    ("RREG", None, "FRAME", None, None, "レジスタの読み出し（CRC 無効時はアドレスを自動加算して連続）"),
    ("RCRC", None, "FRAME", None, None, "CRC 有効時、データ 1 バイトのあとの CRC"),
    ("RDONE", None, "FRAME", None, None, "CRC 付きの読み出しの完了"),
    ("RSMP", None, "FRAME", None, None, "サンプルの窓の読み出し（先頭バイトのあとの 7 バイト：サンプルの状態、SEQ 2、DATA 3、CRC（先頭バイト 0xC0 と 6 バイトの CRC-8）。フレームは 8 バイト）"),
    ("SDONE", None, "FRAME", None, None, "サンプルの 8 バイト（先頭バイトと 7 バイト）の完了（CS_N の立ち上がりで FIFO から取り出す）"),
    ("WDAT", None, "FRAME", None, None, "書き込みのデータ 1 バイト"),
    ("WCRC", None, "FRAME", None, None, "CRC 有効時の CRC の受信"),
    ("WDONE", None, "FRAME", None, None, "書き込みのフレームの完了（CS_N の立ち上がりで確定）"),
    ("OVF", None, "FRAME", None, None, "規定より長いフレーム。以後は無視し、MISO は 0"),
]
SPI_COMPOSITES = {
    "FRAME": (None, "HDR", "CS_N が Low の間"),
}
SPI_EVENTS = [
    ("CSF", "CS_N の立ち下がり"),
    ("BIT", "バイトを完了しない SCLK の立ち上がり"),
    ("BYTE", "バイトを完了する SCLK の立ち上がり（8 ビット目）"),
    ("CSR", "CS_N の立ち上がり"),
]
SPI_CONDS = {
    "rw": "先頭バイトの R/W が 1（読み出し）",
    "smp": "アドレスがサンプルの窓",
    "addr_ok": "アドレスが定義済み",
    "crc_en": "CRC が有効",
    "last": "サンプルの最後のバイト（先頭バイトのあとの 7 バイト目、フレームの 8 バイト目）",
    "mid": "バイトの途中（CS_N の立ち上がりの時点で受信したビット数が 8 の倍数でない）",
    "crc_ok": "受信した CRC のバイトが、受け取った先頭バイトとデータの CRC-8 と一致",
    "wr_ok": "書き込み可能なアドレス（定義済みで読み出し専用でなく、試験のレジスタなら解錠済み）",
    "busy": "前の命令がまだ tick で処理されていない間の、命令レジスタへの定義済みの命令（SOFT_RESET を除く）、またはシャドウ（一括反映の対象）とタイマのレジスタへの書き込み（命令が読む値を tick まで変えない）",
    "head": "写した語が FIFO に格納されたサンプルで、写してから取り出しもフラッシュもなく、まだ先頭",
}
SPI_ACTIONS = {
    "load_status": "STATUS を送信のシフトレジスタへ（その時点の値を写す）",
    "snapshot": "FIFO の先頭（空なら空の語）を写す",
    "load_data": "アドレスのデータを送信のシフトレジスタへ",
    "load_zero": "0x00 を送信のシフトレジスタへ",
    "addr_inc": "アドレスに 1 を加える",
    "load_crc": "受け取った先頭バイトと送ったデータのバイトの CRC-8 を送信のシフトレジスタへ",
    "next_byte": "サンプルの次のバイトを送信のシフトレジスタへ",
    "latch_addr": "アドレスを保持",
    "latch_data": "データを保持",
    "latch_crc": "CRC を保持",
    "commit": "書き込みを確定（値の範囲が不正なら RANGE_ERR として書かない。命令レジスタなら命令を次の tick に渡す。ただし SOFT_RESET は直ちにリセット、未定義のコードは CMD_ERR。TEST_KEY は 0x3C で解錠、0x00 で施錠、その他の値は施錠して CMD_ERR）",
    "pop": "FIFO の先頭（送ったサンプル）を取り出す",
    "FRAME_ERR": "エラー FRAME_ERR を立てる",
    "CRC_ERR": "エラー CRC_ERR を立てる（書かない）",
    "ADDR_ERR": "エラー ADDR_ERR を立てる（書かない。読み出しは 0x00）",
    "STATE_ERR": "エラー STATE_ERR を立てる（前の命令が未処理のため、この命令、またはシャドウとタイマへの書き込みを受け付けない）",
}


def _spi_table():
    t = {}
    names = [s[0] for s in SPI_STATES]
    for s in names:
        t[(s, "CSF")] = IMP                                    # CS_N is already low in every state but IDLE
        t[(s, "BIT")] = IGN                                    # bits accumulate in the shift register
        t[(s, "CSR")] = [B("mid", ["FRAME_ERR"], "IDLE"), B("not mid", [], "IDLE")]
    t[("IDLE", "CSF")] = [B(ALWAYS, ["load_status"], "HDR")]
    t[("IDLE", "BIT")] = IGN                                   # SCLK is ignored while CS_N is high
    t[("IDLE", "BYTE")] = IMP
    t[("IDLE", "CSR")] = IMP
    t[("HDR", "BYTE")] = [B("rw and smp", ["snapshot"], "RSMP"),
                          B("rw and not smp and addr_ok", ["load_data"], "RREG"),
                          B("rw and not smp and not addr_ok", ["ADDR_ERR", "load_zero"], "RREG"),
                          B("not rw", ["latch_addr"], "WDAT")]
    t[("RREG", "BYTE")] = [B("crc_en", ["load_crc"], "RCRC"), B("not crc_en", ["addr_inc", "load_data"])]
    t[("RCRC", "BYTE")] = [B(ALWAYS, [], "RDONE")]
    # CRC on: a read that stops before its CRC byte, or a sample read shorter than its 8 bytes, is a frame error, so
    # that a one-bit header error that changes the kind of frame is flagged both ways (a header-only read of a defined
    # register, the status poll, stays legal; a header-only sample read with CRC on is a frame error, an undefined
    # address an ADDR_ERR)
    t[("RCRC", "CSR")] = [B(ALWAYS, ["FRAME_ERR"], "IDLE")]
    t[("RSMP", "CSR")] = [B("mid or crc_en", ["FRAME_ERR"], "IDLE"), B("not mid and not crc_en", [], "IDLE")]
    t[("RSMP", "BYTE")] = [B("not last", ["next_byte"]), B("last", [], "SDONE")]
    t[("WDAT", "BYTE")] = [B("crc_en", ["latch_data"], "WCRC"), B("not crc_en", ["latch_data"], "WDONE")]
    t[("WCRC", "BYTE")] = [B(ALWAYS, ["latch_crc"], "WDONE")]
    t[("OVF", "BYTE")] = IGN
    for s in ("RDONE", "SDONE", "WDONE"):                      # a completed frame: any further bit overflows it
        t[(s, "BIT")] = [B(ALWAYS, [], "OVF")]
        t[(s, "BYTE")] = IMP                                   # the first further bit already left the state
    t[("RDONE", "CSR")] = [B(ALWAYS, [], "IDLE")]
    # only the entry that was sent: not the empty word, and not after a flush (a later sample may be the head by then)
    t[("SDONE", "CSR")] = [B("head", ["pop"], "IDLE"), B("not head", [], "IDLE")]
    t[("WDONE", "CSR")] = [B("(crc_ok or not crc_en) and wr_ok and not busy", ["commit"], "IDLE"),
                           B("(crc_ok or not crc_en) and wr_ok and busy", ["STATE_ERR"], "IDLE"),
                           B("(crc_ok or not crc_en) and not wr_ok", ["ADDR_ERR"], "IDLE"),
                           B("crc_en and not crc_ok", ["CRC_ERR"], "IDLE")]
    # an incomplete write (header only, or a missing data / CRC byte) is a frame error even on a byte boundary
    for s in ("WDAT", "WCRC", "OVF"):
        t[(s, "CSR")] = [B(ALWAYS, ["FRAME_ERR"], "IDLE")]
    return t


def spi_possible(s, e):
    if s == "IDLE":
        return e in ("CSF", "BIT")
    if e == "CSF":
        return False
    if e == "BYTE" and s in ("RDONE", "SDONE", "WDONE"):
        return False
    return True


def spi_constraint(env):
    return not (env.get("smp") and not env.get("addr_ok", 1))  # the sample window is a defined address


SPI = dict(name="SPI", states=SPI_STATES, composites=SPI_COMPOSITES, events=SPI_EVENTS, conds=SPI_CONDS,
           actions=SPI_ACTIONS, table=_spi_table(), possible=spi_possible, constraint=spi_constraint, initial="IDLE")

# =====================================================================================================================
# Generic checks
# =====================================================================================================================
KEYWORDS = {"and", "or", "not"}


def guard_vars(g):
    return sorted(set(re.findall(r"[a-z_][a-z0-9_]*", g)) - KEYWORDS)


def guard_true(g, env):
    return bool(eval(g, {"__builtins__": {}}, dict(env)))


def pick(cell, env):
    """The branch of a cell for the condition values env (IGN / IMP pass through)."""
    if cell is None or cell in (IGN, IMP):
        return cell
    hits = [b for b in cell if guard_true(b["guard"], env)]
    return hits[0] if len(hits) == 1 else None


def all_envs(names, constraint):
    for vals in itertools.product([0, 1], repeat=len(names)):
        env = dict(zip(names, vals))
        if constraint(env):
            yield env


def check_tables(F):
    errs = []
    names = [s[0] for s in F["states"]]
    for s in names:
        for e, _ in F["events"]:
            cell = F["table"].get((s, e))
            where = f"{F['name']} {s}/{e}"
            if cell is None:
                errs.append(f"{where}: the cell is not defined")
                continue
            possible = F["possible"](s, e)
            if cell == IMP and possible:
                errs.append(f"{where}: marked impossible, but the event can occur")
            if cell != IMP and not possible:
                errs.append(f"{where}: the event cannot occur, but the cell is defined")
            if isinstance(cell, list):
                vs = sorted({v for b in cell for v in guard_vars(b["guard"])})
                unknown = [v for v in vs if v not in F["conds"]]
                if unknown:
                    errs.append(f"{where}: undefined conditions {unknown}")
                    continue
                for env in all_envs(vs, F["constraint"]):
                    n = sum(guard_true(b["guard"], env) for b in cell)
                    if n != 1:
                        errs.append(f"{where}: {n} branches hold for {env} (guards must be exclusive and exhaustive)")
                for b in cell:
                    if b["next"] is not None and b["next"] not in names:
                        errs.append(f"{where}: unknown next state {b['next']}")
                    for a in b["actions"]:
                        if a not in F["actions"]:
                            errs.append(f"{where}: undefined action {a}")
    return errs


def check_vocab(F):
    """Every action and condition of the machine's lists is used in its table (no stale entries)."""
    used_a, used_c = set(), set()
    for cell in F["table"].values():
        if isinstance(cell, list):
            for b in cell:
                used_a |= set(b["actions"])
                used_c |= set(guard_vars(b["guard"]))
    errs = [f"{F['name']}: action {a} is defined but never used" for a in F["actions"] if a not in used_a]
    errs += [f"{F['name']}: condition {c} is defined but never used" for c in F["conds"] if c not in used_c]
    return errs


def edges(F):
    out = []
    for (s, e), cell in F["table"].items():
        if isinstance(cell, list):
            for b in cell:
                if b["next"] is not None and b["next"] != s:
                    out.append((s, e, b["guard"], tuple(b["actions"]), b["next"]))
    return out


def reach(F, start, exclude=()):
    seen, todo = {start}, [start]
    E = [x for x in edges(F) if x[1] not in exclude]
    while todo:
        s = todo.pop()
        for (a, _, _, _, b) in E:
            if a == s and b not in seen:
                seen.add(b)
                todo.append(b)
    return seen


def check_graph(F, must_reach, exclude=()):
    """Every state reachable from the initial state; from every state each target in must_reach is reachable
    without the excluded events (the sequencer's RST: liveness must not rely on a reset)."""
    errs = []
    names = [s[0] for s in F["states"]]
    r = reach(F, F["initial"])
    for s in names:
        if s not in r:
            errs.append(f"{F['name']}: state {s} is not reachable from {F['initial']}")
        for target in must_reach:
            if target != s and target not in reach(F, s, exclude):
                errs.append(f"{F['name']}: no path from {s} to {target} without {sorted(exclude)} (dead end)")
    return errs


# =====================================================================================================================
# Sequencer: one tick with simultaneous events, and the properties checked on every combination
# =====================================================================================================================
SEQ_STATE = {s[0]: s for s in SEQ_STATES}


def seq_tick(s, present, env):
    """Next state and executed actions for the events present in one tick (with RST: the reset alone)."""
    nxt, acts, _ = seq_resolve(s, present, env)
    return nxt, acts


# The allowed state changes, written independently of the transition table: (state, the event that moves it) -> the
# allowed next states. A timed wait (WARMUP, RECOVER, WAIT_E, PRE, PULSE) is left only by its own timer, by STOP, or
# (the AFE running) by APPLY with its pulse; FLUSH never moves; START only leaves IDLE; APPLY_NR moves only before
# RUN (back to the electrode wait or the clear); RUN is left only by STOP or APPLY.
SEQ_AFE_ON = ("RECOVER", "WAIT_E", "ALIGN", "FILL", "RUN")
SEQ_EXITS = {("IDLE", "START"): {"WARMUP"},
             ("WARMUP", "TMR"): {"RECOVER"}, ("RECOVER", "TMR"): {"ALIGN", "WAIT_E"}, ("WAIT_E", "TMR"): {"ALIGN"},
             ("PRE", "TMR"): {"PULSE"}, ("PULSE", "TMR"): {"RECOVER"},
             ("ALIGN", "APPLY_NR"): {"WAIT_E"}, ("FILL", "APPLY_NR"): {"ALIGN", "WAIT_E"},
             ("ALIGN", "OUT"): {"FILL"}, ("FILL", "OUT"): {"RUN"}}
SEQ_EXITS.update({(s, "STOP"): {"IDLE"} for s in ("WARMUP", "PRE", "PULSE") + SEQ_AFE_ON})
SEQ_EXITS.update({(s, "APPLY"): {"PRE"} for s in SEQ_AFE_ON})


def seq_resolve(s, present, env):
    """seq_tick, and the event whose branch decided the next state (None if none moved)."""
    t = SEQ["table"]
    if "RST" in present:                         # a reset: no state change, no control action of its cycle
        b = pick(t.get((s, "RST")), env)
        if not isinstance(b, dict):
            return s, [], None
        acts = list(b["actions"])
        if "OUT" in present:                     # the data path (RESET_N): the output time counted and discarded;
            o = pick(t.get((s, "OUT")), env)     # ALIGN's clear was taken at the edge that started this cycle
            acts += (["cic_clear"] if isinstance(o, dict) and "cic_clear" in o["actions"] else []) + ["discard", "seq_inc"]
        return b["next"], acts, "RST"
    br = {e: pick(t.get((s, e)), env) for e in present}       # a missing cell is reported by check_tables
    if "TMR" in br and any(isinstance(b, dict) and "restart" in b["actions"] for e, b in br.items() if e != "TMR"):
        del br["TMR"]                            # the wait starts again: the expiry of this tick no longer holds
        present = [e for e in present if e != "TMR"]
    winner = None
    if "STOP" in present and br["STOP"] is not None and br["STOP"] != IMP:
        winner = "STOP"                          # STOP always wins: it cancels every other transition of the tick
    else:
        for e in SEQ_PRIORITY + ["OUT"]:        # OUT never shares a cycle with a tick event (checked alone)
            b = br.get(e)
            if isinstance(b, dict) and b["next"] is not None and b["next"] != s:
                winner = e
                break
    acts = []
    for e in present:
        b = br[e]
        if not isinstance(b, dict):
            continue
        moves = b["next"] is not None and b["next"] != s
        if e == winner or not moves:
            acts += b["actions"]
        else:                                    # a transition that lost: only its flags and data bookkeeping
            acts += [a for a in b["actions"] if a in FLAGS or a in DATA]
    nxt = s
    if winner and isinstance(br[winner], dict) and br[winner]["next"] is not None:
        nxt = br[winner]["next"]
    return nxt, acts, winner


def seq_properties(s, present, env, nxt, acts, winner=None):
    """Each returns an error string or None."""
    afe = lambda x: SEQ_STATE[x][3]
    P = []
    if nxt != s and nxt not in SEQ_EXITS.get((s, winner), ()):
        P.append(f"{s} -> {nxt} by {winner}: not an allowed exit (SEQ_EXITS: a timed wait is left only by its timer, "
                 f"STOP or a pulsed APPLY; FLUSH never moves; START only from IDLE; RUN only by STOP or APPLY)")
    if afe(s) == 1 and afe(nxt) == 0 and nxt != "RECOVER":
        P.append("AFE_RST is released without passing RECOVER (ADC recovery wait)")
    if "apply" in acts and afe(s) == 1 and afe(nxt) == 0:
        P.append("settings applied in the tick that releases AFE_RST (no reset after the change)")
    if "apply" in acts and nxt == s and afe(s) == 1 and SEQ_STATE[s][4] and "restart" not in acts:
        P.append("settings applied while AFE_RST is held, without restarting the wait before its release")
    if "restart" in acts and not SEQ_STATE[s][4]:
        P.append("restart in a state without a timer")
    if "store" in acts and not (s == "RUN" or (s == "FILL" and nxt == "RUN")):
        P.append("a sample is stored outside RUN")
    if nxt == "RUN" and s != "RUN" and not (s == "FILL" and "store" in acts):
        P.append("RUN is entered other than with the first valid output")
    if "apply" in acts and s == "RUN" and nxt == "RUN" and "mark" not in acts:
        P.append("settings change in RUN without CHANGED marks")
    if "apply" in acts and s == "FILL" and nxt == "FILL":
        P.append("settings change inside a CIC window being filled")
    if "apply" in acts and not env.get("cfg_ok", 1):
        P.append("an inconsistent configuration is applied")
    if "cic_clear" in acts and not (s == "ALIGN" and nxt == "FILL"):
        P.append("the CIC is cleared off the output grid")
    if nxt == "FILL" and s != "FILL" and "cic_clear" not in acts:
        P.append("FILL entered without clearing the CIC")
    if s == "IDLE" and nxt == "WARMUP" and not {"apply", "flush"} <= set(acts):
        P.append("START without applying the settings and emptying the FIFO")
    if nxt == "PULSE" and s != "PULSE" and s != "PRE":
        P.append("AFE_RST pulse not preceded by PRE")
    if nxt == "PRE" and s != "PRE" and "apply" not in acts:
        P.append("PRE entered without applying settings")
    if nxt == "RECOVER" and s != "RECOVER" and s not in ("WARMUP", "PULSE"):
        P.append("RECOVER entered other than after AFE_RST")
    if "apply" in acts and afe(s) == 0 and nxt != "PRE" and not env.get("nr_ok", 1):
        P.append("a change beyond one offset-DAC step is applied while the AFE runs, without AFE_RST")
    if "flush" in acts and not ((s == "IDLE" and nxt == "WARMUP") or "FLUSH" in present or
                                ("APPLY" in present and nxt == "PRE")):
        P.append("FIFO flushed by something other than START, APPLY (with its pulse) or FLUSH")
    if nxt == "PRE" and s != "PRE" and "flush" not in acts:
        P.append("APPLY with a pulse keeps the samples of the old setting in the FIFO")
    if ("apply" in acts and nxt != "PRE" and s in ("WAIT_E", "ALIGN", "FILL") and not env.get("t_elec0", 1)
            and not (nxt == "WAIT_E" and (s != "WAIT_E" or "restart" in acts))):
        P.append("an offset step before RUN does not wait for the electrode again (T_ELEC)")
    if nxt == "WAIT_E" and s != "WAIT_E" and not (s == "RECOVER" or ("apply" in acts and s in ("ALIGN", "FILL"))):
        P.append("WAIT_E entered other than after RECOVER or an offset step before RUN")
    if "STOP" in present and nxt != "IDLE":
        P.append("STOP does not lead to IDLE")
    if s == "RUN" and nxt not in ("RUN", "IDLE", "PRE"):
        P.append("RUN left other than by STOP or APPLY")
    if s == "RECOVER" and nxt == "ALIGN" and not env.get("t_elec0", 1):
        P.append("T_ELEC > 0 but RECOVER goes to the clear without the electrode wait (WAIT_E)")
    if s == "RECOVER" and nxt == "WAIT_E" and env.get("t_elec0", 0) and "apply" not in acts:
        P.append("T_ELEC = 0 but RECOVER goes to WAIT_E")
    if s == "RUN" and present == ["OUT"] and "store" not in acts:
        P.append("an output time in RUN is not stored")
    if "FLUSH" in present and "flush" not in acts:
        P.append("FLUSH does not empty the FIFO")
    if s == "FILL" and nxt == "RUN" and not env.get("valid", 1):
        P.append("RUN entered with an output that is not valid (the window not yet full)")
    # a command is executed, refused with a flag, or ignored by definition (only STOP in IDLE), judged on the
    # resolved result of the tick, not on its own cell (audit round 5: an IGN cell, and a command losing its
    # transition to the timer by a wrong priority, passed the per-cell form)
    for c in SEQ_COMMANDS:
        if c not in present:
            continue
        cell = SEQ["table"].get((s, c))
        if cell == IGN:
            if (s, c) != ("IDLE", "STOP"):
                P.append(f"command {c} ignored in {s} (no effect and no flag)")
            continue
        b = pick(cell, env)
        if not isinstance(b, dict):
            continue
        flags = {"CFG_ERR", "STATE_ERR"} & set(b["actions"])
        if flags:
            if not flags <= set(acts):
                P.append(f"command {c} refused without its flag in the tick's result")
            continue
        if not b["actions"] and b["next"] in (None, s):
            P.append(f"command {c} silently dropped")
        if not set(b["actions"]) <= set(acts):
            P.append(f"command {c} accepted but its actions not taken ({sorted(b['actions'])} -> {sorted(acts)})")
        if b["next"] not in (None, s) and winner != c:
            P.append(f"command {c} accepted but its transition lost to {winner}")
        if c in ("APPLY", "APPLY_NR") and "apply" not in acts:
            P.append(f"{c} accepted without applying the settings")
    return P


def check_seq_ticks():
    errs, n = [], 0
    timed = {x[0] for x in SEQ_STATES if x[4]}
    for s in [x[0] for x in SEQ_STATES if x[0] != "RESET"]:
        cases = [[c] + (["TMR"] if t else []) for c in SEQ_COMMANDS for t in (0, 1) if t == 0 or s in timed]
        cases += [["TMR"]] if s in timed else []
        cases += [["OUT"]]                      # handled at its own MCLK cycle, never together with a tick
        for present in cases:
            for env in all_envs(list(SEQ_CONDS), lambda e: True):
                nxt, acts, winner = seq_resolve(s, present, env)
                n += 1
                for p in seq_properties(s, present, env, nxt, acts, winner):
                    errs.append(f"SEQ {s} {present} {env}: {p} -> {nxt} {acts}")
                # the same events with a reset in their cycle (SOFT_RESET's commit cycle): RESET, no control action;
                # an output time only counted and discarded (and ALIGN's clear, taken at the start of the cycle)
                nxt, acts, _ = seq_resolve(s, ["RST"] + present, env)
                n += 1
                want = ((["cic_clear"] if s == "ALIGN" else []) + ["discard", "seq_inc"]) if "OUT" in present else []
                if nxt != "RESET" or sorted(acts) != sorted(want):
                    errs.append(f"SEQ {s} {['RST'] + present} {env}: a reset that does not win over the events of "
                                f"its cycle -> {nxt} {acts} (allowed: RESET {want})")
    # RESET (RESET_N low or a SOFT_RESET): only the release leaves it, commands are ignored, an output time is only
    # counted (the CIC and SEQ run on RESET_N), the timer cannot expire
    for e, _ in SEQ_EVENTS:
        cell = SEQ["table"].get(("RESET", e))
        if e == "REL":
            ok = isinstance(cell, list) and all(b["next"] == "IDLE" and not b["actions"] for b in cell)
        elif e == "OUT":
            ok = isinstance(cell, list) and all(b["next"] in (None, "RESET") and set(b["actions"]) <= DATA
                                                for b in cell)
        elif e == "TMR":
            ok = cell == IMP
        else:
            ok = cell == IGN
        if not ok:
            errs.append(f"SEQ RESET/{e}: not what a reset allows (release to IDLE; output times only counted; "
                        f"commands ignored; no timer)")
    # STATE and AFE_RST are Moore outputs of the state; READY = (state == RUN)
    codes = [x[1] for x in SEQ_STATES if x[1] is not None]
    if len(codes) != len(set(codes)):
        errs.append("SEQ: STATE codes are not unique")
    for x in SEQ_STATES:
        if x[4] and any(b["next"] in (None, x[0]) for b in SEQ["table"][(x[0], "TMR")]):
            errs.append(f"SEQ {x[0]}: the timer's expiry does not always leave the state")
    return errs, n


# =====================================================================================================================
# SPI properties
# =====================================================================================================================
# Where each SPI action may happen, written from the frame definitions (spec section 3.2), not from the table
# (audit round 6: actions added to other cells passed the frame checks, which compared effects and load counts only)
SPI_PLACES = {"load_status": {("IDLE", "CSF")}, "snapshot": {("HDR", "BYTE")},
              "load_data": {("HDR", "BYTE"), ("RREG", "BYTE")}, "load_zero": {("HDR", "BYTE")},
              "load_crc": {("RREG", "BYTE")}, "addr_inc": {("RREG", "BYTE")}, "next_byte": {("RSMP", "BYTE")},
              "latch_addr": {("HDR", "BYTE")}, "latch_data": {("WDAT", "BYTE")}, "latch_crc": {("WCRC", "BYTE")},
              "commit": {("WDONE", "CSR")}, "STATE_ERR": {("WDONE", "CSR")}, "CRC_ERR": {("WDONE", "CSR")},
              "pop": {("SDONE", "CSR")}, "ADDR_ERR": {("HDR", "BYTE"), ("WDONE", "CSR")}}


def check_spi_props():
    """Enumerated over every value of every condition (not over the guard strings)."""
    errs, n = [], 0
    t = SPI["table"]
    for (s, e), cell in t.items():                  # every action only where the frame definitions put it
        if isinstance(cell, list):
            for b in cell:
                for a in b["actions"]:
                    if a == "FRAME_ERR" and e != "CSR":
                        errs.append(f"SPI {s}/{e} [{b['guard']}]: FRAME_ERR other than at CS_N rising")
                    elif a in SPI_PLACES and (s, e) not in SPI_PLACES[a]:
                        errs.append(f"SPI {s}/{e} [{b['guard']}]: {a} where the frame definitions do not put it")
                if "addr_inc" in b["actions"] and "load_data" not in b["actions"]:
                    errs.append(f"SPI {s}/{e} [{b['guard']}]: the address advances without loading the next byte")
    done = ("RDONE", "SDONE", "WDONE")             # no bit after completion (a further bit leaves for OVF)
    for (s, e), cell in t.items():
        if not isinstance(cell, list):
            continue
        for env in all_envs(list(SPI_CONDS), SPI["constraint"]):
            if s in done and env["mid"] and e == "CSR":
                continue                            # a done state never sees CS_N rising inside a byte
            b = pick(cell, env)
            if b is None:
                continue                            # reported by check_tables
            n += 1
            a, nxt = b["actions"], b["next"]
            if "commit" in a and not (s == "WDONE" and e == "CSR" and env["wr_ok"] and not env["busy"]
                                      and (env["crc_ok"] or not env["crc_en"])):
                errs.append(f"SPI {s}/{e} {env}: commit outside a complete, checked write to a writable address")
            if "pop" in a and not (s == "SDONE" and e == "CSR" and env["head"]):
                errs.append(f"SPI {s}/{e} {env}: pop outside a complete read of the entry still at the head")
            if s == "SDONE" and e == "CSR" and env["head"] and "pop" not in a:
                errs.append(f"SPI {s}/{e} {env}: a sample read completely is not removed (it would be read twice)")
            if e == "CSR" and nxt != "IDLE":
                errs.append(f"SPI {s}/{e} {env}: CS_N rising does not end the transaction")
            if e == "CSR" and env["mid"] and "FRAME_ERR" not in a:
                errs.append(f"SPI {s}/{e} {env}: a partial byte is not flagged")
            if e == "CSR" and s in ("WDAT", "WCRC", "OVF") and "FRAME_ERR" not in a:
                errs.append(f"SPI {s}/{e} {env}: an incomplete or overlong write is not flagged")
            if e == "CSR" and s == "WDONE" and env["crc_en"] and not env["crc_ok"] and "CRC_ERR" not in a:
                errs.append(f"SPI {s}/{e} {env}: a CRC mismatch is not flagged")
    for s in [x[0] for x in SPI_STATES if x[0] != "IDLE"]:
        if not isinstance(t[(s, "CSR")], list):
            errs.append(f"SPI {s}: no exit on CS_N rising")
    return errs, n


def spi_walk(nbytes, extra, env):
    """One frame through the SPI table: CSF, one BIT or BYTE per SCLK rising edge (BYTE on every 8th), CSR.
    Returns (actions in order, the state at CS_N rising) or None if an impossible or undecided cell is met."""
    t = SPI["table"]
    state, acts, k = "IDLE", [], 0
    e_env = dict(env, mid=int(extra > 0), last=0)
    events = ["CSF"] + ["BYTE" if n % 8 == 0 else "BIT" for n in range(1, 8 * nbytes + extra + 1)] + ["CSR"]
    at_csr = None
    for e in events:
        if e == "CSR":
            at_csr = state
        if e == "BYTE" and state == "RSMP":
            e_env["last"] = int(k == 6)
        cell = t[(state, e)]
        if cell == IMP:
            return None
        if cell == IGN:
            continue
        b = pick(cell, e_env)
        if b is None:
            return None
        acts += b["actions"]
        k += "next_byte" in b["actions"]
        if b["next"] is not None:
            state = b["next"]
    return acts, at_csr


def spi_expect(kind, crc_en, nbytes, mid, env):
    """What a frame must do, written from the frame definitions (spec section 3.2), independently of the table:
    the effects (commit, the error flags, the copy, the pop) and the MISO loads after the header."""
    E, hdr = set(), nbytes >= 1
    if nbytes == 0 and not mid:
        return E, None                                   # an empty frame
    if kind == "write":
        if mid or nbytes != 2 + crc_en:
            E.add("FRAME_ERR")
        elif crc_en and not env["crc_ok"]:
            E.add("CRC_ERR")
        elif not env["wr_ok"]:
            E.add("ADDR_ERR")
        elif env["busy"]:
            E.add("STATE_ERR")
        else:
            E.add("commit")
        loads = None
    elif kind == "read":
        if hdr and not env["addr_ok"]:
            E.add("ADDR_ERR")
        if mid or (crc_en and nbytes not in (1, 3)):
            E.add("FRAME_ERR")
        # a data byte (or 0x00) after every completed byte; with CRC one data byte, then the CRC
        loads = dict(data=min(nbytes, 1) if crc_en else nbytes, crc=int(crc_en and nbytes >= 2))
        # the sequence: the header's address (0x00 if undefined), then (CRC off) the following addresses one by one,
        # or (CRC on) the CRC of the header and the data byte
        first = ("data" if env["addr_ok"] else "zero", 0)
        if crc_en:
            loads["seq"] = ([first] if nbytes >= 1 else []) + ([("crc", 0)] if nbytes >= 2 else [])
        else:
            loads["seq"] = ([first] if nbytes >= 1 else []) + [("data", k) for k in range(1, nbytes)]
    else:
        if hdr:
            E.add("snapshot")
        if mid or nbytes > 8 or (crc_en and hdr and nbytes != 8):
            E.add("FRAME_ERR")
        elif nbytes == 8 and env["head"]:
            E.add("pop")
        loads = dict(next=max(0, min(nbytes, 7) - 1))
    return E, loads


def spi_frame_cases():
    """The frames check_spi_frames walks: every kind, CRC mode, condition value, 0..10 complete bytes and 0..7 bits of
    a partial last byte (audit round 6: the partial byte had 0 and 3 bits only). The generated text takes its count
    from here."""
    for kind in ("write", "read", "sample"):
        for crc_en in (0, 1):
            for vals in itertools.product((0, 1), repeat=5):
                env = dict(zip(("addr_ok", "wr_ok", "busy", "crc_ok", "head"), vals))
                env.update(rw=int(kind != "write"), smp=int(kind == "sample"), crc_en=crc_en)
                if kind == "sample" and not env["addr_ok"]:
                    continue                             # the sample window is a defined address
                for nbytes in range(11):
                    for extra in range(8):
                        yield kind, crc_en, env, nbytes, extra


def check_spi_frames():
    """Every frame of spi_frame_cases walked through the table and compared with spi_expect."""
    errs, n = [], 0
    effects = {"commit", "STATE_ERR", "ADDR_ERR", "CRC_ERR", "FRAME_ERR", "snapshot", "pop"}
    for kind, crc_en, env, nbytes, extra in spi_frame_cases():
        n += 1
        w = spi_walk(nbytes, extra, env)
        tag = f"SPI frame {kind} crc_en={crc_en} {nbytes} bytes + {extra} bits {env}"
        if w is None:
            errs.append(f"{tag}: the walk meets an impossible or undecided cell")
            continue
        acts, _ = w
        exp, loads = spi_expect(kind, crc_en, nbytes, extra > 0, env)
        got = {a for a in acts if a in effects}
        if got != exp:
            errs.append(f"{tag}: {sorted(got)}, expected {sorted(exp)}")
        if loads and not extra:
            if kind == "read":
                d = acts.count("load_data") + acts.count("load_zero")
                if d != loads["data"] or acts.count("load_crc") != loads["crc"]:
                    errs.append(f"{tag}: {d} data and {acts.count('load_crc')} CRC loads, expected {loads}")
                seq, off = [], 0              # the MISO byte sequence with the read addresses
                for a in acts:
                    if a == "addr_inc":
                        off += 1
                    elif a in ("load_data", "load_zero"):
                        seq.append(("data" if a == "load_data" else "zero", off))
                    elif a == "load_crc":
                        seq.append(("crc", off))
                if seq != loads["seq"]:
                    errs.append(f"{tag}: MISO loads {seq}, expected {loads['seq']}")
            elif acts.count("next_byte") != loads["next"]:
                errs.append(f"{tag}: {acts.count('next_byte')} sample bytes loaded, expected {loads['next']}")
        if kind in ("write", "sample") and not extra and \
                any(a in acts for a in ("load_data", "load_zero", "load_crc")):
            errs.append(f"{tag}: a {kind} frame loads register data or a read CRC onto MISO "
                        f"(a write's MISO is 0x00, a sample's bytes come from its copy)")
        if kind == "write" and "commit" in acts:      # a write commits the address and data it latched
            need = ["latch_addr", "latch_data"] + (["latch_crc"] if crc_en else [])
            k_c = acts.index("commit")
            if not all(x in acts[:k_c] for x in need):
                errs.append(f"{tag}: commit without {[x for x in need if x not in acts[:k_c]]}")
    return errs, n


# =====================================================================================================================
# FIFO: push, pop and flush in one MCLK cycle
# =====================================================================================================================
DEPTH = 4                     # the smallest depth allowed (DAT-05); the rules do not depend on it


def fifo_step(count, push, pop, flush, held=0, snap=0):
    """Order inside a cycle: flush, then pop, then push (a new sample is never lost to a flush or a pop).
    pop is the SPI's request (SDONE, CS_N rising); held: the SPI's copy is a stored entry that is still the head (the
    SPI condition `head`). snap: the SPI copies the head this cycle (the copy is the head before this cycle's flush,
    pop and push). Returns (count, overrun, popped, held)."""
    ovr, popped, c0 = False, False, count
    if flush:
        count = 0
    elif pop and held and count > 0:
        count -= 1
        popped = True
    if push:
        if count < DEPTH:
            count += 1
        else:
            ovr = True
    if flush or popped:
        held = 0                                       # the copy is no longer the head
    elif snap:
        held = int(c0 > 0)                             # copied a stored entry (not the empty word)
    return count, ovr, popped, held


def check_fifo():
    """Against an independent model with identities: the FIFO holds entries 0..count-1 (0 at the head), the SPI's copy
    is the head entry (held) or not in the FIFO, a pushed entry is 99. Expected: flush, then a pop of the head only if
    it is the copy, then the push; the new copy (snap) is the head before the cycle or None (the empty word); held
    afterwards means the copy is the head."""
    errs, n = [], 0
    for count in range(DEPTH + 1):
        for held in ((0, 1) if count else (0,)):       # invariant: held -> not empty
            for push, pop, flush, snap in itertools.product([0, 1], repeat=4):
                n += 1
                tag = f"FIFO {count} held={held} push={push} pop={pop} flush={flush} snap={snap}"
                c2, ovr, popped, h2 = fifo_step(count, push, pop, flush, held, snap)
                fifo = list(range(count))
                copy = 0 if held else None
                e_pop = bool(pop and not flush and copy is not None and fifo and fifo[0] == copy)
                q = [] if flush else (fifo[1:] if e_pop else fifo[:])
                e_ovr = bool(push and len(q) == DEPTH)
                if push and not e_ovr:
                    q.append(99)
                copy2 = (fifo[0] if fifo else None) if snap else copy
                e_held = int(copy2 is not None and bool(q) and q[0] == copy2)
                if not 0 <= c2 <= DEPTH:
                    errs.append(f"{tag}: occupancy {c2} out of range")
                if c2 != len(q):
                    errs.append(f"{tag}: occupancy {c2}, expected {len(q)}")
                if ovr != e_ovr:
                    errs.append(f"{tag}: OVERRUN {ovr}, expected {e_ovr}")
                if push and not ovr and c2 == 0:
                    errs.append(f"{tag}: a pushed sample was lost")
                if popped and not e_pop:
                    errs.append(f"{tag}: removed an entry the SPI did not send")
                if e_pop and not popped:
                    errs.append(f"{tag}: the entry sent is not removed")
                if h2 != e_held:
                    errs.append(f"{tag}: the copy is marked {'' if h2 else 'not '}as the head; it is {'' if e_held else 'not '}the head")
    return errs, n


# =====================================================================================================================
# Timing against the analog side (frame-cycle map, timers, CHOP1, SPI) - the numbers behind SEQ's tick
# =====================================================================================================================
MCLK = 32.768e6
FRAME = 32                                     # MCLK per frame (fs = 1.024 MHz)
TIMING = dict(
    # frame cycles (MCLK edge e_n starts cycle n) of the existing frame (eeg_clkgen, eeg_adc_dig, eeg_chop1, eeg_cic3)
    busy_cycles={0: "CMP_STROBE（比較器）", 1: "TH の確定待ち", 2: "TH の取り込み（e2）", 3: "SEL1／SEL2（DAC2、e3）",
                 4: "DAC_CLK（DAC1、e4）", 5: "DAC_CLK の立ち下がり（e5）", 8: "CIC の出力（OUT）",
                 16: "CHOP1 の縁（e16）"},
    blank_max=15,                              # CHOP_BLANK: cycle 31 of the previous frame and cycles 0 .. BLANK_LEN - 1
                                               # (BLANK_LEN + 1 cycles, BLANK_LEN <= 15); checked as 31 and 0 .. 15
    tick_cycle=24,
    rates={"128k": dict(period_frames=8, tick_frame=1), "64k": dict(period_frames=16, tick_frame=3)},
    timers=dict(T_WARM=(5e-3, 5e-3, 255e-3), T_REC=(0.22e-3, 0.25e-3, 255 * 256 / MCLK),
                T_PRE=(20e-6, 20e-6, 255 * 256 / MCLK), T_RST=(100e-6, 100e-6, 255 * 256 / MCLK)),
    # (analog minimum, nominal, the longest the register can give: 255 ms, 255 x 7.8125 us = 1.99 ms)
    decimation=1024, cic_order=3,
    chop1_periods_frames=[1024, 512, 256, 128, 64],    # 1, 2, 4, 8, 16 kHz full periods
    spi_sclk_max=2e6, spi_write_bits=16,
)


def check_timing():
    T, errs, notes = TIMING, [], []
    tc = T["tick_cycle"]
    for c in (tc, (tc + 1) % 32):                  # the tick's strobe cycle and the edge its outputs change at
        if c in T["busy_cycles"]:
            errs.append(f"tick (cycle {tc}, outputs at e{tc + 1}) meets {T['busy_cycles'][c]} at cycle {c}")
    if tc <= T["blank_max"] or tc == 31:
        errs.append(f"tick at frame cycle {tc} can fall inside an output-chopper blanking window")
    for name, r in T["rates"].items():
        half = r["period_frames"] // 2
        pos = (r["tick_frame"] * FRAME + tc) / (half * FRAME)          # fraction of phase A from its rising edge
        if not 0.25 <= pos <= 0.75:
            errs.append(f"{name}: tick at {pos:.2f} of chopper phase A, not in its middle half")
        notes.append(f"{name}: tick {r['tick_frame'] * FRAME + tc} MCLK after the phase-A edge "
                     f"({pos:.3f} of the half period), every {r['period_frames'] * FRAME / MCLK * 1e6:.4f} us")
        tick_s = r["period_frames"] * FRAME / MCLK
        # the timer registers against these analog minimums: regmap.py check (the register codes, in whole frames)
        # SPI: a second command can arrive before the tick when a write frame is shorter than the tick period
        frame_s = T["spi_write_bits"] / T["spi_sclk_max"]
        if frame_s < tick_s and "busy" not in SPI_CONDS:
            errs.append(f"{name}: two commands can arrive between ticks ({frame_s * 1e6:.1f} < {tick_s * 1e6:.2f} us) "
                        "but the SPI specification has no 'busy' rule")
        if frame_s < tick_s:
            notes.append(f"{name}: a write frame ({frame_s * 1e6:.1f} us) is shorter than the tick period: "
                         "one pending command, a second one gets STATE_ERR (SPI 'busy')")
        # the output grid holds a whole number of chopper periods: every output time sees the same chopper phase
        if T["decimation"] % r["period_frames"]:
            errs.append(f"{name}: 1 ms is not a whole number of chopper periods")
        if T["decimation"] % r["period_frames"] == 0:
            out_frame = (T["decimation"] - 1) % r["period_frames"]
            if out_frame == r["tick_frame"]:
                notes.append(f"{name}: OUT and the tick share a frame (different cycles {8} and {tc})")
    # CHOP1: every period divides the decimation ratio (sinc^3 zeros null its square wave); a rate change applies at
    # e16 of frame 1024 k, one input into the CIC window that starts there: weight of that input h[0] / R^3
    for p_ in T["chop1_periods_frames"]:
        if T["decimation"] % p_:
            errs.append(f"CHOP1 period {p_} frames does not divide the decimation ratio")
    R = T["decimation"]
    w0 = 1 / R ** T["cic_order"]
    notes.append(f"CHOP1 rate change: one input of the new window still sees the old phase, sinc^3 weight {w0:.1e}")
    if w0 > 1e-6:
        errs.append("CHOP1 rate change leaves a visible part of a CIC window on the old rate")
    return errs, notes


CHECKS = [
    "完全性：全ての（状態、イベント）の欄が定義されている",
    "起こり得ない事象（IMP）の正しさ：IMP はその状態で起こり得ない事象にのみ使われている",
    "決定性：各欄の条件は排他的かつ網羅的（条件の全ての組み合わせを列挙して確認）",
    "到達性：全ての状態が初期状態から到達できる",
    "行き止まりがない：シーケンサは全ての状態から、リセットを使わずに IDLE と RUN へ到達できる。SPI は全ての状態から IDLE へ到達できる",
    "タイマ：タイマを持つ状態は、満了で必ずその状態を出る（満了の欄の全ての分岐）",
    "語彙：動作と条件の一覧の全ての項目が表で使われ、表で使う全ての項目が一覧にある（古い項目が残らない）",
    "同時の事象（シーケンサ）：1 tick の命令（0〜1 個）とタイマの満了の全ての組み合わせ、および出力の時刻（tick と同じサイクルにはならない）について、全ての条件の値で、優先順位の規則による結果が次の性質を満たす",
    "  状態を変えるのは、表とは独立に書いた出口の一覧（SEQ_EXITS）にある（状態、その tick で状態を決めた事象）の組のみ：タイマの待ち（WARMUP、RECOVER、WAIT_E、PRE、PULSE）を出るのは、その満了、STOP、AFE の動作中の APPLY（PRE へ）のみ。FLUSH は状態を変えない。START は IDLE からのみ。APPLY_NR で状態が変わるのは RUN の前（ALIGN、FILL から電極の待ちかクリアへ）のみ。RUN を出るのは STOP と APPLY のみ",
    "  AFE_RST の解除は必ず RECOVER（ADC の復帰待ち）に入る",
    "  AFE_RST の解除と同じ tick で設定を反映しない。AFE_RST を保っている間（WARMUP）の反映は、解除までの待ちを最初から数え直す（変更から解除まで T_WARM 以上）",
    "  START は必ず一括反映し、FIFO を空にする",
    "  AFE の動作中に AFE_RST なしで反映するのは、オフセット DAC の ±1 段の変更（nr_ok）のみ",
    "  FILL へは CIC のクリアとともにのみ入る",
    "  FIFO への格納は RUN と、FILL から RUN への遷移（最初の有効な出力）のみ",
    "  RUN へ入るのは最初の有効な出力のときのみ。RUN を出るのは STOP と APPLY（と RST）のみ",
    "  RUN のままの設定の反映には必ず CHANGED の印が付く。充填中の窓の中では設定を変えない",
    "  不整合な設定は反映されない",
    "  CIC のクリアは出力の時刻の格子の上（ALIGN から FILL）でのみ",
    "  AFE_RST のパルスの前には必ず PRE（T_PRE の待ち）がある。PRE へは設定の反映とともにのみ入る",
    "  RECOVER へは AFE_RST の解除（WARMUP と PULSE の満了）からのみ入る",
    "  FIFO を空にするのは START、APPLY（パルスあり、すなわち AFE の動作中の APPLY）、FLUSH のみ（ほかはリセット）。APPLY（パルスあり）は必ず FIFO を空にする（古い設定のサンプルを残さない）。IDLE と WARMUP の APPLY はパルスなしで、FIFO を空にしない",
    "  RUN の前のオフセットの 1 段（APPLY_NR）は、T_ELEC > 0 なら電極の整定を待ち直す（WAIT_E、WAIT_E では数え直し）。WAIT_E へは RECOVER の満了か、その 1 段からのみ入る",
    "  STOP は必ず IDLE へ。命令は実行されるか、定義による無視（IDLE の STOP のみ）か、エラーのフラグのいずれか（黙って捨てられない）。これを各欄でなく、その tick の優先順位の解決の結果で確かめる（受け付けた命令の動作が全て取られ、遷移する命令はその tick の遷移を決める）",
    "  T_ELEC ＞ 0 では RECOVER の満了は必ず WAIT_E へ、T_ELEC ＝ 0 では ALIGN へ。RUN の出力の時刻は必ず格納する。FLUSH は全ての状態で FIFO を空にする。RUN へは有効な出力でのみ入る。受け付けた APPLY と APPLY_NR は必ず反映する",
    "RESET の行：リセットの解除でのみ IDLE へ出る。命令は無視、出力の時刻は数えるのみ（格納、クリア、状態の変化なし）、タイマの満了は起こらない",
    "リセットの優先：全ての状態と、上の全ての事象の組み合わせ（全ての条件の値）に RST が加わると、結果は RESET で、状態の変化と制御の動作はない（SOFT_RESET の確定のサイクルの tick と出力の時刻）。その出力の時刻はデータの経路として数えて捨て（seq_inc、discard）、ALIGN では CIC のクリアが出力の時刻のサイクルの始まりの縁で済んでいる（cic_clear）",
    "分岐ごとの性質（シーケンサ、第 6 回で追加）：出力の時刻の分岐は必ず数え（seq_inc）、格納か破棄のちょうど一方。出力の時刻の動作（store、discard、seq_inc、cic_clear）は出力の時刻のみ。RESET の出力の時刻も数える（DAT-03）。拒否の旗はちょうど 1 個で、CFG_ERR は設定の整合に依る分岐、STATE_ERR は状態による無条件の拒否のみ。待ちの数え直しは、表とは独立に書いた一覧（WARMUP の APPLY と APPLY_NR、WAIT_E の APPLY_NR）のとおり",
    "分岐ごとの性質（シーケンサ）：命令を無視（IGN）してよいのは IDLE の STOP のみ。拒否した命令（CFG_ERR、STATE_ERR）はほかの動作を伴わず状態を変えない（SEQ-09）。待ちの数え直し（restart）は反映（apply）とともにのみ。CHANGED の印（mark）は RUN の受け付けた APPLY_NR のみ。FLUSH は FIFO を空にするのみ（数え直し、印、反映、遷移なし）",
    "SPI（条件の全ての値で列挙）：書き込みの確定は、完全で CRC 検査済みの、書き込み可能なアドレスへのフレームの CS_N の立ち上がりのみ（前の命令が未処理なら確定しない）。CRC の不一致は CRC_ERR。取り出しは、8 バイトちょうど（先頭バイトと 7 バイト）読み出したサンプルが写した時点から FIFO の先頭のままのときのみで、そのときは必ず取り出す（空の語とフラッシュのあとの語は取り出さない）。CS_N の立ち上がりは必ず IDLE へ戻り、バイトの途中と不完全・過長な書き込みは FRAME_ERR",
    "SPI の動作の位置（第 6 回で追加）：各動作（STATUS と先頭の写し、MISO への読み込み、アドレスの加算、書き込みの保持、確定、取り出し、エラーの旗）は、フレームの定義から表とは独立に書いた位置（状態と事象）でのみ。FRAME_ERR は CS_N の立ち上がりのみ",
    f"SPI のフレーム（書き込み・読み出し・サンプル × CRC の有無 × 条件の全ての値 × 0〜10 バイトと 0〜7 ビットの途中のバイト、{sum(1 for _ in spi_frame_cases()):,} 通り。第 6 回で途中のビットを 0 と 3 から全てに）：表を歩いた結果を、表とは独立に書いた意味の定義（spi_expect）と照合。確定、STATE_ERR、ADDR_ERR（書き込みと未定義の読み出し）、CRC_ERR、FRAME_ERR（バイトの途中、長さの誤り、CRC 有効時の CRC のない読み出しと 8 バイトでないサンプル）、写し、取り出し、MISO へ載せるデータと CRC のバイト数と、読み出しの MISO のバイトの並び（アドレスの順）、確定する書き込みがアドレスとデータ（CRC 有効時は CRC）を保持していること",
    f"FIFO（深さ {DEPTH}）：同じサイクルの格納・取り出しの要求・クリア・SPI の写しの全ての組み合わせで、占有数が範囲内、OVERRUN は満杯への格納（取り出しとクリアなし）のときのみ、格納したサンプルは失われない。取り出すのは SPI が写して送った語のみ（写しが先頭のままの印は、空の語の写し、フラッシュ、取り出しで消える）",
    "時刻（アナログとの関係）：tick のサイクルが比較器、TH、DAC、CIC の出力、CHOP1 の縁、ブランキングの窓と重ならない。tick はチョッパの相 A の中ほど（半周期の 25〜75 %）。1 ms がチョッパの周期の整数倍。CHOP1 の全ての周期が 1 ms を割り切り、速さの切り替えで旧い相に残る CIC の重みが 1e−6 以下。tick の間に命令が 2 つ届きうる場合に SPI の未処理の規則がある",
]


def check_seq_branches():
    """Per branch of the sequencer's table (audit round 4, 11/20: these table errors passed every other check):
    a refused command (CFG_ERR, STATE_ERR) has no other effect and leaves the state (SEQ-09); 'restart' only with
    'apply' (a wait starts again only for a change applied while the AFE is held or the electrode settles); 'mark'
    only with 'apply' in RUN's APPLY_NR; FLUSH only empties the FIFO (no restart, mark, apply, move)."""
    errs = []
    for (s, e), cell in SEQ["table"].items():
        if s != "RESET" and e in SEQ_COMMANDS and cell == IGN and (s, e) != ("IDLE", "STOP"):
            errs.append(f"SEQ {s}/{e}: a command ignored without effect or flag (only STOP in IDLE is)")
        if s == "RESET" or not isinstance(cell, list):
            continue
        for b in cell:
            acts, nxt = set(b["actions"]), b["next"]
            where = f"SEQ {s}/{e} [{b['guard']}]"
            if acts & {"CFG_ERR", "STATE_ERR"} and (acts - {"CFG_ERR", "STATE_ERR"} or nxt not in (None, s)):
                errs.append(f"{where}: a refused command has another effect ({sorted(acts)} -> {nxt})")
            if "restart" in acts and "apply" not in acts:
                errs.append(f"{where}: the wait starts again without a change applied")
            if "mark" in acts and not ("apply" in acts and s == "RUN" and e == "APPLY_NR"):
                errs.append(f"{where}: CHANGED marked other than by an applied APPLY_NR in RUN")
            if e == "FLUSH" and (acts != {"flush"} or nxt not in (None, s)):
                errs.append(f"{where}: FLUSH does more than empty the FIFO ({sorted(acts)} -> {nxt})")
            # audit round 6 (auditor C: single-action edits that passed every other check)
            if e == "OUT" and ("seq_inc" not in acts or len(acts & {"store", "discard"}) != 1):
                errs.append(f"{where}: an output time not counted, or not exactly one of stored / discarded (DAT-03)")
            if e != "OUT" and acts & {"store", "discard", "seq_inc", "cic_clear"}:
                errs.append(f"{where}: an output-time action ({sorted(acts & {'store', 'discard', 'seq_inc', 'cic_clear'})}) "
                            f"outside an output time")
            flags = acts & {"CFG_ERR", "STATE_ERR"}
            if len(flags) > 1:
                errs.append(f"{where}: a refusal with two flags")
            if "CFG_ERR" in acts and not any(c in b["guard"] for c in ("cfg_ok", "nr_ok")):
                errs.append(f"{where}: CFG_ERR on a branch that does not depend on the settings' consistency")
            if "STATE_ERR" in acts and b["guard"] not in (ALWAYS, "1"):
                errs.append(f"{where}: STATE_ERR on a branch that depends on the settings (a state refuses always)")
            if "restart" in acts and (s, e) not in SEQ_RESTARTS:
                errs.append(f"{where}: a wait started again where no restart is defined")
    for (s, e) in SEQ_RESTARTS:                     # and every defined restart is in the table
        cell = SEQ["table"].get((s, e))
        if not (isinstance(cell, list) and any("restart" in b["actions"] for b in cell)):
            errs.append(f"SEQ {s}/{e}: the defined restart is missing")
    for e in ("OUT",):                              # RESET counts the output time too (the data path runs on RESET_N)
        cell = SEQ["table"].get(("RESET", e))
        if not (isinstance(cell, list) and all("seq_inc" in b["actions"] for b in cell)):
            errs.append("SEQ RESET/OUT: an output time during a reset not counted (DAT-03)")
    return errs


# The waits that start again, written independently of the table (SEQ-16, the electrode wait): a change applied while
# the AFE is held (WARMUP) restarts T_WARM; an offset step in WAIT_E restarts T_ELEC. Nowhere else.
SEQ_RESTARTS = {("WARMUP", "APPLY"), ("WARMUP", "APPLY_NR"), ("WAIT_E", "APPLY_NR")}


def run_checks(verbose=True):
    report, total = [], 0
    report += check_seq_branches()
    for F, must, excl in ((SEQ, ["IDLE", "RUN"], ("RST",)), (SPI, ["IDLE"], ())):
        report += check_tables(F) + check_graph(F, must, excl) + check_vocab(F)
    e, n1 = check_seq_ticks()
    report += e
    e, n2 = check_spi_props()
    report += e
    e, n2b = check_spi_frames()
    report += e
    e, n3 = check_fifo()
    report += e
    e, tnotes = check_timing()
    report += e
    total = n1 + n2 + n3
    if verbose:
        print(f"checked: SEQ {len(SEQ_STATES)} states x {len(SEQ_EVENTS)} events, {n1} tick combinations; "
              f"SPI {len(SPI_STATES)} states x {len(SPI_EVENTS)} events, {n2} branches, {n2b} frames; FIFO {n3} cases")
        for t_ in tnotes:
            print("  timing: " + t_)
        if report:
            print(f"{len(report)} violations:")
            for r in report:
                print("  " + r)
        else:
            print("no violations")
    return report, total


# =====================================================================================================================
# Generators: Mermaid (hierarchical, lifted from the flat table) and Markdown tables
# =====================================================================================================================
def parent_chain(F, s):
    par = {x[0]: x[2] for x in F["states"]}
    par.update({k: v[0] for k, v in F["composites"].items()})
    chain, p = [], par.get(s)
    while p:
        chain.append(p)
        p = par.get(p)
    return chain


def leaves(F, comp):
    return [x[0] for x in F["states"] if comp in parent_chain(F, x[0])]


def label(e, guard, acts, short=None):
    g = "" if guard == ALWAYS else f" [{guard.replace('not ', '!').replace(' and ', ' & ').replace(' or ', ' | ')}]"
    a = [x for x in acts if x not in DATA]
    return (short or e) + g + (f" / {', '.join(a)}" if a else "")


def table_self_loops(F, keep, hide=()):
    """Self-loop labels drawn from the table: every branch that stays in its state and executes one of the actions in
    keep (events with the same guard and actions are merged into one label)."""
    loops = []
    for x in F["states"]:
        s, groups = x[0], {}
        for e, _ in F["events"]:
            cell = F["table"].get((s, e))
            if e in hide or cell in (None, IMP, IGN):
                continue
            for b in cell:
                if b["next"] in (None, s) and set(b["actions"]) & set(keep):
                    groups.setdefault((b["guard"], tuple(b["actions"])), []).append(e)
        labs = [label(", ".join(es), g, list(a)) for (g, a), es in groups.items()]
        if labs:
            loops.append((s, "<br/>".join(labs)))
    return loops


def mermaid(F, title, notes=(), self_loops=(), lump=None, hide=(), internal=()):
    """Hierarchical state diagram. internal: (state, label) pairs written inside the state's box (UML internal
    transitions: the event's actions without leaving the state), one line per label part. A transition shared (same event, guard, actions, target) by every leaf of a
    composite is drawn once from the composite; a transition into a composite's initial leaf from outside is drawn
    into the composite. lump: (composite, event) pairs drawn once from the composite with a summary label."""
    E = [x for x in edges(F) if x[1] not in hide]
    comps = F["composites"]
    drawn = set()
    out = []
    # lift shared transitions to composites (outermost first, so an inner composite does not repeat them)
    order = sorted(comps, key=lambda c: len(parent_chain(F, c)))
    lifted = []
    for c in order:
        L = leaves(F, c)
        sig = {}
        for (s, e, g, a, n) in E:
            if s in L and n not in L:
                sig.setdefault((e, g, a, n), set()).add(s)
        for (e, g, a, n), srcs in sig.items():
            if srcs == set(L) and not any((x, e, g, a, n) in drawn for x in L):
                lifted.append((c, e, g, a, n))
                drawn |= {(s, e, g, a, n) for s in L}
    lumped = []
    for c, e, text in (lump or []):
        L = leaves(F, c)
        for x in E:
            if x[0] in L and x[1] == e:
                drawn.add(x)
        lumped.append((c, text))

    def retarget(src, dst):
        # entering a composite at its initial leaf from outside: draw into the composite (outermost that fits)
        best = dst
        for c in parent_chain(F, dst):
            init = comps[c][1]
            while init in comps:
                init = comps[init][1]
            if init == dst and c not in parent_chain(F, src) and src != c:
                best = c
        return best

    timers = {x[0]: x[4] for x in F["states"]}

    def lab(src, e, g, a):
        return label(e, g, a, short=f"TMR({timers[src]})" if e == "TMR" and timers.get(src) else None)

    rows = []
    for x in lifted:
        rows.append((x[0], retarget(x[0], x[4]), lab(*x[:4])))
    for x in E:
        if x not in drawn:
            rows.append((x[0], retarget(x[0], x[4]), lab(*x[:4])))
    merged = {}
    for a, b, l in rows:
        merged.setdefault((a, b), []).append(l)
    out.append("stateDiagram-v2")
    out.append(f"    %% {title} (generated by gf180/tapeout/rtl/spec/fsm_spec.py; do not edit by hand)")

    def emit(container, ind):
        for x in F["states"]:
            if x[2] == container:
                out.append(f"{ind}{x[0]}")
                for st, text in internal:
                    if st == x[0]:                     # the first description line is the box's title: the name
                        out.append(f"{ind}{st} : {st}")
                        out.extend(f"{ind}{st} : {part}" for part in text.split("<br/>"))
        for c, v in comps.items():
            if v[0] == container:
                out.append(f"{ind}state {c} {{")
                out.append(f"{ind}    [*] --> {v[1]}")
                emit(c, ind + "    ")
                for (a, b), ls in merged.items():
                    if (parent_chain(F, a)[:1] == [c] or (a in comps and comps[a][0] == c)) and \
                       (parent_chain(F, b)[:1] == [c] or (b in comps and comps[b][0] == c)):
                        out.append(f"{ind}    {a} --> {b} : {'<br/>'.join(ls)}")
                        merged[(a, b)] = None
                for st, text in self_loops:                    # a self-loop stays inside the state's composite
                    if parent_chain(F, st)[:1] == [c]:
                        out.append(f"{ind}    {st} --> {st} : {text}")
                out.append(f"{ind}}}")
    out.append(f"    [*] --> {F['initial']}")
    emit(None, "    ")
    for (a, b), ls in merged.items():
        if ls:
            out.append(f"    {a} --> {b} : {'<br/>'.join(ls)}")
    for c, text in lumped:
        out.append(f"    {c} --> IDLE : {text}")
    for st, text in self_loops:
        if not parent_chain(F, st):
            out.append(f"    {st} --> {st} : {text}")
    for n in notes:
        out.append(f"    note right of {n[0]}")
        for line in n[1]:
            out.append(f"        {line}")
        out.append("    end note")
    return "\n".join(out) + "\n"


def cell_md(cell, s):
    if cell == IMP:
        return "—"
    if cell == IGN:
        return "無視"
    parts = []
    for b in cell:
        g = "" if b["guard"] == ALWAYS else f"［{b['guard']}］"
        a = ", ".join(b["actions"])
        n = f"→ {b['next']}" if b["next"] not in (None, s) else ""
        parts.append(" ".join(x for x in (g, a, n) if x) or "—")
    return "<br>".join(parts)


def tables_md(F, moore_cols):
    names = [x[0] for x in F["states"]]
    ev = [e for e, _ in F["events"]]
    lines = ["| 状態 ＼ イベント | " + " | ".join(ev) + " |", "|---|" + "---|" * len(ev)]
    for s in names:
        lines.append(f"| {s} | " + " | ".join(cell_md(F["table"][(s, e)], s) for e in ev) + " |")
    trans = "\n".join(lines)
    head = ["状態", "意味"] + [c[0] for c in moore_cols]
    st = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for x in F["states"]:
        st.append("| " + " | ".join([x[0], x[5]] + [c[1](x) for c in moore_cols]) + " |")
    ev_md = ["| イベント | 意味 |", "|---|---|"] + [f"| {e} | {d} |" for e, d in F["events"]]
    cond_md = ["| 条件 | 意味 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in F["conds"].items()]
    act_md = ["| 動作 | 意味 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in F["actions"].items()]
    return "\n".join(st), trans, "\n".join(ev_md), "\n".join(cond_md), "\n".join(act_md)


def generate(write=True):
    """Writes the diagrams and the document's generated blocks; write=False returns them instead ({path: text})."""
    rep, _ = run_checks(verbose=write)
    if rep:
        print("not generating: fix the violations first")
        return 1
    seq_mmd = mermaid(SEQ, "sequencer", hide=("RST",),
                      notes=[("RESET", ["RST (RESET_N = 0 or SOFT_RESET) from any state leads to RESET.",
                                        "In a state's box: its transitions that stay in the state",
                                        "(apply, restart, mark, store; from the table).",
                                        "Errors (CFG_ERR, STATE_ERR) and FLUSH: see the transition table."])],
                      internal=table_self_loops(SEQ, ("apply", "restart", "mark", "store"), hide=("RST",)))
    spi_mmd = mermaid(SPI, "SPI transaction", lump=[("FRAME", "CSR", "CSR / commit, pop or error (see the table)")],
                      internal=table_self_loops(SPI, ("addr_inc", "next_byte")))
    files = {"seq_fsm.mmd": seq_mmd, "spi_fsm.mmd": spi_mmd}
    seq_tabs = tables_md(SEQ, [("STATE", lambda x: "—" if x[1] is None else str(x[1])),
                               ("AFE_RST", lambda x: str(x[3])),
                               ("READY", lambda x: "1" if x[0] == "RUN" else "0"),
                               ("タイマ", lambda x: x[4] or "—"),
                               ("上位の状態", lambda x: " ⊂ ".join(parent_chain(SEQ, x[0])) or "—")])
    spi_tabs = tables_md(SPI, [("上位の状態", lambda x: " ⊂ ".join(parent_chain(SPI, x[0])) or "—")])
    out = {os.path.join(HERE, k): v for k, v in files.items()}
    blocks = {
        "seq_mermaid": "```mermaid\n" + seq_mmd + "```",
        "seq_states": seq_tabs[0], "seq_table": seq_tabs[1], "seq_events": seq_tabs[2], "seq_conds": seq_tabs[3],
        "seq_actions": seq_tabs[4],
        "spi_mermaid": "```mermaid\n" + spi_mmd + "```",
        "spi_states": spi_tabs[0], "spi_table": spi_tabs[1], "spi_events": spi_tabs[2], "spi_conds": spi_tabs[3],
        "spi_actions": spi_tabs[4],
        "checks": "\n".join(f"- {c}" if not c.startswith("  ") else f"  - {c.strip()}" for c in CHECKS),
    }
    with open(DOC, encoding="utf-8") as f:
        doc = f.read()
    for k, v in blocks.items():
        a, b = f"<!-- BEGIN GENERATED {k} -->", f"<!-- END GENERATED {k} -->"
        if a in doc:
            i, j = doc.index(a) + len(a), doc.index(b)
            doc = doc[:i] + "\n" + v + "\n" + doc[j:]
    out[DOC] = doc
    if not write:
        return out
    for p, text in out.items():
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    print("wrote", ", ".join(files), "and the generated blocks of", os.path.relpath(DOC, REPO))
    return 0


def fresh():
    """The generated files (the two .mmd and the document's generated blocks) equal what the source gives now."""
    want = generate(write=False)
    if not isinstance(want, dict):
        return 1
    stale = [os.path.relpath(p, REPO) for p, text in want.items()
             if not os.path.exists(p) or open(p, encoding="utf-8").read() != text]
    # the PNGs: drawn from the .mmd that the source gives now (the SHA-256 kept in each PNG)
    stale += [os.path.relpath(p[:-4] + ".png", REPO) for p, text in want.items()
              if p.endswith(".mmd") and png_source_sha(p[:-4] + ".png") != source_sha(text)]
    print("generated files up to date" if not stale else
          "STALE (run fsm_spec.py gen, and render for a .png): " + ", ".join(stale))
    return 1 if stale else 0


def selftest():
    """Mutation test of the checker: each mutation below is a plausible specification error and must be detected."""
    import copy
    seq_mut = [
        ("RUN/STOP の欄の欠落", lambda t: t.pop(("RUN", "STOP"))),
        ("起こり得る FLUSH を IMP にする", lambda t: t.__setitem__(("RUN", "FLUSH"), IMP)),
        ("FILL/OUT の条件が網羅的でない", lambda t: t.__setitem__(("FILL", "OUT"), [B("valid", ["store", "seq_inc"], "RUN")])),
        ("RECOVER/TMR の条件の重なり", lambda t: t.__setitem__(("RECOVER", "TMR"), [B("t_elec0", [], "ALIGN"), B(ALWAYS, [], "WAIT_E")])),
        ("WARMUP から RUN へ直行", lambda t: t.__setitem__(("WARMUP", "TMR"), [B(ALWAYS, [], "RUN")])),
        ("RUN の APPLY_NR に印なし", lambda t: t.__setitem__(("RUN", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("FILL のまま APPLY_NR", lambda t: t.__setitem__(("FILL", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("AFE 動作中の APPLY_NR で段数を検査しない", lambda t: t.__setitem__(("RECOVER", "APPLY_NR"), [B("cfg_ok", ["apply"]), B("not cfg_ok", ["CFG_ERR"])])),
        ("APPLY で整合を検査しない", lambda t: t.__setitem__(("RUN", "APPLY"), [B(ALWAYS, ["apply"], "PRE")])),
        ("PRE から PULSE を飛ばす", lambda t: t.__setitem__(("PRE", "TMR"), [B(ALWAYS, [], "RECOVER")])),
        ("STOP で IDLE に戻らない", lambda t: t.__setitem__(("PRE", "STOP"), [B(ALWAYS, [], "PULSE")])),
        ("ALIGN で CIC をクリアしない", lambda t: t.__setitem__(("ALIGN", "OUT"), [B(ALWAYS, ["discard", "seq_inc"], "FILL")])),
        ("PULSE のタイマが状態を出ない", lambda t: t.__setitem__(("PULSE", "TMR"), [B(ALWAYS, [])])),
        ("WAIT_E の STOP を黙って捨てる", lambda t: t.__setitem__(("WAIT_E", "STOP"), [B(ALWAYS, [])])),
        ("RUN の START を黙って捨てる", lambda t: t.__setitem__(("RUN", "START"), [B(ALWAYS, [])])),
        ("RUN へ入れない", lambda t: t.__setitem__(("FILL", "OUT"), [B(ALWAYS, ["discard", "seq_inc"])])),
        ("START で FIFO を空にしない", lambda t: t.__setitem__(("IDLE", "START"), [B("cfg_ok", ["apply"], "WARMUP"), B("not cfg_ok", ["CFG_ERR"])])),
        ("RUN から SETTLE へ黙って戻る", lambda t: t.__setitem__(("RUN", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"], "ALIGN"), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        # audit round 1 (11/20)
        ("WARMUP の APPLY で解除までの待ちを数え直さない", lambda t: t.__setitem__(("WARMUP", "APPLY"), [B("cfg_ok", ["apply"]), B("not cfg_ok", ["CFG_ERR"])])),
        ("WARMUP の APPLY_NR で解除までの待ちを数え直さない", lambda t: t.__setitem__(("WARMUP", "APPLY_NR"), [B("cfg_ok", ["apply"]), B("not cfg_ok", ["CFG_ERR"])])),
        ("APPLY（パルスあり）で FIFO を空にしない", lambda t: t.__setitem__(("RUN", "APPLY"), [B("cfg_ok", ["apply"], "PRE"), B("not cfg_ok", ["CFG_ERR"])])),
        ("WAIT_E の APPLY_NR で電極の待ちを数え直さない", lambda t: t.__setitem__(("WAIT_E", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("FILL の APPLY_NR で電極を待たない", lambda t: t.__setitem__(("FILL", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"], "ALIGN"), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("ALIGN の APPLY_NR で電極を待たない", lambda t: t.__setitem__(("ALIGN", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("PULSE の満了の一部の分岐が状態を出ない", lambda t: t.__setitem__(("PULSE", "TMR"), [B("t_elec0", [], "RECOVER"), B("not t_elec0", [])])),
        ("FILL/OUT で有効の条件を使わない（条件 valid が未使用）", lambda t: t.__setitem__(("FILL", "OUT"), [B(ALWAYS, ["store", "seq_inc"], "RUN")])),
        ("ALIGN から WAIT_E へ黙って戻る", lambda t: t.__setitem__(("ALIGN", "FLUSH"), [B(ALWAYS, ["flush"], "WAIT_E")])),
        # audit round 2 (11/20): a wait cut short by another event (the next state alone looked legal)
        ("WARMUP の FLUSH で AFE_RST を解除（T_WARM より前）", lambda t: t.__setitem__(("WARMUP", "FLUSH"), [B(ALWAYS, ["flush"], "RECOVER")])),
        ("PULSE の FLUSH でパルスを短くする", lambda t: t.__setitem__(("PULSE", "FLUSH"), [B(ALWAYS, ["flush"], "RECOVER")])),
        ("PRE の FLUSH で T_PRE を飛ばす", lambda t: t.__setitem__(("PRE", "FLUSH"), [B(ALWAYS, ["flush"], "PULSE")])),
        ("RECOVER の FLUSH で復帰待ちを飛ばす", lambda t: t.__setitem__(("RECOVER", "FLUSH"), [B(ALWAYS, ["flush"], "ALIGN")])),
        ("WAIT_E の FLUSH で電極の待ちを飛ばす", lambda t: t.__setitem__(("WAIT_E", "FLUSH"), [B(ALWAYS, ["flush"], "ALIGN")])),
        ("RUN の FLUSH で IDLE へ", lambda t: t.__setitem__(("RUN", "FLUSH"), [B(ALWAYS, ["flush"], "IDLE")])),
        ("WARMUP の START で AFE_RST を解除", lambda t: t.__setitem__(("WARMUP", "START"), [B(ALWAYS, [], "RECOVER")])),
        ("PULSE の START でパルスを短くする", lambda t: t.__setitem__(("PULSE", "START"), [B(ALWAYS, [], "RECOVER")])),
        ("RECOVER の APPLY_NR で復帰待ちを飛ばす", lambda t: t.__setitem__(("RECOVER", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply"], "ALIGN"), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("SOFT_RESET の間の出力の時刻を数えない（RESET/OUT を IMP）", lambda t: t.__setitem__(("RESET", "OUT"), IMP)),
        # audit round 3 (11/20)
        ("RECOVER の満了の分岐の入れ違い（T_ELEC ＞ 0 で電極の待ちを飛ばす）", lambda t: t.__setitem__(("RECOVER", "TMR"), [B("t_elec0", [], "WAIT_E"), B("not t_elec0", [], "ALIGN")])),
        ("RUN の出力を格納しない", lambda t: t.__setitem__(("RUN", "OUT"), [B(ALWAYS, ["discard", "seq_inc"])])),
        ("IDLE の FLUSH を無視する", lambda t: t.__setitem__(("IDLE", "FLUSH"), IGN)),
        ("有効でない出力で RUN に入る", lambda t: t.__setitem__(("FILL", "OUT"), [B("valid", ["store", "seq_inc"], "RUN"), B("not valid", ["store", "seq_inc"], "RUN")])),
        ("WARMUP の APPLY が数え直すだけで反映しない", lambda t: t.__setitem__(("WARMUP", "APPLY"), [B("cfg_ok", ["restart"]), B("not cfg_ok", ["CFG_ERR"])])),
        ("RECOVER の APPLY_NR が反映しない", lambda t: t.__setitem__(("RECOVER", "APPLY_NR"), [B("cfg_ok and nr_ok", []), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("RUN の APPLY_NR が印を付けるだけ", lambda t: t.__setitem__(("RUN", "APPLY_NR"), [B("cfg_ok and nr_ok", ["mark"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
        ("RESET の出力の時刻で格納する", lambda t: t.__setitem__(("RESET", "OUT"), [B(ALWAYS, ["store", "seq_inc"])])),
        ("RESET の APPLY を反映する", lambda t: t.__setitem__(("RESET", "APPLY"), [B(ALWAYS, ["apply"])])),
        # audit round 4 (11/20)
        ("RUN のリセットで、そのサイクルの出力を格納する", lambda t: t.__setitem__(("RUN", "RST"), [B(ALWAYS, ["store"], "RESET")])),
        ("PULSE のリセットで RECOVER へ（AFE_RST を解除）", lambda t: t.__setitem__(("PULSE", "RST"), [B(ALWAYS, [], "RECOVER")])),
        # audit round 4, auditor C: refused commands and FLUSH with other effects (each passed every other check)
        ("RUN の拒否した APPLY_NR が CHANGED の印を付ける", lambda t: t.__setitem__(("RUN", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply", "mark"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR", "mark"])])),
        ("WARMUP の拒否した APPLY が T_WARM を数え直す", lambda t: t.__setitem__(("WARMUP", "APPLY"), [B("cfg_ok", ["apply", "restart"]), B("not cfg_ok", ["CFG_ERR", "restart"])])),
        ("PULSE の拒否した APPLY が T_RST を数え直す（パルスが伸びる）", lambda t: t.__setitem__(("PULSE", "APPLY"), [B(ALWAYS, ["STATE_ERR", "restart"])])),
        ("WAIT_E の拒否した START が T_ELEC を数え直す", lambda t: t.__setitem__(("WAIT_E", "START"), [B(ALWAYS, ["STATE_ERR", "restart"])])),
        ("FILL の拒否した APPLY_NR が ALIGN へ", lambda t: t.__setitem__(("FILL", "APPLY_NR"), [B("cfg_ok and nr_ok and t_elec0", ["apply"], "ALIGN"), B("cfg_ok and nr_ok and not t_elec0", ["apply"], "WAIT_E"), B("not (cfg_ok and nr_ok)", ["CFG_ERR"], "ALIGN")])),
        ("PRE の FLUSH が T_PRE を数え直す", lambda t: t.__setitem__(("PRE", "FLUSH"), [B(ALWAYS, ["flush", "restart"])])),
        ("RUN の FLUSH が CHANGED の印を付ける", lambda t: t.__setitem__(("RUN", "FLUSH"), [B(ALWAYS, ["flush", "mark"])])),
        # audit round 5, auditor C: commands ignored without a flag (the per-cell checks let IGN through)
        ("PULSE の APPLY を無視（IGN）", lambda t: t.__setitem__(("PULSE", "APPLY"), IGN)),
        ("RUN の START を無視（IGN）", lambda t: t.__setitem__(("RUN", "START"), IGN)),
        ("WAIT_E の APPLY_NR を無視（IGN）", lambda t: t.__setitem__(("WAIT_E", "APPLY_NR"), IGN)),
        # audit round 6, auditor C: single-action edits that passed
        ("RUN の出力の時刻を数えない", lambda t: t.__setitem__(("RUN", "OUT"), [B(ALWAYS, ["store"])])),
        ("RESET の出力の時刻を数えない", lambda t: t.__setitem__(("RESET", "OUT"), [B(ALWAYS, ["discard"])])),
        ("RUN の APPLY で格納する", lambda t: t.__setitem__(("RUN", "APPLY"), [B("cfg_ok", ["apply", "flush", "store"], "PRE"), B("not cfg_ok", ["CFG_ERR"])])),
        ("拒否に旗を 2 つ立てる", lambda t: t.__setitem__(("PULSE", "APPLY"), [B(ALWAYS, ["STATE_ERR", "CFG_ERR"])])),
        ("RECOVER の APPLY_NR で数え直す", lambda t: t.__setitem__(("RECOVER", "APPLY_NR"), [B("cfg_ok and nr_ok", ["apply", "restart"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])])),
    ]
    spi_mut = [
        ("CRC を検査せずに確定", lambda t: t.__setitem__(("WDONE", "CSR"), [B("wr_ok", ["commit"], "IDLE"), B("not wr_ok", ["ADDR_ERR"], "IDLE")])),
        ("不完全な書き込みを通知しない", lambda t: t.__setitem__(("WDAT", "CSR"), [B(ALWAYS, [], "IDLE")])),
        ("短い読み出しで取り出す", lambda t: t.__setitem__(("RSMP", "CSR"), [B("mid", ["FRAME_ERR"], "IDLE"), B("not mid", ["pop"], "IDLE")])),
        ("先頭バイトの条件が網羅的でない", lambda t: t.__setitem__(("HDR", "BYTE"), [B("rw and smp", ["snapshot"], "RSMP"), B("not rw", ["latch_addr"], "WDAT")])),
        ("CS_N の立ち上がりで IDLE に戻らない", lambda t: t.__setitem__(("OVF", "CSR"), [B(ALWAYS, ["FRAME_ERR"], "OVF")])),
        ("バイトの途中の CS_N を通知しない", lambda t: t.__setitem__(("RREG", "CSR"), [B(ALWAYS, [], "IDLE")])),
        ("読み出し専用への書き込みを確定", lambda t: t.__setitem__(("WDONE", "CSR"), [B("crc_ok or not crc_en", ["commit"], "IDLE"), B("crc_en and not crc_ok", ["CRC_ERR"], "IDLE")])),
        ("未処理の命令を上書き", lambda t: t.__setitem__(("WDONE", "CSR"), [B("(crc_ok or not crc_en) and wr_ok", ["commit"], "IDLE"), B("(crc_ok or not crc_en) and not wr_ok", ["ADDR_ERR"], "IDLE"), B("crc_en and not crc_ok", ["CRC_ERR"], "IDLE")])),
        ("先頭でなくなった写しでも取り出す", lambda t: t.__setitem__(("SDONE", "CSR"), [B(ALWAYS, ["pop"], "IDLE")])),
        ("読み終えたサンプルを取り出さない", lambda t: t.__setitem__(("SDONE", "CSR"), [B(ALWAYS, [], "IDLE")])),
        # audit round 1 (11/20): the cases the per-cell properties could not see (byte counts, missing flags)
        ("2 バイト目でサンプルを終える", lambda t: t.__setitem__(("RSMP", "BYTE"), [B(ALWAYS, [], "SDONE")])),
        ("CRC 無効でも CRC のバイトを待つ（3 バイトの書き込み）", lambda t: t.__setitem__(("WDAT", "BYTE"), [B(ALWAYS, ["latch_data"], "WCRC")])),
        ("未処理の間の書き込みを STATE_ERR なしで捨てる", lambda t: t.__setitem__(("WDONE", "CSR"), [B("(crc_ok or not crc_en) and wr_ok and not busy", ["commit"], "IDLE"), B("(crc_ok or not crc_en) and wr_ok and busy", [], "IDLE"), B("(crc_ok or not crc_en) and not wr_ok", ["ADDR_ERR"], "IDLE"), B("crc_en and not crc_ok", ["CRC_ERR"], "IDLE")])),
        ("書き込めないアドレスへの書き込みを ADDR_ERR なしで捨てる", lambda t: t.__setitem__(("WDONE", "CSR"), [B("(crc_ok or not crc_en) and wr_ok and not busy", ["commit"], "IDLE"), B("(crc_ok or not crc_en) and wr_ok and busy", ["STATE_ERR"], "IDLE"), B("(crc_ok or not crc_en) and not wr_ok", [], "IDLE"), B("crc_en and not crc_ok", ["CRC_ERR"], "IDLE")])),
        ("未定義のアドレスの読み出しで ADDR_ERR を立てない", lambda t: t.__setitem__(("HDR", "BYTE"), [B("rw and smp", ["snapshot"], "RSMP"), B("rw and not smp and addr_ok", ["load_data"], "RREG"), B("rw and not smp and not addr_ok", ["load_zero"], "RREG"), B("not rw", ["latch_addr"], "WDAT")])),
        ("サンプルの読み出しで FIFO の先頭を写さない", lambda t: t.__setitem__(("HDR", "BYTE"), [B("rw and smp", [], "RSMP"), B("rw and not smp and addr_ok", ["load_data"], "RREG"), B("rw and not smp and not addr_ok", ["ADDR_ERR", "load_zero"], "RREG"), B("not rw", ["latch_addr"], "WDAT")])),
        ("CRC 有効時の短いサンプルを通す", lambda t: t.__setitem__(("RSMP", "CSR"), [B("mid", ["FRAME_ERR"], "IDLE"), B("not mid", [], "IDLE")])),
        ("CRC のバイトのない読み出しを通す", lambda t: t.__setitem__(("RCRC", "CSR"), [B("mid", ["FRAME_ERR"], "IDLE"), B("not mid", [], "IDLE")])),
        ("CRC 有効時も連続読み出しを続ける", lambda t: t.__setitem__(("RREG", "BYTE"), [B(ALWAYS, ["addr_inc", "load_data"])])),
        # audit round 6, auditor C: single edits that passed the frame checks (0 and 3 extra bits, load counts only)
        ("書き込みの完了のあとの 1 ビットで読み出しの完了へ（確定も旗もなし）", lambda t: t.__setitem__(("WDONE", "BIT"), [B(ALWAYS, [], "RDONE")])),
        ("連続読み出しで先頭バイトに戻る（アドレスを進めない）", lambda t: t.__setitem__(("RREG", "BYTE"), [B("crc_en", ["load_crc"], "RCRC"), B("not crc_en", ["addr_inc", "load_data"], "HDR")])),
        ("書き込みのデータを保持しない", lambda t: t.__setitem__(("WDAT", "BYTE"), [B("crc_en", [], "WCRC"), B("not crc_en", [], "WDONE")])),
        ("CS_N の立ち上がりで先頭を写す", lambda t: t.__setitem__(("SDONE", "CSR"), [B("head", ["pop", "snapshot"], "IDLE"), B("not head", [], "IDLE")])),
        ("先頭バイトでアドレスを進める", lambda t: t.__setitem__(("HDR", "BYTE"), [B("rw and smp", ["snapshot"], "RSMP"), B("rw and not smp and addr_ok", ["addr_inc", "load_data"], "RREG"), B("rw and not smp and not addr_ok", ["ADDR_ERR", "load_zero"], "RREG"), B("not rw", ["latch_addr"], "WDAT")])),
        ("サンプルの先頭バイトでレジスタのデータを載せる", lambda t: t.__setitem__(("HDR", "BYTE"), [B("rw and smp", ["snapshot", "load_data"], "RSMP"), B("rw and not smp and addr_ok", ["load_data"], "RREG"), B("rw and not smp and not addr_ok", ["ADDR_ERR", "load_zero"], "RREG"), B("not rw", ["latch_addr"], "WDAT")])),
        ("CRC 有効の読み出しでもアドレスを進める", lambda t: t.__setitem__(("RREG", "BYTE"), [B("crc_en", ["load_crc", "addr_inc"], "RCRC"), B("not crc_en", ["addr_inc", "load_data"])])),
    ]
    global fifo_step
    fifo_orig = fifo_step

    def fifo_bad_flush_drops_push(count, push, pop, flush, held=0, snap=0):
        if flush:
            return 0, False, False, 0
        return fifo_orig(count, push, pop, flush, held, snap)

    def fifo_bad_pop_after_push(count, push, pop, flush, held=0, snap=0):
        ovr, popped, c0 = False, False, count
        if flush:
            count = 0
        if push:
            if count < DEPTH:
                count += 1
            else:
                ovr = True
        if pop and held and count > 0 and not flush:
            count -= 1
            popped = True
        return count, ovr, popped, 0 if (flush or popped) else (int(c0 > 0) if snap else held)

    def fifo_bad_flush_keeps_held(count, push, pop, flush, held=0, snap=0):
        c2, ovr, popped, h2 = fifo_orig(count, push, pop, flush, held, snap)
        return c2, ovr, popped, (held if flush and c2 else h2)

    def fifo_bad_snap_empty(count, push, pop, flush, held=0, snap=0):
        c2, ovr, popped, h2 = fifo_orig(count, push, pop, flush, held, snap)
        return c2, ovr, popped, (1 if snap and not flush and not popped and c2 else h2)

    fifo_mut = [("FLUSH と同じサイクルの格納を捨てる", fifo_bad_flush_drops_push),
                ("取り出しより先に格納（満杯で取り出しと同時の格納が OVERRUN）", fifo_bad_pop_after_push),
                ("フラッシュで写しの印を消さない（送っていない語を取り出しうる）", fifo_bad_flush_keeps_held),
                ("空の語の写しにも印を付ける（あとの格納を取り出しうる）", fifo_bad_snap_empty)]
    results, ok = [], True
    # the resolution order itself (audit round 5: the timer above APPLY made RECOVER's APPLY lose its transition)
    prio_orig = list(SEQ_PRIORITY)
    for name, order in (("同じ tick でタイマの満了を APPLY より優先", ["STOP", "START", "TMR", "APPLY", "APPLY_NR", "FLUSH"]),
                        ("同じ tick でタイマの満了を START より優先", ["STOP", "TMR", "START", "APPLY", "APPLY_NR", "FLUSH"])):
        SEQ_PRIORITY[:] = order
        rep, _ = run_checks(verbose=False)
        results.append(("SEQ", name, len(rep), rep[0] if rep else ""))
        ok &= bool(rep)
    SEQ_PRIORITY[:] = prio_orig
    for F, muts in ((SEQ, seq_mut), (SPI, spi_mut)):
        orig = F["table"]
        for name, m in muts:
            F["table"] = copy.deepcopy(orig)
            m(F["table"])
            rep, _ = run_checks(verbose=False)
            results.append((F["name"], name, len(rep), rep[0] if rep else ""))
            ok &= bool(rep)
        F["table"] = orig
    for name, f in fifo_mut:
        fifo_step = f
        rep, _ = run_checks(verbose=False)
        results.append(("FIFO", name, len(rep), rep[0] if rep else ""))
        ok &= bool(rep)
    fifo_step = fifo_orig
    for m, name, n, first in results:
        print(f"{'detected' if n else 'MISSED  '} {m:4s} {name}: {n} violations" + (f" (e.g. {first[:110]})" if n else ""))
    rep, _ = run_checks(verbose=False)
    print(f"{sum(1 for r in results if r[2])} of {len(results)} mutations detected; unmutated specification: "
          f"{len(rep)} violations")
    return 0 if ok and not rep else 1


def source_sha(text):
    """The SHA-256 of a diagram's source text, kept in its PNG (tEXt 'source-sha256') so that 'fresh' can tell a PNG
    drawn from an older source (audit round 4)."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def png_source_sha(path):
    """The 'source-sha256' text of a PNG, or None."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.text.get("source-sha256")
    except (OSError, ImportError, AttributeError):
        return None


def save_tagged_png(im, out, src_text):
    from PIL.PngImagePlugin import PngInfo
    info = PngInfo()
    info.add_text("source-sha256", source_sha(src_text))
    im.save(out, pnginfo=info)


def render():
    """PNG of each generated diagram (headless Google Chrome; Mermaid 11.4.1 from jsDelivr). The Markdown keeps the
    Mermaid source, which GitHub draws itself; the PNGs are for viewing elsewhere. Each PNG keeps the SHA-256 of its
    .mmd ('fresh' compares it). A drawing that Mermaid did not finish is never written: the source text stays hidden
    until Mermaid marks it processed (a blank capture is retried with more time, then an error), and the page's DOM
    must hold the drawing's SVG without a syntax error (audit round 4: a slow load once captured the raw text)."""
    import html
    import subprocess
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome):
        print("Google Chrome not found; skipped")
        return 1
    from PIL import Image, ImageChops
    build = os.path.join(HERE, "..", "build")
    os.makedirs(build, exist_ok=True)
    for name, size, kind in (("seq_fsm", "720,2500", "stateDiagram"), ("spi_fsm", "1080,1150", "stateDiagram")):
        src = open(os.path.join(HERE, name + ".mmd"), encoding="utf-8").read()
        page = os.path.join(build, name + ".html")
        with open(page, "w", encoding="utf-8") as f:
            f.write("<!doctype html><html><head><meta charset='utf-8'><style>body{margin:8px;background:#fff}"
                    "pre.mermaid:not([data-processed]){visibility:hidden}</style>"
                    f"</head><body><pre class='mermaid'>{html.escape(src)}</pre><script type='module'>"
                    "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';"
                    "mermaid.initialize({startOnLoad:false, theme:'default'});"
                    "await mermaid.run({querySelector:'.mermaid'});</script></body></html>")
        raw = os.path.join(build, name + ".raw.png")
        out = os.path.join(HERE, name + ".png")
        im = None
        for budget in (15000, 30000, 60000):
            args = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--virtual-time-budget={budget}"]
            dom = subprocess.run(args + ["--dump-dom", "file://" + os.path.abspath(page)], capture_output=True,
                                 text=True).stdout
            if f'aria-roledescription="{kind}' not in dom or "Syntax error" in dom:
                continue
            if os.path.exists(raw):
                os.remove(raw)
            subprocess.run(args + ["--force-device-scale-factor=2", f"--window-size={size}", f"--screenshot={raw}",
                                   "file://" + os.path.abspath(page)], check=True, capture_output=True)
            shot = Image.open(raw).convert("RGB")
            box = ImageChops.difference(shot, Image.new("RGB", shot.size, (255, 255, 255))).getbbox()
            if box:                              # trim the empty page below and right of the drawing
                im = shot.crop((0, 0, min(shot.width, box[2] + 32), min(shot.height, box[3] + 32)))
                break
        if im is None:
            print(f"{name}: Mermaid did not draw the diagram (DOM without its SVG, or a blank capture); not written")
            return 1
        save_tagged_png(im, out, src)
        print("wrote", os.path.relpath(out, REPO), f"({im.width} x {im.height})")
    return 0

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        sys.exit(1 if run_checks()[0] else 0)
    if cmd == "gen":
        sys.exit(generate())
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "render":
        sys.exit(render())
    if cmd == "fresh":
        sys.exit(fresh())
    print(__doc__)
