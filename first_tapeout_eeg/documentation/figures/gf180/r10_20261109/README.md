# r10：量子化器のラッチのグラウンドを AVSS につないだあと（11/9、今の版、発注の候補）

- チップ：10 回目の組み立て（11/9）。9 回目からの違いは 1 つ。
  - 量子化器のラッチのグラウンド（DVSS の端子）を、Via4 10 個と Metal5 のストラップ 1 つで、上側の AVSS のレールにつないだ（ユーザーの判断）。
  - r0〜r9 では、この端子がどこにもつながっていなかった。詳しくは `gf180_chip_assembly_20261023.md` の「組み直し（11/9、10 回目）」。
- 作ったのは b5643e80 の上の作業ツリー（コミットはまだ）。
- 検証：
  - チップ全体の DRC は違反なし。コアの LVS は一致。
  - パッドリング込みのチップ全体の LVS は、KLayout でも Magic／Netgen でも一致。
  - パッドリング込みのつながり、GDS だけからの電源の確認、タップの規則（`supply_check.tap_check()`。11/9 に流れに足した）も問題なし。
  - 最新の precheck（10/20 版。11/9 にも最新と確かめた）を、事務局の指定どおり `--slot 1x0p5 --cob` で回して通った（pre_20261109_r10）。
- GDS（穴埋めのあと、precheck に出した形）は `gf180/tapeout/chip/gds/chip_top_fill_r10_20261109.gds.gz`（gzip、41,893,938 バイト）。展開した `chip_top_fill.gds` の sha256 は bf45aaf1…。
- ここの図は、すべてこの版の図として描いた（11/9）。ファイル名と図の右上に版（r10）を書いた。
  - 図 31（デジタル側）は、この版で足した図で、r9 の図にはない。11/11 に、ADC を 10 回目の抽出にしたデッキの結果で描き直した。
  - 図 32（電極の入力と DATA の対応）も、この版で足した図（11/12）。傾きは、10 回目の通しが終わるまでは 9 回目の通しから取る（下の「図 32 の元」）。
  - 図 33（ADC のポリ抵抗のフリッカ雑音）も、この版で足した図（11/12）。RIN と DAC1 の抵抗は 7 回目から変わっていない。
- **10 回目で変わっていないブロックは、最後に変わった版の結果を使った**（変わっていないことは XOR で確かめた。`gf180_chip_assembly_20261023.md`）。
  - afe_top は 6 回目から同じなので、AFE だけの解析は 6 回目の抽出のもの。
  - adc_top は 10 回目で変わった（Via4 と Metal5 だけ）ので、ADC の解析は 10 回目の抽出で回し直した。
  - チップの配線（最上位）は 9 回目と同じなので、チップの配線を通す解析（雑音、入力経路の配線抵抗、起動、OUTP／OUTN の窓）は 9 回目のもの。
  - この対応は `figs_perf.py` の `SRC` と `gf180/tapeout/viz/data_r10/` が持つ。
- **ADC の解析は、10 回目の抽出でも 7 回目の抽出と同じ値になった**（トランジスタのループの 19 本のうち 4 本は、判定の列が途中で一時的に分かれた）。
  - 抽出（Magic）は基板を AVSS とするので、r9 までの抽出でも、ラッチは AVSS につながった形で計算されていた。
  - 10 回目では、それを金属でつないだ。抽出の違いはストラップのまわりだけ（AVSS +12.26 fF、CHOP1 +1.89 fF など）で、ADC のループの節点は 0.03 fF 以下。
  - 図 11 のループの窓では、80 フレームの DAC1 の列が 7 回目と同じだった。O2 の差は 21 µV 以内、第 1 段の差は 0.5 µV 以内。
  - E2E の 4 通り、OTA と NTF、行動モデルも、7 回目と同じ値だった。
  - トランジスタのループ（図 30。typical、モンテカルロ 10、R と MIM の角 6、入力なしの角 2 の 19 本、11/9 の 14:36〜22:07）：
    - 15 本は、80 フレームの判定の列が 7 回目と同じだった。O2 の差は 87 µV 以内、O1 の差は 50 µV 以内で、利得と残差は 4 桁まで同じ。
    - 4 本（mc3、mc8、R ff・C ff、R ss・C ss）は、途中で判定の列が分かれ、4〜38 フレームあとにまた同じ列に戻った。違うフレームは 7、18、4、4 個。
    - 分かれたのは、どれも 1 つのストローブで、2 本の O2 が 3〜19 µV しか違わないのに判定が分かれたところ（その比較器のしきい値のすぐそば）。その前の O2 の差は 17 µV 以内。
    - この 4 本でも利得の差は 0.0003 以内。残差は判定の列で変わり（mc3 0.0221 → 0.0233、mc8 0.0340 → 0.0272、R ff・C ff 0.0339 → 0.0336、R ss・C ss 0.0149 → 0.0146）、どれもリミットサイクルにならない（ストローブでの O2 は ±33.2 mV 以内）。
    - 11/9 の夜に「mc3 は 80 フレームのうち 3 つ」と書いたのは、理想のしきい値と合うフレームの数の差（56 → 53）だった。判定の列で比べると 7 つ。
- 比べるために前の値を並べた列（回路図、10/23 の抽出、B7 の前の DC 経路など）は、図の中にそう書いてある。

## `viz/`：可視化（33 枚）

| 番号 | 図 | 元にしたもの |
|---|---|---|
| 01〜06、14 | 配置と配線、層、ネット、ブロック、パッド | `extract.py`（10 回目の GDS とコアの LVS の結果）→ `gf180/tapeout/viz/data_r10/`。表は 9 回目と同じ値 |
| 07 | 雑音の予算（チップの上） | `afe_chip_noise.py`（`runs/chip_noise_r9/`：9 回目の配線、AFE_IBIAS 3、モンテカルロ 30）。ADC とブランキングの折り返しは 10/26 の予算。パッドと配線の行は AFE の行に入っているので外した（11/9。`gf180_realistic_eval_20261028.md` の「11/9 の見直し」） |
| 08 | AFE の雑音 | `final_noise_pex_r6.log`、`final_noise_rwire_pex_r6.log` と、チップの上の行（`runs/chip_noise_r9/`） |
| 09 | 配線抵抗 | `pex_rin.py`（`runs/rin_r9_{E,W,T}.log`） |
| 10 | 歪み | `afe_dcpath.py static`（`final_static_pex_r6.log`）、`pex_afe.py sine`（`afe_sine_r6.log`） |
| 11 | 回路図と抽出の比較 | 下の「図 11 の元」 |
| 12、13 | 密度、検証 | 穴埋めのあとの全 DRC（Metal5 65.78 %）、precheck pre_20261109_r10、チップ全体の LVS（KLayout、Magic＋Netgen）、パッドリング込みのつながり、GDS だけからの電源の確認、タップの規則 |
| 15 | 日程 | 11/9 の管理表 |
| 16〜18 | 寄生込みの E2E | `pex_e2e.py`（`runs/e2e_r10/`）。pex と pexchip は AFE の 6 回目と ADC の 10 回目の抽出。d4 と sch は今の回路図 |
| 19、20、23、24 | AFE のループ、帯域内の伝達、入力インピーダンス | `viz_data.py afe_loop`、`bb`、`zin_ac`、`zin`（`runs/viz/`） |
| 21、22 | ADC の OTA、NTF／STF | `viz_data.py ota`、`ntf`（`runs/viz_r10/`） |
| 25〜28 | 電源投入、解除、電極の DC オフセット、フルスケールの正弦波 | `afe_startup.py`（`runs/startup/*_chip_r9`：9 回目のチップの配線、AFE_IBIAS 3、モンテカルロ 30、AVDD ±5 %。バッチ `runs/startup/batch_20261030_r9.txt`）と `startup_probe.py`（図 26 の計算点） |
| 29 | ADC のブロックのばらつきと SNDR | `adc_block_mc.py`（`runs/adc_mc/`。ブロックは変わっていない）、`adc_beh_mc.py`（`runs/adc_beh_mc_r10/`、C1・C2 ×1.25、ELD 0.22） |
| 30 | ADC のトランジスタのループのばらつき | `adc_loop_mc.py`（`runs/adc_mc_loop_r10/`：10 回目の抽出、typical、モンテカルロ 10、R と MIM の角 6、入力なしの角 2） |
| 32 | 電極の入力と DATA の対応 | `figs_perf.py` の `fig_input_output`：電源投入からの通し（`runs/e2e_startup/…_r10_chain/` が終わっていればそれ、なければ `…_r9_chain/`）、`afe_startup.py`（`runs/startup/*_chip_r9`：電極 0 V と DC オフセット）、`runs/viz/afe_baseband_pex_A.csv`、`runs/viz_r10/adc_ntf_stf.csv`、`data_r10/budget.csv`。下の「図 32 の元」 |
| 33 | ADC のポリ抵抗のフリッカ雑音 | `figs_perf.py` の `fig_adc_flicker`：`adc_flicker.py`（`runs/adc_flicker/`：PDK の式の ngspice での確認、行動モデルのコード列を RTL の DWA に通した 4.1 s の計算、I_cal の掃引）。`gf180_realistic_eval_20261028.md` の 11/12 の評価 |
| 31 | デジタル側：9 個のパッドとデジタルブロックの電源電流 | `digital_noise.py --adc r10`（`runs/digital_noise_r10/`。9 回目の通しのチャンク 14 の ADC を 10 回目の抽出に替え、デジタルのパッド、ブロックの電源電流、チップの DVDD／DVSS を足した 4 通りと、何も足さないもの（A）。比べた値は `compare.json`）。下の「図 31 のデッキ」 |

補足：

- **図 29 の行動モデルの結果：** 10 回目は、角、モンテカルロ、DAC1 の偶成分の掃引の 3 つを 1 回で回したので、1 つのファイル（`even_corners_mc_ain0.3_eld0.2200.json`）に入っている。`figs_perf.py` の `beh()` は、場合ごとのファイル（6 回目、7 回目）と、この形の両方を読む。
- **ADC の基準の負荷：** 25〜28 の `afe_startup.py` では、ADC の基準の負荷を今の ADC の値（`RADC` 29.9 kΩ、487.7 mV で 16.3 µA）にしてある。
- **図 27 の電極換算：** DAC を使うランのブランキングは 15 MCLK なので、7 MCLK の利得 298.9 ではなく、DC のラン 9 本を抽出のビットの重みに当てはめた利得 287.3 で割った（`figs_perf.py` の `dac_fit`）。
- **図 16〜18 の pexchip の窓：** OUTP／OUTN の窓は 9 回目の GDS から切り直したもの（`runs/chipwin_outpn_cha_r9/`）。10 回目の最上位の配線は 9 回目と同じ。
- **図 28 は抽出だけ：** 回路図の正弦波は、ngspice が 1.14 ms で止まる（時間刻みが 1.25e-19 s まで落ちる、BRST の枝）。図の注の止まった時刻は、その版の `run.log` から読む。
- **図 31 のデッキ：** 9 回目の通し（`e2e_startup.py`、`--tag _r9`）のチャンク 14 の写しで、ADC を 10 回目の抽出（`runs/adc_top_c_r10`）に差し替えたもの（`digital_noise.py --adc r10`、`runs/digital_noise_r10/`、11/10〜11/11）。
  - A は、そのデッキに何も足さずに同じ窓を回したもの。
  - 11/9 に描いた図 31 は、ADC が 7 回目の抽出のデッキ（`runs/digital_noise/`、A は通しのチャンクそのもの）の結果だった。
  - 5 本とも、48 フレームの ADC の符号は 7 回目の抽出のときと同じだった。周期ごとの差（電極換算）は、計算の差（b1iso − A）が最大 1.66 nV、ほかの組が 0.85 nV 以下。7 回目の抽出との違いは計算の差の範囲に入る（`gf180_realistic_eval_20261028.md` の「10 回目の抽出での回し直し」）。
  - b2 の MISO と DRDY_N は、b3 の RAW と同じく、チップのクロックの格子から 0.125 ns 遅らせた（11/11。格子の上のままでは、10 回目の抽出の b2 が区切り点の近さで止まった）。
  - 図の値は `digital_noise.py compare --adc r10` が書く `compare.json`（周期ごとの差を、一定のずれ、16 kHz の成分、残りに分けた当てはめと、AFE の入力の揺れを含む）から読み、波形は各組の `out.raw` から描く。

- **図 32 の元：** 傾きは通しの最後の有効なサンプル（+0.3 mV の DC）で、CIC の重みで平均した ADC の入力と電極から求めた（ADC 1.03129 × 2^24／V、AFE 297.50、電極 0 V の起動のランの出力 −0.0748 mV を引いて 297.75）。
  - 11/12 に描いた図は 9 回目の通しの値。10 回目の通しが終わったら（11/13 の昼ごろの見込み）、同じコマンドで描き直すと 10 回目の値になる。
  - DAC を使うときの利得 287.25 は、図 27 と同じ `dac_fit`。周波数は、AFE（チョッパ込みの調波の和）× STF × CIC の sinc³。
  - 値の表と説明は `documentation/gf180_input_output_20261112.md`。

### 図 11 の元

- **AFE：** `final_gain_pex_r6.log`、`final_ripple_pex_r6.log`。
- **ADC のループ：** `pex_adc.py` が回路を書き、そのフォルダで ngspice を回した（`pex_adc.py` は回路を書くだけ）。
  - 10 回目の抽出は `runs/adc_r10/pex_tstop_100e-6_fsig_20e3/`、今の回路図は `runs/adc_r10/sch_tstop_100e-6_fsig_20e3/`。
  - 要約は `runs/adc_r10/{pex,sch}_bench.log`（`tr_window.py` と `pex_adc.py codes`）。
- **CLKQ の結合：** `runs/adc_top_c_r10/eeg_adc_pex.spice`（O2P 2.0100 fF、O2N 2.0088 fF。7 回目と同じ）。
- **DAC1 の偶成分：** `dac1_even_r6.log`（DAC1 のセルは変わっていない）。
- **行動モデルの SNDR：** `runs/beh_dac1_r9.py` と `.log`（`adc_beh_mc.py`、C1・C2 ×1.25、ELD 0.22。入れるのは DAC1 の抽出の偶成分だけで、10 回目でも変わらない）。

ログと CSV は `gf180/tapeout/pex/runs/` にある（git の対象外）。`vizstyle.py` の `CHIP = "r10"` で描く。図 18 は `runs/e2e_r10/summary.json` を読むので、`plot_e2e.py` を先に回す。図 31 は `compare.json` を読むので、`digital_noise.py compare --adc r10` を先に回す。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/pex/digital_noise.py compare --adc r10
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs.py gf180/tapeout/viz/data_r10 documentation/figures/gf180/r10_20261109/viz
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/pex/plot_e2e.py
```

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/figs_perf.py gf180/tapeout/pex documentation/figures/gf180/r10_20261109/viz
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

10 回目の GDS は `gf180/tapeout/layout/runs/chip_top/r10_20261109/` にもある（穴埋めのあとの形は gz から戻せる）。次で描ける。

```bash
gf180/tools/venv310/bin/python gf180/tapeout/viz/layout_views.py gf180/tapeout/layout/runs/chip_top/r10_20261109 documentation/figures/gf180/r10_20261109/layout
```

## `e2e_pex/`：寄生込みの E2E（7 枚）

`gf180/tapeout/pex/runs/e2e_r10/` の d4、sch、pex、pexchip から `plot_e2e.py` で描いた。

- 図は 7 枚：AFE の出力、ADC の入力、O1／O2、DAC1、AVDD、版の差、主な値の表。
- 数字は `runs/e2e_r10/summary.json` にも書いた。7 回目の抽出の結果（`runs/e2e_r7/`）と同じ値。
- pex と pexchip は、AFE の 6 回目と ADC の 10 回目の抽出。
- `plot_e2e.py` は `vizstyle.py` の版を読み、r10 では `runs/e2e_r10/` を使う。

説明の文書：

- `gf180_viz_20261024.md`
- `gf180_chip_assembly_20261023.md`（「組み直し（11/9、10 回目）」）
- `gf180_pex_20261023.md`（「寄生込みの E2E」）
- `gf180_realistic_eval_20261028.md`（図 25〜31）
