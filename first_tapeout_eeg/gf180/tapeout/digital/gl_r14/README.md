# r14 のマクロのゲートレベル（要件 VER-05、記録表 C4）

LibreLane の最終ネットリスト（`eeg_digital_top_r14/runs/<ラン>/final/nl/eeg_digital_top.nl.v`）を、RTL と並べて動かし（並走）、毎サイクルの全出力を比べる仕組み。r13 の `rtl/tb/gl_shadow.sv` と同じ考え方を、r14 の試験台と状態の注入に合わせた。

## ファイル

| ファイル | 内容 |
|---|---|
| `gl_shadow_r14.sv` | 並走のモジュール。試験台の RTL（`dut`）と同じ入力（MCLK、RESET_N、SCLK、CS_N、MOSI、CODE）をネットリストに入れ、50 本の出力と、NFR-05 の 2 つの状態のレジスタ（シーケンサの state、SPI の st）を 4 値で比べる（X も不一致）。遅延なしでは MCLK の立ち下がりの 1 ps あと、SDF ありでは立ち上がりの直前（そのエッジの能動領域、RTL のレジスタの更新の前）。試験台が RTL のレジスタを手で変える所（`tb_top_r14` の SPI の st の force、SEQ の deposit、soft_req の force、`gl_sdf_r14` の state と st の force）は、同じ変化をネットリストのフリップフロップの Q の網に入れる（次の立ち上がりのあとまで force し、フリップフロップはそこでその値から D を取る）。soft_req はネットリストに網として残らないので、レジスタのブロックの書き込みの口（reg_we 1、reg_addr 0x10、reg_wdata 0xA5。eeg_regs はこれを soft_reset としてのみ解く）を同じ時間だけ force する。|
| `gl_names.py` | ネットリストから、比べて force するレジスタのビットの網（RTL の名の候補から探し、緩衝器をさかのぼってフリップフロップの Q の網）を引き、`gl_names.svh` に書く。網の名（u_seq.state か seq_state か）と緩衝器の有無はランごとに変わる。|
| `gl_sdf_r14.sv` | SPI とシーケンサの代表的な試験と、状態のフリップフロップへの不正な値の注入（NFR-05）。SDF の 3 コーナーと遅延なしで回す。非同期の端子（RESET_N、SCLK、CS_N、MOSI）と CODE は MCLK の立ち下がりで変える（MCLK の周期を Icarus の丸める半周期 15.259 ns の 2 倍とし、SPI の時間を周期の整数倍に）。注入の値は MCLK の立ち上がりの 5 ns 後（`INJ`）に入れ、次の立ち上がりで解く。ネットリストのフリップフロップの Q の変わる頃（クロックの木の遅れ ss で 2〜4 ns と、クロックから出力までの遅れのあと）に当たる。11/24 の最初の SDF の実行は立ち上がりの 1 ps 後に入れており、フリップフロップがまだその縁を取る前で、入れた値から作った D を取った（3 コーナーとも、8 回の注入のうち 4 回で AFE_RST が 1 サイクル 0。試験台の作りもので、設計の誤りではない）。`GL_DBG_SKIP23`、`GL_DBG_VCD` はその調べのための定義で、記録の実行では使わない。|
| `run_gl_r14.sh` | 実行の台本（ターミナルのタブから）。`<マクロのラン> <RTL のコミット> [top\|spi\|seq\|all\|sdf\|prep]`。源は `git archive` でそのコミットの写しをランのフォルダに取り（監査のセッションが同じチェックアウトの `rtl_r14` と `build/` を編集するため）、試験台の生成物（`tb/gen_codes.py`、`tb/gen_reg_tests.py`）はその写しで作る。|

## 試験

- `top`：`tb_top_r14`（端子からの全段。サンプルを黄金の CIC と、シーケンサの全事象を fsm_spec と照合する検査器も回す）。
- `spi`：`tb_spi_r14`（乱数のフレーム 1,500 個と前置き。SPI の表と照合する検査器）。
- `seq`：`gl_sdf_r14.sv` を遅延なしで。
- `sdf`：`gl_sdf_r14.sv` を、ランの `final/sdf/` の max_ss_125C_3v00、nom_tt_025C_3v30、min_ff_n40C_3v60 で（3 本を同時に）。セルのモデルは、mux2 の選択と xor2／xnor2 の入力の「ifnone (posedge …)」の経路を素の経路に書き直した写し（Icarus がその形を落とし、遅延がつかなくなるため。r13 の `rtl/gl_sdf_prep.sh` と同じ変換）。Icarus は SDF の経路と配線の遅延を当てるが、タイミング検査（setup／hold）はしないので、その分は STA で見る。

結果は `eeg_digital_top_r14/runs/gl_<ラン>/`（git の対象外）の `gl_top.log`、`gl_spi.log`、`gl_seq_zero.log`、`gl_sdf_<コーナー>.log`、`summary.txt`。判定は、各試験台の検査と検査器が通り（PASS があって FAIL、ERROR、GL MISMATCH がない）、並走の結果の行が「PASS: gate level」であること。

同じマクロを監査の新しい試験台で回し直すときは、ランのフォルダへのリンク（例：`runs/r14f5_20261124_b41 -> r14f5_20261124`）をラン名に与え、結果のフォルダを分ける（`run_gl_r14.sh r14f5_20261124_b41 810a0bc4 prep` のあと `top`、`spi`、`seq`）。11/24〜25 の実行は `gl_r14f5_20261124`（e56bc9da の源。SDF の 3 コーナーを含む）、`gl_r14f5_20261124_b39`（3de8d03b）、`gl_r14f5_20261124_b41`（810a0bc4）で、全て一致（`documentation/gf180_digital_verification_20261024.md` の第 8.6 節）。
