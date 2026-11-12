# 現在版の独立参照探索（2026-11-11）

## 結論
現行 Test-2-4 の full-ring LVS を閉じる独立全接続参照、および full-chip STA に使える現行マクロ SPEF/ODB/ETM の追加発見はありません。新しい長時間試験・設計変更・旧版入力の流用はしていません。

## 確認した範囲
- C:\projects\ft の既知プロジェクト（test1、test1x、test2～test6、20260902、First_Tapeout_2026-f6437bdb182aad42397867cce8e94290f2b97bb0 配布展開）。test1 の対象結果は SKY130 caravel で現行GF180に使えません。Python環境のlibファイルはLibertyではありません。
- C:\Users\ymori\iic-osic-tools、特に gf180_eeg_feasibility\hh_tapeout_20261002。
- C:\Users\ymori\eda\designs（現在のiic-osic-tools既存3コンテナの設計マウント）。対象ファイル未発見。停止コンテナを起動せず、Docker内部全域や他ユーザー領域まで網羅した調査ではありません。
- 前回 digital_timing と extraction/reference_draft の結果を参照。

## 候補と棄却理由
1. 旧iic-osic-toolsに RUN_2026-10-03_01-27-57/final/odb/chip_top.odb（3,886,500 bytes）とSDCが残っています。10月2日のpad-ring runsもあります。ただし PADRING_RECOVERY_R2.md はテンプレートdummy core/SRAM・5VでありEEG3.3V完成実装ではないと明記。現行 chip_lay.py が指定する RUN_2026-10-23_13-27-25 とは異なります。現行GDSの参照に採用不可。
2. 配布アーカイブ内と test1x/gf180 の両マクロ config.yaml、chip_sta/run_chip_sta.sh、両マクロ .nl.v、10月23日 padring GDS.gz は各SHA256一致。アーカイブは欠けたfinal runの補完にはなりません。配布展開のfirst_tapeout_eeg/.gitは存在せず、ここから旧commitの未配布生成物は回収できません。
3. 現行 chip/padring に存在するのは GDS.gz、pad_geometry.json、pad_coordinates.csv。独立した全インスタンス接続Verilog/ODB/CDLはありません。sidecarベースの独立意図草案は43 CORE、9 TIEHIGH、45 TIELOWおよび682 spacerの不足を既に記録しています。抽出GDSから参照を自己生成する方法は採用していません。

## 再生成可能性と不足入力
- full-ring LVS: 元 /Users/noah/Codings/ws_gf180/eeg_padring の RUN_2026-10-23_13-27-25 の最終電源込みVerilog/ODB/configと生成バージョンを回収するのが優先。Test-2-4のchip_lay配線意図変更と接続差を明示して独立top参照へ統合する必要があります。元run不在で現在GDSと同じ接続を再生成できるとは保証できません。
- macro STA: run_chip_sta.sh は eeg_digital_top/runs/f2/final/lib と eeg_adc_dig/runs/f3/final/lib の9 RC/PV組合せを要求します。最終SDC、SPEF、ODB、ETM、resolved configが不足。現行RTL/configで新たにPnRを実行すること自体は候補ですが、違う配置配線になるため現行GDSへのSTA証拠にはなりません。元final DEF/ODBと一致確認済み抽出を回収すべきです。
- chip STA: chip_nets.py はコアLVS DB、固定macro座標、手動RC係数から chip_dig.v/SPEF/quantizer Liberty を作ります。build/はgitignore。生成可能であることと検証済みRC/モデルであることは別です。quantizerモデルもSS=-20C/2.97V、FF=85C/3.63Vの近似式であり、macroのSS125C/3.0V、FF-40C/3.6Vと同じ温度電圧ではありません。現行RCの二重計上・寄生対応検証、quantizer corner/model再検証、実I/O遅延/負荷・タイミング例外の仕様が必要です。
- 現行マクロ.nl.vは前回の限定STAとセル型/個数照合に使える独立候補ですが、配線寄生を含むfull-chip timing signoffへ格上げしません。

## 一致確認した入力SHA256
- eeg_digital_top/config.yaml EB4426791C2AC898AA4A223BE7FD536FC1427AAC11D1E80EF7B600085739D83A
- eeg_adc_dig/config.yaml 9D6AFF4FAD0F1CA0C62BD2E1BE828825800B09BB27121D83458FDAF2BBA245C7
- run_chip_sta.sh F8D1AB6131AAC949F6AD154B0CB3C0E1CED7E7D6A559E8651351DE424B83CF54
- eeg_digital_top.nl.v 6AE8F6C75B8E8BF8FF2B5990ECBAADF82FD0092691BA60CB4AEB814F59C63CF7
- eeg_adc_dig.nl.v C39FE2CF4E05B693C5D910EDD81BD9692DB386048DE8B5E18996B0C7FA63260D
- padring_1x0p5_20261023.gds.gz 8649F062D03D9E098B7A8C422B304963E8C7858830B82DCE13852DF9F132D344

## 追加探索（同日、Docker/Git/退避）
- 現在プロジェクトtest1xおよびgf180、親ft/projectsに.gitなし。iic-osic-toolsはshallow=true、main/origin/mainのみ、2026-07-18 commit 9240a74のclone reflogのみ。gf180_eeg_feasibilityはこのGitの全参照履歴に記録なし、独立.gitもなし。ネットワークfetchは行っていません。
- First_Tapeout配布ZIPの22,678エントリ目次を直接確認。RUN_2026-10-23、runs/f2/f3、ODB/SPEF/SDF、対象マクロETM、.gitを該当条件で探し、候補0。test1x内の退避アーカイブは今回の納品/証拠ZIPとPythonパッケージ資材のみ。
- gf180 precheck/cobコンテナ4個のMountsは既確認test1x内の入力GDS・検証出力のみ。監査コンテナの/foss/designs、/home/ubuntuに該当ODB/SPEF/対象ETM/padring Verilogなし。
- iic-osic-tools_xvnc/xserver/shellはいずれも3か月前に停止。docker diffによる書込レイヤーの変更ファイル名でeeg/padring/.odb/.spef/2026-10-23/designs/workを検索し候補0。前回Mounts確認の設計bind先はC:\Users\ymori\eda\designs。停止コンテナは起動していません。これはイメージ全内容や全ファイル内容の網羅調査ではありません。
- ボリューム名/マウントポイント/既存接続先だけを確認。匿名88e860...はinventory検証DBに接続しているため対象外。匿名473eb...とgf180-hh-pdk-f6eeac7-r1は既存コンテナ接続なし。後者は名称上PDK保存用候補ですが内容は未確認。新コンテナ作成・volumeマウント・変更をせずに到達できる設計ファイル探索範囲には含めていません。9887c...は前回nice_chaumの/opt/rke-tools mountと判明済み。inventory DB等の無関係な内容は読みませんでした。
- 結論は不変。回収できた現行独立参照なし。未接続volume内部、停止コンテナのイメージ全域、元作成者のMac、未提供リモート履歴は探索境界です。環境変数・認証情報の取得、コンテナ起動・変更はしていません。
