# Test-2-4 機能回帰検証

この検証は変更していない回路ソースとデジタル・ネットリストの機能回帰です。修正GDSを寄生抽出して性能を評価したものではありません。元版のログは保全し、このフォルダー内で試験しています。

## 結果の読み方

- デジタル: digital_tests.log の最終 summary と functional_summary.json を参照。RTLテストおよび2種類のゲートレベル/RTL同時比較を実行。
- アナログ: bias動作点・起動、reference、testmux、AFE動作点/雑音推定、quantizerの13ジョブ、ADC/AFEクロック2ジョブを実行。各ログと analog_summary.json に結果。
- 初回デジタル試験はvvpの共有ライブラリ不足でシミュレーション未起動。initial_runtime_error に保存し、プロセス内のLD_LIBRARY_PATHだけを補正して全試験をやり直しました。

## 測定値と限界

- ADCクロック: 5条件で位相切替margin最小0.16 ns。0未満は切替順序が逆転する境界ですが、必要な安全余裕の仕様値やassertはありません。「正の値を測定」であり、PEX/PVTタイミング承認ではありません。
- AFE: typical/27℃、SS/85℃、FF/-20℃、bias code=2で最小 abs(VDS)-abs(VDSAT) は0.22/0.22/0.07 V。これは動作点の測定値で、許容最小値に対するassertではありません。FFの余裕は小さく、供給電圧変動や寄生を含む確認が必要です。
- Quantizer: typical/SS/FFで各8/8の判定が+61 nsの読取時点で期待値一致。23/24条件で遷移遅延を測定し、最大1.58 ns。typical +10 mVは初期状態が既に正しく遷移がなく、その条件の遅延は未測定です。
- Reference差動電圧: 0.4929/0.4918/0.4940 V。Testmux最大選択電圧誤差: 1.962/2.960/1.336 mV。これらの精度許容値は提供されておらず、数値評価として記載します。
- AFE雑音4.59/5.37/4.06 nVrmsは供給された線形MOSCAP近似を含む凍結位相/チョッピング推定であり、全チップENOBや雑音の保証ではありません。
- DAC長時間試験は今回再実行していません。以前のtypical even-chargeは約50分を要し、他の条件にtimeoutがありました。今回DAC全条件や閉ループADCの精度が合格したとは主張しません。

## 再現

既存コンテナーで python3 /work/Test-2-4/functional/run_suite.py を実行します。AFEクロックは run_afe_clock.py、集計は finalize_functional.py です。再実行はこのフォルダー内のログを更新します。

input_hashes.json は試験入力のハッシュです。回路ネットリストを変更せず、モデルパスとローカル実行環境だけを適合させています。全チップPEX、電圧変動、ミスマッチ/Monte Carlo、ENOB、パッド寄生・パッケージ、EM/IRはこの機能試験の範囲外です。
