# r12：敏感な網の下からクロックとデータの線を外したあと（11/13、今の版、発注の候補）

- チップ：12 回目の組み立て（11/13）。10 回目からの違いは 2 回分。
  - 11 回目（11/12〜13）：ADC の RIN、DAC1、R21 を ppolyf_u にした（ポリ抵抗のフリッカ雑音への対策。ユーザーの判断）。
  - 12 回目（11/13）：ADC の SEL1_0〜30 と DAC_CLK を I1N／O1P の Metal5 の幹の下で Metal2 にくぐらせ、上を Metal4 の AVSS の板で覆った。AFE では、クロックドライバの西の行の上から WN の Metal5 を外し、入力チョッパのゲートの通路に Metal4 の覆い（AVDD）を置いた（ユーザーの判断）。
  - 詳しくは `gf180_chip_assembly_20261023.md` の「組み直し（11/12〜13、11 回目）」と「組み直し（11/13、12 回目）」。
- 作ったのは 8de0a0f0 の上の作業ツリー。その設計のファイルは、11/16 に a4e731a5 でそのままコミットした。
- 検証：
  - チップ全体の DRC は違反なし。穴埋めのあとの全 DRC も違反なし。コアの LVS は一致。
  - パッドリング込みのチップ全体の LVS は、KLayout でも Magic／Netgen でも一致。
  - パッドリング込みのつながり、GDS だけからの電源の確認、タップの規則も問題なし。
  - 敏感な網とスイッチする網の交差（`crossings.py`、11/13 に足した）：指摘の組の覆いのない重なりは 0 か 0.01 fF。
  - 最新の precheck（10/20 版。11/13 にも最新と確かめた）を、事務局の指定どおり `--slot 1x0p5 --cob` で回して通った（pre_20261113_r12）。
- GDS（穴埋めのあと、precheck に出した形）は `gf180/tapeout/chip/gds/chip_top_fill_r12_20261113.gds.gz`（gzip、41,882,152 バイト）。展開した `chip_top_fill.gds` の sha256 は 6b832e0e…。
- ここの図は、すべてこの版の図として描いた（11/14）。ファイル名と図の右上に版（r12）を書いた。
  - **まだ描いていない図：** 31（デジタル側。12 回目の通しのチャンク 14 で、11/16 の 3 時 49 分から E コアで回している。1 日ほどかかる）。32（電極の入力と DATA の対応）は、12 回目の通しが 11/16 の 12 時 3 分に終わったので描いた。
  - 図 25〜28 は、起動のバッチ（50 本）が 11/16 の 3 時 44 分に終わってから描いた。
  - 図 34（敏感な網とスイッチする網の交差）、図 35（フルスケールの正弦波から出した ENOB、11/14）、図 36（ADC の OTA の非線形と DAC1 のジッタ、11/15）、図 37（電源投入のプロセスの角と電源の立ち上がりの速さ、11/15）は、この版で足した図。
  - 図 38（角での AFE の解除）、図 39（電極オフセットがある最初の電源投入）、図 40（ADC の過負荷）、図 41（AFE の線形性の窓）は 11/16 に足した図。図 40（8 時 52 分）と図 38（9 時 31 分）は、回していた計算がそろったので描き直した。39 と 41 はまだ途中（回している計算があり、そろったら描き直す）。11 時 7〜9 分に終わった 100 µs のパルスと ±1 % の 2 本を入れて、39 と 41 を描き直した（39 は 4 段にして、パルスの中と図 27 との差を足した）。41 は 12 時 52 分に終わった窓の端の 2 本を入れて仕上げた。
- **12 回目で変わっていないものは、最後に変わった版の結果を使った**（変わっていないことは XOR かデッキの比べで確かめた）。
  - adc_rdac、OTA、量子化器、eeg_bias、eeg_ref は 11 回目と同じなので、ブロックのモンテカルロ（図 29）とポリ抵抗のフリッカ（図 33）は 11 回目のもの。行動モデル（図 29）も 11 回目のブロックのモンテカルロから回した（`runs/adc_beh_mc_r11/`）。
  - 寄生込みの E2E（図 16〜18）の d4 と sch は、11 回目の実行の写し。回路図のデッキは版によらず、`pex_e2e.deck_text()` が 11 回目のものと 1 文字も違わず、読み込むファイルもその実行より前のまま（`runs/e2e_r12/README.md`）。
  - 図 20、23、24 のチョッパ込みの過渡（入力インピーダンスと帯域内の伝達の点）の回路図の行は、6 回目の実行の写し。AFE の回路図は 10/24 16:52 から変わっておらず、その実行は 10/24 22:05〜10/25 0:39（`runs/viz_r12/README.md`）。
  - この対応は `figs_perf.py` の `SRC`、`gf180/tapeout/viz/data_r12/`、`runs/e2e_r12/` と `runs/viz_r12/` の README が持つ。
- **12 回目の抽出の結果は、11 回目と同じ大きさ。**
  - AFE（図 19〜24）：ループ、帯域内の伝達は 6 回目と 4 桁まで同じ。リップルは 2.37 → 1.76 mV p-p（西の行のクロックが WN に結合しなくなった）。電極の DC 電流は ±1.56 → ±1.71 nA（通路のレーンの結合の残りが、ほかの非対称を一部打ち消していた分。ユーザーの判断で覆いは残した）。
  - ADC（図 11、16〜18、21、22、30）：ループの利得 0.9978、残差 0.0190（11 回目は 1.0003、0.0172。短い窓の値は DAC1 の列で変わる）。トランジスタのループ 19 本はどれもリミットサイクルにならない（量子化器の入力 ±34.3 mV 以内）。
  - ブロックのモンテカルロ（図 29）：OTA1 の利得のばらつきが 0.09 → 0.46 dB に増えた。負荷（RIN、R21）が ppolyf_u になり、OTA1 のバイアス電流を決める eeg_bias の ppolyf_u_1k と別々にばらつくため（6 回目との差が 2 つの抵抗の比と相関 0.999）。最悪の 69.26 dB でも、行動モデルの 68.7 dB より高い。30 ダイの SNDR は 114.8〜153.8 dB。
- 比べるために前の値を並べた列（回路図、10/23 の抽出、B7 の前の DC 経路など）は、図の中にそう書いてある。

## `viz/`：可視化（41 枚、残り 1 枚はまだ）

| 番号 | 図 | 元にしたもの |
|---|---|---|
| 01〜06、14 | 配置と配線、層、ネット、ブロック、パッド | `extract.py`（12 回目の GDS とコアの LVS の結果）→ `gf180/tapeout/viz/data_r12/`。ADC の抵抗は ppolyf_u 66、ppolyf_u_1k 94（10 回目は ppolyf_u_1k 160。KLayout が直列と並列をまとめた数） |
| 07 | 雑音の予算（チップの上） | `afe_chip_noise.py`（`runs/chip_noise_r12/`：12 回目の配線、AFE_IBIAS 3、モンテカルロ 30）。ADC とブランキングの折り返しは 10/26 の予算。ADC のポリ抵抗のフリッカ（フルスケール、ppolyf_u で 0.29 nVrms）の行を足した（`runs/adc_flicker_r11/`） |
| 08 | AFE の雑音 | `runs/afe_r12/noise_pex.log`、`noise_pex_rwire.log` と、チップの上の行（`runs/chip_noise_r12/typical_ib3.log`） |
| 09 | 配線抵抗 | E と T は 9 回目の `pex_rin.py`（変わっていない）、W は 12 回目の afe_top（WN 0.359 Ω。11 回目より 2 mΩ 高い） |
| 10 | 歪み | `afe_dcpath.py static`（`runs/final_static_pex_r12.log`。11/14 から版ごとに `runs/afe_dcpath_r12/`）、`pex_afe.py sine`（`runs/afe_r12/sine_pex.log`） |
| 11 | 回路図と抽出の比較 | 下の「図 11 の元」 |
| 12、13 | 密度、検証 | 密度は precheck pre_20261113_r12 の density の段（Metal5 65.76 %）。13 は穴埋めのあとの全 DRC、precheck、チップ全体の LVS（KLayout 90,726 素子、Magic＋Netgen 90,779 素子・51,211 ネット）、コアの LVS（88,768 素子）、つながり、電源、タップ、交差の数え上げ |
| 15 | 日程 | 11/14 の管理表 |
| 16〜18 | 寄生込みの E2E | `pex_e2e.py`（`runs/e2e_r12/`）。pex と pexchip は AFE と ADC の 12 回目の抽出、OUTP／OUTN は `chipnets_r12`。d4 と sch は今の回路図（11 回目の実行の写し） |
| 19、20、23、24 | AFE のループ、帯域内の伝達、入力インピーダンス | `viz_data.py afe_loop`、`bb`、`zin_ac`、`zin`（`runs/viz_r12/`） |
| 21、22 | ADC の OTA、NTF／STF | `viz_data.py ota`、`ntf`（`runs/viz_r12/`） |
| 25〜28 | 電源投入、解除、電極の DC オフセット、フルスケールの正弦波 | `afe_startup.py`（`runs/startup/*_chip_r12`：12 回目のチップの配線、AFE_IBIAS 3、モンテカルロ 30、AVDD ±5 %。バッチ `runs/startup/batch_20261113_r12.txt`）と `startup_probe.py`（図 26 の計算点） |
| 29 | ADC のブロックのばらつきと SNDR | `adc_block_mc.py`（`runs/adc_mc_r11/`。12 回目のブロックは同じ）、`adc_beh_mc.py`（`runs/adc_beh_mc_r11/`、C1・C2 ×1.25、ELD 0.22） |
| 30 | ADC のトランジスタのループのばらつき | `adc_loop_mc.py`（`runs/adc_mc_loop_r12/`：12 回目の抽出、typical、モンテカルロ 10、R と MIM の角 6、入力なしの角 2） |
| 31 | デジタル側：9 個のパッドとデジタルブロックの電源電流 | **まだ**（`digital_noise.py --chain r12`：12 回目の通しのチャンク 14 の写しで b1、b1iso、b2、b3 を回している。`runs/digital_noise_r12/`） |
| 32 | 電極の入力と DATA の対応 | `figs_perf.py` の `fig_input_output`（`runs/e2e_startup/…_r12_chain/`：12 回目の通し、11/16 に終わった。起動のラン `runs/startup/*_chip_r12`。値の表は `gf180_input_output_20261112.md`） |
| 33 | ADC のポリ抵抗のフリッカ雑音 | `figs_perf.py` の `fig_adc_flicker`：`adc_flicker.py`（`runs/adc_flicker_r11/`：作ったままの 1 単位、ppolyf_u 2 本の直列） |
| 34 | 敏感な網とスイッチする網の交差 | `crossings_fig.py`（`gf180/tapeout/viz/data_r12/crossings.json`：`crossings.py` を 11 回目と 12 回目の LVS のデータベースで回したもの、抽出の結合） |
| 35 | フルスケールの正弦波から出した ENOB | `enob_sine.py`（`runs/enob_sine_r12/`：電極に 0.943 mV pk・10.13 Hz。AFE は 12 回目の静的な伝達とチップの上のモンテカルロの雑音、ADC は 11 回目のブロックのモンテカルロのダイで行動モデルのループ、eeg_cic3 はビット一致。DATA 8192 点の FFT）→ `enob_fig.py` |
| 36 | ADC の OTA の非線形と DAC1 のジッタ（フルスケール） | `ota_static.py`（`runs/ota_static_r12/`：抽出した OTA1 と OTA2 を段の負荷で DC スイープ。OTA1 はチョッパの両相、typical、角 4、モンテカルロ 1〜10。OTA2 は typical と角）、`ota_distortion.py`（行動モデルの積分器の出力に当てた入力での誤差、DAC1 のジッタの感度）、`enob_sine.py --ota-nl`（`runs/enob_sine_r12/enob_sine_otanl.json`）→ `ota_fig.py` |
| 37 | 電源投入：プロセスの角、AVDD ±5 %、電源の立ち上がり 10 µs〜100 ms | `powerup_checks.py`（`afe_startup.py` の power、AFE はリセットのまま、起動回路の SB と G1 も残す。`runs/startup/power_*_su_*_chip_r12/`：角 4 つと typical × 3.135／3.3／3.465 V、立ち上がり 10 µs／10 ms／100 ms と 100 ms の ss・sf）。比べるモンテカルロは図 26 のラン（RESET_N の前の code 2）→ `powerup_fig.py` |
| 38 | 角での AFE の解除 | `corner_start_fig.py`（`runs/startup/start_*_sine0.943mV2000Hz_*_chip_r12`：`afe_startup.py` の start と `afe_trim_start.py`。角 5、AVDD 3.3／3.135 V、BOOST_TRIM 4/4 と 10/22 の表のトリム、AFE_IBIAS 3、ss 2/2 は 2 も） |
| 39 | 電極オフセットがある最初の電源投入（途中） | `saturation_fig.py`（`runs/startup/start_c1e-08_v3.3_typical_+{30,300}mV_*_sat6ms*_chip_r12`：`afe_saturation.py`。DAC を切ったまま解除、6.0 ms に書く、AFE_RST の入れ直し 20 µs と 100 µs）。比べるのは図 27 のラン。300 mV の 11 ms までと、ss での 100 µs のパルスを回している |
| 40 | ADC の過負荷 | `overload_fig.py`（`adc_overload.py` の抽出した ADC のループ：±2.5 V と 20 kHz の正弦波、+2.5 V を 150 µs のあと −39 mV の DC。`adc_overload_beh.py` の行動モデル：抽出との比べ、同じ状態からの 2 ms、42 ダイ × 300 状態のスイープ。`runs/adc_overload_r12/`） |
| 41 | AFE の線形性の窓：AVDD に対するフルスケールの HD3 | `afe_window_fig.py`（`gf180/tapeout/sim/afe/afe_margin_map.py`：`runs/margin_map/hd_window.json`、`calib.json`、`map_fine3.json`）。チップの点は図 38 のランと、AVDD 3.40 V の 5 本（`runs/startup/start_c1e-08_v3.4_*_chip_r12`）、3.40 V ±1 % の 2 本（ss 3.366 V、ff 3.434 V）と窓の端の 2 本（ff 3.465 V、ss 3.45 V、`run_edges.py`）。入力対の余裕は `calib.py` の台（3.4845 V の点も） |
| 42 | AFE の雑音：AVDD と BOOST_TRIM（途中） | `afe_noise_avdd_fig.py`（`gf180/tapeout/pex/afe_chip_noise.py --avdd --boost --corner`：`runs/chip_noise_r12/chip_A_ib3_*`、凍結した相 A、AFE_IBIAS 3、各角の typical のモデル。PMOS 入力対の余裕は `afe_chip_noise.op_margins`。typical の BTRIM_P 4 のチップの HD3 は `runs/startup/start_c1e-08_v{3.4,3.45}_typical_*_bt4-4_chip_r12` と `start_c1e-08_v3.4_typical_*_bt4-2_chip_r12`（`afe_trim_start.py`）を図 41 と同じ方法で。4/4 の 2 本は 11/16 の 21 時 11 分に終わり、途中の版に入れた。4/2 は回している） |

### 図 11 の元

- **AFE：** `runs/afe_r12/tran_pex.log`（利得 297.89、入力換算のオフセット −0.337 µV、リップル 1.76 mV p-p）。INP／INN の寄生は 12 回目の抽出で 20.0／25.0 pF（6 回目と同じ）。
- **ADC のループ：** `pex_adc.py` が回路を書き、そのフォルダで ngspice を回した。
  - 12 回目の抽出は `runs/adc_r12/pex_tstop_100e-6_fsig_20e3/`、今の回路図（ppolyf_u）は `runs/adc_r11/sch_tstop_100e-6_fsig_20e3/`。
  - 要約は `runs/adc_r12/pex_bench.log` と `runs/adc_r11/sch_bench.log`（`tr_window.py` と `pex_adc.py codes`）。
- **CLKQ の結合：** `runs/adc_top_c_r12/eeg_adc_pex.spice`（O2P 2.0100 fF、O2N 2.0088 fF。7 回目と同じ）。
- **DAC1 の偶成分：** 11 回目の抽出での `dac1_check.py`（1 素子 −0.00090 fC、31 素子 −0.00138 fC）と、ppolyf_u の回路図（11/12 の調べ、+0.00009／−0.00001 fC）。
- **行動モデルの SNDR：** `runs/adc_beh_mc_r11/even_points_eld0.22.log`（1 素子の偶成分を全素子に入れた。回路図 146.6 dB、抽出 126.5 dB）。

ログと CSV は `gf180/tapeout/pex/runs/` にある（git の対象外）。`vizstyle.py` の `CHIP = "r12"` で描く。図 18 は `runs/e2e_r12/summary.json` を読むので、`plot_e2e.py` を先に回す。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs.py gf180/tapeout/viz/data_r12 documentation/figures/gf180/r12_20261113/viz
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/pex/plot_e2e.py
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r12_20261113/viz
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/crossings_fig.py plot
```

## `layout/`：レイアウト（9 枚）

この版の `chip_top.gds`（穴埋めの前）と `chip_top_fill.gds` を、KLayout 0.30.12 で描いた。描き方は 10 回目と同じ（`r10_20261109/README.md`）。

- 08（RIN と DAC1）の説明は、11 回目からの抵抗（1 単位が ppolyf_u の 320.48 × 0.8 µm の 2 本の直列）に合わせた。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/layout_views.py gf180/tapeout/layout/runs/chip_top documentation/figures/gf180/r12_20261113/layout
```

## `e2e_pex/`：寄生込みの E2E（7 枚）

`gf180/tapeout/pex/runs/e2e_r12/` の d4、sch、pex、pexchip から `plot_e2e.py` で描いた。数字は `runs/e2e_r12/summary.json` にも書いた。

| | 寄生込み（pex） | チップの配線込み（pexchip） |
|---|---|---|
| AFE の利得 | 291.4 | 290.6 |
| 全体の利得 | 300.4 | 299.5 |
| 量子化の残差 | 0.019 | 0.014 |

説明の文書：

- `gf180_chip_assembly_20261023.md`（「組み直し（11/12〜13、11 回目）」「組み直し（11/13、12 回目）」）
- `gf180_realistic_eval_20261028.md`（ADC、フリッカ、雑音）
- `gf180_tapeout_tracker.md`
