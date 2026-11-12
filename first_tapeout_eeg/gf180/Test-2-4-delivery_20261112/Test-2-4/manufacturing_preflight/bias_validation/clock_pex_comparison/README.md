# ADCクロック内部PEXと同一負荷の名目比較

条件: 3.3 V、typical、27℃、既存の実bias回路＋OTAモデル。CHOP1は100ns/300nsに切替、同一刺激・同一負荷で500nsを計算しました。変更はクロック定義のinclude先のみです。

## 事前監査

独立CDLとベンチの24個の外部TG MOSについてD/G/S/B、モデル、合計W、Lが全件一致（load_audit.json）。I1P/I1Nは元ベンチどおり両方VCMへ接続し、OTAの内部S/Dノードは動的に計算しています。全チップ閉ループの入力軌跡ではありません。

抽出は接続監査済みflat/rc.spiceのみを使用。欠陥のある階層RC版は不使用。C-only/RCの486MOS全パラメータは一致し、W=1～10µm、L=.28～4µm、AD/AS=.26～4.5µm²、PD/PS=1.52～20.9µm、nf=m=1。元wrapperはSI値をm0へそのまま渡します。寄生RCは一度だけ含め、削除・閾値変更はしていません。

## 名目結果

- schematic: 12.97秒、最小位相margin 0.228482ns、A→B overlap 5.768963ns、driver電荷14.0552pC/edge。
- C-only: 31.84秒、最小margin 0.573465ns、overlap 7.889296ns、15.9882pC/edge。
- flat-RC（KLU）: 133.81秒、最小margin 0.473643ns、overlap 7.913965ns、16.1003pC/edge。

3版とも位相順序の診断値は正です。C-only/RCとschematicの差には抽出された内部接合幾何も含まれます。C-only→RCの差が同一抽出MOS上の配線抵抗/分布容量化による差です。

## solver診断

元SPARSE1.3は300秒で267nsに達して上限停止。切替波形はtran完了後のwrdata方式だったため未保存ですが、ログ・DC出力は保持しました。KLUは回路・reltol=1e-4・maxstep=0.05nsを変えず完走しました。

SPARSEで同一回路を160nsまで再計算（196.14秒）し、KLUの0～160nsと5psグリッド補間で照合。A→B時刻/marginの最大差0.0000229ns、最大出力電圧差0.1154mV。定常部最大差は約0.0000441mV。診断許容差50ps、50mV、定常1mVを満たしました。tstopと適応刻みが異なるので完全同一波形の要求ではありません。300nsの逆方向切替はこのsolver照合範囲外です。

## 限界

外部TGのAD/AS等はschematic近似、上位出力配線・隣接結合・供給分布・パッケージを除外しています。寄生はこの小クロック内部のみ。供給されたOTA負荷モデルと共通モード入力での限定的な診断結果であり、全チップPEX/PVT、ENOB、製造承認ではありません。最小guardbandの製品仕様も未確定です。

主な機械可読結果: results.json、solver_comparison.json、mos_units_audit.json、load_audit.json、comparison_inputs.json、runtime_diagnostic.json。各サブフォルダーにデッキ・ログ・波形を保持しています。

## 固定nominal RCでの15条件PVT（追加完了）

nominal RCファイルを同一ハッシュで固定し、3.0/3.3/3.6 V × typical/27℃・SS/85℃・FF/−20℃・SF/27℃・FS/27℃の15条件を実bias/OTA負荷で実行。名目1条件は上記完走結果を再利用し、残14条件を最大2並列、1件600秒上限で計算しました。追加runは140～153秒/件、全15件exit0、全位相margin正、timeout/失敗なし。

最小marginは3.6 V、FF/−20℃で0.281959 ns。対応するschematic診断は0.143513 nsでした。寄生が追加されたことで特定の位相間余裕が増える一方、overlapや遅延も変わるため、精度改善を意味するものではありません。

結果: fixed_nominal_rc_pvt/final_summary.json。生データ・実行記録は同フォルダーの各条件に保存。RCハッシュ不変を実行終了時に確認しました。

これはdevice corner/温度/電源を振った「nominal RC固定」の評価です。RC low/highやR/C温度変動は未包含で、全PVT組合せの網羅ではありません。外部OTAの拡散形状近似、共通モード入力、上位配線除外の制約は変わりません。3.0/3.6 Vは探索的境界で、全analog動作仕様として独立確認されたものではありません。製造承認や全チップPVT認定ではありません。

## 公式RC4corner感度（追加完了）

nominal RCの15条件で最小marginだった3.6 V、FF/−20℃を固定し、公式抽出style hrhc/hrlc/lrhc/lrlcの4件を比較しました。各デッキは接続・容量保存・独立MOS LVS監査に合格し、全486MOSのパラメータ集合がnominalと一致。入力ハッシュは実行後も不変です。変更はRC include先のみで、名目結果は再利用しています。

最小位相margin:
- nominal: 0.281959 ns
- hrhc: 0.198300 ns
- hrlc: 0.156315 ns
- lrhc: 0.364957 ns
- lrlc: 0.323047 ns

全4追加runがexit0、有限波形、正のmargin。失敗・timeoutなし、実行時間93～159秒/件。最悪hrlcではB→A margin1が名目より0.125644 ns小さくなりました。

結果: rc_corner_sensitivity/final_summary.json、results.json、approved_inputs.json。各cornerの全デッキ・ログ・波形を同フォルダーに保存しています。

これは選択したdevice条件でのRC感度です。15 device条件×4 RC cornerの全組合せを走らせた結果ではありません。low-Rのcontact抵抗0は公式cornerモデルの境界であり、物理抵抗0を保証しません。正の位相marginだけで製品の必要guardband・全chip signoff・ENOBを認定することはできません。


## MOSCAPモデルの適用範囲（追補）
45件の起動試験、実bias付き15/75条件クロック試験はmoscap_lin.spiceの線形定数C近似です。公式MOSCAPの電圧依存モデルによる動作成立を示しません。回路ソースや配線の一致とモデルの一致は別です。元デッキ・波形・数値結果は変更していません。
