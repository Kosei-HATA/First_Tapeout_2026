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

同じマクロを監査の新しい試験台で回し直すときは、ランのフォルダへのリンク（例：`runs/r14f5_20261124_b41 -> r14f5_20261124`）をラン名に与え、結果のフォルダを分ける（`run_gl_r14.sh r14f5_20261124_b41 810a0bc4 prep` のあと `top`、`spi`、`seq`）。11/24〜25 の実行は `gl_r14f5_20261124`（e56bc9da の源。SDF の 3 コーナーを含む）、`gl_r14f5_20261124_b39`（3de8d03b）、`gl_r14f5_20261124_b41`（810a0bc4）、`gl_r14f5_20261124_b44`（ed9c0ebe）で、全て一致（`documentation/gf180_digital_verification_20261024.md` の第 8.6 節）。

## ADC のデジタル部との組（11/25）

r14 の試験台は、eeg_digital_top の入力 CODE を ADC のデジタル部（`rtl/eeg_adc_dig.sv`。マクロ f3、r12〜r14 のチップで同じ）の模型（e2 で変わる）で与えており、ADC のデジタル部そのものは r14 のどの試験にも入っていなかった。これを入れて、二つのブロックを組で確かめる。

| ファイル | 内容 |
|---|---|
| `sys_adc_r14.sv` | 試験台を変えずに、ADC のデジタル部の RTL を制御の出力（ADC_RST_N、TH_CAPTURE、DAC_LOAD、DWA_EN）につなぐモジュール。TH は、試験台がその e2 に与えるコード（`SYS_NEXT_CODE`）の温度計。確かめは三つ。(1) 制御が CODE を取る全ての縁（cic_en での CIC と過負荷の検出、RAW が有効なときのフレームのサイクル 31 での RAW。eeg_digital_top の CODE の使い道はこれで全て）で、ADC のデジタル部の CODE が試験台の CODE と等しいこと。等しければ、制御は ADC のデジタル部そのものとつないだときと同じに動き、試験台の全ての確かめが二つの組に成り立つ。(2) SEL1／SEL2 を参照の DWA（`rtl/tb/tb_top.sv` のもの）と比べる。DAC_LOAD の縁ごとに k ＝ 31 − そのフレームで取り込んだコード、DWA_EN はその縁の値。SEL は DAC_LOAD の縁でのみ変わる。CMP_STROBE の立ち上がりで popcount(SEL) ＝ 直前の更新の k。CMP_STROBE から SEL までの時間。DAC_CLK は更新の 1 MCLK 後に立ち上がり、幅 1 MCLK。(3) `SYS_GL` のとき、ADC のデジタル部のネットリスト（`layout/gds/eeg_adc_dig.nl.v`、7 トラックのセル）を RTL と並走させ（CODE、SEL1、SEL2）、その CODE を制御のネットリストに入れる（`gl_shadow_r14.sv` の `GL_CODE_SRC`。ループをゲートレベルで閉じる）。ADC のネットリストの制御の入力は、遅延なしでは RTL の制御の出力（並走で制御のネットリストの出力と毎回等しい。遅延なしのネットリスト同士は、クロックの木の段数の差で同じ時刻の中の順が競るため）、SDF では制御のネットリストの出力。TH は、遅延なしでは試験台の次のコードにすぐ従う。`SYS_TH_LAUNCH` を与えると、CMP_STROBE の立ち上がりのその時間あとに変わり、次の立ち上がりまで保つ（チップの量子化器の形。ADC のデジタル部の制約の入力の遅れは 15 ns）。`+sys_stop_us=<n>` で n µs で止める（短い試し）。|
| `sys_tb_top_r14.svh`、`sys_sys_sdf_r14.svh` | `sys_adc_r14.sv` の見る、試験台の次のコード（`tb_top_r14` は ovl_force のとき 31、ほかは `build/top_r14.codes` の cidx 番目。`gl_sys_sdf_r14` は next_code）。|
| `gl_sys_sdf_r14.sv` | 二つの組を遅延込みで回すための試験台。DWA_EN 1 での START から RUN、APPLY で DWA_EN 0（温度計の選択）、APPLY で 1 に戻す、RUN の中の SOFT_RESET（ADC_RST_N は RESET_N のみに従い、ADC のデジタル部は動き続ける）、RESET_N（ADC のデジタル部の非同期のリセットと再開）。それぞれで全てのコードを掃く（7 f ＋ 3 mod 32、k は 0〜31。ほかは CT ループの模型のコード列）。非同期の端子は MCLK の立ち下がりで変える（`gl_sdf_r14.sv` と同じ）。|
| `run_sys_r14.sh` | `<マクロのラン> <コミット> [rtl\|gl\|all]`。`tb_top_r14` に `sys_adc_r14.sv` を足し、RTL と、両方のネットリストの遅延なし（ループをゲートレベルで閉じる）で回す。結果は `runs/sys_<ラン>/sys_rtl.log`、`sys_gl.log`、`summary.txt`。|
| `run_sys_sdf_r14.sh` | `<マクロのラン> <コミット> [zero\|sdf\|all]`。`gl_sys_sdf_r14.sv` を、遅延なしと SDF の 3 コーナーで回す（r14 のランの final/sdf と、f3 の回し直しの final/sdf。チップのマクロの SDF）。結果は `runs/sys_<ラン>/syssdf_*.log`、`summary.txt`。|
| `run_old_sdf_th.sh`、`run_old_sdf_th_full.sh`、`run_old_sdf_e2e_th.sh` | 13 回目のチップの二つのマクロ（f2、f3）の遅延込みのゲートレベルで、11/20 に出た不一致（max ss、nom tt）の切り分け。r13 の試験台の、TH の時刻のみを変えた写しで回す（`rtl/` には書かない）。`run_old_sdf_th_full.sh` は `tb_e2e.sv` の TH の待ち 2.5 MCLK を 15 ns に縮め、同じ手続きの SEL の検査まで早めた（試験台の誤り 23,684 件、ゲートレベルは全サイクルで一致）。待ちを保った形で回し直すのが `run_old_sdf_e2e_th.sh`。|

11/25 の実行は次のとおり。いずれも ed9c0ebe の源で、ランへのリンクで写しを分けた。

- RTL：`runs/sys_r14f5_20261124_b44`
- 遅延なしのゲートレベル：`runs/sys_r14f5_20261124_b44g`
- gl_sys_sdf_r14：`runs/sys_r14f5_20261124_b44s`
- 切り分け：`runs/sys_diag_old_sdf_20261125`、`runs/sys_diag_old_sdf_full_20261125`、`runs/sys_diag_old_sdf_e2e_20261126`

RTL の最初の実行（11/25 20:50〜11/26 0:16）は、検査器の競りで 2 件を誤りと数えた。段 W で RESET_N が DAC_CLK のパルスを 7.248 ns で切ったのを、ADC のデジタル部のリセットの網が同じ時刻の中でまだ落ちる前に判定したもの。RESET_N と ADC_RST_N が高いときのみ判定するよう `sys_adc_r14.sv` を直し、RTL とゲートレベルを回し直した。最初の実行のログは `sys_rtl_checker_race_20261125.log` として残した。

結果は `documentation/gf180_digital_verification_20261024.md` の第 8.8 節と第 6 節。
