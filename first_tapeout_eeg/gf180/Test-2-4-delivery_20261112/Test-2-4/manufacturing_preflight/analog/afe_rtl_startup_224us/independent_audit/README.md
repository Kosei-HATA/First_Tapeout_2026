# 256 µs刺激・224 µs診断向け独立追加監査

## 結論と版

**限定範囲の監査PASS。analog結果・製造認定の合格ではない。**

版: `extension_256us_for_224us_diagnostic_v1`。旧 `afe_rtl_startup/independent_audit/README.md` と `summary.json` は上書きせず保全。新記録は `afe_rtl_startup_224us/independent_audit/` に保存した。旧・新入力、旧監査文書、RTL/analog subcircuitのSHA256をsummary.jsonに記録し、入力byte列が処理前後で不変と確認した。

## 一致件数と延長内容

- CHOP:65/65遷移一致、CHOP_OUT:65/65遷移一致。
- BLANK:128/128遷移一致、ADC_RST_N:1/1、AFE_RST:1/1一致。
- PWL:全30信号の全点、極性、初期ramp、bit抽出、単調時刻順が一致。
- 旧192 µs CSVは新版のbyte単位完全prefix。
- 旧PWLの192 µs終端保持点を除く全点が、新30信号のprefixに一致。
- mapping_and_assumptions.jsonは旧版とbyte完全一致。
- 旧192 µsのbench/CSV/run log/PWL/mapping/criteriaは前回監査時SHA256と一致。
- 新版最終control event:253.281740 µs。全30 PWL最終点:256 µs。
- 元RTL13ファイルはmanifest SHA256と一致。
- 実224 µs deckのXA/XB/XC端子へ全30 controlが1回ずつ正しく接続。

新旧steady deckは改行コードに差がある。改行だけ正規化すると、差分はstopの160→224 µs変更と専用新版controls.incへのinclude変更のみ。tranのtstart=0、tmax=1 ns、回路、保存vector、数値設定は同一の行内容を保持した。

## 固定評価窓と包含

事前宣言された後半8周期窓は **159.318117〜221.818117 µs**。62.5 µsはCHOPの正確な8周期で、両端がCSV記録のCHOP立上りに一致。

評価窓終了221.818117 µs < 診断終了224 µs < 刺激終了256 µs。診断deckが `afe_rtl_startup_224us/controls.inc` をincludeし、全時間履歴保存の `tran 1n 224u 0 1n` であることを確認した。平均差・RMS・VCM等の判定閾値、4周期窓×2、待機と評価の分離は旧版と同一。

元160 µs試験の `periodicity_pass=false` と窓96.818117〜159.318117 µsは旧final_summary.jsonに保全されている。後半窓の試験は元の失敗を消さない。**実際の224 µs完走、定常性、stress結果は本監査の対象外。**

## 独立計算方法

MCLK立上りを `2000 + n × (1000 / 32.768)` nsとし、RTLの1 ps精度に丸める。3 µsのRESET_N解除後の2FF同期と最初のframe0、SPI mode0/MSB-firstの0x20/0x02/0x64、CS同期・edge detect・reg_we・register適用を独自に計算した。

CHOP/CHOP_OUTは3.068117 µsの初回以降128 MCLK間隔。初回BLANK=0を保ち、以後各edgeの1 MCLK前から7 MCLK後までblank。CSV全遷移を比較し、1.01 ps以内で一致した。実差は浮動小数演算の丸め程度。

PWL全(time, voltage)対を別に解析し、各CSV値のbit抽出、0〜1 µsの初期ramp、eventから0.5 nsの遷移を独自再構築した。時刻1e-16 s、電圧1e-12 V以内で全点照合。analogは実subcircuitのポート宣言と診断deckの位置引数を別に対応付けた。worker生成器を再実行して自己照合したものではない。

## 配列・初期値・時刻仮定

- CPF0,1,2,3はLSB順。reset8はCPF3のみHigh。
- biasのIB1,IB0,BP1,BP0,BN1,BN0はHigh,Low,Low,High,Low,High。
- CHOP_EN=1、OFM/OFS/OFEN=0。AFE_RSTはactive-high。
- CSVはRTL eventの2 ps後を記録。PWLは記録時刻から0.5 nsで遷移し、50%交点はRTL eventより約252 ps後。評価位相はCSV event基準で、analog 50%交点ではない。

## 範囲・制限

実eeg_digital_top replayだがCODE=16固定で、eeg_adc_dig/ADC/DWA閉ループ、system decimation/ENOBは含まない。CMP_STROBE、DAC_CLK、CHOP1、TEST_CFG、FIFO/rawは本AFE analogに未接続。MOSCAPはQ診断モデル、ITSTは電源ramp中も理想1 V源。AVDD/DVDD同時rampと理想control電圧を仮定し、physical digital buffer、独立DVDD配電網、pad/package/board/finite substrate、brownout、外部電極モデルを含まない。

analog収束、settling、利得、ENOB、寿命、製造可否は判定していない。さらに長い診断ではanalog時間だけでなくRTL/PWL刺激の有効期間も再確認する。

## 根拠

基準パス: C:\projects\ft\test1x。

- gf180/tapeout/rtl/eeg_digital_top.sv:67–80,127–129,209–243
- gf180/tapeout/rtl/eeg_spi_slave.sv:1–28,65–89,171–205
- gf180/tapeout/rtl/eeg_regs.sv:104–148
- gf180/tapeout/rtl/eeg_clkgen.sv:40–63,160–203
- gf180/tapeout/afe/eeg_afe.spice:302–335,376–384
- gf180/tapeout/afe/eeg_afe_clk.spice:22–79
- gf180/tapeout/bias/eeg_bias.spice:8–17,58–59
- Test-2-4/source/layout/chip_lay.py:565–573

詳細件数、実接続、閾値比較、改行比較、入力hash、前回監査への参照はsummary.json。
