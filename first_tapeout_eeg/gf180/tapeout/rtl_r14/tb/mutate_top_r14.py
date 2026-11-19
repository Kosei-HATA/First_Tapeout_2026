#!/usr/bin/env python3
"""Mutation self-test of the r14 testbenches (11/19): each listed RTL error, put in on purpose into a copy of the r14
RTL, must be detected. MUTATIONS by tb_top_r14 / check_top_r14.py; SPI_MUTATIONS by tb_spi_r14 / check_spi_trace.py
(a mismatch with the specification on some frame; a shorter run than run_tests_r14.sh, +n=800, so branch coverage is
not asked for here); SEQ_MUTATIONS by tb_seq / check_seq_trace.py (the timer modelled independently); each of the
two with an unmutated baseline that must show no mismatch. The unmutated RTL passes both benches
(run_tests_r14.sh), so a mutation that still passes shows a hole in a testbench.

Each mutation runs in build/mut/mNN/ (its own copy of the RTL and its own logs); the register tests
(build/reg_tests.svh) and the CODE stream (build/top_r14.codes) are shared, so run_tests_r14.sh (or gen_reg_tests.py
and the stream) must have run once.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/mutate_top_r14.py [-j N] [--top | --spi | --seq]
       [--only m03,s11,q02]
"""
import concurrent.futures as cf
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
R14 = os.path.normpath(os.path.join(HERE, ".."))
RTL_OLD = os.path.normpath(os.path.join(R14, "..", "rtl"))
SPEC = os.path.join(RTL_OLD, "spec")
BUILD = os.path.join(R14, "build")
SRC = ["eeg_digital_top.sv", "eeg_seq.sv", "eeg_regs.sv", "eeg_spi_slave.sv", "eeg_fifo.sv", "eeg_ovl.sv",
       "eeg_cic3.sv", "eeg_clkgen.sv"]
OLD = ["eeg_chop1.sv", "eeg_raw.sv", "eeg_rnd_sat.sv"]

# (name, file, text in the RTL (must occur exactly once), replacement)
MUTATIONS = [
    ("FIFO：先頭でなくなった写しでも取り出す（旧い挙動）", "eeg_fifo.sv",
     "assign pop_ok    = pop && held && !flush;", "assign pop_ok    = pop && (level != 4'd0) && !flush;"),
    ("FIFO：OVERRUN を立てない", "eeg_fifo.sv",
     "ovr_set  <= push && !push_ok;", "ovr_set  <= 1'b0;"),
    ("レジスタ：誤った鍵で CMD_ERR を立てない", "eeg_regs.sv",
     "if (wdata != TEST_KEY_VALUE && wdata != 8'h00) ev_err[ERR_CMD_ERR_LSB] = 1'b1;", ";"),
    ("レジスタ：未処理の命令があると SOFT_RESET を受け付けない", "eeg_regs.sv",
     "assign soft_reset = we && wr_def && !wr_ro && (addr == A_COMMAND) && is_soft;",
     "assign soft_reset = we && wr_def && !wr_ro && (addr == A_COMMAND) && is_soft && !pend;"),
    ("レジスタ：範囲外の値も書く", "eeg_regs.sv",
     "ev_err[ERR_RANGE_ERR_LSB] = 1'b1;", "ev_err[ERR_RANGE_ERR_LSB] = 1'b1; w_ok = 1'b1;"),
    ("レジスタ：オフセット DAC の端子がシャドウに従う（tick を待たない）", "eeg_regs.sv",
     "assign off_mag    = o_ofm;", "assign off_mag    = s_m;"),
    ("レジスタ：一括反映で CPF_TRIM を写さない", "eeg_regs.sv",
     "a_cpf <= s_cpf;", ";"),
    ("レジスタ：nr_ok が 2 段を許す", "eeg_regs.sv",
     "(dsv >= -12'sd1) && (dsv <= 12'sd1)", "(dsv >= -12'sd2) && (dsv <= 12'sd2)"),
    ("レジスタ：未処理の間の未定義のコードを STATE_ERR とする", "eeg_regs.sv",
     "end else if (!is_cmd_code) begin", "end else if (!is_cmd_code && !pend) begin"),
    ("レジスタ：STATUS の固定ビット 6 が 1", "eeg_regs.sv",
     "assign status_byte = {1'b1, 1'b0, alert,", "assign status_byte = {1'b1, 1'b1, alert,"),
    ("レジスタ：DFLAG を W1C で消せない", "eeg_regs.sv",
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? wdata[1:0] : 2'b00)) | {ovl_set, ovr_set};",
     "dflag <= dflag | {ovl_set, ovr_set};"),
    ("SPI：書き込みの CRC を検査しない", "eeg_spi_slave.sv",
     "if (crc_en && (wcrc != crc8_step(crc8_step(8'h00, hdr), wdat))) crc_err <= 1'b1;",
     "if (1'b0) crc_err <= 1'b1;"),
    ("SPI：バイトの途中の CS_N を通知しない", "eeg_spi_slave.sv",
     "if (bit_cnt != 3'd0 || st == S_OVF || st == S_WDAT || st == S_WCRC ||",
     "if (st == S_OVF || st == S_WDAT || st == S_WCRC ||"),
    ("SPI：途中で止めたサンプルの読み出しでも取り出す", "eeg_spi_slave.sv",
     "end else if (st == S_SDONE) begin", "end else if (st == S_SDONE || st == S_RSMP) begin"),
    ("SPI：読み出しの CRC に先頭バイトを含めない", "eeg_spi_slave.sv",
     "S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), txd);", "S_RCRC:  tx_next = crc8_step(8'h00, txd);"),
    ("SPI：連続読み出しでアドレスを進めない", "eeg_spi_slave.sv",
     "else        reg_addr <= reg_addr + 7'd1;", "else        ;"),
    ("SPI：完了したフレームのあとのビットを無視する（過長な書き込みを確定）", "eeg_spi_slave.sv",
     "st <= S_OVF;                     // a bit after a completed frame", "st <= st;"),
    ("最上位：CHANGED が 1 個少ない（2 ＋ T_ELEC）", "eeg_digital_top.sv",
     "assign chg_new = 9'd3 + {1'b0, t_elec};", "assign chg_new = 9'd2 + {1'b0, t_elec};"),
    ("最上位：T_PRE が 1 単位短い", "eeg_digital_top.sv",
     ".t_pre(t_pre), .t_rst(t_rst), .state(seq_state)", ".t_pre(t_pre - 8'd1), .t_rst(t_rst), .state(seq_state)"),
    ("最上位：T_RST が 1 単位短い", "eeg_digital_top.sv",
     ".t_rst(t_rst), .state(seq_state)", ".t_rst(t_rst - 8'd1), .state(seq_state)"),
    ("最上位：ALIGN で CIC をクリアしない", "eeg_digital_top.sv",
     ".arm(cic_arm),", ".arm(1'b0),"),
    ("最上位：DRDY のパルスをフレームの末尾で数える（119 MCLK）", "eeg_digital_top.sv",
     "((cycle == STORE_CYCLE && drdy_cnt != 3'd0)", "((frame_stb && drdy_cnt != 3'd0)"),
    ("最上位：サンプルの状態に OVERRUN を入れない", "eeg_digital_top.sv",
     ".status_in({1'b1, dflag_overrun,", ".status_in({1'b1, 1'b0,"),
    ("クロック：tick が 1 サイクル早い（サイクル 23）", "eeg_clkgen.sv",
     "tick       <= (cnt_nxt[4:0] == 5'd24) &&", "tick       <= (cnt_nxt[4:0] == 5'd23) &&"),
    # audit round 1 (11/20)
    ("シーケンサ：WARMUP の APPLY で解除までの待ちを数え直さない", "eeg_seq.sv",
     "a_restart = (state == S_WARMUP);", "a_restart = 1'b0;"),
    ("シーケンサ：APPLY で FIFO を空にしない", "eeg_seq.sv",
     "a_flush = 1'b1;                 // the data restart: no sample of the old setting", ";"),
    ("最上位：SOFT_RESET でフレームの計数とチョッパを戻す", "eeg_digital_top.sv",
     ".clk(MCLK), .rst_n(tm_rst_n), .chop_fast(a_chop_fast)", ".clk(MCLK), .rst_n(rst_n), .chop_fast(a_chop_fast)"),
    ("最上位：SOFT_RESET で SEQ を戻す", "eeg_digital_top.sv",
     "if (!tm_rst_n)    seq_cnt <= 16'd0;", "if (!tm_rst_n || !rst_n) seq_cnt <= 16'd0;"),
    ("最上位：OVL が直前の 1 ms のみ", "eeg_digital_top.sv",
     ".status_in({1'b1, dflag_overrun, ovl_iv | ovl_hist[0] | ovl_hist[1],", ".status_in({1'b1, dflag_overrun, ovl_iv,"),
    ("最上位：CHANGED の長さに T_ELEC を足さない", "eeg_digital_top.sv",
     "assign chg_new = 9'd3 + {1'b0, t_elec};", "assign chg_new = 9'd3;"),
    ("最上位：IDLE の過負荷でも DFLAG.OVL を立てる", "eeg_digital_top.sv",
     ".ovl_set(ovl_now && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),", ".ovl_set(ovl_now),"),
    ("レジスタ：未処理の命令がある間もシャドウとタイマへ書く", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin", "end else if (1'b0) begin"),
    ("レジスタ：STATUS の CMD_PENDING が 0 のまま", "eeg_regs.sv",
     "assign status_byte = {1'b1, 1'b0, alert, pend,", "assign status_byte = {1'b1, 1'b0, alert, 1'b0,"),
    ("レジスタ：STATUS の DATA が 0 のまま", "eeg_regs.sv",
     "(state == ST_RUN), fifo_nonempty, ovl_now, afe_rst};", "(state == ST_RUN), 1'b0, ovl_now, afe_rst};"),
    ("レジスタ：STATUS の OVL_NOW が 0 のまま", "eeg_regs.sv",
     "(state == ST_RUN), fifo_nonempty, ovl_now, afe_rst};", "(state == ST_RUN), fifo_nonempty, 1'b0, afe_rst};"),
    ("レジスタ：STATUS の AFE_RST が 1 のまま", "eeg_regs.sv",
     "(state == ST_RUN), fifo_nonempty, ovl_now, afe_rst};", "(state == ST_RUN), fifo_nonempty, ovl_now, 1'b1};"),
    ("SPI：CRC 有効時の CRC のない読み出しと短いサンプルを通す", "eeg_spi_slave.sv",
     "(crc_en && (st == S_RCRC || st == S_RSMP)) || st > S_OVF) begin", "st > S_OVF) begin"),
    ("最上位：RUN を出ても CHANGED の残りを消さない", "eeg_digital_top.sv",
     "else if (seq_state != ST_RUN) chg_cnt <= 9'd0;", "else if (1'b0)                chg_cnt <= 9'd0;"),
    # audit round 2 (11/20)
    ("最上位：新しい印が長い残りを短く上書きする", "eeg_digital_top.sv",
     "chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : chg_new;", "chg_cnt <= chg_new;"),
    ("最上位：サンプルの ERR が 0 のまま", "eeg_digital_top.sv",
     "chg_now, alert, 3'b000}", "chg_now, 1'b0, 3'b000}"),
    ("最上位：サンプルの予約ビットが 0 でない", "eeg_digital_top.sv",
     "chg_now, alert, 3'b000}", "chg_now, alert, 3'b100}"),
    ("最上位：空の語の状態が 0x00", "eeg_digital_top.sv",
     ".empty_status({1'b0, dflag_overrun, ovl_now, 1'b0, alert, 3'b000})", ".empty_status(8'h00)"),
    ("レジスタ：ALERT がマスクを無視する", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag & r_mask_d);", "assign alert       = |err || |dflag;"),
    ("最上位：DRDY_N の解除がフレームの先頭まで遅れる（レベル）", "eeg_digital_top.sv",
     "drdy_n_q   <= drdy_mode ? ~drdy_pulse : ~fifo_nonempty;",
     "drdy_n_q   <= drdy_mode ? ~drdy_pulse : (~fifo_nonempty && (drdy_n_q || cycle == 5'd0));"),
    ("SPI：MISO が 2 MCLK 遅れる（最小の Low で間に合わない）", "eeg_spi_slave.sv",
     "assign miso      = tx_sh[7];",
     "logic [1:0] miso_d; always_ff @(posedge clk) miso_d <= {miso_d[0], tx_sh[7]}; assign miso = miso_d[1];"),
    # audit round 2, auditor C: the mutants that passed every bench (values and mapping of the analog pins, timers,
    # cfg_ok / nr_ok, the overload flag's gating, the reset domains)
    ("最上位：CHOP_EN が AFE_RST の間 0（組み合わせ）", "eeg_digital_top.sv",
     "assign CHOP_EN    = ~a_cstop;", "assign CHOP_EN    = ~a_cstop & ~seq_afe_rst;"),
    ("最上位：CHOP_EN が反転（チョッパが止まる）", "eeg_digital_top.sv",
     "assign CHOP_EN    = ~a_cstop;", "assign CHOP_EN    = a_cstop;"),
    ("最上位：BTRIM の P と N の入れ違い", "eeg_digital_top.sv",
     ".btrim_p(BTRIM_P), .btrim_n(BTRIM_N)", ".btrim_p(BTRIM_N), .btrim_n(BTRIM_P)"),
    ("レジスタ：OFEN が範囲の 2 進（温度計でない）", "eeg_regs.sv",
     "o_ofen <= ofen_of_range(s_range);", "o_ofen <= {1'b0, s_range};"),
    ("レジスタ：DAC を使うときの BLANK 15 がない", "eeg_regs.sv",
     "assign blank_len  = (a_range != 3'd0) ? BLANK_WITH_DAC : a_blank;", "assign blank_len  = a_blank;"),
    ("レジスタ：一括反映で AFE_IBIAS を写さない", "eeg_regs.sv", "a_ibias <= s_ibias;", ";"),
    ("レジスタ：一括反映で DWA_EN を写さない", "eeg_regs.sv", "a_dwa <= s_dwa;", ";"),
    ("レジスタ：一括反映で CHOP1_RATE を写さない", "eeg_regs.sv", "a_c1 <= s_c1;", ";"),
    ("レジスタ：T_REC に T_PRE を出す（RECOVER 23.4 µs）", "eeg_regs.sv",
     "assign t_rec      = r_trec;", "assign t_rec      = r_tpre;"),
    ("レジスタ：nr_ok が範囲の違いを許す", "eeg_regs.sv",
     "assign nr_ok  = (s_range == a_range) && ", "assign nr_ok  = "),
    ("レジスタ：cfg_ok が範囲 2 で M の上限を見ない", "eeg_regs.sv",
     "assign cfg_ok = (s_m <= range_max_m(s_range));", "assign cfg_ok = (s_m <= range_max_m(s_range)) || (s_range == 3'd2);"),
    ("最上位：DFLAG.OVL を IDLE 以外の全ての状態で立てる", "eeg_digital_top.sv",
     ".ovl_set(ovl_now && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),", ".ovl_set(ovl_now && (seq_state != ST_IDLE)),"),
    ("最上位：SOFT_RESET で CHOP1 を戻す", "eeg_digital_top.sv",
     "eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(rst_n),"),
    ("最上位：SOFT_RESET で ADC_RST_N を下げる", "eeg_digital_top.sv",
     "assign ADC_RST_N = tm_rst_n;", "assign ADC_RST_N = rst_n;"),
    # audit round 3, auditor B
    ("最上位：SOFT_RESET で FIFO を空にしない", "eeg_digital_top.sv",
     ".clk(MCLK), .rst_n(rst_n), .flush(seq_flush), .push(seq_store),",
     ".clk(MCLK), .rst_n(tm_rst_n), .flush(seq_flush), .push(seq_store),"),
    ("レジスタ：連続読み出しの途中の未定義のアドレスが 0xFF", "eeg_regs.sv",
     "default:          addr_ok = 1'b0;", "default:          begin addr_ok = 1'b0; rdata = 8'hFF; end"),
    ("SPI：不正な状態の値を FRAME_ERR にしない", "eeg_spi_slave.sv",
     "(crc_en && (st == S_RCRC || st == S_RSMP)) || st > S_OVF) begin",
     "(crc_en && (st == S_RCRC || st == S_RSMP))) begin"),
    # audit round 3, auditor C
    ("レジスタ：nr_ok がトリム（IBIAS、CPF、BTRIM）の変化を見ない", "eeg_regs.sv",
     "(s_ibias == a_ibias) && (s_cpf == a_cpf) && (s_bp == a_bp) && (s_bn == a_bn) &&", "1'b1 &&"),
    ("レジスタ：nr_ok が速さ・DWA・CHOP1・BLANK の変化を見ない", "eeg_regs.sv",
     "(s_fast == a_fast) && (s_dwa == a_dwa) && (s_c1 == a_c1) && (s_blank == a_blank) &&", "1'b1 &&"),
    ("レジスタ：nr_ok が試験の設定の変化を見ない", "eeg_regs.sv",
     "(s_atpen == a_atpen) && (s_atpsel == a_atpsel) && (s_cstop == a_cstop) && (s_azero == a_azero);", "1'b1;"),
    ("レジスタ：nr_ok が符号を無視する", "eeg_regs.sv",
     "assign sv_s   = s_sign ? -$signed({2'b00, s_m}) : $signed({2'b00, s_m});", "assign sv_s   = $signed({2'b00, s_m});"),
    ("レジスタ：チョッパの速さがシャドウに従う", "eeg_regs.sv", "assign chop_fast  = a_fast;", "assign chop_fast  = s_fast;"),
    ("レジスタ：CHOP1 の速さがシャドウに従う", "eeg_regs.sv", "assign chop1_rate = a_c1;", "assign chop1_rate = s_c1;"),
    ("レジスタ：BLANK がシャドウに従う", "eeg_regs.sv",
     "assign blank_len  = (a_range != 3'd0) ? BLANK_WITH_DAC : a_blank;", "assign blank_len  = (s_range != 3'd0) ? BLANK_WITH_DAC : s_blank;"),
    ("最上位：RAW_EN が効かない", "eeg_digital_top.sv", ".raw_en(raw_en), .cycle(cycle)", ".raw_en(1'b0), .cycle(cycle)"),
    ("最上位：DBG_SEL が効かない", "eeg_digital_top.sv",
     ".dbg_sel(dbg_sel), .dbg_clk({CHOP_BLANK", ".dbg_sel(2'b00), .dbg_clk({CHOP_BLANK"),
    ("クロック：TH_CAPTURE がサイクル 2", "eeg_clkgen.sv",
     "th_capture <= (cnt_nxt[4:0] == 5'd1);", "th_capture <= (cnt_nxt[4:0] == 5'd2);"),
    ("最上位：DAC_CLK がサイクル 5（e5 で立ち上がる）", "eeg_digital_top.sv",
     "localparam logic [4:0] DAC_CLK_CYCLE = 5'(DAC_LOAD_CYCLE + 1);", "localparam logic [4:0] DAC_CLK_CYCLE = 5'(DAC_LOAD_CYCLE + 2);"),
    ("SPI：MISO_OE が CS_N の立ち上がりで直ちに切れない", "eeg_spi_slave.sv",
     "assign miso_oe   = ~cs_n & cs_act;", "assign miso_oe   = cs_act;"),
    ("レジスタ：STATE が下位 3 ビットのみ", "eeg_regs.sv",
     "A_STATE:          rdata = {4'h0, state};", "A_STATE:          rdata = {5'h00, state[2:0]};"),
    ("最上位：DRDY_N のパルスを捨てた出力にも出す", "eeg_digital_top.sv",
     "assign drdy_nxt = push_ok ? 3'd4 :", "assign drdy_nxt = seq_store ? 3'd4 :"),
    ("最上位：CHOP_EN が ADC_ZERO でも 0", "eeg_digital_top.sv",
     "assign CHOP_EN    = ~a_cstop;", "assign CHOP_EN    = ~a_cstop & ~a_azero;"),
    ("最上位：空の語の OVERRUN が 0", "eeg_digital_top.sv",
     ".empty_status({1'b0, dflag_overrun, ovl_now, 1'b0, alert, 3'b000})", ".empty_status({1'b0, 1'b0, ovl_now, 1'b0, alert, 3'b000})"),
]

# the unmutated block, run as the top bench's baseline (b00)
TOP_BASELINE = ("（基準：変更なし）", None, None, None)

# the sequencer alone (tb_seq + check_seq_trace, the timer modelled): what only the trace can see
SEQ_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("シーケンサ：WARMUP の APPLY で待ちを数え直さない", "eeg_seq.sv",
     "a_restart = (state == S_WARMUP);", "a_restart = 1'b0;"),
    ("シーケンサ：WAIT_E の APPLY_NR で電極の待ちを数え直さない", "eeg_seq.sv",
     "S_WAIT_E: a_restart = 1'b1;", "S_WAIT_E: ;"),
    ("シーケンサ：ALIGN の APPLY_NR で電極を待たない", "eeg_seq.sv",
     "S_ALIGN:  if (t_elec != 8'd0) nxt = S_WAIT_E;", "S_ALIGN:  ;"),
    ("シーケンサ：FILL の APPLY_NR で電極を待たない", "eeg_seq.sv",
     "S_FILL:   nxt = (t_elec != 8'd0) ? S_WAIT_E : S_ALIGN;", "S_FILL:   nxt = S_ALIGN;"),
    ("シーケンサ：数え直しでも同じ tick の満了を取る", "eeg_seq.sv",
     "if (nxt == state && timed(state) && tmr && !a_restart) begin", "if (nxt == state && timed(state) && tmr) begin"),
    ("シーケンサ：T_WARM の読み込みが 1 フレーム長い", "eeg_seq.sv",
     "S_WARMUP:  load_of = {t_warm, 10'd0};", "S_WARMUP:  load_of = {t_warm, 10'd0} + 18'd1;"),
    ("シーケンサ：T_RST の単位が 4 フレーム", "eeg_seq.sv",
     "S_PULSE:   load_of = {7'd0, t_rst, 3'd0};", "S_PULSE:   load_of = {8'd0, t_rst, 2'd0};"),
    ("シーケンサ：APPLY で FIFO を空にしない", "eeg_seq.sv",
     "a_flush = 1'b1;                 // the data restart: no sample of the old setting", ";"),
    # audit round 2, auditor C
    ("シーケンサ：タイマが 16 ビット（64 ms 以上で折り返す）", "eeg_seq.sv",
     "logic [17:0] timer;", "logic [15:0] timer;"),
    ("シーケンサ：不正な状態の判定が 10 以上（9 を見逃す）", "eeg_seq.sv",
     "if (state > S_PULSE) begin", "if (state > 4'd9) begin"),
    ("シーケンサ：tick でなくても命令の受け取りを返す", "eeg_seq.sv",
     "assign cmd_ack   = a_ack;", "assign cmd_ack   = cmd_valid;"),
]


# the register block alone (tb_regs: a W1C flag set in the cycle of its clear survives)
REGS_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("レジスタ：ERR の W1C でクリアが同じサイクルの事象に勝つ", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;",
     "err   <= (err | ev_err) & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00);"),
    ("レジスタ：ERR の W1C で書いた値によらず全てのビットを消す", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? 8'hFF : 8'h00)) | ev_err;"),
    ("レジスタ：DFLAG の W1C でクリアが同じサイクルの事象に勝つ", "eeg_regs.sv",
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? wdata[1:0] : 2'b00)) | {ovl_set, ovr_set};",
     "dflag <= (dflag | {ovl_set, ovr_set}) & ~((we && w_ok && addr == A_DFLAG) ? wdata[1:0] : 2'b00);"),
]


# the FIFO alone (tb_fifo + check_fifo_trace: fsm_spec.fifo_step and an identity model), depth 8
FIFO_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("FIFO：満杯で同じサイクルの取り出しを見ずに格納を捨てる", "eeg_fifo.sv",
     "assign push_ok   = push && (lvl0 != LEVEL_FULL);", "assign push_ok   = push && (level != LEVEL_FULL);"),
    ("FIFO：フラッシュと同じサイクルの格納を捨てる", "eeg_fifo.sv",
     "assign lvl0      = flush ? 4'd0 : (level - {3'd0, pop_ok});", "assign lvl0      = flush ? LEVEL_FULL : (level - {3'd0, pop_ok});"),
    ("FIFO：取り出しで写しの印を消さない", "eeg_fifo.sv",
     "if (flush || pop_ok) held <= 1'b0;", "if (flush) held <= 1'b0;"),
    ("FIFO：空の語の状態を出さない", "eeg_fifo.sv",
     "assign rd_word = (level == 4'd0) ? {empty_status, 16'h0000, 24'h000000} : mem[rd_ptr];",
     "assign rd_word = mem[rd_ptr];"),
    ("FIFO：nonempty が 1 サイクル遅い", "eeg_fifo.sv",
     "nonempty <= (level_nxt != 4'd0);", "nonempty <= (level != 4'd0);"),
]


SPI_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("SPI：バイトの途中の CS_N を通知しない", "eeg_spi_slave.sv",
     "if (bit_cnt != 3'd0 || st == S_OVF || st == S_WDAT || st == S_WCRC ||",
     "if (st == S_OVF || st == S_WDAT || st == S_WCRC ||"),
    ("SPI：途中で止めたサンプルの読み出しでも取り出しを要求", "eeg_spi_slave.sv",
     "end else if (st == S_SDONE) begin", "end else if (st == S_SDONE || st == S_RSMP) begin"),
    ("SPI：読み出しの CRC に先頭バイトを含めない", "eeg_spi_slave.sv",
     "S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), txd);", "S_RCRC:  tx_next = crc8_step(8'h00, txd);"),
    ("SPI：連続読み出しでアドレスを進めない", "eeg_spi_slave.sv",
     "else        reg_addr <= reg_addr + 7'd1;", "else        ;"),
    ("SPI：完了したフレームのあとのビットを無視する", "eeg_spi_slave.sv",
     "st <= S_OVF;                     // a bit after a completed frame", "st <= st;"),
    ("SPI：書き込みの CRC を検査しない", "eeg_spi_slave.sv",
     "if (crc_en && (wcrc != crc8_step(crc8_step(8'h00, hdr), wdat))) crc_err <= 1'b1;",
     "if (1'b0) crc_err <= 1'b1;"),
    ("SPI：未定義のアドレスの読み出しで ADDR_ERR を立てない", "eeg_spi_slave.sv",
     "addr_err  <= chk_addr && !reg_addr_ok;", "addr_err  <= 1'b0;"),
    ("SPI：先頭バイトで STATUS を返さない", "eeg_spi_slave.sv",
     "tx_sh   <= status_byte;                  // STATUS during the header byte", "tx_sh   <= 8'h80;"),
    ("FIFO：先頭でなくなった写しでも取り出す", "eeg_fifo.sv",
     "assign pop_ok    = pop && held && !flush;", "assign pop_ok    = pop && (level != 4'd0) && !flush;"),
    ("FIFO：フラッシュで写しの印を消さない", "eeg_fifo.sv",
     "if (flush || pop_ok) held <= 1'b0;", "if (pop_ok) held <= 1'b0;"),
    ("FIFO：空の語の写しにも印を付ける", "eeg_fifo.sv",
     "else if (snap)       held <= (level != 4'd0);", "else if (snap)       held <= 1'b1;"),
    ("レジスタ：未処理の命令を上書きする（busy を無視）", "eeg_regs.sv",
     "end else if (pend && !cmd_ack) begin", "end else if (1'b0) begin"),
    ("レジスタ：未定義のアドレスの読み出しが 0x00 でない", "eeg_regs.sv",
     "default:          addr_ok = 1'b0;", "default:          begin addr_ok = 1'b0; rdata = 8'hFF; end"),
]


def run(i, m, bench="top"):
    name, f, old, new = m
    d = os.path.join(BUILD, "mut", "b00" if i < 0 else f"{dict(spi='s', seq='q', fifo='f', regs='r').get(bench, 'm')}{i:02d}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "build"))
    for s in SRC:
        shutil.copy(os.path.join(R14, s), d)
    if f is not None:
        p = os.path.join(d, f)
        text = open(p, encoding="utf-8").read()
        if text.count(old) != 1:
            return i, name, "NOT APPLIED", f"the text occurs {text.count(old)} times in {f}"
        open(p, "w", encoding="utf-8").write(text.replace(old, new))
    os.symlink(os.path.join(BUILD, "top_r14.codes"), os.path.join(d, "build", "top_r14.codes"))
    tb = {"spi": "tb_spi_r14.sv", "seq": "tb_seq.sv", "fifo": "tb_fifo.sv", "regs": "tb_regs.sv"}.get(bench, "tb_top_r14.sv")
    srcs = ({"seq": ["eeg_seq.sv"], "fifo": ["eeg_fifo.sv"], "regs": ["eeg_regs.sv"]}.get(bench) or
            SRC + [os.path.join(RTL_OLD, x) for x in OLD])   # pin_tests.svh: found through -I build
    cmd = (["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", BUILD, "-o", "build/t.vvp"] + srcs
           + [os.path.join(R14, "tb", tb)])
    c = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if c.returncode:
        return i, name, "COMPILE ERROR", c.stderr.strip().splitlines()[-1][:150]
    if bench in ("seq", "spi", "fifo"):
        args = {"seq": ["+n=300000", "+seed=11", "+trace=build/seq_trace.txt"], "spi": ["+n=800", "+seed=7"],
                "fifo": ["+n=100000", "+trace=build/fifo_trace.txt"]}[bench]
        try:
            v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp"] + args, cwd=d, capture_output=True,
                               text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            return i, name, ("BASELINE FAILS" if f is None else "detected"), "no end within 3600 s"
    if bench == "seq":
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_trace.py"),
                            os.path.join(d, "build", "seq_trace.txt")], capture_output=True, text=True)
        head = next((ln for ln in k.stdout.splitlines() if "mismatches" in ln), "")
        if not head:
            return i, name, "CHECKER ERROR", (k.stderr.strip().splitlines() or ["no output"])[-1]
        nbad = int(head.split(":")[1].split()[0])
        direct = "PASS: tb_seq" in v.stdout
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  line")), head)
        if f is None:
            return i, name, ("baseline ok" if nbad == 0 and direct and "PASS" in k.stdout else "BASELINE FAILS"), head
        return i, name, ("detected" if nbad != 0 or not direct else "MISSED"), first
    if bench == "regs":
        try:
            v = subprocess.run(["vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return i, name, ("BASELINE FAILS" if f is None else "detected"), "no end within 600 s"
        head = next((ln for ln in v.stdout.splitlines() if ln.startswith("tb_regs:")), "no summary")
        first = next((ln for ln in v.stdout.splitlines() if ln.startswith("ERROR")), head)
        if f is None:
            return i, name, ("baseline ok" if "PASS: tb_regs" in v.stdout else "BASELINE FAILS"), head
        return i, name, ("detected" if "PASS: tb_regs" not in v.stdout else "MISSED"), first
    if bench == "fifo":
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_fifo_trace.py"),
                            os.path.join(d, "build", "fifo_trace.txt")], capture_output=True, text=True)
        head = next((ln for ln in k.stdout.splitlines() if "mismatches" in ln), "")
        if not head:
            return i, name, "CHECKER ERROR", (k.stderr.strip().splitlines() or ["no output"])[-1]
        nbad = int(head.split(":")[1].split()[0])
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  line")), head)
        if f is None:
            return i, name, ("baseline ok" if nbad == 0 and "PASS" in k.stdout else "BASELINE FAILS"), head
        return i, name, ("detected" if nbad != 0 or "PASS" not in k.stdout else "MISSED"), first
    if bench == "spi":
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_spi_trace.py"),
                            os.path.join(d, "build", "spi_trace.txt")], capture_output=True, text=True)
        head = k.stdout.splitlines()[0] if k.stdout else ("checker error: " + (k.stderr.strip().splitlines() or ["?"])[-1])
        nbad = int(head.split(":")[1].split()[0]) if "frames with mismatches" in head else -1
        if nbad < 0:                                 # the checker failed: neither a detection nor a pass
            return i, name, "CHECKER ERROR", head
        timing = next((ln for ln in v.stdout.splitlines() if "SPI timing errors" in ln), "")
        nt = int(timing.split(",")[1].split()[0]) if timing else -1
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  frame")), head)
        if f is None:
            return i, name, ("baseline ok" if nbad == 0 and nt == 0 else "BASELINE FAILS"), head
        return i, name, ("detected" if nbad != 0 or nt != 0 else "MISSED"), first
    try:
        v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True,
                           timeout=1800)
    except subprocess.TimeoutExpired:
        return i, name, "detected", "no end within 1800 s (the bench did not pass)"
    out = v.stdout
    k = subprocess.run([sys.executable, os.path.join(HERE, "check_top_r14.py"), os.path.join(d, "build")],
                       capture_output=True, text=True)
    tb_pass = "PASS: tb_top_r14" in out
    gold_pass = k.returncode == 0
    if f is None:
        k2 = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_trace.py"),
                             os.path.join(d, "build", "top_seq_trace.txt"), "--no-cover"], capture_output=True, text=True)
        ok = tb_pass and gold_pass and k2.returncode == 0
        return i, name, ("baseline ok" if ok else "BASELINE FAILS"), next((ln for ln in out.splitlines() if ln.startswith("tb_top_r14:")), "")[:150]
    first = next((ln for ln in out.splitlines() if ln.startswith(("ERROR", "SPI ERROR", "FAIL"))), "")
    if tb_pass and not gold_pass:
        first = "check_top_r14: " + next((ln for ln in k.stdout.splitlines() if "mismatch" in ln), "FAIL")
    return i, name, ("detected" if not (tb_pass and gold_pass) else "MISSED"), first


def main():
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 2
    for need in ("top_r14.codes", "reg_tests.svh"):
        if not os.path.exists(os.path.join(BUILD, need)):
            sys.exit(f"build/{need} missing: run run_tests_r14.sh first")
    which = next((w for w in ("spi", "top", "seq", "fifo", "regs") if f"--{w}" in sys.argv), "all")
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None   # e.g. s00,s11
    tasks = []
    if which in ("top", "all"):
        tasks += [(i, m, "top") for i, m in enumerate(MUTATIONS)] + [(-1, TOP_BASELINE, "top")]
    if which in ("spi", "all"):
        tasks += [(i, m, "spi") for i, m in enumerate(SPI_MUTATIONS)]
    if which in ("seq", "all"):
        tasks += [(i, m, "seq") for i, m in enumerate(SEQ_MUTATIONS)]
    if which in ("fifo", "all"):
        tasks += [(i, m, "fifo") for i, m in enumerate(FIFO_MUTATIONS)]
    if which in ("regs", "all"):
        tasks += [(i, m, "regs") for i, m in enumerate(REGS_MUTATIONS)]
    if only:
        tasks = [t for t in tasks if ("b00" if t[0] < 0 else f"{dict(spi='s', seq='q', fifo='f', regs='r').get(t[2], 'm')}{t[0]:02d}") in only]
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda a: (a[2],) + run(*a), tasks))
    ok = True
    title = {"top": "tb_top_r14", "spi": "tb_spi_r14 + check_spi_trace", "seq": "tb_seq + check_seq_trace (timer modelled)",
             "fifo": "tb_fifo + check_fifo_trace (fsm_spec.fifo_step and identities)",
             "regs": "tb_regs (W1C: the set wins)"}
    for bench in ("top", "spi", "seq", "fifo", "regs"):
        rs = sorted(r for r in res if r[0] == bench)
        if not rs:
            continue
        print(f"--- {title[bench]}")
        for _, i, name, verdict, first in rs:
            tag = "b00" if i < 0 else f"{dict(spi='s', seq='q', fifo='f', regs='r').get(bench, 'm')}{i:02d}"
            print(f"{verdict:8s} {tag} {name}" + (f"  ({first[:120]})" if first else ""))
        muts = [r for r in rs if r[3] != "baseline ok" and r[3] != "BASELINE FAILS"]
        n_det = sum(1 for r in muts if r[3] == "detected")
        base_ok = all(r[3] == "baseline ok" for r in rs if r[3] in ("baseline ok", "BASELINE FAILS"))
        print(f"{n_det} of {len(muts)} mutations detected" + ("" if bench == "top" else
                                                              f"; baseline {'clean' if base_ok else 'NOT clean'}"))
        ok &= n_det == len(muts) and base_ok
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
