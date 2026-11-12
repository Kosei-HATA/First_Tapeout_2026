# Test-2-4 製造前追加検証

**追補:** 全75条件、抵抗熱雑音、線形MOSCAPの制約は [FOLLOWUP_20261111.md](FOLLOWUP_20261111.md) を参照してください。

追加検証を完了した範囲と、製造前に残る確認事項をまとめます。**製造準備完了・16.5bit性能達成を認定するものではありません。**

納品GDSと元設計は変更していません。対象SHA-256は 7af0c9bb19fdb005f7b8d54fda6ef0f1d7ee24c68aedc2269310048d9e121755。前回納品ZIPも不変です。今回のZIPは追加検証の根拠集で、GDS原本の置換ではありません。

## 設計変更と物理検証

Test2-3のDVDDブリッジ4本と、Test-2-4のpad下M2/M3/M4ノッチ補完を維持しています。公開DRC177デッキの指摘0、core LVS合格、296点・20ネットの導通検査でopen/short 0は前回の結果です。

追加の固定版wafer.space公式precheckは16段階完了し、密度・ゼロ面積・アンテナ・Magic/KLayout DRCの各指摘0。公式KLayoutフローはCUP除外で、CUPを含む前回177デッキ検証とは別の証拠です。カスタムpadの機械・ボンディング適合は未承認です。仮ID FFFFFFFFを含むprecheck派生GDSは製造提出用原本ではありません。

DVDD供給2か所で各Via2/3/4に1,160カット、8つのtie分岐で各36 Via4を確認し、被覆欠落なし。電流分配・実負荷・温度を解いていないためEM/IR合格とはしません。

## DACと実bias

実biasの接続は現設計ですが、これらのbias/クロック試験はMOSCAPに供給された線形近似を使っています。公式非線形MOSCAPの起動を保証しません。実biasは15 PVT DCと45電源ランプケースを確認。ランプ後100µsのDCとの差は最大0.042731%で、診断閾値2%以内です。全チップ電源順序・brownout保証ではありません。

SS/FFのDAC電荷差8波形を独立積分し、別solver/刻みのFF pilot6件も確認しました。ただし極小残差の符号・細かな桁は安定していません。0.016 fC/toggleは旧セル由来、現公称セルで同比率なら約0.00814 fC。どちらも比較基準であり、現設計の承認済み性能仕様とは扱いません。

典型条件の全32コードで、電流、endpoint INL/DNL、隣接frameの安定性を測定しました。数値は下のJSON集計およびCSV/図を参照してください。これは5bit DACの名目・ミスマッチなし・理想仮想接地条件であり、ADCの16.5bit ENOBや実シリコン精度を示すものではありません。INL/DNLの製品許容値は未定義です。極小INL/DNL残差は数値感度に近く、実物のmicro-LSB精度は主張しません。

## 寄生抽出とクロック

旧Magic 8.3.664の結合容量二重計上を特定し、公式8.3.697を既存環境とは別にビルドしました。小構造6件・7負例に加えvia/分岐・RC cornerを監査。ADCの新旧容量差は側壁オフセット丸めで説明でき、元PDKは変更していません。nominalのvia抵抗は4.5Ω、highは15Ω、lowは0Ωという公式モデル指定です。全cornerが0ではありません。

実クロックは独立11端子・外部24MOSのD/G/S/B対応を確認。階層RC変換には子端子の接続不良が見つかり、不合格のまま保全しました。同じGDSのflat代替は独立LVS、MOS接続・容量保存、負例検出を通過しています。旧不合格版をシミュレーションに採用していません。

実bias/同一外部負荷で、固定nominal RCの15 PVT条件は全て正の位相margin。最小0.281959nsは3.6V FF/-20℃です。同条件で公式RC4cornerを追加すると、確認済み最小は高R・低Cの0.156315nsです。SPARSE/KLUの共通区間も診断許容差内でした。

この比較は内部クロックPEXのみです。外部TG拡散形状はschematic近似、入力は共通モード、上位配線・供給分布は除外。この後の追補で15条件×RC5cornersの全75組合せと数値収束対照を実施しました。必要guardbandの製品仕様、線形MOSCAP近似の妥当性、選択範囲外の動作条件は未認定です。

## 残る製造前確認

- 現行pad-ring RUN_2026-10-23_13-27-25の電源込みVerilog/ODB/configと、digital_top f2・adc_dig f3の最終SDC/SPEF/ETM/ODB。旧世代ODBや新PnR結果を現GDSの証拠には採用していません。
- 全チップ独立LVS、校正された全チップRC、配線込みSTA。既存の2マクロ×3corner STAはideal-wireスクリーニングです。
- 16.5bitシステムENOB・雑音・ミスマッチ、全電源網EM/IR、ESD・パッケージ・カスタムpad機械適合。
- 製造先の最終仕様と承認、die ID。外部提出・支払・契約締結は行っていません。

## 証拠と再現

各サブディレクトリのREADME、入力、スクリプト、ログ、JSONに条件・範囲・失敗した試行を残しています。`final_preflight_summary.json`が集計と原本ハッシュ、`STATUS_20261111.md`が経過、`README_initial_plan_20261111.md`が開始時計画です。

軽量ZIPでは大波形・大GDS・ビルド実行物などを省略し、SNAPSHOT_MANIFEST.jsonに収録ハッシュと除外理由を記録します。全生データはMY-NOTE-2のTest-2-4/manufacturing_preflightに保全。再実行には元gf180プロジェクト、固定PDK、記録されたツール/隔離Magicビルドが必要で、ZIP単体は完全な実行環境ではありません。

### DAC全32コードの集計

更新UTC: 2026-11-11T19:25:04.492200+00:00

- range_A: [-2.569923255790324e-05, 2.5699233863312022e-05]
- LSB_A: 1.6580150458456537e-06
- max_abs_INL_LSB: 1.125862145734402e-06
- max_abs_DNL_LSB: 1.0128894271099753e-06
- monotonic: true
- max_last_frame_delta_A: 5.087632111390114e-13
- input_hash_changed: []
- performance_acceptance_spec_defined: false
- ENOB_qualified: false

詳細: analog/dac_static_typical/final_summary.json
