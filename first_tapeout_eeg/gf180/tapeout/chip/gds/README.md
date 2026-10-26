# チップの GDS

wafer.space に出す形（穴埋めのあと）を、版ごとに gzip で置く（展開：`gunzip -k <ファイル>`）。作る途中の GDS（`gf180/tapeout/layout/runs/chip_top/`）は git の対象外で、1 つ 225 MB あり GitHub の 1 ファイル 100 MB の上限も超えるため、ここに圧縮して置く。

| ファイル | 版 | 中身 |
|---|---|---|
| `chip_top_fill_r6_20261026.gds.gz`（41,951,534 バイト） | r6：6 回目の組み立て（10/26、c752ec78） | `chip_lay.py --fill` が書いた `chip_top_fill.gds`（224,947,506 バイト）。precheck pre_20261026 で通った |

- 展開した GDS の sha256：`1343e9cc55cb2020f6213937c4622f2a126db6381ae66615719398aa6a027529`
- gz の sha256：`9df27bfd00c366c02003d0d076f204af1367756879135435cc0e645cdf982b10`（`gzip -9 -n`。名前と時刻を入れないので、同じ GDS からは同じ gz になる）
- precheck はこのファイルを読み、ID を入れた形（`04-klayout-generateid/chip_top.gds`）で密度、ゼロ面積の図形、アンテナ、Magic DRC、KLayout DRC を回す（`gf180/tapeout/chip/precheck/run_precheck.sh`）。
- 作り方：`gf180/tools/venv310/bin/python gf180/tapeout/layout/chip_lay.py --fill` のあと `gzip -9 -n -c gf180/tapeout/layout/runs/chip_top/chip_top_fill.gds > chip_top_fill_<版>_<日付>.gds.gz`。
- 説明の文書：`documentation/gf180_chip_assembly_20261023.md`。前の版（r0〜r5）の GDS は置いていない。
