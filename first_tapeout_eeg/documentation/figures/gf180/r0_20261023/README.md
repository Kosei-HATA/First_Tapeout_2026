# r0：最初の組み立て（10/23）

- チップ：4c4441aa（組み立て、DRC 違反なし、コアの LVS 一致）と 8ade6689（アンテナの直し、穴埋めのあとの全 DRC 違反なし）。precheck は pre1（d93d3879）で通った。
- 図を入れたコミット：a6ea601b（Cin、C1、基準電圧のフィルタのレイアウト、10/23 朝）、8ade6689（配置図）。

| 図 | 中身 |
|---|---|
| `gf180_chip_placement_20261023.png` | チップ全体の配置（パッドリング、AFE、ADC、デジタル、バイアス、基準電圧、デカップリング） |
| `gf180_afe_placement_20261023.png`、`gf180_adc_placement_20261023.png` | AFE と ADC の中の配置 |
| `gf180_layout_eeg_cin.png`、`gf180_layout_eeg_c1.png` | Cin と C1 の MIM 配列 |
| `gf180_layout_eeg_ref.png` | 基準電圧のフィルタ eeg_ref |

説明の文書：`gf180_chip_assembly_20261023.md`、`gf180_layout_flow_20261023.md`。
