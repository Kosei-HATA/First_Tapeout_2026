# RIN と DAC1 を ppolyf_u に替える案（11/12）

10 回目のチップ（r10）の ADC のポリ抵抗のフリッカ雑音（`documentation/gf180_realistic_eval_20261028.md`、r10 の図 33）への対策の案を調べた図。設計はまだ変えていない（ネットリストは `gf180/tapeout/sim/dac1/runs/ppolyf_u_study/` に写して直した）。

| 図 | 中身 | 作ったスクリプト |
|---|---|---|
| `gf180_rdac_ppolyf_u_20261112.png` | 1 単位（300 kΩ）を幅 0.8 µm の ppolyf_u 2 本にしたときの、ADC の帯への収まり（10 回目の adc_top の配置に重ねた）、雑音、抵抗値のコーナーと温度、DAC1 の確認の比べ | `gf180/tapeout/sim/dac1/ppolyf_u_study.py`（unit、plan、dac1、fig） |

ブロックの位置は `gf180/tapeout/layout/gds/adc_top.gds`（r10、11/9）から読んだ。説明は `documentation/gf180_realistic_eval_20261028.md` の「RIN と DAC1 を ppolyf_u に替える案」。
