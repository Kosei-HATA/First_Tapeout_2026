#!/usr/bin/env python3
"""Timing diagrams of the digital control (WaveDrom), generated from fsm_spec.TIMING and regmap.py (11/19).

Writes wave_<name>.json (WaveDrom source) and wave_<name>.png (headless Google Chrome, WaveDrom 3.5.0 from jsDelivr)
next to this file:
  frame    one frame (32 MCLK) with every event of the existing frame timing and the new tick (e24)
  chop     the chopper period at 128 and 64 kHz, the tick in the middle of phase A, the CIC output time
  startup  RESET_N .. RUN (schematic, not to scale; the durations from the timers' reset values in regmap.py)
  apply    APPLY in RUN: PRE, PULSE, RECOVER, ALIGN, FILL, RUN with the FIFO emptied at the APPLY's tick (schematic;
           the durations from regmap.py)
  spi      the SPI frames at byte level: write, write with CRC, register read (burst), sample read

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/wave.py
"""
import json
import os
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
        {"name": "ADC：CMP_STROBE", "wave": levels(n, hi({0}))},
        {"name": "ADC：TH_CAPTURE（e2 で取り込み）", "wave": levels(n, hi({1}))},
        {"name": "ADC：DAC_LOAD（e3 で SEL 更新）", "wave": levels(n, hi({2}))},
        {"name": "ADC：CIC の入力", "wave": levels(n, hi({3}))},
        {"name": "ADC：DAC_CLK", "wave": levels(n, hi({4}))},
        {},
        {"name": "縁のフレーム：CHOP／CHOP_OUT", "wave": levels(n, set(range(1, n)))},
        {"name": "縁のフレーム：CHOP_BLANK（15）", "wave": levels(n, blank)},
        {"name": "出力のフレーム：CIC の出力", "wave": levels(n, hi({8}))},
        {"name": "CHOP1 の縁のフレーム：CHOP1", "wave": levels(n, {i for i, c in enumerate(pos) if i > 0 and c >= 16})},
        {},
        {"name": "新設：tick（相 A の中ほど）", "wave": levels(n, hi({tc}))},
        {"name": "新設：AFE_RST・設定の出力", "wave": "=" + "." * (up - 1) + "=" + "." * (n - up - 1),
         "data": ["旧い値", "新しい値"]},
    ]
    return {"signal": sig, "head": {"text": "1 フレーム（32 MCLK ＝ 0.977 µs）：既存の事象と新設の tick"},
            "foot": {"text": "左端は前のフレームの cycle 31。ストローブは cycle k の間 High、出力はその終わりの縁（e(k+1)）で変わる。tick は cycle 24、出力は e25"},
            "config": {"hscale": 1}}


def chop():
    # 16 frames, 2 slots (16 MCLK) per frame
    n = 32
    slot = lambda f, c: 2 * f + c // 16
    r128, r64 = FS.TIMING["rates"]["128k"], FS.TIMING["rates"]["64k"]
    tc = FS.TIMING["tick_cycle"]
    t128 = {slot(f, tc) for f in range(16) if f % r128["period_frames"] == r128["tick_frame"]}
    t64 = {slot(f, tc) for f in range(16) if f % r64["period_frames"] == r64["tick_frame"]}
    out = {slot(15, 8)}
    c128 = {i for i in range(n) if (i // 2) % 8 < 4}
    c64 = {i for i in range(n) if (i // 2) % 16 < 8}
    sig = [
        {"name": "フレーム", "wave": "=." * 16, "data": [str(f) for f in range(16)]},
        {},
        {"name": "128 kHz：CHOP（1 ＝ 相 A）", "wave": levels(n, c128)},
        {"name": "128 kHz：tick", "wave": levels(n, t128)},
        {},
        {"name": "64 kHz：CHOP（1 ＝ 相 A）", "wave": levels(n, c64)},
        {"name": "64 kHz：tick", "wave": levels(n, t64)},
        {},
        {"name": "CIC の出力", "wave": levels(n, out)},
    ]
    return {"signal": sig,
            "head": {"text": "チョッパの周期と tick：相 A の中ほど（128 kHz で縁から 56 MCLK、64 kHz で 120 MCLK）に 1 周期 1 回"},
            "foot": {"text": "CIC の出力は 1,024 フレーム目（フレーム番号 ≡ 15 mod 16）の cycle 8。tick とは同じサイクルにならない"},
            "config": {"hscale": 1}}


def timer_text(name):
    """The timer's reset value as a duration: T_WARM, T_ELEC in ms; T_REC, T_PRE, T_RST in 8-frame units."""
    v = next(f for *_, f in RM.all_fields() if f["name"] == name)["reset"]
    if name in ("T_WARM", "T_ELEC"):
        return f"{name} {v} ms"
    us = v * 8 * FS.FRAME / FS.MCLK * 1e6
    return f"{name} {us:.4g} µs" if us < 1000 else f"{name} {us / 1000:.4g} ms"


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
        {"name": "格納（DRDY_N のパルス）", "wave": "10..........1010"},
    ]
    return {"signal": sig, "head": {"text": "APPLY（パルス付きの一括反映、模式図。T_ELEC ＞ 0 なら RECOVER のあとに WAIT_E）"},
            "foot": {"text": "再整定の間の出力は格納しない（SEQ は 1 ms ごとに数え続け、欠けた数が分かる）"},
            "config": {"hscale": 2}}


def spi():
    def frame_(name, mosi, miso):
        k = len(mosi)
        return [name,
                {"name": "CS_N", "wave": "1" + "0" + "." * (2 * k - 1) + "1"},
                {"name": "MOSI", "wave": "x" + "=." * k + "x", "data": mosi},
                {"name": "MISO", "wave": "z" + "=." * k + "z", "data": miso}]
    sig = [
        frame_("書き込み", ["W＋adr", "データ"], ["STATUS", "0x00"]),
        {},
        frame_("書き込み（CRC）", ["W＋adr", "データ", "CRC"], ["STATUS", "0x00", "0x00"]),
        {},
        frame_("読み出し（連続）", ["R＋adr", "0x00", "0x00"], ["STATUS", "[adr]", "[adr＋1]"]),
        {},
        frame_("読み出し（CRC）", ["R＋adr", "0x00", "0x00"], ["STATUS", "[adr]", "CRC"]),
        {},
        frame_("サンプル", ["R＋0x40", "0x00", "0x00", "0x00", "0x00", "0x00", "0x00", "0x00"],
               ["STATUS", "状態", "SEQ 上", "SEQ 下", "DATA 上", "DATA 中", "DATA 下", "CRC"]),
    ]
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
                "<body onload='WaveDrom.ProcessAll()'><script type='WaveDrom'>"
                + json.dumps(src, ensure_ascii=False) + "</script></body></html>")
    out = os.path.join(HERE, f"wave_{name}.png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={width},900", "--virtual-time-budget=10000", f"--screenshot={out}",
                    "file://" + os.path.abspath(page)], check=True, capture_output=True)
    try:                                            # trim the white margin
        from PIL import Image, ImageChops
        im = Image.open(out).convert("RGB")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        box = ImageChops.difference(im, bg).getbbox()
        if box:
            pad = 16
            im.crop((max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width),
                     min(box[3] + pad, im.height))).save(out)
    except ImportError:
        pass
    return out


def fresh():
    """The wave_*.json equal what the source gives now (the PNGs are rendered from them)."""
    stale = []
    for name, (fn, width) in DIAGRAMS.items():
        p = os.path.join(HERE, f"wave_{name}.json")
        if not os.path.exists(p) or json.load(open(p, encoding="utf-8")) != json.loads(json.dumps(fn())):
            stale.append(os.path.basename(p))
    print("timing diagrams up to date" if not stale else "STALE (run wave.py): " + ", ".join(stale))
    return 1 if stale else 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "fresh":
        return fresh()
    for name, (fn, width) in DIAGRAMS.items():
        src = fn()
        with open(os.path.join(HERE, f"wave_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(src, f, ensure_ascii=False, indent=1)
        print("wrote", os.path.relpath(render(name, src, width), FS.REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
