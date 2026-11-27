#!/usr/bin/env python3
"""Timing diagrams of the digital control (WaveDrom), generated from fsm_spec.TIMING and regmap.py (11/19).

Writes wave_<name>.json (WaveDrom source) and wave_<name>.png (headless Google Chrome, WaveDrom 3.5.0 from jsDelivr)
next to this file:
  frame    one frame (32 MCLK) with every event of the existing frame timing and the tick (cycle 24, outputs at e25)
  chop     the chopper period at 128 and 64 kHz, the tick in the middle of phase A, the CIC output time
  startup  RESET_N .. RUN (schematic, not to scale; the durations from the timers' reset values in regmap.py)
  apply    APPLY in RUN: PRE, PULSE, RECOVER, ALIGN, FILL, RUN with the FIFO emptied at the APPLY's tick (schematic;
           the durations from regmap.py)
  spi      the SPI frames at byte level: write, write with CRC, register read (burst), read with CRC, sample read
           (generated from fsm_spec's SPI table and SAMPLE_BYTES; audit round 15)

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/wave.py [fresh | selftest]
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fsm_spec as FS  # noqa: E402
import regmap as RM  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WD = "https://cdn.jsdelivr.net/npm/wavedrom@3.5.0"


def levels(n, high, start=0):
    """WaveDrom wave string: '1' at the positions in high, '0' elsewhere, repeats as '.'."""
    out, prev = [], None
    for i in range(n):
        v = "1" if (i + start) in high else "0"
        out.append("." if v == prev else v)
        prev = v
    return "".join(out)


def frame():
    T = FS.TIMING
    # the strobes from fsm_spec.TIMING (audit round 35, auditor C: they were hand-written cycles no check read): the
    # busy cycles by their labels, the DAC's from dac_load_cycle (a strobe is high in the cycle before its edge)
    busy = FS.busy_all(T)
    cyc = lambda prefix: next(c for c, s in busy.items() if s.startswith(prefix))
    c_cmp, c_th, c_out, c_c1, d = cyc("CMP_STROBE"), cyc("TH の取り込み"), cyc("CIC の出力"), cyc("CHOP1"), T["dac_load_cycle"]
    pos = [31] + list(range(32))                      # cycle 31 of the previous frame, then cycles 0..31
    n = len(pos)
    hi = lambda cyc: {i for i, c in enumerate(pos) if c in cyc and not (i == 0 and c != 31)}
    # CHOP_BLANK: from cycle 31 of the previous frame for BLANK_LEN + 1 cycles (cycles 31, 0 .. BLANK_LEN - 1)
    blank = {0} | {i for i, c in enumerate(pos) if i > 0 and c < T["blank_max"]}
    tc = T["tick_cycle"]
    up = pos.index(tc) + 1                          # the outputs change at the edge that ends the tick cycle
    sig = [
        {"name": "MCLK", "wave": "p" + "." * (n - 1)},
        {"name": "フレームサイクル", "wave": "=" * n, "data": [str(c) for c in pos]},
        {},
        {"name": "ADC：CMP_STROBE", "wave": levels(n, hi({c_cmp}))},
        {"name": f"ADC：TH_CAPTURE（e{c_th} で取り込み）", "wave": levels(n, hi({c_th - 1}))},
        {"name": f"ADC：DAC_LOAD（e{d + 1} で SEL 更新）", "wave": levels(n, hi({d}))},
        {"name": "ADC：CIC の入力", "wave": levels(n, hi({T["cic_in_cycle"]}))},  # eeg_clkgen's cic_en (TIMING, round 44)
        {"name": "ADC：DAC_CLK", "wave": levels(n, hi({d + 2}))},
        {},
        {"name": "縁のフレーム：CHOP／CHOP_OUT", "wave": levels(n, set(range(1, n)))},
        {"name": f"縁のフレーム：CHOP_BLANK（{T['blank_max']}）", "wave": levels(n, blank)},   # captions from TIMING (audit round 14)
        {"name": "出力のフレーム：CIC の出力", "wave": levels(n, hi({c_out}))},
        {"name": "CHOP1 の縁のフレーム：CHOP1", "wave": levels(n, {i for i, c in enumerate(pos) if i > 0 and c >= c_c1})},
        {},
        {"name": "新設：tick（相 A の中ほど）", "wave": levels(n, hi({tc}))},
        {"name": "新設：AFE_RST・設定の出力", "wave": "=" + "." * (up - 1) + "=" + "." * (n - up - 1),
         "data": ["旧い値", "新しい値"]},
    ]
    return {"signal": sig, "head": {"text": "1 フレーム（32 MCLK ＝ 0.977 µs）：既存の事象と新設の tick"},
            "foot": {"text": "左端は前のフレームの cycle 31。ストローブは cycle k の間 High、出力はその終わりの縁（e(k+1)）で変わる。"
                             f"tick は cycle {tc}、出力は e{tc + 1}"},
            "config": {"hscale": 1}}


def chop():
    # 16 frames, 2 slots (16 MCLK) per frame; every lane from fsm_spec.TIMING (audit round 45, auditor C: the CHOP
    # halves and the CIC output's frame and cycle were hand-written, and check compared no lane of this diagram)
    T = FS.TIMING
    n = 32
    slot = lambda f, c: 2 * f + c // 16
    r128, r64 = T["rates"]["128k"], T["rates"]["64k"]
    tc = T["tick_cycle"]
    t128 = {slot(f, tc) for f in range(16) if f % r128["period_frames"] == r128["tick_frame"]}
    t64 = {slot(f, tc) for f in range(16) if f % r64["period_frames"] == r64["tick_frame"]}
    f_out = (T["decimation"] - 1) % 16                  # the output frame (the ms's last) among the 16 drawn
    c_out = next(c for c, s in FS.busy_all(T).items() if s.startswith("CIC の出力"))
    out = {slot(f_out, c_out)}
    half = lambda r: {i for i in range(n) if (i // 2) % r["period_frames"] < r["period_frames"] // 2}   # phase A
    c128, c64 = half(r128), half(r64)
    sig = [
        {"name": "フレーム", "wave": "=." * 16, "data": [str(f) for f in range(16)]},
        {},
        {"name": "128 kHz：CHOP", "wave": levels(n, c128)},    # short lane names: a longer one was drawn past the
        {"name": "128 kHz：tick", "wave": levels(n, t128)},
        {},
        {"name": "64 kHz：CHOP", "wave": levels(n, c64)},      # figure's left edge ("28 kHz", audit round 23, A)
        {"name": "64 kHz：tick", "wave": levels(n, t64)},
        {},
        {"name": "CIC の出力", "wave": levels(n, out)},
    ]
    return {"signal": sig,
            "head": {"text": f"チョッパの周期と tick（CHOP の 1 は相 A）：相 A の中ほど（128 kHz で縁から {r128['tick_frame'] * 32 + tc} MCLK、"
                             f"64 kHz で {r64['tick_frame'] * 32 + tc} MCLK）に 1 周期 1 回"},
            "foot": {"text": f"CIC の出力は {T['decimation']:,} フレーム目（フレーム番号 ≡ {f_out} mod 16）の cycle {c_out}。"
                             "tick とは同じサイクルにならない"},
            "config": {"hscale": 1}}


def timer_text(name):
    """The timer's reset value as a duration: T_WARM, T_ELEC in ms; T_REC, T_PRE, T_RST in 8-frame units."""
    v = next(f for *_, f in RM.all_fields() if f["name"] == name)["reset"]
    if name in ("T_WARM", "T_ELEC"):
        return f"{name} {v} ms"
    us = v * 8 * FS.FRAME / FS.MCLK * 1e6
    return f"{name} {us:.4g} µs" if us < 1000 else f"{name} {us / 1000:.4g} ms"


def time_label(state):
    """The 時間 labels the startup and APPLY diagrams may show in a state (audit round 45, auditor C: they were written
    here and compared with nothing; FILL's 3 outputs drawn as 2 and the T_PRE and T_RST labels swapped passed every
    check): a timed state its timer's reset value (timer_text of SEQ_TIMERS_REQUIRED's timer, written apart from the
    table), FILL the outputs from the CIC's clear to its first valid output (the CIC's order, with or without their
    duration), ALIGN at most one output interval, RUN one output an interval; None in a state with no duration (RESET,
    IDLE's '設定')."""
    T = FS.TIMING
    ms = T["decimation"] * FS.FRAME / FS.MCLK * 1e3          # the output interval
    if state in FS.SEQ_TIMERS_REQUIRED:
        return {timer_text(FS.SEQ_TIMERS_REQUIRED[state])}
    k = T["cic_order"]
    return {"FILL": {f"{k} 出力", f"{k} 出力（{k * ms:g} ms）"}, "ALIGN": {f"≤ {ms:g} ms"},
            "RUN": {f"{ms:g} ms ごと"}}.get(state)


def startup():
    st = ["RESET", "IDLE", "WARMUP", "RECOVER", "ALIGN", "FILL", "RUN"]
    dur = ["", "設定", timer_text("T_WARM"), timer_text("T_REC"), "≤ 1 ms", "3 出力（3 ms）", "1 ms ごと"]
    sig = [
        {"name": "RESET_N", "wave": "01" + "." * 13},
        {"name": "命令", "wave": "x.=x" + "." * 11, "data": ["START"]},
        {"name": "状態", "wave": "==.=.=.=.=.=...", "data": st},
        {"name": "時間", "wave": "x=.=.=.=.=.=...", "data": dur[1:]},
        {"name": "AFE_RST", "wave": "1....0........."},
        {"name": "CIC", "wave": "x........=.=...", "data": ["クリア後の充填", "有効"]},
        {"name": "READY", "wave": "0..........1..."},
        {"name": "FIFO", "wave": "=..=.......=...", "data": ["", "空（START の tick）", "格納"]},
        {"name": "DRDY_N（パルス）", "wave": "1..........0101"},
    ]
    return {"signal": sig, "head": {"text": "起動（模式図、時間の比は実際と異なる。T_ELEC ＞ 0 なら RECOVER のあとに WAIT_E）"},
            "foot": {"text": "AFE_RST の縁と設定の反映は tick（相 A の中ほど）で。SEQ は RESET_N の解除から数え続ける"},
            "config": {"hscale": 2}}


def apply_seq():
    st = ["RUN", "PRE", "PULSE", "RECOVER", "ALIGN", "FILL", "RUN"]
    dur = ["", timer_text("T_PRE"), timer_text("T_RST"), timer_text("T_REC"), "≤ 1 ms", "3 出力", ""]
    sig = [
        {"name": "命令", "wave": "x=x" + "." * 13, "data": ["APPLY"]},
        {"name": "状態", "wave": "=.=.=.=.=.=.=...", "data": st},
        {"name": "時間", "wave": "x.=.=.=.=.=.x...", "data": dur[1:6]},
        {"name": "アクティブの設定", "wave": "=.=.............", "data": ["旧い値", "新しい値（PRE の入口の tick で一括）"]},
        {"name": "AFE_RST", "wave": "0...1.0........."},
        {"name": "READY", "wave": "1.0.........1..."},
        {"name": "FIFO", "wave": "=.=.........=...", "data": ["旧い設定のサンプル", "空（APPLY の tick で空にする）", "格納"]},
        {"name": "DRDY_N（パルス）", "wave": "01..........0101"},   # active low, as wave_startup (audit round 9)
    ]
    return {"signal": sig, "head": {"text": "APPLY（パルス付きの一括反映、模式図。T_ELEC ＞ 0 なら RECOVER のあとに WAIT_E）"},
            "foot": {"text": "再整定の間の出力は格納しない（SEQ は 1 ms ごとに数え続け、欠けた数が分かる）"},
            "config": {"hscale": 2}}


# the frames of the SPI diagram: (title, kind, CRC on, length). A write and a sample take the length at which the
# table commits or pops (None); the reads show 3 bytes (CRC on: the data and its CRC; off: two addresses).
SPI_FRAMES = [("書き込み", "write", 0, None), ("書き込み（CRC）", "write", 1, None), ("読み出し（連続）", "read", 0, 3),
              ("読み出し（CRC）", "read", 1, 3), ("サンプル", "sample", 1, None)]
# check's messages (selftest: each is expected by a mutation, each mutation gives its own)
MSG = {"path": "is not a transition of the table", "lane": ", but the table gives",
       "spi_accept": "that the table completes without an error flag",
       "spi_status": "MISO does not load STATUS at the frame's start (CS_N falling)",
       "spi_sample": "sample bytes loaded by the table, but fsm_spec.SAMPLE_BYTES names",
       "frame": ", but fsm_spec.TIMING gives",   # audit round 35, auditor C (round 44: CIC input, CHOP, CHOP_BLANK)
       "frame_lanes": " lanes named so in the frame diagram, where the check needs exactly",   # audit round 36, C
       # audit round 44, auditor C: the FIFO, DRDY_N, active-setting and CIC lanes and a missing lane
       "fifo": ", but the table's flush (the command's tick) and first store give",
       "active": ", but the table's apply (the command's tick) gives",
       "cic": ", but the table's cic_clear and first store give (undrawn before the clear)",
       "drdy": ", where no output time stores a sample: DRDY_N pulses only in",
       "missing": " missing; the check compares these lanes with the table:",
       # audit round 45, auditor C: the chopper diagram, the 時間 labels and DRDY_N's pulse in each storing segment
       "chop": ", but fsm_spec.TIMING's rates, tick and CIC output give",
       "chop_lanes": " lanes named so in the chopper diagram, where the check needs exactly",
       "time": ", but the timers' reset values and TIMING give",
       "drdy_store": ", where every output time stores a sample: DRDY_N pulses in each segment of",
       # audit round 46, auditor C: the startup diagram's RESET_N lane
       "reset": ", where RESET_N is Low exactly in the state lane's RESET columns: expected"}


def sample_labels():
    """The sample bytes' labels from fsm_spec.SAMPLE_BYTES (a 2-byte field: 上, 下; a 3-byte one: 上, 中, 下)."""
    out = []
    for _id, lab, n in FS.SAMPLE_BYTES:
        sfx = {1: [""], 2: [" 上", " 下"], 3: [" 上", " 中", " 下"]}.get(n) or [f" {i + 1}" for i in range(n)]
        out += [lab + x for x in sfx]
    return out


def spi_lanes(kind, crc_en, length):
    """One frame of the SPI diagram from fsm_spec's SPI table (audit round 15, auditor B: the five frames were typed
    here by hand, so a changed frame definition left the diagram stale while every check passed). Returns (MOSI
    labels, MISO labels, problems). MOSI: the header, then what the table latches (データ, CRC) or 0x00. MISO: STATUS
    during the header, then what the table loads at the end of each byte (a write loads nothing: 0x00; a sample
    loads its copy's bytes, named from fsm_spec.SAMPLE_BYTES)."""
    tag = f"wave_spi: {kind} frame (CRC {'on' if crc_en else 'off'})"
    env = dict(rw=int(kind != "write"), smp=int(kind == "sample"), crc_en=crc_en, addr_ok=1,
               wr_ok=int(kind == "write"), busy=0, crc_ok=1, head=1)
    goal = {"write": "commit", "sample": "pop"}.get(kind)
    found = None
    for n in ([length] if length else range(1, 11)):
        tr = []
        w = FS.spi_walk(n, 0, env, trace=tr)
        if w and not {"FRAME_ERR", "ADDR_ERR", "CRC_ERR", "STATE_ERR"} & set(w[0]) and (goal is None or goal in w[0]):
            found = (n, tr)
            break
    if found is None:
        return None, None, [f"{tag}: no {length or '1..10'}-byte frame {MSG['spi_accept']}"]
    n, tr = found
    smp_addr = next(a for a, nm, *_ in RM.REGS if nm == "SAMPLE")
    mosi = [{"write": "W＋adr", "read": "R＋adr"}.get(kind, f"R＋0x{smp_addr:02X}")]
    csf = [a for e, a in tr if e == "CSF"]
    miso, probs = ["STATUS" if csf and "load_status" in csf[0] else "?"], []
    if miso[0] != "STATUS":
        probs.append(f"{tag}: {MSG['spi_status']}")
    byte_acts = [a for e, a in tr if e == "BYTE"]
    names, k_s, off = sample_labels(), 0, 0
    for i, acts in enumerate(byte_acts):
        if i:
            mosi.append("データ" if "latch_data" in acts else "CRC" if "latch_crc" in acts else "0x00")
        off += acts.count("addr_inc")
        smp = "snapshot" in acts or "next_byte" in acts
        if i < n - 1:                                     # what the last byte loads is not shifted out
            if "load_data" in acts:
                miso.append("[adr]" if off == 0 else f"[adr＋{off}]")
            elif "load_crc" in acts:
                miso.append("CRC")
            elif smp:
                miso.append(names[k_s] if k_s < len(names) else "?")
            else:
                miso.append("0x00")                       # load_zero, or a write (its MISO is 0x00)
        k_s += smp
    if kind == "sample" and k_s != len(names):
        probs.append(f"{tag}: {k_s} {MSG['spi_sample']} {len(names)}")
    return mosi, miso, probs


def spi():
    def frame_(name, mosi, miso):
        k = len(mosi)
        return [name,
                {"name": "CS_N", "wave": "1" + "0" + "." * (2 * k - 1) + "1"},
                {"name": "MOSI", "wave": "x" + "=." * k + "x", "data": mosi},
                {"name": "MISO", "wave": "z" + "=." * k + "z", "data": miso}]
    sig = []
    for title, kind, crc_en, length in SPI_FRAMES:      # each frame from fsm_spec's SPI table (audit round 15)
        mosi, miso, _p = spi_lanes(kind, crc_en, length)
        sig += ([{}] if sig else []) + [frame_(title, mosi or ["?"], miso or ["?"])]
    return {"signal": sig, "head": {"text": "SPI のフレーム（1 区切り ＝ 8 SCLK、モード 0、MSB 先頭）"},
            "foot": {"text": "先頭バイト：bit 7 ＝ R/W（1 ＝ 読み出し）、bit 6:0 ＝ アドレス"},
            "config": {"hscale": 2}}


DIAGRAMS = {"frame": (frame, 1900), "chop": (chop, 1900), "startup": (startup, 1500), "apply": (apply_seq, 1700),
            "spi": (spi, 2300)}


def render(name, src, width):
    page = os.path.join(HERE, "..", "build", f"wave_{name}.html")
    os.makedirs(os.path.dirname(page), exist_ok=True)
    with open(page, "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'>"
                f"<script src='{WD}/skins/default.js'></script><script src='{WD}/wavedrom.min.js'></script>"
                "<style>body{margin:8px;background:#fff;font-family:'Hiragino Sans',sans-serif}</style></head>"
                "<script>function clipCheck(){var bad=[];document.querySelectorAll('svg text').forEach(function(t){"
                "var s=t;while(s.ownerSVGElement)s=s.ownerSVGElement;var r=s.getBoundingClientRect(),b=t.getBoundingClientRect();"
                "if(b.width>0&&(b.left<r.left-0.5||b.right>r.right+0.5))bad.push(t.textContent);});"
                "var p=document.createElement('pre');p.style.display='none';p.textContent='CLIPCHECK '+JSON.stringify(bad);"
                "document.body.appendChild(p);}</script>"
                "<body onload='WaveDrom.ProcessAll();clipCheck()'><script type='WaveDrom'>"
                + json.dumps(src, ensure_ascii=False) + "</script></body></html>")
    out = os.path.join(HERE, f"wave_{name}.png")
    raw = os.path.join(os.path.dirname(page), f"wave_{name}.raw.png")
    from PIL import Image, ImageChops               # trim the white margin; keep the JSON's SHA-256 ('fresh')
    for budget in (10000, 30000, 60000):            # WaveDrom draws nothing until it ran: a blank capture is retried
        if os.path.exists(raw):
            os.remove(raw)
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        f"--window-size={width},900", f"--virtual-time-budget={budget}", f"--screenshot={raw}",
                        "file://" + os.path.abspath(page)], check=True, capture_output=True)
        im = Image.open(raw).convert("RGB")
        box = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
        if box:
            pad = 16
            im = im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width),
                          min(box[3] + pad, im.height)))
            clipped = clip_check(page, budget)
            if clipped:                             # (audit round 23, auditor A: '128 kHz' was drawn as '28 kHz')
                raise RuntimeError(f"wave_{name}: labels drawn past the figure's edges, not written: {clipped}")
            FS.save_tagged_png(im, out, json_text(src))
            return out
    raise RuntimeError(f"wave_{name}: WaveDrom drew nothing (blank capture); not written")


def clip_check(page, budget):
    """The labels WaveDrom drew past its figure's left or right edge (the SVG clips them: a lane name wider than the
    name column lost its first character). From the page's DOM after WaveDrom ran (clipCheck in the page)."""
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--virtual-time-budget={budget}", "--dump-dom",
                        "file://" + os.path.abspath(page)], check=True, capture_output=True, text=True)
    m = re.search(r"CLIPCHECK (\[.*?\])<", r.stdout)
    if not m:
        raise RuntimeError(f"{os.path.basename(page)}: the label check did not run (no CLIPCHECK in the DOM)")
    return json.loads(m.group(1).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


def json_text(src):
    """The wave_*.json file's text for a diagram source (what the PNG's SHA-256 is taken over)."""
    return json.dumps(src, ensure_ascii=False, indent=1)


def lane_values(wave, data=None):
    """Per column: a WaveDrom lane's value ('0' / '1' levels, the data of '=' segments; '.' continues; else None)."""
    out, cur, k = [], None, 0
    for ch in wave:
        if ch in "01":
            cur = ch
        elif ch == "=":
            cur = data[k] if data is not None else "="
            k += 1
        elif ch != ".":
            cur = None
        out.append(cur)
    return out


# the lanes of the startup and APPLY diagrams the check compares with the table (audit round 44, auditor C: a missing
# lane must not pass silently)
LANES_CHECKED = {"startup": ("状態", "命令", "時間", "RESET_N", "AFE_RST", "READY", "FIFO", "DRDY_N（パルス）", "CIC"),
                 "apply": ("状態", "命令", "時間", "AFE_RST", "READY", "FIFO", "DRDY_N（パルス）", "アクティブの設定")}


def store_states():
    """The states an output time stores a sample in (DRDY_N pulses only there): the state of an OUT branch with
    'store' that stays, and the state such a branch enters (FILL's first valid output is stored on entering RUN)."""
    out = set()
    for (s, e), cell in FS.SEQ["table"].items():
        if e == "OUT" and isinstance(cell, list):
            out |= {br["next"] or s for br in cell if isinstance(br, dict) and "store" in br["actions"]}
    return out


def action_lanes(name, lanes, st):
    """The FIFO, アクティブの設定, CIC and DRDY_N（パルス） lanes against the actions of the table's branches on the
    drawn path (audit round 44, auditor C: they were drawn by hand and compared with nothing; eight wrong lanes passed).
    The drawn command's branch is the one that enters the next drawn state: at that state's first column (the
    command's tick) 'flush' empties the FIFO ('空…') and 'apply' applies the settings ('新しい値…'). Where an OUT branch
    with 'cic_clear' enters its state the CIC starts filling (undrawn before); where one with 'store' enters its state
    the CIC is valid ('有効') and the FIFO stores ('格納'). Each of these lanes changes exactly there. DRDY_N pulses (Low)
    only in a state an output time stores in, and in each segment of such a state (audit round 45, auditor C: a DRDY_N
    never Low passed)."""
    errs, tag, tbl = [], f"wave_{name}", FS.SEQ["table"]
    branches = lambda s, e: [b for b in (tbl.get((s, e)) if isinstance(tbl.get((s, e)), list) else []) if isinstance(b, dict)]
    seg = [(x, i) for i, x in enumerate(st) if x is not None and (i == 0 or st[i - 1] != x)]
    want = {"FIFO": {}, "アクティブの設定": {}, "CIC": {}}
    cmd = lane_values(lanes["命令"]["wave"], lanes["命令"].get("data"))
    for c in [i for i, v in enumerate(cmd) if v is not None and (i == 0 or cmd[i - 1] != v)]:
        nxt = next(((x, i) for x, i in seg if i > c), None)
        br = next((b for b in branches(st[c], cmd[c]) if nxt is not None and b["next"] == nxt[0]), None)
        if br is None:
            errs.append(f"{tag}: {cmd[c]} in {st[c]} then {nxt[0] if nxt else 'no state'} {MSG['path']}")
            continue
        if "flush" in br["actions"]:
            want["FIFO"][nxt[1]] = "空"
        if "apply" in br["actions"]:
            want["アクティブの設定"][nxt[1]] = "新しい値"
    for (a, _i0), (b, i1) in zip(seg, seg[1:]):
        for br in branches(a, "OUT"):
            if br["next"] == b and "cic_clear" in br["actions"]:
                want["CIC"][i1] = ""                     # the filling: any drawn value
            if br["next"] == b and "store" in br["actions"]:
                want["CIC"][i1] = "有効"
                want["FIFO"][i1] = "格納"
    for lane, key in (("FIFO", "fifo"), ("アクティブの設定", "active"), ("CIC", "cic")):
        if lane not in lanes:
            continue
        vals = lane_values(lanes[lane]["wave"], lanes[lane].get("data"))
        got = {i: vals[i] for i in range(1, len(vals)) if vals[i] != vals[i - 1]}
        w = want[lane]
        bad = set(got) ^ set(w) or {i for i in w if got[i] is None or not str(got[i]).startswith(w[i])}
        if lane == "CIC" and w:
            bad |= {i for i in range(min(w)) if vals[i] is not None}
        if bad:
            errs.append(f"{tag}: {lane} changes at columns {sorted(got.items())}{MSG[key]} {sorted(w.items())}")
    dv = lane_values(lanes["DRDY_N（パルス）"]["wave"])
    sst = store_states()
    off = [i for i, v in enumerate(dv) if v == "0" and st[i] not in sst]
    if off:
        errs.append(f"{tag}: DRDY_N Low in columns {off} ({', '.join(str(st[i]) for i in off)}){MSG['drdy']} {sorted(sst)}")
    for k_, (x, i0) in enumerate(seg):                 # a pulse in each storing segment (audit round 45, auditor C)
        i1 = seg[k_ + 1][1] if k_ + 1 < len(seg) else len(st)
        if x in sst and not any(dv[i] == "0" for i in range(i0, i1)):
            errs.append(f"{tag}: DRDY_N not Low in {x} (columns {i0}..{i1 - 1}){MSG['drdy_store']} {sorted(sst)}")
    return errs


def check():
    """The startup and APPLY diagrams against fsm_spec's table (audit round 4: the waveforms are written here, only
    their durations came from the timers): the drawn states form a path of the table, and the AFE_RST and READY lanes
    are the drawn state's at every column (SEQ_STATES' AFE_RST; READY = RUN); the FIFO, DRDY_N, active-setting and
    CIC lanes follow the actions of the branches the path takes (action_lanes; audit round 44, auditor C); the 時間
    labels are each state's (time_label; audit round 45, auditor C). The frame diagram's lanes are TIMING's (strobes,
    the CIC input, CHOP's edge at e0, CHOP_BLANK, the CIC output, CHOP1's edge, and since audit round 45 the tick and
    the edge its outputs change at), and so are the chopper diagram's (CHOP's phase A at each rate, the ticks, the CIC
    output).
    The SPI diagram's frames are generated from the SPI table (spi_lanes): each must complete without an error flag,
    load STATUS during its header, and a sample load as many bytes as fsm_spec.SAMPLE_BYTES names (audit round 15)."""
    errs = []
    afe = {x[0]: str(x[3]) for x in FS.SEQ_STATES}
    for name, fn in (("startup", startup), ("apply", apply_seq)):
        lanes = {ln["name"]: ln for ln in fn()["signal"] if isinstance(ln, dict) and "name" in ln}
        miss = [ln for ln in LANES_CHECKED[name] if ln not in lanes]
        if miss:
            errs.append(f"wave_{name}: lane(s) {miss}{MSG['missing']} {list(LANES_CHECKED[name])}")
            continue
        st = lane_values(lanes["状態"]["wave"], lanes["状態"]["data"])
        seq = [x for i, x in enumerate(st) if x is not None and (i == 0 or st[i - 1] != x)]
        for a, b in zip(seq, seq[1:]):
            if not any(isinstance(c, list) and any(br["next"] == b for br in c)
                       for (s0, _e), c in FS.SEQ["table"].items() if s0 == a):
                errs.append(f"wave_{name}: {a} -> {b} {MSG['path']}")
        for lane, want in (("AFE_RST", lambda x: afe[x]), ("READY", lambda x: "1" if x == "RUN" else "0")):
            for i, (x, v) in enumerate(zip(st, lane_values(lanes[lane]["wave"]))):
                if x is not None and v is not None and v != want(x):
                    errs.append(f"wave_{name}: column {i}: {lane} {v} in {x}{MSG['lane']} {want(x)}")
        # RESET_N (the startup diagram; audit round 46, auditor C: drawn never released, released after the START or
        # falling again in RUN, it passed every check): Low exactly in the state lane's RESET columns
        if "RESET_N" in lanes:
            for i, (x, v) in enumerate(zip(st, lane_values(lanes["RESET_N"]["wave"]))):
                w_ = "0" if x == "RESET" else "1"
                if x is not None and v is not None and v != w_:
                    errs.append(f"wave_{name}: column {i}: RESET_N {v} in {x}{MSG['reset']} {w_}")
        # the 時間 labels (audit round 45, auditor C): each column's label is its state's, and a timed state, ALIGN and
        # FILL carry one
        tv = lane_values(lanes["時間"]["wave"], lanes["時間"].get("data"))
        for i, (x, v) in enumerate(zip(st, tv)):
            ok_ = time_label(x) if x is not None else None
            if ok_ is not None and v is not None and v not in ok_:
                errs.append(f"wave_{name}: column {i}: 時間 {v!r} in {x}{MSG['time']} {sorted(ok_)}")
        segs_ = [(x, i) for i, x in enumerate(st) if x is not None and (i == 0 or st[i - 1] != x)]
        for k_, (x, i0) in enumerate(segs_):
            i1 = segs_[k_ + 1][1] if k_ + 1 < len(segs_) else len(st)
            if (x in FS.SEQ_TIMERS_REQUIRED or x in ("ALIGN", "FILL")) and all(tv[i] is None for i in range(i0, i1)):
                errs.append(f"wave_{name}: {x} (columns {i0}..{i1 - 1}) drawn without its 時間{MSG['time']} {sorted(time_label(x))}")
        errs += action_lanes(name, lanes, st)
    # the frame diagram's strobes against fsm_spec.TIMING's busy cycles (audit round 35, auditor C)
    busy = FS.busy_all()
    one = lambda prefix: [c for c, s in busy.items() if s.startswith(prefix)]
    pos = [31] + list(range(32))
    T = FS.TIMING
    d = T["dac_load_cycle"]
    # -1: cycle 31 of the previous frame. CHOP's edge at e0 (the chopper period starts with the frame: TIMING's rates
    # count the tick from it), CHOP_BLANK from 1 MCLK before it for blank_max + 1 cycles (audit round 44, auditor C)
    want = {"ADC：CMP_STROBE": {c - 0 for c in one("CMP_STROBE")}, "ADC：TH_CAPTURE": {c - 1 for c in one("TH の取り込み")},
            "ADC：DAC_LOAD": {c - 1 for c in one("SEL1／SEL2")}, "ADC：CIC の入力": {T["cic_in_cycle"]},
            "ADC：DAC_CLK": set(one("DAC_CLK（DAC1")), "縁のフレーム：CHOP／CHOP_OUT": set(range(32)),
            "縁のフレーム：CHOP_BLANK": {-1} | set(range(T["blank_max"])),
            "出力のフレーム：CIC の出力": set(one("CIC の出力")), "CHOP1 の縁のフレーム：CHOP1": set(one("CHOP1")),
            # audit round 45, auditor C: the tick (its cycle) and the analog outputs (the edge that ends the tick cycle)
            "新設：tick": {T["tick_cycle"]}, "新設：AFE_RST・設定の出力": {(T["tick_cycle"] + 1) % 32}}
    seen = {k: 0 for k in want}                       # each expected lane exactly once (audit round 36, auditor C: a
    for ln in frame()["signal"]:                      # renamed or dropped lane was skipped)
        if not isinstance(ln, dict) or "name" not in ln:
            continue
        key = next((k for k in want if ln["name"].startswith(k)), None)
        if key is None:
            continue
        seen[key] += 1
        vals = lane_values(ln["wave"])
        hi_ = {(pos[i] if i else -1) for i, v in enumerate(vals) if v == "1"}
        data_lane = key == "新設：AFE_RST・設定の出力"
        if data_lane:                                   # a data lane: the cycle its value changes in (round 45)
            dv_ = lane_values(ln["wave"], ln.get("data"))
            got = {pos[i] for i in range(1, len(dv_)) if dv_[i] != dv_[i - 1]}
        elif key.startswith("CHOP1"):                   # CHOP1: its edge, the first high cycle
            got = {min(c for c in hi_ if c >= 0)} if any(c >= 0 for c in hi_) else set()
        else:
            got = hi_
        if got != want[key]:
            errs.append(f"wave_frame: {key}: {'changes' if data_lane else 'high'} in cycles {sorted(got)} (-1: cycle 31 of the previous frame){MSG['frame']} "
                        f"{sorted(want[key])} (dac_load_cycle {d}, cic_in_cycle {T['cic_in_cycle']}, blank_max {T['blank_max']}, tick_cycle {T['tick_cycle']})")
    for key, n_ in seen.items():
        if n_ != 1:
            errs.append(f"wave_frame: {key}: {n_}{MSG['frame_lanes']} 1")
    # the chopper diagram against TIMING (audit round 45, auditor C: no lane of it was compared; CHOP inverted, a tick
    # in phase B and the CIC output in frame 14 passed every check): CHOP high in the first half of each rate's period
    # (phase A, from the frame boundary), the tick in frame tick_frame of each period at the tick cycle's slot, the CIC
    # output in frame (decimation - 1) mod 16 at its cycle (two 16-MCLK slots a frame); each lane exactly once
    slot = lambda f, c: 2 * f + c // 16
    cwant = {}
    for k_, r_ in T["rates"].items():
        P_ = r_["period_frames"]
        cwant[f"{k_[:-1]} kHz：CHOP"] = {i for i in range(32) if (i // 2) % P_ < P_ // 2}
        cwant[f"{k_[:-1]} kHz：tick"] = {slot(f, T["tick_cycle"]) for f in range(16) if f % P_ == r_["tick_frame"]}
    cwant["CIC の出力"] = {slot((T["decimation"] - 1) % 16, c) for c in one("CIC の出力")}
    cseen = {k: 0 for k in cwant}
    for ln in chop()["signal"]:
        if not isinstance(ln, dict) or "name" not in ln:
            continue
        key = next((k for k in cwant if ln["name"].startswith(k)), None)
        if key is None:
            continue
        cseen[key] += 1
        got = {i for i, v in enumerate(lane_values(ln["wave"])) if v == "1"}
        if got != cwant[key]:
            errs.append(f"wave_chop: {key}: high in slots {sorted(got)} (two 16-MCLK slots a frame){MSG['chop']} "
                        f"{sorted(cwant[key])} (tick cycle {T['tick_cycle']}, decimation {T['decimation']})")
    for key, n_ in cseen.items():
        if n_ != 1:
            errs.append(f"wave_chop: {key}: {n_}{MSG['chop_lanes']} 1")
    for _t, kind, crc_en, length in SPI_FRAMES:           # the SPI diagram (audit round 15)
        errs += spi_lanes(kind, crc_en, length)[2]
    return errs


def selftest():
    """Mutation test of check (audit round 15): each mutation is a plausible specification change the diagrams must
    follow and is detected by the message it is written for; every message is expected by a mutation; the unmutated
    sources give none."""
    import copy
    B, A = FS.B, FS.ALWAYS
    i_pre = [x[0] for x in FS.SEQ_STATES].index("PRE")

    def table(F, key, cell):                       # cell None: drop every cell of the state key
        def apply():
            orig = F["table"]
            t = copy.deepcopy(orig)
            if cell is None:
                t = {k: v for k, v in t.items() if k[0] != key}
            else:
                t[key] = cell
            F["table"] = t
            return lambda: F.__setitem__("table", orig)
        return apply

    def dac_clk_moved():                           # audit round 35, auditor C: a strobe drawn off TIMING's cycle
        orig = frame

        def drawn():
            f = orig()
            for ln in f["signal"]:
                if isinstance(ln, dict) and ln.get("name") == "ADC：DAC_CLK":
                    ln["wave"] = levels(33, {6})          # cycle 5 (DAC_CLK in cycle 4 from dac_load_cycle 2)
            return f
        globals()["frame"] = drawn
        return lambda: globals().__setitem__("frame", orig)

    def th_renamed():                              # audit round 36, auditor C: a lane renamed (and moved)
        orig = frame

        def drawn():
            f = orig()
            for ln in f["signal"]:
                if isinstance(ln, dict) and ln.get("name", "").startswith("ADC：TH_CAPTURE"):
                    ln["name"] = "ADC：TH の取り込み（e5）"
                    ln["wave"] = levels(33, {5})          # cycle 4
            return f
        globals()["frame"] = drawn
        return lambda: globals().__setitem__("frame", orig)

    def afe_rst_pre():
        saved = FS.SEQ_STATES[i_pre]
        FS.SEQ_STATES[i_pre] = saved[:3] + (1,) + saved[4:]
        return lambda: FS.SEQ_STATES.__setitem__(i_pre, saved)

    def ready_in_fill():                           # audit round 34, auditor C: the READY lane (no mutation pinned it)
        orig = startup

        def drawn():
            d = orig()
            for ln in d["signal"]:
                if isinstance(ln, dict) and ln.get("name") == "READY":
                    ln["wave"] = "0........1....."       # rising at FILL's column
            return d
        globals()["startup"] = drawn
        return lambda: globals().__setitem__("startup", orig)

    def redraw(fn_name, prefix, wave, data=None):  # audit round 44, auditor C: a lane drawn otherwise
        def apply():
            orig = globals()[fn_name]

            def drawn():
                d_ = orig()
                for ln in d_["signal"]:
                    if isinstance(ln, dict) and ln.get("name", "").startswith(prefix):
                        ln["wave"] = wave
                        if data is not None:
                            ln["data"] = data
                return d_
            globals()[fn_name] = drawn
            return lambda: globals().__setitem__(fn_name, orig)
        return apply

    def drop_lane(fn_name, lane):                  # audit round 44, auditor C: a lane dropped
        def apply():
            orig = globals()[fn_name]

            def drawn():
                d_ = orig()
                d_["signal"] = [ln for ln in d_["signal"] if not (isinstance(ln, dict) and ln.get("name") == lane)]
                return d_
            globals()[fn_name] = drawn
            return lambda: globals().__setitem__(fn_name, orig)
        return apply

    def rename(fn_name, old, new):                 # audit round 45, auditor C: a lane renamed
        def apply():
            orig = globals()[fn_name]

            def drawn():
                d_ = orig()
                for ln in d_["signal"]:
                    if isinstance(ln, dict) and ln.get("name") == old:
                        ln["name"] = new
                return d_
            globals()[fn_name] = drawn
            return lambda: globals().__setitem__(fn_name, orig)
        return apply

    low = lambda n_, cols: levels(n_, set(range(n_)) - set(cols))   # DRDY_N Low (a pulse) at the columns cols
    tt = timer_text
    muts = [
        ("起動の図：WARMUP から出る遷移を表から除く", table(FS.SEQ, "WARMUP", None), "path"),
        ("起動の図：READY を FILL で立ち上げる", ready_in_fill, "lane"),
        ("フレームの図：DAC_CLK をサイクル 5 に（TIMING の dac_load_cycle と合わない）", dac_clk_moved, "frame"),
        ("フレームの図：TH_CAPTURE の線を改名してサイクル 4 に", th_renamed, "frame_lanes"),
        ("APPLY の図：PRE で AFE_RST を 1 に（状態の表）", afe_rst_pre, "lane"),
        ("SPI の図：CRC 付きの読み出しの CRC のあとを長すぎるフレームに",
         table(FS.SPI, ("RCRC", "BYTE"), [B(A, [], "OVF")]), "spi_accept"),
        ("SPI の図：先頭バイトの間に STATUS を載せない", table(FS.SPI, ("IDLE", "CSF"), [B(A, [], "HDR")]), "spi_status"),
        ("SPI の図：サンプルの最後のバイトでも次のバイトを載せる",
         table(FS.SPI, ("RSMP", "BYTE"), [B("not last", ["next_byte"]), B("last", ["next_byte"], "SDONE")]), "spi_sample"),
        # audit round 44, auditor C: the lanes the check compared with nothing (each of these passed before)
        ("APPLY の図：FIFO を RECOVER の入口で空に（APPLY の tick でなく）",
         redraw("apply_seq", "FIFO", "=.....=.....=...", ["旧い設定のサンプル", "空（APPLY の tick で空にする）", "格納"]), "fifo"),
        ("APPLY の図：設定を RECOVER の入口で反映（PRE の入口の tick でなく）",
         redraw("apply_seq", "アクティブの設定", "=.....=.........", ["旧い値", "新しい値（PRE の入口の tick で一括）"]), "active"),
        ("APPLY の図：DRDY_N を PRE と PULSE でもパルスに", redraw("apply_seq", "DRDY_N", low(16, {0, 2, 4, 12, 14})), "drdy"),
        ("起動の図：FIFO を RUN の入口で空に（START の tick でなく）",
         redraw("startup", "FIFO", "=..........=.=.", ["", "空（START の tick）", "格納"]), "fifo"),
        ("起動の図：DRDY_N を FILL からパルスに", redraw("startup", "DRDY_N", low(15, {9, 11, 13})), "drdy"),
        ("起動の図：CIC を ALIGN から有効に", redraw("startup", "CIC", "x......=.......", ["有効"]), "cic"),
        ("起動の図：FIFO の線を除く", drop_lane("startup", "FIFO"), "missing"),
        ("フレームの図：CIC の入力をサイクル 4 に（TIMING の cic_in_cycle 3 と合わない）",
         redraw("frame", "ADC：CIC の入力", levels(33, {5})), "frame"),
        ("フレームの図：CHOP_BLANK を 3 サイクルに（見出しは TIMING の blank_max 15）",
         redraw("frame", "縁のフレーム：CHOP_BLANK", levels(33, {0, 1, 2})), "frame"),
        ("フレームの図：CHOP の縁を e1 に（フレームの境の e0 でなく）",
         redraw("frame", "縁のフレーム：CHOP／CHOP_OUT", levels(33, set(range(2, 33)))), "frame"),
        # audit round 45, auditor C: the lanes still compared with nothing (each of these passed before)
        ("フレームの図：tick をサイクル 23 に（TIMING の tick_cycle 24 と合わない）", redraw("frame", "新設：tick", levels(33, {24})), "frame"),
        ("フレームの図：設定の出力を e24 に（tick の終わりの縁 e25 でなく）",
         redraw("frame", "新設：AFE_RST・設定の出力", "=" + "." * 24 + "=" + "." * 7, ["旧い値", "新しい値"]), "frame"),
        ("チョッパの図：CIC の出力をフレーム 14 に", redraw("chop", "CIC の出力", levels(32, {28})), "chop"),
        ("チョッパの図：128 kHz の CHOP を反転（tick を相 B に描く）",
         redraw("chop", "128 kHz：CHOP", levels(32, {i for i in range(32) if (i // 2) % 8 >= 4})), "chop"),
        ("チョッパの図：64 kHz の tick を相 B（フレーム 11）に", redraw("chop", "64 kHz：tick", levels(32, {23})), "chop"),
        ("チョッパの図：64 kHz の tick の線を改名", rename("chop", "64 kHz：tick", "64 kHz の tick"), "chop_lanes"),
        ("起動の図：FILL の時間を 2 出力（2 ms）に",
         redraw("startup", "時間", "x=.=.=.=.=.=...", ["設定", tt("T_WARM"), tt("T_REC"), "≤ 1 ms", "2 出力（2 ms）", "1 ms ごと"]), "time"),
        ("APPLY の図：T_PRE と T_RST の時間の札を入れ替える",
         redraw("apply_seq", "時間", "x.=.=.=.=.=.x...", [tt("T_RST"), tt("T_PRE"), tt("T_REC"), "≤ 1 ms", "3 出力"]), "time"),
        ("起動の図：DRDY_N を Low にしない（RUN の格納にパルスなし）", redraw("startup", "DRDY_N", "1" + "." * 14), "drdy_store"),
        # audit round 46, auditor C: the startup diagram's RESET_N lane
        ("起動の図：RESET_N を解除しない", redraw("startup", "RESET_N", "0" + "." * 14), "reset"),
        ("起動の図：RESET_N を START のあと（列 4）に解除", redraw("startup", "RESET_N", "0...1" + "." * 10), "reset"),
        ("起動の図：RESET_N を RUN で再び下げる", redraw("startup", "RESET_N", "01.........0..."), "reset"),
    ]
    base, missed, used = check(), 0, set()
    for name, apply, key in muts:
        undo = apply()
        try:
            got = check()
        finally:
            undo()
        det = any(MSG[key] in r for r in got)
        used.add(key)
        missed += not det
        print(f"{'detected' if det else 'MISSED  '} {name}: {len(got)} violations")
    unused = sorted(set(MSG) - used)
    for k in unused:
        print(f"PROBLEM  no mutation expects the message {MSG[k]!r}")
    # the counts the spec quotes (audit round 22, auditor C, as fsm_spec and regmap since round 21)
    doc = os.path.join(HERE, "..", "..", "..", "..", "documentation", "gf180_digital_control_spec_r15_20261127.md")
    stale = []
    try:
        txt = open(doc, encoding="utf-8").read()
        for pat, have in ((r"`wave\.py selftest`（(\d+) 種／\d+ 文", len(muts)), (r"`wave\.py selftest`（\d+ 種／(\d+) 文", len(MSG)),
                          (r"`wave\.py selftest` の (\d+) 種も同じ形", len(muts))):
            got = [int(x) for x in re.findall(pat, txt)]
            if not got or any(g != have for g in got):
                stale.append(f"the spec quotes {got} for the self-test ({pat}), which has {have}")
    except OSError as ex:
        stale.append(f"the spec cannot be read ({ex})")
    for p_ in stale:
        print("PROBLEM  " + p_)
    for e in base:
        print(f"PROBLEM  unmutated: {e}")
    print(f"{len(muts) - missed} of {len(muts)} mutations detected by their expected messages; {len(MSG)} check "
          f"messages; unmutated sources: {len(base)} violations")
    return 0 if not missed and not unused and not base and not stale else 1


def fresh():
    """The wave_*.json equal what the source gives now, each PNG was rendered from that JSON (its SHA-256), and the
    startup and APPLY diagrams agree with fsm_spec's table (check)."""
    errs = check()
    for e in errs:
        print("  " + e)
    stale = ["(the diagrams disagree with the table)"] if errs else []
    for name, (fn, width) in DIAGRAMS.items():
        p = os.path.join(HERE, f"wave_{name}.json")
        if not os.path.exists(p) or json.load(open(p, encoding="utf-8")) != json.loads(json.dumps(fn())):
            stale.append(os.path.basename(p))
        if FS.png_source_sha(p[:-5] + ".png") != FS.source_sha(json_text(fn())):
            stale.append(os.path.basename(p[:-5] + ".png"))
    print("timing diagrams up to date" if not stale else "STALE (run wave.py): " + ", ".join(stale))
    return 1 if stale else 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "fresh":
        return fresh()
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        return selftest()
    errs = check()
    if errs:
        print("not writing: the diagrams disagree with fsm_spec's table:\n  " + "\n  ".join(errs))
        return 1
    for name, (fn, width) in DIAGRAMS.items():
        src = fn()
        with open(os.path.join(HERE, f"wave_{name}.json"), "w", encoding="utf-8") as f:
            f.write(json_text(src))
        print("wrote", os.path.relpath(render(name, src, width), FS.REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
