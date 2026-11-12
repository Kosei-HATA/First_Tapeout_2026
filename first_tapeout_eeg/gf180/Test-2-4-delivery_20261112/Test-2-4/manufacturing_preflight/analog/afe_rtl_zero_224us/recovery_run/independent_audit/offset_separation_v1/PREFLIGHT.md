# zero回復試験・offset分離の独立監査準備

状態: **入力一致を確認済み。zero波形の完成待ち。結果未判定。**

+100 µV、旧zero、recovery zeroのcontrols、mapping、固定窓criteria、.spiceinitはSHA256同一。回復deckは旧zeroとbyte同一。+100 µVとの差はSRCの最終振幅100u→0と、byte同一controlsへのinclude先だけ。実include先は元zeroフォルダで、その内容も一致。AFE/bias/clock subcircuitのhashは前回刺激監査時と一致。全入力hashをpreflight_summary.jsonに保存した。

## 完成後の式

同じ159.318117〜221.818117 µsを8周期に分割。各caseのOUTP−OUTNを、境界線形補間と非一様時間重み積分で求める。

- zero baseline: zero caseの同一窓の差動平均。各周期値と8周期平均を報告。
- 条件付き差分感度: (positive差動平均−zero差動平均)/(positive実入力平均−zero実入力平均)、V/V。実ELP−ELNとSRCで分母100 µVを確認し、周期ごとと全窓を報告。
- 両caseの8周期/7隣接比較を同じ閾値で確認。RMSは区間線形波形の二乗を厳密積分し、worker互換の二乗sample台形法も照合。
- 224 µs到達、必要列のfinite/時刻単調、全固定窓包含、入力とreset状態、output rail余裕、原波形hash不変を確認。

## 注意

mappingは元positive metadataをコピーしているためinput_differential_step_V=100 µVが残る。zero deckとinput_manifestが0 Vへ明示的に上書きしている。分母はコピー値でなく実deck/波形から求める。

これは仮条件AFE/Qモデル、+100 µV対0の有限差分感度で、正式周波数gain、小信号微分、ENOBではない。元160 µs窓の失敗を消さず、長時定数、電極/servo、全system、PVT/mismatch、58MOS再監査、寿命、製造保証を含まない。片方が不安定ならそのまま報告し、勝手な延長や閾値緩和をしない。外部VCM capacitorは追加していない。

原ファイルと既存監査は変更していない。波形の重い読取はまだ行っていない。
