# r14 のデジタルのマクロ（14 回目のチップ）

`chip_lay.py` は既定（`EEG_DIG_REV` を与えない、または r14）でここのマクロを使う（`../../digrev.py`）。`EEG_DIG_REV=r13` では一つ上の `gds/` の r13 のマクロ（LibreLane のラン f2）を使い、13 回目のチップと同一の GDS を組む（11/24 に 45 層の XOR で確かめた）。

- ラン：`gf180/tapeout/digital/eeg_digital_top_r14/runs/r14f5_20261124`（設定は同じフォルダの `config.yaml`、記録は `README_r14f_20261124.md`）。RTL は `gf180/tapeout/rtl_r14/` のコミット e56bc9da の版。
- ファイル：LibreLane の final の GDS、LEF、ネットリスト（nl.v、pnl.v）と、チップの LVS 用の CDL（`../../../digital/pnl2cdl.py` で pnl.v と PDK の 9 トラックのセルの SPICE から作る）。写しと CDL は `../../../digital/eeg_digital_top_r14/install_r14_macro.sh r14f5_20261124` で作る。sha256 は `SHA256SUMS`。
- 端子の名前と順は r13 のマクロと同じ（CDL の 62 本が同順。コアのネットリスト `gf180/tapeout/chip/eeg_core.spice` は変わらない）。外形は 440 × 900 µm（r13 は 440 × 700 µm）。
