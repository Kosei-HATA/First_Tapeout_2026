# Test-2-4 製造前アナログ追加検証

元の Test-2-4/functional と製造候補GDSは変更していません。独立コピーを用い、回路レベルの追加試験を行っています。PEX・製造承認・ENOB全条件合格を意味しません。

## 完了した試験

1. ADCクロック感度: 3.0/3.3/3.6V × typical27℃/SS85℃/FF−20℃/SF27℃/FS27℃の15条件。位相順序の余裕は全条件で正。最小0.146009ns（3.6V、FF、−20℃）。固定の理想バイアスとVCM1.65Vを維持した感度試験であり、全回路の電源追従を含むPVT試験ではありません。
2. 数値収束: FFの3.3V/3.6Vをreltol1e-5、出力刻み5ps、最大刻み25psで再計算。基準条件との差は−0.033ps/+0.432ps。3.6V最小余裕は0.146441ns。小さな正余裕を確認しただけで、必要安全余裕の認定ではありません。
3. DAC1 break-before-make: typical27℃/SS85℃/FF−20℃。BRK幅1.561/2.098/1.181ns。保存波形でcell0のD/DBが同時に0.7Vを超える点は0。これはゲート閾値による観測で、全31セルの電流・ミスマッチ・寄生込みの保証ではありません。
4. 元ベンチは解析後に波形を削除するため、波形保存だけを追加したコピーでDAC3条件を再取得しました。回路・モデル・solver設定は変更していません。

結果: analog_preflight_summary.json、clock_sensitivity.json、clock_convergence.json、dac_break_results.json、dac_trace/runs/。

## DAC even-charge 最終結果

2026-11-11 17:42 JST（08:42 UTC）に全8波形の独立積分と入力ハッシュを確認し、部分報告から最終報告へ更新しました。旧READMEと旧summaryは report_history/20261111T084247Z に保全しています。

- SS85℃: one-cell −0.000106071 fC/toggle、all-cells +0.000011114 fC/toggle。
- FF−20℃: one-cell −0.000100016 fC/toggle、all-cells −0.000103266 fC/toggle。
- 4結果すべて絶対値0.016 fC/toggleの設計基準内。最大絶対値は0.000106071 fC/toggle。
- 各条件4波形、合計8波形を完走。独立積分値は元runnerの値と一致。差分toggle数32、all-cellsの正規化セル数31、積分時間窓をJSONに記録しています。
- 保存済み53入力ファイルのSHA-256不変。Test-2-4 GDSのSHA-256も納品版と一致。

これは3.3V、理想virtual-ground出力と理想reference、既定tolerance A、72フレームの回路レベル試験です。別solver設定でのDAC電荷誤差の数値収束、mismatch、PEX、全コードINL/DNL、デバイス雑音、システムENOBは認定していません。厳密条件での再測定を行ったのは上記クロック2条件です。

最終結果: analog_preflight_summary.json、dac_even_results.json、dac_even_independent_final.json。
全8波形: dac_even/runs/。波形ハッシュ・サイズ・終端時刻・点数は最終summaryに記録。

過去のtypical結果（verification_20261029/source_followup/dac1_even_typical.log）はone-cell +0.00005 fC、all-cells約0 fCですが、今回の新規測定ではありません。
## 性能目標と不足

requirements_audit.json は元設計資料の16.5bit、SNDR101.1008dB、0.5–100Hz、0.943396mVpk、残留5.8768nVrmsという目標を整理しています。資料の古い512kHz条件は現RTLで1.024MHzへ更新され、MCLK32.768MHz/32、R1024、出力1kSPSと整合します。これは資料の設計意図の整合確認であり、現GDSが16.5bitを達成した証明ではありません。

4秒（低周波20秒）の連続ノイズ込み検証、実装デシメータ、数値収束、信号周波数/振幅掃引、ミスマッチ/電源変動/寄生込みの条件は未完です。既存70µs・16kHzのe2eベンチは短窓機能評価で、帯域内ENOB認定とは異なります。既存e2eにはXSPICE DWA制御と線形MOSCAP近似があり、通常のtranだけではデバイス雑音が含まれません。

純抵抗の外部source雑音は別会計です。27℃、差動総抵抗100kΩ、0.5–100Hzの熱雑音だけで約406nVrmsとなります。チップ固有16.5bitと電極/source込み性能を混同しないでください。この計算は実際の電極の測定結果でも、チップの不良判定でもありません。

## 再現

既存 iic-osic-tools コンテナの /work と保存モデルを使用します。元結果を残して新しい出力先を指定し、同じジョブが動いていないことを確認してから各run_*.pyを実行してください。入力コピーのハッシュはinput_manifest.jsonに記録しています。
