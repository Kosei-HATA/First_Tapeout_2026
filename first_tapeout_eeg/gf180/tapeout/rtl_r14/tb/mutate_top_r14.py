#!/usr/bin/env python3
"""Mutation self-test of the r14 testbenches (11/19): each listed RTL error, put in on purpose into a copy of the r14
RTL, must be detected. MUTATIONS by tb_top_r14 / check_top_r14.py; SPI_MUTATIONS by tb_spi_r14 / check_spi_trace.py
(a mismatch with the specification on some frame; a shorter run than run_tests_r14.sh, +n=800, so branch coverage is
not asked for here), with an unmutated baseline that must show no mismatch. The unmutated RTL passes both benches
(run_tests_r14.sh), so a mutation that still passes shows a hole in a testbench.

Each mutation runs in build/mut/mNN/ (its own copy of the RTL and its own logs); the register tests
(build/reg_tests.svh) and the CODE stream (build/top_r14.codes) are shared, so run_tests_r14.sh (or gen_reg_tests.py
and the stream) must have run once.

Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/mutate_top_r14.py [-j N] [--top | --spi] [--only m03,s11]
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
     "if (bit_cnt != 3'd0 || st == S_OVF || st == S_WDAT || st == S_WCRC) begin",
     "if (st == S_OVF || st == S_WDAT || st == S_WCRC) begin"),
    ("SPI：途中で止めたサンプルの読み出しでも取り出す", "eeg_spi_slave.sv",
     "end else if (st == S_SDONE) begin", "end else if (st == S_SDONE || st == S_RSMP) begin"),
    ("SPI：読み出しの CRC に先頭バイトを含めない", "eeg_spi_slave.sv",
     "S_RCRC:  tx_next = crc8_step(crc8_step(8'h00, hdr), txd);", "S_RCRC:  tx_next = crc8_step(8'h00, txd);"),
    ("SPI：連続読み出しでアドレスを進めない", "eeg_spi_slave.sv",
     "else        reg_addr <= reg_addr + 7'd1;", "else        ;"),
    ("SPI：完了したフレームのあとのビットを無視する（過長な書き込みを確定）", "eeg_spi_slave.sv",
     "st <= S_OVF;                     // a bit after a completed frame", "st <= st;"),
    ("最上位：CHANGED を 2 個にしか付けない", "eeg_digital_top.sv",
     "if (seq_mark)                    chg_cnt <= 2'd3;", "if (seq_mark)                    chg_cnt <= 2'd2;"),
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
]


SPI_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("SPI：バイトの途中の CS_N を通知しない", "eeg_spi_slave.sv",
     "if (bit_cnt != 3'd0 || st == S_OVF || st == S_WDAT || st == S_WCRC) begin",
     "if (st == S_OVF || st == S_WDAT || st == S_WCRC) begin"),
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
    d = os.path.join(BUILD, "mut", f"{'s' if bench == 'spi' else 'm'}{i:02d}")
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
    tb = "tb_spi_r14.sv" if bench == "spi" else "tb_top_r14.sv"
    cmd = (["iverilog", "-g2012", "-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", BUILD, "-o", "build/t.vvp"] + SRC
           + [os.path.join(RTL_OLD, x) for x in OLD] + [os.path.join(R14, "tb", tb)])
    c = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    if c.returncode:
        return i, name, "COMPILE ERROR", c.stderr.strip().splitlines()[-1][:150]
    if bench == "spi":
        v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp", "+n=800", "+seed=7"], cwd=d,
                           capture_output=True, text=True, timeout=3600)
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
    v = subprocess.run(["nice", "-n", "10", "vvp", "-n", "build/t.vvp"], cwd=d, capture_output=True, text=True,
                       timeout=1800)
    out = v.stdout
    k = subprocess.run([sys.executable, os.path.join(HERE, "check_top_r14.py"), os.path.join(d, "build")],
                       capture_output=True, text=True)
    tb_pass = "PASS: tb_top_r14" in out
    gold_pass = k.returncode == 0
    first = next((ln for ln in out.splitlines() if ln.startswith(("ERROR", "SPI ERROR", "FAIL"))), "")
    if tb_pass and not gold_pass:
        first = "check_top_r14: " + next((ln for ln in k.stdout.splitlines() if "mismatch" in ln), "FAIL")
    return i, name, ("detected" if not (tb_pass and gold_pass) else "MISSED"), first


def main():
    jobs = int(sys.argv[sys.argv.index("-j") + 1]) if "-j" in sys.argv else 2
    for need in ("top_r14.codes", "reg_tests.svh"):
        if not os.path.exists(os.path.join(BUILD, need)):
            sys.exit(f"build/{need} missing: run run_tests_r14.sh first")
    which = "spi" if "--spi" in sys.argv else ("top" if "--top" in sys.argv else "both")
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None   # e.g. s00,s11
    tasks = []
    if which in ("top", "both"):
        tasks += [(i, m, "top") for i, m in enumerate(MUTATIONS)]
    if which in ("spi", "both"):
        tasks += [(i, m, "spi") for i, m in enumerate(SPI_MUTATIONS)]
    if only:
        tasks = [t for t in tasks if f"{'s' if t[2] == 'spi' else 'm'}{t[0]:02d}" in only]
    with cf.ThreadPoolExecutor(jobs) as ex:
        res = list(ex.map(lambda a: (a[2],) + run(*a), tasks))
    ok = True
    for bench in ("top", "spi"):
        rs = sorted(r for r in res if r[0] == bench)
        if not rs:
            continue
        print(f"--- {'tb_top_r14' if bench == 'top' else 'tb_spi_r14 + check_spi_trace'}")
        for _, i, name, verdict, first in rs:
            print(f"{verdict:8s} {'m' if bench == 'top' else 's'}{i:02d} {name}" + (f"  ({first[:120]})" if first else ""))
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
