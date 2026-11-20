#!/usr/bin/env python3
"""The register map, SPI byte formats and command codes of the new digital control, as one machine-readable source
(11/19, detailed specification for requirements r3; decisions D-1..D-8 as recommended).

From this file are generated: the register tables of documentation/gf180_digital_control_spec_20261119.md and the
SystemVerilog package eeg_regs_pkg.sv (addresses, field positions, reset values, legal ranges, codes) that the RTL
will use. `check` proves the properties listed in CHECKS, including the cross-checks with fsm_spec.py (timers against
the analog minimums, STATE codes, the conditions cfg_ok and nr_ok, every analog control output covered).

Usage:
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/regmap.py check
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/regmap.py gen      (check, then write the generated files)
  gf180/tools/venv310/bin/python gf180/tapeout/rtl/spec/regmap.py selftest (each listed register-map error must be
                                                                          detected)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
DOC = os.path.join(REPO, "documentation", "gf180_digital_control_spec_20261119.md")
PKG = os.path.join(HERE, "eeg_regs_pkg.sv")
DEFS = os.path.join(HERE, "eeg_regs_defs.svh")      # the same constants as localparams, `include'd inside a module
sys.path.insert(0, HERE)
import fsm_spec as FS  # noqa: E402

TICK_UNIT_S = 256 / FS.MCLK                     # 7.8125 us: unit of T_PRE, T_RST, T_REC (one 128 kHz chopper period)
# the overload rule (FLG-04; `check` compares it with the requirement's row and the spec's section 5, audit round 7)
OVL_RULE = dict(window=32, threshold=4, codes=(0, 31))
REQ_DOC = os.path.join(REPO, "documentation", "gf180_digital_control_requirements_20261119.md")
# the full-scale streams of the CT loop model (gitignored build outputs, 10/24): their SHA-256, so that a changed or
# regenerated stream cannot pass unnoticed (audit round 7)
FULLSCALE_SHA256 = {"s4": "fbc092845489d9b7df1bb48cd158a6b95006cb59a0e7e30c2c7510dd78632f11",
                    "s20": "2f06a6497bed6c65cb10f530ac4811cf6e2636c152961b8a548dfcea96b388a8"}

# update classes of a field
#   apply  analog-affecting: written to a shadow, copied to the active copy (and the pins) by START / APPLY / APPLY_NR
#   seq    driven by the sequencer only
#   imm    takes effect at once; no analog effect (or latched at a timer start)
#   ro     read only        w1c  write 1 to clear        cmd  write only, executed at the next tick


def F(name, msb, lsb, reset, legal, cls, desc, pin=None):
    return dict(name=name, msb=msb, lsb=lsb, reset=reset, legal=legal, cls=cls, desc=desc, pin=pin)


def rng(a, b):
    return list(range(a, b + 1))


REGS = [
    # addr, name, access, lock (test key), fields, description
    (0x00, "ID", "RO", False, [F("ID", 7, 0, 0xE6, [0xE6], "ro", "チップの識別（0xE6）")], "識別"),
    (0x01, "VERSION", "RO", False, [F("VERSION", 7, 0, 0x10, [0x10], "ro", "制御の版（0x10 ＝ r3 の SPI とシーケンサ）")], "版"),
    (0x02, "CAPS", "RO", False, [F("FIFO_DEPTH", 3, 0, 8, [4, 8], "ro", "FIFO の深さ（合成で決める。4 または 8）"),
                                 F("CRC", 4, 4, 1, [1], "ro", "CRC を持つ（1）")], "機能"),
    (0x03, "STATUS", "RO", False, [F("MARK1", 7, 7, 1, [1], "ro", "固定の 1（MISO の無応答と区別）"),
                                   F("MARK0", 6, 6, 0, [0], "ro", "固定の 0"),
                                   F("ALERT", 5, 5, 1, [0, 1], "ro", "マスクしないエラーのフラグがある（リセット直後は RESET_FLAG で 1）"),
                                   F("CMD_PENDING", 4, 4, 0, [0, 1], "ro", "命令が tick での処理を待っている"),
                                   F("READY", 3, 3, 0, [0, 1], "ro", "状態が RUN"),
                                   F("DATA", 2, 2, 0, [0, 1], "ro", "FIFO が空でない"),
                                   F("OVL_NOW", 1, 1, 0, [0, 1], "ro", f"過負荷を検出中（直近 {OVL_RULE['window']} フレームに両端の符号が {OVL_RULE['threshold']} 個以上）"),
                                   F("AFE_RST", 0, 0, 1, [0, 1], "ro", "AFE_RST の出力の現在値")],
     "状態（フレームの先頭バイトで MISO から返す値と同じ）"),
    (0x04, "STATE", "RO", False, [F("STATE", 3, 0, 0, [x[1] for x in FS.SEQ_STATES if x[1] is not None], "ro",
                                    "シーケンサの状態（0 IDLE、1 WARMUP、2 RECOVER、3 WAIT_E、4 ALIGN、5 FILL、6 RUN、7 PRE、8 PULSE）")],
     "シーケンサの状態"),
    (0x05, "FIFO_LEVEL", "RO", False, [F("LEVEL", 3, 0, 0, rng(0, 8), "ro", "FIFO のサンプルの数")], "FIFO の占有数"),
    (0x06, "ERR", "W1C", False, [F("CMD_ERR", 7, 7, 0, [0, 1], "w1c", "未定義の命令コード、または TEST_KEY への 0x3C と 0x00 以外の値"),
                                 F("STATE_ERR", 6, 6, 0, [0, 1], "w1c", "その状態で受け付けない命令、未処理の命令への上書き、または未処理の命令がある間のシャドウとタイマへの書き込み（SOFT_RESET は常に受け付ける）、シーケンサの不正な状態の値（直ちに IDLE へ。NFR-05）"),
                                 F("CFG_ERR", 5, 5, 0, [0, 1], "w1c", "整合しない設定（cfg_ok でない）での START、APPLY、APPLY_NR、または AFE の動作中の nr_ok でない APPLY_NR"),
                                 F("RANGE_ERR", 4, 4, 0, [0, 1], "w1c", "範囲外の値の書き込み（書かない）"),
                                 F("ADDR_ERR", 3, 3, 0, [0, 1], "w1c", "未定義のアドレス、読み出し専用への書き込み、鍵なしの試験のレジスタへの書き込み"),
                                 F("CRC_ERR", 2, 2, 0, [0, 1], "w1c", "書き込みの CRC の不一致（書かない）"),
                                 F("FRAME_ERR", 1, 1, 0, [0, 1], "w1c", "バイトの途中の CS_N、不完全または過長な書き込み、完了したフレーム（書き込み、CRC 付きの読み出し、8 バイトのサンプル）のあとのビット、CRC 有効時の CRC のバイトのない読み出し（先頭バイトだけのフレームを除く）と 8 バイトでないサンプル、SPI の状態機械の不正な状態の値（何も確定しない。NFR-05）"),
                                 F("RESET_FLAG", 0, 0, 1, [0, 1], "w1c", "リセットが起きた（既定値 1）")], "エラー（W1C）"),
    (0x07, "DFLAG", "W1C", False, [F("OVL", 1, 1, 0, [0, 1], "w1c", "FILL または RUN の間に、過負荷の検出の成り立つ両端の符号があった（検出の窓の尾だけでは立たない）"),
                                   F("OVERRUN", 0, 0, 0, [0, 1], "w1c", "FIFO が満杯でサンプルを捨てた")], "データのフラグ（W1C）"),
    (0x08, "ALERT_MASK", "RW", False, [F("ALERT_MASK", 7, 0, 0xFF, rng(0, 255), "imm", "ERR のビットごとに ALERT に含める（1）")], "ALERT のマスク"),
    (0x09, "ALERT_MASK_D", "RW", False, [F("ALERT_MASK_D", 1, 0, 0x3, rng(0, 3), "imm", "DFLAG のビットごとに ALERT に含める（1）")], "ALERT のマスク（データ）"),
    (0x0A, "ODR_H", "RO", False, [F("ODR_H", 7, 0, 0x03, [0x03], "ro", "出力データレート 1000 SPS の上位")], "出力データレート"),
    (0x0B, "ODR_L", "RO", False, [F("ODR_L", 7, 0, 0xE8, [0xE8], "ro", "同下位")], "出力データレート"),
    (0x0C, "FORMAT", "RO", False, [F("QBITS", 3, 0, 5, [5], "ro", "量子化器のビット数")], "形式"),
    (0x10, "COMMAND", "WO", False, [F("CMD", 7, 0, 0, None, "cmd", "命令コード（第 2.3 節）。次の tick で処理")], "命令"),
    (0x11, "TEST_KEY", "WO", False, [F("KEY", 7, 0, 0, None, "imm", "0x3C で試験のレジスタを解錠、0x00 で施錠。その他の値は施錠し、CMD_ERR（書き込みの確定の時点で効く）")], "試験の鍵"),
    # analog configuration (shadow; the active copies are read at addr + 0x10)
    (0x20, "OFF_M_H", "RW", False, [F("M_H", 1, 0, 0, rng(0, 3), "apply", "オフセット DAC の大きさ M[9:8]", "OFM[9:8]")], "オフセット DAC（上位）"),
    (0x21, "OFF_M_L", "RW", False, [F("M_L", 7, 0, 0, rng(0, 255), "apply", "M[7:0]", "OFM[7:0]")], "オフセット DAC（下位）"),
    (0x22, "OFF_CTRL", "RW", False, [F("SIGN", 4, 4, 0, [0, 1], "apply", "符号 S（打ち消す量は (1 − 2 S) × M × 0.311 mV）", "OFS"),
                                     F("RANGE", 2, 0, 0, rng(0, 4), "apply", "範囲（0 切、1〜4 で ±39／79／159／318 mV。5〜7 は RANGE_ERR）", "OFEN[3:0]")],
     "オフセット DAC（符号と範囲）"),
    (0x23, "AFE_IBIAS", "RW", False, [F("AFE_IBIAS", 1, 0, 3, rng(0, 3), "apply", "AFE のバイアス電流（通常の動作は 3。0〜2 は評価用で性能を保証しない。書き込みは拒否しない）", "AFE_IBIAS[1:0]")], "AFE のバイアス"),
    (0x24, "CPF_TRIM", "RW", False, [F("CPF_TRIM", 3, 0, 8, rng(0, 15), "apply", "入力インピーダンスの補償容量のトリム", "CPF_TRIM[3:0]")], "補償容量のトリム"),
    (0x25, "BOOST_TRIM", "RW", False, [F("BTRIM_N", 5, 4, 0, rng(0, 3), "apply", "NMOS カスコードのブースタ（00 ＝ 2 単位 … 11 ＝ 8 単位。既定 2）", "BTRIM_N[1:0]"),
                                       F("BTRIM_P", 1, 0, 1, rng(0, 3), "apply", "PMOS カスコードのブースタ（既定 01 ＝ 4 単位）", "BTRIM_P[1:0]")],
     "ブースタのトリム（typical 4/2）"),
    (0x26, "CHOP_CFG", "RW", False, [F("CHOP_FAST", 0, 0, 1, [0, 1], "apply", "AFE のチョッパ（1 ＝ 128 kHz、0 ＝ 64 kHz）", "CHOP／CHOP_OUT／CHOP_BLANK の速さ")], "AFE のチョッパ"),
    (0x27, "ADC_CFG", "RW", False, [F("DWA_EN", 4, 4, 1, [0, 1], "apply", "DAC1／DAC2 の DWA", "DWA_EN"),
                                    F("CHOP1_RATE", 2, 0, 3, rng(0, 5), "apply", "OTA1 のチョッパ（0 切、1〜5 で 1／2／4／8／16 kHz。6、7 は RANGE_ERR）", "CHOP1")],
     "ADC の設定"),
    (0x28, "BLANK", "RW", False, [F("BLANK_LEN", 3, 0, 7, rng(1, 15), "apply", "出力チョッパのブランキング（MCLK。0 は RANGE_ERR。範囲 1 以上では 15 として出す）", "CHOP_BLANK の幅")],
     "ブランキング"),
    # data window
    (0x40, "SAMPLE", "RO", False, [F("SAMPLE", 7, 0, 0, None, "ro", "サンプルの窓（先頭のアドレスとしてのみ。先頭バイトのあとの 7 バイト、フレームは 8 バイト。第 3.2 節、第 3.4 節）")], "サンプル"),
    # timers and interface (immediate; timers are latched when the timer starts)
    (0x50, "T_WARM", "RW", False, [F("T_WARM", 7, 0, 5, rng(5, 255), "imm", "WARMUP（ms）")], "タイマ"),
    (0x51, "T_ELEC", "RW", False, [F("T_ELEC", 7, 0, 0, rng(0, 255), "imm", "WAIT_E（ms。0 で WAIT_E を通らない）")], "タイマ"),
    (0x52, "T_REC", "RW", False, [F("T_REC", 7, 0, 32, rng(29, 255), "imm", "RECOVER（7.8125 µs 単位。既定 32 ＝ 250 µs）")], "タイマ"),
    (0x53, "T_PRE", "RW", False, [F("T_PRE", 7, 0, 3, rng(3, 255), "imm", "PRE（7.8125 µs 単位。既定 3 ＝ 23.4 µs）")], "タイマ"),
    (0x54, "T_RST", "RW", False, [F("T_RST", 7, 0, 13, rng(13, 255), "imm", "PULSE（7.8125 µs 単位。既定 13 ＝ 101.6 µs）")], "タイマ"),
    (0x55, "IF_CFG", "RW", False, [F("DRDY_MODE", 1, 1, 0, [0, 1], "imm", "DRDY_N（0 ＝ FIFO が空でない間 Low のレベル、1 ＝ 格納ごとに 128 MCLK（4 フレーム、3.906 µs）の Low のパルス。満杯で捨てた出力ではパルスなし）"),
                                   F("CRC_EN", 0, 0, 0, [0, 1], "imm", "書き込みと読み出しの CRC")], "インターフェース"),
    # test (locked by TEST_KEY)
    (0x60, "TEST_MUX", "RW", True, [F("ATP_EN", 4, 4, 0, [0, 1], "apply", "試験用マルチプレクサを ATP へ", "TEST_CFG[4]"),
                                    F("ATP_SEL", 3, 0, 0, rng(0, 15), "apply", "節点の選択（0 AVSS … 15 ADC O2N）", "TEST_CFG[3:0]")], "試験用マルチプレクサ"),
    (0x61, "TEST_CTRL", "RW", True, [F("CHOP_STOP", 1, 1, 0, [0, 1], "apply", "1 で CHOP_EN ＝ 0（入力と出力のチョッパを相 A に固定し、AFE はチョップされずに動く。CHOP、CHOP_OUT、CHOP_BLANK の端子は動き続ける：第 4.1 節、ANA-03）", "CHOP_EN"),
                                     F("ADC_ZERO", 0, 0, 0, [0, 1], "apply", "ADC の入力の短絡と CHOP_BLANK の保持", "TEST_CFG[5]")], "試験の制御"),
    (0x62, "DEBUG", "RW", True, [F("DBG_SEL", 2, 1, 0, rng(0, 3), "imm", "RAW のパッドに時刻の信号（RAW_EN ＝ 0 のとき）", "TEST_CFG[7:6]"),
                                 F("RAW_EN", 0, 0, 0, [0, 1], "imm", "生の符号の出力", "RAW_DATA／RAW_CLK")], "デバッグの出力"),
]
SHADOW_MIRROR = 0x10                            # active copy of a shadowed register at addr + 0x10 (read only)

COMMANDS = {"START": 0x11, "STOP": 0x22, "APPLY": 0x33, "APPLY_NR": 0x44, "FLUSH": 0x55, "SOFT_RESET": 0xA5}
TEST_KEY = 0x3C

# every control the analog side receives from the digital block (gf180_digital_control_requirements_20261119.md 4.10)
ANALOG_CONTROLS = ["AFE_RST", "CHOP_EN", "OFM[9:8]", "OFM[7:0]", "OFS", "OFEN[3:0]", "CPF_TRIM[3:0]", "AFE_IBIAS[1:0]",
                   "BTRIM_P[1:0]", "BTRIM_N[1:0]", "CHOP／CHOP_OUT／CHOP_BLANK の速さ", "CHOP_BLANK の幅", "CHOP1",
                   "DWA_EN", "TEST_CFG[4]", "TEST_CFG[3:0]", "TEST_CFG[5]"]
SEQ_DRIVEN = {"AFE_RST"}
DIGITAL_ONLY = {"TEST_CFG[7:6]", "RAW_DATA／RAW_CLK"}       # pads and debug: no analog effect (11/16: +0.64 nV)

SAMPLE_STATUS = [("VALID", 7, "格納したサンプル（空の FIFO の読み出しでは 0）"), ("OVERRUN", 6, "格納の時点で DFLAG.OVERRUN が立っていた"),
                 ("OVL", 5, "この出力の窓（sinc³ の 3 ms：この出力と直前の 2 個の出力の間隔）のいずれかに、過負荷の検出の成り立つ両端の符号があった"),
                 ("CHANGED", 4, "APPLY_NR の反映をまたぐ窓と電極の整定（反映の直後の 3 ＋ T_ELEC 個。残りのほうが長ければその長さ。RUN を出ると残りは取り消す）"),
                 ("ERR", 3, "格納の時点で ALERT が立っていた"), ("0", 2, "0"), ("0", 1, "0"), ("0", 0, "0")]
RANGE_MAX_M = {0: 1023, 1: 127, 2: 255, 3: 511, 4: 1023}       # range 0: the DAC is off and OFM/OFS are driven 0
BLANK_WITH_DAC = 15                    # CHOP_BLANK's length (MCLK) with the offset DAC on (range >= 1): its settling


def ofen_of_range(r):
    """OFEN[3:0]: range r turns on the DAC's groups G0 .. G(r-1) (a thermometer); range 0 turns all off."""
    return (1 << r) - 1


# every analog control (ANALOG_CONTROLS) and the key of pins_from_active that gives it (AFE_RST: the sequencer)
PIN_OF_CONTROL = {"CHOP_EN": "CHOP_EN", "OFM[9:8]": "OFM", "OFM[7:0]": "OFM", "OFS": "OFS", "OFEN[3:0]": "OFEN",
                  "CPF_TRIM[3:0]": "CPF_TRIM", "AFE_IBIAS[1:0]": "AFE_IBIAS", "BTRIM_P[1:0]": "BTRIM_P",
                  "BTRIM_N[1:0]": "BTRIM_N", "CHOP／CHOP_OUT／CHOP_BLANK の速さ": "CHOP_HALF",
                  "CHOP_BLANK の幅": "BLANK_W", "CHOP1": "CHOP1_HALF", "DWA_EN": "DWA_EN", "TEST_CFG[4]": "TEST_CFG",
                  "TEST_CFG[3:0]": "TEST_CFG", "TEST_CFG[5]": "TEST_CFG"}


def pins_from_active(ac):
    """The analog control pins for the active settings ac (field name -> value; DBG_SEL from the DEBUG register,
    which takes effect at once). OFM / OFS are driven 0 with the DAC off; OFEN is the range's thermometer; CHOP_BLANK
    is high for its length + 1 MCLK around each output-chopper edge (eeg_clkgen), BLANK_WITH_DAC with the DAC on, and
    held high by ADC_ZERO; the chopper's and CHOP1's half periods in MCLK (CHOP1 0 = off)."""
    dac = ac["RANGE"] != 0
    m = (ac["M_H"] << 8) | ac["M_L"]
    c1 = ac["CHOP1_RATE"]
    return dict(OFM=m if dac else 0, OFS=ac["SIGN"] if dac else 0, OFEN=ofen_of_range(ac["RANGE"]),
                AFE_IBIAS=ac["AFE_IBIAS"], CPF_TRIM=ac["CPF_TRIM"], BTRIM_P=ac["BTRIM_P"], BTRIM_N=ac["BTRIM_N"],
                DWA_EN=ac["DWA_EN"], CHOP_EN=1 - ac["CHOP_STOP"],
                TEST_CFG=(ac["DBG_SEL"] << 6) | (ac["ADC_ZERO"] << 5) | (ac["ATP_EN"] << 4) | ac["ATP_SEL"],
                BLANK_W=(BLANK_WITH_DAC if dac else ac["BLANK_LEN"]) + 1, BLANK_HELD=ac["ADC_ZERO"],
                CHOP_HALF=128 if ac["CHOP_FAST"] else 256,
                CHOP1_HALF=0 if c1 == 0 else FS.TIMING["chop1_periods_frames"][c1 - 1] * FS.FRAME // 2)


def guarded_addrs():
    """Writes refused (STATE_ERR) while a command is pending: the registers with fields applied at the tick (the
    shadows) and the timers (loaded at the tick), so that the command uses the values present when it was written."""
    return sorted({a for a, n, acc, lock, fields, _ in REGS
                   if any(f["cls"] == "apply" for f in fields) or n in ("T_WARM", "T_ELEC", "T_REC", "T_PRE", "T_RST")})


def cfg_ok(sh):
    """START / APPLY / APPLY_NR: the shadow offset-DAC magnitude fits the shadow range."""
    return sh["M"] <= RANGE_MAX_M[sh["RANGE"]]


def nr_ok(sh, ac):
    """APPLY_NR while the AFE runs: only the signed offset-DAC value moves, by one step, in the same range."""
    sv = lambda r: (1 - 2 * r["SIGN"]) * r["M"]
    others = [k for k in sh if k not in ("M", "SIGN")]
    return sh["RANGE"] == ac["RANGE"] and abs(sv(sh) - sv(ac)) <= 1 and all(sh[k] == ac[k] for k in others)


CHECKS = [
    "アドレスの重なりがない。アクティブの写しのアドレス（＋0x10）が他のレジスタと重ならない",
    "各レジスタのフィールドは 8 ビットに収まり、重ならない（未使用のビットが 0 を返すことは、レジスタ表から生成した試験 tb_top_r14 で確かめる）",
    "既定値はフィールドの幅に収まり、合法な値。推奨の動作値（AFE_IBIAS 3、BOOST_TRIM 4/2、BLANK 7、CHOP_FAST 1、CHOP1 4 kHz、DWA_EN 1）",
    "アナログ側が受ける制御の全て（17 項目）が、ちょうど 1 つのフィールド（apply）かシーケンサ（AFE_RST）から出る。アナログに効く設定に、即時に効くもの（imm）はない",
    "端子の規則（pins_from_active）：OFEN は範囲 r で DAC の群 G0〜G(r−1) を入れる温度計の符号（RANGE_MAX_M の群の構成と一致）、範囲 0 では OFM と OFS を 0、DAC を使うときの CHOP_BLANK は 15 MCLK（フレームの最長のブランキング）。アナログの全ての制御が、この規則のいずれかの端子に対応する。RTL はこの範囲の表と OFEN の表を生成した eeg_regs_defs.svh から使い、tb_top_r14 は同じ規則から生成した端子の試験（build/pin_tests.svh）で端子を確かめる",
    "タイマの最小値と既定値は、tick の格子に切り上げても（フレームの整数で計算）アナログの最小値（fsm_spec.TIMING）以上。タイマの最大値（255 × 単位）は TIMING の最大と一致",
    "未処理の命令がある間に書き込みを止めるレジスタ（GUARDED）は、一括反映のフィールドを持つレジスタとタイマのレジスタに一致",
    "STATE の値は fsm_spec のシーケンサの状態のコードと一致する",
    "STATUS は固定のビット（bit 7 ＝ 1、bit 6 ＝ 0）を持ち、0x00 と 0xFF にならない",
    "命令コードと試験の鍵は互いに、また 0x00、0xFF と 2 ビット以上異なる（1 ビットの誤りで別の命令にならない）",
    "範囲の上限の表を、DAC の群（G0 は M0〜M6、G1〜G3 は M7〜M9）と範囲の電圧（±39／79／159／318 mV、0.311 mV／段）から独立に確かめる",
    "cfg_ok と nr_ok：全ての範囲の上限で境界の値を確かめる（M が上限なら可、上限＋1 なら不可。±1 段は可、±2 段と範囲の変更と他の設定の変更は不可）",
    "過負荷の規則は、フルスケールの行動モデルのコード列（s4、s20）で 1 回も成立しない（誤検出なし）",
]


def all_fields():
    for a, n, acc, lock, fields, _ in REGS:
        for f in fields:
            yield a, n, acc, lock, f


def check(verbose=True):
    errs, notes = [], []
    addrs = {}
    for a, n, acc, lock, fields, _ in REGS:
        if a in addrs:
            errs.append(f"address 0x{a:02X} used by two registers: {addrs[a]} and {n}")
        addrs[a] = n
    for a, n, acc, lock, fields, _ in REGS:
        if any(f["cls"] == "apply" for f in fields):
            m = a + SHADOW_MIRROR
            if m in addrs:
                errs.append(f"{n}: the active copy 0x{m:02X} collides with {addrs[m]}")
    for a, n, acc, lock, fields, _ in REGS:
        used = 0
        for f in fields:
            if not 0 <= f["lsb"] <= f["msb"] <= 7:
                errs.append(f"{n}.{f['name']}: bits {f['msb']}:{f['lsb']} outside the byte")
            mask = ((1 << (f["msb"] - f["lsb"] + 1)) - 1) << f["lsb"]
            if used & mask:
                errs.append(f"{n}.{f['name']}: overlaps another field")
            used |= mask
            width = f["msb"] - f["lsb"] + 1
            if f["reset"] >= 1 << width:
                errs.append(f"{n}.{f['name']}: reset value {f['reset']} wider than the field ({width} bits)")
            if f["legal"] is not None and f["reset"] not in f["legal"]:
                errs.append(f"{n}.{f['name']}: reset value {f['reset']} is not among the legal values")
            if f["legal"] is not None and any(v >= 1 << width for v in f["legal"]):
                errs.append(f"{n}.{f['name']}: a legal value does not fit the field")
    rec = {f["name"]: f["reset"] for *_, f in all_fields()}
    for k, v in dict(AFE_IBIAS=3, BTRIM_P=1, BTRIM_N=0, BLANK_LEN=7, CHOP_FAST=1, CHOP1_RATE=3, DWA_EN=1).items():
        if rec.get(k) != v:
            errs.append(f"reset value of {k} is {rec.get(k)}, the recommended operating value is {v}")
    # analog controls: exactly one source each, never immediate
    src = {}
    for a, n, acc, lock, f in all_fields():
        if f["pin"]:
            src.setdefault(f["pin"], []).append((n, f["name"], f["cls"]))
    for c in ANALOG_CONTROLS:
        s_ = src.get(c, [])
        if c in SEQ_DRIVEN:
            if s_:
                errs.append(f"{c}: driven by the sequencer but also by {s_}")
            continue
        if len(s_) != 1:
            errs.append(f"{c}: {len(s_)} sources {s_} (exactly one required)")
        elif s_[0][2] != "apply":
            errs.append(f"{c}: class {s_[0][2]} (analog controls change only through START / APPLY / APPLY_NR)")
    for pin, s_ in src.items():
        if pin not in ANALOG_CONTROLS and pin not in DIGITAL_ONLY:
            errs.append(f"{pin}: a pin that is in neither list of controls")
    # timers against the analog minimums (fsm_spec.TIMING) on both tick grids
    unit = {"T_REC": 8, "T_PRE": 8, "T_RST": 8, "T_WARM": 1024}                   # frames per register step
    frame_s = FS.FRAME / FS.MCLK
    for tn, u in unit.items():
        f = next(f for *_, f in all_fields() if f["name"] == tn)
        mn, df, mx = FS.TIMING["timers"][tn]
        for label, code in (("minimum", min(f["legal"])), ("default", f["reset"])):
            for rate, r in FS.TIMING["rates"].items():
                per = r["period_frames"]                                          # the expiry waits for a tick
                frames = -(-(code * u) // per) * per                              # integers: exact
                if frames * frame_s < mn - 1e-12:
                    errs.append(f"{tn} {label} code {code}: {frames * frame_s * 1e6:.2f} us at {rate}, below the analog "
                                f"minimum of {mn * 1e6:g} us")
            notes.append(f"{tn} {label}: code {code} = {code * u * frame_s * 1e6:.4f} us")
        if abs(max(f["legal"]) * u * frame_s - mx) > 1e-12:
            errs.append(f"{tn}: the register reaches {max(f['legal']) * u * frame_s * 1e3:.4f} ms, TIMING says {mx * 1e3:.4f} ms")
    g = guarded_addrs()
    want = sorted({a for a, n, acc, lock, fields, _ in REGS if any(f["cls"] == "apply" for f in fields)} |
                  {a for a, n, *_ in REGS if n.startswith("T_")})
    if g != want or not g:
        errs.append(f"guarded addresses {g}, expected {want}")
    # STATE codes
    st = next(f for *_, f in all_fields() if f["name"] == "STATE")
    codes = sorted(x[1] for x in FS.SEQ_STATES if x[1] is not None)
    if sorted(st["legal"]) != codes or max(codes) >= 1 << (st["msb"] - st["lsb"] + 1):
        errs.append("STATE field does not match the sequencer's state codes")
    # STATUS marker
    stat = next(r for r in REGS if r[1] == "STATUS")[4]
    m1 = next(f for f in stat if f["name"] == "MARK1")
    m0 = next(f for f in stat if f["name"] == "MARK0")
    if not (m1["legal"] == [1] and m0["legal"] == [0] and m1["msb"] != m0["msb"]):
        errs.append("STATUS has no fixed 1 and 0 bits (cannot tell it from a dead MISO)")
    # command codes: Hamming distance >= 2 between codes and from 0x00 / 0xFF
    vals = list(COMMANDS.items()) + [("TEST_KEY", TEST_KEY), ("idle 0x00", 0x00), ("idle 0xFF", 0xFF)]
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            d = bin(vals[i][1] ^ vals[j][1]).count("1")
            if d < 2:
                errs.append(f"{vals[i][0]} 0x{vals[i][1]:02X} and {vals[j][0]} 0x{vals[j][1]:02X} differ in {d} bit "
                            f"(codes must differ in 2 bits or more)")
    # the range table against the DAC's groups (independent of RANGE_MAX_M): range r uses G0 (M0..M6) .. G(r-1)
    # (M7, M8, M9), so M fits 6 + r bits; and the documented ranges +-39 / 79 / 159 / 318 mV at 0.311 mV per step
    for r_, mv in {1: 39, 2: 79, 3: 159, 4: 318}.items():
        if RANGE_MAX_M.get(r_) != 2 ** (6 + r_) - 1 or abs(RANGE_MAX_M[r_] * 0.311 - mv) > 1.0:
            errs.append(f"range {r_}: largest M {RANGE_MAX_M.get(r_)}, the DAC groups give {2 ** (6 + r_) - 1} (+-{mv} mV)")
    # the pins of the active settings: OFEN switches on exactly the groups G0 .. G(r-1) that RANGE_MAX_M assumes;
    # every analog control maps to a pin of pins_from_active; CHOP_BLANK's length with the DAC on is the longest
    # blanking the frame allows (fsm_spec.TIMING blank_max)
    for r_ in range(5):
        if ofen_of_range(r_) != sum(1 << k for k in range(r_)) or (r_ and RANGE_MAX_M[r_] != 2 ** (6 + r_) - 1):
            errs.append(f"range {r_}: OFEN {ofen_of_range(r_):04b} does not switch on the groups G0..G{r_ - 1}")
    if set(PIN_OF_CONTROL) != set(ANALOG_CONTROLS) - SEQ_DRIVEN:
        errs.append("PIN_OF_CONTROL does not list exactly the analog controls")
    probe = pins_from_active(dict(M_H=0, M_L=0, SIGN=0, RANGE=0, AFE_IBIAS=3, CPF_TRIM=8, BTRIM_P=1, BTRIM_N=0,
                                  CHOP_FAST=1, CHOP1_RATE=3, DWA_EN=1, BLANK_LEN=7, ATP_EN=0, ATP_SEL=0, CHOP_STOP=0,
                                  ADC_ZERO=0, DBG_SEL=0))
    if set(PIN_OF_CONTROL.values()) - set(probe):
        errs.append("pins_from_active lacks " + ", ".join(sorted(set(PIN_OF_CONTROL.values()) - set(probe))))
    if BLANK_WITH_DAC != FS.TIMING["blank_max"]:
        errs.append(f"BLANK_WITH_DAC {BLANK_WITH_DAC} is not the frame's longest blanking {FS.TIMING['blank_max']}")
    # audit round 7: range 0 (the DAC off, OFM / OFS driven 0) accepts every M; pins_from_active against an
    # independent derivation from the statements of the spec (2.2, 4.1) over a grid of active settings
    m_bits = sum(f["msb"] - f["lsb"] + 1 for *_, f in all_fields() if f["name"] in ("M_H", "M_L"))
    if RANGE_MAX_M.get(0) != 2 ** m_bits - 1:
        errs.append(f"range 0: largest M {RANGE_MAX_M.get(0)}; the DAC is off, so every M (0..{2 ** m_bits - 1}) is accepted")
    import random
    rnd_ = random.Random(20261120)
    legal = {f["name"]: f["legal"] for *_, f in all_fields()}
    for k_ in range(6000):                             # each field drawn on its own (audit round 8)
        ac = {n_: rnd_.choice(legal[n_]) for n_ in ("SIGN", "RANGE", "AFE_IBIAS", "CPF_TRIM", "BTRIM_P", "BTRIM_N",
                                                    "CHOP_FAST", "CHOP1_RATE", "DWA_EN", "BLANK_LEN", "ATP_EN",
                                                    "ATP_SEL", "CHOP_STOP", "ADC_ZERO", "DBG_SEL")}
        mm = rnd_.choice((0, 1, 127, 128, 255, 256, 511, 512, 1023, rnd_.randrange(1024)))
        ac.update(M_H=mm >> 8, M_L=mm & 0xFF)
        rg, sg, bl, cf, c1 = ac["RANGE"], ac["SIGN"], ac["BLANK_LEN"], ac["CHOP_FAST"], ac["CHOP1_RATE"]
        az, cs = ac["ADC_ZERO"], ac["CHOP_STOP"]
        win = 15 if rg >= 1 else bl                    # the blanking runs from cycle 31 through cycle win - 1
        ind = dict(OFM=mm * (rg >= 1), OFS=sg * (rg >= 1), OFEN=int("0" * (4 - rg) + "1" * rg, 2),
                   AFE_IBIAS=ac["AFE_IBIAS"], CPF_TRIM=ac["CPF_TRIM"], BTRIM_P=ac["BTRIM_P"], BTRIM_N=ac["BTRIM_N"],
                   DWA_EN=ac["DWA_EN"], CHOP_EN=1 - cs,
                   TEST_CFG=ac["DBG_SEL"] * 64 + az * 32 + ac["ATP_EN"] * 16 + ac["ATP_SEL"],
                   BLANK_W=len([31] + list(range(win))), BLANK_HELD=az,
                   CHOP_HALF=int(FS.MCLK) // (128000 if cf else 64000) // 2,
                   CHOP1_HALF=0 if c1 == 0 else (32 * 1024 >> (c1 - 1)) // 2)
        got = pins_from_active(ac)
        bad = {k: (got.get(k), v) for k, v in ind.items() if got.get(k) != v}
        if bad:
            errs.append(f"pins_from_active differs from the independent derivation for {ac}: {bad}")
            break
    # the overload rule against the requirement (FLG-04) and the spec's section 5, which state it in words
    R = OVL_RULE
    for path, pat in ((REQ_DOC, r"直近 (\d+) フレームに両端が (\d+) 個以上"),
                      (DOC, r"直近 (\d+) フレームに (\d+) 個以上")):
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError as ex:
            errs.append(f"the overload rule cannot be compared with {os.path.basename(path)}: {ex}")
            continue
        mt = re.search(pat, txt)
        mc = re.search(r"両端（(\d+) または (\d+)）", txt)
        if not mt or not mc:
            errs.append(f"{os.path.basename(path)}: the overload rule's statement not found")
        elif (int(mt.group(1)), int(mt.group(2))) != (R["window"], R["threshold"]) or \
                (int(mc.group(1)), int(mc.group(2))) != tuple(R["codes"]):
            errs.append(f"OVL_RULE {R} differs from the rule stated in {os.path.basename(path)}: window {mt.group(1)}, threshold "
                        f"{mt.group(2)}, codes {mc.group(1)} / {mc.group(2)}")
    ovl_txt = next(f["desc"] for *_, f in all_fields() if f["name"] == "OVL_NOW")
    if f"直近 {R['window']} フレームに両端の符号が {R['threshold']} 個以上" not in ovl_txt:
        errs.append(f"STATUS.OVL_NOW's text does not state OVL_RULE: {ovl_txt}")
    # cfg_ok / nr_ok at the boundaries
    base = dict(M=0, SIGN=0, RANGE=1, AFE_IBIAS=3, CPF_TRIM=8, BTRIM_P=1, BTRIM_N=0, CHOP_FAST=1, CHOP1_RATE=3,
                DWA_EN=1, BLANK_LEN=7, ATP_EN=0, ATP_SEL=0, CHOP_STOP=0, ADC_ZERO=0)
    for r_, mx in RANGE_MAX_M.items():
        if not cfg_ok(dict(base, RANGE=r_, M=mx)) or (r_ and cfg_ok(dict(base, RANGE=r_, M=mx + 1))):
            errs.append(f"cfg_ok wrong at the top of range {r_}")
    ac = dict(base, M=1, SIGN=0)
    cases = [(dict(base, M=2), True), (dict(base, M=0), True), (dict(base, M=1, SIGN=1), False),
             (dict(base, M=0, SIGN=1), True), (dict(base, M=3), False), (dict(base, M=1, RANGE=2), False),
             (dict(base, M=1, CPF_TRIM=9), False), (dict(base, M=2, CHOP1_RATE=4), False)]
    for sh, want in cases:
        if nr_ok(sh, ac) != want:
            errs.append(f"nr_ok({sh['M']}, S{sh['SIGN']}, R{sh['RANGE']}) is {nr_ok(sh, ac)}, but the boundary case "
                        f"gives {want}")
    if set(base) != {f["name"] for *_, f in all_fields() if f["cls"] == "apply"} - {"M_H", "M_L"} | {"M"}:
        errs.append("the nr_ok model does not list exactly the shadowed settings")
    # overload rule against the full-scale code streams
    import numpy as np
    import hashlib
    for name in ("s4", "s20"):
        pth = os.path.join(HERE, "..", "build", "e2e", f"{name}.codes")
        if not os.path.exists(pth):
            errs.append(f"{name}.codes not found: the overload false-alarm check cannot run")
            continue
        h = hashlib.sha256(open(pth, "rb").read()).hexdigest()
        if h != FULLSCALE_SHA256[name]:
            errs.append(f"{name}.codes is not the stream checked on 11/19 (SHA-256 {h[:16]}...)")
        c = np.fromfile(pth, dtype=np.uint8)[256000:]
        ext = np.isin(c, OVL_RULE["codes"]).astype(np.int32)
        k = np.convolve(ext, np.ones(OVL_RULE["window"], dtype=np.int32), mode="valid")
        hits = int((k >= OVL_RULE["threshold"]).sum())
        if hits:
            errs.append(f"overload rule fires {hits} times on the full-scale stream {name}")
        notes.append(f"overload rule on {name}: {len(c)} frames, codes {c.min()}..{c.max()}, {hits} detections")
    if verbose:
        for n_ in notes:
            print("  " + n_)
        print(f"{len(errs)} violations" if errs else "no violations")
        for e in errs:
            print("  " + e)
    return errs


# ---------------------------------------------------------------------------------------------------------------
def md_tables():
    reg = ["| アドレス | 名前 | 種別 | 試験の鍵 | 既定値 | 内容 |", "|---|---|---|---|---|---|"]
    fld = ["| レジスタ | ビット | フィールド | 既定値 | 合法な値 | 反映 | アナログの端子 | 内容 |", "|---|---|---|---|---|---|---|---|"]
    cls_j = {"apply": "一括反映", "seq": "シーケンサ", "imm": "即時", "ro": "読み出し専用", "w1c": "W1C", "cmd": "命令"}
    for a, n, acc, lock, fields, desc in REGS:
        rv = 0
        for f in fields:
            rv |= f["reset"] << f["lsb"]
        shadow = any(f["cls"] == "apply" for f in fields)
        reg.append(f"| 0x{a:02X}{'（写し 0x%02X）' % (a + SHADOW_MIRROR) if shadow else ''} | {n} | {acc} | "
                   f"{'要' if lock else '—'} | {'—' if acc in ('WO',) or n == 'SAMPLE' else '0x%02X' % rv} | {desc} |")
        for f in fields:
            bits = f"[{f['msb']}:{f['lsb']}]" if f["msb"] != f["lsb"] else f"[{f['msb']}]"
            if f["legal"] is None:
                lg = "—"
            elif len(f["legal"]) > 3 and f["legal"] == list(range(f["legal"][0], f["legal"][-1] + 1)):
                lg = f"{f['legal'][0]}〜{f['legal'][-1]}"
            else:
                lg = "、".join(str(v) for v in f["legal"])
            fld.append(f"| {n} | {bits} | {f['name']} | {f['reset']} | {lg} | {cls_j[f['cls']]} | {f['pin'] or '—'} | {f['desc']} |")
    cmd = ["| 命令 | コード | 受け付ける状態（fsm_spec の状態遷移表） |", "|---|---|---|"]
    acc_states = {}
    for c in ("START", "STOP", "APPLY", "APPLY_NR", "FLUSH"):
        ok = [x[0] + ("（何もしない）" if FS.SEQ["table"][(x[0], c)] == FS.IGN else "")
              for x in FS.SEQ_STATES if x[0] != "RESET" and FS.SEQ["table"][(x[0], c)] != FS.IMP
              and (FS.SEQ["table"][(x[0], c)] == FS.IGN or
                   not all(b["actions"] == ["STATE_ERR"] for b in FS.SEQ["table"][(x[0], c)]))]
        acc_states[c] = "、".join(ok)
    acc_states["SOFT_RESET"] = "全て（未処理の命令があっても受け付け、CS_N の立ち上がりで直ちにリセット）"
    for c, v in COMMANDS.items():
        cmd.append(f"| {c} | 0x{v:02X} | {acc_states[c]} |")
    cmd.append(f"| （試験の鍵） | 0x{TEST_KEY:02X}（TEST_KEY へ。0x00 で施錠、その他の値は施錠して CMD_ERR） | — |")
    ss = ["| ビット | 名前 | 内容 |", "|---|---|---|"] + [f"| {b} | {n} | {d} |" for n, b, d in SAMPLE_STATUS]
    return "\n".join(reg), "\n".join(fld), "\n".join(cmd), "\n".join(ss)


def sv_package():
    out = ["// eeg_regs_pkg - addresses, fields, reset values and codes of the digital control's registers.",
           "// GENERATED by gf180/tapeout/rtl/spec/regmap.py; do not edit by hand.",
           "`timescale 1ns / 1ps", "`default_nettype none", "", "package eeg_regs_pkg;", ""]
    for a, n, acc, lock, fields, desc in REGS:
        out.append(f"    localparam logic [6:0] A_{n} = 7'h{a:02X};")
        if any(f["cls"] == "apply" for f in fields):
            out.append(f"    localparam logic [6:0] A_{n}_ACT = 7'h{a + SHADOW_MIRROR:02X};")
    out.append("")
    for a, n, acc, lock, fields, desc in REGS:
        for f in fields:
            w = f["msb"] - f["lsb"] + 1
            out.append(f"    localparam int {n}_{f['name']}_LSB = {f['lsb']};  localparam int {n}_{f['name']}_W = {w};"
                       f"  localparam logic [{w - 1}:0] {n}_{f['name']}_RST = {w}'d{f['reset']};")
            if f["legal"] is not None and f["cls"] in ("apply", "imm") and f["legal"] == list(range(f["legal"][0], f["legal"][-1] + 1)):
                # the field's own width, so that comparing a field with its limits needs no width extension
                out.append(f"    localparam logic [{w - 1}:0] {n}_{f['name']}_MIN = {w}'d{f['legal'][0]};"
                           f"  localparam logic [{w - 1}:0] {n}_{f['name']}_MAX = {w}'d{f['legal'][-1]};")
    out.append("")
    for n_, b_, _d in SAMPLE_STATUS:                   # the sample word's status byte (audit round 8: the RTL builds it
        if n_ != "0":                                  # from these, so the map and the RTL cannot differ)
            out.append(f"    localparam int SMP_{n_}_LSB = {b_};")
    out.append("")
    for c, v in COMMANDS.items():
        out.append(f"    localparam logic [7:0] CMD_{c} = 8'h{v:02X};")
    out.append(f"    localparam logic [7:0] TEST_KEY_VALUE = 8'h{TEST_KEY:02X};")
    mask = sum(1 << a for a in guarded_addrs())
    out.append(f"    localparam logic [127:0] GUARDED_ADDRS = 128'h{mask:032X};   // writes refused while a command is pending")
    for x in FS.SEQ_STATES:
        if x[1] is not None:
            out.append(f"    localparam logic [3:0] ST_{x[0]} = 4'd{x[1]};")
    out.append(f"    localparam logic [3:0] BLANK_WITH_DAC = 4'd{BLANK_WITH_DAC};   // CHOP_BLANK length, DAC on")
    out.append("    function automatic logic [9:0] range_max_m(input logic [2:0] r);   // cfg_ok: the largest M")
    out.append("        case (r)")
    out += [f"            3'd{r_}: range_max_m = 10'd{mx};" for r_, mx in sorted(RANGE_MAX_M.items())]
    out.append("            default: range_max_m = 10'd0;    // ranges 5..7 are never stored (RANGE_ERR)")
    out.append("        endcase")
    out.append("    endfunction")
    out.append("    function automatic logic [3:0] ofen_of_range(input logic [2:0] r);   // the DAC's group enables")
    out.append("        case (r)")
    out += [f"            3'd{r_}: ofen_of_range = 4'b{ofen_of_range(r_):04b};" for r_ in range(5)]
    out.append("            default: ofen_of_range = 4'b0000;")
    out.append("        endcase")
    out.append("    endfunction")
    wc = OVL_RULE["window"].bit_length()               # the width of a count 0 .. window
    out.append(f"    localparam int OVL_WINDOW = {OVL_RULE['window']};"
               f"  localparam logic [{wc - 1}:0] OVL_THRESHOLD = {wc}'d{OVL_RULE['threshold']};")
    out += ["", "endpackage", "", "`default_nettype wire", ""]
    return "\n".join(out)


def sv_defs():
    """The package's constants as module-scope localparams (synthesis without package support): `include it in the
    body of every module that needs them."""
    lines = sv_package().split("\n")
    body = lines[lines.index("package eeg_regs_pkg;") + 1: lines.index("endpackage")]
    body = [l for l in body if l.strip()]
    return "\n".join(["// eeg_regs_defs.svh - the register map's constants (GENERATED by gf180/tapeout/rtl/spec/regmap.py;",
                      "// do not edit by hand). `include inside a module body; each module uses only some of them.",
                      "/* verilator lint_off UNUSEDPARAM */"] + body + ["/* verilator lint_on UNUSEDPARAM */"]) + "\n"


def generate(write=True):
    """Writes the package, the defs and the document's generated blocks; write=False returns them ({path: text})."""
    if check(verbose=write):
        print("not generating: fix the violations first")
        return 1
    out = {PKG: sv_package(), DEFS: sv_defs()}
    blocks = dict(zip(("reg_summary", "reg_fields", "commands", "sample_status"), md_tables()))
    blocks["reg_checks"] = "\n".join(f"- {c}" for c in CHECKS)
    if os.path.exists(DOC):
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
    print("wrote", os.path.relpath(PKG, REPO), "and the generated blocks of", os.path.relpath(DOC, REPO))
    return 0


def fresh():
    """The generated files (package, defs, the document's generated blocks) equal what the map gives now."""
    want = generate(write=False)
    if not isinstance(want, dict):
        return 1
    stale = [os.path.relpath(p, REPO) for p, text in want.items()
             if not os.path.exists(p) or open(p, encoding="utf-8").read() != text]
    print("generated files up to date" if not stale else "STALE (run regmap.py gen): " + ", ".join(stale))
    return 1 if stale else 0


def check_messages():
    """(line, fixed text) of every violation message of check(): the longest literal piece of each errs append. The
    self-test requires each to be the expected message of a mutation that produces it (audit round 9, auditor C, as
    fsm_spec.check_messages)."""
    import ast
    import inspect
    import textwrap
    out, first = [], check.__code__.co_firstlineno
    for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(check)))):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "errs" and n.args):
            arg = n.args[0]
            if isinstance(arg, ast.BinOp):              # "text " + ", ".join(...)
                arg = arg.left
            parts = arg.values if isinstance(arg, ast.JoinedStr) else [arg]
            lits = [v.value for v in parts if isinstance(v, ast.Constant) and isinstance(v.value, str)]
            out.append((first + n.lineno - 1, max(lits, key=len).strip() if lits else "", "\x00".join(lits)))
    return out


def selftest():
    """Mutation test of the checker: each mutation is a plausible register-map error and must be detected by the
    message it is written for (SELFTEST_EXPECT); every message of check() must be the expected message of a mutation,
    and a crash of check() is no detection (audit round 9, auditor C)."""
    import copy
    import tempfile
    g = globals()
    keep = {k: copy.deepcopy(g[k]) for k in ("REGS", "COMMANDS", "RANGE_MAX_M", "OVL_RULE", "TEST_KEY", "PIN_OF_CONTROL",
                                             "BLANK_WITH_DAC", "REQ_DOC", "DOC", "HERE", "FULLSCALE_SHA256")}
    keep_fn = {"nr_ok": nr_ok, "cfg_ok": cfg_ok, "pins_from_active": pins_from_active, "guarded_addrs": guarded_addrs,
               "ofen_of_range": ofen_of_range}
    tmp = tempfile.mkdtemp()
    no_rule = os.path.join(tmp, "no_rule.md")
    with open(no_rule, "w", encoding="utf-8") as fo:
        fo.write("過負荷の規則の文のない文書\n")

    def fld(reg, name):
        return next(f for f in next(r for r in g["REGS"] if r[1] == reg)[4] if f["name"] == name)

    def m_dup_addr():
        r = list(g["REGS"][1]); r[0] = 0x00; g["REGS"][1] = tuple(r)

    def m_overlap():
        fld("BOOST_TRIM", "BTRIM_N").update(msb=1, lsb=0)

    def m_reset_illegal():
        fld("BLANK", "BLANK_LEN")["reset"] = 0

    def m_imm_analog():
        fld("CPF_TRIM", "CPF_TRIM")["cls"] = "imm"

    def m_no_source():
        fld("ADC_CFG", "CHOP1_RATE")["pin"] = None

    def m_short_rst():
        fld("T_RST", "T_RST")["legal"] = rng(12, 255)

    def m_bad_default():
        fld("AFE_IBIAS", "AFE_IBIAS")["reset"] = 2

    def m_cmd_close():
        g["COMMANDS"]["FLUSH"] = 0x45

    def m_marker():
        fld("STATUS", "MARK0")["legal"] = [0, 1]

    def m_state():
        fld("STATE", "STATE")["legal"] = [0, 1, 2, 3, 4, 5, 6, 7]

    def m_range():
        g["RANGE_MAX_M"][1] = 128

    def m_nr_range():
        g["nr_ok"] = lambda sh, ac: abs((1 - 2 * sh["SIGN"]) * sh["M"] - (1 - 2 * ac["SIGN"]) * ac["M"]) <= 1

    def m_nr_two_steps():
        g["nr_ok"] = lambda sh, ac: sh["RANGE"] == ac["RANGE"] and abs((1 - 2 * sh["SIGN"]) * sh["M"] - (1 - 2 * ac["SIGN"]) * ac["M"]) <= 2

    def m_ovl():
        g["OVL_RULE"]["threshold"] = 0

    def m_ovl2():                                       # audit round 7, auditor C (each passed check)
        g["OVL_RULE"]["threshold"] = 2

    def m_ovl_window():
        g["OVL_RULE"]["window"] = 8
        g["OVL_RULE"]["threshold"] = 8

    def m_range0():
        g["RANGE_MAX_M"][0] = 0

    def m_blank():
        f0 = keep_fn["pins_from_active"]
        g["pins_from_active"] = lambda ac: dict(f0(ac), BLANK_W=f0(ac)["BLANK_W"] - 1)

    def m_tcfg4():                                     # audit round 8: TEST_CFG[4] from CHOP_STOP, not ATP_EN
        f0 = keep_fn["pins_from_active"]
        g["pins_from_active"] = lambda ac: dict(f0(ac), TEST_CFG=(f0(ac)["TEST_CFG"] & ~16) | (ac["CHOP_STOP"] << 4))

    def m_mirror():
        g["REGS"].append((0x30, "EXTRA", "RO", False, [F("X", 7, 0, 0, [0], "ro", "x")], "x"))

    # audit round 9, auditor C: the messages no mutation produced
    def m_outside():
        fld("BLANK", "BLANK_LEN").update(msb=8, lsb=5)

    def m_reset_wide():
        fld("AFE_IBIAS", "AFE_IBIAS")["reset"] = 4

    def m_legal_wide():
        fld("AFE_IBIAS", "AFE_IBIAS")["legal"] = [0, 1, 2, 3, 4]

    def m_seq_pin():
        fld("TEST_CTRL", "ADC_ZERO")["pin"] = "AFE_RST"

    def m_stray_pin():
        fld("DEBUG", "DBG_SEL")["pin"] = "TEST_CFG[7]"

    def m_twarm_max():
        f = fld("T_WARM", "T_WARM")
        f["legal"] = [v for v in f["legal"] if v != max(f["legal"])]

    def m_guard():
        f0 = keep_fn["guarded_addrs"]
        g["guarded_addrs"] = lambda: f0()[:-1]

    def m_ofen():
        f0 = keep_fn["ofen_of_range"]
        g["ofen_of_range"] = lambda r: 0b0111 if r == 4 else f0(r)

    def m_pin_of_control():
        g["PIN_OF_CONTROL"] = {k: v for k, v in keep["PIN_OF_CONTROL"].items() if k != "DWA_EN"}

    def m_pins_lack():
        f0 = keep_fn["pins_from_active"]
        g["pins_from_active"] = lambda ac: {k: v for k, v in f0(ac).items() if k != "DWA_EN"}

    def m_blank_dac():
        g["BLANK_WITH_DAC"] = keep["BLANK_WITH_DAC"] - 1

    def m_req_missing():
        g["REQ_DOC"] = os.path.join(tmp, "missing.md")

    def m_doc_no_rule():
        g["DOC"] = no_rule

    def m_extra_apply():
        next(r for r in g["REGS"] if r[1] == "CHOP_CFG")[4].append(F("CHOP_X", 1, 1, 0, [0, 1], "apply", "x"))

    def m_codes_missing():
        g["HERE"] = os.path.join(tmp, "nowhere")

    def m_codes_other():
        g["FULLSCALE_SHA256"] = {k: "0" * 64 for k in keep["FULLSCALE_SHA256"]}

    def m_cfg_top():
        f0 = keep_fn["cfg_ok"]
        g["cfg_ok"] = lambda sh: f0(sh) or (sh["RANGE"] >= 1 and sh["M"] == g["RANGE_MAX_M"][sh["RANGE"]] + 1)

    muts = [("アドレスの重なり", m_dup_addr), ("フィールドの重なり", m_overlap), ("合法でない既定値", m_reset_illegal),
            ("アナログに効く設定が即時", m_imm_analog), ("アナログの端子の出どころの欠落", m_no_source),
            ("T_RST の最小値が 100 µs 未満", m_short_rst), ("既定値が推奨値でない（AFE_IBIAS 2）", m_bad_default),
            ("命令コードが 1 ビット違い", m_cmd_close), ("STATUS の固定ビットがない", m_marker),
            ("STATE のコードの欠落", m_state), ("範囲 1 の上限の誤り", m_range), ("nr_ok が範囲の変更を許す", m_nr_range),
            ("nr_ok が 2 段を許す", m_nr_two_steps), ("過負荷の規則が常に成立", m_ovl), ("写しのアドレスとの重なり", m_mirror),
            ("過負荷の閾値が 2", m_ovl2), ("過負荷の窓が 8 で閾値が 8", m_ovl_window), ("範囲 0 の M の上限が 0", m_range0),
            ("CHOP_BLANK の幅に 1 を足さない", m_blank), ("TEST_CFG[4] を CHOP_STOP から取る", m_tcfg4),
            ("フィールドがバイトの外", m_outside), ("既定値がフィールドの幅を超える", m_reset_wide),
            ("合法な値がフィールドの幅を超える", m_legal_wide), ("シーケンサの駆動する AFE_RST をレジスタも駆動", m_seq_pin),
            ("どちらの一覧にもない端子", m_stray_pin), ("T_WARM の最大が TIMING と合わない", m_twarm_max),
            ("ガードするアドレスの欠落", m_guard), ("範囲 4 の OFEN が G3 を入れない", m_ofen),
            ("PIN_OF_CONTROL の欠落", m_pin_of_control), ("pins_from_active の端子の欠落", m_pins_lack),
            ("BLANK_WITH_DAC がフレームの最長のブランキングでない", m_blank_dac),
            ("要件定義が読めない", m_req_missing), ("詳細仕様に過負荷の規則の文がない", m_doc_no_rule),
            ("nr_ok の模型にない反映の設定", m_extra_apply), ("全振幅の符号の列がない", m_codes_missing),
            ("全振幅の符号の列が 11/19 のものでない", m_codes_other), ("cfg_ok が範囲の上限 ＋ 1 を受け付ける", m_cfg_top)]
    results, problems = [], []
    for name, m in muts:
        for k, v in keep.items():
            g[k] = copy.deepcopy(v)
        g.update(keep_fn)
        m()
        try:
            e = check(verbose=False)
        except Exception as ex:                        # a crash is no detection (audit round 9)
            e = None
            problems.append(f"mutation {name}: check() crashed ({ex!r})")
        results.append((name, e))
    for k, v in keep.items():
        g[k] = copy.deepcopy(v)
    g.update(keep_fn)
    msgs = check_messages()
    texts = [t for _, t, _ in msgs]
    problems += [f"line {ln}: a message without 12 fixed characters (it cannot be told apart)" for ln, t, _ in msgs
                 if len(t) < 12]
    problems += [f"two messages share the fixed text {t!r}" for t in sorted(set(texts)) if texts.count(t) > 1]
    problems += [f"line {ln}: the fixed text {t!r} also occurs in the message of line {l2}" for ln, t, _ in msgs
                 for l2, _, whole in msgs if l2 != ln and t in whole]
    expected, n_det = set(), 0
    for name, e in results:
        want = SELFTEST_EXPECT.get(name, ())
        if not want:
            problems.append(f"mutation {name}: no expected message (SELFTEST_EXPECT)")
        expected |= set(want)
        problems += [f"mutation {name}: expects {w!r}, which is not a message of check()" for w in want if w not in texts]
        lacking = [w for w in want if e is None or not any(w in x for x in e)]
        det = bool(want) and e is not None and not lacking and all(w in texts for w in want)
        n_det += det
        print(f"{'detected' if det else 'MISSED  '} {name}: " + ("crashed" if e is None else f"{len(e)} violations")
              + (", the expected one(s) among them" if det else f", without the expected {lacking[0]!r}" if lacking else ""))
    for ln, t, _ in msgs:
        if t not in expected:
            problems.append(f"line {ln}: no mutation expects the message {t!r}")
    e = check(verbose=False)
    for p_ in problems:
        print("PROBLEM  " + p_)
    print(f"{n_det} of {len(results)} mutations detected by their expected messages; {len(msgs)} messages, "
          f"{len(set(texts) & expected)} expected by a mutation; unmutated map: {len(e)} violations")
    return 0 if n_det == len(results) and not problems and not e else 1


# The message each self-test mutation is written for, by its fixed text (audit round 9, auditor C; as in
# fsm_spec.SELFTEST_EXPECT): the self-test checks that each is produced and that every message of check() is
# expected by a mutation.
SELFTEST_EXPECT = {
    'アドレスの重なり': ('used by two registers:',),
    'フィールドの重なり': (': overlaps another field',),
    '合法でない既定値': ('is not among the legal values',),
    'アナログに効く設定が即時': ('(analog controls change only through START / APPLY / APPLY_NR)',),
    'アナログの端子の出どころの欠落': ('(exactly one required)',),
    'T_RST の最小値が 100 µs 未満': (', below the analog minimum of',),
    '既定値が推奨値でない（AFE_IBIAS 2）': (', the recommended operating value is',),
    '命令コードが 1 ビット違い': ('bit (codes must differ in 2 bits or more)',),
    'STATUS の固定ビットがない': ('STATUS has no fixed 1 and 0 bits (cannot tell it from a dead MISO)',),
    'STATE のコードの欠落': ("STATE field does not match the sequencer's state codes",),
    '範囲 1 の上限の誤り': (', the DAC groups give',),
    'nr_ok が範囲の変更を許す': (', but the boundary case gives',),
    'nr_ok が 2 段を許す': (', but the boundary case gives',),
    '過負荷の規則が常に成立': ('times on the full-scale stream',),
    '写しのアドレスとの重なり': (': the active copy 0x',),
    '過負荷の閾値が 2': ("STATUS.OVL_NOW's text does not state OVL_RULE:", 'differs from the rule stated in',),
    '過負荷の窓が 8 で閾値が 8': ("STATUS.OVL_NOW's text does not state OVL_RULE:",),
    '範囲 0 の M の上限が 0': ('; the DAC is off, so every M (0..',),
    'CHOP_BLANK の幅に 1 を足さない': ('pins_from_active differs from the independent derivation for',),
    'TEST_CFG[4] を CHOP_STOP から取る': ('pins_from_active differs from the independent derivation for',),
    'フィールドがバイトの外': ('outside the byte',),
    '既定値がフィールドの幅を超える': ('wider than the field (',),
    '合法な値がフィールドの幅を超える': (': a legal value does not fit the field',),
    'シーケンサの駆動する AFE_RST をレジスタも駆動': (': driven by the sequencer but also by',),
    'どちらの一覧にもない端子': (': a pin that is in neither list of controls',),
    'T_WARM の最大が TIMING と合わない': (': the register reaches',),
    'ガードするアドレスの欠落': ('guarded addresses',),
    '範囲 4 の OFEN が G3 を入れない': ('does not switch on the groups G0..G',),
    'PIN_OF_CONTROL の欠落': ('PIN_OF_CONTROL does not list exactly the analog controls',),
    'pins_from_active の端子の欠落': ('pins_from_active lacks',),
    'BLANK_WITH_DAC がフレームの最長のブランキングでない': ("is not the frame's longest blanking",),
    '要件定義が読めない': ('the overload rule cannot be compared with',),
    '詳細仕様に過負荷の規則の文がない': (": the overload rule's statement not found",),
    'nr_ok の模型にない反映の設定': ('the nr_ok model does not list exactly the shadowed settings',),
    '全振幅の符号の列がない': ('.codes not found: the overload false-alarm check cannot run',),
    '全振幅の符号の列が 11/19 のものでない': ('.codes is not the stream checked on 11/19 (SHA-256',),
    'cfg_ok が範囲の上限 ＋ 1 を受け付ける': ('cfg_ok wrong at the top of range',),
}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        sys.exit(1 if check() else 0)
    if cmd == "gen":
        sys.exit(generate())
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "fresh":
        sys.exit(fresh())
    print(__doc__)
