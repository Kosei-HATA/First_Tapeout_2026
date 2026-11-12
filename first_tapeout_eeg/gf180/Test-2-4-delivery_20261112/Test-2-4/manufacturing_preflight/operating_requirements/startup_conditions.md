# 起動条件表: 既知RTL仕様と未取得board条件

## 読み方

「資料に明記」は既存設計資料または実装に書かれた事項であり、実ボード全体の承認済み仕様を意味しない。「bench条件」は診断の入力であり、運用上の要求に昇格しない。全パスは `C:\projects\ft\test1x` 基準。

| 起動項目 | 資料に明記された設計/RTL | 現benchまたは旧モデルの条件 | 実ボードで未取得の条件 | 根拠 |
|---|---|---|---|---|
| AVDD/DVDD | 旧baseline 3.3 V、digital DVDD公称3.3 V | analog探索点3.0/3.3/3.6 V | min/max、rail間順序、許容差、brownout | analog/acceptance_source.json:23-36、gf180/tapeout/rtl/README.md:166、analog/clock_sensitivity.json:2 |
| 電源ramp | 許容範囲の記載を未発見 | 旧bias試験10 µs、最新診断100 ns | 最短/最長ramp、投入/遮断時の波形 | gf180/tapeout/sim/bias/bias_check.py:6,51-52、startup bench:15 |
| VREFP/VREFN | 外部低雑音源からpad経由 | 1.9/1.4 V。最新変更ケースでは100 ns比例ramp | 精度、許容電圧、AVDDとの順序、settling判定 | gf180/tapeout/adc/eeg_ref.spice:4-18、gf180/tapeout/sim/ref/ref_check.py:29,52-57、startup bench:16-17 |
| VCM | VREFP/VREFNの100 kΩ×2 midpoint、padで外付けdecouple | 最新benchはbias回路から生成 | 外付け容量/ESR、起動時定数、外部負荷 | gf180/tapeout/bias/eeg_bias.spice:30,161-163、startup bench:19 |
| 電極common-mode | 許容範囲の記載を未発見 | 旧AFEは固定1.65 V、最新EP/ENはVCM基準のdependent source | 電源OFF/起動時の接続、CM拘束、範囲、source impedance | gf180/tapeout/sim/afe/afe_offset.py:89,97-100、startup bench:39-40 |
| 外部MCLK | 32.768 MHz、唯一のclock | 最新AFE診断はMCLK/RTLそのものではなく理想CHOP/BLANK源 | 電源/参照に対する開始条件、停止時状態、外部レベル | gf180/tapeout/rtl/README.md:41、startup bench:33-35 |
| RESET_N | 非同期assert、2FF同期deassert | 最新AFE単体benchでは外部RESET_Nと同期器を未実装 | assertion幅、解除までの電源/参照安定条件、brownout再assert | gf180/tapeout/rtl/eeg_digital_top.sv:67-80 |
| reset保持中 | CHOP/CHOP_OUT/CMP_STROBE/DAC_CLK/CHOP_BLANK=0、AFE_RST/CHOP_EN=1 | 診断では供給ramp中の約19.5 nsでBLANK、50 nsでCHOP開始 | 電源投入中にRTL reset状態をいつから保証するか | gf180/tapeout/rtl/README.md:88-97、startup bench:33-36 |
| 内部同期reset解除直後 | 最初のMCLKでframe 0/CHOP開始。CHOP_DLY=0の初回CHOP_OUTだけblankなし、AFE_RST=1を前提 | 完全なRTL reset sequenceを再現していない | 外部RESET_N解除時刻とMCLK位相 | gf180/tapeout/rtl/README.md:128,140-142、eeg_clkgen.sv:55-63 |
| AFE_RST解除 | CONTROL bit4、reset値1、register writeで変更 | 最新benchは7.8125 µsで解除 | SPI手順、解除時刻、bias/VCM/ref安定判定 | gf180/tapeout/rtl/eeg_regs.sv:104-123,130-137、startup bench:36 |
| 通常blank | CHOP_OUTの1 MCLK前からBLANK_LEN MCLK後、reset値7 | 理想波形源による指定 | analog側で必要なguardband、rail非定常時の成立条件 | gf180/tapeout/rtl/README.md:140、eeg_regs.sv:117 |
| CHOP_EN | CHOP/CHOP_OUT生成自体はCHOP_ENに依存せず継続 | clock停止命令とはみなさない | board起動手順での使用意図 | gf180/tapeout/rtl/README.md:416 |
| clock supply/return | 旧設計は分離return、現LVSはAVSS_CLK/DVSSをAVSSへtie | 最新診断は共通AVSS、有限substrate/rail/package impedanceなし | 設計意図の確定、物理impedance | analog/clock_supply_model_reconciliation.json:28-44 |
| package/board PDN | AVDD×3/AVSS×3 padという設計 | 旧モデルは理想3.3 V、各側3並列bondwire 2 nH/0.1 Ω等 | 実package、wire、board regulator/decap/配線、許容bounce | Test-2-4/source/layout/chip_lay.py:7-9、gf180/tapeout/sim/afe/supply_check.py:6-16,157-164 |
| 過渡信頼性 | 現記録はQ-diagnosticでありphysical lifetime判定ではない | 3.6 Vで短いgate-pair excursionを記録 | 適用transient基準、duty/lifetime、モデル妥当性 | analog/afe_lvs_startup_controls/README.md:34-37,53-58 |

省略パス:
- `analog/` = `Test-2-4/manufacturing_preflight/analog/`
- `startup bench` = `Test-2-4/manufacturing_preflight/analog/afe_lvs_startup_controls/ramped_refs_reset/tb.spice`
- `eeg_clkgen.sv` / `eeg_regs.sv` = `gf180/tapeout/rtl/` 内の同名ファイル

## 使用上の注意

既知のRTL動作を取り込んだ試験を作る場合も、未知の電源・参照・電極条件は仮定として明示する。資料に記載された3.3 V公称だけからAVDD/DVDDの順序やramp-rateを補わない。初回CHOP_OUTがblankされない設計とAFE_RST保持を両方保存し、都合のよいblank追加による試験結果を元設計の結果と混同しない。