# Test-2-4: GF180 DRC修正候補

## 目的と状態

Test2-3 の DVDD 接続修正を保持し、公開 DRC が検出した Bondpad_5LM 内 M2/M3/M4 の CUP.3 スロット違反を、同一パッド内への金属追加で解消する候補です。元の Test2-3 と元 PDK は変更していません。

このセルは標準 Bondpad_5LM から変更したカスタム形状です。セル名が同じでも、標準 PDK セルとしての認定を引き継ぐものではありません。製造・ボンディングの承認済みデータではありません。

## 成果物

- gds/Test-2-4.gds: 修正候補 GDS
- scripts/build_pad_eco.py: ハッシュで固定した Test2-3 から生成するパッド ECO
- source/layout/chip_lay.py: Test2-3 の DVDD 修正を含むソースの独立コピー
- source/dvdd_connection.patch: DVDD 修正差分
- scripts/audit_pad_eco.py: 元図形保全、変更範囲、パッド下非重複の監査
- scripts/check_connectivity.py: 実 GDS の296点・20ネット導通
- scripts/run_verification.py: コア LVS と全公開 DRC を含む検証
- functional/: 独立コピーを用いた回路レベル・デジタル機能再試験
- verification/: 実行状況、結果、データベースとログ

## 設計変更の根拠

既存 Bondpad_5LM の M2～M4 スロット0.3µmに対し、公開 cup.rb の CUP.3 は1µm未満を指摘します。CUP.2/3の閾値変更、ルール除外、waiver追加、guard marker追加はしていません。

パッドローカル領域 x=3.34～62µm、y=1.27～62.205µmと既存金属との差だけを追加しました。各層で元の単一金属ネットを維持し、元金属の削除はありません。ビア、PAD開口、最上層Metal5、コア回路は変更しません。

## CUP適用条件と製造上の留保

公式CUP章はパッド下に能動回路を置く場合の追加規則です。公開cup.rbは能動回路の有無を判定せずにCUP.2/3を検出します。本候補はパッド下にCOMP/Polyがない非CUPパッドとして監査します。

CUP.7aには下層金属ストライプ形状の推奨があり、スロットを埋めた本候補を「CUP全条件適合」とは主張しません。実際のボンディング方式、接合強度、ESD、EM/IR、製造サービスの承認は別途必要です。公開DRCの0指摘はこれらの承認を代替しません。

参考:
https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_09_3.html
https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_09_2.html

## 検証の解釈

実行中の状態は verification/jobs.json に保存します。終了コード0だけを合格としません。全DRCの指摘数、LVSの回路一致、導通の断線・短絡数と機能試験の数値判定を確認してください。

コアLVSはpad-ringを除外し、既存版と同じネット名対応と6つのラベル復元を使用します。296点導通は全デバイスLVSや電流容量の保証ではありません。回路レベル機能試験は実チップの全寄生・ノイズ・ENOBを保証しません。

## 再現

既存 iic-osic-tools コンテナの /work マウント内で実行します。

python3 /work/Test-2-4/scripts/build_pad_eco.py
python3 /work/Test-2-4/scripts/run_verification.py

元GDSは /work/Test2-3/gds/Test2-3.gds を使用します。完了した試験を再実行する場合は、古い検証結果を別フォルダーに保全し、同時実行中のプロセスがないことを確認してください。

## 最終結果（2026-11-11 再確認）

接続切断前の独立ジョブは2026-11-10に完走していました。2026-11-11に保存ログ、結果DB集計、全177デッキ、GDSハッシュを再確認しました。同じ長時間ジョブの重複実行はしていません。

- 全公開DRC: PASS、177/177デッキ完了、0指摘。CUP除外・waiver・閾値緩和なし。
- コアLVS: PASS、回路一致、必須19ポート欠落なし。
- 実GDS導通: 296点・20ネット、断線0・短絡0。
- 修正監査: M2/M3/M4の指定追加領域以外は図形・配置・階層・属性まで一致。元ビア・PAD開口・Metal5・DVDD修正を保持。
- 72個のボンド開口下にCOMP/Polyの重複なし。Metal5の2µm包囲不足なし。
- デジタルRTL/GL: 15/15 PASS。GL SPIは994,067サイクル、GLトップは1,380,777サイクル、各117信号一致。
- アナログ13ジョブとADC/AFEクロック2ジョブ: 実行成功。Quantizerは3条件×8判定で期待値一致。
- 元GDS、元chip_lay.py、Test2-3 GDSのハッシュ不変。

最終機械可読結果: verification/final_summary.json。
機能試験詳細: functional/functional_summary.json、functional/README.md。
修正候補GDSのSHA-256:
7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755

### 動作の見込みと未確認事項

回路一致、導通、デジタル比較試験、限定アナログ試験は正常動作を支持します。ただし、全チップの正確な動作や製造提出の承認を保証する結果ではありません。

ADCクロック最小余裕0.16ns、AFE最小VDS−VDSAT余裕0.07Vは正の測定値ですが、安全余裕の仕様値が未定義です。Reference差動0.4918～0.4940V、testmux最大誤差2.960mVも許容精度が未提供のため性能合格とは断定しません。Quantizerの24条件中1条件は初期状態が正しく遷移しないため、遷移遅延は未測定です。

全チップPEX、電源変動、Monte Carlo、ENOB、パッド/パッケージ寄生、EM/IR、全pad-ringデバイスLVS、ESD、ボンディングの機械的承認は未完です。DAC長時間試験は今回再実行していません。パッド金属追加で寄生容量が変わり得るため、精度を要求する用途では寄生込み検証を次段階としてください。

### 元結果を上書きしない再検証

既存コンテナで次を実行すると、時刻付き rechecks フォルダーにコピーを作り、導通・コアLVS・全DRCを再実行します。数十分から約90分の計算が必要です。

python3 /work/Test-2-4/scripts/reproduce_checks.py

これは既存 /work/gf180 と /foss/pdks/gf180mcuD、導入済みKLayout等を前提とします。配布物だけで全PDK・元プロジェクトまで自己完結するものではありません。機能試験は functional/README.md と各実行スクリプトを参照してください。
