# r15 のデジタルのマクロ（15 回目のチップ）

`chip_lay.py` は `EEG_DIG_REV=r15` でここのマクロを使い（`../../digrev.py`）、`runs/chip_top_r15` に組む（r14 の `runs/chip_top` は変えない）。

- ラン：`gf180/tapeout/digital/eeg_digital_top_r15/runs/r15m1_20261127`（設定は同じフォルダの `config.yaml`。r14f5 と同じ設定で、源だけ r15）。RTL は `gf180/tapeout/rtl_r15/` のコミット 8cbe4bd7 の版（VERSION 0x11、CFG_GEN、DROP_CNT、LATEST の窓）。
- ファイル：LibreLane の final の GDS、LEF、ネットリスト（nl.v、pnl.v）と、チップの LVS 用の CDL（`../../../digital/pnl2cdl.py`）。写しと CDL は `../../../digital/eeg_digital_top_r15/install_r15_macro.sh r15m1_20261127` で作る。sha256 は `SHA256SUMS`。
- 外形 440 × 900 µm、LEF の端子 30 個の名前と形と位置、CDL の端子 62 本の並びが r14 のマクロと同じ（11/27 に照合）。コアのネットリスト `gf180/tapeout/chip/eeg_core.spice` は変わらない。
