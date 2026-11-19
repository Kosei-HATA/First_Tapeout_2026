# r14 のデジタル制御の面積の試行（11/19 夜）

r14 の RTL（`gf180/tapeout/rtl_r14/`、コミット 5fd5e022 の版。lint の整理 cc3652e6 は論理を変えない）を、r13 のマクロ（`../eeg_digital_top/config.yaml`）と同じ設定で LibreLane に通した試行。チップには入れていない。

## 回し方

- `run_trial_20261119.sh`（ターミナルのタブから。効率コア、2 本を並列）。PDK と nix shell は r13 のマクロとその 11/19 の回し直しと同じ。
- `trial_h700.yaml`：r13 の外形 440 × 700 µm（ランのタグ `t14_h700_20261119`）。`trial_h900.yaml`：440 × 900 µm（`t14_h900_20261119`）。試行の時点の名前は `config.yaml` と `config_h900.yaml`（決定のあと、`config.yaml` は r14 のマクロの設定とした）。
- 比較：`compare_trial.py`（r13 は `../eeg_digital_top/runs/f2_rerun_20261119`、チップのマクロと同一）。ランのフォルダは git の対象外。

## 結果

```
                                         r13 macro (f2 rerun)          r14, 440 x 700          r14, 440 x 900
                                                     finished stopped after 34-openro                finished
die area (um^2)                                       308,000                 308,000                 396,000
core area (um^2)                                      279,220                 279,220                 365,134
standard cells (um^2, no fill)                        211,739                 256,768                 268,563
  sequential                                           75,731                  96,049                  96,117
  combinational                                       100,706                 128,007                 129,043
  timing repair buffers                                11,211                  12,729                  13,282
  clock buffers and inverters                           6,254                       -                   7,282
  taps and endcaps                                      9,303                   9,303                  12,125
utilization (standard cells / core)                     75.8%                   92.0%                   73.6%
flip-flops                                                873                   1,097                   1,097
cells (no fill, taps, endcaps)                          5,432                   6,697                   6,844
setup WS max_ss_125C_3v00 (ns)                          1.096                       -                   0.520
setup WS nom_tt_025C_3v30 (ns)                         15.824                -226.222                  14.008
hold WS min_ff_n40C_3v60 (ns)                           0.191                       -                   0.194
setup violations (all corners)                              0                     740                       0
hold violations (all corners)                               0                     463                       0
max slew / cap / fanout violations                         63                   1,961                      94
routing DRC errors                                          0                       -                       0
antenna violating nets                                      0                       -                       0
routed wire length (um)                               262,700                       -                 346,614
Magic DRC errors                                            0                       -                       0
KLayout DRC errors                                          0                       -                       0
LVS errors                                                  0                       -                       0
```

- 440 × 700 µm：配置後の使用率 92.0 %。クロックツリーの挿入後の詳細配置が失敗（DPL-0036、22 時 46 分）。表の 440 × 700 の列は、失敗の直前の段（34、詳細配置）の値であり、タイミングはクロックツリーを含まない。
- 440 × 900 µm：80 段を完走（22 時 41 分〜23 時 07 分）。配線の DRC、Magic DRC、KLayout DRC は 0、LVS 一致、アンテナ 0。セットアップとホールドの違反は全コーナーで 0。最悪のセットアップ（ss・125 °C、＋0.520 ns）は、CIC のくし形の加算から丸めと飽和を経て出力のレジスタへ至る既存の経路。
- 最大容量の警告はクロックの根のバッファで、r13 と同じ。最大スルーは、新しいリセット rst_n（SOFT_RESET を含む。1 個のフリップフロップから全てのフリップフロップのリセットへ）の分配木（buf_1 72 個、clkbuf_2 19 個）で 4.76 ns（上限 3 ns）。r13 の最大は 3.07 ns。マクロの確定までに解消する。
- lint の段の警告（613 件）は、この試行の時点の RTL のもの。cc3652e6 で Verilator の -Wall（除外なし）で 0 に整理した。
- 決定：r14 のマクロの外形を 440 × 900 µm とする（11/19 夜、ユーザーの判断「Yes, 440 × 900」）。
