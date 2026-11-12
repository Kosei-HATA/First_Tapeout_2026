# DAC1 全32コード静的試験
全32件正常終了。typical/27C/3.3V、12frame/コード、理想参照源・理想仮想接地、ミスマッチ無効。元入力53hashは不変。4コードpilot結果を再利用し、重複実行なし。最大2並列。

## 結果
単調性: 全隣接コードで正の差。
差動平均電流: -25.6992326～+25.6992339 uA。
endpoint LSB: 1.65801505 uA。
最大絶対endpoint INL: 1.12586215e-6 LSB。
最大絶対DNL: 1.01288943e-6 LSB。
最終隣接frame平均差最大: 0.508763 pA (約3.07e-7 LSB)。
微小INL/DNLは数値積分感度に近い残差であり、実物のmicro-LSB精度や16.5bit ADC性能の証拠ではない。具体的な静的許容仕様が未確定なので性能合否は設定していない。

## 定義
集計J=i(VOP)-i(VON)。per-run result.jsonのJ_Aは逆符号なので、summary/CSVで統一した。
frame9/10の各全周期平均を平均。積分境界はT0+j*T+4*TM、端点を線形補間。breakを含む周期平均と平坦部平均は別。
LSB=(J31-J0)/31、INL=(Jk-J0)/LSB-k、DNL=(Jk-J(k-1))/LSB-1。
settlingは最終隣接frame平均差であり、コード変更後の過渡settling時間や負荷駆動保証ではない。

## 階層multiplier警告
multiplier_audit/expanded.logで全659 MOSの有効m=1を確認。上位DACにm>1指定なし、nfスケーリングは別に維持されている。PDK wrapper既定m=1による警告について、このDACで倍率喪失を認めない。他回路へ一般化しない。モデルやPDKを警告抑制のため改変していない。

## 成果
final_summary.jsonが統合報告用、summary.json、codes.csv、static_metrics.png、各code_XXのdeck/waveform/log/result。
再現: analog/run_dac_static_typical.py --all、analog/summarize_dac_static.py。
既存resultを再利用するため、別条件の検証は新しい出力先を使うこと。
PEX、ノイズ、製造ミスマッチ、DWA、有限参照インピーダンス、実OTA負荷、供給/温度全域、ADC閉ループSNDRは含まない。
