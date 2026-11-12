# Test-2-4 公式製造前precheck（2026-11-11）

## 結果

厳密判定PASS。全16ステップ完走、コンテナ終了コード0、Precheck successfully completedを確認しました。MagicはDRC Checking DONEを確認しており、空レポートだけで成功としたものではありません。

密度、zero-area、antenna、Magic DRC、KLayout DRCの各指摘数はすべて0です。別実行のCoB 1x0p5 pad-mask幾何チェックもPASSです。開始01:58:54 UTC、終了03:26:44 UTC、約1時間28分でした。

## 条件と範囲

- 固定公式イメージ: ghcr.io/wafer-space/gf180mcu-precheck@sha256:e24fd3963dae3b0bad09d82178b34cab1a17f21b5fbed7111dceab07a70f5ca6
- イメージ版1.7.3、revision 8d58ff75fb9e2169a37876696eb470a42c6c9701。
- GF180MCU D、top chip_top、slot 1x0p5、WS_COB=false、WS_ID=FFFFFFFF。
- ネットワーク無効、入力GDS読取専用、新規コンテナと出力先を使用。
- 公式KLayout DRCは all,-antenna,-density,-cup。antenna/densityは独立ステップ。CUPはこの公式フローでは対象外で、別途保存済みの全177デッキCUP込み0指摘とは区別します。
- CoBマスク一致は幾何条件だけで、CoB採用や接合強度の承認ではありません。

入力GDS SHA-256:
7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755
実行後も一致し、元GDSは未変更です。

## 保存物・再現

- official_summary.json: 厳密結果、全ステップ、全メトリクス
- run_manifest.json: 正確なdocker引数、イメージ、入力/出力ハッシュと時刻
- official_precheck.log / container_state.json: 全実行ログと終了状態
- runs/verify_test24_20261111/: 各ステップの設定、ログ、結果、レポート
- cob_mask.log / cob_mask_state.json: 別CoB幾何チェック
- official_tool_hashes.txt: 使用したprecheck/マスク処理/ゴールデンマスクのハッシュ
- summarize.py: Magic完走、必要メトリクス、入力不変を確認する集計

再実行はrun_manifest.jsonの引数を基に、新しいコンテナ名、run-tag、出力先を使用してください。既存結果を上書きする再実行はしないでください。

Test-2-4_prechecked.gdsはID追加・dummy正規化を経た派生出力です。FFFFFFFFは仮IDで、製造提出用の確定IDではありません。元の納品GDSを自動置換していません。

## 留保

この結果は固定版のローカル製造前チェック合格であり、製造サービスへの提出・受理・契約・費用支払いは行っていません。ファウンドリ固有の承認、カスタムパッドの機械的接合評価、ESD/EM/IR、全チップ寄生込み性能を保証するものではありません。

Magicでは元設計由来の重複fill-instance警告16,175件があり、重複配置を無視して処理を続けています。チェックは正常完走して0指摘ですが、警告がないとは主張しません。
