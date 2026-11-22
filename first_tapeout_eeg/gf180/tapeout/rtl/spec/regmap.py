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
#   imm    takes effect at once; no analog effect (or latched at a timer start); DEBUG's DBG_SEL and RAW_EN: none
#          with DBG_SEL 0 and RAW_EN 0, DBG_SEL 1..3 and the RAW stream are debug only, their pad coupling not
#          characterized (requirements 4.10; audit round 30, auditor B, as item 410)
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
                                    "シーケンサの状態（" + "、".join(f"{c} {n}" for c, n in sorted((x[1], x[0]) for x in FS.SEQ_STATES
                                                                                            if x[1] is not None)) + "）")],
     "シーケンサの状態"),
    (0x05, "FIFO_LEVEL", "RO", False, [F("LEVEL", 3, 0, 0, rng(0, 8), "ro", "FIFO のサンプルの数")], "FIFO の占有数"),
    (0x06, "ERR", "W1C", False, [F("CMD_ERR", 7, 7, 0, [0, 1], "w1c", "未定義の命令コード、または TEST_KEY への 0x3C と 0x00 以外の値"),
                                 F("STATE_ERR", 6, 6, 0, [0, 1], "w1c", "その状態で受け付けない命令、未処理の命令への上書き、または未処理の命令がある間のシャドウとタイマへの書き込み（SOFT_RESET は常に受け付ける）、シーケンサの不正な状態の値（直ちに IDLE へ。NFR-05）"),
                                 F("CFG_ERR", 5, 5, 0, [0, 1], "w1c", "整合しない設定（cfg_ok でない）での START、APPLY、APPLY_NR、または AFE の動作中の nr_ok でない APPLY_NR"),
                                 F("RANGE_ERR", 4, 4, 0, [0, 1], "w1c", "範囲外の値の書き込み（書かない）"),
                                 F("ADDR_ERR", 3, 3, 0, [0, 1], "w1c", "未定義のアドレス、読み出し専用への書き込み、鍵なしの試験のレジスタへの書き込み"),
                                 F("CRC_ERR", 2, 2, 0, [0, 1], "w1c", "書き込みの CRC の不一致（書かない）"),
                                 F("FRAME_ERR", 1, 1, 0, [0, 1], "w1c", "バイトの途中の CS_N、不完全または過長な書き込み、完了したフレーム（書き込み、CRC 付きの読み出し、8 バイトのサンプル）のあとのビット、CRC 有効時の CRC のバイトのない読み出し（先頭バイトだけのフレームを除く）と 8 バイトでないサンプル、フレームの中（CS_N の立ち上がりの時点）の SPI の状態機械の不正な状態の値（何も確定しない。フレームの間の不正な値は次の CS_N の立ち下がりで先頭バイトの状態に戻り、旗は立たない。NFR-05）"),
                                 F("RESET_FLAG", 0, 0, 1, [0, 1], "w1c", "リセットが起きた（既定値 1）")], "エラー（W1C）"),
    (0x07, "DFLAG", "W1C", False, [F("OVL", 1, 1, 0, [0, 1], "w1c", "FILL または RUN の間に、過負荷の検出の成り立つ両端の符号があった（検出の窓の尾だけでは立たない）"),
                                   F("OVERRUN", 0, 0, 0, [0, 1], "w1c", "FIFO が満杯でサンプルを捨てた")], "データのフラグ（W1C）"),
    (0x08, "ALERT_MASK", "RW", False, [F("ALERT_MASK", 7, 0, 0xFF, rng(0, 255), "imm", "ERR のビットごとに ALERT に含める（1）")], "ALERT のマスク"),
    (0x09, "ALERT_MASK_D", "RW", False, [F("ALERT_MASK_D", 1, 0, 0x3, rng(0, 3), "imm", "DFLAG のビットごとに ALERT に含める（1）。ホスト手順は 0x00 とする（要件 5.4 の手順 3。第 22 回）")], "ALERT のマスク（データ）"),
    (0x0A, "ODR_H", "RO", False, [F("ODR_H", 7, 0, 0x03, [0x03], "ro", "出力データレート 1000 SPS の上位")], "出力データレート"),
    (0x0B, "ODR_L", "RO", False, [F("ODR_L", 7, 0, 0xE8, [0xE8], "ro", "同下位")], "出力データレート"),
    (0x0C, "FORMAT", "RO", False, [F("QBITS", 3, 0, 5, [5], "ro", "量子化器のビット数")], "形式"),
    (0x10, "COMMAND", "WO", False, [F("CMD", 7, 0, 0, None, "cmd", "命令コード（第 2.3 節）。次の tick で処理")], "命令"),
    (0x11, "TEST_KEY", "WO", False, [F("KEY", 7, 0, 0, None, "imm", "0x3C で試験のレジスタを解錠、0x00 で施錠。その他の値は施錠し、CMD_ERR（書き込みの確定の時点で効く）")], "試験の鍵"),
    # analog configuration (shadow; the active copies are read at addr + 0x10)
    (0x20, "OFF_M_H", "RW", False, [F("M_H", 1, 0, 0, rng(0, 3), "apply", "オフセット DAC の大きさ M[9:8]", "OFM[9:8]")], "オフセット DAC（上位）"),
    (0x21, "OFF_M_L", "RW", False, [F("M_L", 7, 0, 0, rng(0, 255), "apply", "M[7:0]", "OFM[7:0]")], "オフセット DAC（下位）"),
    (0x22, "OFF_CTRL", "RW", False, [F("SIGN", 4, 4, 0, [0, 1], "apply", "符号 S（打ち消す量は (1 − 2 S) × M × 公称 0.311 mV。実測の 1 段は増幅器の入力で約 0.301 mV）", "OFS"),
                                     F("RANGE", 2, 0, 0, rng(0, 4), "apply", "範囲（0 切、1〜4 で公称 ±39／79／159／318 mV（範囲 4 は実測で約 ±308 mV）。5〜7 は RANGE_ERR）", "OFEN[3:0]")],
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
# pads and debug: no analog effect with DBG_SEL 0 and RAW_EN 0 (11/16: +0.64 nV); DBG_SEL 1..3 and the RAW stream are
# debug only, their pad coupling not characterized (requirements 4.10, items 308, 385; audit round 29, auditor A: this
# said "no analog effect" for DBG_SEL)
DIGITAL_ONLY = {"TEST_CFG[7:6]", "RAW_DATA／RAW_CLK"}

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


# The reset value of every writable field, written from the requirements and not from REGS (audit round 10, auditor C:
# a one-character edit of a test control's reset - CHOP_STOP 1 stops the chopper from power-up, ADC_ZERO 1 shorts the
# ADC's input - passed every check, test and self-test, because the generated tests and the pin monitor follow the map)
REQUIRED_RESET = dict(
    ALERT_MASK=0xFF, ALERT_MASK_D=0x3,                    # every flag raises ALERT (REG-05)
    M_H=0, M_L=0, SIGN=0, RANGE=0,                        # the offset DAC off (range 0) from power-up (5.4, step 9)
    AFE_IBIAS=3, CPF_TRIM=8, BTRIM_N=0, BTRIM_P=1, CHOP_FAST=1, DWA_EN=1, CHOP1_RATE=3, BLANK_LEN=7,   # REG-05
    T_WARM=5, T_ELEC=0, T_REC=32, T_PRE=3, T_RST=13,      # SEQ-02, SEQ-03, SEQ-05 (5 ms, 0, 250 us, 23.4 us, 101.6 us)
    DRDY_MODE=0, CRC_EN=0,                                # DAT-04 (level), SPI-05 (off)
    ATP_EN=0, ATP_SEL=0, CHOP_STOP=0, ADC_ZERO=0, DBG_SEL=0, RAW_EN=0,   # the test settings off (ANA-05, REG-08)
    RESET_FLAG=1, CMD_ERR=0, STATE_ERR=0, CFG_ERR=0, RANGE_ERR=0, ADDR_ERR=0, CRC_ERR=0, FRAME_ERR=0,   # FLG-02
    OVL=0, OVERRUN=0, CMD=0, KEY=0,
    # read-only, after a reset: STATUS's fixed bits (SPI-03), ALERT from RESET_FLAG (FLG-02) under the default masks,
    # AFE_RST held (SEQ-13), IDLE, no command pending, no data (the FIFO empty)
    MARK1=1, MARK0=0, ALERT=1, CMD_PENDING=0, READY=0, DATA=0, OVL_NOW=0, AFE_RST=1, STATE=0, LEVEL=0)
ACCESS_CLASSES = {"RO": ("ro",), "W1C": ("w1c",), "RW": ("apply", "imm"), "WO": ("cmd", "imm")}
# The legal values of every writable field, written from the requirements and not from REGS (audit round 11, auditor
# C: a legal set narrowed in regmap.py, e.g. CRC_EN [0], CHOP1_RATE 0..4, BLANK_LEN 2..15, AFE_IBIAS [3], or a timer
# with a hole, passed every check; eeg_regs enforces only a field's [MIN, MAX] or nothing)
_bit = [0, 1]
REQUIRED_LEGAL = dict(
    ALERT_MASK=list(range(256)), ALERT_MASK_D=list(range(4)),               # any mask
    M_H=list(range(4)), M_L=list(range(256)), SIGN=_bit, RANGE=list(range(5)),   # M up to 1023, ranges 0..4
    AFE_IBIAS=list(range(4)),                     # 0..2 for evaluation, writable (the user's decision, 11/20)
    CPF_TRIM=list(range(16)), BTRIM_N=list(range(4)), BTRIM_P=list(range(4)),     # the trims' full ranges
    CHOP_FAST=_bit, DWA_EN=_bit, CHOP1_RATE=list(range(6)),                 # CHOP1 off, 1 / 2 / 4 / 8 / 16 kHz
    BLANK_LEN=list(range(1, 16)),                 # REG-06: 0 gives RANGE_ERR
    T_WARM=list(range(5, 256)), T_ELEC=list(range(256)),                    # SEQ-02 (5..255 ms), SEQ-03 (0..255 ms)
    T_REC=list(range(29, 256)), T_PRE=list(range(3, 256)), T_RST=list(range(13, 256)),   # SEQ-14: 0.22 ms, 20 us,
    #                                             100 us on the 7.8125-us grid (29, 3, 13)
    DRDY_MODE=_bit, CRC_EN=_bit,                  # DAT-04, SPI-05
    ATP_EN=_bit, ATP_SEL=list(range(16)), CHOP_STOP=_bit, ADC_ZERO=_bit, DBG_SEL=list(range(4)), RAW_EN=_bit,   # TST
    RESET_FLAG=_bit, CMD_ERR=_bit, STATE_ERR=_bit, CFG_ERR=_bit, RANGE_ERR=_bit, ADDR_ERR=_bit, CRC_ERR=_bit,
    FRAME_ERR=_bit, OVL=_bit, OVERRUN=_bit,       # the W1C flags
    CMD=None, KEY=None)                           # any code: undefined commands give CMD_ERR, wrong keys lock
# a mask register's bit k masks its flag register's bit k: every flag needs its mask bit
MASKS = {"ALERT_MASK": "ERR", "ALERT_MASK_D": "DFLAG"}
# the read-only fields the requirements and the spec name (with REQUIRED_RESET's fields: every field of the map)
REQUIRED_RO = {"ID", "VERSION", "FIFO_DEPTH", "CRC", "ODR_H", "ODR_L", "QBITS", "SAMPLE"}
# addresses and bits the requirements name (the host procedure 5.4 and its examples, SPI-03): the host relies on them
# (audit round 20, auditor C: FIFO_LEVEL, which steps 5 and 6 and rule (b) read at 0x05 since round 18, and TEST_MUX
# were missing; check() now requires every NAME（0xNN） of the requirements and the spec to be held here; audit round
# 29, auditor B: step 3's bracket confirms the lock by a write of TEST_CTRL（0x61）; audit round 31, auditor C: the
# bracket names TEST_KEY and DEBUG (0x11, 0x60-0x62) without the NAME（0xNN） form, so a move of either passed check();
# audit round 32, auditor B: the spec's 2.3 names the guarded set by ranges, 0x20-0x28, 0x60, 0x61 and 0x50-0x54, and
# BLANK, CPF_TRIM or OFF_CTRL moved within their regions passed: every guarded register is held here, REG-01's list
# must equal this table, and the stated ranges must equal guarded_addrs())
FIXED_ADDR = {"ID": 0x00, "STATUS": 0x03, "STATE": 0x04, "FIFO_LEVEL": 0x05, "ERR": 0x06, "DFLAG": 0x07,
              "ALERT_MASK": 0x08, "COMMAND": 0x10, "TEST_KEY": 0x11, "OFF_M_H": 0x20, "OFF_M_L": 0x21,
              "OFF_CTRL": 0x22, "AFE_IBIAS": 0x23, "CPF_TRIM": 0x24, "BOOST_TRIM": 0x25, "CHOP_CFG": 0x26,
              "ADC_CFG": 0x27, "BLANK": 0x28, "SAMPLE": 0x40, "T_WARM": 0x50, "T_ELEC": 0x51, "T_REC": 0x52,
              "T_PRE": 0x53, "T_RST": 0x54, "IF_CFG": 0x55, "TEST_MUX": 0x60, "TEST_CTRL": 0x61, "DEBUG": 0x62}
FIXED_BITS = {"MARK1": 7, "MARK0": 6, "CRC_EN": 0, "DRDY_MODE": 1,
              # audit round 13, auditor C: the flags the host procedure writes and reads by value (REG-01, FLG-02), and
              # the state and the level from bit 0 (their moves passed every check, caught only by tb literals)
              "CMD_ERR": 7, "STATE_ERR": 6, "CFG_ERR": 5, "RANGE_ERR": 4, "ADDR_ERR": 3, "CRC_ERR": 2, "FRAME_ERR": 1,
              "RESET_FLAG": 0, "OVL": 1, "OVERRUN": 0, "STATE": 0, "LEVEL": 0,
              # audit round 15, auditor C: STATUS's other six bits (the host reads READY, DATA, CMD_PENDING and ALERT by
              # position; READY and DATA exchanged in the map passed every check, the RTL and the benches following it)
              "ALERT": 5, "CMD_PENDING": 4, "READY": 3, "DATA": 2, "OVL_NOW": 1, "AFE_RST": 0}
# the registers the requirements name for the test fields (REG-08: TEST_MUX, TEST_CTRL, DEBUG, locked) and for the
# interface fields (IF_CFG), checked both ways: each field in its register, and those registers holding no other
# field (audit round 29, auditor C: a field moved to another register at its lowest free bits passed check() in 88
# of 227 cases, among them CHOP_STOP in CHOP_CFG, RAW_EN in IF_CFG (round 28's m179 made legal at the source) and
# SIGN in TEST_CTRL, which steps 3 and 7 would then write only with the key)
FIELD_REGISTER_REQUIRED = {"ATP_EN": "TEST_MUX", "ATP_SEL": "TEST_MUX", "CHOP_STOP": "TEST_CTRL",
                           "ADC_ZERO": "TEST_CTRL", "DBG_SEL": "DEBUG", "RAW_EN": "DEBUG", "DRDY_MODE": "IF_CFG",
                           "CRC_EN": "IF_CFG"}
# the fields the requirements compare as whole bytes (REG-02, SPI-09, REG-08: the command codes, 0xA5 among them, and
# the test key; audit round 15, auditor C: either narrowed to 7 bits passed every check)
WHOLE_BYTE = {"CMD", "KEY"}
# the defined readable addresses one bit away from the sample window (0x40): a read header of theirs that loses a bit
# becomes 0xC0, a short sample read whose third byte (SEQ_H) passes the host's CRC for one SEQ_H in 256; the host
# procedure confirms exactly these by a second read (requirements 5.4 (b); audit round 16, auditor B)
WINDOW_NEIGHBOURS_REQUIRED = [0x00, 0x50, 0x60]
# The readable addresses a single SCLK slip in the header turns into a read of the sample window (audit round 19,
# auditor B): the host reads 0x00, 0x50 and 0x60 twice (5.4 (b)), never reads 0x01 (VERSION), and reads 0x20
# (OFF_M_H) only back after writing it (step 3), twice since audit round 27 (auditor B: "a wrong value that passes
# also needs a failed write" was the lost-write-plus-one-slip case round 26 had closed for the active copies), and in
# step 4's comparison of every shadow with its active copy, twice there too (audit round 29, auditor B)
WINDOW_SLIP_NEIGHBOURS_REQUIRED = [0x00, 0x01, 0x20, 0x50, 0x60]
# The registers the host procedure decides from by a CRC read, with the slip pairs it tolerates (audit round 18,
# auditor B: one SCLK slip turned STATUS into another value with a valid CRC, 62 pairs, since the header 0x83 and
# STATUS's bit 7 make the CRC's own polynomial; the host reads READY from STATE, DATA from FIFO_LEVEL and CMD_PENDING
# only 17 frames after the command, when it is 0 and a slip can only read a false 1: audit round 24, auditor B).
# ERR's one pair needs four flags at once (0x66: RESET_FLAG read, a needless restart by rule (c)). The
# active copies too (NAME.ACT; audit round 20, auditor B): step 4 confirms an APPLY_NR (always) and an APPLY in
# IDLE..FILL by them and rule (c) compares them. OFF_M_L's copy reads 0xAA as 0xAB under one slip, both ways: with
# 0xAA the new value an executed step reads as not executed (the APPLY_NR sent again changes nothing and marks
# 3 + T_ELEC samples); with 0xAA the old value and 0xAB the new (a step up from M = 170, 426, 682, 938) a command that
# was not executed reads as executed (audit round 26, auditor B: old-setting samples used as new, the host's M one
# step off). Step 4 and rule (c) use a copy only when two CRC-valid reads in a row agree (audit round 24, auditor B:
# rule (c)'s one read restarted the channel, the offset search included)
# the slip counts the documents quote for registers the host does not decide from alone (5.4 (b): STATUS is not used
# alone, T_WARM is read twice; audit round 20, auditor C: the counts were not pinned and T_WARM's was wrong)
SLIP_COUNTS_RECORDED = {"STATUS": 62, "T_WARM": 17,
                        # every register step 3 writes and reads back, twice (audit round 27, auditor B: one
                        # read-back took a lost write for a done one under one slip: OFF_M_L 0xDA read as 0xDB,
                        # T_REC 0x32 as 0x31); every writable register is recorded here or in SLIP_DECIDE_REQUIRED
                        "ALERT_MASK": 3, "ALERT_MASK_D": 1, "OFF_M_H": 0, "OFF_M_L": 1, "OFF_CTRL": 0,
                        "AFE_IBIAS": 0, "CPF_TRIM": 0, "BOOST_TRIM": 0, "CHOP_CFG": 0, "ADC_CFG": 0, "BLANK": 0,
                        "T_ELEC": 3, "T_REC": 10, "T_PRE": 32, "T_RST": 2, "TEST_MUX": 1, "TEST_CTRL": 0,
                        "DEBUG": 0}
# where the requirements' rule 5.4 (b) states them (audit round 21, auditor C: the record was checked against the
# model only, so the requirements' text could say anything)
SLIP_COUNT_PATTERNS = {"STATUS": r"STATUS の 64 通りの値で (\d+) 組", "T_WARM": r"T_WARM は (\d+) 組"}
SLIP_DECIDE_REQUIRED = {"STATE": [], "FIFO_LEVEL": [], "DFLAG": [], "IF_CFG": [], "ERR": [(0x66, 0x67)],
                        "OFF_M_H.ACT": [], "OFF_M_L.ACT": [(0xAA, 0xAB)], "OFF_CTRL.ACT": [], "AFE_IBIAS.ACT": [],
                        "CPF_TRIM.ACT": [], "BOOST_TRIM.ACT": [], "CHOP_CFG.ACT": [], "ADC_CFG.ACT": [],
                        "BLANK.ACT": [], "TEST_MUX.ACT": [], "TEST_CTRL.ACT": []}
# the codes the requirements give (REG-01, REG-02, SPI-09, REG-08; audit round 13: a two-bit change of a code, which
# keeps the distance check, passed every check)
FIXED_CODES = {"START": 0x11, "STOP": 0x22, "APPLY": 0x33, "APPLY_NR": 0x44, "FLUSH": 0x55, "SOFT_RESET": 0xA5,
               "TEST_KEY": 0x3C}
# the sample status byte (DAT-02, spec 3.4: VALID, OVERRUN, OVL, CHANGED, ERR, then three zeros)
FIXED_SAMPLE_STATUS = {"VALID": 7, "OVERRUN": 6, "OVL": 5, "CHANGED": 4, "ERR": 3}
# the values a read-only field may return, from the requirements (ID, VERSION and the data window are free; ODR and
# QBITS are checked against fsm_spec.TIMING and the overload rule's codes)
REQUIRED_RO_LEGAL = {"STATE": list(range(9)), "LEVEL": list(range(9)), "FIFO_DEPTH": [4, 8], "CRC": [1], "MARK1": [1],
                     "MARK0": [0], "ALERT": [0, 1], "CMD_PENDING": [0, 1], "READY": [0, 1], "DATA": [0, 1],
                     "OVL_NOW": [0, 1], "AFE_RST": [0, 1]}
# REG-01's regions (stated with these ranges in the requirements): the kind of a register from its fields
# the regions hold their registers' active copies (addr + SHADOW_MIRROR): settings 0x20-0x2F and copies 0x30-0x3F,
# test registers 0x60-0x6F and copies 0x70-0x7F (audit round 12, auditor B: the copies 0x70, 0x71 were in no region)
# (audit round 20, auditor C: one test region 0x60-0x7F let DEBUG sit at 0x72, among the copies): the registers'
# halves here, their copies' halves in COPY_REGIONS
REGIONS = {"status": range(0x00, 0x10), "command": range(0x10, 0x20), "settings": range(0x20, 0x30),
           "data": range(0x40, 0x41), "timers": range(0x50, 0x60), "test": range(0x60, 0x70)}
COPY_REGIONS = {"settings": range(0x30, 0x40), "test": range(0x70, 0x80)}


def region_of(n, acc, lock, fields):
    """REG-01: identification and status (read-only, W1C, and the ALERT masks of that status), the command register
    and the test key, the settings (shadows applied at a tick), the data window, the timers and the interface, the
    test registers (locked)"""
    cls = {f["cls"] for f in fields}
    if lock:
        return "test"
    if n == "SAMPLE":
        return "data"
    if cls & {"cmd"} or n == "TEST_KEY":
        return "command"
    if cls & {"apply"}:
        return "settings"
    if cls <= {"ro", "w1c"} or n.startswith("ALERT_MASK"):
        return "status"
    return "timers"


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
                BLANK_W=blank_w(BLANK_WITH_DAC if dac else ac["BLANK_LEN"]), BLANK_HELD=ac["ADC_ZERO"],
                CHOP_HALF=128 if ac["CHOP_FAST"] else 256,
                CHOP1_HALF=0 if c1 == 0 else FS.TIMING["chop1_periods_frames"][c1 - 1] * FS.FRAME // 2)


def blank_w(length):
    """CHOP_BLANK's width in MCLK for a blanking length: length + 1, and no pulse for 0 (eeg_clkgen; 0 is not legal,
    REG-06; audit round 10: the model gave a 1-MCLK pulse)"""
    return length + 1 if length else 0


def guarded_addrs():
    """Writes refused (STATE_ERR) while a command is pending: the registers with fields applied at the tick (the
    shadows) and the timers, so that no write lands between a command and its tick. Read at the command's tick are
    T_WARM (START; an APPLY or APPLY_NR in WARMUP restarts its count, audit round 21), T_PRE (APPLY) and T_ELEC
    (APPLY_NR: the restart, ALIGN / FILL -> WAIT_E, the mark's length); a
    START's or an APPLY's T_RST, T_REC and T_ELEC are read when each wait starts, after the guard, so the host writes
    them only in IDLE or RUN (5.4 steps 4 and 7; audit round 20, auditor A)."""
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


def crc8(bs, c=0):
    """CRC-8 with the polynomial 0x07 (x^8 + x^2 + x + 1), MSB first, from 0: the SPI's CRC (SPI-05)."""
    for b in bs:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def reg_values(name):
    """Every value a register can read: the product of its fields' legal values (a field without them: every value).
    A field outside the byte is left out: the geometry check reports it (audit round 21, auditor C: it crashed the
    slip model, lsb -1 of T_WARM, VERSION, STATUS.AFE_RST and others)."""
    vals = {0}
    for f in next(r[4] for r in REGS if r[1] == name):
        if not 0 <= f["lsb"] <= f["msb"] <= 7:
            continue
        lg = f["legal"] if f["legal"] is not None else range(1 << (f["msb"] - f["lsb"] + 1))
        vals = {v | (x << f["lsb"]) for v in vals for x in lg}
    return vals


def _skip(x, k):
    """A 32-bit stream, MSB first, with its bit k left out (a 0 shifted in at the end)."""
    return ((x >> (32 - k)) << (32 - k) if k else 0) | ((x & ((1 << (31 - k)) - 1)) << 1)


def _dup(x, k):
    """A 32-bit stream, MSB first, with its bit k repeated (the last bit dropped)."""
    return ((x >> (31 - k)) << (31 - k)) | ((x >> 1) & ((1 << (31 - k)) - 1))


def slip_responses(h_):
    """The byte pairs the chip can send after the header of a 3-byte CRC read when it decoded the header as h_: a read
    of a defined readable register (or an active copy) its value and the CRC of the header and the value; of the
    sample window a valid word's status byte and SEQ's high byte, or an empty word's status byte and 0x00; of a
    write-only or undefined address 0x00 and its CRC; after a write header zeros."""
    if not h_ & 0x80:
        return [(0, 0)]
    a = h_ & 0x7F
    by = {r[0]: r for r in REGS}
    copies = {r[0] + SHADOW_MIRROR: r for r in REGS if any(f["cls"] == "apply" for f in r[4])}
    if a in by and by[a][1] == "SAMPLE":
        bits = {n_: b_ for n_, b_, _d in SAMPLE_STATUS if n_ != "0"}
        flags = [b_ for n_, b_ in bits.items() if n_ != "VALID"]
        empty_flags = [bits[n_] for n_ in ("OVERRUN", "OVL", "ERR") if n_ in bits]
        valid, empty = {1 << bits["VALID"]}, {0}
        for b_ in flags:
            valid |= {v | (1 << b_) for v in valid}
        for b_ in empty_flags:
            empty |= {v | (1 << b_) for v in empty}
        return [(s, q) for s in sorted(valid) for q in range(256)] + [(s, 0) for s in sorted(empty)]
    if a in by and by[a][2] != "WO":
        return [(w, crc8([h_, w])) for w in sorted(reg_values(by[a][1]))]
    if a in copies:
        return [(w, crc8([h_, w])) for w in sorted(reg_values(copies[a][1]))]
    return [(0, crc8([h_, 0]))]


def slip_target(key):
    """A slip target: a register by name (its address and legal values), or NAME.ACT for its active copy (address +
    SHADOW_MIRROR, the same values; audit round 20, auditor B)."""
    name, _, act = key.partition(".")
    r = next(r for r in REGS if r[1] == name)
    if act:
        if act != "ACT" or not any(f["cls"] == "apply" for f in r[4]):
            raise ValueError(f"{key}: not an active copy")
        return r[0] + SHADOW_MIRROR, reg_values(name)
    return r[0], reg_values(name)


def slip_hazards(key):
    """Where one SCLK slip in a 3-byte CRC read gives the host another legal value with a valid CRC and a first byte
    that passes rule (a) (bits 7..6 = 10): (value sent, value read) for a slip after the header, (-1, value read) for
    a slip in the header, where the chip decodes another address (or a write, or the window) and answers for it. key:
    a register's name, or NAME.ACT for its active copy. The four single SCLK faults, k over all 24 pulses: the chip
    misses host pulse k (the host reads bit k twice; the chip skips MOSI bit k); counts an extra pulse in a low phase
    before it (the host skips bit k; the chip reads MOSI bit k twice); sees a bounce inside pulse k's high phase (the
    chip reads MOSI bit k twice; the host skips bit k + 1); or loses the low phase between pulses k and k + 1, which
    merge (the chip skips MOSI bit k + 1; the host reads bit k twice). The last two since audit round 31, auditor B
    (they gave no new pair then; the RTL agreed with this model in 96 bounce and 92 merge frames). A slip in the first byte moves STATUS's bits into what the host takes as the data and decides
    rule (a): every STATUS value 0x80..0xBF is tried there (a missed pulse puts AFE_RST, bit 0, at the top of the data
    byte). Audit round 18, auditor B (the data and CRC bytes); round 19, auditor B (the header, rule (a)); round 20,
    auditor B (every STATUS value, the active copies)."""
    import numpy as np
    addr, vals = slip_target(key)
    h = 0x80 | addr
    t8 = np.array([crc8([x]) for x in range(256)], dtype=np.int64)
    legal = np.zeros(256, dtype=bool)
    legal[[v for v in sorted(vals) if 0 <= v < 256]] = True     # (a field outside the byte is reported elsewhere)
    want_crc = t8[t8[h] ^ np.arange(256)]                # the CRC the host checks for each value it may read
    mosi = h << 24
    out, cache = set(), {}
    kinds = ((lambda k: _skip(mosi, k), lambda x, k: _dup(x, k)),       # a missed pulse k
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k)),       # an extra pulse in a low phase before pulse k
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k + 1)),   # a bounce in pulse k's high phase (round 31)
             (lambda k: _skip(mosi, k + 1), lambda x, k: _dup(x, k)))   # pulses k, k + 1 merged (round 31)
    for ki, (chip, host) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24                                   # the header the chip decoded
            if h_ not in cache:
                cache[h_] = np.array(slip_responses(h_), dtype=np.int64).reshape(-1, 2)
            b1, b2 = cache[h_][:, 0], cache[h_][:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = host((st << 24) | (b1 << 16) | (b2 << 8), k)  # what the host sampled
                d, c = (hs >> 16) & 0xFF, (hs >> 8) & 0xFF
                hit = ((hs >> 30) == 2) & legal[d] & (c == want_crc[d])
                if h_ == h:
                    hit &= d != b1
                out |= {(int(v) if h_ == h else -1, int(x)) for v, x in zip(b1[hit], d[hit])}
    return sorted(out)


# The mode probe of rule (c) and step 9 reads IF_CFG with [0xD5, 0x00, 0x00]: CRC on, the chip answers IF_CFG (bit 0
# set) and its CRC; CRC off, IF_CFG (bit 0 clear) and 0x56's 0x00 (undefined). The CRC-off answer is protected by no
# CRC (audit round 32, auditor B: one SCLK fault of the four kinds made a CRC-on chip decode 0xD2 or 0xD4 and answer as
# CRC off with T_REC 0x30 or T_RST 0x22, both legal; 6 of 285 faulted probes in the RTL. Harmless, as rule (c) acts only
# on two matching probes; never with the reset values, at which step 3 first reads IF_CFG; step 3's rewrite loop
# reads it again under the host's timers, where a misread costs one more loop: audit round 33, auditor B). Audit round
# 33, auditor B: one MOSI flip of the header's address bits as well (bit 0, 0xD4: T_RST 0x22 again; bit 7, R/W, always
# gives the CRC-off form, rule (c)). The pairs the documents record, (register, value):
PROBE_SLIP_RECORDED = {("T_REC", 0x30), ("T_RST", 0x22)}


def probe_slip_hazards():
    """(register, value) pairs with which a CRC-on chip answers the mode probe [0x80 | IF_CFG, 0x00, 0x00] as CRC off
    under one SCLK fault of the four kinds of slip_hazards or one MOSI flip of the header's seven address bits (audit
    round 33, auditor B): STATUS's fixed bits (rule (a)), byte 2 with CRC_EN's bit clear, byte 3 0x00 (audit round 32,
    auditor B). With the header undisturbed the chip answers IF_CFG's CRC-on values
    and their CRC; with another decoded header, slip_responses' pairs; every STATUS value is tried where a fault in the
    first byte moves STATUS's bits (as slip_hazards)."""
    import numpy as np
    h = 0x80 | FIXED_ADDR["IF_CFG"]
    crc_bit = FIXED_BITS["CRC_EN"]
    mosi = h << 24
    names = {0x80 | a: n for a, n, *_ in REGS}
    names.update({0x80 | (a + SHADOW_MIRROR): n + ".ACT" for a, n, _acc, _l, fl, _ in REGS
                  if any(f["cls"] == "apply" for f in fl)})
    own = np.array([(v, crc8([h, v])) for v in sorted(reg_values("IF_CFG")) if v >> crc_bit & 1],
                   dtype=np.int64).reshape(-1, 2)
    kinds = ((lambda k: _skip(mosi, k), lambda x, k: _dup(x, k)),       # a missed pulse k
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k)),       # an extra pulse in a low phase before pulse k
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k + 1)),   # a bounce in pulse k's high phase
             (lambda k: _skip(mosi, k + 1), lambda x, k: _dup(x, k)))   # pulses k, k + 1 merged
    out, cache = set(), {}
    for ki, (chip, host) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24                                   # the header the chip decoded
            if h_ == h:
                pairs = own
            else:
                if h_ not in cache:
                    cache[h_] = np.array(slip_responses(h_), dtype=np.int64).reshape(-1, 2)
                pairs = cache[h_]
            b1, b2 = pairs[:, 0], pairs[:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                hs = host((st << 24) | (b1 << 16) | (b2 << 8), k)  # what the host sampled
                hit = ((hs >> 30) == 2) & (((hs >> (16 + crc_bit)) & 1) == 0) & (((hs >> 8) & 0xFF) == 0)
                out |= {(names.get(h_, f"0x{h_:02X}"), int(v)) for v in b1[hit]}
    for b in range(7):                                   # one MOSI flip of an address bit of the header (audit round
        h_ = h ^ (1 << b)                                # 33, auditor B; bit 7, R/W, always gives the CRC-off form)
        if h_ not in cache:
            cache[h_] = np.array(slip_responses(h_), dtype=np.int64).reshape(-1, 2)
        b1, b2 = cache[h_][:, 0], cache[h_][:, 1]
        hit = (((b1 >> crc_bit) & 1) == 0) & (b2 == 0)    # STATUS unshifted: rule (a) holds
        out |= {(names.get(h_, f"0x{h_:02X}"), int(v)) for v in b1[hit]}
    return sorted(out)


# The values a CRC-off chip can hold besides the reset values: those one fault of the procedure's own CRC-off frames
# leaves (audit round 34, auditor B: round 33's "always the reset values" was false): step 3's first IF_CFG write
# [0x55, 0x01 or 0x03] landing on T_ELEC (0x51), the 0x03 losing data bit 0 (IF_CFG 0x02), step 2's CRC-off SOFT_RESET
# [0x10, 0xA5] landing on T_WARM (0x50: 165), step 9's CRC-off ERR clear landing on CHOP_CFG (0x26: any legal value).
# None: every legal value of the register
PROBE_OFF_REACHABLE = {"T_ELEC": [1, 3], "IF_CFG": [0x02], "T_WARM": [165], "CHOP_CFG": None}


def probe_off_hazards():
    """(register, value) pairs with which a CRC-off chip at its reset values answers the mode probe as CRC on (STATUS's
    fixed bits, byte 2 with CRC_EN's bit set, byte 3 the CRC of the probe's header and byte 2) under one fault: the four
    SCLK kinds and the seven address bits of the header flipped on MOSI. With CRC off the chip reads on: byte 3 is the
    next address's value. The read-only registers that change (STATUS, STATE, FIFO_LEVEL, ERR, DFLAG) take every value;
    the rest their reset values, as a CRC-off chip has them in the procedure: the host writes the timers and the shadows
    only after step 3 turns CRC on, and every way back to CRC off is a reset (audit round 33, auditor B: with T_RST 0x25
    a bit-0 flip read 0xD4's 0x25 and IF_CFG's 0x00 as a CRC-on answer), or the values of PROBE_OFF_REACHABLE, which one
    fault of the procedure's own CRC-off frames leaves (audit round 34, auditor B). Must be empty."""
    import numpy as np
    h = 0x80 | FIXED_ADDR["IF_CFG"]
    crc_bit = FIXED_BITS["CRC_EN"]
    mosi = h << 24
    names = {0x80 | a: n for a, n, *_ in REGS}
    names.update({0x80 | (a + SHADOW_MIRROR): n + ".ACT" for a, n, _acc, _l, fl, _ in REGS
                  if any(f["cls"] == "apply" for f in fl)})
    vals = {}
    for a, n, acc, _l, fl, _ in REGS:
        if acc == "RO" and n != "SAMPLE":
            v = sorted(reg_values(n))
        else:
            v = [sum(f["reset"] << f["lsb"] for f in fl if isinstance(f["reset"], int) and 0 <= f["lsb"] <= f["msb"] <= 7)
                 if acc != "WO" and n != "SAMPLE" else 0]
            if n in PROBE_OFF_REACHABLE:                 # one fault of the CRC-off frames (audit round 34, auditor B)
                more = PROBE_OFF_REACHABLE[n]
                v = sorted(set(v) | set(reg_values(n) if more is None else more))
        vals[a] = v
        if any(f["cls"] == "apply" for f in fl):
            vals[a + SHADOW_MIRROR] = v
    t8 = np.array([crc8([h, x]) for x in range(256)], dtype=np.int64)

    def pairs_of(h_):                                   # (byte 2, byte 3) the chip sends after the header it decoded
        if not h_ & 0x80:
            return np.zeros((1, 2), dtype=np.int64)     # a write: 0x00 after the header
        a = h_ & 0x7F
        return np.array([(x, y) for x in vals.get(a, [0]) for y in vals.get((a + 1) & 0x7F, [0])],
                        dtype=np.int64).reshape(-1, 2)

    def hits(hs, b1):                                   # the host's view of a CRC-on answer
        d = (hs >> 16) & 0xFF
        ok = ((hs >> 30) == 2) & (((d >> crc_bit) & 1) == 1) & (((hs >> 8) & 0xFF) == t8[d])
        return b1[ok]

    kinds = ((lambda k: _skip(mosi, k), lambda x, k: _dup(x, k)),
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k)),
             (lambda k: _dup(mosi, k), lambda x, k: _skip(x, k + 1)),
             (lambda k: _skip(mosi, k + 1), lambda x, k: _dup(x, k)))
    out = set()
    for ki, (chip, host) in enumerate(kinds):
        for k in range(23 if ki == 3 else 24):
            h_ = chip(k) >> 24
            pr = pairs_of(h_)
            b1, b2 = pr[:, 0], pr[:, 1]
            for st in (range(0x80, 0xC0) if k <= 8 else (0x80,)):
                out |= {(names.get(h_, f"0x{h_:02X}"), int(v)) for v in hits(host((st << 24) | (b1 << 16) | (b2 << 8), k), b1)}
    for b in range(7):
        h_ = h ^ (1 << b)
        pr = pairs_of(h_)
        out |= {(names.get(h_, f"0x{h_:02X}"), int(v)) for v in hits((0x80 << 24) | (pr[:, 0] << 16) | (pr[:, 1] << 8), pr[:, 0])}
    return sorted(out)


def _addr_ranges(s):
    """The addresses a text states as "0xAA〜0xBB、0xCC" (audit round 32, auditor B)."""
    out = set()
    for lo, hi in re.findall(r"0x([0-9A-Fa-f]{2})(?:〜0x([0-9A-Fa-f]{2}))?", s):
        out |= set(range(int(lo, 16), int(hi or lo, 16) + 1))
    return out


def window_slip_neighbours():
    """The readable addresses (active copies included) whose CRC read the chip decodes as a read of the sample window
    after one SCLK slip in the header (audit round 19, auditor B: the one-bit neighbours alone missed 0x01 and 0x20)."""
    hdr = smp_hdr()
    readable = ({a for a, n, acc, *_ in REGS if acc != "WO" and n != "SAMPLE"} |
                {a + SHADOW_MIRROR for a, _n, _acc, _l, fl, _ in REGS if any(f["cls"] == "apply" for f in fl)})
    out = set()
    for a in readable:
        m = (0x80 | a) << 24
        if any((_skip(m, k) >> 24) == hdr or (_dup(m, k) >> 24) == hdr for k in range(8)):
            out.add(a)
    return sorted(out)


def smp_hdr():
    """A sample read's header: R/W 1 and the window's address (0xC0 for the window 0x40)."""
    return 0x80 | next(a for a, n, *_ in REGS if n == "SAMPLE")


CHECKS = [
    "アドレスの重なりがない。アクティブの写しのアドレス（＋0x10）が他のレジスタと重ならない",
    "各レジスタのフィールドは 8 ビットに収まり、重ならない（未使用のビットが 0 を返すことは、レジスタ表から生成した試験 tb_top_r14 で確かめる）",
    "既定値はフィールドの幅に収まり、合法な値。推奨の動作値（AFE_IBIAS 3、BOOST_TRIM 4/2、BLANK 7、CHOP_FAST 1、CHOP1 4 kHz、DWA_EN 1）",
    "アナログ側が受ける制御の全て（17 項目）が、ちょうど 1 つのフィールド（apply）かシーケンサ（AFE_RST）から出る。アナログに効く設定に、即時に効くもの（imm）はない（即時の DEBUG の DBG_SEL と RAW_EN は RAW のパッドの試験用の出力で、DBG_SEL 0 と RAW_EN 0 ではアナログに効かない。DBG_SEL 1〜3 と RAW の流れのパッドの結合は評価していない：要件の第 4.10 節。第 29 回、A）",
    "端子の規則（pins_from_active）：OFEN は範囲 r で DAC の群 G0〜G(r−1) を入れる温度計の符号（RANGE_MAX_M の群の構成と一致）、範囲 0 では OFM と OFS を 0、DAC を使うときの CHOP_BLANK は 15 MCLK（フレームの最長のブランキング）。アナログの全ての制御が、この規則のいずれかの端子に対応する。RTL はこの範囲の表と OFEN の表を生成した eeg_regs_defs.svh から使い、tb_top_r14 は同じ規則から生成した端子の試験（build/pin_tests.svh）で端子を確かめる",
    "タイマの最小値と既定値は、tick の格子に切り上げても（フレームの整数で計算）アナログの最小値（fsm_spec.TIMING）以上。タイマの最大値（255 × 単位）は TIMING の最大と一致",
    "未処理の命令がある間に書き込みを止めるレジスタ（GUARDED）は、一括反映のフィールドを持つレジスタとタイマのレジスタに一致",
    "REG-08 の試験の欄（ATP_EN、ATP_SEL、CHOP_STOP、ADC_ZERO、DBG_SEL、RAW_EN）は施錠する TEST_MUX、TEST_CTRL、DEBUG に、IF_CFG の欄（DRDY_MODE、CRC_EN）は IF_CFG にあり、これらのレジスタはほかの欄を持たない（第 29 回、C）",
    "STATE の値は fsm_spec のシーケンサの状態のコードと一致する",
    "STATUS は固定のビット（bit 7 ＝ 1、bit 6 ＝ 0）を持ち、0x00 と 0xFF にならない",
    "命令コードと試験の鍵は互いに、また 0x00、0xFF と 2 ビット以上異なる（1 ビットの誤りで別の命令にならない）",
    "範囲の上限の表を、DAC の群（G0 は M0〜M6、G1〜G3 は M7〜M9）と範囲の公称の電圧（±39／79／159／318 mV、公称 0.311 mV／段）から独立に確かめる。サンプルの窓（0x40）と 1 ビットだけ違う定義済みの読めるアドレス（アクティブの写しを含む。第 17 回）は、ホスト手順が 2 回読む 0x00、0x50、0x60 のみ（第 16 回）。サンプルの読み出しの先頭バイト（SMP_HDR ＝ 0xC0）とその CRC（CRC_SMP_HDR）を窓のアドレスから生成し、RTL、BFM、試験台、照合器はこれを使う。SPI の表の RSMP の文がこの先頭バイトを名指すこと（第 17 回）。ホスト手順が判断に使う CRC 付きの読み出し（STATE、FIFO_LEVEL、DFLAG、IF_CFG、ERR と、手順 4 と共通の規則 (c) の読むアクティブの写しの全て。第 20 回）は、SCLK の 1 回の滑り（取りこぼしか余分な縁）で別の合法な値が CRC を通らない（ERR の 0x66 → 0x67 と、OFF_M_L の写しの 0xAA → 0xAB の 2 組のみ。後者は両方の向きに効き、0xAA が新しい値なら実行済みの命令を未実行と（変化のない出し直し）、古い値なら（上向きの 1 段）実行されなかった命令を実行済みと読ませるので、手順 4 と規則 (c) はアクティブの写しを 2 回続けて同じ値のときのみ使う（第 24 回、第 26 回）。STATUS は 62 組で通るので、手順は READY と DATA を STATUS から判断せず、CMD_PENDING ＝ 0 は真の値が 0 となる命令の 17 フレームのあとの読み出しでのみ受け入れる（0 を 1 とする 16 組の偽りの 1 は読み直す。第 24 回）。第 18 回）。アクティブの写しの全てがこの一覧にあること（第 20 回）。滑りは 3 バイトの全ての 24 パルスで考え、先頭バイトの中の滑りではチップの復号した番地（書き込み、窓、未定義を含む）の応答と、ホストの規則 (a) を入れる。最初のバイトの中の滑りでは STATUS の全ての値（0x80〜0xBF）を入れる（取りこぼしでは STATUS の bit 0（AFE_RST）がホストの受けるデータのバイトの最上位となる。第 20 回）。先頭バイトの滑りでサンプルの窓の読み出しとなる読めるアドレスは 0x00、0x01、0x20、0x50、0x60 のみ（ホストは 0x00、0x50、0x60 を 2 回読み、0x01 は読まない。第 19 回）。サンプルの状態のバイトの表は bit 0〜7 をちょうど 1 回ずつ持つ（予約の 0 の行を含む。第 18 回）",
    "cfg_ok と nr_ok：全ての範囲の上限で境界の値を確かめる（M が上限なら可、上限＋1 なら不可。±1 段は可、±2 段と範囲の変更と他の設定の変更は不可）",
    "過負荷の規則は、フルスケールの行動モデルのコード列（s4、s20）で 1 回も成立しない（誤検出なし）。過負荷の規則（窓、閾値、両端の符号）は要件 FLG-04 と詳細仕様の第 5 節の文と一致し（第 7 回）、両端の符号の集合は RTL へ OVL_EXT_CODES として生成する（第 11 回）",
    "範囲 0 は全ての M を受け付ける。端子の規則（pins_from_active）は、詳細仕様の文から独立に書いた式と、各欄を独立に乱数で選んだ 6,000 通りの設定で一致する（第 7、8 回）。BLANK_LEN ＝ 0 の模型はパルスなし（第 10 回）",
    "既定値と合法な値：書き込み可能な全てのフィールドの既定値と合法な値は、要件から書いた表（REQUIRED_RESET、REQUIRED_LEGAL）と一致する（試験の設定は既定で切、オフセット DAC は範囲 0、タイマは SEQ-02、03、14、AFE_IBIAS の 0〜2 は書き込み可能。第 10、11 回）。リセットのあとの STATUS、STATE、FIFO_LEVEL の値も同じ表による",
    "フィールドとアドレス（第 10 回）：要件の名指す全てのフィールドがあり、ほかの読み出し専用のフィールドはない。ホスト手順の名指すアドレス（FIXED_ADDR：要件と詳細仕様の文の「名（0xNN）」の全てと、ほかの形で名指すもの。第 20 回で FIFO_LEVEL と TEST_MUX、第 29 回で TEST_CTRL、第 31 回で TEST_KEY と DEBUG、第 32 回で守るレジスタの全てを加えた。REG-01 の一覧はこれに等しく、詳細仕様 2.3 と要件の CRC 無効の注記の範囲の文は guarded_addrs() に等しい。第 32 回）と、STATUS の固定のビット、IF_CFG の CRC_EN（bit 0）と DRDY_MODE（bit 1）の位置は変わらない。区画はレジスタとアクティブの写しの半分に分けて確かめる（設定 0x20〜0x2F と写し 0x30〜0x3F、試験 0x60〜0x6F と写し 0x70〜0x7F。第 20 回）。モードの判定のフレームが SCLK の 1 回の故障か先頭のアドレスの 1 ビットの化けで CRC 無効の答えを返す組（" + "、".join(f"{n_} 0x{v_:02X}" for n_, v_ in sorted(PROBE_SLIP_RECORDED)) + "）を記録して確かめ、どれもリセット値でないことを求める（第 32 回。化けは第 33 回）。リセット値と、手順の CRC 無効のフレームの 1 回の故障で残る値（PROBE_OFF_REACHABLE）の CRC 無効のチップが、1 回の故障で CRC 有効の答えに読まれないことも確かめる（第 33 回、第 34 回）。文書の記す滑りの組の数（STATUS " + str(SLIP_COUNTS_RECORDED["STATUS"]) + " 組、T_WARM " + str(SLIP_COUNTS_RECORDED["T_WARM"]) + " 組）を確かめ、要件 5.4 の (b) の文の数とも照合する（第 20、21 回）。手順 3 が書いて 2 回読み戻すレジスタの組の数（" + "、".join(f"{k_} {v_} 組" for k_, v_ in SLIP_COUNTS_RECORDED.items() if k_ not in ("STATUS", "T_WARM") and v_) + "、ほかは 0 組）も記録して確かめ、書き込み可能な全てのレジスタがこの記録か判断に使う一覧にあることを求める（第 27 回）。REG-01 の区画（アクティブの写しも、そのレジスタの区画に。第 12 回）、施錠は試験の区画のみ（REG-08）、書き込み専用は命令と試験の鍵のみ、アクセスと区分の整合、8 ビットを超えるフィールドは連続したアドレスに上位から（REG-04）、0x56 は未定義（手順 9 の判定）",
    "端子の出どころ（第 10 回）：デジタルのみの端子（RAW、DBG_SEL）にも書き込み可能な出どころがちょうど 1 個。ALERT_MASK は ERR の、ALERT_MASK_D は DFLAG の全てのビットを覆う（第 11 回）",
    "コードとビット（第 13 回）：命令のコードと試験の鍵、ERR、DFLAG、STATE、FIFO_LEVEL のビットの位置、サンプルの状態のバイトの並び、読み出し専用のフィールドの値の集合は、要件の値と一致する。ODR は MCLK とデシメーションの出力の速さ、QBITS は量子化器の符号のビット数。端子の欄は、各フィールドを変えて動く端子と一致し、読み出し専用の定数の値は既定値のみ（第 14 回）。STATUS のほかの 6 ビット（ALERT、CMD_PENDING、READY、DATA、OVL_NOW、AFE_RST）の位置、命令のコードと試験の鍵が 1 バイトの全体であること、読み出し専用の定数の読み値の定め、SAMPLE の既定値 0（第 15 回）。STATE の値の文は fsm_spec の状態の表から生成する（第 16 回）",
    "生成のブロック（第 32 回）：詳細仕様の生成のブロック（GEN_KEYS の 5 個）の全てに BEGIN と END の印が 1 個ずつ順にあり、ほかの鍵の印はなく、詳細仕様が読める（gen と fresh は印のないブロックと詳細仕様のない場合を黙って飛ばし、手で直した文を自らと比べていた。二重のブロックも比べなかった）",
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
                continue                                 # (audit round 18, auditor C: lsb -1 crashed the mask)
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
    names_all = {f["name"] for *_, f in all_fields()}
    for nm in sorted((set(REQUIRED_RESET) | REQUIRED_RO) - names_all):
        errs.append(f"{nm}: a field the requirements name is missing from the map")
    for nm in sorted(names_all - set(REQUIRED_RESET) - REQUIRED_RO):
        if next(f for *_, f in all_fields() if f["name"] == nm)["cls"] == "ro":
            errs.append(f"{nm}: a read-only field the requirements do not name")
    for a, n, acc, lock, fields, _ in REGS:              # audit round 10: addresses, bits, regions, locks, write-only
        if n in FIXED_ADDR and a != FIXED_ADDR[n]:
            errs.append(f"{n} at 0x{a:02X}: the host procedure names it at 0x{FIXED_ADDR[n]:02X}")
        rg = region_of(n, acc, lock, fields)
        if a not in REGIONS[rg]:
            errs.append(f"{n} at 0x{a:02X}: outside the {rg} region of REG-01 (0x{REGIONS[rg][0]:02X}-0x{REGIONS[rg][-1]:02X})")
        if bool(lock) != (a in REGIONS["test"]):
            errs.append(f"{n}: lock {lock} at 0x{a:02X} (REG-08: exactly the registers of the test region are locked)")
        if any(f["cls"] == "apply" for f in fields) and a + SHADOW_MIRROR not in COPY_REGIONS.get(rg, ()):
            errs.append(f"{n}: active copy 0x{a + SHADOW_MIRROR:02X} outside its register's {rg} region (REG-01)")
        if (acc == "WO") != (n in ("COMMAND", "TEST_KEY")):
            errs.append(f"{n}: access {acc}; only the command register and the test key are write-only")
    where_ = {f["name"]: n for _, n, _, _, fields, _ in REGS for f in fields}   # REG-08 and IF_CFG (audit round 29)
    for fn_, rn_ in sorted(FIELD_REGISTER_REQUIRED.items()):
        if where_.get(fn_, rn_) != rn_:
            errs.append(f"{fn_} is in {where_[fn_]}, while the requirements name its register {rn_} (REG-08, IF_CFG; "
                        f"audit round 29)")
    for _, n, _, lock, fields, _ in REGS:
        if lock or n in set(FIELD_REGISTER_REQUIRED.values()):
            for f in fields:
                if FIELD_REGISTER_REQUIRED.get(f["name"]) != n:
                    errs.append(f"{n} holds {f['name']}, a field the requirements do not put there (REG-08 locks only "
                                f"the test fields; IF_CFG holds DRDY_MODE and CRC_EN; audit round 29)")
        for f in fields:
            if (f["cls"] == "cmd") != (n == "COMMAND"):
                errs.append(f"{n}.{f['name']}: class {f['cls']}; the class cmd is the command register's alone")
            if f["name"] in FIXED_BITS and f["lsb"] != FIXED_BITS[f["name"]]:
                errs.append(f"{n}.{f['name']}: at bit {f['lsb']}, the requirements read it at bit {FIXED_BITS[f['name']]}")
    for a, n, acc, lock, fields, _ in REGS:              # audit round 10: every writable reset as the requirements give
        for f in fields:
            if f["cls"] not in ACCESS_CLASSES.get(acc, ()):
                errs.append(f"{n}.{f['name']}: access {acc} with class {f['cls']} (RO: ro; W1C: w1c; RW: apply or imm; "
                            f"WO: cmd or imm)")
            if f["cls"] == "ro":
                if f["name"] in REQUIRED_RESET and f["reset"] != REQUIRED_RESET[f["name"]]:
                    errs.append(f"{n}.{f['name']}: reads {f['reset']} after a reset, where the requirements give "
                                f"{REQUIRED_RESET[f['name']]} (read-only, REQUIRED_RESET)")
                continue
            if f["name"] not in REQUIRED_RESET:
                errs.append(f"{n}.{f['name']}: a writable field without a reset value stated from the requirements "
                            f"(REQUIRED_RESET)")
            elif f["reset"] != REQUIRED_RESET[f["name"]]:
                errs.append(f"{n}.{f['name']}: reset value {f['reset']}, but the requirements give "
                            f"{REQUIRED_RESET[f['name']]} (REQUIRED_RESET)")
            if f["name"] not in REQUIRED_LEGAL:
                errs.append(f"{n}.{f['name']}: a writable field without legal values stated from the requirements "
                            f"(REQUIRED_LEGAL)")
            elif f["legal"] != REQUIRED_LEGAL[f["name"]]:
                lg = f["legal"]
                errs.append(f"{n}.{f['name']}: legal values "
                            f"{lg if lg is None or len(lg) < 6 else f'{min(lg)}..{max(lg)} ({len(lg)})'}"
                            f" differ from those the requirements give (REQUIRED_LEGAL)")
            for v in map(int, re.findall(r"(\d+) は RANGE_ERR", f["desc"])):
                if f["legal"] is not None and v in f["legal"]:
                    errs.append(f"{n}.{f['name']}: {v} is legal, but the field's text says {v} gives RANGE_ERR")
    fd = {f["name"]: f for *_, f in all_fields()}
    if 0 in (fd["BLANK_LEN"]["legal"] or []):
        errs.append("BLANK_LEN 0 is legal (REG-06: it must give RANGE_ERR; CDA and CDB would overlap at the edges)")
    if sorted(fd["RANGE"]["legal"] or []) != sorted(RANGE_MAX_M):   # (None: audit round 17, the check crashed)
        errs.append(f"OFF_CTRL.RANGE legal {fd['RANGE']['legal']}, but the ranges of RANGE_MAX_M are {sorted(RANGE_MAX_M)}")
    if sorted(fd["SIGN"]["legal"] or []) != [0, 1]:
        errs.append(f"OFF_CTRL.SIGN legal {fd['SIGN']['legal']}: the offset needs both signs")
    if not (fd["M_H"]["legal"] == list(range(1 << (fd["M_H"]["msb"] - fd["M_H"]["lsb"] + 1))) and
            fd["M_L"]["legal"] == list(range(256)) and
            max(fd["M_H"]["legal"]) * 256 + max(fd["M_L"]["legal"]) >= max(RANGE_MAX_M.values())):
        errs.append(f"M: the legal values of M_H and M_L do not reach every M up to {max(RANGE_MAX_M.values())}")
    regs_by = {n: a for a, n, *_ in REGS}
    for n in regs_by:                                    # REG-04: over 8 bits, consecutive addresses, the high byte first
        if n.endswith("_H") and n[:-2] + "_L" in regs_by and regs_by[n[:-2] + "_L"] != regs_by[n] + 1:
            errs.append(f"{n} and {n[:-2]}_L: a field over 8 bits not at consecutive addresses, the high byte first (REG-04)")
    fbits = lambda rn: {b for a_, n_, *_r, fl, _d in [r for r in REGS if r[1] == rn] for f in fl
                        for b in range(f["lsb"], f["msb"] + 1)}
    for mk, fl in MASKS.items():                         # audit round 11: a flag its mask cannot mask
        if mk in regs_by and fl in regs_by and not fbits(fl) <= fbits(mk):
            errs.append(f"{mk} does not cover {fl}'s bits {sorted(fbits(fl) - fbits(mk))} (a flag that no mask bit masks)")
    if 0x56 in regs_by.values():
        errs.append("address 0x56 is defined: step 9's mode probe reads it, after IF_CFG, as undefined (0x00)")
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
    for pin in sorted(DIGITAL_ONLY):                   # audit round 10: one writable source each, as the analog ones
        s_ = src.get(pin, [])
        if len(s_) != 1 or s_[0][2] == "ro":
            errs.append(f"{pin}: sources {s_} (a digital-only control needs exactly one, writable)")
    # timers against the analog minimums (fsm_spec.TIMING) on both tick grids
    unit = {"T_REC": 8, "T_PRE": 8, "T_RST": 8, "T_WARM": 1024, "T_ELEC": 1024}   # frames per register step
    frame_s = FS.FRAME / FS.MCLK
    for tn, u in unit.items():
        f = next(f for *_, f in all_fields() if f["name"] == tn)
        mn, df, mx = FS.TIMING["timers"][tn]
        if f["legal"] is None:                         # REQUIRED_LEGAL reports it (audit round 17: it crashed here)
            continue
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
    if sorted(st["legal"] or []) != codes or max(codes) >= 1 << (st["msb"] - st["lsb"] + 1):   # (None crashed: round 18)
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
    # the pin rules are defined for the requirements' values only (audit round 17, auditor C: a legal list None, or
    # CHOP1_RATE 6 or 7 as a legal or reset value, made this check crash instead of reporting)
    pin_names = ("M_H", "M_L", "SIGN", "RANGE", "AFE_IBIAS", "CPF_TRIM", "BTRIM_P", "BTRIM_N", "CHOP_FAST",
                 "CHOP1_RATE", "DWA_EN", "BLANK_LEN", "ATP_EN", "ATP_SEL", "CHOP_STOP", "ADC_ZERO", "DBG_SEL")
    out_dom = [n_ for n_ in pin_names if n_ in fd and (fd[n_]["legal"] is None or
               not set(fd[n_]["legal"]) <= set(REQUIRED_LEGAL.get(n_, ())) or
               fd[n_]["reset"] not in REQUIRED_LEGAL.get(n_, ()))]
    if out_dom:
        errs.append(f"the pin rules not derived from the map: {out_dom} hold values the requirements do not give "
                    f"(REQUIRED_LEGAL), for which pins_from_active is not defined")
    for k_ in range(0 if out_dom else 6000):          # each field drawn on its own (audit round 8)
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
                   BLANK_W=len([31] + list(range(win))) if win else 0, BLANK_HELD=az,
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
    # audit round 14, auditor C: the pin column against the pins the field drives (toggled through pins_from_active,
    # TEST_CFG bit by bit; a swap of SIGN and RANGE, of the trims, of ATP_EN and ADC_ZERO, or a W1C flag listed as
    # driving TEST_CFG[7:6], passed); the read-only constants hold their reset value only
    base = {f["name"]: f["reset"] for *_r, fl_, _d in REGS for f in fl_}
    tcfg = {"TEST_CFG[3:0]": range(0, 4), "TEST_CFG[4]": range(4, 5), "TEST_CFG[5]": range(5, 6), "TEST_CFG[7:6]": range(6, 8)}
    for a_, n_, acc_, _l, fl_, _ in ([] if out_dom else REGS):
        for f in fl_:
            if not f["pin"] or f["pin"] not in set(PIN_OF_CONTROL) | set(tcfg):
                continue                               # RAW_DATA／RAW_CLK: not in pins_from_active
            moved, moved_bits = set(), {}
            for rng_ in (0, 4):                        # the DAC off and on (BLANK_LEN acts with it off, M and S with it on)
                b0 = dict(base, RANGE=rng_)
                other = next((v for v in (f["legal"] or [b0.get(f["name"], 0) ^ 1]) if v != b0.get(f["name"])), None)
                if other is None or f["name"] not in b0:
                    continue
                try:
                    p0, p1 = pins_from_active(b0), pins_from_active(dict(b0, **{f["name"]: other}))
                except KeyError:
                    continue
                for k in p0:
                    if isinstance(p0[k], int) and isinstance(p1[k], int) and p0[k] != p1[k]:
                        moved_bits.setdefault(k, set()).update(i for i in range(16) if (p0[k] >> i & 1) != (p1[k] >> i & 1))
                    if p0[k] != p1[k]:
                        if k == "TEST_CFG":
                            moved |= {lb for lb, bits in tcfg.items() if any((p0[k] >> i & 1) != (p1[k] >> i & 1) for i in bits)}
                        else:
                            moved.add(k)
            want = {f["pin"]} if f["pin"] in tcfg else {PIN_OF_CONTROL[f["pin"]]}
            if not want <= moved:
                errs.append(f"{n_}.{f['name']}: listed as driving {f['pin']}, but changing it moves {sorted(moved) or 'no pin'} "
                            f"(pins_from_active)")
            mb_ = re.fullmatch(r"([A-Z_0-9]+)\[(\d+)(?::(\d+))?\]", f["pin"])   # audit round 21, auditor C: the bit
            if mb_ and mb_.group(1) != "TEST_CFG":                           # split too (M_H and M_L's OFM ranges
                pin_ = mb_.group(1)                                             # swapped passed: OFM moved either way)
                hi_, lo_ = int(mb_.group(2)), int(mb_.group(3) or mb_.group(2))
                bits_ = moved_bits.get(pin_, set())
                if not bits_ or not bits_ <= set(range(lo_, hi_ + 1)):
                    errs.append(f"{n_}.{f['name']}: the pin column gives {f['pin']}, yet a change of the field toggles "
                                f"bits {sorted(bits_)} of {pin_} (pins_from_active, the bit split; audit round 21)")
    for a_, n_, acc_, _l, fl_, _ in REGS:
        for f in fl_:
            if (f["cls"] == "ro" and f["legal"] is not None and f["name"] not in REQUIRED_RO_LEGAL and f["name"] != "SAMPLE"
                    and f["legal"] != [f["reset"]]):
                errs.append(f"{n_}.{f['name']}: read-only constant values {f['legal']}, not its reset value alone")
    # audit round 13, auditor C: the codes, the sample status bits, the read-only values, ODR and QBITS
    for c_, v_ in sorted(FIXED_CODES.items()):
        got = TEST_KEY if c_ == "TEST_KEY" else COMMANDS.get(c_)
        if got != v_:
            errs.append(f"code {c_} {got if got is None else f'0x{got:02X}'}: the requirements fix it at 0x{v_:02X} "
                        f"(REG-02, REG-08, SPI-09)")
    for n_, b_, _d in SAMPLE_STATUS:
        if n_ in FIXED_SAMPLE_STATUS and b_ != FIXED_SAMPLE_STATUS[n_]:
            errs.append(f"sample status {n_} at bit {b_}; DAT-02 orders the byte VALID, OVERRUN, OVL, CHANGED, ERR "
                        f"(bit {FIXED_SAMPLE_STATUS[n_]})")
    if sorted(b_ for _n, b_, _d in SAMPLE_STATUS) != list(range(8)):   # audit round 18, auditor C: the reserved rows
        errs.append(f"sample status bits {sorted(b_ for _n, b_, _d in SAMPLE_STATUS)}: each of the bits 0..7 must be listed "
                    f"exactly once (the generated table showed one bit twice and none for another)")
    if sorted(n_ for n_, *_ in SAMPLE_STATUS if n_ in FIXED_SAMPLE_STATUS) != sorted(FIXED_SAMPLE_STATUS):
        errs.append("sample status: a bit DAT-02 names is missing")
    for a_, n_, acc_, _l, fl_, _ in REGS:
        for f in fl_:
            if f["cls"] == "ro" and f["name"] in REQUIRED_RO_LEGAL and f["legal"] != REQUIRED_RO_LEGAL[f["name"]]:
                errs.append(f"{n_}.{f['name']}: read values {f['legal']} are not the ones the requirements give "
                            f"(REQUIRED_RO_LEGAL)")
    fv = {f["name"]: f["reset"] for *_r, fl_, _d in REGS for f in fl_}
    odr = (fv.get("ODR_H", 0) << 8) | fv.get("ODR_L", 0)
    odr_t = round(FS.MCLK / FS.FRAME / FS.TIMING["decimation"])
    if odr != odr_t:
        errs.append(f"ODR {odr} SPS in ODR_H, ODR_L; fsm_spec.TIMING outputs {odr_t} SPS (MCLK / frame / decimation)")
    for a_, n_, acc_, _l, fl_, _ in REGS:               # audit round 15, auditor C: whole bytes, read values, the window
        for f in fl_:
            if f["name"] in WHOLE_BYTE and (f["msb"], f["lsb"]) != (7, 0):
                errs.append(f"{n_}.{f['name']}: bits {f['msb']}:{f['lsb']}; the requirements compare the whole byte "
                            f"(REG-02, SPI-09, REG-08: the command codes and the test key)")
            if f["cls"] == "ro" and n_ != "SAMPLE" and f["legal"] is None:
                errs.append(f"{n_}.{f['name']}: a read-only field without its read values (legal None)")
            if n_ == "SAMPLE" and f["reset"] != 0:
                errs.append(f"SAMPLE.{f['name']}: reset {f['reset']}; the window reads 0x00 inside a burst and alone "
                            f"(spec 3.2), so the map holds 0 for it")
    win = next(a_ for a_, n_, *_ in REGS if n_ == "SAMPLE")
    readable = ({a_ for a_, n_, acc_, *_ in REGS if acc_ != "WO" and n_ != "SAMPLE"} |   # the active copies are
                {a_ + SHADOW_MIRROR for a_, _n, _acc, _l, fl_, _ in REGS        # readable too (audit round 17, B)
                 if any(f["cls"] == "apply" for f in fl_)})
    nb = sorted(a_ for a_ in readable if bin(a_ ^ win).count("1") == 1)
    if nb != WINDOW_NEIGHBOURS_REQUIRED:
        errs.append(f"readable addresses one bit from the sample window: {[hex(x) for x in nb]}; the host procedure "
                    f"confirms {[hex(x) for x in WINDOW_NEIGHBOURS_REQUIRED]} by a second read (5.4 (b), audit round 16)")
    copies_ = {f"{rg_[1]}.ACT" for rg_ in REGS if any(f_["cls"] == "apply" for f_ in rg_[4])}
    if not copies_ <= set(SLIP_DECIDE_REQUIRED):        # audit round 20, auditor B: the active copies too
        errs.append(f"active copies without a slip check: {sorted(copies_ - set(SLIP_DECIDE_REQUIRED))} (step 4 "
                    f"confirms APPLY and APPLY_NR by the active copies and rule (c) compares them; audit round 20)")
    for n_, want_ in SLIP_DECIDE_REQUIRED.items():      # audit round 18, auditor B: SCLK slips
        try:
            got_ = slip_hazards(n_)
        except (StopIteration, ValueError):
            errs.append(f"{n_}: in the slip list, but neither a register nor an active copy (audit round 20)")
            continue
        if got_ != want_:
            errs.append(f"{n_}: one SCLK slip in its CRC read gives another legal value with a valid CRC for the pairs "
                        f"{[(hex(a_), hex(b_)) for a_, b_ in got_[:4]]}, where the host procedure decides from it "
                        f"(tolerated: {want_}; 5.4 (b))")
    wsn = window_slip_neighbours()
    if wsn != WINDOW_SLIP_NEIGHBOURS_REQUIRED:
        errs.append(f"readable addresses a single SCLK slip in the header turns into a sample read: {[hex(x) for x in wsn]}; "
                    f"the host procedure accounts for {[hex(x) for x in WINDOW_SLIP_NEIGHBOURS_REQUIRED]} (5.4 (b), audit round 19)")
    try:                                                # audit round 21, auditor C: the counts the requirements
        req_txt_ = open(REQ_DOC, encoding="utf-8").read()   # state (5.4 (b)) against the record
    except OSError:
        req_txt_ = None                                 # (reported by the overload rule's comparison)
    for n_, pat_ in SLIP_COUNT_PATTERNS.items():
        if req_txt_ is None:
            break
        got_ = [int(x) for x in re.findall(pat_, req_txt_)]
        if not got_ or any(g_ != SLIP_COUNTS_RECORDED.get(n_) for g_ in got_):
            errs.append(f"{os.path.basename(REQ_DOC)} states {got_} slip pairs for {n_}, SLIP_COUNTS_RECORDED holds "
                        f"{SLIP_COUNTS_RECORDED.get(n_)} (5.4 (b), the record the model is held to; audit round 21)")
    for n_, want_ in SLIP_COUNTS_RECORDED.items():
        got_ = len(slip_hazards(n_))
        if got_ != want_:
            errs.append(f"{n_}: {got_} slip pairs read as another legal value with a valid CRC, while the documents "
                        f"record {want_} (5.4 (b); audit round 20)")
    gp_ = []                                            # the spec's generated blocks (audit round 32, auditor C)
    try:
        with open(DOC, encoding="utf-8") as f_:
            dtxt_ = f_.read()
    except OSError as ex_:
        dtxt_ = None
        gp_.append(f"unreadable ({ex_})")
    if dtxt_ is not None:
        for k_ in sorted(set(re.findall(r"<!-- (?:BEGIN|END) GENERATED (\S+) -->", dtxt_)) - set(GEN_KEYS)):
            gp_.append(f"a marker of {k_!r}, which generate() does not write")
        for k_ in GEN_KEYS:
            a_, b_ = f"<!-- BEGIN GENERATED {k_} -->", f"<!-- END GENERATED {k_} -->"
            na_, nb_ = dtxt_.count(a_), dtxt_.count(b_)
            if na_ != 1 or nb_ != 1 or dtxt_.index(a_) > dtxt_.index(b_):
                gp_.append(f"{k_}: {na_} BEGIN and {nb_} END markers" + (" (END first)" if na_ == nb_ == 1 else ""))
    if gp_:
        errs.append(f"{os.path.basename(DOC)}'s generated blocks: {'; '.join(gp_)} (every block of the spec with its BEGIN "
                    f"and END markers once each and in order, no other block, the spec readable: generate() and fresh() "
                    f"skipped a block without its markers and a missing spec; audit round 32, auditor C)")
    ph_ = set(probe_slip_hazards())                     # the mode probe (audit round 32, auditor B)
    if ph_ != PROBE_SLIP_RECORDED:
        errs.append(f"the mode probe reads as CRC off under one fault (SCLK or a header bit) for {sorted(ph_)}, while the "
                    f"documents record "
                    f"{sorted(PROBE_SLIP_RECORDED)} (rule (c), step 9; audit round 32, auditor B)")
    rst_ = {n_: sum(f_["reset"] << f_["lsb"] for f_ in fl_ if isinstance(f_["reset"], int) and 0 <= f_["lsb"] <= f_["msb"] <= 7)
            for _a, n_, _acc, _l, fl_, _ in REGS}
    for n_, v_ in sorted(ph_):
        if rst_.get(n_.partition(".")[0]) == v_:
            errs.append(f"the mode probe reads as CRC off under one fault (SCLK or a header bit) at the reset value "
                        f"0x{v_:02X} of {n_} (step 3 first reads IF_CFG at the reset values; audit rounds 32, 33)")
    po_ = probe_off_hazards()                           # the other way round (audit round 33, auditor B)
    if po_:
        errs.append(f"a CRC-off chip at its reset values answers the mode probe as CRC on under one fault for {po_} "
                    f"(rule (c): the procedure writes the timers and the shadows only with CRC on; audit round 33, auditor B)")
    try:                                                # REG-01's list of the procedure's addresses (round 32, B)
        m_ = re.search(r"ホスト手順が名指すアドレス（([^）]*?)。第 20 回", open(REQ_DOC, encoding="utf-8").read())
        reg01_ = {n_: int(a_, 16) for n_, a_ in re.findall(r"([A-Z][A-Z0-9_]*) 0x([0-9A-F]{2})", m_.group(1))} if m_ else {}
        if reg01_ != FIXED_ADDR:
            errs.append(f"REG-01 lists the host procedure's addresses {sorted(reg01_.items())}, which differ from "
                        f"FIXED_ADDR {sorted(FIXED_ADDR.items())} (audit round 32, auditor B: rounds 29 and 31 added to one only)")
    except OSError:
        pass                                            # (reported by the overload rule's comparison)
    guard_ = set(guarded_addrs())                       # the guarded set as the documents state it (round 32, B)
    timers_ = {a_ for a_, n_, *_ in REGS if a_ in guard_ and n_.startswith("T_")}
    locked_ = {a_ for a_, _n, _acc, l_, *_ in REGS if l_}
    for path_, pat_, want_ in ((DOC, r"シャドウ（一括反映の対象：([^）]*)）とタイマ（([^）]*)）", (guard_ - timers_, timers_)),
                               (REQ_DOC, r"全てのシャドウ（([^）]*)）と全てのタイマ（([^）]*)）", (guard_ - timers_ - locked_, timers_))):
        try:
            hits_ = re.findall(pat_, open(path_, encoding="utf-8").read()) or [("", "")]
        except OSError:
            continue                                    # (reported by the overload rule's comparison)
        for sh_, tm_ in hits_:
            if (_addr_ranges(sh_), _addr_ranges(tm_)) != want_:
                errs.append(f"{os.path.basename(path_)} states the guarded shadows {sh_!r} and timers {tm_!r}, while "
                            f"guarded_addrs() gives {[hex(x) for x in sorted(want_[0])]} and {[hex(x) for x in sorted(want_[1])]} "
                            f"(the spec's 2.3 and the requirements' CRC-off note state the guarded set by ranges; audit round 32, auditor B)")
    rw_ = {rg_[1] for rg_ in REGS if rg_[2] == "RW"}
    unrec_ = sorted(rw_ - set(SLIP_COUNTS_RECORDED) - set(SLIP_DECIDE_REQUIRED))
    if unrec_:
        errs.append(f"writable registers without a recorded slip count: {unrec_} (step 3 reads every register it "
                    f"wrote back twice; audit round 27, auditor B)")
    notes.append(f"STATUS: {len(slip_hazards('STATUS'))} slip pairs read as another legal value with a valid CRC "
                 f"(the host decides READY, DATA and CMD_PENDING otherwise); T_WARM: {len(slip_hazards('T_WARM'))} "
                 f"(read twice)")
    names_ = {n_ for _a, n_, *_ in REGS}                 # audit round 20, auditor C: every address the documents
    named_ = set()                                      # name for a register is held by FIXED_ADDR
    for path_ in (REQ_DOC, DOC):
        try:
            txt_ = open(path_, encoding="utf-8").read()
        except OSError:
            continue                                    # (reported by the overload rule's comparison)
        for m_ in re.finditer(r"([A-Z][A-Z0-9_]*)（0x([0-9A-Fa-f]{2})）", txt_):
            if m_.group(1) in names_:
                named_.add((os.path.basename(path_), m_.group(1), int(m_.group(2), 16)))
    for doc_, nm_, ad_ in sorted(named_):
        if FIXED_ADDR.get(nm_) != ad_:
            errs.append(f"{doc_} names {nm_} at 0x{ad_:02X}, which FIXED_ADDR does not hold (the host relies on the "
                        f"addresses the documents name; audit round 20)")
    rsmp = next(x[5] for x in FS.SPI_STATES if x[0] == "RSMP")      # the SPI table's text names the header
    if f"先頭バイト 0x{0x80 | win:02X}" not in rsmp:                    # (audit round 17, auditor B)
        errs.append(f"the SPI table's RSMP text (fsm_spec.SPI_STATES) does not name the sample read's header "
                    f"0x{0x80 | win:02X}, which the RTL and the benches take from SMP_HDR")
    q_t = max(OVL_RULE["codes"]).bit_length()
    if fv.get("QBITS") != q_t:
        errs.append(f"QBITS {fv.get('QBITS')}; the quantizer's codes 0..{max(OVL_RULE['codes'])} take {q_t} bits")
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
    pos = 1                                            # the sample frame's bytes after its header (SPI-07,
    for ident, _lab, nb in FS.SAMPLE_BYTES:            # fsm_spec.SAMPLE_BYTES; audit round 15: the bench decodes a
        out.append(f"    localparam int SMP_BYTE_{ident} = {pos};")   # sample by these, the diagram draws them)
        pos += nb
    out.append(f"    localparam int SMP_FRAME_LEN = {pos};")
    # the sample read's header and the CRC it starts the sample's CRC with (audit round 17, auditor B: the RTL, the
    # BFM, the benches and the trace checker had 0xC0 and 0x4E by hand, so a move of the window (item 258) would
    # have left them behind)
    out.append(f"    localparam logic [7:0] SMP_HDR = 8'h{smp_hdr():02X};   // R/W 1 and the window's address")
    out.append(f"    localparam logic [7:0] CRC_SMP_HDR = 8'h{crc8([smp_hdr()]):02X};   // CRC-8 of SMP_HDR: a sample's "
               f"CRC starts from it (SPI-07)")
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
    mask = sum(1 << c for c in OVL_RULE["codes"])      # FLG-04's extreme codes (audit round 11: the RTL had them by hand)
    out.append(f"    localparam logic [31:0] OVL_EXT_CODES = 32'h{mask:08X};   // bit c: the quantizer code c is extreme")
    # the sequencer's tick (fsm_spec.TIMING; audit round 13, auditor A: eeg_clkgen and the benches wrote it by hand, so
    # an edit of TIMING moved the analog decks' events (VER-07, the APPLY_NR carry runs) and not the chip). eeg_clkgen
    # decodes the frame of the chopper period from its counter: cnt[7:5] at 128 kHz (8 frames), cnt[8:5] at 64 kHz (16)
    rt = FS.TIMING["rates"]
    assert rt["128k"]["period_frames"] == 8 and rt["64k"]["period_frames"] == 16, "eeg_clkgen's counter fields"
    out.append(f"    localparam logic [4:0] TICK_CYCLE = 5'd{FS.TIMING['tick_cycle']};"
               f"  localparam logic [2:0] TICK_FRAME_128K = 3'd{rt['128k']['tick_frame']};"
               f"  localparam logic [3:0] TICK_FRAME_64K = 4'd{rt['64k']['tick_frame']};")
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


# The spec's generated blocks, by key (audit round 32, auditor C): generate() writes exactly these, and check()
# requires each key's markers once and in order, and no other key's
GEN_KEYS = ("reg_summary", "reg_fields", "commands", "sample_status", "reg_checks")


def generate(write=True):
    """Writes the package, the defs and the document's generated blocks; write=False returns them ({path: text})."""
    if check(verbose=write):
        print("not generating: fix the violations first")
        return 1
    out = {PKG: sv_package(), DEFS: sv_defs()}
    blocks = dict(zip(("reg_summary", "reg_fields", "commands", "sample_status"), md_tables()))
    blocks["reg_checks"] = "\n".join(f"- {c}" for c in CHECKS)
    if set(blocks) != set(GEN_KEYS):                    # audit round 32, auditor C: the keys check() holds
        print(f"not generating: the blocks {sorted(blocks)} differ from GEN_KEYS {sorted(GEN_KEYS)}")
        return 1
    with open(DOC, encoding="utf-8") as f:              # (check() above: readable, each marker once, in order)
        doc = f.read()
    for k, v in blocks.items():
        a, b = f"<!-- BEGIN GENERATED {k} -->", f"<!-- END GENERATED {k} -->"
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
    import shutil
    import tempfile
    g = globals()
    keep = {k: copy.deepcopy(g[k]) for k in ("REGS", "COMMANDS", "RANGE_MAX_M", "OVL_RULE", "TEST_KEY", "SAMPLE_STATUS", "PIN_OF_CONTROL", "SLIP_DECIDE_REQUIRED", "PROBE_SLIP_RECORDED", "PROBE_OFF_REACHABLE",
                                             "BLANK_WITH_DAC", "REQ_DOC", "DOC", "HERE", "FULLSCALE_SHA256",
                                             "FIXED_ADDR", "SLIP_COUNTS_RECORDED", "SLIP_COUNT_PATTERNS")}
    keep_fn = {"nr_ok": nr_ok, "cfg_ok": cfg_ok, "pins_from_active": pins_from_active, "guarded_addrs": guarded_addrs,
               "ofen_of_range": ofen_of_range}
    tmp = tempfile.mkdtemp()
    req_slip9 = os.path.join(tmp, "req_slip9.md")      # audit round 21, auditor C: the requirements' T_WARM count
    with open(req_slip9, "w", encoding="utf-8") as fo:   # as round 19 recorded it
        fo.write(open(REQ_DOC, encoding="utf-8").read().replace("T_WARM は 17 組", "T_WARM は 9 組"))
    no_rule = os.path.join(tmp, "no_rule.md")
    with open(no_rule, "w", encoding="utf-8") as fo:
        fo.write("過負荷の規則の文のない文書\n")
    spec_nomark = os.path.join(tmp, "spec_nomark.md")    # audit round 32, auditor C: a generated block's marker gone
    with open(spec_nomark, "w", encoding="utf-8") as fo:
        fo.write(open(DOC, encoding="utf-8").read().replace("<!-- END GENERATED reg_fields -->", "", 1))
    spec_unknown = os.path.join(tmp, "spec_unknown.md")  # audit round 33, auditor C: a key no generator writes
    with open(spec_unknown, "w", encoding="utf-8") as fo:
        fo.write(open(DOC, encoding="utf-8").read() + "\n<!-- BEGIN GENERATED reg_old -->\n手で書いた表\n<!-- END GENERATED reg_old -->\n")
    spec_order = os.path.join(tmp, "spec_order.md")      # and a block's END before its BEGIN
    with open(spec_order, "w", encoding="utf-8") as fo:
        fo.write(open(DOC, encoding="utf-8").read().replace("<!-- BEGIN GENERATED commands -->", "\x00").replace(
            "<!-- END GENERATED commands -->", "<!-- BEGIN GENERATED commands -->").replace("\x00", "<!-- END GENERATED commands -->"))
    spec_double = os.path.join(tmp, "spec_double.md")    # and a block doubled
    with open(spec_double, "w", encoding="utf-8") as fo:
        fo.write(open(DOC, encoding="utf-8").read() + "\n<!-- BEGIN GENERATED commands -->\n<!-- END GENERATED commands -->\n")

    req_codes30 = os.path.join(tmp, "req_codes30.md")  # audit round 34, auditor C: FLG-04's codes alone
    with open(req_codes30, "w", encoding="utf-8") as fo:
        fo.write(open(REQ_DOC, encoding="utf-8").read().replace("両端（0 または 31）", "両端（0 または 30）", 1))
    req_slip_unread = os.path.join(tmp, "req_slip_unread.md")   # and a T_WARM count the pattern no longer reads
    with open(req_slip_unread, "w", encoding="utf-8") as fo:
        fo.write(open(REQ_DOC, encoding="utf-8").read().replace("T_WARM は 17 組", "T_WARM は 17 個の組", 1))

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

    # audit round 10, auditor C: the reset values and field rules
    def m_chopstop_reset():
        fld("TEST_CTRL", "CHOP_STOP")["reset"] = 1

    def m_adczero_reset():
        fld("TEST_CTRL", "ADC_ZERO")["reset"] = 1

    def m_no_default():
        next(r for r in g["REGS"] if r[1] == "IF_CFG")[4].append(F("NEW_BIT", 2, 2, 0, [0, 1], "imm", "x"))

    def m_access_class():
        fld("ALERT_MASK", "ALERT_MASK")["cls"] = "ro"

    def m_range_legal():
        fld("OFF_CTRL", "RANGE")["legal"] = rng(0, 5)

    def m_sign_legal():
        fld("OFF_CTRL", "SIGN")["legal"] = [0]

    def m_mh_legal():
        fld("OFF_M_H", "M_H")["legal"] = [0, 1, 2]

    def m_hilo():
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "ODR_L")
        r = list(g["REGS"][i]); r[0] = 0x0D; g["REGS"][i] = tuple(r)

    def m_define56():
        g["REGS"].append((0x56, "EXTRA56", "RO", False, [F("X", 7, 0, 0, [0], "ro", "x")], "x"))

    def m_blank0():
        fld("BLANK", "BLANK_LEN")["legal"] = rng(0, 15)

    def m_telec_max():
        f = fld("T_ELEC", "T_ELEC")
        f["legal"] = [v for v in f["legal"] if v != max(f["legal"])]

    def m_drop_field():
        r = next(r for r in g["REGS"] if r[1] == "ERR")
        r[4][:] = [f for f in r[4] if f["name"] != "CMD_ERR"]

    def m_extra_ro():
        next(r for r in g["REGS"] if r[1] == "CAPS")[4].append(F("SPARE", 7, 7, 0, [0], "ro", "x"))

    def m_move_status():
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "STATUS")
        r = list(g["REGS"][i]); r[0] = 0x0D; g["REGS"][i] = tuple(r)

    def m_region():
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "VERSION")
        r = list(g["REGS"][i]); r[0] = 0x41; g["REGS"][i] = tuple(r)

    def m_lock_mask():
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "ALERT_MASK")
        r = list(g["REGS"][i]); r[3] = True; g["REGS"][i] = tuple(r)

    def m_wo_timer():
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "T_WARM")
        r = list(g["REGS"][i]); r[2] = "WO"; g["REGS"][i] = tuple(r)

    def m_cmd_class():
        fld("TEST_KEY", "KEY")["cls"] = "cmd"

    def m_crc_bit():
        fld("IF_CFG", "CRC_EN").update(msb=2, lsb=2)

    def m_digital_pin():
        fld("ID", "ID")["pin"] = "TEST_CFG[7:6]"

    def m_status_reset():
        fld("STATUS", "ALERT")["reset"] = 0

    # audit round 11, auditor C: the legal sets, the masks
    def m_legal_narrow():
        fld("ADC_CFG", "CHOP1_RATE")["legal"] = rng(0, 4)

    def m_legal_hole():
        fld("T_REC", "T_REC")["legal"] = [v for v in rng(29, 255) if v != 100]

    def m_soft_code():                                   # audit round 13, auditor C: codes, bits and values
        g["COMMANDS"]["SOFT_RESET"] = 0xA6

    def m_key_code():
        g["TEST_KEY"] = 0x3D

    def m_err_swap():
        fld("ERR", "FRAME_ERR").update(msb=2, lsb=2)
        fld("ERR", "CRC_ERR").update(msb=1, lsb=1)

    def m_smp_swap():
        ss = list(g["SAMPLE_STATUS"])
        ss[0], ss[1] = (ss[0][0], ss[1][1], ss[0][2]), (ss[1][0], ss[0][1], ss[1][2])
        g["SAMPLE_STATUS"] = ss

    def m_smp_missing():
        g["SAMPLE_STATUS"] = [("0", b, d) if n == "CHANGED" else (n, b, d) for n, b, d in g["SAMPLE_STATUS"]]

    def m_level_ro():
        fld("FIFO_LEVEL", "LEVEL")["legal"] = rng(0, 7)

    def m_odr():
        fld("ODR_L", "ODR_L").update(reset=0xE9, legal=[0xE9])

    def m_qbits():
        fld("FORMAT", "QBITS").update(reset=4, legal=[4])

    def m_pin_swap():                                    # audit round 14, auditor C: the pin column
        fld("OFF_CTRL", "SIGN")["pin"], fld("OFF_CTRL", "RANGE")["pin"] = "OFEN[3:0]", "OFS"

    def m_pin_w1c():
        fld("ERR", "CMD_ERR")["pin"], fld("DEBUG", "DBG_SEL")["pin"] = "TEST_CFG[7:6]", None

    def m_ro_const():
        fld("VERSION", "VERSION")["legal"] = [16, 17]

    def m_status_swap():                                 # audit round 15, auditor C: STATUS, whole bytes, the window
        fld("STATUS", "READY").update(msb=2, lsb=2)
        fld("STATUS", "DATA").update(msb=3, lsb=3)

    def m_cmd_narrow():
        fld("COMMAND", "CMD").update(msb=6)

    def m_key_narrow():
        fld("TEST_KEY", "KEY").update(msb=6)

    def m_ro_none():
        fld("ID", "ID")["legal"] = None

    def m_window_neighbour():                            # audit round 16, auditor B: TEST_MUX moved to 0x68
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "TEST_MUX")
        r = list(g["REGS"][i]); r[0] = 0x68; g["REGS"][i] = tuple(r)

    def m_chop1_rate_6():                                # audit round 17, auditor C: a value the pin rules do not
        fld("ADC_CFG", "CHOP1_RATE")["legal"] = fld("ADC_CFG", "CHOP1_RATE")["legal"] + [6]   # define (it crashed)

    def m_timer_legal_none():                            # audit round 17, auditor C: a timer without legal values
        fld("T_PRE", "T_PRE")["legal"] = None                                                  # (it crashed)

    def m_lsb_negative():                                # audit round 18, auditor C: a field at bit -1 (it crashed)
        fld("BLANK", "BLANK_LEN")["lsb"] = -1

    def m_twarm_lsb_negative():                          # audit round 21, auditor C: the same on a register the slip
        fld("T_WARM", "T_WARM")["lsb"] = -1               # model decodes (it crashed there)

    def m_ofm_pins_swapped():                            # audit round 21, auditor C: M_H and M_L's OFM ranges swapped
        a_, b_ = fld("OFF_M_H", "M_H"), fld("OFF_M_L", "M_L")
        a_["pin"], b_["pin"] = b_["pin"], a_["pin"]

    def m_req_slip_count():                              # audit round 21, auditor C: the requirements' T_WARM count
        g["REQ_DOC"] = req_slip9                          # back at round 19's 9

    def m_req_slip_unread():                             # audit round 34, auditor C: the count not readable (the
        g["REQ_DOC"] = req_slip_unread                    # check's "not got_" operand)

    def m_req_ovl_codes():                               # audit round 34, auditor C: FLG-04 stating other codes
        g["REQ_DOC"] = req_codes30                        # (window and threshold as OVL_RULE)

    def m_cfg_top_refused():                             # audit round 34, auditor C: cfg_ok refusing a range's top
        f0 = keep_fn["cfg_ok"]                            # (M 255 in range 2; every other mutation accepted M + 1)
        g["cfg_ok"] = lambda sh: f0(sh) and not (sh["RANGE"] == 2 and sh["M"] == g["RANGE_MAX_M"][2])

    def m_state_legal_none():                            # audit round 18, auditor C: STATE without its values (it
        fld("STATE", "STATE")["legal"] = None                                         # crashed)

    def m_sample_reserved_moved():                       # audit round 18, auditor C: a reserved sample status bit
        i = next(k for k, x in enumerate(g["SAMPLE_STATUS"]) if x[0] == "0" and x[1] == 2)   # listed at bit 7
        g["SAMPLE_STATUS"][i] = ("0", 7, g["SAMPLE_STATUS"][i][2])

    def m_slip_twarm():                                  # audit round 19, auditor B: a header slip makes T_WARM's read
        g["SLIP_DECIDE_REQUIRED"]["T_WARM"] = []          # a sample read

    def m_slip_status():                                 # audit round 18, auditor B: STATUS decided from alone
        g["SLIP_DECIDE_REQUIRED"]["STATUS"] = []

    def m_slip_twarm_afe():                              # audit round 20, auditor B: T_WARM's pairs as round 19's
        g["SLIP_DECIDE_REQUIRED"]["T_WARM"] = [(-1, 0x40), (-1, 0x44), (-1, 0x48), (-1, 0x4C), (-1, 0x50),   # model
                                               (-1, 0x54), (-1, 0x58), (-1, 0x5C), (0x8A, 0x8B)]   # (AFE_RST 0)

    def m_slip_copy_pair():                              # audit round 20, auditor B: OFF_M_L's copy, its pair not
        g["SLIP_DECIDE_REQUIRED"]["OFF_M_L.ACT"] = []    # tolerated

    def m_slip_copy_missing():                           # audit round 20, auditor B: an active copy left out
        del g["SLIP_DECIDE_REQUIRED"]["BLANK.ACT"]

    def m_slip_copy_unknown():                           # audit round 20: an entry that is no active copy
        g["SLIP_DECIDE_REQUIRED"]["STATUS.ACT"] = []

    def m_fifo_level_moved():                            # audit round 20, auditor C: FIFO_LEVEL, which the host reads
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "FIFO_LEVEL")   # at 0x05, moved within its block
        r = list(g["REGS"][i]); r[0] = 0x0D; g["REGS"][i] = tuple(r)

    def m_fixed_addr_drop():                             # audit round 20, auditor C: an address the requirements name
        del g["FIXED_ADDR"]["TEST_MUX"]                 # left out of FIXED_ADDR

    def m_debug_in_copies():                             # audit round 20, auditor C: a test register among the copies
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "DEBUG")
        r = list(g["REGS"][i]); r[0] = 0x72; g["REGS"][i] = tuple(r)

    def m_slip_count_status():                           # audit round 20, auditor C: a recorded slip count off by one
        g["SLIP_COUNTS_RECORDED"]["STATUS"] = 61

    def m_slip_count_missing():                          # audit round 27, auditor B: a register step 3 reads back,
        del g["SLIP_COUNTS_RECORDED"]["T_REC"]        # left out of the slip record

    def move_field(src, name, dst, bit):                 # audit round 29, auditor C: a field moved to another
        f = fld(src, name)                                # register at a free bit
        next(r for r in g["REGS"] if r[1] == src)[4].remove(f)
        f = dict(f)
        f.update(msb=bit, lsb=bit)
        next(r for r in g["REGS"] if r[1] == dst)[4].append(f)

    def m_probe_record():                                # audit round 32, auditor B: a probe pair left out of the record
        g["PROBE_SLIP_RECORDED"] = {("T_REC", 0x30)}

    def m_probe_at_reset():                              # audit round 32, auditor B: T_RST's reset value one at which
        fld("T_RST", "T_RST")["reset"] = 0x22          # one SCLK fault makes the mode probe read CRC off

    def m_probe_off_reach():                             # audit round 34, auditor B: a reachable T_RST of 0x25
        g["PROBE_OFF_REACHABLE"]["T_RST"] = [0x25]

    def m_probe_off():                                   # audit round 33, auditor B: a T_RST reset value at which a
        fld("T_RST", "T_RST")["reset"] = 0x25          # CRC-off chip answers the probe as CRC on (bit-0 flip)

    def m_reg01_list():                                  # audit round 32, auditor B: FIXED_ADDR beyond REG-01's list
        g["FIXED_ADDR"]["ALERT_MASK_D"] = 0x09

    def m_guard_text():                                  # audit round 32, auditor B: BLANK out of the stated range
        i_ = next(i for i, r in enumerate(g["REGS"]) if r[1] == "BLANK")
        r = list(g["REGS"][i_]); r[0] = 0x29; g["REGS"][i_] = tuple(r)

    def m_doc_marker():                                  # audit round 32, auditor C: the spec's generated blocks
        g["DOC"] = spec_nomark

    def m_doc_double():
        g["DOC"] = spec_double

    def m_doc_missing():
        g["DOC"] = os.path.join(tmp, "missing_spec.md")

    def m_doc_unknown():                                 # audit round 33, auditor C
        g["DOC"] = spec_unknown

    def m_doc_order():
        g["DOC"] = spec_order

    def m_test_field_out():                              # a test field out of its locked register
        move_field("TEST_CTRL", "CHOP_STOP", "CHOP_CFG", 1)

    def m_field_into_test():                             # an operating field into a locked register
        move_field("OFF_CTRL", "SIGN", "TEST_CTRL", 2)

    def m_window_moved():                                # audit round 17, auditor B: the window moved (item 258's
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "SAMPLE")  # option), the SPI table's text left behind
        r = list(g["REGS"][i]); r[0] = 0x4F; g["REGS"][i] = tuple(r)

    def m_sample_reset():
        fld("SAMPLE", "SAMPLE")["reset"] = 0x5A

    def m_copy_region():                                 # audit round 12, auditor B: an active copy in no region
        i = next(k for k, r in enumerate(g["REGS"]) if r[1] == "BLANK")
        r = list(g["REGS"][i]); r[0] = 0x38; g["REGS"][i] = tuple(r)

    def m_mask_cover():
        fld("DFLAG", "OVL").update(msb=2, lsb=2)

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
            ("全振幅の符号の列が 11/19 のものでない", m_codes_other), ("cfg_ok が範囲の上限 ＋ 1 を受け付ける", m_cfg_top),
            ("CHOP_STOP の既定値が 1（電源投入からチョッパが止まる）", m_chopstop_reset),
            ("ADC_ZERO の既定値が 1（電源投入から ADC の入力が短絡）", m_adczero_reset),
            ("既定値の定めのない書き込み可能なフィールド", m_no_default), ("RW のレジスタに読み出し専用の区分", m_access_class),
            ("RANGE の合法な値に 5", m_range_legal), ("SIGN の合法な値が 0 のみ", m_sign_legal),
            ("M_H の合法な値が 0〜2（M ≤ 767）", m_mh_legal), ("ODR_L が ODR_H の次のアドレスでない", m_hilo),
            ("0x56 を定義する（手順 9 のモードの判定が未定義として読む）", m_define56),
            ("BLANK_LEN の 0 を合法とする", m_blank0), ("T_ELEC の最大が TIMING と合わない", m_telec_max),
            ("ERR から CMD_ERR を除く", m_drop_field), ("要件にない読み出し専用のフィールド", m_extra_ro),
            ("STATUS を 0x0D に移す（手順が 0x03 として読む）", m_move_status), ("VERSION をデータの窓の区画へ", m_region),
            ("ALERT_MASK を施錠する", m_lock_mask), ("T_WARM を書き込み専用に", m_wo_timer),
            ("試験の鍵を命令の区分に", m_cmd_class), ("CRC_EN を bit 2 に（手順 9 は bit 0 を読む）", m_crc_bit),
            ("読み出し専用の ID を DBG_SEL の端子の出どころに", m_digital_pin), ("STATUS.ALERT の既定値を 0", m_status_reset),
            ("CHOP1_RATE の合法な値を 0〜4 に（16 kHz を書けない）", m_legal_narrow), ("T_REC の合法な値に穴（100）", m_legal_hole),
            ("DFLAG.OVL を bit 2 に（ALERT_MASK_D が覆わない）", m_mask_cover),
            ("BLANK を 0x38 に（写し 0x48 が設定の区画の外）", m_copy_region),
            ("SOFT_RESET のコードを 0xA6 に（2 ビットの差は保つ）", m_soft_code), ("試験の鍵を 0x3D に", m_key_code),
            ("ERR の FRAME_ERR と CRC_ERR のビットの入れ違い", m_err_swap),
            ("サンプルの状態の VALID と OVERRUN の入れ違い", m_smp_swap), ("サンプルの状態から CHANGED の名を除く", m_smp_missing),
            ("FIFO_LEVEL の値を 0〜7 に", m_level_ro),
            ("ODR_L を 0xE9 に（1001 SPS）", m_odr), ("QBITS を 4 に", m_qbits),
            ("SIGN と RANGE の端子の入れ違い", m_pin_swap), ("ERR.CMD_ERR を TEST_CFG[7:6] の出どころに", m_pin_w1c),
            ("VERSION の値に 17 も", m_ro_const),
            ("STATUS の READY と DATA の入れ違い", m_status_swap), ("COMMAND の CMD を 7 ビットに（0xA5 が入らない）", m_cmd_narrow),
            ("TEST_KEY の KEY を 7 ビットに", m_key_narrow), ("ID の読み値を定めない（legal None）", m_ro_none),
            ("SAMPLE の既定値を 0x5A に", m_sample_reset), ("TEST_MUX を 0x68 に（窓の 1 ビットの隣が変わる）", m_window_neighbour),
            ("サンプルの窓を 0x4F に（SPI の表の文が古い先頭バイトのまま）", m_window_moved),
            ("CHOP1_RATE の合法な値に 6 を加える（端子の規則にない値）", m_chop1_rate_6),
            ("T_PRE の合法な値を None に", m_timer_legal_none),
            ("STATUS を判断に使う一覧に加える（滑りで別の値が CRC を通る）", m_slip_status),
            ("T_WARM を判断に使う一覧に加える（先頭バイトの滑りで窓の読み出しとなる）", m_slip_twarm),
            ("T_WARM の滑りを AFE_RST ＝ 0 のみの 9 組で許す（第 19 回の模型の数）", m_slip_twarm_afe),
            ("OFF_M_L の写しの滑りの 1 組を許さない", m_slip_copy_pair),
            ("BLANK の写しを滑りの一覧から除く", m_slip_copy_missing),
            ("STATUS の写し（ない）を滑りの一覧に加える", m_slip_copy_unknown),
            ("FIFO_LEVEL を 0x0D に移す（手順が 0x05 として読む）", m_fifo_level_moved),
            ("FIXED_ADDR から TEST_MUX を除く（要件が 0x60 と名指す）", m_fixed_addr_drop),
            ("DEBUG を写しの半分の 0x72 に", m_debug_in_copies),
            ("STATUS の滑りの組の数を 61 と記す", m_slip_count_status),
            ("T_REC を滑りの記録から除く（手順 3 の読み戻し）", m_slip_count_missing),
            ("CHOP_STOP を CHOP_CFG に移す（試験の欄を施錠しないレジスタへ）", m_test_field_out),
            ("SIGN を TEST_CTRL に移す（運転の欄を施錠するレジスタへ）", m_field_into_test),
            ("モードの判定の滑りの組を記録から除く（T_RST 0x22）", m_probe_record),
            ("T_RST の既定値を 0x22 に（モードの判定が 1 回の故障で CRC 無効に読める値）", m_probe_at_reset),
            ("FIXED_ADDR に REG-01 の一覧にない ALERT_MASK_D を加える", m_reg01_list),
            ("T_RST の既定値を 0x25 に（CRC 無効のチップがモードの判定で CRC 有効と読める値）", m_probe_off),
            ("CRC 無効のチップの到達しうる値に T_RST 0x25 を加える", m_probe_off_reach),
            ("要件の T_WARM の滑りの数を読めない形に（17 個の組）", m_req_slip_unread),
            ("要件の FLG-04 の両端の符号を 0 と 30 に", m_req_ovl_codes),
            ("cfg_ok が範囲 2 の上限（M 255）を拒む", m_cfg_top_refused),
            ("BLANK を 0x29 に移す（詳細仕様 2.3 の守る範囲の外）", m_guard_text),
            ("詳細仕様の生成のブロックの END の印を除く（reg_fields）", m_doc_marker),
            ("詳細仕様の生成のブロックを二重に（commands）", m_doc_double),
            ("詳細仕様がない", m_doc_missing),
            ("詳細仕様に生成しない鍵の印を加える（reg_old）", m_doc_unknown),
            ("詳細仕様の生成のブロックの END を BEGIN の前に（commands）", m_doc_order),
            ("BLANK_LEN の lsb を −1 に（バイトの外）", m_lsb_negative),
            ("T_WARM の lsb を −1 に（滑りの模型の読むレジスタ）", m_twarm_lsb_negative),
            ("OFF_M_H と OFF_M_L の端子の欄の OFM の範囲を入れ替える", m_ofm_pins_swapped),
            ("要件の T_WARM の滑りの数を 9 組に（第 19 回の数）", m_req_slip_count), ("STATE の合法な値を None に", m_state_legal_none),
            ("サンプルの状態の予約のビット 2 を 7 に", m_sample_reserved_moved)]
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
    # the counts the spec quotes (audit round 21, auditor A, as in fsm_spec): every count of this self-test equals what
    # it ran
    spec_doc = os.path.join(REPO, "documentation", "gf180_digital_control_spec_20261119.md")
    for pat_, what_, have_ in ((r"`regmap\.py` は (\d+) 種類", "mutations", len(results)),
                               (r"`regmap\.py selftest`（(\d+) 種", "mutations", len(results)),
                               (r"check の全ての違反の文 (\d+) 種が目的の文", "messages", len(msgs)),
                               (r"（`fsm_spec\.py` \d+ 種、`regmap\.py` (\d+) 種", "messages", len(msgs))):
        try:
            got_ = [int(x) for x in re.findall(pat_, open(spec_doc, encoding="utf-8").read())]
        except OSError as ex:
            problems.append(f"{os.path.basename(spec_doc)} cannot be read ({ex})")
            continue
        if not got_:
            problems.append(f"{os.path.basename(spec_doc)} no longer quotes the self-test's {what_} ({pat_})")
        elif any(g_ != have_ for g_ in got_):
            problems.append(f"{os.path.basename(spec_doc)} quotes {got_} {what_} of the self-test, which has {have_}")
    e = check(verbose=False)
    shutil.rmtree(tmp, ignore_errors=True)               # the self-test's own folder (audit round 10)
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
    'CHOP_STOP の既定値が 1（電源投入からチョッパが止まる）': (', but the requirements give',),
    'ADC_ZERO の既定値が 1（電源投入から ADC の入力が短絡）': (', but the requirements give',),
    '既定値の定めのない書き込み可能なフィールド': (': a writable field without a reset value stated from the requirements (REQUIRED_RESET)', ': a writable field without legal values stated from the requirements (REQUIRED_LEGAL)',),
    'RW のレジスタに読み出し専用の区分': ('(RO: ro; W1C: w1c; RW: apply or imm; WO: cmd or imm)',),
    'RANGE の合法な値に 5': (', but the ranges of RANGE_MAX_M are',),
    'SIGN の合法な値が 0 のみ': (': the offset needs both signs',),
    'M_H の合法な値が 0〜2（M ≤ 767）': ('M: the legal values of M_H and M_L do not reach every M up to',),
    'ODR_L が ODR_H の次のアドレスでない': ('_L: a field over 8 bits not at consecutive addresses, the high byte first (REG-04)',),
    '0x56 を定義する（手順 9 のモードの判定が未定義として読む）': ("address 0x56 is defined: step 9's mode probe reads it, after IF_CFG, as undefined (0x00)",),
    'BLANK_LEN の 0 を合法とする': ('BLANK_LEN 0 is legal (REG-06: it must give RANGE_ERR; CDA and CDB would overlap at the edges)', "is legal, but the field's text says",),
    'T_ELEC の最大が TIMING と合わない': (': the register reaches',),
    'ERR から CMD_ERR を除く': (': a field the requirements name is missing from the map',),
    '要件にない読み出し専用のフィールド': (': a read-only field the requirements do not name',),
    'STATUS を 0x0D に移す（手順が 0x03 として読む）': (': the host procedure names it at 0x',),
    'VERSION をデータの窓の区画へ': ('region of REG-01 (0x',),
    'ALERT_MASK を施錠する': ('(REG-08: exactly the registers of the test region are locked)',),
    'T_WARM を書き込み専用に': ('; only the command register and the test key are write-only',),
    '試験の鍵を命令の区分に': ("; the class cmd is the command register's alone",),
    'CRC_EN を bit 2 に（手順 9 は bit 0 を読む）': (', the requirements read it at bit',),
    '読み出し専用の ID を DBG_SEL の端子の出どころに': ('(a digital-only control needs exactly one, writable)',),
    'STATUS.ALERT の既定値を 0': ('after a reset, where the requirements give',),
    'CHOP1_RATE の合法な値を 0〜4 に（16 kHz を書けない）': ('differ from those the requirements give (REQUIRED_LEGAL)',),
    'T_REC の合法な値に穴（100）': ('differ from those the requirements give (REQUIRED_LEGAL)',),
    'CHOP1_RATE の合法な値に 6 を加える（端子の規則にない値）': ('differ from those the requirements give (REQUIRED_LEGAL)',
                                                     'hold values the requirements do not give (REQUIRED_LEGAL), for which pins_from_active is not defined'),
    'T_PRE の合法な値を None に': ('differ from those the requirements give (REQUIRED_LEGAL)',),
    'STATUS を判断に使う一覧に加える（滑りで別の値が CRC を通る）': (': one SCLK slip in its CRC read gives another legal value with a valid CRC for the pairs',),
    'BLANK_LEN の lsb を −1 に（バイトの外）': ('outside the byte',),
    # audit round 21, auditor C
    'T_WARM の lsb を −1 に（滑りの模型の読むレジスタ）': ('outside the byte',),
    'OFF_M_H と OFF_M_L の端子の欄の OFM の範囲を入れ替える': ('(pins_from_active, the bit split; audit round 21)',),
    '要件の T_WARM の滑りの数を 9 組に（第 19 回の数）': ('(5.4 (b), the record the model is held to; audit round 21)',),
    '要件の T_WARM の滑りの数を読めない形に（17 個の組）': ('(5.4 (b), the record the model is held to; audit round 21)',),
    '要件の FLG-04 の両端の符号を 0 と 30 に': ('differs from the rule stated in',),
    'cfg_ok が範囲 2 の上限（M 255）を拒む': ('cfg_ok wrong at the top of range',),
    'STATE の合法な値を None に': ("STATE field does not match the sequencer's state codes",),
    'サンプルの状態の予約のビット 2 を 7 に': (': each of the bits 0..7 must be listed exactly once (the generated table showed one bit twice and none for another)',),
    'DFLAG.OVL を bit 2 に（ALERT_MASK_D が覆わない）': ('(a flag that no mask bit masks)',),
    'BLANK を 0x38 に（写し 0x48 が設定の区画の外）': ("outside its register's",       # and the copy 0x48 is one bit from
                                                   'readable addresses one bit from the sample window:'),   # the window (round 17)
    'SOFT_RESET のコードを 0xA6 に（2 ビットの差は保つ）': (': the requirements fix it at 0x',),
    '試験の鍵を 0x3D に': (': the requirements fix it at 0x',),
    'ERR の FRAME_ERR と CRC_ERR のビットの入れ違い': (', the requirements read it at bit',),
    'サンプルの状態の VALID と OVERRUN の入れ違い': ('; DAT-02 orders the byte VALID, OVERRUN, OVL, CHANGED, ERR (bit',),
    'サンプルの状態から CHANGED の名を除く': ('sample status: a bit DAT-02 names is missing',),
    'FIFO_LEVEL の値を 0〜7 に': ('are not the ones the requirements give (REQUIRED_RO_LEGAL)',),
    'ODR_L を 0xE9 に（1001 SPS）': ('SPS in ODR_H, ODR_L; fsm_spec.TIMING outputs',),
    'QBITS を 4 に': ("; the quantizer's codes 0..",),
    'SIGN と RANGE の端子の入れ違い': (', but changing it moves',),
    'ERR.CMD_ERR を TEST_CFG[7:6] の出どころに': (', but changing it moves',),
    'VERSION の値に 17 も': (': read-only constant values',),
    'STATUS の READY と DATA の入れ違い': (', the requirements read it at bit',),
    'COMMAND の CMD を 7 ビットに（0xA5 が入らない）': ('; the requirements compare the whole byte (REG-02, SPI-09, REG-08: the command codes and the test key)',),
    'TEST_KEY の KEY を 7 ビットに': ('; the requirements compare the whole byte (REG-02, SPI-09, REG-08: the command codes and the test key)',),
    'ID の読み値を定めない（legal None）': (': a read-only field without its read values (legal None)',),
    'TEST_MUX を 0x68 に（窓の 1 ビットの隣が変わる）': ('readable addresses one bit from the sample window:',),
    'サンプルの窓を 0x4F に（SPI の表の文が古い先頭バイトのまま）': ("the SPI table's RSMP text (fsm_spec.SPI_STATES) does not name the sample read's header 0x",
                                                    'readable addresses a single SCLK slip in the header turns into a sample read:'),
    'T_WARM を判断に使う一覧に加える（先頭バイトの滑りで窓の読み出しとなる）': (': one SCLK slip in its CRC read gives another legal value with a valid CRC for the pairs',),
    # audit round 20, auditor B
    'T_WARM の滑りを AFE_RST ＝ 0 のみの 9 組で許す（第 19 回の模型の数）': (': one SCLK slip in its CRC read gives another legal value with a valid CRC for the pairs',),
    'OFF_M_L の写しの滑りの 1 組を許さない': (': one SCLK slip in its CRC read gives another legal value with a valid CRC for the pairs',),
    'BLANK の写しを滑りの一覧から除く': ('(step 4 confirms APPLY and APPLY_NR by the active copies and rule (c) compares them; audit round 20)',),
    'STATUS の写し（ない）を滑りの一覧に加える': (': in the slip list, but neither a register nor an active copy (audit round 20)',),
    'FIFO_LEVEL を 0x0D に移す（手順が 0x05 として読む）': (': the host procedure names it at 0x',),
    'FIXED_ADDR から TEST_MUX を除く（要件が 0x60 と名指す）': (', which FIXED_ADDR does not hold (the host relies on the addresses the documents name; audit round 20)',),
    'DEBUG を写しの半分の 0x72 に': ('region of REG-01 (0x',),
    'STATUS の滑りの組の数を 61 と記す': ('slip pairs read as another legal value with a valid CRC, while the documents record',),
    'T_REC を滑りの記録から除く（手順 3 の読み戻し）': ('(step 3 reads every register it wrote back twice; audit round 27, auditor B)',),
    'CHOP_STOP を CHOP_CFG に移す（試験の欄を施錠しないレジスタへ）': (', while the requirements name its register',),
    'SIGN を TEST_CTRL に移す（運転の欄を施錠するレジスタへ）': (', a field the requirements do not put there (REG-08 locks only the test fields; IF_CFG holds DRDY_MODE and CRC_EN; audit round 29)',),
    'モードの判定の滑りの組を記録から除く（T_RST 0x22）': ('the mode probe reads as CRC off under one fault (SCLK or a header bit) for',),
    'T_RST の既定値を 0x22 に（モードの判定が 1 回の故障で CRC 無効に読める値）': ('the mode probe reads as CRC off under one fault (SCLK or a header bit) at the reset value 0x',),
    'T_RST の既定値を 0x25 に（CRC 無効のチップがモードの判定で CRC 有効と読める値）': ('(rule (c): the procedure writes the timers and the shadows only with CRC on; audit round 33, auditor B)',),
    'CRC 無効のチップの到達しうる値に T_RST 0x25 を加える': ('(rule (c): the procedure writes the timers and the shadows only with CRC on; audit round 33, auditor B)',),
    'FIXED_ADDR に REG-01 の一覧にない ALERT_MASK_D を加える': ('(audit round 32, auditor B: rounds 29 and 31 added to one only)',),
    'BLANK を 0x29 に移す（詳細仕様 2.3 の守る範囲の外）': ("(the spec's 2.3 and the requirements' CRC-off note state the guarded set by ranges; audit round 32, auditor B)",),
    '詳細仕様の生成のブロックの END の印を除く（reg_fields）': ('(every block of the spec with its BEGIN and END markers once each and in order, no other block, the spec readable: generate() and fresh() skipped a block without its markers and a missing spec; audit round 32, auditor C)',),
    '詳細仕様の生成のブロックを二重に（commands）': ('(every block of the spec with its BEGIN and END markers once each and in order, no other block, the spec readable: generate() and fresh() skipped a block without its markers and a missing spec; audit round 32, auditor C)',),
    '詳細仕様がない': ('(every block of the spec with its BEGIN and END markers once each and in order, no other block, the spec readable: generate() and fresh() skipped a block without its markers and a missing spec; audit round 32, auditor C)',),
    '詳細仕様に生成しない鍵の印を加える（reg_old）': ('(every block of the spec with its BEGIN and END markers once each and in order, no other block, the spec readable: generate() and fresh() skipped a block without its markers and a missing spec; audit round 32, auditor C)',),
    '詳細仕様の生成のブロックの END を BEGIN の前に（commands）': ('(every block of the spec with its BEGIN and END markers once each and in order, no other block, the spec readable: generate() and fresh() skipped a block without its markers and a missing spec; audit round 32, auditor C)',),
    'SAMPLE の既定値を 0x5A に': ('; the window reads 0x00 inside a burst and alone (spec 3.2), so the map holds 0 for it',),
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
