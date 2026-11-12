# 成果物の案内

## 設計・物理検証
- `Test-2-4/gds/Test-2-4.gds`: 修正GDS。Test2-3のDVDD修正を維持し、Bondpad_5LMのM2/M3/M4の指定領域のみ金属を追加。
- `Test-2-4/source/layout/`: layoutソース。
- `Test-2-4/source/dvdd_connection.patch`: 先行DVDD修正の差分。
- `Test-2-4/scripts/build_pad_eco.py`: Test2-3からのパッドECO生成。
- `Test-2-4/scripts/audit_pad_eco.py`: 変更範囲、既存図形保全、単一接続成分等の監査。
- `Test-2-4/baseline/`: 変更監査/導通検査の基準。
- `Test-2-4/verification/final_summary.json`: 物理検証の集約。
- `Test-2-4/verification/full_drc.log`, `full_drc.lyrdb`, `drc_summary.json`: 公開DRC177デッキの実行・結果。
- `Test-2-4/verification/core_with_hints/`: コアLVSのデータベース、抽出netlist、log、summary。6個のネット名ヒントを使用した範囲を記録。
- `Test-2-4/verification/connectivity.json`: 全GDS296点・20ネットの導通確認。
- `Test-2-4/manufacturing_preflight/official_precheck/`: 固定公式precheckの設定・ログ・結果。CUPを除外した公式フローであり、別途の177デッキ検証と同一ではありません。

## 主要AFEシミュレーション
共通接頭辞: `Test-2-4/manufacturing_preflight/analog/`

+100 µV:
- `afe_rtl_startup_224us/steady/wave.csv`: 生波形の全列・全行。
- 同階層 `tb.spice`, `.spiceinit`, `run.log`: デッキ、solver初期化、実行ログ。
- `afe_rtl_startup_224us/controls.inc`, `mapping_and_assumptions.json`, `steady_criteria.json`: RTL波形・条件・事前評価基準。
- `afe_rtl_startup_224us/final_summary.json`
- `afe_rtl_startup_224us/independent_audit/periodicity_224us_v1/summary.json`: 固定8周期/7隣接比較の独立監査。

0 µV:
- `afe_rtl_zero_224us/recovery_run/steady/wave.csv`: 回復実行の生波形全列・全行。
- `afe_rtl_zero_224us/recovery_run/final_summary.json`
- `afe_rtl_zero_224us/recovery_run/independent_audit/offset_separation_v1/`: 0/+100 µV比較CSVと独立監査。
- 元の中断試行のstatus/logも保全してあり、最終波形とは区別します。

共通入力/再解析:
- `models/`: 使用したモデルコピー。
- `sim_work/gf180/tapeout/`: 使用した回路/benchコピー。
- `moscap_charge_equivalent/q_models.spice`, `bias_q_diagnostic.spice`: 診断用Qモデル。foundry承認済みモデルではありません。
- `run_afe_rtl_224us.py`, `run_afe_rtl_zero_recovery.py`: 実行script。
- `analyze_afe_rtl_224us.py`, `analyze_afe_rtl_zero_recovery.py`: 保存波形の解析script。
- `ngspice48_isolated/commit.txt`, `version.txt`, `build_isolated.sh`: 使用した開発版のcommit・表示version・build手順。ディレクトリ名48は正式version番号を意味しません。表示はngspice-47+です。

## その他のシミュレーション・検証
- `Test-2-4/functional/`: RTL/GL 15試験、回路レベル回帰、testbench、netlist、モデル、ログ、summary。
- `Test-2-4/manufacturing_preflight/analog/`: DAC32コード、ノイズ、MOSCAP、電源/起動対照等。
- `Test-2-4/manufacturing_preflight/bias_validation/`: biasのPVT/ランプ、clock PEXの75条件と数値対照。
- `Test-2-4/manufacturing_preflight/extraction/`: PEX抽出検証、負の対照、tool不具合診断。失敗した階層RC候補は失敗の記録として残しており、合格済みと読み替えません。
- `Test-2-4/manufacturing_preflight/digital_timing/`: ideal-wire STA/制約スクリーニング。post-route signoffではありません。
- `Test-2-4/manufacturing_preflight/operating_requirements/`: 既知RTL条件と未確定ボード条件の区分。
- `dependency_sources/gf180/tapeout/`: 再現の参照に使う元プロジェクトの関連テキストsource。元layout/chip_lay.pyと修正版source/layout/chip_lay.pyは役割が異なります。全プロジェクト/全GDS/PDKの代替ではありません。

生波形の除外は `EXCLUDED_FILES.json` を参照してください。未収録波形を必要とする過去解析は、このZIPだけでは再実行できません。

## 比較専用の参照GDS
`reference/Test2-3/gds/Test2-3.gds` はPNGの前後比較とECO再生成のための中間版です。製造候補の正本は `Test-2-4/gds/Test-2-4.gds` です。元GDSは `dependency_sources/gf180/tapeout/chip/gds/chip_top_fill_r6_20261026.gds.gz` として収録しています。これで比較に必要な3版を揃えていますが、PDK/ツールまで含む完全実行環境ではありません。
