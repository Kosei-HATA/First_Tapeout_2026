# r1：D6 の直しのあと（10/24）

- チップ：493f9753（D6 の直しを入れた 1 回目の組み直し、DRC 違反なし、LVS 一致）。precheck は pre_20261024（274e2508）で通った。
- 図を入れたコミット：310ec54b（ADC の直し）、e4536b67（AFE の直し）。

| 図 | 中身 |
|---|---|
| `gf180_layout_dac1_quad_20261023.png` | DAC1 の素子を XP–XN の軸で鏡像対称に描き直した形 |
| `gf180_layout_qcmp_inputs_20261023.png` | 量子化器の入力と CLK を手で引いた形 |
| `gf180_layout_afe_w_20261024.png` | AFE の入力の W（チョッパから Cin の下の板）の面 |

説明の文書：`gf180_adc_d6_fix_20261023.md`、`gf180_afe_d6_fix_20261024.md`。
