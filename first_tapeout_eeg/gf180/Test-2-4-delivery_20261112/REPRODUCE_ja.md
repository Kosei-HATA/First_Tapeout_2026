# 再現と依存関係

## 1. 既存成果物の確認
このZIPを新しい空のディレクトリーに展開し、`python verify_manifest.py` を実行します。これは読取り専用の完全性検査です。
PNG/PDFは通常のviewer、GDS/lyrdb/lvsdbはKLayoutで開けます。生波形は大きいため、必要列だけを読むことを推奨します。読み出し例は既存の独立監査summaryの `method` を参照してください。

## 2. 元データを上書きしない
既存scriptには `/work/Test-2-4`, `/work/gf180`, `/foss/pdks/gf180mcuD` 等の絶対パスがあります。元プロジェクトをそのまま再実行すると既存log/summary/波形を更新するscriptがあります。
再現時はZIPのコピーを新しい実験専用workspaceに展開し、そのworkspaceだけをcontainerの `/work` にmountしてください。配布ZIP/元設計/既存結果はread-onlyの保管コピーを別に残してください。既存作業用containerの `/work` に上書きしないでください。

## 3. 必要環境
Linuxの既存iic-osic-tools相当環境とGF180MCU D PDKが前提です。このZIPはcontainer imageやPDK全体を含みません。
- KLayout実行ファイル: `/foss/tools/klayout/klayout`; Pythonの `klayout.db`, `klayout.rdb`。
- PDK: `/foss/pdks/gf180mcuD`。モデルコピーの記録revision: `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`。
- SPICE、Icarus Verilog/vvp、Netgen、Magic、OpenSTA等は各実行log/scriptのパス・optionを参照。
- Python、NumPy等。パッケージング端末のversionと実シミュレーション環境のversionは同一とは限りません。
- 主要224 µs波形で使用したngspice開発版commit: `8e03f9570eae8bb11dac18873587f052e7c8d02e`。表示はngspice-47+、KLUを含む。公式release 48と称しません。
- Magic比較: 旧8.3.664 / 新8.3.697。新commit `e400017fdfb221a410cce9e1674910fe70a14e7d`。詳細とPDK tech hashは `manufacturing_preflight/extraction/core_pex_probe/rc_diagnosis/magic_candidate/provenance_manifest.json`。
- 公式precheck imageは `ghcr.io/wafer-space/gf180mcu-precheck@sha256:e24fd3963dae3b0bad09d82178b34cab1a17f21b5fbed7111dceab07a70f5ca6`。全引数は `official_precheck/run_manifest.json`。

主要simulationモデル・回路deck・RTLの必要コピーは収録していますが、ツールsource/build/install/depsは省略しています。元のbuild/log/commit記録は保持しています。再buildには対応sourceと依存関係の準備が必要です。再現可能性の記録を整理したもので、新しい環境での完全再構築を今回検証したわけではありません。

## 4. 主要simulationの再解析
新規workspace内の `/work/Test-2-4` を使い、必要なPython依存を用意して実行します。
`python3 /work/Test-2-4/manufacturing_preflight/analog/analyze_afe_rtl_224us.py steady`
`python3 /work/Test-2-4/manufacturing_preflight/analog/analyze_afe_rtl_zero_recovery.py steady`

scriptが使用する絶対パス、入力hash、出力先を先に確認してください。保存rawの再解析であり、ngspiceの新規実行は不要です。出力log/summaryはコピー先で更新されます。

## 5. 主要simulationの再実行（必要なときのみ）
新規workspaceで正しいngspice buildを準備し、次を実行します。
`python3 /work/Test-2-4/manufacturing_preflight/analog/run_afe_rtl_224us.py`
`python3 /work/Test-2-4/manufacturing_preflight/analog/run_afe_rtl_zero_recovery.py`
実行後に上記再解析scriptを実行します。各試験は約25–35分を要した記録があり、端末・環境に依存します。各runの `tb.spice`, `.spiceinit`, `controls.inc`, `mapping_and_assumptions.json` を正本として条件を保持してください。

## 6. 物理検証の再実行
新規workspaceでGF180 PDKと元gf180プロジェクトの必要layout/reference入力を準備します。部分sourceだけで全GDSをゼロから再構築できるとは限りません。
`python3 /work/Test-2-4/scripts/reproduce_checks.py`
このhelperは新しい日時付き `rechecks` へGDSと基準をコピーして、導通・コアLVS・公開DRCを実行します。約90分の既存目安があります。KLayout/PDKが必要です。

Test2-3からECOそのものを再生成する場合のみ、同梱参照入力 `/work/Test2-3/gds/Test2-3.gds` が必要です。期待SHA-256: `1ec7bd329d5ee1ba7cf3ac39ab22a698fb91847c486b6ede2aa6c3fb2003277c`。
その入力を準備して別copyで `scripts/build_pad_eco.py` を実行します。最終GDSの受渡し/閲覧にはこの旧GDSは不要です。

## 7. 判定の範囲
プロセスexitcode=0だけで回路合格とはしません。DRC指摘数、LVS一致、導通、最後の時刻、有限値、固定評価窓と基準を照合してください。
Q診断モデルと仮起動条件の結果をfoundry/ボード承認に昇格させないでください。全チップLVS/PEX、ENOB、EM/IR、ESD、custom pad機械/ボンディング評価等の未確認範囲は最終PDFに記載しています。

## 8. 物理検証の追加入力
物理検証helperが参照する旧chip_topの圧縮GDS（元入力hash確認用）、OTA局所GDS（6ラベル復元用）、デジタルCDL2点を dependency_sources/gf180 に収録しています。これらは修正GDSの正本ではありません。新しい実験workspaceで dependency_sources/gf180 を /work/gf180 に配置してください。PDKのstandard-cell netlistやKLayout runset等は別途必要です。Test2-3の全GDSは reference/Test2-3/gds/Test2-3.gds に比較専用として収録しています。製造候補の正本は Test-2-4/gds/Test-2-4.gds です。


## 9. PNGの再生成と参照GDS

### 図02だけを保存geometryから再描画する最短経路
`changes/refresh_bridge_png_from_geometry.py` は `geometry_extract.json` と `render_gds_comparisons.py` を使い、図02の橋比較PNGだけを再描画します。元/Test2-3 GDSは不要です。KLayout、NumPy、Matplotlibは必要です。
成果物を保全するため `changes` を新しい作業フォルダーへコピーし、そのコピー上で `python3 refresh_bridge_png_from_geometry.py` を実行します。表示レイアウトを変えた場合は目視QAとhashを更新してください。これは保存済みgeometryからの再描画であり、GDS差分検証の再実行ではありません。

### 4図の全再生成・GDS差分再検証
`render_gds_comparisons.py` は3版のGDSを実際に読みます。ZIP直下の `changes` からそのまま実行すると、相対配置の前提が合いません。新しい作業rootを作り、script類を `<作業root>/Test-2-4/delivery_visuals_20261112/` へ配置してください。必要な入力は次のとおりです。
- `<作業root>/chip_top_fill_r6_20261026.gds`: 元GDS。SHA-256 `1343e9cc55cb2020f6213937c4622f2a126db6381ae66615719398aa6a027529`。ZIP内 `dependency_sources/gf180/tapeout/chip/gds/chip_top_fill_r6_20261026.gds.gz` を新作業rootへ解凍すれば復元できます。既存保存先は `C:\projects\ft\test1x\chip_top_fill_r6_20261026.gds`。
- `<作業root>/Test2-3/gds/Test2-3.gds`: 比較専用の中間版。ZIP内 `reference/Test2-3/gds/Test2-3.gds` をこの配置へコピーしてください。**製造候補の正本ではありません。** SHA-256 `1ec7bd329d5ee1ba7cf3ac39ab22a698fb91847c486b6ede2aa6c3fb2003277c`。既存保存先は `C:\projects\ft\test1x\Test2-3\gds\Test2-3.gds`。
- `<作業root>/Test-2-4/gds/Test-2-4.gds`: ZIP同梱の最終版。SHA-256 `7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755`。

記録環境はKLayout 0.30.9、Matplotlib 3.11.0です。Linux上で `MPLBACKEND=Agg python3 <作業root>/Test-2-4/delivery_visuals_20261112/render_gds_comparisons.py` を実行します。scriptは入力GDSを上書きせず、scriptと同じ出力フォルダーを更新します。最終目視QA/hashの更新は `changes/finalize_visual_manifest.py` の前提を確認し、実際に画像を目視したうえで行ってください。
geometry JSONは正確な抽出記録を含みますが、現在同梱のJSON専用helperが対応するのは図02のみです。4図すべてのJSON専用再描画経路が検証済みとは主張しません。
