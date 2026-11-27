# r15 のデジタルのマクロ（15 回目のチップ）

`chip_lay.py` は `EEG_DIG_REV=r15` でここのマクロを使い（`../../digrev.py`）、`runs/chip_top_r15` に組む（r14 の `runs/chip_top` は変えない）。

- ラン：`gf180/tapeout/digital/eeg_digital_top_r15/runs/r15m13_20261128`（11/28 から。設定は同じフォルダの `config.yaml`）。RTL は `gf180/tapeout/rtl_r15/` のコミット 8cbe4bd7 の版（VERSION 0x11、CFG_GEN、DROP_CNT、LATEST の窓。11/28 の試験台の強化のあとも RTL の源は同じ）。
  - 11/27 の r15m1_20261127 は、LibreLane の最後の警告の一覧に Max Slew（max ss の 2 件）と Max Cap（3 コーナーの 1 件）を残していた。12 本の試しのランで、警告のない r15m13 に替えた（`gf180/tapeout/digital/eeg_digital_top_r15/README_r15m_20261128.md`）。
  - r15m13：9 コーナーで slew・容量・ファンアウトの違反 0、setup ≥ ＋0.623 ns（max ss）、hold ≥ ＋0.165 ns、DRC・LVS・アンテナ・XOR 0。
- ファイル：LibreLane の final の GDS、LEF、ネットリスト（nl.v、pnl.v）と、チップの LVS 用の CDL（`../../../digital/pnl2cdl.py`）。写しと CDL は `../../../digital/eeg_digital_top_r15/install_r15_macro.sh r15m13_20261128` で作る。sha256 は `SHA256SUMS`。
- nl.v（sha256 a8d1c089…）は、ゲートの水準の並走と ADC との組の試験が読んだものと同じ（`documentation/gf180_digital_verification_20261024.md` 第 9 節）。
- 外形 440 × 900 µm、LEF の端子 30 個の名前と形と位置、CDL の端子 62 本の並びが r14 と r15m1 のマクロと同じ（11/27、11/28 に照合）。コアのネットリスト `gf180/tapeout/chip/eeg_core.spice` は変わらない。
