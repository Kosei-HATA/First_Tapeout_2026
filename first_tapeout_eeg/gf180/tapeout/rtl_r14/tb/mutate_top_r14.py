#!/usr/bin/env python3
"""Mutation self-test of the r14 testbenches (11/19, extended by the audits of 11/20): each listed RTL error, put in on
purpose into a copy of the r14 RTL (and of the blocks kept from rtl/), must be detected, and each bench's unmutated
baseline must pass. The groups and their benches:
  top    MUTATIONS          tb_top_r14 + check_top_r14.py (golden CIC); baseline b00 also replays the sequencer trace
  spi    SPI_MUTATIONS      tb_spi_r14 + check_spi_trace.py (as run_tests_r14.sh: +n=1500 +seed=5; the baseline must
                            also cover every branch)
  seq    SEQ_MUTATIONS      tb_seq + check_seq_trace.py (the timer modelled independently)
  fifo   FIFO_MUTATIONS     tb_fifo + check_fifo_trace.py (fsm_spec.fifo_step and an identity model)
  regs   REGS_MUTATIONS     tb_regs (W1C; cfg_ok / nr_ok against regmap over build/ok_vectors.txt)
  chop1  CHOP1_MUTATIONS    rtl/tb/tb_chop1.sv with the r14 clock generator
  rnd    RND_MUTATIONS      rtl/tb/tb_rnd_sat.sv (build/rnd_sat.vec from rtl/model/gen_vectors.py)
  struct STRUCT_MUTATIONS   check_outputs_registered.py (every output a flip-flop's: NFR-06, yosys)
Each mutation runs in build/mut/<tag>/ (its own copy of the RTL and its own logs); the generated files (build/
reg_tests.svh, pin_tests.svh, top_r14.codes, ok_vectors.txt, rnd_sat.vec) are shared, so run_tests_r14.sh must have
run once. Every run's report (also with --only) is printed and written to build/mutate_<date-time>.log with its
arguments, so a recorded result always has its log (audit round 4).

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/mutate_top_r14.py [-j N]
       [--top | --spi | --seq | --fifo | --regs | --chop1 | --rnd | --struct | --ovl] [--only m03,s11,q02]
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
     ".arm(cic_arm & ~soft_req),", ".arm(1'b0),"),
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
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),", ".ovl_set(ovl_hit),"),
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
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : (~fifo_nonempty && (drdy_n_q || cycle == 5'd0)));"),
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
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),", ".ovl_set(ovl_hit && (seq_state != ST_IDLE)),"),
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
    # audit round 4, auditor B
    ("レジスタ：拒否した命令が未処理の命令を置き換える", "eeg_regs.sv",
     "            if (w_ok && addr == A_COMMAND) begin",
     "            if (we && addr == A_COMMAND && is_cmd_code && pend && !cmd_ack) pcode <= wdata;\n            if (w_ok && addr == A_COMMAND) begin"),
    ("レジスタ：拒否した命令が未処理の命令を取り消す", "eeg_regs.sv",
     "            end else if (cmd_ack) begin\n                pend  <= 1'b0;",
     "            end else if (cmd_ack || (we && addr == A_COMMAND && is_cmd_code)) begin\n                pend  <= 1'b0;"),
    ("SPI：不正な状態の判定が 12 以上（11 を見逃す）", "eeg_spi_slave.sv",
     "(crc_en && (st == S_RCRC || st == S_RSMP)) || st > S_OVF) begin",
     "(crc_en && (st == S_RCRC || st == S_RSMP)) || st > 4'd11) begin"),
    # audit round 4, auditor A: SOFT_RESET committed in the cycle of a tick, an output time, after a store (NFR-06)
    ("最上位：SOFT_RESET の確定の周期にも tick を通す（AFE_RST と反映の端子に短いパルス）", "eeg_digital_top.sv",
     "assign tick_s = tick & ~soft_req;", "assign tick_s = tick;"),
    ("最上位：SOFT_RESET の確定の周期にも出力の時刻を通す（RESET の行に反して格納）", "eeg_digital_top.sv",
     "assign out_s  = cic_stb & ~soft_req;", "assign out_s  = cic_stb;"),
    ("最上位：SOFT_RESET の確定の周期に DRDY_N を High にしない", "eeg_digital_top.sv",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= drdy_mode ? ~drdy_pulse : ~fifo_nonempty;"),
    # audit round 4, auditor C (each passed every test before the round's additions)
    ("レジスタ：nr_ok の 1 段を M[7:0] だけで計算（M_H だけの変化を受け付ける）", "eeg_regs.sv",
     "    assign sv_s   = s_sign ? -$signed({2'b00, s_m}) : $signed({2'b00, s_m});\n    assign sv_a   = a_sign ? -$signed({2'b00, a_m}) : $signed({2'b00, a_m});",
     "    assign sv_s   = s_sign ? -$signed({4'b0000, s_m[7:0]}) : $signed({4'b0000, s_m[7:0]});\n    assign sv_a   = a_sign ? -$signed({4'b0000, a_m[7:0]}) : $signed({4'b0000, a_m[7:0]});"),
    ("レジスタ：nr_ok が M[9:8] の一致も求める（255/256 の 1 段を拒否）", "eeg_regs.sv",
     "assign nr_ok  = (s_range == a_range) &&", "assign nr_ok  = (s_range == a_range) && (s_m[9:8] == a_m[9:8]) &&"),
    ("最上位：CHOP_EN が PULSE で 0", "eeg_digital_top.sv",
     "assign CHOP_EN    = ~a_cstop;", "assign CHOP_EN    = ~a_cstop & (seq_state != ST_PULSE);"),
    ("レジスタ：STATUS の READY が RUN 以上（PRE と PULSE でも 1）", "eeg_regs.sv",
     "(state == ST_RUN), fifo_nonempty, ovl_now, afe_rst};", "(state >= ST_RUN), fifo_nonempty, ovl_now, afe_rst};"),
    ("最上位：過負荷の検出を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "eeg_ovl u_ovl (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_ovl u_ovl (.clk(MCLK), .rst_n(rst_n),"),
    ("最上位：DAC_CLK を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n) DAC_CLK <= 1'b0;",
     "    always_ff @(posedge MCLK or negedge rst_n) begin\n        if (!rst_n) DAC_CLK <= 1'b0;"),
    ("レジスタ：解錠のあとの誤った鍵が解錠を保つ", "eeg_regs.sv",
     "A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);",
     "A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE) || (unlocked && wdata != 8'h00);"),
    # audit round 5, auditor A
    ("最上位：CIC のクリアの判断を SOFT_RESET の確定のサイクルでも取る", "eeg_digital_top.sv",
     ".arm(cic_arm & ~soft_req)", ".arm(cic_arm)"),
    ("SPI：サンプルの CRC に先頭バイトを含めない（全て 0 の応答が CRC の合う空の語になる）", "eeg_spi_slave.sv",
     "default: tx_next = crc8_48(CRC_SMP_HDR, shadow);", "default: tx_next = crc8_48(8'h00, shadow);"),
    # audit round 5, auditor C (each passed all 16 groups of run_tests_r14.sh)
    ("レジスタ：確認のサイクルに書いた命令を失う", "eeg_regs.sv", "            if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end else if (cmd_ack) begin\n                pend  <= 1'b0;\n            end", "            if (cmd_ack) begin\n                pend  <= 1'b0;\n            end else if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end"),
    ("レジスタ：確認のサイクルの命令を拒否", "eeg_regs.sv",
     "end else if (pend && !cmd_ack) begin", "end else if (pend) begin"),
    ("最上位：FLUSH で CHANGED の残りを消す", "eeg_digital_top.sv",
     "else if (seq_state != ST_RUN) chg_cnt <= 9'd0;", "else if (seq_state != ST_RUN || seq_flush) chg_cnt <= 9'd0;"),
    ("最上位：CHOP_DLY が 1", "eeg_digital_top.sv", ".chop_dly(8'd0)", ".chop_dly(8'd1)"),
    ("最上位：反映でも FIFO を空にする", "eeg_digital_top.sv",
     ".flush(seq_flush), .push(seq_store),", ".flush(seq_flush | apply), .push(seq_store),"),
    ("レジスタ：ALERT が CMD、STATE、CFG、RANGE の ERR を含まない", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag & r_mask_d);",
     "assign alert       = |(err[3:0] & r_mask[3:0]) || |(dflag & r_mask_d);"),
    ("レジスタ：ALERT が OVERRUN を含まない", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag & r_mask_d);",
     "assign alert       = |(err & r_mask) || (dflag[1] & r_mask_d[1]);"),
    ("最上位：CHANGED の計数が 8 ビット", "eeg_digital_top.sv", "logic [8:0]  chg_cnt;", "logic [7:0]  chg_cnt;"),
    ("最上位：DFLAG.OVL を WAIT_E と ALIGN でも立てる", "eeg_digital_top.sv",
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),",
     ".ovl_set(ovl_hit && (seq_state >= ST_WAIT_E) && (seq_state <= ST_RUN)),"),
    ("SPI：読み出しの CRC を送ったバイトでなくその時のレジスタの値で計算", "eeg_spi_slave.sv",
     "S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), txd);",
     "S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), reg_rdata);"),
    # audit round 6, auditor A: OVL only for extreme codes during a detected overload
    ("最上位：間隔の OVL に検出の尾を含める（区切りで検出の状態を持ち越す）", "eeg_ovl.sv",
     "if (out_stb)      ovl_seen <= 1'b0;", "if (out_stb)      ovl_seen <= ovl_now;"),
    ("最上位：DFLAG.OVL を検出の状態で立てる（ALIGN の尾で FILL に立つ）", "eeg_digital_top.sv",
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),",
     ".ovl_set(ovl_now && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),"),
    # audit round 6, auditor C (each passed all 16 groups before the round's additions)
    ("最上位：OVL の履歴を格納したサンプルごとに進める", "eeg_digital_top.sv",
     "else if (cic_stb) ovl_hist <= {ovl_hist[0], ovl_iv};", "else if (push_ok) ovl_hist <= {ovl_hist[0], ovl_iv};"),
    ("最上位：DFLAG.OVL を ALIGN でも立てる", "eeg_digital_top.sv",
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),",
     ".ovl_set(ovl_hit && ((seq_state == ST_ALIGN) || (seq_state == ST_FILL) || (seq_state == ST_RUN))),"),
    ("最上位：CHANGED を格納したサンプルで数える", "eeg_digital_top.sv",
     "else if (cic_stb && chg_now)  chg_cnt <= chg_cnt - 9'd1;", "else if (push_ok && chg_now)  chg_cnt <= chg_cnt - 9'd1;"),
    ("最上位：CHANGED の印が 255 で飽和", "eeg_digital_top.sv",
     "chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : chg_new;",
     "chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : ((chg_new > 9'd255) ? 9'd255 : chg_new);"),
    ("レジスタ：STATUS の READY が FILL でも 1", "eeg_regs.sv",
     "(state == ST_RUN), fifo_nonempty, ovl_now, afe_rst};", "((state == ST_RUN) || (state == ST_FILL)), fifo_nonempty, ovl_now, afe_rst};"),
    ("最上位：STATUS の OVL_NOW が次の出力まで残る", "eeg_digital_top.sv",
     ".ovl_now(ovl_now), .ovr_set(ovr_set),", ".ovl_now(ovl_iv), .ovr_set(ovr_set),"),
    ("最上位：空の語の OVL を間隔の印から取る", "eeg_digital_top.sv",
     ".empty_status({1'b0, dflag_overrun, ovl_now, 1'b0, alert, 3'b000})", ".empty_status({1'b0, dflag_overrun, ovl_iv, 1'b0, alert, 3'b000})"),
    ("レジスタ：RESET_FLAG を ALERT から隠せない", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag & r_mask_d);",
     "assign alert       = |(err & r_mask) || |(dflag & r_mask_d) || err[ERR_RESET_FLAG_LSB];"),
    ("最上位：RAW を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "eeg_raw u_raw (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_raw u_raw (.clk(MCLK), .rst_n(rst_n),"),
    ("最上位：SOFT_RESET の確定のサイクルに DRDY_N を High にするのはレベルのモードのみ", "eeg_digital_top.sv",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= drdy_mode ? ~drdy_pulse : (soft_req ? 1'b1 : ~fifo_nonempty);"),
    ("最上位：SEQ を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n)    seq_cnt <= 16'd0;",
     "    always_ff @(posedge MCLK or negedge rst_n) begin\n        if (!rst_n)       seq_cnt <= 16'd0;"),
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
    # audit round 4, auditor C: cfg_ok / nr_ok against regmap over the full 10-bit M
    ("レジスタ：nr_ok の 1 段を M[7:0] だけで計算", "eeg_regs.sv",
     "    assign sv_s   = s_sign ? -$signed({2'b00, s_m}) : $signed({2'b00, s_m});\n    assign sv_a   = a_sign ? -$signed({2'b00, a_m}) : $signed({2'b00, a_m});",
     "    assign sv_s   = s_sign ? -$signed({4'b0000, s_m[7:0]}) : $signed({4'b0000, s_m[7:0]});\n    assign sv_a   = a_sign ? -$signed({4'b0000, a_m[7:0]}) : $signed({4'b0000, a_m[7:0]});"),
    ("レジスタ：nr_ok が M[9:8] の一致も求める", "eeg_regs.sv",
     "assign nr_ok  = (s_range == a_range) &&", "assign nr_ok  = (s_range == a_range) && (s_m[9:8] == a_m[9:8]) &&"),
    ("レジスタ：nr_ok が CPF_TRIM の変化を見ない", "eeg_regs.sv", "(s_cpf == a_cpf) && ", ""),
    ("レジスタ：cfg_ok が範囲の上限を拒否", "eeg_regs.sv",
     "assign cfg_ok = (s_m <= range_max_m(s_range));", "assign cfg_ok = (s_m < range_max_m(s_range));"),
    # audit round 5, auditor C: the command's acknowledge cycle
    ("レジスタ：確認のサイクルに書いた命令を失う", "eeg_regs.sv", "            if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end else if (cmd_ack) begin\n                pend  <= 1'b0;\n            end", "            if (cmd_ack) begin\n                pend  <= 1'b0;\n            end else if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end"),
    ("レジスタ：確認のサイクルのシャドウの書き込みを拒否", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin", "end else if (pend && GUARDED_ADDRS[addr]) begin"),
    ("レジスタ：確認のサイクルの命令を拒否", "eeg_regs.sv",
     "end else if (pend && !cmd_ack) begin", "end else if (pend) begin"),
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


# CHOP1 alone (rtl/tb/tb_chop1.sv with the r14 eeg_clkgen: a reference from a count of MCLK edges; audit round 4,
# auditor A: the 1 ms rate boundary on the output grid was not checked by the r14 tests)
CHOP1_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("CHOP1：フレームの数の初期値が 511（1 ms の境界が出力の格子から 512 フレームずれる）", "eeg_chop1.sv",
     "fcnt   <= 10'h3FF;", "fcnt   <= 10'h1FF;"),
    ("CHOP1：速さを 1 ms の境界でなく毎フレーム取り込む", "eeg_chop1.sv",
     "if (fcnt == 10'h3FF) begin", "if (1'b1) begin"),
    ("CHOP1：e16 でなく e17 で変える", "eeg_chop1.sv",
     "if (cycle == 5'd15) begin     // this edge is e16", "if (cycle == 5'd16) begin     // this edge is e16"),
]

# the rounding and saturation of the CIC output (rtl/eeg_rnd_sat.sv) alone, against the Python golden model
RND_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("丸め：同値を切り上げる（偶数への丸めでない）", "eeg_rnd_sat.sv",
     "assign up   = (r > HALF) || ((r == HALF) && q[0]);", "assign up   = (r >= HALF);"),
    ("飽和：正と負の飽和の入れ違い", "eeg_rnd_sat.sv",
     "assign dout = fits ? qr[WO-1:0] : (qr[WQ] ? MAXNEG : MAXPOS);",
     "assign dout = fits ? qr[WO-1:0] : (qr[WQ] ? MAXPOS : MAXNEG);"),
]

# the structure (NFR-06: every output a flip-flop's), which no functional bench can see
STRUCT_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("最上位：DRDY_N を組み合わせ回路で出す", "eeg_digital_top.sv",
     "    assign DRDY_N = drdy_n_q;", "    assign DRDY_N = drdy_mode ? ~drdy_pulse : ~fifo_nonempty;"),
    ("最上位：AFE_RST を状態の復号で出す", "eeg_digital_top.sv",
     "    assign AFE_RST = seq_afe_rst;",
     "    assign AFE_RST = (seq_state == ST_IDLE) || (seq_state == ST_WARMUP) || (seq_state == ST_PULSE);"),
]

# the overload detector alone (tb_ovl + check_ovl.py against regmap.OVL_RULE: detector, hits, interval flags)
OVL_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("過負荷：間隔の印に検出の尾を含める（旧い規則）", "eeg_ovl.sv",
     "if (out_stb)      ovl_seen <= 1'b0;", "if (out_stb)      ovl_seen <= ovl_now;"),
    ("過負荷：両端の符号でなくても検出の間は印を付ける", "eeg_ovl.sv",
     "assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);", "assign ovl_hit = en && (cnt_nxt >= OVL_THRESHOLD);"),
    ("過負荷：この符号を数える前の値で判定（検出が 1 フレーム遅れる）", "eeg_ovl.sv",
     "assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);", "assign ovl_hit = en && ext && (cnt >= OVL_THRESHOLD);"),
]

TAG = dict(spi="s", seq="q", fifo="f", regs="r", chop1="c", rnd="n", struct="g", ovl="v")
GROUPS = ("top", "spi", "seq", "fifo", "regs", "chop1", "rnd", "struct", "ovl")


def run(i, m, bench="top"):
    name, f, old, new = m
    d = os.path.join(BUILD, "mut", "b00" if i < 0 else f"{TAG.get(bench, 'm')}{i:02d}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "build"))
    for s in SRC:
        shutil.copy(os.path.join(R14, s), d)
    for s in OLD:                                    # the blocks kept from r13 (rtl/), copied so they can be mutated
        shutil.copy(os.path.join(RTL_OLD, s), d)
    if f is not None:
        p = os.path.join(d, f)
        text = open(p, encoding="utf-8").read()
        if text.count(old) != 1:
            return i, name, "NOT APPLIED", f"the text occurs {text.count(old)} times in {f}"
        open(p, "w", encoding="utf-8").write(text.replace(old, new))
    for x in ("top_r14.codes", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes", "ovl.split"):   # shared generated files
        os.symlink(os.path.join(BUILD, x), os.path.join(d, "build", x))
    tb = {"spi": "tb_spi_r14.sv", "seq": "tb_seq.sv", "fifo": "tb_fifo.sv", "regs": "tb_regs.sv",
          "ovl": "tb_ovl.sv"}.get(bench, "tb_top_r14.sv")
    if bench == "struct":                            # the structure: yosys on this copy
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_outputs_registered.py"), d], capture_output=True,
                           text=True)
        if k.returncode == 2 or k.returncode not in (0, 1):      # the tool did not run: no verdict (audit round 6)
            return i, name, "TOOL ERROR", (k.stdout.strip().splitlines() or ["no output"])[-1][:150]
        passed = k.returncode == 0 and "PASS" in k.stdout
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  ") or ln.startswith("FAIL")), "")
        if f is None:
            return i, name, ("baseline ok" if passed else "BASELINE FAILS"), first
        return i, name, ("detected" if not passed else "MISSED"), first
    tbp = {"chop1": os.path.join(RTL_OLD, "tb", "tb_chop1.sv"),
           "rnd": os.path.join(RTL_OLD, "tb", "tb_rnd_sat.sv")}.get(bench, os.path.join(R14, "tb", tb))
    srcs = ({"seq": ["eeg_seq.sv"], "fifo": ["eeg_fifo.sv"], "regs": ["eeg_regs.sv"],
             "chop1": ["eeg_clkgen.sv", "eeg_chop1.sv"], "rnd": ["eeg_rnd_sat.sv"], "ovl": ["eeg_ovl.sv"]}.get(bench)
            or SRC + OLD)                            # pin_tests.svh: through -I build
    cmd = (["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", BUILD, "-o", "build/t.vvp"] + srcs
           + [tbp])
    c = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if c.returncode:
        return i, name, "COMPILE ERROR", c.stderr.strip().splitlines()[-1][:150]
    if bench in ("seq", "spi", "fifo"):
        args = {"seq": ["+n=600000", "+seed=11", "+trace=build/seq_trace.txt"], "spi": ["+n=1500", "+seed=5"],
                "fifo": ["+n=400000", "+trace=build/fifo_trace.txt"]}[bench]   # as run_tests_r14.sh (audit round 6)
        try:
            v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp"] + args, cwd=d, capture_output=True,
                               text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 3600 s (undecided: rerun)"
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
    if bench == "ovl":
        try:
            subprocess.run(["vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 1200 s (undecided: rerun)"
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_ovl.py"), os.path.join(d, "build")],
                           capture_output=True, text=True)
        passed = k.returncode == 0
        first = (k.stdout.strip().splitlines() or ["no output"])[0][:150]
        if f is None:
            return i, name, ("baseline ok" if passed else "BASELINE FAILS"), first
        return i, name, ("detected" if not passed else "MISSED"), first
    if bench in ("chop1", "rnd"):
        try:
            v = subprocess.run(["vvp", "-n", "build/t.vvp"] + (["+vec=build/rnd_sat.vec"] if bench == "rnd" else []),
                               cwd=d, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 1200 s (undecided: rerun)"
        passed = ("PASS: chop1" if bench == "chop1" else "PASS: tb_rnd_sat") in v.stdout and "FAIL" not in v.stdout
        first = next((ln for ln in v.stdout.splitlines() if ln.startswith(("ERROR", "FAIL"))), "")
        if f is None:
            return i, name, ("baseline ok" if passed else "BASELINE FAILS"), first
        return i, name, ("detected" if not passed else "MISSED"), first
    if bench == "regs":
        try:
            v = subprocess.run(["vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 600 s (undecided: rerun)"
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
        failed = "FAIL" in v.stdout                  # e.g. the bench's watchdog (the trace then ends early)
        if f is None:                                # the baseline also covers every branch, as in the runner
            covered = "every branch covered" in k.stdout
            return i, name, ("baseline ok" if nbad == 0 and nt == 0 and not failed and covered else "BASELINE FAILS"), head
        return i, name, ("detected" if nbad != 0 or nt != 0 or failed else "MISSED"), first
    try:                                             # the bench's own watchdog (600 ms simulated) ends a hang
        v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True,
                           timeout=5400)
    except subprocess.TimeoutExpired:
        return i, name, "TIMEOUT", "no end within 5400 s (undecided: rerun)"
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
    k2 = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_trace.py"),
                         os.path.join(d, "build", "top_seq_trace.txt"), "--no-cover"], capture_output=True, text=True)
    seq_pass = k2.returncode == 0
    first = next((ln for ln in out.splitlines() if ln.startswith(("ERROR", "SPI ERROR", "FAIL"))), "")
    if tb_pass and not gold_pass:
        first = "check_top_r14: " + next((ln for ln in k.stdout.splitlines() if "mismatch" in ln), "FAIL")
    elif tb_pass and not seq_pass:
        first = "check_seq_trace: " + next((ln.strip() for ln in k2.stdout.splitlines() if ln.startswith("  line")), "FAIL")
    return i, name, ("detected" if not (tb_pass and gold_pass and seq_pass) else "MISSED"), first


def main():
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 2
    for need in ("top_r14.codes", "reg_tests.svh", "pin_tests.svh", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes",
                 "ovl.split"):
        if not os.path.exists(os.path.join(BUILD, need)):
            sys.exit(f"build/{need} missing: run run_tests_r14.sh first")
    # every listed mutation must apply to the RTL as it is now (audit round 5: two targets had changed with the RTL
    # and would have shown only as NOT APPLIED at the end of a long run)
    stale = []
    for g, lst in (("top", MUTATIONS), ("spi", SPI_MUTATIONS), ("seq", SEQ_MUTATIONS), ("fifo", FIFO_MUTATIONS),
                   ("regs", REGS_MUTATIONS), ("chop1", CHOP1_MUTATIONS), ("rnd", RND_MUTATIONS),
                   ("struct", STRUCT_MUTATIONS), ("ovl", OVL_MUTATIONS)):
        for i, (name, f, old, _new) in enumerate(lst):
            if f is not None:
                src = os.path.join(R14 if f in SRC else RTL_OLD, f)
                if open(src, encoding="utf-8").read().count(old) != 1:
                    stale.append(f"{TAG.get(g, 'm')}{i:02d} {name} ({f})")
    if stale:
        sys.exit("mutations whose text does not occur exactly once in the RTL (update them first):\n  " + "\n  ".join(stale))
    which = next((w for w in GROUPS if f"--{w}" in sys.argv), "all")
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
    if which in ("chop1", "all"):
        tasks += [(i, m, "chop1") for i, m in enumerate(CHOP1_MUTATIONS)]
    if which in ("rnd", "all"):
        tasks += [(i, m, "rnd") for i, m in enumerate(RND_MUTATIONS)]
    if which in ("struct", "all"):
        tasks += [(i, m, "struct") for i, m in enumerate(STRUCT_MUTATIONS)]
    if which in ("ovl", "all"):
        tasks += [(i, m, "ovl") for i, m in enumerate(OVL_MUTATIONS)]
    if only:
        tasks = [t for t in tasks if ("b00" if t[0] < 0 else f"{TAG.get(t[2], 'm')}{t[0]:02d}") in only]
    import datetime
    import threading
    t0 = datetime.datetime.now()
    log = os.path.join(BUILD, f"mutate_{t0:%Y%m%d-%H%M%S}.log")    # every run keeps its record (audit rounds 4, 5)
    lock = threading.Lock()
    def tool(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=R14)
            return ((r.stdout or r.stderr).strip().splitlines() or ["?"])[0]
        except OSError as ex:
            return f"not found ({ex})"
    env = (f"commit {tool(['git', 'rev-parse', '--short', 'HEAD'])}"
           f"{' (with uncommitted changes)' if tool(['git', 'status', '--porcelain', '--', '.', '../rtl']) not in ('?', '') else ''}; "
           f"python {sys.version.split()[0]}; {tool(['iverilog', '-V'])}; yosys {os.environ.get('YOSYS', 'default path')}")
    with open(log, "w", encoding="utf-8") as fo:           # written as the results arrive: an interrupted run
        fo.write(f"mutate_top_r14.py {' '.join(sys.argv[1:])}: started {t0:%Y-%m-%d %H:%M:%S}, "   # keeps what it did
                 f"{len(tasks)} runs (results in the order they end; the summary follows at the end)\n{env}\n")

    def run_logged(a):
        r = (a[2],) + run(*a)
        tag = "b00" if r[1] < 0 else f"{TAG.get(r[0], 'm')}{r[1]:02d}"
        with lock, open(log, "a", encoding="utf-8") as fo:
            fo.write(f"{datetime.datetime.now():%H:%M:%S} {r[3]:8s} {tag} {r[2]}" + (f"  ({r[4][:120]})" if r[4] else "") + "\n")
        return r
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(run_logged, tasks))
    ok = True
    out = [f"--- summary ({(datetime.datetime.now() - t0).total_seconds() / 60:.1f} min)"]
    missing_base = []
    title = {"top": "tb_top_r14", "spi": "tb_spi_r14 + check_spi_trace", "seq": "tb_seq + check_seq_trace (timer modelled)",
             "fifo": "tb_fifo + check_fifo_trace (fsm_spec.fifo_step and identities)",
             "regs": "tb_regs (W1C: the set wins; cfg_ok / nr_ok == regmap)",
             "chop1": "tb_chop1 (r14 eeg_clkgen; MCLK-count reference)", "rnd": "tb_rnd_sat (Python golden vectors)",
             "struct": "check_outputs_registered (every output a flip-flop's, yosys)",
             "ovl": "tb_ovl + check_ovl (regmap.OVL_RULE: detector, hits, interval flags)"}
    for bench in GROUPS:
        rs = sorted(r for r in res if r[0] == bench)
        if not rs:
            continue
        out.append(f"--- {title[bench]}")
        for _, i, name, verdict, first in rs:
            tag = "b00" if i < 0 else f"{TAG.get(bench, 'm')}{i:02d}"
            out.append(f"{verdict:8s} {tag} {name}" + (f"  ({first[:120]})" if first else ""))
        base = [r for r in rs if (r[1] < 0 if bench == "top" else r[1] == 0)]       # b00, or the group's 00
        muts = [r for r in rs if r not in base]
        n_det = sum(1 for r in muts if r[3] == "detected")
        n_to = sum(1 for r in rs if r[3] == "TIMEOUT")
        base_txt = ("not run" if not base else
                    "clean" if all(r[3] == "baseline ok" for r in base) else "NOT clean")
        out.append(f"{n_det} of {len(muts)} mutations detected; baseline {base_txt}"
                   + (f"; {n_to} undecided (TIMEOUT)" if n_to else ""))
        ok &= n_det == len(muts) and base_txt != "NOT clean" and not n_to
        if base_txt == "not run":
            missing_base.append(bench)
    out.append("FAIL" if not ok else ("INCOMPLETE (baselines not run: " + ", ".join(missing_base) + ")")
               if missing_base else "PASS")
    ok &= not missing_base
    with open(log, "a", encoding="utf-8") as fo:
        fo.write("\n".join(out) + "\n")
    print("\n".join(out[:-1]))
    print("report written to " + os.path.relpath(log, R14))
    print(out[-1])
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
