# r9：AFE の AVSS の渡りに Metal3 を足したあと（10/29）

**この版は使わない。** 量子化器のラッチのグラウンド（DVSS の端子）が、どこにもつながっていない（11/9 に判明。最初の組み立てから r9 までのすべての版）。今の版は r10（`../r10_20261109/`）。ここの図は、比べるために残している。抽出は基板を AVSS とするので、ここの ADC の結果はラッチを AVSS につないだ形のもので、r10 の抽出でも同じ値になった。

- チップ：9 回目の組み立て（10/29）。6 回目からの違いは 3 つ。
  - 7 回目：ADC の C1・C2 を 1.25 倍にした。
  - 8 回目：コアの DVDD の幹線 2 本をつなぎ、DVDD パッドにつないだ。最初の組み立てから 7 回目まで、コアの DVDD はどの DVDD パッドにもつながっていなかった。
  - 9 回目：AFE の AVSS の Metal4 の渡りの下に Metal3 を足した（電流密度）。
- 作ったのは 7c2e9c70 の上の作業ツリーで、その中身を b5643e80 でコミットした。
- 検証：
  - チップ全体の DRC は違反なし。コアの LVS は一致。
  - パッドリング込みのチップ全体の LVS は、KLayout でも Magic／Netgen でも一致。
  - パッドリング込みのつながりと、GDS だけからの電源の確認も問題なし。
  - 最新の precheck（10/20 版）を、事務局の指定どおり `--slot 1x0p5 --cob` で回して通った（pre_20261029_r9）。
- GDS（穴埋めのあと、precheck に出した形）は `gf180/tapeout/chip/gds/chip_top_fill_r9_20261029.gds.gz`（gzip、41,891,598 バイト）。展開した `chip_top_fill.gds` の sha256 は c96d5b1f…。
- ここの図は、すべてこの版の図として描いた（10/30。25〜27 は起動のバッチが終わった 10/31）。ファイル名と図の右上に版（r9）を書いた。
- **9 回目で変わっていないブロックは、最後に変わった版の結果を使った**（変わっていないことは XOR で確かめた。`gf180_chip_assembly_20261023.md`）。
  - afe_top は 6 回目から同じなので、AFE だけの解析は 6 回目の抽出のもの。
  - adc_top は 7 回目から同じなので、ADC の解析は 7 回目の抽出のもの。
  - チップの配線を通す解析（雑音、入力経路の配線抵抗、起動、OUTP／OUTN の窓）は、9 回目の GDS で取り直した。
  - この対応は `figs_perf.py` の `SRC` と `gf180/tapeout/viz/data_r9/` が持つ。
- 比べるために前の値を並べた列（回路図、10/23 の抽出、B7 の前の DC 経路など）は、図の中にそう書いてある。

## `viz/`：可視化（30 枚）

| 番号 | 図 | 元にしたもの |
|---|---|---|
| 01〜06、14 | 配置と配線、層、ネット、ブロック、パッド | `extract.py`（9 回目の GDS とコアの LVS の結果）→ `gf180/tapeout/viz/data_r9/` |
| 07 | 雑音の予算（チップの上） | `afe_chip_noise.py`（`runs/chip_noise_r9/`：9 回目の配線、AFE_IBIAS 3、モンテカルロ 30）。ADC、パッド、ブランキングの折り返しは 10/26 の予算 |
| 08 | AFE の雑音 | `final_noise_pex_r6.log`、`final_noise_rwire_pex_r6.log` と、チップの上の行（`runs/chip_noise_r9/`） |
| 09 | 配線抵抗 | `pex_rin.py`（`runs/rin_r9_{E,W,T}.log`。6 回目と mΩ まで同じ） |
| 10 | 歪み | `afe_dcpath.py static`（`final_static_pex_r6.log`）、`pex_afe.py sine`（`afe_sine_r6.log`） |
| 11 | 回路図と抽出の比較 | 下の「図 11 の元」 |
| 12、13 | 密度、検証 | 穴埋めのあとの全 DRC、precheck pre_20261029_r9、チップ全体の LVS（KLayout、Magic＋Netgen）、パッドリング込みのつながり、GDS だけからの電源の確認 |
| 15 | 日程 | 10/29 の管理表 |
| 16〜18 | 寄生込みの E2E | `pex_e2e.py`（`runs/e2e_r7/`）。pex と pexchip は AFE の 6 回目と ADC の 7 回目の抽出。d4 と sch は今の回路図 |
| 19、20、23、24 | AFE のループ、帯域内の伝達、入力インピーダンス | `viz_data.py afe_loop`、`bb`、`zin_ac`、`zin`（`runs/viz/`） |
| 21、22 | ADC の OTA、NTF／STF | `viz_data.py ota`、`ntf`（`runs/viz_r7/`） |
| 25〜28 | 電源投入、解除、電極の DC オフセット、フルスケールの正弦波 | `afe_startup.py`（`runs/startup/*_chip_r9`：9 回目のチップの配線、AFE_IBIAS 3、モンテカルロ 30、AVDD ±5 %。バッチ `runs/startup/batch_20261030_r9.txt`、300 mV の M = 996 は 10/31 に足した）と `startup_probe.py`（図 26 の計算点） |
| 29 | ADC のブロックのばらつきと SNDR | `adc_block_mc.py`（`runs/adc_mc/`。ブロックは変わっていない）、`adc_beh_mc.py`（`runs/adc_beh_mc_r7/`、C1・C2 ×1.25） |
| 30 | ADC のトランジスタのループのばらつき | `adc_loop_mc.py`（`runs/adc_mc_loop_r7/`） |

補足：

- **ADC の基準の負荷：** 25〜28 の `afe_startup.py` では、ADC の基準の負荷を今の ADC の値（`RADC` 29.9 kΩ、487.7 mV で 16.3 µA）に直してある。6 回目の図は、C1 を半分にする前の 18.4 kΩ で描いていた。
- **図 27 の電極換算：** DAC を使うランのブランキングは 15 MCLK なので、7 MCLK の利得 298.9 ではなく、DC のラン 9 本を抽出のビットの重みに当てはめた利得 287.3 で割った（`figs_perf.py` の `dac_fit`）。6 回目の図 27 は 298.9 で割っていて、残差が 4 % 小さい。ADC の入力（OUTP − OUTN）の値は変わらない。
- **図 16〜18 の pexchip の窓：** OUTP／OUTN の窓は、9 回目の GDS から切り直した（`runs/chipwin_outpn_cha_r9/`）。容量は 10/24 の窓（`runs/chipwin_outpn_cha/`）と全部同じなので、`runs/e2e_r7/pexchip` はそのまま 9 回目の結果になる。
- **図 28 は抽出だけ：** 回路図の正弦波は、6 回目と同じく ngspice が途中で止まる。9 回目は 1.14 ms、6 回目は 1.33 ms で、どちらも時間刻みが 1.25e-19 s まで落ちる（BRST の枝）。図の注の止まった時刻は、その版の `run.log` から読む。

### 図 11 の元

- **AFE：** `final_gain_pex_r6.log`、`final_ripple_pex_r6.log`。
- **ADC のループ：** `pex_adc.py`。7 回目の抽出は `runs/adc_r7/pex_tstop_100e-6_fsig_20e3/`、今の回路図は `runs/adc_r7/sch_tstop_100e-6_fsig_20e3/` で回した。
- **CLKQ の結合：** `runs/adc_top_c_r7/eeg_adc_pex.spice`。
- **DAC1 の偶成分：** `dac1_even_r6.log`（DAC1 のセルは変わっていない）。
- **行動モデルの SNDR：** `runs/beh_dac1_r9.py` と `.log`（`adc_beh_mc.py`、C1・C2 ×1.25、ELD 0.22）。

ログと CSV は `gf180/tapeout/pex/runs/` にある（git の対象外）。`vizstyle.py` の `CHIP = "r9"` で描く。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs.py gf180/tapeout/viz/data_r9 documentation/figures/gf180/r9_20261029/viz
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r9_20261029/viz
```

## `layout/`：レイアウト（9 枚）

この版の `chip_top.gds`（穴埋めの前）と `chip_top_fill.gds` を、KLayout 0.30.12 で描いた。

- 色は PDK の層の色（`gf180mcu.lyp`）。階層はすべて描き、文字は隠した。
- KLayout の描画は縮めずに貼った。縮めると層の模様がぼけ、PNG が 20〜50 MB になるため。
- ブロックの枠と名前は GDS のセルの配置から取り、名前はレイアウトの生成スクリプトの説明に合わせた。

| 番号 | 図 | 中身 |
|---|---|---|
| 01 | chip | チップ全体（穴埋めの前）：パッドリング、AFE、ADC、デジタル、バイアス、基準電圧のフィルタ、デカップリング、電極のパッド |
| 02 | chip_fill | 提出した形（穴埋めのあと。sha256 は図の副題） |
| 03 | afe | AFE（afe_top）：Cin_P／Cin_N、入力チョッパ、コア、出力部、オフセット DAC、クロックドライバ |
| 04 | adc | ADC（adc_top）：C1P／C1N（1.25 倍で足した分は「rest」の枠）、RIN＋DAC1、OTA1、OTA2、C2、量子化器、DAC2、ADC のデジタル |
| 05 | afe_input | 入力チョッパ（afe_tgin。PMOS／NMOS／PMOS の 3 つのセル）と、Cin とコアの端 |
| 06 | afe_core | AFE のコア：NMOS と PMOS の入力対、テイル、カスコード、ブースタ |
| 07 | quantizer | 量子化器：比較器 31 個、前置増幅器の負荷、しきい値のラダー、VBQ のバイアス |
| 08 | dac1 | RIN と DAC1：抵抗の配列（156 本）、スイッチの列、素子ごとの論理 |
| 09 | ota1 | ADC の OTA1：入力対、負荷、カスコード、チョッパと 2 つの交換器、CMFB、位相補償の MIM |

`gf180/tapeout/layout/runs/chip_top/` に 9 回目の GDS があるときに、次で描ける（穴埋めのあとの形は gz から戻せる）。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/layout_views.py gf180/tapeout/layout/runs/chip_top documentation/figures/gf180/r9_20261029/layout
```

## `e2e_pex/`：寄生込みの E2E（7 枚）

`gf180/tapeout/pex/runs/e2e_r7/` の d4、sch、pex、pexchip から `plot_e2e.py` で描いた。

- 図は 7 枚：AFE の出力、ADC の入力、O1／O2、DAC1、AVDD、版の差、主な値の表。
- 数字は `runs/e2e_r7/summary.json` にも書いた。
- pex と pexchip は、AFE の 6 回目と ADC の 7 回目の抽出。
- `plot_e2e.py` は `vizstyle.py` の版を読み、r9 では `runs/e2e_r7/` を使う。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/pex/plot_e2e.py
```

説明の文書：

- `gf180_viz_20261024.md`
- `gf180_pex_20261023.md`（「寄生込みの E2E」）
- `gf180_realistic_eval_20261028.md`（図 25〜30）
