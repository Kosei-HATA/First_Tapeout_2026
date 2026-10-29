# r6：Magic DRC の直しのあと（10/26、今の版）

- チップ：c752ec78（6 回目の組み立て：抵抗の頭のコンタクト、MIM の下の板の Via4、穴埋めの COMP／ポリを木に組み替えた形）。チップ全体の DRC 違反なし、コアの LVS 一致、precheck は pre_20261026 で通り、10/27 に最新の precheck（10/20 版）と `--slot 1x0p5 --cob` でも通った（pre_20261027_cob。`chip_top_fill.gds` の sha256 1343e9cc…）。
- GDS（穴埋めのあと、precheck に出した形）は `gf180/tapeout/chip/gds/chip_top_fill_r6_20261026.gds.gz`（gzip、42 MB）。
- ここの図は、すべてこの版の GDS、コアの LVS の結果、抽出から描いた（10/26 夜）。ファイル名と図の右上に版（r6）を書いた。
- 比べるために前の値を並べた列（回路図、10/23 の抽出、B7 の前の DC 経路など）は、図の中にそう書いてある。

## `viz/`：可視化（24 枚）

| 番号 | 図 | 元にしたもの |
|---|---|---|
| 01〜06、14 | 配置と配線、層、ネット、ブロック、パッド | `extract.py`（6 回目の GDS とコアの LVS の結果）→ `gf180/tapeout/viz/data/` |
| 07〜09 | 雑音の予算、AFE の雑音、配線抵抗 | `pex_rin.py`（`runs/rin_r6_{W,E,T}.log`）、`final_noise_pex_r6.log`、`final_noise_rwire_pex_r6.log` |
| 10 | 歪み | `afe_dcpath.py static`（`final_static_pex_r6.log`）、`pex_afe.py sine`（`afe_sine_r6.log`） |
| 11 | 回路図と抽出の比較 | AFE：`final_gain_pex_r6.log`、`final_ripple_pex_r6.log`。ADC：`dac1_even_r6.log`、行動モデル（`beh_dac1_r6.log`）、ループ（`pex_adc.py`、`runs/adc/pex_tstop_100e-6_fsig_20e3/`）、CLKQ の結合（`runs/adc_top_c/eeg_adc_pex.spice`） |
| 12、13 | 密度、検証 | 穴埋めのあとの全 DRC、precheck pre_20261027_cob（10/20 版、`--slot 1x0p5 --cob`）、Magic DRC |
| 15 | 日程 | 10/26 の管理表 |
| 16〜18 | 寄生込みの E2E | `pex_e2e.py run pex`／`run pexchip`（6 回目の抽出）。d4 と sch は回路図 |
| 19、20 | AFE のループ、帯域内の伝達 | `viz_data.py afe_loop`、`bb`、`zin`（帯域内の過渡の菱形） |
| 21、22 | ADC の OTA、NTF／STF | `viz_data.py ota`、`ntf`（6 回目の adc_top の抽出） |
| 23、24 | 入力インピーダンス | `viz_data.py zin_ac`、`zin` |

ログと CSV は `gf180/tapeout/pex/runs/` と `runs/viz/`（git の対象外）。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs.py gf180/tapeout/viz/data documentation/figures/gf180/r6_20261026/viz
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r6_20261026/viz
```

## `layout/`：レイアウト（9 枚）

この版の `chip_top.gds`（穴埋めの前）と `chip_top_fill.gds` を KLayout 0.30.12 で描いた（PDK の層の色 `gf180mcu.lyp`、階層はすべて、文字は隠す）。KLayout の描画は縮めずに貼った（縮めると層の模様がぼけ、PNG が 20〜50 MB になる）。ブロックの枠と名前は GDS のセルの配置から取り、名前はレイアウトの生成スクリプトの説明に合わせた。

| 番号 | 図 | 中身 |
|---|---|---|
| 01 | chip | チップ全体（穴埋めの前）：パッドリング、AFE、ADC、デジタル、バイアス、基準電圧のフィルタ、デカップリング、電極のパッド |
| 02 | chip_fill | 提出した形（穴埋めのあと。sha256 は図の副題） |
| 03 | afe | AFE（afe_top）：Cin_P／Cin_N、入力チョッパ、コア、出力部、オフセット DAC、クロックドライバ |
| 04 | adc | ADC（adc_top）：C1P／C1N、RIN＋DAC1、OTA1、OTA2、C2、量子化器、DAC2、ADC のデジタル |
| 05 | afe_input | 入力チョッパ（afe_tgin。PMOS／NMOS／PMOS の 3 つのセル）と、Cin とコアの端 |
| 06 | afe_core | AFE のコア：NMOS と PMOS の入力対、テイル、カスコード、ブースタ |
| 07 | quantizer | 量子化器：比較器 31 個、前置増幅器の負荷、しきい値のラダー、VBQ のバイアス |
| 08 | dac1 | RIN と DAC1：抵抗の配列（156 本）、スイッチの列、素子ごとの論理 |
| 09 | ota1 | ADC の OTA1：入力対、負荷、カスコード、チョッパと 2 つの交換器、CMFB、位相補償の MIM |

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/layout_views.py gf180/tapeout/layout/runs/chip_top documentation/figures/gf180/r6_20261026/layout
```

## `e2e_pex/`：寄生込みの E2E（7 枚）

`gf180/tapeout/pex/runs/e2e/` の d4、sch、pex、pexchip（pex と pexchip が 6 回目の抽出）から `plot_e2e.py` で描いた：AFE の出力、ADC の入力、O1／O2、DAC1、AVDD、版の差、主な値の表。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/pex/plot_e2e.py
```

説明の文書：`gf180_viz_20261024.md`、`gf180_pex_20261023.md`（「寄生込みの E2E」と「Magic DRC の直しのあと」）。
