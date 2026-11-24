# r14：r14 のデジタル制御のマクロを入れた 14 回目のチップ（11/24、検証の途中）

- チップ：14 回目の組み立て（11/24）。r13 からの違いは、デジタルのマクロ eeg_digital_top を r14 の RTL（`gf180/tapeout/rtl_r14/`、コミット e56bc9da。監査の第 10 回から論理は不変）のマクロ（LibreLane のラン r14f5_20261124、440 × 900 µm）に替えたことと、その上の DVDD のデカップリングを 200 µm 上へ移したこと（`chip_lay.DIG_REV`、`gf180/tapeout/layout/digrev.py`）。アナログ（AFE、ADC、バイアス、基準電圧、試験用マルチプレクサ）、パッドリング、アナログの配線は r13 と同一（XOR、図 54）。詳しくは `gf180_chip_assembly_20261023.md` の「組み直し（11/24、14 回目）」と `gf180_digital_verification_20261024.md` の第 8 節。
- 発注の候補は r13 のまま。r14 に替えるかは 12/10〜12 に判断する（要件定義の第 10 節）。
- ここの図
  - 53（r14 のデジタルのマクロ、11/24）：`gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_macro_fig.py`。データは `gf180/tapeout/digital/eeg_digital_top_r14/runs/r14f5_20261124/`（final/metrics.json、`run_sta_r14.sh` と `soft_paths.py` の sta_r14/）と r13 のマクロの `eeg_digital_top/runs/f2_rerun_20261119/`。ランのフォルダは git の対象外。
  - 54（r13 との XOR、11/24）：`gf180/tools/venv310/bin/python gf180/tapeout/viz/r14_xor_fig.py`。データは `gf180/tapeout/layout/chip_xor.py --raster 2900,370,3600,2162,4 --json …` の `layout/runs/chip_top/xor_r13_r14_chip_top_20261124.json`（git の対象外）。比べた 14 回目の GDS は、DRC と LVS の組み立てで書き直した `chip_top.gds` とバイト単位で同じ。
