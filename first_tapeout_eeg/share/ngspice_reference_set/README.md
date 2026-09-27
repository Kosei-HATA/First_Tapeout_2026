# ngspice リファレンスセット（互換性テスト用）

ngspice-46（Homebrew、macOS arm64）で実際に実行したデッキと結果ファイルのセット。
各デッキは実行時に `results/` 相当の CSV を `wrdata` で出力する。

## セット一覧

| デッキ（decks/） | 結果（results/） | 解析 | カバーする機能 |
|---|---|---|---|
| tb_zin_sanity.spice | zin_sanity.csv | AC | 最小構成（受動素子のみ、電流源 AC、複素数出力 mag/ph）。まずこれから |
| tb_fet_dc.spice | fet_dc_idvg.csv 他 2 本 | DC | GF180 nfet/pfet モデル（ciel PDK）、DC 掃引、meas |
| tb_bias_start.spice | bias_start_cmp.csv | tran | beta-multiplier バイアス生成器の起動、サブ circuit、疑似抵抗（MOS 非線形）、2 回路並列比較 |
| tb_ac_ol_ph.spice | ac_ol_ph.csv | AC | チョップ OTA 開ループ（多数サブ circuit 階層）、ゲイン+位相の wrdata |
| tb_noise_cmp_base.spice | noise_cmp_base.csv | noise | .noise 解析（onoise_spectrum）、凍結チョッパ構成 |
| tb_sdm1ct_pr.spice | sdm1ct_pr.csv.gz（gunzip して使用） | tran（長時間） | ΣΔ ADC: PULSE クロック、TG スイッチ、strongARM、NAND ラッチ、B ソース（行為モデル）、疑似抵抗、nodeset、save 限定 + wrdata |

## 依存ファイル

- sky130 系デッキ（tb_bias_start, tb_ac_ol_ph, tb_noise_cmp_base, tb_sdm1ct_pr）は
  `.lib .../sky130A/libs.tech/ngspice/sky130.lib.spice tt` を絶対パスで参照する
  （このマシンでは volare 版 PDK が ~/.volare にある）。他環境で動かす場合はパスを
  書き換えること。
- tb_fet_dc.spice は GF180（ciel 版 gf180mcuD）のモデルを参照。
- tb_zin_sanity.spice は PDK 不要（受動のみ）。

## 実行方法（再現）

```bash
cd <deck のあるディレクトリの元の場所>  # wrdata の相対パス ../results/ に注意
/opt/homebrew/bin/ngspice -b tb_xxx.spice
```

wrdata の CSV 形式: 各ベクタが (scale, value) の列ペア。値は列 3+2i（0 始まり）。
トランジェントデッキは `.control` 内で `save` により保持ベクタを限定している
（全ノード保存だと長時間ランでメモリが枯渇するため）。
