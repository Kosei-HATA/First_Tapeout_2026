# Test-2-4 統合成果物

更新日: 2026-11-12
用途: 修正箇所の確認、設計候補の受渡し、既存検証結果とシミュレーション証拠の確認。

**製造・ボンディング承認用の最終サインオフではありません。** カスタムパッド、全チップLVS/PEX、ENOB、EM/IR、ESD、実ボード条件等に未確定事項があります。外部提出・購入・製造依頼は行っていません。

## 最初に開くもの
1. `Test-2-4/manufacturing_preflight/delivery_report_20261112/Test-2-4_verification_report_ja_20261112_final.pdf`: 最終日本語レポート（10ページ）。
2. `changes/`: 実GDSに基づく修正前後・差分PNGと、その読図説明。
3. `Test-2-4/gds/Test-2-4.gds`: 修正GDS本体。製造候補はこのファイルです。precheckが付加した仮ID付き派生GDSは収録していません。
4. `FILE_GUIDE_ja.md`: 証拠、主要波形、再現用入力の場所。
5. `REPRODUCE_ja.md`: 再現手順、環境依存、再実行時の注意。
6. `EXCLUDED_FILES.json`: 収録しなかった大波形・重複GDS・ビルド資材等の明細。
7. `MANIFEST_SHA256.json` と `verify_manifest.py`: 収録物のサイズとSHA-256照合。

## 今回の収録方針
最終GDS、layoutソース、修正script、DRC/LVS/導通結果、RTL/回路シミュレーション入力・小型結果・ログ・解析、最終PDF、修正比較PNGをまとめました。最終AFE 0 µV / +100 µVの224 µs生波形は、全列・全行を無加工で両方収録しています。CSVは拡張子がcsvですが、ngspice wrdata形式の空白区切りで、112列（56信号それぞれの時刻・値）です。

それ以外の1 MiB超のCSV生波形、重複/再生成可能な大GDS、ツールsource/build/install/deps、コンパイル済みRTL中間物、旧レポートは除外しました。小型結果・試験条件・デッキ・実行script・ログは可能な限り収録しています。除外は元ファイルの削除ではなく、元データはMY-NOTE-2の `C:\projects\ft\test1x\Test-2-4` に保全しています。全過去波形・全PDKを含む完全実行環境ではありません。

元の設計/波形/PDFは変更せず、別stagingへコピーしてZIPを作成しています。今回、新規シミュレーションやDRC/LVSの再実行はしていません。

## 結果を読む際の境界
- 公開DRC 177/177、指摘0。CUP除外・waiver・閾値緩和なし。
- コアLVS合格、296点・20ネットの導通検査はopen/short 0。全pad-ringを含む独立全デバイスLVSの保証ではありません。
- 0 / +100 µVの評価はAFE単体の仮定条件によるQ診断です。TT/27°C、3.3 V、理想共通AVSS、仮の起動手順、外付けVCM容量なし等の制限があります。
- +100 µVと0 µVの片側有限差分応答は平均約298.907 V/V（49.511 dB）。DC利得、0.5–100 Hz伝達、直線性、16.5 bit ENOBの認証ではありません。0入力のほぼゼロ残差を物理オフセット/ノイズ測定値とは扱いません。
- 旧160 µs試験の不合格や初期中断は消していません。過去README/summaryは時点別の記録です。全体の最新説明は上記の最終PDFを優先し、数値の根拠は対応する最終summary/独立監査を参照してください。

## 主要固定ハッシュ
GDS SHA-256: `7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755`

PDF SHA-256: `12b36e6f7028bcbdc334d8181a7cdaf941dcd69420f0205841f56e7018a6bce4`

展開後、このフォルダーで `python verify_manifest.py` を実行すると、収録全ファイルを照合します。検査結果はパッケージ内容の完全性を示すもので、回路性能/製造承認を示しません。

## 比較専用の参照GDS
`reference/Test2-3/gds/Test2-3.gds` はPNGの前後比較とECO再生成のための中間版です。製造候補の正本は `Test-2-4/gds/Test-2-4.gds` です。元GDSは `dependency_sources/gf180/tapeout/chip/gds/chip_top_fill_r6_20261026.gds.gz` として収録しています。これで比較に必要な3版を揃えていますが、PDK/ツールまで含む完全実行環境ではありません。
