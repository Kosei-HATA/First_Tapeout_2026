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
        cycle, which never coincides with a tick. RST is asynchronous.
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
    ("RST", "RESET_N = 0、または SOFT_RESET（非同期。どの時点でも）"),
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
    "full": "FIFO が満杯",
}
SEQ_ACTIONS = {
    "apply": "シャドウからアクティブへ一括反映（オフセット DAC、トリム、チョッパ、BLANK、試験の設定）",
    "flush": "FIFO を空にする",
    "cic_clear": "CIC をクリアする（出力の時刻に合わせて行うので、格子は変わらない）",
    "store": "出力を FIFO へ格納する（DRDY）",
    "discard": "出力を捨てる",
    "seq_inc": "SEQ に 1 を加える（SEQ はリセットの解除からの出力の時刻の番号）",
    "mark": "このあとの 3 個の出力（反映をまたぐ窓）に CHANGED を付ける",
    "cancel": "同じ tick の START を取り消す（IDLE に留まる）",
    "CFG_ERR": "エラー CFG_ERR を立てる（命令は実行しない）",
    "STATE_ERR": "エラー STATE_ERR を立てる（命令は実行しない）",
    "OVERRUN": "エラー OVERRUN を立てる（出力は捨てる）",
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
        t[(s, "APPLY")] = [B("cfg_ok", ["apply"], "PRE"), B("not cfg_ok", ["CFG_ERR"])]
        # AFE running: without a pulse only a one-step change of the offset DAC (the operating 1-step tracking)
        t[(s, "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
        t[(s, "FLUSH")] = [B(ALWAYS, ["flush"])]
        t[(s, "TMR")] = IMP if s not in timed else None
        t[(s, "OUT")] = [B(ALWAYS, ["discard", "seq_inc"])]
    # RESET: nothing is served; only the release leaves it
    for e, _ in SEQ_EVENTS:
        t[("RESET", e)] = IGN
    t[("RESET", "REL")] = [B(ALWAYS, [], "IDLE")]
    t[("RESET", "TMR")] = IMP
    t[("RESET", "OUT")] = IMP
    # IDLE
    t[("IDLE", "START")] = [B("cfg_ok", ["apply", "flush"], "WARMUP"), B("not cfg_ok", ["CFG_ERR"])]
    t[("IDLE", "STOP")] = IGN
    # IDLE and WARMUP hold the AFE in reset: any consistent change is applied without a pulse
    for st in ("IDLE", "WARMUP"):
        t[(st, "APPLY")] = [B("cfg_ok", ["apply"]), B("not cfg_ok", ["CFG_ERR"])]
        t[(st, "APPLY_NR")] = [B("cfg_ok", ["apply"]), B("not cfg_ok", ["CFG_ERR"])]
    t[("WARMUP", "TMR")] = [B(ALWAYS, [], "RECOVER")]
    # RECOVER / WAIT_E
    t[("RECOVER", "TMR")] = [B("t_elec0", [], "ALIGN"), B("not t_elec0", [], "WAIT_E")]
    t[("WAIT_E", "TMR")] = [B(ALWAYS, [], "ALIGN")]
    # ALIGN: the CIC is cleared at the next output time, keeping the output grid
    t[("ALIGN", "OUT")] = [B(ALWAYS, ["cic_clear", "discard", "seq_inc"], "FILL")]
    # FILL: an unpulsed APPLY_NR restarts the clear, so no stored window ever straddles a change
    t[("FILL", "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply"], "ALIGN"), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    t[("FILL", "OUT")] = [B("valid", ["store", "seq_inc"], "RUN"), B("not valid", ["discard", "seq_inc"])]
    # RUN
    t[("RUN", "APPLY_NR")] = [B("cfg_ok and nr_ok", ["apply", "mark"]), B("not (cfg_ok and nr_ok)", ["CFG_ERR"])]
    t[("RUN", "OUT")] = [B("not full", ["store", "seq_inc"]), B("full", ["OVERRUN", "discard", "seq_inc"])]
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
        return s != "RESET"
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
    ("RSMP", None, "FRAME", None, None, "サンプルの窓の読み出し（STATUS、SEQ、DATA、CRC の 7 バイト）"),
    ("SDONE", None, "FRAME", None, None, "サンプルの 7 バイトの完了（CS_N の立ち上がりで FIFO から取り出す）"),
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
    "last": "サンプルの 7 バイト目",
    "mid": "バイトの途中（CS_N の立ち上がりの時点で受信したビット数が 8 の倍数でない）",
    "crc_ok": "受信した CRC が一致",
    "wr_ok": "書き込み可能なアドレス（定義済みで読み出し専用でない）",
    "busy": "命令レジスタへの書き込みで、前の命令がまだ tick で処理されていない",
}
SPI_ACTIONS = {
    "load_status": "STATUS を送信のシフトレジスタへ（その時点の値を写す）",
    "snapshot": "FIFO の先頭（空なら空の語）を写す",
    "load_data": "アドレスのデータを送信のシフトレジスタへ",
    "load_zero": "0x00 を送信のシフトレジスタへ",
    "addr_inc": "アドレスに 1 を加える",
    "load_crc": "送ったバイトの CRC を送信のシフトレジスタへ",
    "next_byte": "サンプルの次のバイトを送信のシフトレジスタへ",
    "latch_addr": "アドレスを保持",
    "latch_data": "データを保持",
    "latch_crc": "CRC を保持",
    "commit": "書き込みを確定（値の範囲が不正なら RANGE_ERR として書かない。命令レジスタなら命令を次の tick に渡す）",
    "pop": "FIFO の先頭を取り出す（空なら何もしない）",
    "FRAME_ERR": "エラー FRAME_ERR を立てる",
    "CRC_ERR": "エラー CRC_ERR を立てる（書かない）",
    "ADDR_ERR": "エラー ADDR_ERR を立てる（書かない。読み出しは 0x00）",
    "STATE_ERR": "エラー STATE_ERR を立てる（前の命令が未処理のため、この命令を受け付けない）",
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
    t[("RSMP", "BYTE")] = [B("not last", ["next_byte"]), B("last", [], "SDONE")]
    t[("WDAT", "BYTE")] = [B("crc_en", ["latch_data"], "WCRC"), B("not crc_en", ["latch_data"], "WDONE")]
    t[("WCRC", "BYTE")] = [B(ALWAYS, ["latch_crc"], "WDONE")]
    t[("OVF", "BYTE")] = IGN
    for s in ("RDONE", "SDONE", "WDONE"):                      # a completed frame: any further bit overflows it
        t[(s, "BIT")] = [B(ALWAYS, [], "OVF")]
        t[(s, "BYTE")] = IMP                                   # the first further bit already left the state
    t[("RDONE", "CSR")] = [B(ALWAYS, [], "IDLE")]
    t[("SDONE", "CSR")] = [B(ALWAYS, ["pop"], "IDLE")]
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
    """Next state and executed actions for the events present in one tick (RST excluded: asynchronous)."""
    t = SEQ["table"]
    br = {e: pick(t.get((s, e)), env) for e in present}       # a missing cell is reported by check_tables
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
    return nxt, acts


def seq_properties(s, present, env, nxt, acts):
    """Each returns an error string or None."""
    afe = lambda x: SEQ_STATE[x][3]
    P = []
    if afe(s) == 1 and afe(nxt) == 0 and nxt != "RECOVER":
        P.append("AFE_RST is released without passing RECOVER (ADC recovery wait)")
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
    if "flush" in acts and not ((s == "IDLE" and nxt == "WARMUP") or "FLUSH" in present):
        P.append("FIFO flushed by something other than START or FLUSH")
    if "STOP" in present and nxt != "IDLE":
        P.append("STOP does not lead to IDLE")
    if s == "RUN" and nxt not in ("RUN", "IDLE", "PRE"):
        P.append("RUN left other than by STOP or APPLY")
    for c in SEQ_COMMANDS:                          # a command is executed, ignored by definition, or flagged
        if c in present:
            b = pick(SEQ["table"].get((s, c)), env)
            if isinstance(b, dict) and not b["actions"] and b["next"] in (None, s):
                P.append(f"command {c} silently dropped")
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
                nxt, acts = seq_tick(s, present, env)
                n += 1
                for p in seq_properties(s, present, env, nxt, acts):
                    errs.append(f"SEQ {s} {present} {env}: {p} -> {nxt} {acts}")
    # STATE and AFE_RST are Moore outputs of the state; READY = (state == RUN)
    codes = [x[1] for x in SEQ_STATES if x[1] is not None]
    if len(codes) != len(set(codes)):
        errs.append("SEQ: STATE codes are not unique")
    for x in SEQ_STATES:
        if x[4] and all(b["next"] in (None, x[0]) for b in SEQ["table"][(x[0], "TMR")]):
            errs.append(f"SEQ {x[0]}: the timer's expiry does not leave the state")
    return errs, n


# =====================================================================================================================
# SPI properties
# =====================================================================================================================
def check_spi_props():
    """Enumerated over every value of every condition (not over the guard strings)."""
    errs, n = [], 0
    t = SPI["table"]
    done = ("RDONE", "SDONE", "WDONE")             # no bit after completion (a further bit leaves for OVF)
    for (s, e), cell in t.items():
        if not isinstance(cell, list):
            continue
        for env in all_envs(list(SPI_CONDS), SPI["constraint"]):
            if s in done and env["mid"]:
                continue
            b = pick(cell, env)
            if b is None:
                continue                            # reported by check_tables
            n += 1
            a, nxt = b["actions"], b["next"]
            if "commit" in a and not (s == "WDONE" and e == "CSR" and env["wr_ok"] and not env["busy"]
                                      and (env["crc_ok"] or not env["crc_en"])):
                errs.append(f"SPI {s}/{e} {env}: commit outside a complete, checked write to a writable address")
            if "pop" in a and not (s == "SDONE" and e == "CSR"):
                errs.append(f"SPI {s}/{e} {env}: pop outside a complete sample read")
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


# =====================================================================================================================
# FIFO: push, pop and flush in one MCLK cycle
# =====================================================================================================================
DEPTH = 4                     # the smallest depth allowed (DAT-05); the rules do not depend on it


def fifo_step(count, push, pop, flush):
    """Order inside a cycle: flush, then pop, then push (a new sample is never lost to a flush or a pop)."""
    ovr = False
    if flush:
        count = 0
    elif pop and count > 0:
        count -= 1
    if push:
        if count < DEPTH:
            count += 1
        else:
            ovr = True
    return count, ovr


def check_fifo():
    errs, n = [], 0
    for count in range(DEPTH + 1):
        for push, pop, flush in itertools.product([0, 1], repeat=3):
            n += 1
            c2, ovr = fifo_step(count, push, pop, flush)
            if not 0 <= c2 <= DEPTH:
                errs.append(f"FIFO {count} {push}{pop}{flush}: occupancy {c2} out of range")
            expect_ovr = push and count == DEPTH and not pop and not flush
            if ovr != bool(expect_ovr):
                errs.append(f"FIFO {count} push={push} pop={pop} flush={flush}: OVERRUN {ovr}, expected {expect_ovr}")
            if push and not ovr and c2 == 0:
                errs.append(f"FIFO {count}: a pushed sample was lost")
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
    blank_max=15,                              # CHOP_BLANK: cycle 31 of the previous frame .. BLANK_LEN (<= 15)
    tick_cycle=24,
    rates={"128k": dict(period_frames=8, tick_frame=1), "64k": dict(period_frames=16, tick_frame=3)},
    timers=dict(T_WARM=(5e-3, 5e-3, 255e-3), T_REC=(0.22e-3, 0.25e-3, 4e-3), T_PRE=(20e-6, 20e-6, 255e-6),
                T_RST=(100e-6, 100e-6, 4e-3)),          # (analog minimum, default, maximum)
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
        for tn, (mn, df, mx) in T["timers"].items():
            for label, v in (("default", df), ("minimum", mn)):
                actual = -(-v // tick_s) * tick_s if v > 0 else tick_s
                if actual < mn - 1e-12:
                    errs.append(f"{name} {tn} {label}: {actual * 1e6:.2f} us is below the analog minimum")
            notes.append(f"{name} {tn}: default {df * 1e6:g} us -> {(-(-df // tick_s)) * tick_s * 1e6:.2f} us on the tick grid")
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
    "タイマ：タイマを持つ状態は、満了で必ずその状態を出る",
    "同時の事象（シーケンサ）：1 tick の命令（0〜1 個）とタイマの満了の全ての組み合わせ、および出力の時刻（tick と同じサイクルにはならない）について、全ての条件の値で、優先順位の規則による結果が次の性質を満たす",
    "  AFE_RST の解除は必ず RECOVER（ADC の復帰待ち）に入る",
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
    "  FIFO を空にするのは START と FLUSH のみ",
    "  STOP は必ず IDLE へ。命令は実行されるか、定義による無視か、エラーのフラグのいずれか（黙って捨てられない）",
    "SPI（条件の全ての値で列挙）：書き込みの確定は、完全で CRC 検査済みの、書き込み可能なアドレスへのフレームの CS_N の立ち上がりのみ（前の命令が未処理なら確定しない）。CRC の不一致は CRC_ERR。取り出しは 7 バイトちょうどのサンプルの読み出しのみ。CS_N の立ち上がりは必ず IDLE へ戻り、バイトの途中と不完全・過長な書き込みは FRAME_ERR",
    f"FIFO（深さ {DEPTH}）：同じサイクルの格納・取り出し・クリアの全ての組み合わせで、占有数が範囲内、OVERRUN は満杯への格納（取り出しとクリアなし）のときのみ、格納したサンプルは失われない",
    "時刻（アナログとの関係）：tick のサイクルが比較器、TH、DAC、CIC の出力、CHOP1 の縁、ブランキングの窓と重ならない。tick はチョッパの相 A の中ほど（半周期の 25〜75 %）。タイマの既定値と最小値を tick の格子に切り上げてもアナログの最小値以上。1 ms がチョッパの周期の整数倍。CHOP1 の全ての周期が 1 ms を割り切り、速さの切り替えで旧い相に残る CIC の重みが 1e−6 以下。tick の間に命令が 2 つ届きうる場合に SPI の未処理の規則がある",
]


def run_checks(verbose=True):
    report, total = [], 0
    for F, must, excl in ((SEQ, ["IDLE", "RUN"], ("RST",)), (SPI, ["IDLE"], ())):
        report += check_tables(F) + check_graph(F, must, excl)
    e, n1 = check_seq_ticks()
    report += e
    e, n2 = check_spi_props()
    report += e
    e, n3 = check_fifo()
    report += e
    e, tnotes = check_timing()
    report += e
    total = n1 + n2 + n3
    if verbose:
        print(f"checked: SEQ {len(SEQ_STATES)} states x {len(SEQ_EVENTS)} events, {n1} tick combinations; "
              f"SPI {len(SPI_STATES)} states x {len(SPI_EVENTS)} events, {n2} branches; FIFO {n3} cases")
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


def mermaid(F, title, notes=(), self_loops=(), lump=None, hide=()):
    """Hierarchical state diagram. A transition shared (same event, guard, actions, target) by every leaf of a
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


def generate():
    rep, _ = run_checks(verbose=True)
    if rep:
        print("not generating: fix the violations first")
        return 1
    seq_mmd = mermaid(SEQ, "sequencer", hide=("RST",),
                      notes=[("RESET", ["RST (RESET_N = 0 or SOFT_RESET) from any state leads to RESET.",
                                        "Self-loops and errors: see the transition table."])],
                      self_loops=[("RUN", "APPLY_NR [cfg_ok & nr_ok] / apply, mark<br/>OUT / store")])
    spi_mmd = mermaid(SPI, "SPI transaction", lump=[("FRAME", "CSR", "CSR / commit, pop or error (see the table)")],
                      self_loops=[("RREG", "BYTE [!crc_en] / addr_inc, load_data"),
                                  ("RSMP", "BYTE [!last] / next_byte")])
    files = {"seq_fsm.mmd": seq_mmd, "spi_fsm.mmd": spi_mmd}
    seq_tabs = tables_md(SEQ, [("STATE", lambda x: "—" if x[1] is None else str(x[1])),
                               ("AFE_RST", lambda x: str(x[3])),
                               ("READY", lambda x: "1" if x[0] == "RUN" else "0"),
                               ("タイマ", lambda x: x[4] or "—"),
                               ("上位の状態", lambda x: " ⊂ ".join(parent_chain(SEQ, x[0])) or "—")])
    spi_tabs = tables_md(SPI, [("上位の状態", lambda x: " ⊂ ".join(parent_chain(SPI, x[0])) or "—")])
    for k, v in files.items():
        with open(os.path.join(HERE, k), "w", encoding="utf-8") as f:
            f.write(v)
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
    with open(DOC, "w", encoding="utf-8") as f:
        f.write(doc)
    print("wrote", ", ".join(files), "and the generated blocks of", os.path.relpath(DOC, REPO))
    return 0


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
    ]
    global fifo_step
    fifo_orig = fifo_step

    def fifo_bad_flush_drops_push(count, push, pop, flush):
        if flush:
            return 0, False
        return fifo_orig(count, push, pop, flush)

    def fifo_bad_pop_after_push(count, push, pop, flush):
        ovr = False
        if flush:
            count = 0
        if push:
            if count < DEPTH:
                count += 1
            else:
                ovr = True
        if pop and count > 0 and not flush:
            count -= 1
        return count, ovr

    fifo_mut = [("FLUSH と同じサイクルの格納を捨てる", fifo_bad_flush_drops_push),
                ("取り出しより先に格納（満杯で取り出しと同時の格納が OVERRUN）", fifo_bad_pop_after_push)]
    results, ok = [], True
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


def render():
    """PNG of each generated diagram (headless Google Chrome; Mermaid 11.4.1 from jsDelivr). The Markdown keeps the
    Mermaid source, which GitHub draws itself; the PNGs are for viewing elsewhere."""
    import html
    import subprocess
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not os.path.exists(chrome):
        print("Google Chrome not found; skipped")
        return 1
    build = os.path.join(HERE, "..", "build")
    os.makedirs(build, exist_ok=True)
    for name, size in (("seq_fsm", "720,2500"), ("spi_fsm", "1080,1150")):
        src = open(os.path.join(HERE, name + ".mmd"), encoding="utf-8").read()
        page = os.path.join(build, name + ".html")
        with open(page, "w", encoding="utf-8") as f:
            f.write("<!doctype html><html><head><meta charset='utf-8'><style>body{margin:8px;background:#fff}</style>"
                    f"</head><body><pre class='mermaid'>{html.escape(src)}</pre><script type='module'>"
                    "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs';"
                    "mermaid.initialize({startOnLoad:false, theme:'default'});"
                    "await mermaid.run({querySelector:'.mermaid'});</script></body></html>")
        out = os.path.join(HERE, name + ".png")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        f"--window-size={size}", "--virtual-time-budget=15000", f"--screenshot={out}",
                        "file://" + os.path.abspath(page)], check=True, capture_output=True)
        print("wrote", os.path.relpath(out, REPO))
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
    print(__doc__)
