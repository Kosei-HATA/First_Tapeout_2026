# チップの GDS

wafer.space に出す形（穴埋めのあと）を、版ごとに gzip で置く（展開：`gunzip -k <ファイル>`）。作る途中の GDS（`gf180/tapeout/layout/runs/chip_top/`）は git の対象外で、1 つ 225 MB あり GitHub の 1 ファイル 100 MB の上限も超えるため、ここに圧縮して置く。

| ファイル | 版 | 中身 |
|---|---|---|
| `chip_top_fill_r6_20261026.gds.gz`（41,951,534 バイト） | r6：6 回目の組み立て（10/26、c752ec78） | `chip_lay.py --fill` が書いた `chip_top_fill.gds`（224,947,506 バイト）。precheck pre_20261026 で通り、10/27 に最新の precheck（10/20 版）と事務局の指定の `--slot 1x0p5 --cob` でも通った（pre_20261027_cob） |
| `chip_top_fill_r7_20261029.gds.gz`（41,885,093 バイト） | r7：7 回目の組み立て（10/29。ADC の C1・C2 を 1.25 倍にした形。コミットはまだで、f6437bdb の上の作業ツリーから作った） | `chip_lay.py --fill` が書いた `chip_top_fill.gds`（224,076,194 バイト）。10/27 の直し（同じ場所に重なったセルの写しを消す、`chip_lay.drop_copies`）も入っている。最新の precheck（10/20 版、10/29 にも最新と確かめた）を `--slot 1x0p5 --cob` で回して通った（pre_20261029_r7：密度、ゼロ面積の図形、アンテナ、Magic DRC、KLayout DRC がどれも 0 件、パッドマスク一致、Magic DRC は最後まで走った） |

- 展開した GDS の sha256：r6 `1343e9cc55cb2020f6213937c4622f2a126db6381ae66615719398aa6a027529`、r7 `b1a260eef924e26dce9ab16aa2cc869943de4aa3ba68ba83bea7955dcaccdce3`
- gz の sha256：r6 `9df27bfd00c366c02003d0d076f204af1367756879135435cc0e645cdf982b10`、r7 `43b767ef271463e38a6353c5166dc62a32efc65d92b47ab61e9f632a7833f145`（`gzip -9 -n`。名前と時刻を入れないので、同じ GDS からは同じ gz になる）
- 発注に使うのは r7。r6 は比べるために残している（r6 の gz は 10/27 の直しの前の形。直しのあとの形は XOR で全層同じだった）。
- precheck はこのファイルを読み、ID を入れた形（`--cob` では `05-klayout-generateid/chip_top.gds`）で密度、ゼロ面積の図形、アンテナ、Magic DRC、KLayout DRC を回す（`gf180/tapeout/chip/precheck/run_precheck.sh`）。`--cob`（CoB で発注）では、その前にパッドマスクと ID の 4 つのセルの位置も検査する。
- 作り方：`gf180/tools/venv310/bin/python gf180/tapeout/layout/chip_lay.py --fill` のあと `gzip -9 -n -c gf180/tapeout/layout/runs/chip_top/chip_top_fill.gds > chip_top_fill_<版>_<日付>.gds.gz`。
- 説明の文書：`documentation/gf180_chip_assembly_20261023.md`。前の版（r0〜r5）の GDS は置いていない。
