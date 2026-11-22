# 監査の模擬の元（第 24〜28 回）

デジタル制御の監査（`documentation/gf180_digital_control_audit_20261120.md`）の独立の監査人が、各自の写しで走らせた試験台と写しの作り方の元。監査の記録が引く模擬の結果を、後から読み直し、走らせ直せるように残す（第 26 回、C の付記：第 24、25 回の A と B の試験台はリポジトリになく、記録の数を確かめられなかった）。

- これらは `run_tests_r14.sh` と変異の実行器（`tb/mutate_top_r14.py`）の外にあり、試験の群には入らない。
- 監査人の写し（その回の版の git archive に、記録の外の入力を結んだもの）で走らせたままの形で残す。中の場所の指定（絶対の場所を含む）は、その写しを指す。走らせ直すときは、その回の版の写しを作り、場所を合わせる。
- 第 23 回以前の監査の模擬の元は残っていない（作業の場所の外で走らせ、Mac の更新で消えた）。

| 回 | 監査人 | ファイル | 記録の項目 | 内容 |
|---|---|---|---|---|
| 24 | A | `r24/A/tb_a24.sv`、`tb_a24d.sv` | 352、353（第 25.1 節） | 乱数のホストによる全ての命令と設定、要件から書いた照合（黄金の CIC、旗、端子の規則、AFE_RST の解除の条件）。範囲の上端の 1 段、RUN の待ちの起点 |
| 24 | B | `r24/B/tb_b24_pend.sv` | 356（第 25.2 節） | CMD_PENDING の待ちと STATUS の滑り（64 kHz、1 MHz） |
| 24 | B | `r24/B/tb_b24_copy.sv` | 357（第 25.2 節） | OFF_M_L のアクティブの写しの滑り（0xAA → 0xAB） |
| 24 | C | `r24/C/mutants.py`、`mkmut.py` | 358〜360（第 25.3 節） | 試みた RTL の写し（u1、u6 など）の書き換えと、写しの作り方 |
| 25 | A | `r25/A/tb_a25_stop.sv` | 364（第 26.1 節） | 規則 (b) に従うホストの APPLY_NR／APPLY のあとの次の命令の時刻（tick の周期にわたる位相） |
| 25 | A | `r25/A/tb_a25_m1024.sv` | 365（第 26.1 節） | 範囲 4、M 1023 からの M 1024 の書き込み |
| 25 | C | `r25/C/*.json`、`*.result`、`mkmut.py`、`runmut.sh` | 371、372（第 26.3 節） | 写し MA、MA2、BF、RUNNER の書き換えと 16 群の結果 |
| 25 | C | `r25/C/fsm_sweep*.py`、`regmap_sweep.py`、`regs_field_sweep.py`、`equiv.py`、`spi_cov.py` | 第 26.3 節 | 仕様の表とレジスタの表の 1 編集の掃き、同値の確かめ、SPI の網羅 |
| 26 | A | `r26/A/tb_a26_blank.sv`、`eeg_digital_top_tree.sv` | 376（第 27.1 節） | ADC_ZERO の試験のモードの SOFT_RESET と CHOP_BLANK（リセットの木の遅れの模型） |
| 26 | B | `r26/B/tb_b26_copy.sv` | 377（第 27.2 節） | 実行されなかった APPLY_NR（M 170 → 171）の確かめの読み出しの滑り |
| 26 | C | `r26/C/mkmut.py` | 379〜381（第 27.3 節） | 試みた RTL の写し（spi_tmrst、status_wr、shadow_mem、dbuf、caps8） |
| 26 | C | `r26/C/sweep_split.py`、`sweep_whole.py`、`sweep_regmap.py` | 第 27.3 節 | 分岐の分割と入れ替え、古典の 1 編集、レジスタの表の 1 編集の掃き |
| 27 | A | `r27/A/tb_a27_dbg.sv`、`tb_a27_dbg64.sv` | 385（第 28.1 節） | DBG_SEL 1〜3 の RAW のパッドの縁をチョッパの相で数える（128 kHz と 64 kHz） |
| 27 | B | `r27/B/tb_b27_shadow.sv`、`tb_b27_trec.sv` | 387（第 28.2 節） | 失った書き込み（OFF_M_L ＝ 0xDB、T_REC）と読み戻しの 1 回の滑り（AC DB 02、AC 31 07） |
| 27 | C | `r27/C/tb_probe_w1c.sv`、`tb_probe_ovf.sv` | 389、391（第 28.3 節） | W1C の門の滑りの端子の模擬（ERR の消え方）、SPI の不正な状態の値 9〜15 の注入 |
| 27 | C | `r27/C/hand_mutants.py`、`hand2_mutants.py`、`auto_mutants.py`、`auto_sample.py`、`genmut.py`、`mkmut.py` | 389〜391（第 28.3 節） | 試みた RTL の写し（W1C の門、派生した時計の 2 種、S_OVF ＝ 11、古典の 105 個）の書き換えと作り方 |
| 27 | C | `r27/C/clkcheck.py` | 390（第 28.3 節） | 全てのフリップフロップと記憶の書き込みの口の時計の確かめの試作（`check_outputs_registered.check_clocks` の元） |
| 27 | C | `r27/C/sweep_guards.py`、`sweep_data.py`、`sweep_regmap2.py` | 第 28.3 節 | 条件の置き換えの類、表の外のデータの編集、レジスタの表の新しい 1 編集の掃き |
| 28 | A | `r28/A/tb_a28_lock_top.sv`、`tb_a28_lock.sv` | 394（第 29.1 節） | 反映していない試験のシャドウを残して施錠したあとの APPLY_NR（CFG_ERR）と、手順 4 の手当ての APPLY（CHOP_EN 0 と ATP を旗なしに反映） |
| 28 | A | `r28/A/mon_afeclk.sv` | 第 29.1 節 | `eeg_afe_clk.spice` の論理（PH0、COE、CDA、CDB）の変化をチョッパの縁、tick、AFE_RST と照合する監視（tb_top_r14 とともに走らせる第 2 の最上位） |
| 28 | A | `r28/A/tb_a28_drdy.sv` | 396（第 29.1 節） | DRDY_N のパルスのモードの縁をチョッパの相で数える（両方の速さ） |
| 28 | B | `r28/B/tb_b28_rewrite.sv` | 397（第 29.2 節） | 手順 3 の文字どおりの書き直し（IF_CFG を CRC 無効の形で CRC 有効のチップへ）で FRAME_ERR がくり返す |
| 28 | B | `r28/B/tb_b28_faults.sv` | 第 29.2 節 | ホストの CRC の書き込み 21 種の MOSI の各ビットの反転、各パルスの取りこぼしと二重、CRC の読み出しの先頭の各ビットの反転 |
| 28 | C | `r28/C/tb_c28_w1c.sv` | 400（第 29.3 節） | DFLAG の W1C の書き戻しが ERR の RESET_FLAG と FRAME_ERR を消す共有の門の模擬（eeg_regs のみ） |
| 28 | C | `r28/C/sem_mutants.py`、`sem2_mutants.py`、`sem3_mutants.py`、`mkmut.py`、`spi_seeds.sh`、`fullrun.sh` | 400〜402、406（第 29.3 節） | 試みた RTL の写し（共有の W1C の門、データのみの SOFT_RESET、一方向の写し、IF_CFG のビット 2、armed の遅れ、サンプルの CRC、OVL）と tb_spi_r14 の種の比べ |
| 28 | C | `r28/C/gen_del.py`、`del_mutants.py`、`screen.py`、`batch_screen.py`、`sweep_queue.sh`、`hangcheck.sh` | 403、404（第 29.3 節） | 文の削除の類の生成と選別、tb_clkgen の止まりの確かめ |
| 28 | C | `r28/C/sweep_cellcopy.py` | 第 29.3 節 | 状態遷移表の欄の写しと同じ事象の分岐の置き換えの掃き |
