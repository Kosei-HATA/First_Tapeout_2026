# GF180 E2E 統合・パッドフレーム計画

> **10/22 追記**：この計画は旧構成（SC 2 次 5 bit の mb5 ADC、fs 256 kHz、AFE vb）に基づいている。今回の rev の構成は次の文書を正とする。
> - 全体：`gf180_tapeout_tracker.md`
> - 配置とパッド割り当て：`gf180_floorplan_20261022.md`
>
> 現在の構成は、CT 2 次 5 bit ADC（fs 1.024 MHz）と、利得 318 の CCIA AFE。

2026-10-15。Wafer.space GF180MCU（全ユーザー領域、caravel 不使用）向けの
EEG マクロ統合計画。netlist: `gf180/sim/gf180_e2e_macro.spice`、
ブリングアップ: `gf180/sim/tb_gf180_e2e_bringup.spice`、
デジタル詳細案: `documentation/gf180_digital_spi_proposal_20261008.md`。

## マクロ構成

```
ELP/ELN ──> PGA (gf180_afe_pga_ln: チョッパ IA, vb 低ノイズ, x8/16/32/64)
                │ APGP/APGN
                ▼
           ΣΔ ADC (gf180_sdm3_mod_mb: 5bit 31本サーモメータ, fs=256 kHz)
                │ TH0..TH30
                ▼
           デジタル (コード化 → CIC → FIFO → SPI)  ※RTL 未実装
```

クロック生成（外部 MCLK 32.768 MHz → 128 分周 256 kHz → PH1/NPH1/PH2/NPH2
非重複 + CMPCK + PUP + チョッパ 1/2 kHz 位相生成）もチップ内デジタル
ブロックとする。シミュレーション上は現状これらを外部ピンから与える。

## ピン案（パッドフレーム）

| ピン | 種別 | 説明 |
|---|---|---|
| ELP, ELN | アナログ入力 | 電極差動入力（高入力インピーダンス、ESD 要注意） |
| VCM_REF | アナログ | コモンモード基準 1.65 V（外付けデカップリング推奨） |
| VP, VN | アナログ | ADC DAC 基準 ±25 mV（VCM±25m、外付けデカップリング推奨） |
| MCLK | デジタル入力 | 32.768 MHz 基準クロック（基板発振器から常時供給） |
| SCLK, CS_N, MOSI, MISO | デジタル | SPI スレーブ（Mode 0、1 MHz 標準） |
| DRDY_N | デジタル出力 | データ ready（FIFO 非空で Low） |
| RESET_N | デジタル入力 | 非同期リセット |
| VDD33A / VSSA | 電源 | アナログ 3.3 V（PGA + ADC アナログ部） |
| VDD33D / VSSD | 電源 | デジタル 3.3 V（クロック生成・SPI・CIC/FIFO） |

- ゲイン選択 S8/S16/S32/S64・チョッパ周波数選択は外部ピンではなく
  **SPI 設定レジスタ経由**とする（ピン数削減、`gf180_digital_spi_proposal`
  のレジスタマップ案と整合）。
- アナログ/デジタル電源はパッドレベルで分離し基板で合流。
  ガードリング・ディープ N ウェル分離はレイアウト段で検討。
- Wafer.space のハーフスロット（~4.5 mm² 級）に対し、アナログ部の
  現行見積もり（`gf180/size_estimate.py`）では約 3 分の 1。デジタル部
  （CIC/FIFO/SPI、標準セル合成）は面積的に軽微。

## タイミング基準（fs=256 kHz、TCLK=3.90625 µs）

| 信号 | delay | width | 備考 |
|---|---|---|---|
| PH1 | 1.322 µs | 1.62 µs | 立上り 15 ns |
| PH2 | 3.275 µs | 1.62 µs | 立上り 15 ns、PH1 と非重複 |
| CMPCK | 2.522 µs | 0.36 µs | 立上り 10 ns |
| PUP | 1.342 µs | 0.1 µs | 立上り 5 ns（DWA ポインタ/レジスタ用） |
| チョッパ PHI/PHIB | 50 n / 500.05 µs | 499.85 µs | 1 kHz（2 kHz も検証済み） |

## 既知の未決事項

- デジタル RTL（コード化・CIC・FIFO・SPI・クロック生成）は未実装。
  アナログピン定義は `gf180_e2e_macro.spice` に固定済み。
- AFE の ADC 負荷駆動（16 pF/側・256 kHz サンプリング）は独立検討で
  改善済みだが、E2E スモークでの最終確認が必要。
- ADC の構造改善（ENOB 18 目標の構造再設計）が入った場合、
  マクロの ADC インスタンスを差し替えるだけで済むよう
  `gf180_sdm3_mod_mb` のピン互換を維持する。
