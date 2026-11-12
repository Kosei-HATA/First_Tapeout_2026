# Test-2-4 動作・起動条件の資料調査

## 結論

既存資料から **3.3 V公称、RTLのreset/clock動作、外部参照とVCMの設計構成** を確認した。一方、実ボードのAVDD/DVDD許容範囲、電源・参照の立上げ順序、電極common-mode、package/board PDNの確定条件は見つからなかった。

3.0/3.3/3.6 Vの既存検証点と100 nsの診断rampを、確定した製品動作範囲や実ボード起動仕様として扱ってはならない。本資料は既存資料の調査結果であり、新しいユーザー要求、製造承認、過渡信頼性の合否判定ではない。

起動条件の一覧は [startup_conditions.md](startup_conditions.md)、構造化した根拠と未取得条件は [summary.json](summary.json) を参照。

## 1. 電源電圧

### 既存資料に明記された事項

- 旧acceptance baselineの電源は3.3 V。`Test-2-4/manufacturing_preflight/analog/acceptance_source.json:23-36`、特に29行。
- digitalの公称DVDDは3.3 V。`gf180/tapeout/rtl/README.md:166`。
- digital STAは3.0/3.3/3.6 VのLiberty cornerを使用。同README:166。これはanalog全体の保証動作範囲を定義しない。
- `Test-2-4/manufacturing_preflight/analog/clock_sensitivity.json:2` は3.0/3.6 Vをdigital資料由来の探索的境界とし、confirmed full analog specificationではないと明記する。

### 試験条件であって実ボード要求ではない事項

- 旧bias起動試験は0→3.3 Vを10 µsで上昇させる。`gf180/tapeout/sim/bias/bias_check.py:6,51-52`。
- 最新起動診断は0→3.6 Vを100 nsで上昇させる。`Test-2-4/manufacturing_preflight/analog/afe_lvs_startup_controls/ramped_refs_reset/tb.spice:15`。
- 許容ramp-rateのmin/max、AVDDとDVDDの投入順序、brownout条件は未確認。

## 2. RTLのreset/clock仕様

根拠は `gf180/tapeout/rtl/README.md` と対応RTL。README、`eeg_digital_top.sv`、`eeg_regs.sv`、`eeg_clkgen.sv` が `Test-2-4/functional/rtl_tests/` の同名コピーとSHA256一致することを確認した。ハッシュはsummary.jsonに記録する。

- 外部MCLKは32.768 MHzで、唯一のclock。README:41。
- RESET_Nは非同期assert、2FF同期deassert。README:42、`eeg_digital_top.sv:67-80`。
- reset中はCMP_STROBE/DAC_CLK/CHOP/CHOP_OUT=0、CHOP_BLANK=0。AFE_RST=1、CHOP_EN=1、CHOP_DLY=0、BLANK_LEN=7。README:88-97、`eeg_regs.sv:104-123`。
- AFE_RSTはCONTROL bit4であり、reset後に経過時間で自動解除されない。register writeで変更する。`eeg_regs.sv:130-137`。
- 内部同期reset解除後、最初のMCLK edgeでframe 0が開始しCHOPが上昇する。README:128。
- CHOP_DLY=0時の最初のCHOP_OUT立上りだけはblankされず、その時点でAFE_RST=1を保持するという設計説明がある。README:140-142、`eeg_clkgen.sv:55-63`。
- 通常のCHOP_BLANKはCHOP_OUT edgeの1 MCLK前に開始し、BLANK_LEN MCLK後まで継続する。README:140。
- CHOP/CHOP_OUT生成はCHOP_ENに関係なく継続する。README:416。CHOP_EN=0を「全clock停止」とみなさない。
- CHOP_DLYの運転中変更では短いCHOP_OUT位相が生じ得るため、必要ならAFE_RST=1で設定するという既存説明がある。README:138、`eeg_clkgen.sv:37-38`。

### 現在の診断benchとの区別

`afe_lvs_startup_controls/ramped_refs_reset/tb.spice:15-17,33-36` は、100 nsの電源ramp中にBLANKを約19.5 ns、CHOPを50 nsで開始し、AFE_RSTを7.8125 µsで解除する。

これは外部RESET_N、内部reset synchronizer、SPIによるAFE_RST解除までを再現した完全なRTL/board起動シミュレーションではない。ただし、これだけで実運用における違反を断定できるわけでもない。RESET_Nの解除条件、MCLK投入条件、AFE_RSTを解除するSPI手順と時刻が必要である。

最新診断READMEも、これを未確定の診断sequenceとして扱っている。`Test-2-4/manufacturing_preflight/analog/afe_lvs_startup_controls/README.md:19,45-57`。

## 3. 外部参照と電極common-mode

### 設計構成

- VREFP/VREFNは外部低雑音源からpad経由で供給する。`gf180/tapeout/adc/eeg_ref.spice:4-18`。
- 同ファイル:15-18には外部差動参照noise≤375 nVrmsという旧要求の記載がある。元の `documentation/gf180_dac1_ref_20261022.md` は対象内で見つからず、現在の性能目標との再照合が必要。記述される帯域も原文どおり「signal周辺のband」であり、ここで別の帯域や確定仕様を付与しない。
- VCMはVREFP/VREFNの100 kΩ×2 dividerによるmidpointで、VCM padに外付けdecoupleする設計。`gf180/tapeout/bias/eeg_bias.spice:30,161-163`。

### 試験条件

- 外部参照1.9/1.4 Vは既存benchのnominal。`gf180/tapeout/sim/ref/ref_check.py:29,52-57`。
- 旧AFE benchは固定CM=1.65 V。`gf180/tapeout/sim/afe/afe_offset.py:89,97-100`。
- 最新benchのEP/ENは実bias生成VCMを基準とするdependent source。`afe_lvs_startup_controls/ramped_refs_reset/tb.spice:19,39-40`。外部電極common-modeを独立に規定するモデルではない。

### 未取得

参照の絶対許容範囲・精度・AVDDに対する投入順序・settling、VCM外付け容量/ESR、実電極のcommon-mode範囲、電源OFF/起動時の電極状態やCM拘束回路は未確認。

## 4. package/board電源条件

`gf180/tapeout/sim/afe/supply_check.py:6-16,27-30,157-164` に以下の旧モデルと設計意図がある。実packageの採寸値やboard保証仕様とは区別する。

| 項目 | 旧モデル/既定値 | 根拠行 |
|---|---|---|
| package位置の電源 | 理想3.3 V | 6-16 |
| bondwire | AVDD/AVSS各側3並列、各2 nH/0.1 Ω | 158-160 |
| pad/ESD容量 | 3 pF/pad | 161 |
| amplifier local decap | 200 pF | 157 |
| 他回路decap/負荷 | 100 pF、5 mA DC | 162-163 |
| on-chip rail抵抗 | 各側0.3 Ω | 164 |
| clock supply/return分離 | 各側100 Ω、150 pFを採用と記載 | 27-30 |

`Test-2-4/source/layout/chip_lay.py:7-9` はAVDD×3、AVSS×3のpad構成を記載する。pad cell名のasig_5p0を、5 V電源動作許可と解釈しない。

現LVSの対応は `Test-2-4/manufacturing_preflight/analog/clock_supply_model_reconciliation.json:28-44`。AVSS_CLKとDVSSはAVSSへtieされ、RCKN両端もAVSSである。旧分離return意図との差異と、有限substrate/rail/package impedance未抽出という状態は未解決のまま。

参照電源の別の試験モデルでは、外部参照ごとに2 nH/0.2 Ωを用いる。`gf180/tapeout/sim/ref/ref_check.py:4-5,52-57`。AFE供給モデルのbondwire値と混同せず、実package値と断定しない。

## 5. 次に必要な最小入力

1. AVDD/DVDDのmin/nom/max、ramp範囲、rail間順序、brownout動作。
2. 外部refsの精度・起動順序・settling、VCM外付け部品。
3. RESET_N解除条件、MCLK開始条件、AFE_RST解除のSPI手順。
4. 電極common-modeと電源OFF/起動時の接続条件。
5. 実package/bondwire/board PDN、transient reliabilityの寿命・duty基準。

既知RTL仕様を起動条件表へ反映し、未知board条件だけを確認対象にする。追加のparameter sweep、GDS変更、信頼性合否判定を本調査から自動的に正当化しない。

## 探索範囲・限界

- 対象コンピューター: MY-NOTE-2。対象ルート: `C:\projects\ft\test1x`。
- 主にgf180/tapeout、Test-2-4のsource/functional/manufacturing_preflight、Test2-3、verification_20261029を調査。
- tools、ngspice48_isolated、一部dependency/source_tcl等を除いた列挙で9,743ファイルを確認し、関連文書・回路・RTL・試験生成スクリプトを選択して内容を調べた。全9,743ファイルの全文精読ではない。
- 対象内でboard schematic/PCB、製品datasheet、参照先 `documentation/gf180_test_decap_20261022.md` と `documentation/gf180_dac1_ref_20261022.md` は見つからなかった。
- `test1x/documentation` が存在しないことを確認。補助的に確認した隣接 `test1/documentation` と `First_Tapeout_2026-f6437bdb182aad42397867cce8e94290f2b97bb0/documentation` も存在しなかった。隣接repository全体やarchiveを完全調査したという意味ではない。
- 「未確認」は、ユーザーの運用条件が存在しないという断定ではなく、今回の対象資料から確定できないという意味。
- 原設計・GDS・既存bench・既存結果は変更していない。本フォルダの報告3ファイルのみを追加した。