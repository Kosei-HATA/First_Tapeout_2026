# r13：増幅器の加算点 INP と INN の帯をコア全体で交互にしたあと（11/19、検証と評価の途中）

- チップ：13 回目の組み立て（11/19）。r12 からの違いは afe_top の中の増幅器のコアだけ（`afecore_lay.SYM_GATES`、設計のファイルは 1ae9787c）。電源の除去（PSRR）のため、INN だけが電流源とブースタの上を覆っていた形をやめた。詳しくは `gf180_chip_assembly_20261023.md` の「組み直し（11/19、13 回目）」。
- 検証（11/19）
  - チップ全体の DRC と、穴埋めのあとの全 DRC は違反なし。
  - パッドリング込みのチップ全体の LVS（KLayout）とコアの LVS は一致。Magic／Netgen のチップ全体の LVS は回している。
  - 最新の precheck（10/20 版。11/19 にも最新と確かめた）を `--slot 1x0p5 --cob` で回して通った（pre_20261119_r13）。
  - r12 との XOR（穴埋めの前）では、違うのは afe_top の中だけ。
- GDS（穴埋めのあと、precheck に出した形）は `gf180/tapeout/chip/gds/chip_top_fill_r13_20261119.gds.gz`。展開した `chip_top_fill.gds` の sha256 は 67891f406a2b590a9099b60c0dfe973f49d0b3b94e852b99b87f2389154ba7f7。
- 発注の候補は、r13 の評価が通るまで r12 のまま。
- ここの図
  - 48（クロックとデータの線と敏感な網、11/19）：`gf180/tapeout/viz/clocklines_fig.py extract` のあと `plot`。データは `gf180/tapeout/viz/data_r13/clock_lines.json`。(e) の波形は r12 の typical の起動のラン（チップの配線は r13 と同じ形）。
  - 46（電源の除去、途中の版、11/19 夜）：`EEG_PEX_REV=r13 gf180/tools/venv310/bin/python gf180/tapeout/viz/psrr_fig.py`（`psrr.py` を同じ環境変数で回したあと）。ランは `gf180/tapeout/pex/runs/psrr_r13/`（`run_psrr_r13.sh`）。最初の 4 本（typical の釣り合いと ELP に 51 kΩ ∥ 47 nF、ff、ss）とモンテカルロ 1〜4（11/19 21 時 51 分に更新）。モンテカルロ 5〜8 と sf、fs は実行中、DVDD は未実行。
  - ほかの番号は、r13 の評価（PSRR から）がそろってから、この版の図としてひとそろい描く。
