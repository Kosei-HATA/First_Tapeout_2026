# Test-2-4 クロック75条件追補

## 結果
既存19件を入力・設定・波形再計算照合の上で再利用し、追加56件を4並列・各600秒上限で実行しました。追加実行時間は1704.5秒（28.4分）です。75件すべて500nsまで到達し、有限値・正の位相順序marginを確認。timeoutはありません。

最小marginは3.6V、FF/-20°C、HRLCで0.1563150767nsです。製品に必要なguardbandは未定義で、正であることは製造承認や全チップ精度の合格判定ではありません。

3.3V FF/-20°CのLRHC/LRLCはdynamic gmin警告が各2回ありますが、各々true gminで収束しています。元results.json/summary.jsonは保守的な警告検出を残し、最終監査はaudited_results.jsonとfinal_summary.jsonを参照してください。警告も元ログも保全しました。

## 数値収束対照
最悪条件の回路・刺激を保持し、1因子ずつ変更した2件を追加しました。
- maxstepを50psから25psへ半減: 最小margin 0.1559367495ns、基準との差 -0.378327ps。全10タイミング指標の最大差1.801352ps。
- reltolを1e-4から1e-5へ厳格化: 最小margin 0.1563095334ns、基準との差 -0.005543ps。全10指標の最大差2.869464ps。
いずれも500ns完走し正marginを維持。診断用5ps比較閾値内で、約156psの余裕がこの2つの数値設定に支配される兆候はありません。ただし同時変更の追加試験や製品guardband保証ではありません。

## 重要なモデル範囲
実bias回路の接続を用いますが、MOSCAPはmoscap_lin.spiceの線形定数C近似です。公式電圧依存MOSCAPでの起動成立は未検証です。この制約は45startup、実bias付き15条件、今回75条件、数値対照に適用されます。接続/LVS一致と使用モデル一致は別です。

PEXはクロック内部のみ。外部24MOSのD/G/S/B・寸法は独立CDLと照合済みですが、外部接合面積/周長は回路図近似、入力はVCM固定、上位配線・隣接結合・全供給網・パッケージを除外します。温度とprocessは5組の選択条件で、全process×全temperatureの直積ではありません。RC温度係数や全チップ閉ループ性能、ENOB、ばらつき認定も含みません。

## ファイル
- minimum_margins.csv / minimum_margins.json: 75条件の一覧。
- margin_heatmap.png: 15×5数値付きヒートマップ。注意事項付き、目視確認済み。
- audited_results.json / final_summary.json: 警告回復を監査した最終結果。
- reuse_audit.json / input_manifest.json / input_preservation.json: 19件再利用照合、入力hash、既存入力・ログ・波形の不変確認。
- moscap_scope_audit.json: 45起動デッキの線形MOSCAP確認。
- convergence_controls/results.json: 数値対照結果。
配布済みZIP・元GDS・PDK・元デッキ/ログは変更していません。
