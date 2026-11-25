# 監査の模擬の元（第 24〜44 回）

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
| 29 | A | `r29/A/tb_a29_reset.sv` | 408（第 30.1 節） | RUN（64 kHz、CHOP1 16 kHz、BLANK 3）の途中の RESET_N と SOFT_RESET のあとの CHOP の半周期、CHOP1、CHOP_BLANK の幅（レベルのモードの DRDY_N の立ち上がりの相は監査人の写しで別に測った） |
| 29 | B | `r29/B/tb_b29_remedy.sv` | 411（第 30.2 節） | 反映していない試験のシャドウを残して施錠したあとの手順 4 の比べと直しの書き込み（ADDR_ERR が 3 回） |
| 29 | B | `r29/B/tb_b29_lockrw.sv` | 411（第 30.2 節） | 戻して施錠したあとの BOOST_TRIM の CRC_ERR と、試験のシャドウを含む文字どおりの書き直し（ERR 0x08 が 3 回） |
| 29 | B | `r29/B/tb_b29_lockmiss.sv` | 411（第 30.2 節） | RUN の施錠の書き込みの 1 回の SCLK の取りこぼし（16 通り）で鍵が開いたまま全ての確かめが通る |
| 29 | B | `r29/B/tb_b29_guard.sv` | 第 30.2 節 | 未処理の APPLY を取る tick をまたぐ守られたシャドウへの書き込み（1/4 MCLK ずつ、64 kHz） |
| 29 | C | `r29/C/tb_c29_offmh.sv`、`mon_lock.sv`、`lockcov.py` | 413（第 30.3 節） | OFF_M_H を施錠する写しの模擬と、全ての確定の施錠の状態の記録とその集計 |
| 29 | C | `r29/C/tb_c29_dacclk.sv` | 414（第 30.3 節） | DAC_CLK のリセット値を 1 とする写しの模擬（リセットの間と MCLK を止めたとき） |
| 29 | C | `r29/C/muts1.py`、`muts2.py`、`muts3.py`、`mkmut.py` | 413、414（第 30.3 節） | 試みた RTL の写し（OFF_M_H の施錠、DAC_CLK のリセット値、過負荷の 5 ビットの計数、BLANK のバイト全体の比べ）と写しの作り方 |
| 29 | C | `r29/C/gen_classic.py`、`classic_top.py`、`classic_unit.py`、`cscreen.py` | 第 30.3 節 | 古典の 1 点の写しの生成（それまでの掃きが覆わないファイルと行）と選別 |
| 29 | C | `r29/C/sweep_regmove.py`、`sweep_replace.py`、`sweep_cellguard.py`、`run_sweeps2.sh` | 415（第 30.3 節） | レジスタの表の欄の移動、状態遷移表の動作の置き換えと欄の条件の書き換えの掃き |
| 30 | A | `r30/A/tb_a30_restore.sv` | 417（第 31.1 節） | 反映した試験の設定（TEST_CTRL ＝ 0x02）を括弧で戻したあとも写しと CHOP_EN が試験の設定のまま |
| 30 | A | `r30/A/tb_a30_bracket.sv` | 418（第 31.1 節） | 括弧で値を設定し施錠の書き込みを失ったときの (5) の 0x00 による上書き |
| 30 | B | `r30/B/tb_b30_bracket.sv` | 419（第 31.2 節） | 括弧の 1 回の故障（CRC_ERR、施錠のパルスの取りこぼし、括弧の間のサンプルの読み直し）と ERR の読み続け |
| 30 | B | `r30/B/alias_crcoff.py` | 420（第 31.2 節） | CRC 無効の書き込みの先頭の 1 ビットの別名（eeg_regs の復号の模型） |
| 30 | C | `r30/C/tb_c30_race.sv`、`tb_c30_race_nr.sv` | 422（第 31.3 節） | 未処理の APPLY（IDLE）と APPLY_NR（RUN）を取る tick をまたぐ OFF_M_L の書き込みの掃き |
| 30 | C | `r30/C/tb_regs_fix.sv`、`mon_c30_apply.sv` | 422（第 31.3 節） | 確認のサイクルに反映を入れた tb_regs の試作と、反映のサイクルの確定を数える監視 |
| 30 | C | `r30/C/tb_c30_keydata.sv` | 423（第 31.3 節） | 施錠の間に施錠しないレジスタへ 0x3C を書いたあとの TEST_MUX の書き込み |
| 30 | C | `r30/C/muts_b1.py`、`muts_b2.py`、`mkcopy.py` | 422、423（第 31.3 節） | 試みた RTL の写し（反映が次の状態を写す、反映が書き込みを捨てる、データのみの解錠）と写しの作り方 |
| 30 | C | `r30/C/sweep_regdata.py` | 第 31.3 節 | REGS の外の仕様のデータの 1 編集の掃き |
| 31 | A | `r31/A/tb_a31_crcoff.sv` | 424（第 32.1 節） | CRC 無効の運用の書き込みの別名（ALERT_MASK_D → ALERT_MASK、T_ELEC → IF_CFG、TEST_KEY）と、第 30 回の読み戻しの手当てが見ないこと |
| 31 | A | `r31/A/tb_a31_inv.sv`、`mut_seq_rec.sv`、`mut_top_chg.sv` | 第 32.1 節 | 乱数のホストと第 4.10 節から書いた不変条件の監視（7 種 × 400 ms）と、その感度を確かめた写し |
| 31 | B | `r31/B/tb_b31_crcoff.sv`、`alias_all.py` | 426（第 32.2 節） | CRC 無効の運用の黙った別名の全ての列挙と模擬（ALERT_MASK_D、IF_CFG、COMMAND） |
| 31 | B | `r31/B/tb_b31_bounce.sv`、`tb_b31_merge.sv`、`bounce_cmp.py`、`merge_cmp.py`、`slip_e2.py`、`slip_e3.py` | 427（第 32.2 節） | SCLK の 1 回の故障の 4 種（跳ねと融合を加えた）の RTL と模型の比べ |
| 31 | B | `r31/B/smp_flip.py` | 第 32.2 節 | サンプルの先頭 0xC0 の 1 ビットの化けとホストのサンプルの CRC |
| 31 | C | `r31/C/tb_c31_judge.sv` | 428（第 32.3 節） | 反映の tick の判断と、確認のサイクルの書き込み（S1：判じるシャドウが範囲外、S2：競う値が範囲外） |
| 31 | C | `r31/C/fsm_sweep.py`、`regs_sweep.py`、`apply_edit.py`、`mkmut.sh`、`fastrun.sh` | 428〜432（第 32.3 節） | 状態遷移表とレジスタの表の 1 編集の掃き、写しの作り方と速い走らせ方 |
| 32 | A | `r32/A/tb_a32_path.sv` | 433（第 33.1 節） | CRC 有効で STATE を 10 µs ごとに読み、START と手順 7 の探索の APPLY のあとに通る状態の列と長さ（T_ELEC 0 と 2 ms） |
| 32 | A | `r32/A/tb_a32_rate.sv`、`tb_a32_rate4.sv` | 434（第 33.1 節） | RUN で CHOP_FAST を交互に変える APPLY の PRE と AFE_RST の長さ、速さの切り替えの時刻、命令の確定から tick まで（T_PRE 3。`tb_a32_rate4.sv` は修正のあとの T_PRE 4 の確かめ） |
| 32 | B | `r32/B/tb_b32_probe.sv`、`probe_slip.py` | 437（第 33.2 節） | モードの判定 [0xD5、0、0] の SCLK の 1 回の故障の 4 種（RTL と模型）：CRC 有効のチップが CRC 無効と読める組と、逆の向き |
| 32 | B | `r32/B/smp_slip_rate.py`、`dgrep.py` | 第 33.2 節 | 滑ったサンプルの写しが CRC を通る割合、文書の番地と数の探し |
| 32 | C | `r32/C/tb_c32_fillovl.sv`、`mkmut.py` | 438（第 33.3 節） | FILL を終える出力の過負荷（清い RTL と、out_valid を過負荷で落とす写し）と写しの作り方 |
| 32 | C | `r32/C/fsm_sweep.py`、`regmap_sweep2.py` | 439、440（第 33.3 節） | 状態遷移表と優先順位の 1 編集の掃きと同値の確かめ、レジスタの表の 1 欄の編集の掃き |
| 33 | A | `r33/A/tb_a33_illegal.sv` | 442（第 34.1 節） | START のあとの WARMUP（`+pulse` で RUN の APPLY のあとの PULSE）に不正な状態の値 9 を 1 MCLK 置き、CRC 有効の STATE、STATUS、ERR の読み出しを続ける |
| 33 | A | `r33/A/tb_a33_dlc.sv` | 443（第 34.1 節） | DAC_LOAD_CYCLE 2、22、23、24 で AFE_RST の解除の縁と DAC の縁の時刻 |
| 33 | B | `r33/B/tb_b33_probe_mosi.sv` | 444（第 34.2 節） | モードの判定のヘッダの 8 ビットの各々の化け（CRC 有効と無効、既定値、T_REC 0x30、T_RST 0x22 と 0x25） |
| 33 | B | `r33/B/tb_b33_flushread.sv` | 445（第 34.2 節） | FLUSH と RUN の APPLY の直後に始めるサンプルの読み出し（tick から 250 ns ずつ）：取り出されない命令の前の語 |
| 33 | C | `r33/C/tb_c33_fillclr.sv` | 446（第 34.3 節） | FILL の中の APPLY_NR（T_ELEC 0）と APPLY の掃き：ALIGN のクリアと最初の格納 |
| 33 | C | `r33/C/tb_c33_twarm.sv` | 447（第 34.3 節） | T_WARM 128、200、255 の読み戻しとシーケンサの読み込み |
| 33 | C | `r33/C/fsm_sweep2.py`、`fsm_sweep_sig.py`、`regmap_const_sweep.py`、`fastrun.sh` | 第 34.3 節 | 状態遷移表と TIMING の広げた 1 編集の掃き、regmap の定数と番地の移動の掃き、写しの速い走らせ方（`fsm_sweep2.py` は隣の `fsm_sweep_sig.py` を読む。第 36 回、C で残し、相対の場所に直した） |
| 34 | A | `r34/A/tb_a34_c1blank.sv` | 450（第 35.1 節） | r14 の eeg_clkgen と eeg_chop1：128 kHz と 64 kHz、CHOP1 の速さ 1〜5 で、CHOP1 の縁と CHOP_OUT の立ち上がり、CHOP_BLANK の立ち下がりの距離 |
| 34 | A | `r34/A/seq_ref.py` | 第 35.1 節 | SEQ-01〜16 と 5.0 から独立に書いたシーケンサの模型と `fsm_spec.seq_tick` の全ての組の照合 |
| 34 | B | `r34/B/tb_b34_csbreak.sv`、`a34B_csbreak2.py`、`a34B_csbreak_probe.py` | 451（第 35.2 節） | CRC 付きの読み出しをパルス 2〜23 の前で CS_N の跳ねで切る RTL の試験台と、ホストの見方の模型 |
| 34 | B | `r34/B/tb_b34_offprobe.sv`、`a34B_probeoff2.py` | 452（第 35.2 節） | CRC 無効の到達しうる値（T_ELEC 1、3、IF_CFG 0x02）のもとでのモードの判定の 1 回の故障 |
| 34 | C | `r34/C/tb_c34_status.sv` | 455（第 35.3 節） | 格納自らのサイクルの始まりの縁で FRAME_ERR を立てたときの、格納したサンプルの状態のバイト |
| 34 | C | `r34/C/orpin.py`、`selfvar.py`、`focus.py` | 456（第 35.3 節） | 検査の Or の項の留め（自己試験の各発火で真の項）と、項を除いた変種の自己試験 |
| 34 | C | `r34/C/muts.py`、`mk.py`、`fastrun.sh`、`runmut.sh` | 第 35.3 節 | RTL の写し（status_q、aerr_burst、guard_apply、m190）の作り方と速い走らせ方 |
| 35 | A | `r35/A/tb_a35_prestop.sv` | 第 36.1 節 | チョッパの速さを切り替える APPLY の PRE の中で取った STOP：OFM の変化から AFE_RST の立ち上がりまで（T_PRE 3、両方の向き） |
| 35 | B | `r35/B/tb_b35_csshort.sv`、`tb_b35_csshort2.sv` | 462（第 36.2 節） | CRC 有効の読み出しの Low の相の 1 回の CS_N の High（幅 0.25〜2.0 MCLK、8 通りの位相）でフレームが分かれるか |
| 35 | B | `r35/B/tb_b35_csglitch.sv` | 462（第 36.2 節） | CRC 付きの読み出しの 1〜23 ビットのあとの 3 MCLK の High：一つ目の部分の FRAME_ERR |
| 35 | C | `r35/C/tb_c35_flags.sv` | 464、465（第 36.3 節） | 受け付けた START と APPLY のあとの ERR、DFLAG、STATUS（端子のみから）、空の語の写しのサイクルの始まりの縁の FRAME_ERR |
| 35 | C | `r35/C/tb_c35_hdr.sv`、`tb_c35_slack.sv` | 465（第 36.3 節） | 先頭の STATUS の写しのサイクルの始まりの縁の FRAME_ERR、誤りの確定から次の先頭の写しまでの縁の数 |
| 35 | C | `r35/C/muts.py`、`probe_off_exp.py`、`fsm_sweep3.py`、`fsm_sweep_sig.py` | 第 36.3 節 | RTL の写し（rflag_apply、dflag_apply、empty_q、status_hdr_q）と試験台の走査の写し、PROBE_OFF_REACHABLE の空と欠けの実験、状態遷移表の新しい類の 1 編集の掃き（第 36.3 節の 45,368 個は類を名指して `python fsm_sweep3.py <rtl/spec の場所> <出力> ins,copy,comp,dup,prio,sb`。類を省くと SEQ の表を飛ばし 20,782 個。`fsm_sweep_sig.py` は第 36 回、C で残した） |
| 36 | A | `r36/A/tb_a36_release.sv`、`ver07_51k_windows.py`、`ver07_51k_zero.py` | 469（第 37.1 節） | RUN の APPLY の解除から ALIGN のクリアと最初の格納までの時刻（両方の速さ、出力の間隔の 16 の位置）、その sinc³ の窓を 51 kΩ ∥ 47 nF のデッキの OUTP − OUTN に当てた読み、平均の 0 の横切り |
| 36 | A | `r36/A/tb_a36_softsweep.sv` | 第 37.1 節 | SOFT_RESET を超周期の 512 の位相の全てに 2 回（64 kHz・範囲 1・CHOP1 16 kHz と、範囲 0・BLANK 1）：CHOP_OUT の縁とブランキング、パルスと半周期の幅、端子のリセット値 |
| 36 | B | `r36/B/tb_b36_id.sv` | 471（第 37.2 節） | 手順 2 の CRC 無効の ID の読み [80 00 00] と、その bit 6 の化け [C0 00 00]（空の語を旗なしで返す） |
| 36 | B | `r36/B/tb_b36_crcoff.sv`、`crcoff.txt`（実行の記録。`*.log` は git の対象外なので改名） | 第 37.2 節 | 手順の CRC 無効のフレームの 1 回の故障（MOSI の化け、SCLK の欠けと重複）504 通り：CRC 無効のまま残るチップの値（PROBE_OFF_REACHABLE に等しい） |
| 36 | C | `r36/C/tb_c36_trec.sv`、`tb_c36_dflag.sv`、`tb_c36_nr.sv`、`tb_c36_aerr.sv` | 473〜476（第 37.3 節） | WARMUP の T_REC と PRE の T_RST の書き込み、DFLAG の立った間の START、IDLE の APPLY_NR の設定、未定義の 0x7F からの連続読み出しの ADDR_ERR の時刻 |
| 36 | C | `r36/C/muts.py`、`mkmut.py`、`fastrun.sh`、`regmap_sweep2.py` | 第 37.3 節 | RTL の写し（timers_at_apply、dflag_at_start、nr_dac_only、aerr_at_end）の作り方と速い走らせ方、regmap.REGS のフィールドの編集の掃き（478 の落ちを見つけた） |
| 37 | A | `r37/A/tb_a37_relbound.sv`、`tb_a37_relbound.txt` | 480（第 38.1 節） | 解除からクリアまでの時刻の上下限（RUN の APPLY を 1024 を法として 633／641（128 kHz）、611／627（64 kHz）のフレームで） |
| 37 | A | `r37/A/tb_a37_recexp.sv`、`tb_a37_recexp.txt` | 第 38.1 節 | RECOVER の満了のちょうどの tick で取る未処理の 1 段の APPLY_NR（T_ELEC 0、各速さで 16 の位置） |
| 37 | B | `r37/B/tb_b37_idver.sv`、`b37_models.py` | 482（第 38.2 節） | 手順 3 の ID と VERSION の CRC 付きの読みの 1 個の故障 624 回（ホストとチップの SCLK を別に）、CRC 無効のチップと滑りの数の模型 |
| 37 | C | `r37/C/tb_c37_apply.sv`、`mon_cov.sv`、`cov_summary.py` | 484、485（第 38.3 節） | IDLE の APPLY_NR の反映の模擬、全ての反映でシャドウとアクティブの異なる欄を記録する網羅の監視とその集計 |
| 37 | C | `r37/C/muts.py`、`mkmut.py`、`screen.sh`、`fsm_sweep_c37.py` | 第 38.3 節 | RTL の写し（m1、m2、m3、m5：変異 m202〜m205）の作り方と群の走らせ方、状態遷移表の指示の類の 1 編集の掃き |
| 38 | A | `r38/A/a38_track.py` | 489（第 39.1 節） | 固定の閾値 ±54 mV での追従の行き来（R_e ごとの落ち着かないオフセットの割合） |
| 38 | A | `r38/A/tb_a38_chopstop.sv` | 490（第 39.1 節） | CHOP_STOP の試験のモードを相 B の SOFT_RESET と RESET_N が終わらせるときの PH0 と COE の変化（対照 2 通り） |
| 38 | B | `r38/B/tb_b38_step5ovr.sv`、`tb_b38_step5ovr_f4.sv`、`step5ovr*_w*.txt` | 491（第 39.2 節） | 2 個のチップの手順 5 (i)：比べるチップを 3〜12 区間読まずにおいたときの判定（8 段と 4 段） |
| 38 | C | `r38/C/tb_c38_regs.sv` | 493、494（第 39.3 節） | eeg_regs の確認のサイクルの STATUS と、DFLAG の W1C の確定のサイクルの dflag_overrun |
| 38 | C | `r38/C/mon_c38.sv`、`c38_ack_summary.py`、`run_cov.sh`、`c38_ack_copies.txt`、`cov_summary.txt` | 493、496（第 39.3 節） | 確認のサイクルの先頭の写しと、状態ごとの反映の欄の網羅の監視とその集計 |
| 38 | C | `r38/C/muts.py`、`fsm_sweep_c38.py` | 第 39.3 節 | RTL の写し（m1、m15：変異 m206、m207）、状態遷移表の新しい類の 1 編集の掃き |
| 39 | A | `r39/A/tb_a39_rand.sv`、`run_s1_short.txt`、`run_s2.txt`〜`run_s5.txt` | 第 40.1 節 | 要件から書いた不変条件（P1〜P4、S1）の乱数のホストの模擬と、4 種の乱数 × 600 ms の記録 |
| 39 | A | `r39/A/a39_muts.diff`、`a39_mut_runs.txt` | 第 40.1 節 | 模擬の自己試験の RTL の写し 3 種（CHANGED の個数、サンプルの OVL の区間、OFM の端子の時刻）とその記録 |
| 39 | C | `r39/C/tb_c39_status.sv`、`st_clean.txt`、`st_mr1.txt`、`st_mr5.txt` | 500（第 40.3 節） | RUN の STOP を取る tick の e25 をまたぐ STATUS の読み出しの掃き（READY と AFE_RST、清い RTL と写し MR1、MR5） |
| 39 | C | `r39/C/tb_c39_emptyovl.sv`、`eo_clean.txt`、`eo_mr6.txt` | 500（第 40.3 節） | OVL_NOW の立ち上がりをまたぐ空の FIFO のサンプルの読み出しの掃き（清い RTL と写し MR6） |
| 39 | C | `r39/C/muts.py`、`mkmut.sh`、`apply_mut.py`、`run_sweeps.sh`、`sweep_c37.txt`、`sweep_c38.txt`、`sweep_regmap.txt` | 第 40.3 節 | RTL の写し（MR1、MR3〜MR7：変異 m208〜m212。MR7 は等価）の作り方、状態遷移表と regmap.REGS の 1 編集の掃きとその結果 |
| 40 | A | `r40/A/a40_track_meas.py`、`a40_track_meas.txt` | 503（第 41.1 節） | 抽出のビットの重みからの局所の 1 段と、測った 1 段による閾値での行き来の割合 |
| 40 | A | `r40/A/a40_ovl_onset_eld.py`、`a40_ovl_onset_eld.txt`、`a40_overrange.py`、`a40_overrange.txt` | 504、505（第 41.1 節） | 行動模型（ループの遅れ 3／32）の過負荷の始まりと、範囲を越える DC の走り去り |
| 40 | A | `r40/A/a40_exitcode2.sh` | 506（第 41.1 節） | pipefail のもとの `! printf | grep -q FAIL` の終了コード |
| 40 | B | `r40/B/tb_b40_readout.sv`、`tb_b40_readout.txt`、`tb_b40_readout2.txt` | 508、509（第 41.2 節） | 7 回と 9 回の出力の間読まなかったチップの読み切りの語と DFLAG、遅らせたチップの DRDY_N の縁 |
| 40 | B | `r40/B/b40_step5_budget.py` | 509（第 41.2 節） | 手順 5 を行えるチップの数の見積もり |
| 40 | B | `r40/B/b40_slip_empty.py`、`b40_slip_false_empty.py`、`b40_slip_valid_sanity.py`、`tb_spi_r14_s40.txt`、`tb_spi_r14_f4.txt` | 第 41.2 節 | 8 バイトのサンプルのフレームの SCLK の故障の模型と、新しい系列の tb_spi_r14 の記録 |
| 40 | C | `r40/C/tb_c40_first.sv`、`run_probe.sh`、`clean.txt`、`fill_ovr.txt`、`smp_err_norf.txt`、`smp_err_nomaskd.txt` | 511、512（第 41.3 節） | オーバーランのあとの最初のサンプルと、RESET_FLAG や ALERT_MASK_D 0x00 のもとのサンプルの ERR（清い RTL と写し 3 種） |
| 40 | C | `r40/C/muts.py`、`mkmut.sh`、`apply_mut.py`、`fillstore.py`、`run_mut_fill_ovr.txt`、`run_mut_smp_err_norf.txt`、`run_mut_smp_err_nomaskd.txt` | 511、512（第 41.3 節） | RTL の写し（変異 m213〜m215）の作り方と 15 群の記録 |
| 40 | C | `r40/C/out_c37.txt`、`out_c38.txt`、`all_pass_now.txt`、`regmap_recheck.py`、`out_regmap_recheck.txt` | 513（第 41.3 節） | 状態遷移表と regmap.REGS の 1 編集の掃きの結果（SEQ_PRIORITY の移動） |
| 41 | A | `r41/A/tb_a41_cicwin.sv`、`cicwin.txt` | 第 42.1 節 | eeg_cic3 のみの全精度のくし形の値での単位入力の届く出力とクリア |
| 41 | A | `r41/A/tb_a41_branches.sv`、`branches.txt` | 第 42.1 節 | tb_top_r14 の記録が取らない分岐 16 個（状態、端子、ERR） |
| 41 | A | `r41/A/rand_4101.txt`〜`rand_4103.txt`、`rand64_4164.txt`、`tb_a41_rand64_from_a39.diff` | 第 42.1 節 | 第 39 回の不変条件の試験台（`r39/A/tb_a39_rand.sv`）の新しい乱数と 64 kHz のみの形の記録、その差分 |
| 41 | B | `r41/B/tb_b41_readout.sv`、`rd8.txt`、`rd4.txt` | 516（第 42.2 節） | パルスとレベルのモードの k 回の出力のあとの読み切りのフレームの数と時間（8 段と 4 段） |
| 41 | B | `r41/B/b41_slip_any.py` | 第 42.2 節 | どの値も受ける滑りの模型の確かめ |
| 41 | C | `r41/C/tb_c41_rdinstant.sv`、`rdi_clean.txt`、`rdi_rd_data_late.txt` | 520（第 42.3 節） | START と STOP の tick をまたぐ STATE の読みのデータのバイトの写しの瞬間（清い RTL と写し） |
| 41 | C | `r41/C/muts.py`、`mut_rd_data_late.txt`、`mut_te_latched.txt` | 520（第 42.3 節） | RTL の写し（rd_data_late：変異 m216、te_latched：D3／D4 が捕らえる）と 16 群の記録 |
| 41 | C | `r41/C/busy_sweep.py`、`busy_all3.py`、`sweep_busy.txt`、`timing_pass.txt`、`sweep_c37.txt`、`sweep_c38.txt`、`sweep_regmap.txt` | 521（第 42.3 節） | TIMING の使用中のサイクルとタイマの編集の掃き、状態遷移表と regmap.REGS の掃きの結果 |
| 42 | A | `r42/A/a42_win_check.py` | 第 43.1 節 | CIC の算術から書いた窓、CHANGED、OVL の独立の模型（全ての tick の位置、128／64 kHz、T_ELEC 0、1、2、5） |
| 42 | A | `r42/A/a42_m1_ofs_range0.diff`、`a42_m2_ofm_range0.diff`、`a42_m1_top.txt`、`a42_m2_top.txt`、`a42_run_top_only.sh`、`run_tests_baseline.txt` | 第 43.1 節 | 範囲 0 の端子の規則の写し 2 種と tb_top_r14 の記録（段 N と端子の監視が捕らえる） |
| 42 | B | `r42/B/tb_b42_lvlwin.sv`、`tb_b42_lvlwin.txt`、`tb_b42_lvlwin2.sv`、`tb_b42_lvlwin2.txt` | 522（第 43.2 節） | 格納のまわりの FIFO_LEVEL の読み込みの縁（窓の方法の境） |
| 42 | B | `r42/B/tb_b42_status_afe.sv`、`tb_b42_status_afe.txt`、`b42_status_pairs.py`、`b42_status_which.py` | 523（第 43.2 節） | 過負荷の間の RUN の STATUS の滑りによる偽りの AFE_RST ＝ 1 |
| 42 | B | `r42/B/b42_slip_any.py`、`b42_slip_masked.py`、`b42_crcoff_after_reset.py`、`crc_off_probe.py`、`crcclaims.py`、`smp_hdr_flip.py`、`tb_spi_s42.txt` | 第 43.2 節 | 滑りの模型、リセットされたチップの CRC の形の読み、CRC の定数、新しい系列の tb_spi_r14 |
| 42 | C | `r42/C/tb_c42_stread.sv`、`stread_clean.txt`、`stread_err_rd_q.txt`、`stread_st_hdrcopy.txt` | 524（第 43.3 節） | STATUS と ERR の読みのデータのバイトの写しの瞬間（清い RTL と写し 2 種） |
| 42 | C | `r42/C/tb_c42_telec.sv`、`telec_clean.txt`、`telec_te_seq_latched.txt` | 525（第 43.3 節） | WARMUP で書いた T_ELEC の RECOVER の満了での扱い（清い RTL と写し） |
| 42 | C | `r42/C/muts.py`、`mut_err_rd_q.txt`、`mut_te_seq_latched.txt`、`mut_st_hdrcopy.txt`、`baseline_run.txt` | 524、525（第 43.3 節） | RTL の写しの定義と 16 群の記録 |
| 42 | C | `r42/C/th_swap_selftest.py`、`busy_sweep.py`、`sweep_timing.txt`、`fsm_sweep_c42.py`、`sweep_c42.txt`、`sweep_c37.txt`、`sweep_c38.txt`、`regmap_sweep_c42.py`、`sweep_regmap_c42.txt`、`dut_refs.txt` | 526（第 43.3 節） | TH の札の入れ替えと TIMING の掃き、状態遷移表と regmap.REGS の掃きの結果、`dut.` の参照の一覧 |
| 43 | A | `r43/A/tb_a43_rand.sv`、`tb_a43_rand64.sv`、`rand_4301.txt`〜`rand_4305.txt`、`rand64_4364.txt` | 第 44.1 節 | 第 39 回の乱数のホストを広げた試験台（タイマの書き込みを合法な範囲の全体に、RUN でのタイマの書き直し、CHOP_FAST の変化）と 6 回の記録 |
| 43 | B | `r43/B/tb_b43_ver_bounce.sv`、`slip4.py`、`probe4.py` | 527（第 44.2 節） | FIFO にサンプルのある間の VERSION の読みの跳ねと、4 番目のバイトを入れた滑りの模型 |
| 43 | B | `r43/B/tb_spi_mut.txt`、`tb_top_mut.txt`、`check_top_mut.txt`、`check_seq_mut.txt` | 528（第 44.2 節） | OVF の MISO を 0xA5 とする写しの tb_spi_r14 と tb_top_r14 の記録 |
| 43 | B | `r43/B/fake_empty.py`、`smp_slip_crc.py`、`reset_crcform.py`、`tb_spi_4343.txt`、`check_4343.txt`、`run_all.txt` | 第 44.2 節 | サンプルの読みの滑りと CRC、リセットされたチップの CRC の形の読み、新しい系列の tb_spi_r14 |
| 43 | C | `r43/C/tb_c43_idleapply.sv`、`c43_idleapply_clean.txt`、`c43_idleapply_mutant.txt`、`screen_c1.txt` | 530（第 44.3 節） | STOP の残したサンプルと IDLE の APPLY、APPLY_NR（清い RTL と写し、写しの 16 群） |
| 43 | C | `r43/C/tb_c43_ovlpulse.sv`、`c43_ovlpulse.txt`、`mon43.sv`、`mon43_8deep.txt`、`screen_k.txt` | 531（第 44.3 節） | PULSE の中の過負荷と DFLAG.OVL、状態ごとの hit と読みの監視 |
| 43 | C | `r43/C/tb_c43_acthread.sv`、`c43_acthread.txt`、`screen_b.txt` | 532（第 44.3 節） | OFF_M_H の写しの読みの瞬間（清い RTL と写し） |
| 43 | C | `r43/C/regmap_sweep_c43.py`、`sweep_regmap_c43.txt`、`regmap_check.txt`、`regmap_selftest.txt` | 533（第 44.3 節） | regmap.REGS のフィールドの間の入れ替えの掃きと、RAW_EN の端子を ALERT_MASK に移した通しの確かめ |
| 43 | C | `r43/C/muts43.py`、`fsm_sweep_c43.py`、`sweep_c43.txt`、`baseline_run.txt`、`a43_dutrefs_now.txt` | 第 44.3 節 | RTL の写しの定義、状態遷移表の新しい類の掃き、基準の 16 群の記録、`dut.` の参照の一覧 |
| 44 | A | `r44/A/tb_a44_pend.sv`、`a44pend.txt`、`a44pend_crc1m.txt`、`a44pend_crc2m.txt` | 535（第 45.1 節） | 命令を取るはずの tick の不正な状態の値と CMD_PENDING の読み（先頭バイトで数えたもの） |
| 44 | A | `r44/A/tb_r44_pend_data.sv`、`pend_data_2m.txt`、`pend_data_fast.txt`、`pend_data_1m.txt` | 535（第 45.1 節） | 対応の側の数え直し：規則 (b) の判断する CRC 付きのデータのバイトと、最速の合法なタイミング |
| 44 | A | `r44/A/timing_model.py`、`changed_model.py`、`tb_a44_softclr.sv`、`a44softclr.txt`、`a44softclr2.txt`、`rand_4401.txt`、`rand_4402.txt`、`rand64_4464.txt` | 第 45.1 節 | RTL から書いた時刻の模型、ALIGN の出力のフレームの SOFT_RESET、第 43 回の不変の台の新しい系列 |
| 44 | B | `r44/B/tb_b44_slipall.sv`、`tb_b44_slipall.py`、`slipall.txt`、`slipall2.txt`、`slipall_log.txt`、`slipall2_log.txt` | 第 45.2 節 | 読める全てのレジスタとアクティブの写しの CRC 付きの読み出しへの 1 回の故障と、受け入れた誤った値の記録の組との照合 |
| 44 | B | `r44/B/tb_b44_slipdir.sv`、`tb_b44_slipdir.py`、`slipdir.txt`、`slipdir_log.txt`、`tb_b44_sliperr.sv`、`sliperr.txt` | 第 45.2 節 | 記録の組を持つ値と ERR 0x66 の滑り |
| 44 | B | `r44/B/tb_b44_minhigh.sv`、`minhigh_log.txt`、`tb_spi_r14_f4.sv`、`tb_spi_f4_log.txt`、`tb_spi_s4401_log.txt`、`crc.py`、`hdrslip.py`、`mirror_shift_diff.txt`、`mirror_shift_check.txt` | 第 45.2 節 | 誤りのフレームのあとの最短の CS_N の High と ALERT、FIFO 4 段と新しい系列の tb_spi_r14、サンプルの先頭バイトの滑り、アクティブの写しの番地をずらした regmap の検査 |
| 44 | C | `r44/C/wave_lanes_c44.py`、`wave_lanes_c44_before.txt`、`wave_lanes_c44_after.txt` | 536（第 45.3 節） | タイミング図の線の8 通りの書き換え（31000048 で全て通り、直した版で全て検出） |
| 44 | C | `r44/C/r44_c2_variant.txt` | 537（第 45.3 節） | 対応の側の確かめ：段 AG の (3) の APPLY_NR を FILL に移した試験台の写し |
| 44 | C | `r44/C/fsm_sweep_c44.py`、`fsm_sweep_sig.py`、`sweep_fsm_c44.txt`、`regmap_sweep2.py`、`sweep_regmap_std.txt`、`sweep_regmap_std_mid.txt`、`sweep_regmap_std_tail.txt`、`regmap_fmove_c44.py`、`sweep_regmap_fmove.txt` | 第 45.3 節 | 状態遷移表の新しい類と regmap.REGS の掃き |
| 44 | C | `r44/C/muts44.py`、`c44_dbg3_genblank.screen.txt`、`m224.screen.txt`、`chk_spi_ovfkind.py`、`baseline_run.txt` | 第 45.3 節 | RTL の写しの定義とその記録、OVF の種類の照合、基準の 16 群の記録 |
