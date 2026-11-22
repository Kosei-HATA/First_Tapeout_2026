#!/usr/bin/env python3
"""Mutation self-test of the r14 testbenches (11/19, extended by the audits of 11/20): each listed RTL error, put in on
purpose into a copy of the r14 RTL (and of the blocks kept from rtl/), must be detected, and each bench's unmutated
baseline must pass. The groups and their benches:
  top    MUTATIONS          tb_top_r14 + check_top_r14.py (golden CIC); baseline b00 also replays the sequencer trace
                            (the 8-deep FIFO); before it, tb_tick and tb_clkgen for an edit of eeg_clkgen.sv and
                            tb_cic_arm for eeg_cic3.sv (all three for b00; audit round 22), tb_chop1 for an edit
                            of eeg_chop1.sv or eeg_clkgen.sv (and b00; audit round 27). tb_top_r14 with the
                            4-deep FIFO (-DFIFO4, about 6 minutes a run) for b00 and for the mutants whose edits
                            name DEPTH or edit eeg_fifo.sv: the depth reaches eeg_fifo and, through FIFO_DEPTH,
                            eeg_regs's CAPS (audit round 26, auditor C: "the depth is eeg_fifo's alone" was false,
                            and CAPS fixed at 8 was MISSED; round 27: an edit breaking only the 4-deep FIFO);
                            eeg_fifo's own mutants run tb_fifo and tb_fifo4 in the fifo group
  spi    SPI_MUTATIONS      tb_spi_r14 + check_spi_trace.py (as run_tests_r14.sh: +n=1500 +seed=5; the baseline must
                            also cover every branch)
  seq    SEQ_MUTATIONS      tb_seq + check_seq_trace.py (the timer modelled independently), then tb_seq_exh +
                            check_seq_exh.py (every state value, event, command and condition for one step;
                            audit round 22: the random walk took its rarest branch once)
  fifo   FIFO_MUTATIONS     tb_fifo and tb_fifo4 (-DDEPTH4) + check_fifo_trace.py (fsm_spec.fifo_step and an
                            identity model; audit round 22)
  regs   REGS_MUTATIONS     tb_regs (W1C; cfg_ok / nr_ok against regmap over build/ok_vectors.txt)
  chop1  CHOP1_MUTATIONS    rtl/tb/tb_chop1.sv with the r14 clock generator
  rnd    RND_MUTATIONS      rtl/tb/tb_rnd_sat.sv (build/rnd_sat.vec from rtl/model/gen_vectors.py)
  struct STRUCT_MUTATIONS   check_outputs_registered.py (yosys: every output a flip-flop's, NFR-06; the
                            synchronizers; the resets, RST-01; one clock, RST-05 since audit round 27)
Each mutation runs in build/mut/<tag>/ (its own copy of the RTL and its own logs); the generated files (build/
reg_tests.svh, pin_tests.svh, top_r14.codes, ok_vectors.txt, rnd_sat.vec) are shared and made afresh at the start
(as run_tests_r14.sh makes them; audit round 16). Every run's report (also with --only) is printed and written to build/mutate_<date-time>.log with its
arguments, so a recorded result always has its log (audit round 4).
Verdicts: detected / MISSED for a mutation, baseline ok / BASELINE FAILS for a baseline. A run without a verdict fails
the whole run (audit rounds 5, 6, 9): NOT APPLIED (the text is not in the RTL), COMPILE ERROR, TIMEOUT (undecided),
SIM ERROR (the bench ended without its closing line: a crash is no detection), CHECKER ERROR (a checker ended without
its PASS / FAIL line and nothing else judged the mutant), TOOL ERROR (yosys did not run). --only with a tag that is
not in the selected groups, or a selection with nothing to run, is a FAIL.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/mutate_top_r14.py [-j N]
       [--top | --spi | --seq | --fifo | --regs | --chop1 | --rnd | --struct | --ovl] [--only m03,s11,q02]
"""
import concurrent.futures as cf
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_outputs_registered import YOSYS  # noqa: E402  (the same yosys as the structural check, for the record)
R14 = os.path.normpath(os.path.join(HERE, ".."))
RTL_OLD = os.path.normpath(os.path.join(R14, "..", "rtl"))
SPEC = os.path.join(RTL_OLD, "spec")
BUILD = os.path.join(R14, "build")
SRC = ["eeg_digital_top.sv", "eeg_seq.sv", "eeg_regs.sv", "eeg_spi_slave.sv", "eeg_fifo.sv", "eeg_ovl.sv",
       "eeg_cic3.sv", "eeg_clkgen.sv"]
OLD = ["eeg_chop1.sv", "eeg_raw.sv", "eeg_rnd_sat.sv"]
# the shared generated inputs: copied into each run and checked against their hash at the start of the run (audit
# round 22, auditor C: symlinks to files that run_tests_r14.sh rewrites non-atomically could give a run a truncated
# input, a false detection)
SHARED = ("top_r14.codes", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes", "ovl.split", "reg_tests.svh", "pin_tests.svh",
          "plain_writes.txt")                       # tb_regs's locked writes (audit round 29)
SHARED_SHA = {}


def run_version():
    """(the record's version text, a function giving the files that differ from that version, or None). Audit round
    25, auditor C: run_fullmut_r14.sh's copy lies in the checkout's git-ignored build/, so git answered for the
    checkout (its HEAD, its changes): another version's run would record the wrong commit, and edits inside the copy
    never showed. In the tracked checkout: git's HEAD and whether rtl_r14 or rtl differ from it. In a copy: the
    version run_fullmut_r14.sh wrote to FULLRUN_VERSION (the commit, then the repository), every file of the
    version's rtl and rtl_r14 compared with the copy's (git ls-tree against git hash-object), at the start and the
    end. Any other copy: "version unknown"."""
    def git(*a, cwd=R14, inp=None):
        try:
            return subprocess.run(['git', *a], cwd=cwd, input=inp, capture_output=True, text=True)
        except OSError:
            return None
    t = git('ls-files', '--error-unmatch', 'tb/mutate_top_r14.py')
    if t is not None and t.returncode == 0:          # the checkout itself
        h = git('rev-parse', '--short', 'HEAD')
        s = git('status', '--porcelain', '--', '.', '../rtl')
        head = h.stdout.strip() if h is not None and h.returncode == 0 else 'unknown'
        dirty = s is not None and s.returncode == 0 and s.stdout.strip() != ''
        # the sources at the start, compared at the end (audit round 27, auditor C: every mutant copies the RTL when
        # it starts and compiles tb/ and rtl/spec/ in place, so an edit during a checkout run mixed versions under one
        # recorded commit)
        snap = checkout_sources()
        def changed():
            now = checkout_sources()
            return sorted(p for p in set(snap) | set(now) if snap.get(p) != now.get(p))
        return f"commit {head}{' (with uncommitted changes)' if dirty else ''} (the checkout)", changed
    vf = os.path.join(R14, 'FULLRUN_VERSION')
    try:
        commit, repo = open(vf, encoding='utf-8').read().split()[:2]
    except (OSError, ValueError):
        return "version unknown (a copy without FULLRUN_VERSION: run run_fullmut_r14.sh, or run in the checkout)", None
    root = os.path.normpath(os.path.join(R14, '..', '..', '..'))
    def differ():
        ls = git('-C', repo, 'ls-tree', '-r', commit, '--', 'gf180/tapeout/rtl', 'gf180/tapeout/rtl_r14')
        if ls is None or ls.returncode != 0 or not ls.stdout.strip():
            return [f"git ls-tree of {commit} in {repo} failed"]
        ents = [(ln.split('\t', 1)[0].split(), ln.split('\t', 1)[1]) for ln in ls.stdout.splitlines()]
        bad = [p for (mode, typ, _), p in ents if typ != 'blob' or mode not in ('100644', '100755')]
        blobs = [(sha, p) for (mode, typ, sha), p in ents if typ == 'blob' and mode in ('100644', '100755')]
        bad += [p + ' (missing)' for _, p in blobs if not os.path.isfile(os.path.join(root, p))]
        have = [(sha, p) for sha, p in blobs if os.path.isfile(os.path.join(root, p))]
        # absolute paths (audit round 28: the copy lies in the checkout's git-ignored build/, so git finds the checkout's
        # repository and reads --stdin-paths from its top level; every relative path failed, "git hash-object failed",
        # and the check had never worked in a copy)
        hs = git('hash-object', '--no-filters', '--stdin-paths', cwd=root,
                 inp=''.join(os.path.join(root, p) + '\n' for _, p in have))
        got = hs.stdout.split() if hs is not None and hs.returncode == 0 else []
        if len(got) != len(have):
            return bad + ['git hash-object failed: ' + ((hs.stderr.strip().splitlines() or ['?'])[-1] if hs is not None
                                                        else 'git not run')[:120]]
        return bad + [p for (sha, p), g in zip(have, got) if g != sha]
    d0 = differ()
    if d0:
        return (f"commit {commit[:8]} (run_fullmut_r14.sh's copy), BUT ITS FILES DIFFER FROM THAT VERSION: "
                + ", ".join(d0[:8])), differ
    return f"commit {commit[:8]} (run_fullmut_r14.sh's copy; its rtl and rtl_r14 files equal that version's)", differ


def source_stamps():
    """(mtime in ns, size) of every file under rtl_r14 and rtl, as checkout_sources lists them (audit round 28,
    auditor C: the run compared the sources only at its start and its end, so an edit made and reverted during the
    run, which a mutant's compile of tb/ or rtl/spec/ could take, still mixed versions under one record): checked
    at every mutant's start and end against the run's start; any file touched, even back to its old content, makes
    that mutant's verdict a TOOL ERROR"""
    out = {}
    for top in (R14, RTL_OLD):
        for dp, dn, fn in os.walk(top):
            dn[:] = [x for x in dn if x not in ("build", "__pycache__") and not x.startswith(".")]
            for x in fn:
                p = os.path.join(dp, x)
                if os.path.isfile(p) and not os.path.islink(p):
                    st = os.stat(p)
                    out[os.path.relpath(p, os.path.dirname(R14))] = (st.st_mtime_ns, st.st_size)
    return out


def checkout_sources():
    """SHA-256 of every file under rtl_r14 and rtl, their build/ folders left out (audit round 27, auditor C)"""
    out = {}
    for top in (R14, RTL_OLD):
        for dp, dn, fn in os.walk(top):
            dn[:] = [x for x in dn if x not in ("build", "__pycache__") and not x.startswith(".")]
            for x in fn:
                p = os.path.join(dp, x)
                if os.path.isfile(p) and not os.path.islink(p):
                    out[os.path.relpath(p, os.path.dirname(R14))] = sha256_file(p)
    return out


def sha256_file(p):
    with open(p, "rb") as fo:
        return hashlib.sha256(fo.read()).hexdigest()

# (name, file, text in the RTL (must occur exactly once), replacement); a mutation of several edits (audit round 15:
# a RESET_N-only reset port in eeg_regs and its wiring in the top): (name, [(file, text, replacement), ...], None, None),
# applied in order, each text occurring exactly once when its turn comes
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
     "status_byte[STATUS_MARK0_LSB]       = STATUS_MARK0_RST;", "status_byte[STATUS_MARK0_LSB]       = 1'b1;"),
    ("レジスタ：DFLAG を W1C で消せない", "eeg_regs.sv",
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n                                                                : 2'b00)) | {ovl_set, ovr_set};",
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
     "smp_status[SMP_OVERRUN_LSB] = dflag_overrun;", "smp_status[SMP_OVERRUN_LSB] = 1'b0;"),
    ("クロック：tick が 1 サイクル早い（サイクル 23）", "eeg_clkgen.sv",
     "tick       <= (cnt_nxt[4:0] == TICK_CYCLE) &&", "tick       <= (cnt_nxt[4:0] == TICK_CYCLE - 5'd1) &&"),
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
     "smp_status[SMP_OVL_LSB]     = ovl_iv | ovl_hist[0] | ovl_hist[1];", "smp_status[SMP_OVL_LSB]     = ovl_iv;"),
    ("最上位：CHANGED の長さに T_ELEC を足さない", "eeg_digital_top.sv",
     "assign chg_new = 9'd3 + {1'b0, t_elec};", "assign chg_new = 9'd3;"),
    ("最上位：IDLE の過負荷でも DFLAG.OVL を立てる", "eeg_digital_top.sv",
     ".ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),", ".ovl_set(ovl_hit),"),
    ("レジスタ：未処理の命令がある間もシャドウとタイマへ書く", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin", "end else if (1'b0) begin"),
    ("レジスタ：STATUS の CMD_PENDING が 0 のまま", "eeg_regs.sv",
     "status_byte[STATUS_CMD_PENDING_LSB] = pend;", "status_byte[STATUS_CMD_PENDING_LSB] = 1'b0;"),
    ("レジスタ：STATUS の DATA が 0 のまま", "eeg_regs.sv",
     "status_byte[STATUS_DATA_LSB]        = fifo_nonempty;", "status_byte[STATUS_DATA_LSB]        = 1'b0;"),
    ("レジスタ：STATUS の OVL_NOW が 0 のまま", "eeg_regs.sv",
     "status_byte[STATUS_OVL_NOW_LSB]     = ovl_now;", "status_byte[STATUS_OVL_NOW_LSB]     = 1'b0;"),
    ("レジスタ：STATUS の AFE_RST が 1 のまま", "eeg_regs.sv",
     "status_byte[STATUS_AFE_RST_LSB]     = afe_rst;", "status_byte[STATUS_AFE_RST_LSB]     = 1'b1;"),
    ("SPI：CRC 有効時の CRC のない読み出しと短いサンプルを通す", "eeg_spi_slave.sv",
     "(crc_en && (st == S_RCRC || st == S_RSMP)) || st > S_OVF) begin", "st > S_OVF) begin"),
    ("最上位：RUN を出ても CHANGED の残りを消さない", "eeg_digital_top.sv",
     "else if (seq_state != ST_RUN) chg_cnt <= 9'd0;", "else if (1'b0)                chg_cnt <= 9'd0;"),
    # audit round 2 (11/20)
    ("最上位：新しい印が長い残りを短く上書きする", "eeg_digital_top.sv",
     "chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : chg_new;", "chg_cnt <= chg_new;"),
    ("最上位：サンプルの ERR が 0 のまま", "eeg_digital_top.sv",
     "smp_status[SMP_ERR_LSB]     = alert;", "smp_status[SMP_ERR_LSB]     = 1'b0;"),
    ("最上位：サンプルの予約ビットが 0 でない", "eeg_digital_top.sv",
     "smp_status                  = 8'h00;", "smp_status                  = 8'h04;"),
    ("最上位：空の語の状態が 0x00", "eeg_digital_top.sv",
     "empty_status[SMP_OVERRUN_LSB] = dflag_overrun;\n        empty_status[SMP_OVL_LSB]     = ovl_now;\n        empty_status[SMP_ERR_LSB]     = alert;",
     "// the empty word's flags left out"),
    ("レジスタ：ALERT がマスクを無視する", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);", "assign alert       = |err || |dflag_byte;"),
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
     "A_STATE:          begin rdata = 8'h00; rdata[STATE_STATE_LSB +: STATE_STATE_W] = state; end",
     "A_STATE:          begin rdata = 8'h00; rdata[STATE_STATE_LSB +: 3] = state[2:0]; end"),
    ("最上位：DRDY_N のパルスを捨てた出力にも出す", "eeg_digital_top.sv",
     "assign drdy_nxt = push_ok ? 3'd4 :", "assign drdy_nxt = seq_store ? 3'd4 :"),
    ("最上位：CHOP_EN が ADC_ZERO でも 0", "eeg_digital_top.sv",
     "assign CHOP_EN    = ~a_cstop;", "assign CHOP_EN    = ~a_cstop & ~a_azero;"),
    ("最上位：空の語の OVERRUN が 0", "eeg_digital_top.sv",
     "empty_status[SMP_OVERRUN_LSB] = dflag_overrun;", "empty_status[SMP_OVERRUN_LSB] = 1'b0;"),
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
     "status_byte[STATUS_READY_LSB]       = (state == ST_RUN);", "status_byte[STATUS_READY_LSB]       = (state >= ST_RUN);"),
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
     "assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);",
     "assign alert       = |(err[3:0] & r_mask[3:0]) || |(dflag_byte & mask_d_byte);"),
    ("レジスタ：ALERT が OVERRUN を含まない", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);",
     "assign alert       = |(err & r_mask) || (dflag_byte[DFLAG_OVL_LSB] & mask_d_byte[DFLAG_OVL_LSB]);"),
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
     "status_byte[STATUS_READY_LSB]       = (state == ST_RUN);", "status_byte[STATUS_READY_LSB]       = (state == ST_RUN) || (state == ST_FILL);"),
    ("最上位：STATUS の OVL_NOW が次の出力まで残る", "eeg_digital_top.sv",
     ".ovl_now(ovl_now), .ovr_set(ovr_set),", ".ovl_now(ovl_iv), .ovr_set(ovr_set),"),
    ("最上位：空の語の OVL を間隔の印から取る", "eeg_digital_top.sv",
     "empty_status[SMP_OVL_LSB]     = ovl_now;", "empty_status[SMP_OVL_LSB]     = ovl_iv;"),
    ("レジスタ：RESET_FLAG を ALERT から隠せない", "eeg_regs.sv",
     "assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);",
     "assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte) || err[ERR_RESET_FLAG_LSB];"),
    ("最上位：RAW を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "eeg_raw u_raw (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_raw u_raw (.clk(MCLK), .rst_n(rst_n),"),
    ("最上位：SOFT_RESET の確定のサイクルに DRDY_N を High にするのはレベルのモードのみ", "eeg_digital_top.sv",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= drdy_mode ? ~drdy_pulse : (soft_req ? 1'b1 : ~fifo_nonempty);"),
    ("最上位：SEQ を SOFT_RESET で戻す", "eeg_digital_top.sv",
     "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n)    seq_cnt <= 16'd0;",
     "    always_ff @(posedge MCLK or negedge rst_n) begin\n        if (!rst_n)       seq_cnt <= 16'd0;"),
    # audit round 7, auditor C (each passed all 16 groups before the round's additions) and the SEQ count
    ("レジスタ：FIFO_LEVEL の最上位のビットを落とす（満杯の 8 段が 0 と読める）", "eeg_regs.sv",
     "A_FIFO_LEVEL:     begin rdata = 8'h00; rdata[FIFO_LEVEL_LEVEL_LSB +: FIFO_LEVEL_LEVEL_W] = fifo_level; end",
     "A_FIFO_LEVEL:     begin rdata = 8'h00; rdata[FIFO_LEVEL_LEVEL_LSB +: 3] = fifo_level[2:0]; end"),
    ("レジスタ：未処理の命令の間も OFF_M_H を書ける（ガードの漏れ）", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr] && (addr != A_OFF_M_H)) begin"),
    ("レジスタ：TEST_CTRL を鍵なしで書ける", "eeg_regs.sv",
     "A_TEST_MUX, A_TEST_CTRL, A_DEBUG: wr_locked = !unlocked;", "A_TEST_MUX, A_DEBUG: wr_locked = !unlocked;"),
    ("最上位：SEQ を RUN の出力の時刻だけ数える", "eeg_digital_top.sv",
     "else if (cic_stb) seq_cnt <= seq_cnt + 16'd1;", "else if (cic_stb && (seq_state == ST_RUN)) seq_cnt <= seq_cnt + 16'd1;"),
    # audit round 8, auditor C (each passed all 16 groups)
    ('レジスタ：範囲の検査を未処理の命令のガードより先に（範囲外の書き込みが RANGE_ERR）', 'eeg_regs.sv',
     "            end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin\n                ev_err[ERR_STATE_ERR_LSB] = 1'b1;                // no write between a command and its tick\n            end else if (wr_range_bad) begin\n                ev_err[ERR_RANGE_ERR_LSB] = 1'b1;\n",
     "            end else if (wr_range_bad) begin\n                ev_err[ERR_RANGE_ERR_LSB] = 1'b1;\n            end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin\n                ev_err[ERR_STATE_ERR_LSB] = 1'b1;                // no write between a command and its tick\n"),
    ('レジスタ：施錠の検査を未処理の命令のガードより後に（施錠の書き込みが STATE_ERR）', 'eeg_regs.sv',
     "            if (!wr_def || wr_ro || wr_locked) begin\n                ev_err[ERR_ADDR_ERR_LSB] = 1'b1;\n            end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin\n                ev_err[ERR_STATE_ERR_LSB] = 1'b1;                // no write between a command and its tick\n",
     "            if (!wr_def || wr_ro) begin\n                ev_err[ERR_ADDR_ERR_LSB] = 1'b1;\n            end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin\n                ev_err[ERR_STATE_ERR_LSB] = 1'b1;                // no write between a command and its tick\n            end else if (wr_locked) begin\n                ev_err[ERR_ADDR_ERR_LSB] = 1'b1;\n"),
    ('最上位：空の語の CHANGED を印の残りから取る', 'eeg_digital_top.sv',
     'empty_status[SMP_ERR_LSB]     = alert;',
     'empty_status[SMP_ERR_LSB]     = alert;\n        empty_status[SMP_CHANGED_LSB] = chg_now;'),
    ('RAW：止めていても語を読み込む（RAW_DATA が動く）', 'eeg_raw.sv',
     "sh <= raw_en ? {3'b101, code} : 8'h00;",
     "sh <= {3'b101, code};"),
    # audit round 9, auditor C: errors that passed every test (the bench now checks the control reset's length, drives
    # CODE so that it changes at e2, after the TH capture, checks the RAW word's load and clock cycles, and phase V
    # takes APPLY and APPLY_NR in every running state)
    ("最上位：SOFT_RESET の制御のリセットが 1 MCLK", "eeg_digital_top.sv",
     "if (soft_req)              soft_cnt <= 3'd4;", "if (soft_req)              soft_cnt <= 3'd0;"),
    ("最上位：CIC が TH の取り込みのサイクルで符号を取る", "eeg_digital_top.sv",
     ".arm(cic_arm & ~soft_req), .en(cic_en), .code(CODE),", ".arm(cic_arm & ~soft_req), .en(th_capture), .code(CODE),"),
    ("最上位：過負荷の検出が TH の取り込みのサイクルで符号を取る", "eeg_digital_top.sv",
     "eeg_ovl u_ovl (.clk(MCLK), .rst_n(tm_rst_n), .en(cic_en),", "eeg_ovl u_ovl (.clk(MCLK), .rst_n(tm_rst_n), .en(th_capture),"),
    ("RAW：語を cycle 0 で読み込む", "eeg_raw.sv", "if (cycle == 5'd31) begin", "if (cycle == 5'd0) begin"),
    ("シーケンサ：RECOVER の APPLY_NR を CFG_ERR で拒む", "eeg_seq.sv",
     "if (cfg_ok && nr_ok) begin", "if (cfg_ok && nr_ok && state != S_RECOVER) begin"),
    # audit round 10, auditor B: a frame running at a reset's release (phase W)
    ("SPI：CS_N の同期の初期値が High（解除のときのフレームを途中から拾う）", "eeg_spi_slave.sv",
     "cs_q   <= 3'b000;                        // no CS_N fall", "cs_q   <= 3'b111;                        // no CS_N fall"),
    ("SPI：リセットの解除のときのフレームで MISO を駆動する", "eeg_spi_slave.sv",
     "assign cs_act    = armed & ~cs_q[1];", "assign cs_act    = ~cs_q[1];"),
    # audit round 10, auditor C: the test controls' reset values (the pins after RESET_N and SOFT_RESET)
    ("レジスタ：CHOP_STOP のリセット値が 1（電源投入からチョッパが止まる）", "eeg_regs.sv",
     "s_cstop <= TEST_CTRL_CHOP_STOP_RST;             a_cstop <= TEST_CTRL_CHOP_STOP_RST;",
     "s_cstop <= 1'b1;             a_cstop <= 1'b1;"),
    ("レジスタ：ADC_ZERO のリセット値が 1（電源投入から ADC の入力が短絡）", "eeg_regs.sv",
     "s_azero <= TEST_CTRL_ADC_ZERO_RST;              a_azero <= TEST_CTRL_ADC_ZERO_RST;",
     "s_azero <= 1'b1;              a_azero <= 1'b1;"),
    # audit round 12, auditor C: RESET_N's reset of the registers made synchronous (phase X: MCLK stopped, RESET_N low)
    ("レジスタ：RESET_N のリセットを同期に（MCLK がないと端子が既定値に戻らない）", "eeg_regs.sv",
     "    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            s_m <= ",
     "    always_ff @(posedge clk) begin\n        if (!rst_n) begin\n            s_m <= "),
    # audit round 13, auditor A: the tick's frame at 64 kHz (the AFE_RST edges at 64 kHz are now checked too)
    ("クロック：64 kHz の tick がフレーム 4（相 A の後半）", "eeg_clkgen.sv",
     "(cnt_nxt[8:5] == TICK_FRAME_64K));", "(cnt_nxt[8:5] == TICK_FRAME_64K + 4'd1));"),
    # audit round 13, auditor C: the guard widened (J2's run_free_tests), a write's CRC byte not held (A's CRC-on write
    # to the sample window)
    ("レジスタ：0x20 以上の全てのアドレスを守る（IF_CFG と DEBUG も STATE_ERR）", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin",
     "end else if (pend && !cmd_ack && (addr >= 7'h20)) begin"),
    ("レジスタ：試験の鍵も守る（未処理の命令の間は STATE_ERR）", "eeg_regs.sv",
     "end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin",
     "end else if (pend && !cmd_ack && (GUARDED_ADDRS[addr] || addr == A_TEST_KEY)) begin"),
    ("SPI：標本の窓への書き込みで CRC のバイトを保持しない", "eeg_spi_slave.sv",
     "                                wcrc <= rx_byte;", "                                if (hdr[6:0] != 7'h40) wcrc <= rx_byte;"),
    # audit round 14, auditor B: the FIFO sees the SPI's copy one MCLK late (T13's sweep of a copy in a store's cycle)
    # audit round 14, auditor C: STOP applying the shadows (V12), OVERRUN tied to 1 (G), the empty word's ERR tied to 1 (T4)
    ("シーケンサ：WARMUP と PULSE の STOP でシャドウを反映する（REG-03）", "eeg_seq.sv",
     "                if (state != S_IDLE) nxt = S_IDLE;          // IDLE: accepted, does nothing (IGN)",
     "                if (state != S_IDLE) nxt = S_IDLE;          // IDLE: accepted, does nothing (IGN)\n                if ((state == S_WARMUP || state == S_PULSE) && cfg_ok) a_apply = 1'b1;"),
    ("最上位：サンプルの OVERRUN を常に 1", "eeg_digital_top.sv",
     "        smp_status[SMP_OVERRUN_LSB] = dflag_overrun;", "        smp_status[SMP_OVERRUN_LSB] = 1'b1;"),
    ("最上位：空の語の ERR を常に 1", "eeg_digital_top.sv",
     "        empty_status[SMP_ERR_LSB]     = alert;", "        empty_status[SMP_ERR_LSB]     = 1'b1;"),
    ("SPI：標本の写しを 1 MCLK 遅れて FIFO に知らせる（格納と同じサイクルの写しで標本を失う）", "eeg_spi_slave.sv",
     "    assign smp_snap = !cs_start",
     "    logic smp_snap_c;\n    always_ff @(posedge clk or negedge rst_n) if (!rst_n) smp_snap <= 1'b0; else smp_snap <= smp_snap_c;\n    assign smp_snap_c = !cs_start"),
    # audit round 15, auditor B: an illegal SPI state value between frames kept through the next frame (NFR-05)
    ("SPI：フレームの間の不正な状態値を次のフレームの始まりで戻さない（そのフレームは FRAME_ERR）", "eeg_spi_slave.sv",
     "            if (cs_start) begin\n                st      <= S_HDR;",
     "            if (cs_start && st <= S_OVF) begin\n                st      <= S_HDR;"),
    # audit round 15, auditor C: the write-only registers read back (a01, a02), a key dropped while a command waits
    # (a03), RANGE's legality decoded by hand (a04), READY and DATA crosswise in STATUS, registers and flags kept
    # through a SOFT_RESET by a RESET_N-only reset (a06: the timers and the ALERT masks; a07: DFLAG and DRDY_MODE)
    ('レジスタ：COMMAND が最後の命令のコードを返す（書き込み専用は 0x00）', 'eeg_regs.sv',
     "            A_COMMAND, A_TEST_KEY, A_SAMPLE: rdata = 8'h00;    // write only; the window is the SPI's",
     "            A_COMMAND:        rdata = pcode;               \n            A_TEST_KEY, A_SAMPLE: rdata = 8'h00;"),
    ('レジスタ：TEST_KEY が施錠の状態を返す', 'eeg_regs.sv',
     "            A_COMMAND, A_TEST_KEY, A_SAMPLE: rdata = 8'h00;    // write only; the window is the SPI's",
     "            A_TEST_KEY:       rdata = {7'd0, unlocked};\n            A_COMMAND, A_SAMPLE: rdata = 8'h00;"),
    ('レジスタ：未処理の命令の間に送られた試験の鍵を黙って捨てる', 'eeg_regs.sv',
     '                    A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);',
     '                    A_TEST_KEY:     if (!pend) unlocked <= (wdata == TEST_KEY_VALUE);'),
    ('レジスタ：RANGE の合法性を bit 2 と bit 0 から手で（6 を旗なしに書く）', 'eeg_regs.sv',
     '            A_OFF_CTRL:  wr_range_bad = (wdata[2:0] > OFF_CTRL_RANGE_MAX);',
     '            A_OFF_CTRL:  wr_range_bad = wdata[2] & wdata[0];'),
    ('レジスタ：STATUS の READY と DATA の入れ違い', 'eeg_regs.sv',
     '        status_byte[STATUS_READY_LSB]       = (state == ST_RUN);\n        status_byte[STATUS_DATA_LSB]        = fifo_nonempty;',
     '        status_byte[STATUS_READY_LSB]       = fifo_nonempty;\n        status_byte[STATUS_DATA_LSB]        = (state == ST_RUN);'),
    ('レジスタ：タイマと ALERT のマスクを SOFT_RESET で戻さない（RESET_N のみ）', [
      ('eeg_regs.sv', '    input  logic       rst_n,\n    // SPI slave', "    input  logic       rst_n,\n    input  logic       pin_rst_n = 1'b1,   // (mutant) RESET_N only\n    // SPI slave"),
      ('eeg_regs.sv', '            r_mask <= ALERT_MASK_ALERT_MASK_RST;            r_mask_d <= ALERT_MASK_D_ALERT_MASK_D_RST;\n            r_tw <= T_WARM_T_WARM_RST;  r_te <= T_ELEC_T_ELEC_RST;  r_trec <= T_REC_T_REC_RST;\n            r_tpre <= T_PRE_T_PRE_RST;  r_trst <= T_RST_T_RST_RST;\n', ''),
      ('eeg_regs.sv', '                    A_ALERT_MASK:   r_mask <= wdata;\n                    A_ALERT_MASK_D: r_mask_d <= wdata[ALERT_MASK_D_ALERT_MASK_D_LSB +: ALERT_MASK_D_ALERT_MASK_D_W];\n                    A_T_WARM:       r_tw <= wdata;\n                    A_T_ELEC:       r_te <= wdata;\n                    A_T_REC:        r_trec <= wdata;\n                    A_T_PRE:        r_tpre <= wdata;\n                    A_T_RST:        r_trst <= wdata;\n', ''),
      ('eeg_regs.sv', '    // ---------------- outputs\n', "    // (mutant) the host's settings: RESET_N only\n    always_ff @(posedge clk or negedge pin_rst_n) begin\n        if (!pin_rst_n) begin\n            r_mask <= ALERT_MASK_ALERT_MASK_RST;            r_mask_d <= ALERT_MASK_D_ALERT_MASK_D_RST;\n            r_tw <= T_WARM_T_WARM_RST;  r_te <= T_ELEC_T_ELEC_RST;  r_trec <= T_REC_T_REC_RST;\n            r_tpre <= T_PRE_T_PRE_RST;  r_trst <= T_RST_T_RST_RST;\n        end else if (w_ok) begin\n            case (addr)\n                A_ALERT_MASK:   r_mask <= wdata;\n                A_ALERT_MASK_D: r_mask_d <= wdata[ALERT_MASK_D_ALERT_MASK_D_LSB +: ALERT_MASK_D_ALERT_MASK_D_W];\n                A_T_WARM:       r_tw <= wdata;\n                A_T_ELEC:       r_te <= wdata;\n                A_T_REC:        r_trec <= wdata;\n                A_T_PRE:        r_tpre <= wdata;\n                A_T_RST:        r_trst <= wdata;\n                default:        ;\n            endcase\n        end\n    end\n\n    // ---------------- outputs\n"),
      ('eeg_digital_top.sv', '        .clk(MCLK), .rst_n(rst_n), .addr(reg_addr), .rdata(reg_rdata),', '        .clk(MCLK), .rst_n(rst_n), .pin_rst_n(tm_rst_n), .addr(reg_addr), .rdata(reg_rdata),')], None, None),
    ('レジスタ：DFLAG と DRDY_MODE を SOFT_RESET で戻さない（RESET_N のみ）', [
      ('eeg_regs.sv', '    input  logic       rst_n,\n    // SPI slave', "    input  logic       rst_n,\n    input  logic       pin_rst_n = 1'b1,   // (mutant) RESET_N only\n    // SPI slave"),
      ('eeg_regs.sv', '            r_crc <= IF_CFG_CRC_EN_RST; r_drdy <= IF_CFG_DRDY_MODE_RST;\n', '            r_crc <= IF_CFG_CRC_EN_RST;\n'),
      ('eeg_regs.sv', "            dflag <= 2'b00;\n            pend <= 1'b0;", "            pend <= 1'b0;"),
      ('eeg_regs.sv', '                    A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; end', '                    A_IF_CFG:       r_crc <= wdata[0];'),
      ('eeg_regs.sv', "            dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n                                                                : 2'b00)) | {ovl_set, ovr_set};\n", ''),
      ('eeg_regs.sv', '    // ---------------- outputs\n', "    // (mutant) DFLAG and DRDY_MODE: RESET_N only\n    always_ff @(posedge clk or negedge pin_rst_n) begin\n        if (!pin_rst_n) begin\n            dflag  <= 2'b00;\n            r_drdy <= IF_CFG_DRDY_MODE_RST;\n        end else begin\n            if (w_ok && addr == A_IF_CFG) r_drdy <= wdata[1];\n            dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n                                                                : 2'b00)) | {ovl_set, ovr_set};\n        end\n    end\n\n    // ---------------- outputs\n"),
      ('eeg_digital_top.sv', '        .clk(MCLK), .rst_n(rst_n), .addr(reg_addr), .rdata(reg_rdata),', '        .clk(MCLK), .rst_n(rst_n), .pin_rst_n(tm_rst_n), .addr(reg_addr), .rdata(reg_rdata),')], None, None),
    # audit round 16, auditor C: the pending command kept through a SOFT_RESET (a RESET_N-only reset), and the codes,
    # the key and SOFT_RESET's code compared on 7 bits
    ('レジスタ：未処理の命令を SOFT_RESET で消さない（RESET_N のみ）', [
      ('eeg_regs.sv', '    input  logic       rst_n,\n    // SPI slave', '    input  logic       rst_n,\n    input  logic       pin_rst_n,          // RESET_N only (the pending command)\n    // SPI slave'),
      ('eeg_regs.sv', "            pend <= 1'b0;\n            pcode <= 8'h00;\n        end else begin", '        end else begin'),
      ('eeg_regs.sv', "            // command: taken by the sequencer at a tick; a new one only when none is pending (else STATE_ERR)\n            if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end else if (cmd_ack) begin\n                pend  <= 1'b0;\n            end\n", ''),
      ('eeg_regs.sv', '    // ---------------- outputs\n', "    // the pending command: RESET_N only (a SOFT_RESET leaves it)\n    always_ff @(posedge clk or negedge pin_rst_n) begin\n        if (!pin_rst_n) begin\n            pend <= 1'b0;\n            pcode <= 8'h00;\n        end else begin\n            if (w_ok && addr == A_COMMAND) begin\n                pend  <= 1'b1;\n                pcode <= wdata;\n            end else if (cmd_ack) begin\n                pend  <= 1'b0;\n            end\n        end\n    end\n\n    // ---------------- outputs\n"),
      ('eeg_digital_top.sv', '        .clk(MCLK), .rst_n(rst_n), .addr(reg_addr), .rdata(reg_rdata),', '        .clk(MCLK), .rst_n(rst_n), .pin_rst_n(tm_rst_n), .addr(reg_addr), .rdata(reg_rdata),')], None, None),
    ('レジスタ：命令のコードを下位 7 ビットで比べる', 'eeg_regs.sv',
     '    assign is_cmd_code = (wdata == CMD_START) || (wdata == CMD_STOP) || (wdata == CMD_APPLY) ||\n                         (wdata == CMD_APPLY_NR) || (wdata == CMD_FLUSH);',
     '    assign is_cmd_code = (wdata[6:0] == CMD_START[6:0]) || (wdata[6:0] == CMD_STOP[6:0]) || (wdata[6:0] == CMD_APPLY[6:0]) ||\n                         (wdata[6:0] == CMD_APPLY_NR[6:0]) || (wdata[6:0] == CMD_FLUSH[6:0]);'),
    ('レジスタ：試験の鍵を下位 7 ビットで比べる', [
      ('eeg_regs.sv', '                    A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);', '                    A_TEST_KEY:     unlocked <= (wdata[6:0] == TEST_KEY_VALUE[6:0]);'),
      ('eeg_regs.sv', "                if (wdata != TEST_KEY_VALUE && wdata != 8'h00) ev_err[ERR_CMD_ERR_LSB] = 1'b1;", "                if (wdata[6:0] != TEST_KEY_VALUE[6:0] && wdata != 8'h00) ev_err[ERR_CMD_ERR_LSB] = 1'b1;")], None, None),
    ('レジスタ：SOFT_RESET のコードを下位 7 ビットで比べる', 'eeg_regs.sv',
     '    assign is_soft     = (wdata == CMD_SOFT_RESET);',
     '    assign is_soft     = (wdata[6:0] == CMD_SOFT_RESET[6:0]);'),
    # audit round 17, auditor C: a register on the CHOP_BLANK pad and on the CHOP1 pad (the obvious NFR-06 clean-ups),
    # and DBG_SEL 3's CHOP1 retimed at the frame boundary
    ('上位：CHOP_BLANK の端子をフリップフロップに（立ち上がりが CHOP_OUT の縁に遅れる）', 'eeg_digital_top.sv',
     '    assign CHOP_BLANK = gen_blank | a_azero;',
     "    logic chop_blank_q;\n    always_ff @(posedge MCLK or negedge tm_rst_n) if (!tm_rst_n) chop_blank_q <= 1'b0; "
     "else chop_blank_q <= gen_blank | a_azero;\n    assign CHOP_BLANK = chop_blank_q;"),
    ('上位：CHOP1 の端子をフリップフロップに（縁が e17）', 'eeg_digital_top.sv',
     '    eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n), .cycle(cycle), .chop1_rate(a_c1), .chop1(CHOP1));',
     "    logic chop1_i;\n    eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n), .cycle(cycle), .chop1_rate(a_c1), .chop1(chop1_i));\n"
     "    always_ff @(posedge MCLK or negedge tm_rst_n) if (!tm_rst_n) CHOP1 <= 1'b1; else CHOP1 <= chop1_i;"),
    ('上位：DBG_SEL 3 の CHOP1 をフレームの境で取り直す（16 MCLK 遅れ）', [
      ('eeg_digital_top.sv', '    eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n), .cycle(cycle), .chop1_rate(a_c1), .chop1(CHOP1));',
       "    eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n), .cycle(cycle), .chop1_rate(a_c1), .chop1(CHOP1));\n"
       "    logic chop1_dbg;\n    always_ff @(posedge MCLK or negedge tm_rst_n) if (!tm_rst_n) chop1_dbg <= 1'b1; "
       "else if (frame_stb) chop1_dbg <= CHOP1;"),
      ('eeg_digital_top.sv', '.dbg_data({CHOP1, CHOP_OUT, DAC_CLK}),', '.dbg_data({chop1_dbg, CHOP_OUT, DAC_CLK}),')], None, None),
    # audit round 18, auditor C: SOFT_RESET's commit registered once before soft_req (R forces soft_req)
    ('上位：SOFT_RESET の確定を soft_req の前で 1 段のレジスタに', [
      ('eeg_digital_top.sv', "    wire        soft_req;                             // SOFT_RESET's commit cycle (eeg_regs; a net, so tests can force it)\n",
       "    wire        soft_req;                             // SOFT_RESET's commit cycle (eeg_regs; a net, so tests can force it)\n"
       "    logic       soft_raw, soft_q;\n"),
      ('eeg_digital_top.sv', '        .cmd_ack(cmd_ack), .soft_reset(soft_req), .apply(apply),',
       '        .cmd_ack(cmd_ack), .soft_reset(soft_raw), .apply(apply),'),
      ('eeg_digital_top.sv', '    logic tm_rst_n;                                   // timing and data path: RESET_N only\n',
       "    always_ff @(posedge MCLK or negedge pin_rst_n) if (!pin_rst_n) soft_q <= 1'b0; else soft_q <= soft_raw;\n"
       '    assign soft_req = soft_q;\n'
       '    logic tm_rst_n;                                   // timing and data path: RESET_N only\n')], None, None),
    # audit round 19, auditor B: FRAME_ERR set at the next frame's start, after that header's STATUS copy (the host's
    # step 6 locates a slipped frame by the ALERT in the next header)
    ('SPI：FRAME_ERR を次のフレームの始まりで立てる（次の先頭バイトの STATUS に現れない）', [
      ('eeg_spi_slave.sv', '    (* fsm_encoding = "none" *) logic [3:0]  st;',
       '    logic        fe_pend;\n    (* fsm_encoding = "none" *) logic [3:0]  st;'),
      ('eeg_spi_slave.sv', "            frame_err <= 1'b0;\n            crc_err   <= 1'b0;\n            addr_err  <= 1'b0;\n",
       "            frame_err <= 1'b0;\n            crc_err   <= 1'b0;\n            addr_err  <= 1'b0;\n            fe_pend   <= 1'b0;\n"),
      ('eeg_spi_slave.sv', '                tx_sh   <= status_byte;                  // STATUS during the header byte\n',
       "                tx_sh   <= status_byte;                  // STATUS during the header byte\n                frame_err <= fe_pend;\n                fe_pend   <= 1'b0;\n"),
      ('eeg_spi_slave.sv', "                        frame_err <= 1'b1;               // inside a byte, overlong",
       "                        fe_pend   <= 1'b1;               // inside a byte, overlong")], None, None),
    # audit round 19, auditor C: copies that passed all 16 groups
    ('上位：TEST_CFG[7:6]（DBG_SEL）を APPLY で反映する（ANA-01 は書き込みで直ちに）', 'eeg_digital_top.sv',
     '    assign TEST_CFG   = {dbg_sel, a_azero, a_atpen, a_atpsel};',
     "    logic [1:0] a_dbg_q;\n    always_ff @(posedge MCLK or negedge rst_n) begin\n        if (!rst_n)     a_dbg_q <= 2'b00;\n"
     "        else if (apply) a_dbg_q <= dbg_sel;\n    end\n    assign TEST_CFG   = {a_dbg_q, a_azero, a_atpen, a_atpsel};"),
    ('レジスタ：ロック中の試験のレジスタ（0x60〜0x62）の読み出しが 0x00（REG-08 は書き込みのみを閉じる）', [
      ('eeg_regs.sv', "            A_TEST_MUX:       rdata = {3'd0, s_atpen, s_atpsel};",
       "            A_TEST_MUX:       rdata = unlocked ? {3'd0, s_atpen, s_atpsel} : 8'h00;"),
      ('eeg_regs.sv', "            A_TEST_CTRL:      rdata = {6'd0, s_cstop, s_azero};",
       "            A_TEST_CTRL:      rdata = unlocked ? {6'd0, s_cstop, s_azero} : 8'h00;"),
      ('eeg_regs.sv', "            A_DEBUG:          rdata = {5'd0, r_dbg, r_raw};",
       "            A_DEBUG:          rdata = unlocked ? {5'd0, r_dbg, r_raw} : 8'h00;")], None, None),
    ('レジスタ：サンプルと空の語の ERR を ERR のマスクした旗のみから（DFLAG を含めない。STATUS の ALERT は正しい）', [
      ('eeg_regs.sv', '    assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);',
       '    assign alert       = |(err & r_mask);'),
      ('eeg_regs.sv', '        status_byte[STATUS_ALERT_LSB]       = alert;',
       '        status_byte[STATUS_ALERT_LSB]       = alert || |(dflag_byte & mask_d_byte);')], None, None),
    # audit round 20, auditor C: the RAW stream's priority over DBG_SEL and its switch at the frame boundary
    ('RAW：DBG_SEL が 0 でなければ RAW_EN を止める（流れが優先しない）', 'eeg_digital_top.sv',
     '    eeg_raw u_raw (.clk(MCLK), .rst_n(tm_rst_n), .raw_en(raw_en), .cycle(cycle)',
     '    eeg_raw u_raw (.clk(MCLK), .rst_n(tm_rst_n), .raw_en(raw_en && (dbg_sel == 2\'b00)), .cycle(cycle)'),
    ('RAW：流れと対を書き込みで切り替える（語と対を切る）', 'eeg_raw.sv',
     "            if (on || dbg_sel == 2'b00) begin", "            if (raw_en || dbg_sel == 2'b00) begin"),
    # audit round 22, auditor C: pulse-mode DRDY_N (DAT-04) and the CHANGED marks, each of which passed all 16 groups
    # or was caught only through the state an earlier phase left
    ('上位：パルスのモードの DRDY_N を RUN の格納のみで（FILL の格納にパルスなし）', 'eeg_digital_top.sv',
     "assign drdy_nxt = push_ok ? 3'd4 :", "assign drdy_nxt = (push_ok && seq_state == ST_RUN) ? 3'd4 :"),
    ('上位：パルスのモードの DRDY_N を FIFO が空になると終える', 'eeg_digital_top.sv',
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~(drdy_pulse && fifo_nonempty) : ~fifo_nonempty);"),
    ('上位：CHANGED の印を PRE でのみ消す（STOP で消さない）', 'eeg_digital_top.sv',
     "else if (seq_state != ST_RUN) chg_cnt <= 9'd0;", "else if (seq_state == ST_PRE) chg_cnt <= 9'd0;"),
    ('上位：走っている印があれば新しい長い印で延ばさない', 'eeg_digital_top.sv',
     "chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : chg_new;", "chg_cnt <= (chg_cnt != 9'd0) ? chg_cnt : chg_new;"),
    # audit round 23, auditor C: one register's write clobbering another's field (every write went in ascending order
    # with the others at reset and only the written register read back; both passed all 16 groups)
    ('レジスタ：OFF_M_H への書き込みが M[7:0] も消す（上位のバイトを先に書く前提）', 'eeg_regs.sv',
     "A_OFF_M_H:      s_m[9:8] <= wdata[1:0];", "A_OFF_M_H:      s_m <= {wdata[1:0], 8'h00};"),
    ('レジスタ：OFF_M_L への書き込みが SIGN も消す', 'eeg_regs.sv',
     "A_OFF_M_L:      s_m[7:0] <= wdata;", "A_OFF_M_L:      begin s_m[7:0] <= wdata; s_sign <= 1'b0; end"),
    # audit round 24, auditor C (u1): the CIC reset by the control reset (a SOFT_RESET moves the CIC's grid)
    ('上位：CIC のリセットを制御のリセットから（SOFT_RESET で CIC の格子が動く）', 'eeg_digital_top.sv',
     "eeg_cic3 u_cic (.clk(MCLK), .rst_n(tm_rst_n),", "eeg_cic3 u_cic (.clk(MCLK), .rst_n(rst_n),"),
    # audit round 25, auditor C (MA): level-mode DRDY_N falling only at frame cycle 0 (only pulse mode was monitored;
    # it passed all 16 groups)
    ('上位：レベルのモードの DRDY_N の立ち下がりがフレームのサイクル 0 まで遅れる', 'eeg_digital_top.sv',
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);",
     "drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : (~fifo_nonempty | (drdy_n_q & (cycle != 5'd0))));"),
    # audit round 26, auditor C: CAPS reporting the 8-deep FIFO on a 4-deep chip (only the 4-deep bench sees it; it
    # names DEPTH, so the runner runs that bench), a write to STATUS taken silently (no fixed test wrote STATUS), and
    # the pulse-mode DRDY_N one MCLK late (the monitor allowed 1 to 2 MCLK)
    ('上位：CAPS の FIFO の深さを 8 に固定（eeg_regs に深さを渡さない）', 'eeg_digital_top.sv',
     "    eeg_regs #(.FIFO_DEPTH(FIFO_DEPTH)) u_regs (", "    eeg_regs #(.FIFO_DEPTH(8)) u_regs ("),
    ('レジスタ：STATUS への書き込みを黙って受ける（読み出し専用の一覧から外す）', [
        ('eeg_regs.sv', "            A_ID, A_VERSION, A_CAPS, A_STATUS, A_STATE, A_FIFO_LEVEL, A_ODR_H, A_ODR_L, A_FORMAT, A_SAMPLE,",
         "            A_ID, A_VERSION, A_CAPS, A_STATE, A_FIFO_LEVEL, A_ODR_H, A_ODR_L, A_FORMAT, A_SAMPLE,"),
        ('eeg_regs.sv', "            A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,",
         "            A_STATUS, A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,")],
     None, None),
    ('上位：パルスのモードの DRDY_N が 1 MCLK 遅れる（登録した数から）', 'eeg_digital_top.sv',
     "drdy_pulse <= (drdy_nxt != 3'd0);", "drdy_pulse <= (drdy_cnt != 3'd0);"),
    # audit round 27, auditor C: ERR's W1C gate on every write (the generated test's 2b now reads ERR in its bursts);
    # the SPI's state codes with a gap (10 unused, unflagged by st > S_OVF; the bench now takes the codes from the RTL)
    ('レジスタ：ERR の W1C の門が全ての書き込み（上位）', 'eeg_regs.sv',
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata", "err   <= (err & ~((we || w_ok && addr == A_ERR) ? wdata"),
    ('SPI：S_OVF を 11 に（10 を使わない符号）', 'eeg_spi_slave.sv',
     "                           S_OVF = 4'd10;", "                           S_OVF = 4'd11;"),
    # audit round 28, auditor C: the command codes and the key as data (no fixed test wrote 0xA5 elsewhere)
    ("レジスタ：SOFT_RESET をアドレスを見ずにデータの 0xA5 のみで解く", "eeg_regs.sv",
     "assign soft_reset = we && wr_def && !wr_ro && (addr == A_COMMAND) && is_soft;",
     "assign soft_reset = we && wr_def && !wr_ro && is_soft;"),
    # audit round 28, auditor C: one-way aliases 2b could not see
    ("レジスタ：ALERT_MASK の書き込みが ALERT_MASK_D も書く", "eeg_regs.sv",
     "                    A_ALERT_MASK:   r_mask <= wdata;",
     "                    A_ALERT_MASK:   begin r_mask <= wdata; r_mask_d <= wdata[1:0]; end"),
    ("レジスタ：IF_CFG の予約のビット 2 が RAW_EN を書く", "eeg_regs.sv",
     "                    A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; end",
     "                    A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; r_raw <= wdata[2]; end"),
    # audit round 28, auditor C: one W1C enable shared by ERR and DFLAG, through the pins (J2's DFLAG write)
    ("レジスタ：DFLAG への W1C の書き込みが ERR も消す（共有の門、端子から）", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata",
     "err   <= (err & ~((we && w_ok && (addr == A_ERR || addr == A_DFLAG)) ? wdata"),
    # audit round 28, auditor C: a CHOP_BLANK pulse that never starts hung tb_clkgen (no verdict before)
    ("クロック：CHOP_BLANK のパルスが始まらない", "eeg_clkgen.sv",
     "            if (out_edge_ahead && (blank_len != 4'd0)) begin\n                chop_blank <= 1'b1;\n",
     "            if (out_edge_ahead && (blank_len != 4'd0)) begin\n"),
    # audit round 29, auditor C: OFF_M_H locked by the test key, through the pins (2e)
    ("レジスタ：OFF_M_H を鍵で施錠する（端子から）", [("eeg_regs.sv", "A_TEST_KEY, A_OFF_M_H, A_OFF_M_L,", "A_TEST_KEY, A_OFF_M_L,"),
      ("eeg_regs.sv", "A_TEST_MUX, A_TEST_CTRL, A_DEBUG: wr_locked = !unlocked;",
       "A_TEST_MUX, A_TEST_CTRL, A_DEBUG, A_OFF_M_H: wr_locked = !unlocked;")], None, None),
    # audit round 29, auditor C: DAC_CLK's reset value (read by no test)
    ("最上位：DAC_CLK のリセット値を 1 に", "eeg_digital_top.sv",
     "        if (!tm_rst_n) DAC_CLK <= 1'b0;", "        if (!tm_rst_n) DAC_CLK <= 1'b1;"),
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
    # audit round 11, auditor C: NFR-05 with a command pending and at a tick (tb_seq's illegal-state loop)
    ("シーケンサ：不正な状態値で未処理の命令を受け取って捨てる", "eeg_seq.sv",
     "            nxt    = S_IDLE;\n            a_serr = 1'b1;\n        end else if (tick) begin",
     "            nxt    = S_IDLE;\n            a_serr = 1'b1;\n            a_ack  = cmd_valid;\n        end else if (tick) begin"),
    ("シーケンサ：tick では不正な状態値を見ない（tick の分岐が先）", "eeg_seq.sv",
     "        if (state > S_PULSE) begin                          // illegal value: safe side",
     "        if (state > S_PULSE && !tick) begin                 // illegal value: safe side"),
    # (audit round 23, auditor C: round 22's q14 was this list's q03 again, the same edit; removed. The runner now
    # refuses two identical edits in one group)
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
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}\n                                                                : 2'b00)) | {ovl_set, ovr_set};",
     "dflag <= (dflag | {ovl_set, ovr_set}) & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]} : 2'b00);"),
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
    # audit round 27, auditor C: the W1C gate on every write (no test wrote elsewhere with a flag set)
    ("レジスタ：ERR の W1C の門が全ての書き込み（we || w_ok && …）", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata", "err   <= (err & ~((we || w_ok && addr == A_ERR) ? wdata"),
    ("レジスタ：DFLAG の W1C の門が全ての書き込み（we || w_ok && …）", "eeg_regs.sv",
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ?", "dflag <= (dflag & ~((we || w_ok && addr == A_DFLAG) ?"),
    ("レジスタ：ERR の W1C がアドレスを見ない", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata", "err   <= (err & ~((we && w_ok) ? wdata"),
    # audit round 28, auditor C: one W1C enable shared by the two flag registers (the loop skipped both)
    ("レジスタ：DFLAG への W1C の書き込みが ERR も消す（共有の門）", "eeg_regs.sv",
     "err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata",
     "err   <= (err & ~((we && w_ok && (addr == A_ERR || addr == A_DFLAG)) ? wdata"),
    ("レジスタ：ERR への W1C の書き込みが DFLAG も消す（共有の門）", "eeg_regs.sv",
     "dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ?",
     "dflag <= (dflag & ~((we && w_ok && (addr == A_DFLAG || addr == A_ERR)) ?"),
    # audit round 29, auditor C: OFF_M_H among the locked registers (no test wrote it with the key locked)
    ("レジスタ：OFF_M_H を鍵で施錠する", [("eeg_regs.sv", "A_TEST_KEY, A_OFF_M_H, A_OFF_M_L,", "A_TEST_KEY, A_OFF_M_L,"),
      ("eeg_regs.sv", "A_TEST_MUX, A_TEST_CTRL, A_DEBUG: wr_locked = !unlocked;",
       "A_TEST_MUX, A_TEST_CTRL, A_DEBUG, A_OFF_M_H: wr_locked = !unlocked;")], None, None),
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


# one flip-flop less on CS_N and SCLK (audit round 9: in the SPI and the structural groups)
SYNC_OLD = '    assign cs_act    = armed & ~cs_q[1];\n    assign cs_start  = armed & ~cs_q[1] &  cs_q[2];\n    assign cs_end    = armed &  cs_q[1] & ~cs_q[2];\n    assign sclk_rise = cs_act &  sclk_q[1] & ~sclk_q[2];\n    assign sclk_fall = cs_act & ~sclk_q[1] &  sclk_q[2];'
SYNC_NEW = '    assign cs_act    = armed & ~cs_q[0];\n    assign cs_start  = armed & ~cs_q[0] &  cs_q[1];\n    assign cs_end    = armed &  cs_q[0] & ~cs_q[1];\n    assign sclk_rise = cs_act &  sclk_q[0] & ~sclk_q[1];\n    assign sclk_fall = cs_act & ~sclk_q[0] &  sclk_q[1];'

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
    # audit round 7: the shared bus (another chip's frame with this CS_N high; MISO_OE off as CS_N rises)
    ("SPI：MISO_OE を CS_N の立ち上がりで直ちに切らない（同期化の 2〜3 MCLK の間、共有の MISO を駆動）", "eeg_spi_slave.sv",
     "assign miso_oe   = ~cs_n & cs_act;", "assign miso_oe   = cs_act;"),
    # (SCLK edges counted with CS_N high is an equivalent mutant: IDLE ignores the bits and CS_N falling resets the
    #  bit count; an edge in the 2-3 MCLK after CS_N rises is counted with or without the gate. Not listed.)
    # audit round 8, auditor C: MISO one register later (4 MCLK after the SCLK fall; the latency check had been dropped)
    ('SPI：MISO をもう 1 段のレジスタから出す', 'eeg_spi_slave.sv',
     '    assign miso      = tx_sh[7];',
     '    logic miso_q;\n    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) miso_q <= 1\'b0;\n        else        miso_q <= tx_sh[7];\n    end\n    assign miso      = miso_q;'),
    # audit round 9, auditor C: one flip-flop less on CS_N and SCLK (MISO and MISO_OE one MCLK early: the BFM's lower
    # bounds on the latencies)
    ("SPI：CS_N と SCLK を 1 段で同期（MISO が 1 MCLK 早い）", "eeg_spi_slave.sv", SYNC_OLD, SYNC_NEW),
    # audit round 10, auditor C: the start of a frame one MCLK late (the BFM's upper bounds: MISO_OE 2 MCLK, STATUS's
    # bit 7 at 3 MCLK and the pad delay)
    ("SPI：MISO_OE をもう 1 段遅く（CS_N の立ち下がりから 2〜3 MCLK）", "eeg_spi_slave.sv",
     "assign miso_oe   = ~cs_n & cs_act;", "assign miso_oe   = ~cs_n & armed & ~cs_q[2];"),
    ("SPI：STATUS を cs_start の 1 MCLK あとに載せる", "eeg_spi_slave.sv",
     "                tx_sh   <= status_byte;                  // STATUS during the header byte\n            end else if (cs_end) begin",
     "                tx_sh   <= 8'h00;                        // (mutant: STATUS one MCLK later)\n"
     "            end else if (st == S_HDR && bit_cnt == 3'd0 && tx_sh == 8'h00 && !sclk_rise) begin\n"
     "                tx_sh   <= status_byte;\n            end else if (cs_end) begin"),
    # audit round 24, auditor C: the frame start's one MCLK of MISO Low (spec 3.1, PIN-04) was checked by nothing
    ("SPI：CS_N の立ち上がりで MISO の送りのレジスタを 0 にしない（フレームの始まりの 1 MCLK の Low がない）", "eeg_spi_slave.sv",
     "                st    <= S_IDLE;\n                tx_sh <= 8'h00;\n            end else begin",
     "                st    <= S_IDLE;\n            end else begin"),
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
    # audit round 9, auditor C: single-flop synchronizers (their metastability cannot be simulated; the structure shows
    # them: check_outputs_registered.check_synchronizers)
    ("最上位：RESET_N の解除を 1 段で同期", "eeg_digital_top.sv",
     "assign pin_rst_n = rst_sync[1];", "assign pin_rst_n = rst_sync[0];"),
    ("SPI：CS_N と SCLK を 1 段で同期", "eeg_spi_slave.sv", SYNC_OLD, SYNC_NEW),
    ("SPI：MOSI を 1 段で同期", "eeg_spi_slave.sv",
     "assign mosi_s    = mosi_q[1];", "assign mosi_s    = mosi_q[0];"),
    # audit round 12, auditor C: synchronous resets (RST-01 asks for an asynchronous one; every bench held RESET_N across
    # MCLK edges): check_outputs_registered.check_resets
    ("SPI：フレームの処理のリセットを同期に", "eeg_spi_slave.sv",
     "    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            st        <= S_IDLE;",
     "    always_ff @(posedge clk) begin\n        if (!rst_n) begin\n            st        <= S_IDLE;"),
    ("CIC：リセットを同期に", "eeg_cic3.sv",
     "    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            i1         <= '0;",
     "    always_ff @(posedge clk) begin\n        if (!rst_n) begin\n            i1         <= '0;"),
    # audit round 14, auditor A: the state register left to FSM recoding (NFR-05 through synthesis)
    ("シーケンサ：状態のレジスタの fsm_encoding を外す（合成で符号化し直されうる）", "eeg_seq.sv",
     "    (* fsm_encoding = \"none\" *)                // NFR-05", "    // (no attribute)                         // NFR-05"),
    # audit round 26, auditor C: storage without a reset outside the FIFO (the check had never run): a 2-word buffer
    # of CIC outputs, read into the FIFO's data input outside the store cycles (harmless in function)
    ("最上位：リセットのない 2 語のバッファ（FIFO の外の記憶）", [
        ("eeg_digital_top.sv", ".seq_in(seq_cnt), .data_in(cic_data),",
         ".seq_in(seq_cnt), .data_in(cic_stb ? cic_data : dbuf[seq_cnt[0]]),"),
        ("eeg_digital_top.sv", "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (",
         "    logic [23:0] dbuf [0:1];\n    always_ff @(posedge MCLK) if (cic_stb) dbuf[seq_cnt[0]] <= cic_data;\n"
         "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (")], None, None),
    # audit round 27, auditor C: derived clocks (RST-05; the same counts in every bench, Verilator silent):
    # check_outputs_registered.check_clocks
    ("CHOP1：出力のフリップフロップをフレームの計数のビット 4 で（派生した時計）", [
        ("eeg_chop1.sv", "            rate_q <= 3'd3;\n            chop1  <= 1'b1;\n", "            rate_q <= 3'd3;\n"),
        ("eeg_chop1.sv", "            if (cycle == 5'd15) begin     // this edge is e16\n                chop1 <= wave;\n"
                         "            end\n", ""),
        ("eeg_chop1.sv", "\nendmodule", "\n    always_ff @(posedge cycle[4] or negedge rst_n) begin   // e16: cycle 15 -> 16\n"
                         "        if (!rst_n) chop1 <= 1'b1;\n        else        chop1 <= wave;\n    end\n\nendmodule")],
     None, None),
    ("最上位：SEQ の計数を CIC の strobe の立ち下がりで（派生した時計）", "eeg_digital_top.sv",
     "    always_ff @(posedge MCLK or negedge tm_rst_n) begin\n        if (!tm_rst_n)    seq_cnt <= 16'd0;\n"
     "        else if (cic_stb) seq_cnt <= seq_cnt + 16'd1;",
     "    always_ff @(negedge cic_stb or negedge tm_rst_n) begin\n        if (!tm_rst_n)    seq_cnt <= 16'd0;\n"
     "        else              seq_cnt <= seq_cnt + 16'd1;"),
    # audit round 28, auditor C: a latch from an always_comb, refused by yosys (no verdict before)
    ("構造：eeg_chop1 の always_comb の default を消す（ラッチ）", "eeg_chop1.sv",
     "            default: wave = 1'b1;\n", ""),
]

def bench_ended(v, closing):
    """The bench printed its closing line (its verdict or summary). Without it the simulation crashed or stopped, which
    is no verdict about the mutant (audit round 9, auditor C: a crash counted as a detection)."""
    return any(ln.startswith(closing) for ln in v.stdout.splitlines())


def sim_tail(v, tb):
    return f"{tb} ended without its closing line: " + ((v.stderr.strip().splitlines() or v.stdout.strip().splitlines()
                                                         or ["no output"])[-1])[:110]

def unit_benches(d, files):
    """The unit benches of the blocks a mutation edits, in its copy, as run_tests_r14.sh runs them (audit round 22,
    auditor C: tb_tick, tb_clkgen and tb_cic_arm were never run on a mutant): tb_tick and tb_clkgen for eeg_clkgen.sv,
    tb_chop1 for eeg_chop1.sv and eeg_clkgen.sv (audit round 27, auditor C: run_tests_r14.sh builds it with the r14
    clock generator, the top group never ran it), tb_cic_arm (cleared at outputs 3, 5, 7, 9) for eeg_cic3.sv. Returns (status, text): 'pass'; 'fail' (a bench or its
    check judged FAIL: a detection); 'error' (a compile error, a crash, no closing line: no verdict); 'timeout' (a
    bench without an end within 1200 s, the others run: audit round 28, auditor C: a timeout ended the mutant's run
    without tb_top_r14, which fails such a clock generator at once)."""
    timed_out = []
    inc = ["-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", os.path.join(d, "build")]
    runs = []
    if "eeg_clkgen.sv" in files:
        runs += [("tb_tick", ["eeg_clkgen.sv", os.path.join(R14, "tb", "tb_tick.sv")], ("PASS: tick", "FAIL: tb_tick")),
                 ("tb_clkgen", ["eeg_clkgen.sv", os.path.join(RTL_OLD, "tb", "tb_clkgen.sv")],
                  ("PASS: tb_clkgen", "FAIL: tb_clkgen"))]
    if "eeg_chop1.sv" in files or "eeg_clkgen.sv" in files:
        runs += [("tb_chop1", ["eeg_clkgen.sv", "eeg_chop1.sv", os.path.join(RTL_OLD, "tb", "tb_chop1.sv")],
                  ("PASS: chop1", "FAIL: "))]
    for nm, srcs, closing in runs:
        c = subprocess.run(["iverilog", "-g2012"] + inc + ["-o", f"build/{nm}.vvp"] + srcs, cwd=d, capture_output=True,
                           text=True)
        if c.returncode:
            return "error", f"{nm}: compile: " + (c.stderr.strip().splitlines() or ["?"])[-1][:120]
        try:
            v = subprocess.run(["vvp", "-n", f"build/{nm}.vvp"], cwd=d, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            timed_out.append(f"{nm}: no end within 1200 s")
            continue
        if not bench_ended(v, closing):
            return "error", sim_tail(v, nm)
        if closing[0] not in v.stdout or "FAIL" in v.stdout:
            return "fail", f"{nm}: " + next((ln.strip() for ln in v.stdout.splitlines() if ln.startswith(("ERROR", "FAIL"))),
                                            "FAIL")[:130]
    if "eeg_cic3.sv" in files:
        b = os.path.join(d, "build")
        g = subprocess.run([sys.executable, os.path.join(HERE, "check_cic_arm.py"), "gen", "7", "13", b],
                           capture_output=True, text=True)
        if g.returncode:
            return "error", "check_cic_arm gen: " + ((g.stderr.strip().splitlines() or ["?"])[-1])[:120]
        c = subprocess.run(["iverilog", "-g2012"] + inc + ["-o", "build/tb_cic_arm.vvp", "eeg_cic3.sv", "eeg_rnd_sat.sv",
                            os.path.join(R14, "tb", "tb_cic_arm.sv")], cwd=d, capture_output=True, text=True)
        if c.returncode:
            return "error", "tb_cic_arm: compile: " + (c.stderr.strip().splitlines() or ["?"])[-1][:120]
        for k_ in (3, 5, 7, 9):
            try:
                v = subprocess.run(["vvp", "-n", "build/tb_cic_arm.vvp", f"+k={k_}"], cwd=d, capture_output=True,
                                   text=True, timeout=1200)
            except subprocess.TimeoutExpired:
                timed_out.append(f"tb_cic_arm +k={k_}: no end within 1200 s")
                continue
            if v.returncode:
                return "error", sim_tail(v, "tb_cic_arm")
            k = subprocess.run([sys.executable, os.path.join(HERE, "check_cic_arm.py"), "check", str(k_), b],
                               capture_output=True, text=True)
            if not any(ln.startswith(("PASS:", "FAIL")) for ln in k.stdout.splitlines()):
                return "error", "check_cic_arm crashed: " + ((k.stderr.strip().splitlines() or ["?"])[-1])[:120]
            if k.returncode:
                return "fail", f"tb_cic_arm +k={k_}: " + next((ln.strip() for ln in k.stdout.splitlines()
                                                              if "mismatches" in ln), "FAIL")[:120]
    if timed_out:
        return "timeout", "; ".join(timed_out)
    return "pass", ""



# the overload detector alone (tb_ovl + check_ovl.py against regmap.OVL_RULE: detector, hits, interval flags)
OVL_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("過負荷：間隔の印に検出の尾を含める（旧い規則）", "eeg_ovl.sv",
     "if (out_stb)      ovl_seen <= 1'b0;", "if (out_stb)      ovl_seen <= ovl_now;"),
    ("過負荷：両端の符号でなくても検出の間は印を付ける", "eeg_ovl.sv",
     "assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);", "assign ovl_hit = en && (cnt_nxt >= OVL_THRESHOLD);"),
    ("過負荷：この符号を数える前の値で判定（検出が 1 フレーム遅れる）", "eeg_ovl.sv",
     "assign ovl_hit = en && ext && (cnt_nxt >= OVL_THRESHOLD);", "assign ovl_hit = en && ext && (cnt >= OVL_THRESHOLD);"),
    # audit round 11, auditor A: the codes next to the rails counted as extremes (the edge bursts of build/ovl.codes)
    ("過負荷：両端の隣の符号（1、30）も両端と数える", "eeg_ovl.sv",
     "assign ext     = OVL_EXT_CODES[code];", "assign ext     = OVL_EXT_CODES[code] || (code == 5'd1) || (code == 5'd30);"),
]

TAG = dict(spi="s", seq="q", fifo="f", regs="r", chop1="c", rnd="n", struct="g", ovl="v")
GROUPS = ("top", "spi", "seq", "fifo", "regs", "chop1", "rnd", "struct", "ovl")


def edits_of(m):
    """A mutation's edits in order: [] for a baseline, one (file, text, replacement) or the listed ones."""
    _name, f, old, new = m
    if f is None:
        return []
    return list(f) if isinstance(f, list) else [(f, old, new)]


def run(i, m, bench="top"):
    name, f, old, new = m
    d = os.path.join(BUILD, "mut", "b00" if i < 0 else f"{TAG.get(bench, 'm')}{i:02d}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "build"))
    for s in SRC:
        shutil.copy(os.path.join(R14, s), d)
    for s in OLD:                                    # the blocks kept from r13 (rtl/), copied so they can be mutated
        shutil.copy(os.path.join(RTL_OLD, s), d)
    for f_, old_, new_ in edits_of(m):
        p = os.path.join(d, f_)
        text = open(p, encoding="utf-8").read()
        if text.count(old_) != 1:
            return i, name, "NOT APPLIED", f"the text occurs {text.count(old_)} times in {f_}"
        open(p, "w", encoding="utf-8").write(text.replace(old_, new_))
    for x in SHARED:                                 # the shared generated inputs, copied and checked (audit round 22)
        shutil.copy(os.path.join(BUILD, x), os.path.join(d, "build", x))
        if sha256_file(os.path.join(d, "build", x)) != SHARED_SHA.get(x):
            return i, name, "TOOL ERROR", f"the shared input build/{x} changed during the run (another run_tests_r14.sh?)"
    tb = {"spi": "tb_spi_r14.sv", "seq": "tb_seq.sv", "fifo": "tb_fifo.sv", "regs": "tb_regs.sv",
          "ovl": "tb_ovl.sv"}.get(bench, "tb_top_r14.sv")
    if bench == "struct":                            # the structure: yosys on this copy
        # a copy that does not compile is no verdict (audit round 28, auditor C: check_outputs_registered now calls
        # a design yosys refuses a FAIL, so a broken edit must not count as detected)
        c = subprocess.run(["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(d, "build"), "-o", "build/s.vvp"]
                           + SRC + OLD, cwd=d, capture_output=True, text=True)
        if c.returncode:
            return i, name, "COMPILE ERROR", (c.stderr.strip().splitlines() or ["?"])[-1][:150]
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_outputs_registered.py"), d], capture_output=True,
                           text=True)
        if k.returncode == 2 or k.returncode not in (0, 1) or not any(  # the tool did not run, or crashed: no verdict
                ln.startswith(("PASS:", "FAIL:")) for ln in k.stdout.splitlines()):   # (audit rounds 6, 9)
            return i, name, "TOOL ERROR", ((k.stdout + k.stderr).strip().splitlines() or ["no output"])[-1][:150]
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
    cmd = (["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", os.path.join(d, "build"), "-o",
            "build/t.vvp"] + srcs
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
        closing = {"seq": ("PASS: tb_seq", "FAIL: tb_seq"), "spi": ("tb_spi_r14: ", "FAIL: tb_spi_r14 watchdog"),
                   "fifo": ("PASS: tb_fifo", "FAIL: ")}[bench]
        if not bench_ended(v, closing):
            return i, name, "SIM ERROR", sim_tail(v, "tb_" + bench)
    if bench == "seq":
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_trace.py"),
                            os.path.join(d, "build", "seq_trace.txt")], capture_output=True, text=True)
        head = next((ln for ln in k.stdout.splitlines() if "mismatches" in ln), "")
        if not head:
            if "PASS: tb_seq" not in v.stdout:           # the bench judged it already (audit round 22, auditor C)
                return i, name, ("BASELINE FAILS" if f is None else "detected"), next(
                    (ln.strip() for ln in v.stdout.splitlines() if ln.startswith("ERROR")), "tb_seq FAIL")
            return i, name, "CHECKER ERROR", (k.stderr.strip().splitlines() or ["no output"])[-1]
        nbad = int(head.split(":")[1].split()[0])
        direct = "PASS: tb_seq" in v.stdout
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  line")), head)
        if nbad == 0 and not direct:                 # caught by the bench's direct checks: say which (audit round 11:
            first = next((ln.strip() for ln in v.stdout.splitlines() if ln.startswith("ERROR")), first)   # it showed the
                                                     # replay's clean line as the reason)
        # the exhaustive one-step bench (audit round 22, auditor A), as run_tests_r14.sh's tb_seq group runs it
        ce = subprocess.run(["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", os.path.join(d, "build"), "-o",
                             "build/te.vvp", "eeg_seq.sv", os.path.join(R14, "tb", "tb_seq_exh.sv")], cwd=d,
                            capture_output=True, text=True)
        if ce.returncode:
            return i, name, "COMPILE ERROR", "tb_seq_exh: " + ce.stderr.strip().splitlines()[-1][:140]
        try:
            ve = subprocess.run(["vvp", "-n", "build/te.vvp", "+trace=build/seq_exh.txt"], cwd=d, capture_output=True,
                                text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "tb_seq_exh: no end within 1200 s (undecided: rerun)"
        if not bench_ended(ve, ("tb_seq_exh: ",)):
            return i, name, "SIM ERROR", sim_tail(ve, "tb_seq_exh")
        ke = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_exh.py"),
                             os.path.join(d, "build", "seq_exh.txt")], capture_output=True, text=True)
        if not any(ln.startswith(("PASS:", "FAIL")) for ln in ke.stdout.splitlines()):
            if nbad != 0 or not direct:                # tb_seq judged it already
                return i, name, ("BASELINE FAILS" if f is None else "detected"), first
            return i, name, "CHECKER ERROR", "check_seq_exh: " + ((ke.stderr.strip().splitlines() or ["no output"])[-1])[:140]
        exh_ok = ke.returncode == 0
        if nbad == 0 and direct and not exh_ok:      # caught only by the exhaustive pass: say so
            first = "check_seq_exh: " + next((ln.strip() for ln in ke.stdout.splitlines() if ln.startswith("  ")),
                                               ke.stdout.strip().splitlines()[0])[:140]
        if f is None:
            return i, name, ("baseline ok" if nbad == 0 and direct and "PASS" in k.stdout and exh_ok
                             else "BASELINE FAILS"), head
        return i, name, ("detected" if nbad != 0 or not direct or not exh_ok else "MISSED"), first
    if bench == "ovl":
        try:
            v = subprocess.run(["vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 1200 s (undecided: rerun)"
        if not bench_ended(v, ("tb_ovl: ",)):
            return i, name, "SIM ERROR", sim_tail(v, "tb_ovl")
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_ovl.py"), os.path.join(d, "build")],
                           capture_output=True, text=True)
        passed = k.returncode == 0
        first = (k.stdout.strip().splitlines() or ["no output"])[0][:150]
        if not k.stdout.strip().endswith(("PASS", "FAIL")):     # audit round 9: a crash is no verdict
            return i, name, "CHECKER ERROR", (k.stderr.strip().splitlines() or ["no output"])[-1][:150]
        if f is None:
            return i, name, ("baseline ok" if passed else "BASELINE FAILS"), first
        return i, name, ("detected" if not passed else "MISSED"), first
    if bench in ("chop1", "rnd"):
        try:
            v = subprocess.run(["vvp", "-n", "build/t.vvp"] + (["+vec=build/rnd_sat.vec"] if bench == "rnd" else []),
                               cwd=d, capture_output=True, text=True, timeout=1200)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "no end within 1200 s (undecided: rerun)"
        if not bench_ended(v, ("PASS: chop1", "FAIL: ") if bench == "chop1" else ("PASS: tb_rnd_sat", "FAIL: tb_rnd_sat")):
            return i, name, "SIM ERROR", sim_tail(v, "tb_" + bench)
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
        if not bench_ended(v, ("PASS: tb_regs", "FAIL: tb_regs")):
            return i, name, "SIM ERROR", sim_tail(v, "tb_regs")
        head = next((ln for ln in v.stdout.splitlines() if ln.startswith("tb_regs:")), "no summary")
        first = next((ln for ln in v.stdout.splitlines() if ln.startswith("ERROR")), head)
        if f is None:
            return i, name, ("baseline ok" if "PASS: tb_regs" in v.stdout else "BASELINE FAILS"), head
        return i, name, ("detected" if "PASS: tb_regs" not in v.stdout else "MISSED"), first
    if bench == "fifo":
        # the 8-deep bench (run above) and the 4-deep one (-DDEPTH4), as run_tests_r14.sh's tb_fifo and tb_fifo4 (audit
        # round 22, auditor C: tb_fifo4 was never run on a mutant)
        c4 = subprocess.run(["iverilog", "-g2012", "-DDEPTH4", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I",
                             os.path.join(d, "build"), "-o", "build/t4.vvp"] + srcs + [tbp], cwd=d, capture_output=True,
                            text=True)
        if c4.returncode:
            return i, name, "COMPILE ERROR", "tb_fifo4: " + (c4.stderr.strip().splitlines() or ["?"])[-1][:140]
        try:
            v4 = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t4.vvp", "+n=400000",
                                 "+trace=build/fifo4_trace.txt"], cwd=d, capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", "tb_fifo4: no end within 3600 s (undecided: rerun)"
        if not bench_ended(v4, ("PASS: tb_fifo", "FAIL: ")):
            return i, name, "SIM ERROR", sim_tail(v4, "tb_fifo4")
        all_ok, first, head = True, "", ""
        for vv, tr in ((v, "fifo_trace.txt"), (v4, "fifo4_trace.txt")):
            bench_ok = "PASS: tb_fifo" in vv.stdout      # audit round 14, auditor C: the bench's own coverage line
            k = subprocess.run([sys.executable, os.path.join(HERE, "check_fifo_trace.py"), os.path.join(d, "build", tr)],
                               capture_output=True, text=True)
            hd = next((ln for ln in k.stdout.splitlines() if "mismatches" in ln), "")
            if not hd:
                if bench_ok:                             # neither the bench nor the checker judged it
                    return i, name, "CHECKER ERROR", (k.stderr.strip().splitlines() or ["no output"])[-1]
                all_ok = False                           # the bench judged FAIL (audit round 22, auditor C)
                first = first or next((ln.strip() for ln in vv.stdout.splitlines() if ln.startswith(("ERROR", "FAIL"))), tr)
                continue
            head = head or hd
            nbad = int(hd.split(":")[1].split()[0])
            ok_ = nbad == 0 and "PASS" in k.stdout and bench_ok
            if not ok_ and not first:
                first = (next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  line")), hd) if nbad else
                         next((ln.strip() for ln in vv.stdout.splitlines() if ln.startswith(("ERROR", "FAIL"))), hd))
            all_ok = all_ok and ok_
        if f is None:
            return i, name, ("baseline ok" if all_ok else "BASELINE FAILS"), head
        return i, name, ("detected" if not all_ok else "MISSED"), first
    if bench == "spi":
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_spi_trace.py"),
                            os.path.join(d, "build", "spi_trace.txt")], capture_output=True, text=True)
        head = k.stdout.splitlines()[0] if k.stdout else ("checker error: " + (k.stderr.strip().splitlines() or ["?"])[-1])
        nbad = int(head.split(":")[1].split()[0]) if "frames with mismatches" in head else -1
        if nbad < 0:                                 # the checker failed: a verdict only if the bench judged it
            if "FAIL" in v.stdout or "SPI ERROR" in v.stdout:   # (audit round 22, auditor C)
                return i, name, ("BASELINE FAILS" if f is None else "detected"), next(
                    (ln.strip() for ln in v.stdout.splitlines() if ln.startswith(("SPI ERROR", "ERROR", "FAIL"))), head)
            return i, name, "CHECKER ERROR", head
        timing = next((ln for ln in v.stdout.splitlines() if "SPI timing errors" in ln), "")
        nt = int(timing.split(",")[1].split()[0]) if timing else -1
        first = next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  frame")), head)
        if nbad == 0 and nt != 0:                    # caught by the BFM's timing checks: say so (audit round 9)
            first = next((ln.strip() for ln in v.stdout.splitlines() if ln.startswith("SPI ERROR")), timing)
        failed = "FAIL" in v.stdout                  # e.g. the bench's watchdog (the trace then ends early)
        if f is None:                                # the baseline also covers every branch, as in the runner
            covered = "every branch covered" in k.stdout
            # and, as run_tests_r14.sh needs, no ERROR line of the bench (a coverage shortfall) and the checker's exit 0
            # (every VER-02 pair; audit round 25, auditor C)
            errl = next((ln.strip() for ln in v.stdout.splitlines() if ln.startswith("ERROR")), "")
            clean = nbad == 0 and nt == 0 and not failed and covered and not errl and k.returncode == 0
            return i, name, ("baseline ok" if clean else "BASELINE FAILS"), (errl or head)
        return i, name, ("detected" if nbad != 0 or nt != 0 or failed else "MISSED"), first
    st_, txt_ = unit_benches(d, {e_[0] for e_ in edits_of(m)} if f is not None else {"eeg_clkgen.sv", "eeg_cic3.sv"})
    if st_ == "error":
        return i, name, "SIM ERROR", txt_
    if st_ == "fail":
        return i, name, ("BASELINE FAILS" if f is None else "detected"), txt_
    def top_once(vvp, tag):
        """One tb_top_r14 run and its two checkers: ("ok" | "fail", text), or a status without a verdict."""
        try:                                         # the bench's own watchdog (800 ms simulated) ends a hang
            v = subprocess.run(["nice", "-n", "10", "vvp", "-n", vvp], cwd=d, capture_output=True, text=True,
                               timeout=5400)
        except subprocess.TimeoutExpired:
            return "TIMEOUT", tag + "no end within 5400 s (undecided: rerun)"
        out = v.stdout
        if not bench_ended(v, ("PASS: tb_top_r14", "FAIL")):
            return "SIM ERROR", tag + sim_tail(v, "tb_top_r14")
        k = subprocess.run([sys.executable, os.path.join(HERE, "check_top_r14.py"), os.path.join(d, "build")],
                           capture_output=True, text=True)
        k2 = subprocess.run([sys.executable, os.path.join(HERE, "check_seq_trace.py"),
                             os.path.join(d, "build", "top_seq_trace.txt"), "--no-cover"], capture_output=True, text=True)
        tb_pass = "PASS: tb_top_r14" in out
        gold_pass, seq_pass = k.returncode == 0, k2.returncode == 0
        verdict = lambda kk: any(ln.startswith(("PASS:", "FAIL")) for ln in kk.stdout.splitlines())   # it ran to its end
        judged = (not tb_pass) or (verdict(k) and not gold_pass) or (verdict(k2) and not seq_pass)
        if not judged and not (verdict(k) and verdict(k2)):     # a checker crashed and nothing else judged (round 9)
            kk, nm = (k, "check_top_r14") if not verdict(k) else (k2, "check_seq_trace")
            return "CHECKER ERROR", tag + f"{nm}: " + ((kk.stderr.strip().splitlines() or ["no output"])[-1])[:140]
        if tb_pass and gold_pass and seq_pass:
            return "ok", tag + next((ln for ln in out.splitlines() if ln.startswith("tb_top_r14:")), "")[:150]
        first = next((ln for ln in out.splitlines() if ln.startswith(("ERROR", "SPI ERROR", "FAIL"))), "")
        if tb_pass and not gold_pass:
            first = "check_top_r14: " + next((ln for ln in k.stdout.splitlines() if "mismatch" in ln and ": 0 mismatches" not in ln),
                                             next((ln for ln in k.stdout.splitlines() if "mismatch" in ln), "FAIL"))
        elif tb_pass and not seq_pass:
            first = "check_seq_trace: " + next((ln.strip() for ln in k2.stdout.splitlines() if ln.startswith("  line")), "FAIL")
        return "fail", tag + first
    st8, t8 = top_once("build/t.vvp", "")
    if st_ == "timeout":                           # a unit bench without an end: tb_top_r14 decides (round 28, C)
        if st8 == "fail":
            return i, name, ("BASELINE FAILS" if f is None else "detected"), t8 + "; and " + txt_
        return i, name, "TIMEOUT", txt_ + " (undecided: tb_top_r14 " + ("passed" if st8 == "ok" else st8) + ")"
    if st8 not in ("ok", "fail"):
        return i, name, st8, t8
    if st8 == "fail":
        return i, name, ("BASELINE FAILS" if f is None else "detected"), t8
    # the 4-deep FIFO (-DFIFO4, run_tests_r14.sh's tb_top_r14_fifo4) for b00 and for the mutants whose edits name
    # DEPTH: the depth reaches eeg_fifo and, through FIFO_DEPTH, eeg_regs's CAPS (audit round 26, auditor C: "the
    # depth is eeg_fifo's alone" was false, and CAPS fixed at 8 was MISSED); and for every edit of eeg_fifo.sv (audit
    # round 27, auditor C: an edit that breaks only the 4-deep FIFO, e.g. lvl0 != 4'd8, would be reported MISSED)
    if f is not None and not any("DEPTH" in o_ + n_ or f_ == "eeg_fifo.sv" for f_, o_, n_ in edits_of(m)):
        return i, name, "MISSED", t8
    cmd4 = list(cmd)
    cmd4.insert(1, "-DFIFO4")
    cmd4[cmd4.index("build/t.vvp")] = "build/t4.vvp"
    c4 = subprocess.run(cmd4, cwd=d, capture_output=True, text=True)
    if c4.returncode:
        return i, name, "COMPILE ERROR", "4-deep: " + (c4.stderr.strip().splitlines() or ["?"])[-1][:140]
    st4, t4 = top_once("build/t4.vvp", "4-deep: ")
    if st4 not in ("ok", "fail"):
        return i, name, st4, t4
    if f is None:
        return i, name, ("baseline ok" if st4 == "ok" else "BASELINE FAILS"), (t8 if st4 == "ok" else t4)
    return i, name, ("detected" if st4 == "fail" else "MISSED"), t4


def main():
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 2
    # the shared generated inputs, made afresh as run_tests_r14.sh makes them (audit round 16, auditor C: only their
    # presence was checked, so a run after an edit of regmap.py or gen_reg_tests.py could use stale tests)
    py = sys.executable
    for cmd in ([py, "tb/gen_codes.py"], [py, "tb/gen_reg_tests.py"], [py, "tb/gen_ok_vectors.py"],
                [py, "-c", "import sys; sys.path.insert(0, '../rtl/model'); import gen_vectors as G; "
                             "G.gen_rnd_sat('build', sys.stdout)"]):
        r = subprocess.run(cmd, cwd=R14, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"generating the shared inputs failed ({' '.join(cmd[1:])[:60]}): "
                     + ((r.stdout + r.stderr).strip().splitlines() or ['no output'])[-1])
    for need in ("top_r14.codes", "reg_tests.svh", "pin_tests.svh", "ok_vectors.txt", "rnd_sat.vec", "ovl.codes",
                 "ovl.split", "plain_writes.txt"):
        if not os.path.exists(os.path.join(BUILD, need)):
            sys.exit(f"build/{need} missing after generating it")
    SHARED_SHA.update({x: sha256_file(os.path.join(BUILD, x)) for x in SHARED})
    # every listed mutation must apply to the RTL as it is now (audit round 5: two targets had changed with the RTL
    # and would have shown only as NOT APPLIED at the end of a long run)
    stale = []
    for g, lst in (("top", MUTATIONS), ("spi", SPI_MUTATIONS), ("seq", SEQ_MUTATIONS), ("fifo", FIFO_MUTATIONS),
                   ("regs", REGS_MUTATIONS), ("chop1", CHOP1_MUTATIONS), ("rnd", RND_MUTATIONS),
                   ("struct", STRUCT_MUTATIONS), ("ovl", OVL_MUTATIONS)):
        for i, m in enumerate(lst):
            texts = {}                                    # several edits: each applied before the next is looked for
            for f, old, new in edits_of(m):
                src = os.path.join(R14 if f in SRC else RTL_OLD, f)
                t = texts[src] if src in texts else open(src, encoding="utf-8").read()
                if t.count(old) != 1:
                    stale.append(f"{TAG.get(g, 'm')}{i:02d} {m[0]} ({f})")
                    break
                texts[src] = t.replace(old, new)
    for g, lst in (("top", MUTATIONS), ("spi", SPI_MUTATIONS), ("seq", SEQ_MUTATIONS), ("fifo", FIFO_MUTATIONS),
                   ("regs", REGS_MUTATIONS), ("chop1", CHOP1_MUTATIONS), ("rnd", RND_MUTATIONS),
                   ("struct", STRUCT_MUTATIONS), ("ovl", OVL_MUTATIONS)):
        seen = {}                                     # the same edits twice in one group (audit round 23, C)
        for i, m in enumerate(lst):
            key = tuple(edits_of(m))
            if key and key in seen:
                stale.append(f"{TAG.get(g, 'm')}{i:02d} {m[0]}: the same edits as {TAG.get(g, 'm')}{seen[key]:02d}")
            seen.setdefault(key, i)
    if stale:
        sys.exit("mutations whose text does not occur exactly once in the RTL, or repeated in a group (update them "
                 "first):\n  " + "\n  ".join(stale))
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
    if only:                                          # audit round 9: an unknown tag, or nothing to run, is an error
        tagof = lambda t: "b00" if t[0] < 0 else f"{TAG.get(t[2], 'm')}{t[0]:02d}"
        unknown = only - {tagof(t) for t in tasks}
        if unknown:
            sys.exit(f"FAIL: --only names tags not in the selected groups: {', '.join(sorted(unknown))}")
        tasks = [t for t in tasks if tagof(t) in only]
    if not tasks:
        sys.exit("FAIL: nothing to run")
    import datetime
    import threading
    t0 = datetime.datetime.now()
    log = os.path.join(BUILD, f"mutate_{t0:%Y%m%d-%H%M%S}-{os.getpid()}.log")   # every run keeps its record (audit
    # rounds 4, 5; round 8: two runs in one second no longer share a name, and the file is opened only if new)
    lock = threading.Lock()
    def tool(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=R14)
            if r.returncode != 0:                      # e.g. not a git checkout (a copy): say so plainly
                return "unknown"
            return ((r.stdout or r.stderr).strip().splitlines() or ["?"])[0]
        except OSError as ex:
            return f"not found ({ex})"
    yv = tool([YOSYS, '-V'])                            # e.g. "Yosys 0.69 (git sha1 9f75ca1f..., Release, Clang ...)"
    yv = yv.split(", Release")[0] + ")" if ", Release" in yv else yv
    ver, ver_check = run_version()
    env = f"{ver}; python {sys.version.split()[0]}; {tool(['iverilog', '-V'])}; {yv}"
    with open(log, "x", encoding="utf-8") as fo:           # written as the results arrive: an interrupted run
        fo.write(f"mutate_top_r14.py {' '.join(sys.argv[1:])}: started {t0:%Y-%m-%d %H:%M:%S}, "   # keeps what it did
                 f"{len(tasks)} runs (results in the order they end; the summary follows at the end)\n{env}\n")

    stamps0 = source_stamps()

    def run_logged(a):
        s1 = source_stamps()
        r = (a[2],) + run(*a)
        s2 = source_stamps()
        moved = sorted(p for p in set(stamps0) | set(s1) | set(s2) if not stamps0.get(p) == s1.get(p) == s2.get(p))
        if moved:                                    # (audit round 28, auditor C)
            r = r[:3] + ("TOOL ERROR", "the sources were touched during this mutant's run: " + ", ".join(moved[:4]))
        tag = "b00" if r[1] < 0 else f"{TAG.get(r[0], 'm')}{r[1]:02d}"
        with lock, open(log, "a", encoding="utf-8") as fo:
            fo.write(f"{datetime.datetime.now():%H:%M:%S} {r[3]:8s} {tag} {r[2]}" + (f"  ({r[4][:120]})" if r[4] else "") + "\n")
        return r
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(run_logged, tasks))
    ok = True
    out = [f"--- summary ({(datetime.datetime.now() - t0).total_seconds() / 60:.1f} min)"]
    missing_base = []
    title = {"top": "tb_top_r14 (the 4-deep FIFO too for b00, the edits naming DEPTH and the edits of eeg_fifo.sv)", "spi": "tb_spi_r14 + check_spi_trace", "seq": "tb_seq + check_seq_trace (timer modelled), tb_seq_exh + check_seq_exh",
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
    changed = [x for x in SHARED if sha256_file(os.path.join(BUILD, x)) != SHARED_SHA.get(x)]   # (audit round 22)
    if changed:
        out.append("the shared inputs changed during the run (another run_tests_r14.sh?): " + ", ".join(changed))
        ok = False
    if ver_check is not None:                        # still the version's files at the end (audit round 25, auditor C;
        end_diff = ver_check()                         # the checkout too since round 27)
        if end_diff:
            out.append("the sources differ from the run's version at the end of the run: " + ", ".join(end_diff[:8]))
            ok = False
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
