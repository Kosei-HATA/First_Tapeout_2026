# デジタルSTA追加検証

OpenSTA 3.1.0で、実GDSに対応するeeg_digital_top/eeg_adc_digの配置後ネットリストをスクリーニングしました。元ファイルは変更していません。

## 結果

MCLK 32.768MHz（30.517578125ns）、TT/25℃/3.3V、SS/125℃/3.0V、FF/−40℃/3.6Vの計6条件でsetup/hold余裕が正でした。

- 最小setup余裕: 4.526982ns（digital_top SS）
- 最小hold余裕: 0.158917ns（digital_top FF）
- Libertyに記載の制約違反: 報告0
- 100MHzへ意図的に厳しくした負対照: setup −15.990598nsを検出
- ネットリストと実GDSのセル種別個数: digital_top 13,446個、adc_dig 4,791個で完全一致。ただし個数一致だけを接続等価の証明にはしていません。

## 制約と重要な限界

SPEF/SDFと元の最終I/O設定、マクロtiming model、chip-level STA生成物は現行プロジェクト内にありません。したがって配線遅延なし・セル遅延のみです。クロックバッファのセル遅延は伝播していますが、配線RCはありません。

元SDCのTH/CODEマルチサイクルとCODE hold false-path、明記された制御入力遅延は維持しました。環境変数で未保存だったI/O遅延は周期20%、出力負荷20fF、buf_4駆動、クロック遷移0.15nsの明示的な仮条件です。これを実基板・実アナログ負荷の保証にしていません。

初回スクリーニングでは仮のglobal slew 1.5ns基準で違反が出ました。そのログは保存していますが、元の採用基準と確認できないため設計不良とは断定しません。library_constraint_screenでは未知のglobal fanout/slew/cap制約を付加せず、実Liberty制約を報告しました。これは正式な制約を緩めてsignoffしたものではありません。

この結果は全チップタイミング合格ではありません。元PnRのSPEF/最終SDC、実I/O条件、検証済みマクロモデルとchip配線RCが必要です。32.768MHz以外のモード・リセット遷移・非同期SPIを含むCDCの全保証もしていません。

## 再現

既存コンテナ内:
python3 /work/Test-2-4/manufacturing_preflight/digital_timing/run_screen.py
python3 /work/Test-2-4/manufacturing_preflight/digital_timing/run_library_screen.py

上記はこの検証フォルダーの結果を再生成します。再実行前にこのフォルダーを保全してください。元SDC/ネットリスト/LibertyのSHA-256は各manifest.json、数値一覧はsummary.jsonにあります。
