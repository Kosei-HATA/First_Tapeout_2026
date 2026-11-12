# GF180MCU 3.3 V MOS 過渡信頼性の公開資料調査

調査日：2026-11-11  
対象：Test-2-4 manufacturing_preflight の current-LVS / integral-Q 過渡診断。  
この文書は公開資料と使用中PDKの読み取り調査を保存したものです。製造承認、寿命認定、設計変更、foundryへの問い合わせを行った記録ではありません。

## 結論

公開資料だけでは、今回の短時間超過を信頼性合格にも不合格にも確定できません。3.63 V は薄膜酸化膜MOSの DC gate-to-any-node 上限です。公式資料は周期的超過の可能性を認めていますが、今回確認した公開資料とモデルからは定量TDDB条件を得られませんでした。

「短時間なので許容」として処理せず、**過渡信頼性未承認**を維持します。同時に、3.63 V を瞬時絶対最大値と読み替えて、今回の波形だけから物理破壊を断定することもしません。現時点の証拠は、追加評価が必要なDC基準超過を検出した診断結果です。

## 公式資料の根拠

### DRM §14.1 Chip Operating Conditions

URL: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_14_1.html  
原文ソース: https://gf180mcu-pdk.readthedocs.io/en/latest/_sources/physical_verification/design_manual/drm_14_1.rst.txt

- §14.1.4.2：薄膜酸化膜では、gateと他の任意FET端子間のDC電圧絶対値上限が3.63 V。VGS/VGDだけでなくVGBも対象です。
- 同節は周期的超過が許され得ること、過電圧値がdutyに依存すること、そのdutyがDC上限を超えて動作する時間割合であることを説明しています。
- 正確な原文抜粋1：“allowed to periodically exceed the maximum DC values”
- 正確な原文抜粋2：“Maximum allowable duty cycle will depend upon TDDB lifetime at that duty cycle.”
- 同節とその原文には、許容電圧対dutyの数値曲線、TDDB係数、目標寿命、故障確率、面積依存、温度加速条件、単発パルス上限がありません。公開資料全体に絶対存在しないとの断定ではなく、今回確認した範囲では取得できなかったという結論です。
- §14.1.4.1：HCI劣化はVDSとhot carrierを生成しながら導通する時間割合に依存します。短L、双方向動作、遅い遷移、高負荷等への注意があります。VGBのピークとdutyだけでHCI寿命は評価できません。
- §14.1.1：通常設計温度は−40～125℃。0℃未満は別文書 R-QR-MI-008 のHCI指針参照を要求しています。今回の公開検索では、その本文を取得できませんでした。
- §14.1.2：LV nominal 3.3 V、電源overshoot tolerance 10%。これは、3.63 Vを超える任意の内部過渡波形への包括許可ではありません。
- §14.1.3：burn-inの150℃、1.1×VDDはburn-in条件です。通常運用の過渡寿命認定には転用できません。

### 電気仕様 §5.4 Oxide Breakdown Voltage

URL: https://gf180mcu-pdk.readthedocs.io/en/latest/analog/spice/elec_specs/elec_specs_5_4.html

同表のBVoxはTDDBの長期使用許容値ではありません。7 V等の破壊電圧から3.665 Vの寿命安全性を推定するのは不適切です。

### モデル抽出説明 §2.1 MOSFET Model Extraction

URL: https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_1.html

モデルは−40/25/125℃におけるDC I-V測定、形状・端子bias条件、EP targetへの調整とprocess skewの説明です。この説明から過渡寿命認定モデルが提供されるとはいえません。通常過渡計算の完走、電流値の正常性、警告なしはTDDB/HCI寿命合格の証明ではありません。

### DRM §2.5：rules と guidelines の区別

URL: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_02.html

DRC rules と guidelines は区別され、guidelinesはDRC runsetやCX-020の審査対象とはされていません。この過渡問題をそのまま「CX-020 DRC waiver必須」と呼ぶ根拠はありません。必要なのは、適用可能な過渡信頼性基準とその認定です。

## 使用中の公開PDK実装

読み取り対象環境：MY-NOTE-2  
Dockerコンテナー：gf180-audit-20261029  
PDKパス：/foss/pdks/gf180mcuD

- SOURCES の open_pdks：b344c97eacc2aaf8e14ae7e43e2e9dc0871de2c0
- .config/nodeinfo.json の primitive gf180mcu_fd_pr：a0c31bd71c2084a5283204dc4e80f1f901d2d5d0
- 同reference gf180mcu_pdk：a897aa30369d3bcec87d9d50ce9b01f320f854ef
- libs.tech/ngspice/sm141064.ngspice：YI-141-SM064 Rev.9、BSIM 4.5／level 54
- sm141064.ngspice SHA-256：f6f4a96e18fc5ad11270ad3451aaecc7ac37fc81eb61e15b0d7d94c7bc594a24

libs.tech/ngspice直下のモデル一式を、reliability / aging / TDDB / HCI / lifetime / SOA / assert / vgs_max / vgd_max / vgb_max / vds_max で走査しましたが、対応する定義は見つかりませんでした。PDKを変更していません。これは調査したモデル群についての否定的結果であり、全てのfoundry提供物の不存在証明ではありません。

## Test-2-4の記録との照合

参照：
- ../analog/afe_lvs_supply_comparison.json
- ../analog/afe_lvs_startup_controls/README.md
- ../analog/afe_lvs_startup_controls/final_summary.json

対象は3.6 V、TT27、current-LVS common-AVSS、integral-Qの診断であり、正式モデル・物理寿命の認定ではありません。

- 起動最大：xa.xamp.xop_a.xp の |VGB| = 3.665517019979512 V、時刻0.532001308 µs。3.63 V超過合計3.313944603 ns。上限より約35.5 mV高い値です。
- 最大刻み0.25 nsの起動対照でも3.665122777 V、超過3.294887924 ns。二つの刻みだけでは完全な数値収束の証明になりません。
- 起動後1～7.8125 µs窓の3.644227526 Vは xc.xcda3.xn の |VGS| です。
- 後続周期の約3.647 Vは xa.xoff.xop.xnph.xp の |VGS| です。同じVGBが繰り返すとは記述しません。
- 後続超過時間約36～97 psは、1 ns最大刻みの保存波形からの補間値です。細刻みで検証済みなのは起動1 µsだけで、後続周期の露出時間は未検証です。
- 3.313945 ns / 31.25 µs ≈ 0.0106% は、当該端子対の保存窓に対する割合です。製品寿命dutyには置換できません。起動回数、稼働時間、周期動作、温度履歴を分離する必要があります。
- 理想substrate/rail条件、Q診断モデル、未確定の実電源シーケンスという制約があります。3周期程度の後続記録は定常状態や寿命dutyの証明ではありません。
- VDSにも別途超過が記録されています。DC gate-to-any-node上限とHCI側のVDS条件を同一の物理判定として扱いません。

## 超過を許容と認定するために必要な事項

超過を残したまま許容と判断するには、製造窓口／foundryから適用可能な資料または個別判断を得る必要があります。これは公開資料の不足から導く技術上の判断であり、既に承認を得たという意味ではありません。

1. 対象3.3 V MOSの極性・寸法・端子対に適用できる過渡電圧、パルス幅、反復率、dutyの許容条件。
2. TDDB/HCIの目標寿命、温度、故障確率／許容劣化、面積依存、波形積算方法。
3. 単発起動、繰返し起動、周期スイッチングの区別と積算方法。
4. 使用mission profile：目標年数／通電時間、動作・待機割合、clock周波数とモード、寿命中の起動・reset・brownout回数、junction温度分布、AVDD許容範囲。
5. 実電源条件：AVDD ramp-rate範囲、VRP/VRNの成立順序、clock/blank enable、reset assertion/release、電極common-modeの起動挙動、substrate/rail/packageインピーダンス。
6. 妥当性が確認されたモデル・PEX条件で、全gate端子対およびVDS、導通状態を含む収束済み波形。

当面、3.63 V以下へ抑えることを保守的なプロジェクト内screenとして採用することは可能ですが、それはfoundryの瞬時絶対最大値として新しい仕様を発明することではありません。また、それだけで他の信頼性項目まで合格になるものではありません。

## 今回の確認範囲と未実施事項

公式公開DRM、電気仕様、モデル説明、公開Web検索、指定ローカルPDKと既存診断記録を読み取り確認しました。R-QR-MI-008本文と定量TDDB/HCI過渡認定データは取得できませんでした。公開GitHubの特定revisionへの閲覧は取得制限があり、実装revisionはローカルSOURCES / nodeinfo.jsonで確認しました。

外部投稿・問い合わせ・承認取得・新しいシミュレーション・原設計変更・PDK変更は実施していません。今回の追加作業は本README.mdとsummary.jsonへの調査結果保存のみです。
