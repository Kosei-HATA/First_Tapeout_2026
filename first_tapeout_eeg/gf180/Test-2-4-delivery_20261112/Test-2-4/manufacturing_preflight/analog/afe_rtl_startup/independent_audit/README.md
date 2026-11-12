# RTL→analog PWL 独立監査

## 結論

**限定範囲の監査PASS。製造認定・analog性能合格ではない。** 初回128 µs刺激と追加192 µs刺激を独立計算で監査した。元workerのファイルは変更していない。

| 確認対象 | 初回128 µs | 延長192 µs |
|---|---:|---:|
| CHOP遷移 | 32/32一致 | 49/49一致 |
| CHOP_OUT遷移 | 32/32一致 | 49/49一致 |
| BLANK遷移 | 62/62一致 | 96/96一致 |
| ADC_RST_N遷移 | 1/1一致 | 1/1一致 |
| AFE_RST遷移 | 1/1一致 | 1/1一致 |
| PWL信号 | 30/30一致 | 30/30一致 |

元RTL13ファイルのSHA256がmanifestと一致。PWL全点の極性・初期ramp・bit抽出・遷移時刻・電圧・単調時刻順を確認。実XA/XB/XC端子へ全30信号が1回ずつ接続され、反転・欠落・配列逆転はない。旧CSVは新CSVのbyte単位で完全なprefix。旧PWLは128 µs終端保持点を除く全点が新PWLのprefixに一致した。

## 独立計算方法

MCLK立上りを `2000 + n × (1000 / 32.768)` ns として、RTLの1 ps精度に丸めた。3 µsのRESET_N解除後、最初の立上りは3.007080 µs、2本目で同期reset解除、3本目でframe0とCHOP開始となる。

SPIはmode0、MSB-first、0x20 / 0x02 / 0x64の24 bit。SCLK High/Lowは250 ns、CS_Nは8 µsにLow、21 µsにHigh。CS同期・edge detect・reg_we・register適用を独立に追跡した。CONTROL0x64はreset0x74からAFE_RSTのbit4だけを落とし、RUN=0、DWA_EN=1、RAW_EN=0、CHOP_EN=1、CHOP_FAST=1を保つ。

初回CHOP/CHOP_OUT立上りだけBLANK=0。以降128 MCLKごとの各遷移に対し、1 MCLK前から7 MCLK後まで、計8 MCLKのblankを期待値とした。CSV全遷移を独自計算値と比較し、1.01 ps以内で全件一致。実差は浮動小数演算の丸め程度だった。

PWL電圧源の全(time, voltage)対を別に解析し、CSVのbit値から期待点列を再構築した。時刻1e-16 s、電圧1e-12 V以内で全点を照合。analogは実際にincludeされる .subckt 宣言とpilotの位置引数を突き合わせた。worker生成器を実行して自己照合したものではない。

## 主要時刻と配列

- RESET_N外部解除3.000000 µs、CSV記録3.000002 µs。
- ADC_RST_N↑3.037600 µs、CHOP/CHOP_OUT初回↑3.068117 µs（BLANK=0）。
- 最初のBLANKは6.943850〜7.187990 µs、CHOP↓は6.974367 µs。
- CS_N↑21.000000 µs、AFE_RST↓21.104006 µs。
- AFEのCPF端子はCPF0,1,2,3のLSB順。reset8はCPF3のみHigh。
- bias端子はIB1,IB0,BP1,BP0,BN1,BN0の順。reset2/1/1はHigh,Low,Low,High,Low,High。
- CHOP_EN=1、OFM/OFS/OFEN=0を保持。AFE_RSTはactive-highで、driver内2段invert後にRSTへ接続。

## 2 ps + slewと電源投入仮定

CSVはRTL eventの**2 ps後**を記録し、PWLはその時刻から**0.5 ns**で遷移する。中心化していないため50%交点はRTL eventの約252 ps後。reset中Highの信号は0〜1 µsに0〜3.3 Vへramp、Lowは0 Vを維持する。これは仮定したDVDD振幅であり、power-aware RTLや実digital出力bufferの検証ではない。

## 長窓延長の確認

初回の128 µs刺激では、それ以後CHOP/BLANKが最終値で静止するため不足していた。入力step28.916506 µs後に8周期（62.5 µs）待機し、その後4周期窓×2（さらに62.5 µs）を評価する。待機と評価は重ねない。

- 最短未整列終了:153.916506 µs。
- CHOP立上りに位相整列した評価窓:**96.818117〜159.318117 µs**。
- 現192 µs版は全30 PWLの最終点が192 µs。最終control eventは190.781740 µs。
- 計画160 µs transientと上記評価窓を刺激が包含することを確認。

旧snapshot（rtl/controls.csv.128us、rtl/tb.sv.128us、controls_128us.inc）と現版を別々に照合し、延長前の内容が保存されていることを確認した。1 ns入力slewの完了を待機起点としても位相整列窓は同じ。

**32 µs pilotは定常試験ではない。長時間analog結果の完走・数値収束・基準適合は本監査の対象外。** 実行deckがこの192 µs controls.incを使い、159.318117 µs以後まで完走したことを別途確認する必要がある。今後さらに長くする場合もanalog時間だけを延長せず、必ずRTL/PWLの有効範囲を再確認する。

## 範囲と未検証項目

- 実eeg_digital_topのreplay。CODE=16固定でeeg_adc_dig、ADC/DWA閉ループ、system decimation/ENOBは含まない。
- CMP_STROBE、DAC_CLK、CHOP1、TEST_CFG、FIFO/rawなどはAFE analogへ接続していない。
- MOSCAPはcharge-equivalent診断モデル。foundry元transient modelを無変更で評価したものではない。
- ITSTは電源ramp中も理想1 V源。電極common-modeは生成VCMへ追従し、外部電極モデルなし。
- AVDD/DVDD同時3.3 V rampを仮定。独立DVDD配電網、digital出力buffer、pad/package/board/finite substrate、brownoutは含まない。
- analog収束・settling・利得・ENOB・stress寿命・製造可否は判定していない。

## 根拠と再確認用情報

基準パス: C:\projects\ft\test1x。

- gf180/tapeout/rtl/eeg_digital_top.sv:67–80,127–129,209–243
- gf180/tapeout/rtl/eeg_spi_slave.sv:1–28,65–89,171–205
- gf180/tapeout/rtl/eeg_regs.sv:104–148
- gf180/tapeout/rtl/eeg_clkgen.sv:40–63,160–203
- gf180/tapeout/afe/eeg_afe.spice:302–335,376–384
- gf180/tapeout/afe/eeg_afe_clk.spice:22–79
- gf180/tapeout/bias/eeg_bias.spice:8–17,58–59
- Test-2-4/source/layout/chip_lay.py:565–573

summary.jsonに独自計算方法、初回/追加監査の全件数、各PWL点数、実接続、許容差、入力SHA256、範囲を保存した。監査入力のbyte列は処理前後で不変を確認。この監査は成果読取と独立数値照合であり、RTL simulatorやanalog simulatorの再実行ではない。
