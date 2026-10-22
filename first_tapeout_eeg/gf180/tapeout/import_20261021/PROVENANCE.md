# 独立環境（Codex）からの取り込み（2026-10-22）

今回の rev は、これらを起点にこのリポジトリで設計を進める。ここにあるファイルは書き換えない。作業用の回路は `gf180/tapeout/` の別フォルダに派生させる。

取り込み元は `/Volumes/mukiebi/Codex/gf180_ishi_env_20261015/` 以下。SHA-256 は先頭 16 桁だけを記す。

| ファイル | 取り込み元 | SHA-256 | 中身 |
|---|---|---|---|
| afe_cpf210/candidate.spice | instrumented_ngspice_20261020/afe_m2_cpf210_input100_matched_20261021/cos-positive/ | 7587ad93cecde7e9 | AFE（CCIA、M2 コア、入力 TG m=64、出力 TG m=8、CMFB）の最新候補 |
| afe_cpf210/tb_circuit.spice | 同上の circuit.spice | 04c65fbbb6c13adf | 上の AFE のテストベンチ。Cin 636p、Cf 2p、Cpf 2.10p、負荷 9375 Ω、64 kHz チョッパ、バイアスは理想電圧源 |
| adc_gain10_loop/* | enob18_20261015/ct_candidate/adc_gain10_loop_20261020/results/positive_32/ | circuit 2356577b70376daa、otas ef588653685f740a、quantizer ae3031f602f5f967 | CT 2 次 5 bit ADC（利得 10 系）の単体ループ。量子化器と DWA は XSPICE のイベントモデル、DAC は理想 |
| afe_adc_cap2_direct/* | enob18_20261015/ct_candidate/afe_adc_cap2_direct_threshold1u_20261020/ | circuit 6373b955fe4e6563 | AFE と ADC の接続デッキ |
| acceptance_16p5_20261020.json | enob18_20261015/ | 4946bfba84e6c7aa | 16.5 bit 目標の受入基準 |

- 取り込み時の注意：デッキの `.include`／`.lib` は SSD 上の PDK コピーを指している。手元で回すときは `~/.ciel/ciel/gf180mcu/versions/f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7/gf180mcuD/libs.tech/ngspice` に置き換える。中身は同じ版。
- 10/22 時点で分かっている、このままでは使えない点：
  - DAC2 の値（106.7 MΩ × 62）。MOS 電流 DAC に置き換える（`documentation/gf180_large_resistors_20261022.md`）。
  - 量子化器モデルが X（不定）を保持すること。
  - バイアスが理想電圧源のため、数値的に弱いこと。
