# 0入力対照・offset分離の独立数値監査

**条件付き一方向差分感度を独立確認。両caseの固定8周期窓は全7比較PASS。正式gain/ENOBや物理offset精度の保証ではない。**

版: independent_offset_separation_recovery_v1。入力preflight、旧監査、原波形は保全。

## 結果

- 条件付き差分感度: **298.90696712 V/V**（20log10表示 **49.51072076 dB**）。
- +100 µV caseの差動平均: 0.0298906966997644 V。
- 0入力caseの差動平均: -1.22096169426331e-11 V（-12.209617 pV）。
- 実測ELP−ELN平均差: 0.0001000000000002128 V。SRC差も100 µVを確認。
- 8周期ごとの差分感度範囲: 298.90381714〜298.90979058 V/V。
- 指定窓159.318117〜221.818117 µs、8周期×各7.8125 µs。両caseとも7隣接比較すべてPASS、4→5周期の窓境界も含む。

## 方法とworker照合

各原波形からtime、OUTP、OUTN、VCM、VDD、SRC、RTL_AFE_RST、ELP、ELNの必要9列のみを保持した。両caseはadaptive time gridが異なるため、行番号で差を取らず、同じ物理時刻の境界を補間し、各caseを別々に時間重み積分した。全内部sampleを使い、外れ値の除外はない。

平均の区間積分はdt×(y0+y1)/2。RMSは別法として、区間線形波形の二乗積分dt×(y0²+y0×y1+y1²)/3をmath.fsumで合算。worker互換の二乗sample台形法でも両caseの全7比較PASS。RMSはDCを含むtotal differential RMS。

差分感度は(+100 µV差動平均−0入力差動平均)/(実ELP−ELN平均差)で計算し、SRCと公称100 µVの分母も照合。全窓の直接積分と8周期平均も一致した。worker値との差は浮動小数丸めおよび実入力表現の丸め範囲で、summary.jsonに分けて記録した。

## 原本・入力条件の確認

preflightで保存したdeck、controls、mapping、criteria、.spiceinit等のhashを再確認。両caseの相違は入力振幅とbyte同一controlsのinclude先のみ。コピーmetadataの100 µV値をzero分母として使わず、実deck/ELP−ELN/SRCを採用した。

両波形とも224 µs到達、読取9列finite、時刻単調、固定窓内reset解除、出力のrail余裕を確認。各原CSV全体のSHA256を処理前後に計算して一致。元ファイルと旧監査は変更していない。

## 解釈の限界

**−12.2 pV程度のzero平均は、公称対称・決定論モデルの数値残差。物理offset、mismatch、noise、pV精度を示す値ではない。**

この値は仮条件AFE/Qモデルの0→+100 µV有限差分であり、正式DC/EEG帯域gain/phase、小信号微分、負入力対称性・線形性、ENOBではない。有限224 µs/8周期の周期moment安定性は長時定数を排除しない。理想VCM共通mode、外部VCM capacitorなし、Q診断モデル、理想共通AVSS、full ADC/DWA loopなしの制限を継承する。元160 µs窓の失敗は残り、58MOS再監査、PVT/mismatch統計、寿命、製造認定は対象外。

詳細な8周期値、両case全14比較、入力差、hashはsummary.json、周期ごとの差分はoffset_comparison.csv。
