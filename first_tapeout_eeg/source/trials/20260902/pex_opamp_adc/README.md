# pex_opamp_adc: PEX（寄生成分抽出）検証トライアル

ALIGN生成レイアウト（`opamp_adc.gds`）の寄生容量をMagic `.ext` データベースから
抽出し、フラットPEXネットリストを生成して理想回路と特性比較したトライアル。
元の作業場所: `~/OSBCIChip`（xschem/ および lvs_work/）。

## 構成

- `xschem/`
  - `1samp_opamp_adc_pex.sch` — PEXテストベンチ（理想回路と同一帰還: R1=99 kΩ / R2=1 kΩ）
  - `opamp_adc_pex.spice` — PEXフラットネットリスト（素子＋寄生容量、L=0.15 µm）
  - `opamp_adc_pex_v1_l015.spice` — PEXネットリスト v1
  - `1samp_opamp_adc.sch` / `1samp_opamp_adc_ideal.spice` — 理想回路（L=0.5 µm）対照
  - `1samp_opamp_adc_pex_vs_ideal.png` — 理想 vs PEX の比較プロット
- `scripts/`
  - `ext2pex.py` — Magic `.extDB`（基板容量・結合容量）から階層名を再帰解決し
    フラットPEX Spiceネットリストを自動生成
  - `run_pex_compare.py` — 理想/PEX 両ネットリストのAC・過渡比較実行
  - `extract_opamp_adc.tcl` — Magic 抽出スクリプト

## 主な結果（詳細は wr_2026-0801-0806.md 参照）

| 評価項目 | 理想回路 (L=0.5 µm) | PEX実レイアウト (L=0.15 µm) |
| :--- | :--- | :--- |
| 開ループ利得 | ~56 dB | ~32 dB |
| 閉ループ利得 | 38.7 dB | 28.7 dB |
| 1bit ADC出力 | 反転（正常動作） | 1.8 V に張り付き（不動作） |

不動作の直接原因は実レイアウト素子のチャネル長 L=0.15 µm（最小長）による
オペアンプ利得不足。対策: 長チャネル素子（L ≥ 0.5 µm）への変更、
コンパレータ閾値・ゲイン要求仕様の再検討。

※ `.raw`（ngspiceバイナリ波形、`1samp_opamp_adc_pex.raw` は約21 MB）も同梱。
再現は `run_pex_compare.py` を実行。
