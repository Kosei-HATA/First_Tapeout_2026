# 後輩の Test-2-4（11/12 に受け取ったもの）

`Test-2-4-delivery_20261112/` は、後輩から 11/12 に受け取った `Test-2-4.zip`（420 MB）を展開したもの。6 回目のチップ（r6）をもとに、DVDD のつながり（Test2-3）とパッドの金属を直し、DRC、LVS、つながり、RTL／ゲートレベル／回路のシミュレーションを回した記録が入っている。最初に読むのは、中の `README_ja.md` と、`Test-2-4/manufacturing_preflight/delivery_report_20261112/` の PDF（10 ページ）。後輩の README にあるとおり、製造の承認ではない。

こちらで読んだ結果と、10 回目のチップとの比べは、`documentation/gf180_chip_assembly_20261023.md` の「後輩の Test-2-4 との比べ（11/12）」にある。Test-2-4 には 7 回目から 10 回目の直しが入っておらず、発注の候補にはしない。PDK のポリ抵抗の雑音の件は、こちらでも確かめて評価した（`documentation/gf180_realistic_eval_20261028.md` の「ADC のポリ抵抗のフリッカ雑音」）。

## git に入れていないもの

GitHub は 100 MB を超えるファイルを受け付けない。次の 5 つは、ZIP の中身をそのままは入れていない。ほかは ZIP のとおりすべて入れた（macOS の `.DS_Store` を除く。こちらの `.gitignore` が外す `*.log` などのログも入れた）。

| ファイル | 大きさ | git では |
| --- | ---: | --- |
| `Test-2-4/gds/Test-2-4.gds` | 225.0 MB | `Test-2-4.gds.gz` にして入れた（`gzip -9 -n`、42.0 MB） |
| `reference/Test2-3/gds/Test2-3.gds` | 224.9 MB | `Test2-3.gds.gz` にして入れた（同じく 41.9 MB） |
| `Test-2-4/manufacturing_preflight/analog/afe_rtl_startup_224us/steady/wave.csv` | 651.8 MB | 入れていない（+100 µV の 224 µs の生波形） |
| `Test-2-4/manufacturing_preflight/analog/afe_rtl_zero_224us/recovery_run/steady/wave.csv` | 651.5 MB | 入れていない（0 µV の 224 µs の生波形） |
| `Test-2-4/verification/core_with_hints/eeg_core.lvsdb` | 455.3 MB | 入れていない（コアの LVS のデータベース） |

- 入れていない 3 つは、ZIP（こちらの手元）と後輩の手元にある。それぞれの大きさと sha256 は `MANIFEST_SHA256.json` にある。
- 生波形から出した要約と独立の確かめ（`final_summary.json`、`independent_audit/`）は入っている。生波形を読み直す解析だけは、git からは回せない。
- gz を展開した GDS の sha256 は、目録のものと同じ（Test-2-4.gds `7af0c9bb…`、Test2-3.gds `1ec7bd32…`）。
  - gz の sha256：Test-2-4.gds.gz `767c1a15b4f43de6cc22545e32f0dd13a649c5e4780b541fc455edb6f7b10b49`、Test2-3.gds.gz `a48fc570172b89b66c208d449b703792a02f51b2cf5e1d8363f46e9d93d7db44`。

## 中身を確かめる

git から取り出したあと、GDS を展開してから同梱の照合を回す。

```bash
cd gf180/Test-2-4-delivery_20261112
gunzip Test-2-4/gds/Test-2-4.gds.gz reference/Test2-3/gds/Test2-3.gds.gz
python3 -I verify_manifest.py
```

結果は FAIL になるが、エラーは上の入れていない 3 つの「Missing」だけになる（目録の 4,402 ファイルのうち、ほかの 4,399 は大きさと sha256 が合う）。
