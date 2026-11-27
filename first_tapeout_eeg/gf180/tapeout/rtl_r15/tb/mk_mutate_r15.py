#!/usr/bin/env python3
"""Write gf180/tapeout/rtl_r15/tb/mutate_top_r15.py from rtl_r15/tb/mutate_top_r14.py (11/28): the r15 tree's own
version check (rtl_r15), the five mutants whose r14 text r15 rewrote given in r15's text (the same error), and the group
r15 (tb_r15 at depth 8 and 4, tb_regs, tb_fifo at depth 8 and 4) with the mutants of CFG_GEN, DROP_CNT and LATEST."""
R = "/Users/noah/Codings/First_Tapeout_2026/first_tapeout_eeg/gf180/tapeout/rtl_r15/tb"
t = open(f"{R}/mutate_top_r14.py", encoding="utf-8").read()


def rep(a, b, n=1):
    global t
    assert t.count(a) == n, (a[:80], t.count(a))
    t = t.replace(a, b)


rep('''"""Mutation self-test of the r14 testbenches (11/19, extended by the audits of 11/20): each listed RTL error, put in on
purpose into a copy of the r14 RTL (and of the blocks kept from rtl/), must be detected, and each bench's unmutated
baseline must pass. The groups and their benches:''',
    '''"""Mutation self-test of the r15 testbenches (11/28: mutate_top_r14.py of the r14 tree, 11/19 and the audits of 11/20, for
the r15 tree; written by mk_mutate_r15.py): each listed RTL error, put in on purpose into a copy of the r15 RTL (and of
the blocks kept from rtl/), must be detected, and each bench's unmutated baseline must pass. The r14 lists are kept as
they are; the five mutants whose text r15 rewrote are given in r15's text (R15_RETEXT, the same errors), and the group
r15 adds r15's CFG_GEN, DROP_CNT and LATEST. The groups and their benches:''')
rep('''  struct STRUCT_MUTATIONS   check_outputs_registered.py (yosys: every output a flip-flop's, NFR-06; the
                            synchronizers; the resets, RST-01; one clock, RST-05 since audit round 27)''',
    '''  struct STRUCT_MUTATIONS   check_outputs_registered.py (yosys: every output a flip-flop's, NFR-06; the
                            synchronizers; the resets, RST-01; one clock, RST-05 since audit round 27)
  r15    R15_MUTATIONS      tb_r15 at depth 8 and 4 (the r15 additions at the pins), tb_regs (CFG_GEN and DROP_CNT at
                            the cycle level since 11/28) and tb_fifo at depth 8 and 4 + check_fifo_trace.py (LATEST's
                            identity model): a mutant is detected when any of the five judges FAIL''')
rep('''Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r14/tb/mutate_top_r14.py [-j N]
       [--top | --spi | --seq | --fifo | --regs | --chop1 | --rnd | --struct | --ovl] [--only m03,s11,q02]''',
    '''Usage: gf180/tools/venv310/bin/python gf180/tapeout/rtl_r15/tb/mutate_top_r15.py [-j N]
       [--top | --spi | --seq | --fifo | --regs | --chop1 | --rnd | --struct | --ovl | --r15] [--only m03,s11,l02]
The complete run on a committed version: gf180/tapeout/rtl_r15/run_fullmut_r15.sh <version> (its own copy).''')
rep("""    t = git('ls-files', '--error-unmatch', 'tb/mutate_top_r14.py')""",
    """    t = git('ls-files', '--error-unmatch', 'tb/mutate_top_r15.py')""")
rep("""        ls = git('-C', repo, 'ls-tree', '-r', commit, '--', 'gf180/tapeout/rtl', 'gf180/tapeout/rtl_r14')""",
    """        ls = git('-C', repo, 'ls-tree', '-r', commit, '--', 'gf180/tapeout/rtl', 'gf180/tapeout/rtl_r15')""")
rep('''        return "version unknown (a copy without FULLRUN_VERSION: run run_fullmut_r14.sh, or run in the checkout)", None''',
    '''        return "version unknown (a copy without FULLRUN_VERSION: run run_fullmut_r15.sh, or run in the checkout)", None''')
rep('''        return (f"commit {commit[:8]} (run_fullmut_r14.sh's copy), BUT ITS FILES DIFFER FROM THAT VERSION: "''',
    '''        return (f"commit {commit[:8]} (run_fullmut_r15.sh's copy), BUT ITS FILES DIFFER FROM THAT VERSION: "''')
rep('''    return f"commit {commit[:8]} (run_fullmut_r14.sh's copy; its rtl and rtl_r14 files equal that version's)", differ''',
    '''    return f"commit {commit[:8]} (run_fullmut_r15.sh's copy; its rtl and rtl_r15 files equal that version's)", differ''')

# ---- the r15 group and the retexts, after the last list (OVL_MUTATIONS) and before TAG
rep('''TAG = dict(spi="s", seq="q", fifo="f", regs="r", chop1="c", rnd="n", struct="g", ovl="v")
GROUPS = ("top", "spi", "seq", "fifo", "regs", "chop1", "rnd", "struct", "ovl")''',
    '''# ---- r15 (11/28)
# The five r14 mutants whose text r15 rewrote, given in r15's text (the same error; the runner refuses a list whose text
# is not in the RTL exactly once, so without these the run would not start)
R15_RETEXT = {
    "SPI：サンプルの CRC に先頭バイトを含めない（全て 0 の応答が CRC の合う空の語になる）": [
        ("eeg_spi_slave.sv", "default: tx_next = crc8_48(lat ? CRC_LAT_HDR : CRC_SMP_HDR, shadow);",
         "default: tx_next = crc8_48(lat ? CRC_LAT_HDR : 8'h00, shadow);")],
    "レジスタ：COMMAND が最後の命令のコードを返す（書き込み専用は 0x00）": [
        ("eeg_regs.sv",
         "            A_COMMAND, A_TEST_KEY, A_SAMPLE, A_LATEST: rdata = 8'h00;   // write only; the windows are the SPI's",
         "            A_COMMAND:        rdata = pcode;\\n            A_TEST_KEY, A_SAMPLE, A_LATEST: rdata = 8'h00;")],
    "レジスタ：TEST_KEY が施錠の状態を返す": [
        ("eeg_regs.sv",
         "            A_COMMAND, A_TEST_KEY, A_SAMPLE, A_LATEST: rdata = 8'h00;   // write only; the windows are the SPI's",
         "            A_TEST_KEY:       rdata = {7'd0, unlocked};\\n            A_COMMAND, A_SAMPLE, A_LATEST: rdata = 8'h00;")],
    "最上位：DFLAG の立ての信号（OVL、OVERRUN）を 1 段のレジスタで受ける（1 MCLK 遅れる）": None,   # its first edit, below
    "SPI：サンプルの写しを先頭バイトの 1 MCLK あとに（先頭バイトの判定をレジスタで受ける）": None,   # its third edit, below
}


def _r15_retext():
    for lst in (MUTATIONS, SPI_MUTATIONS):
        for k, m in enumerate(lst):
            if m[0] not in R15_RETEXT:
                continue
            new = R15_RETEXT[m[0]]
            if new is None:                          # several edits: only the one r15 rewrote changes
                eds = edits_of(m)
                out = []
                for f_, o_, n_ in eds:
                    if o_ == "    logic        fifo_nonempty, ovr_set, push_ok, smp_snap, smp_pop;\\n":
                        o_ = "    logic        fifo_nonempty, ovr_set, push_ok, smp_snap, smp_pop, lat_snap;   // lat_snap: r15\\n"
                        n_ = o_ + "    logic        ovl_set_q, ovr_set_q;                    // DFLAG's set strobes, registered\\n"
                    elif o_ == "                                        shadow <= smp_word;\\n":
                        o_ = "                                        shadow <= (rx_byte[6:0] == A_LATEST) ? lat_word : smp_word;\\n"
                        n_ = "                                        if (rx_byte[6:0] == A_LATEST) shadow <= lat_word;\\n"
                    out.append((f_, o_, n_))
                if out == eds:
                    raise SystemExit(f"r15 retext: nothing of {m[0]} changed")
                lst[k] = (m[0], out, None, None)
            else:
                lst[k] = (m[0], new, None, None) if len(new) > 1 else (m[0], new[0][0], new[0][1], new[0][2])
            R15_RETEXT[m[0]] = "done"
    left = [n for n, v in R15_RETEXT.items() if v != "done"]
    if left:
        raise SystemExit("r15 retext: mutants not found: " + "; ".join(left))


# the r15 additions (CFG_GEN, DROP_CNT, LATEST, VERSION): group r15, its baseline first
R15_MUTATIONS = [
    ("（基準：変更なし）", None, None, None),
    ("CFG_GEN：適用で進まない", "eeg_regs.sv",
     "if (apply) cfg_gen <= cfg_gen + 8'd1;", "if (1'b0) cfg_gen <= cfg_gen + 8'd1;"),
    ("CFG_GEN：2 ずつ進む", "eeg_regs.sv",
     "if (apply) cfg_gen <= cfg_gen + 8'd1;", "if (apply) cfg_gen <= cfg_gen + 8'd2;"),
    ("CFG_GEN：255 で止まる（0 に戻らない）", "eeg_regs.sv",
     "if (apply) cfg_gen <= cfg_gen + 8'd1;", "if (apply && cfg_gen != 8'hFF) cfg_gen <= cfg_gen + 8'd1;"),
    ("CFG_GEN：リセットの値が 1", "eeg_regs.sv",
     "cfg_gen <= CFG_GEN_CFG_GEN_RST;", "cfg_gen <= 8'd1;"),
    ("DROP_CNT：255 で止まらない（0 に戻る）", "eeg_regs.sv",
     "drop_cnt <= (ovr_set && drop_base != 8'hFF) ? drop_base + 8'd1 : drop_base;",
     "drop_cnt <= ovr_set ? drop_base + 8'd1 : drop_base;"),
    ("DROP_CNT：254 で止まる", "eeg_regs.sv",
     "drop_cnt <= (ovr_set && drop_base != 8'hFF) ? drop_base + 8'd1 : drop_base;",
     "drop_cnt <= (ovr_set && drop_base < 8'hFE) ? drop_base + 8'd1 : drop_base;"),
    ("DROP_CNT：OVERRUN の消去で 0 に戻らない", "eeg_regs.sv",
     "assign drop_base = drop_clr ? 8'd0 : drop_cnt;", "assign drop_base = drop_cnt;"),
    ("DROP_CNT：OVERRUN を含まない DFLAG の書き込みでも 0 に戻る", "eeg_regs.sv",
     "assign drop_clr  = we && w_ok && (addr == A_DFLAG) && wdata[DFLAG_OVERRUN_LSB];",
     "assign drop_clr  = we && w_ok && (addr == A_DFLAG);"),
    ("DROP_CNT：消去が同じサイクルの取りこぼしに勝つ（0 のまま）", "eeg_regs.sv",
     "drop_cnt <= (ovr_set && drop_base != 8'hFF) ? drop_base + 8'd1 : drop_base;",
     "drop_cnt <= drop_clr ? 8'd0 : ((ovr_set && drop_base != 8'hFF) ? drop_base + 8'd1 : drop_base);"),
    ("DROP_CNT：リセットで 0 に戻らない（リセットの値が 1）", "eeg_regs.sv",
     "drop_cnt <= DROP_CNT_DROP_CNT_RST;", "drop_cnt <= 8'd1;"),
    ("読み出し：CFG_GEN の番地で DROP_CNT を返す", "eeg_regs.sv",
     "A_CFG_GEN:        rdata = cfg_gen;", "A_CFG_GEN:        rdata = drop_cnt;"),
    ("読み出し：DROP_CNT の番地で CFG_GEN を返す", "eeg_regs.sv",
     "A_DROP_CNT:       rdata = drop_cnt;", "A_DROP_CNT:       rdata = cfg_gen;"),
    ("読み出し：VERSION が r14 の 0x10", "eeg_regs.sv",
     "A_VERSION:        rdata = VERSION_VERSION_RST;", "A_VERSION:        rdata = 8'h10;"),
    ("LATEST：適用（lat_clr）で空にしない", "eeg_fifo.sv",
     "            if (lat_clr) begin", "            if (1'b0) begin"),
    ("LATEST：同じサイクルの出力が適用に勝つ", "eeg_fifo.sv",
     "            if (lat_clr) begin", "            if (lat_clr && !push) begin"),
    ("LATEST：FLUSH で空にしない", "eeg_fifo.sv",
     "            end else if (flush) begin\\n                lat_v <= 1'b0;",
     "            end else if (1'b0) begin\\n                lat_v <= 1'b0;"),
    ("LATEST：満杯で落とした出力を追わない（格納したものだけ）", "eeg_fifo.sv",
     "            end else if (push) begin", "            end else if (push_ok) begin"),
    ("LATEST：写しで held を消さない（短いサンプルの読み出しのあとの LATEST の読み出しが取り出す）", "eeg_fifo.sv",
     "            else if (lat_snap)   held <= 1'b0;", "            else if (1'b0)   held <= 1'b0;"),
    ("LATEST：空の語の状態バイトが 0（生きている旗を載せない）", "eeg_fifo.sv",
     "assign lat_word = lat_v ? lat : {empty_status, 16'h0000, 24'h000000};", "assign lat_word = lat_v ? lat : 48'h0;"),
    ("LATEST：状態バイトを VALID だけに", "eeg_fifo.sv",
     "lat   <= {status_in, seq_in, data_in};", "lat   <= {8'h80, seq_in, data_in};"),
    ("LATEST：SEQ を一つ前の値で保つ（一つ遅れる）", "eeg_fifo.sv",
     "lat   <= {status_in, seq_in, data_in};", "lat   <= {status_in, seq_in - 16'd1, data_in};"),
    ("SPI：LATEST の CRC を SMP_HDR から", "eeg_spi_slave.sv",
     "default: tx_next = crc8_48(lat ? CRC_LAT_HDR : CRC_SMP_HDR, shadow);",
     "default: tx_next = crc8_48(CRC_SMP_HDR, shadow);"),
    ("SPI：LATEST の窓を解かない（0x4F をレジスタとして読む）", "eeg_spi_slave.sv",
     "if (rx_byte[6:0] == A_SAMPLE || rx_byte[6:0] == A_LATEST) begin", "if (rx_byte[6:0] == A_SAMPLE) begin"),
    ("SPI：LATEST の読み出しで FIFO の先頭を写す", "eeg_spi_slave.sv",
     "shadow <= (rx_byte[6:0] == A_LATEST) ? lat_word : smp_word;", "shadow <= smp_word;"),
    ("SPI：lat_snap を出さない", "eeg_spi_slave.sv",
     "    assign lat_snap = !cs_start && !cs_end && sclk_rise && (st == S_HDR) && (bit_cnt == 3'd7) && rx_byte[7] &&\\n"
     "                      (rx_byte[6:0] == A_LATEST);",
     "    assign lat_snap = 1'b0;"),
    ("SPI：LATEST のあとのサンプルの読み出しも LATEST の CRC（lat が残る）", "eeg_spi_slave.sv",
     "lat    <= (rx_byte[6:0] == A_LATEST);", "lat    <= lat || (rx_byte[6:0] == A_LATEST);"),
    ("最上位：LATEST を適用で空にしない（lat_clr を 0 に）", "eeg_digital_top.sv",
     ".lat_snap(lat_snap), .lat_clr(apply), .lat_word(lat_word),",
     ".lat_snap(lat_snap), .lat_clr(1'b0), .lat_word(lat_word),"),
]

TAG = dict(spi="s", seq="q", fifo="f", regs="r", chop1="c", rnd="n", struct="g", ovl="v", r15="l")
GROUPS = ("top", "spi", "seq", "fifo", "regs", "chop1", "rnd", "struct", "ovl", "r15")''')


# ---- edits_of is defined after TAG: call the retext after it
rep('''def edits_of(m):
    """A mutation's edits in order: [] for a baseline, one (file, text, replacement) or the listed ones."""
    _name, f, old, new = m
    if f is None:
        return []
    return list(f) if isinstance(f, list) else [(f, old, new)]
''', '''def edits_of(m):
    """A mutation's edits in order: [] for a baseline, one (file, text, replacement) or the listed ones."""
    _name, f, old, new = m
    if f is None:
        return []
    return list(f) if isinstance(f, list) else [(f, old, new)]


_r15_retext()


def run_r15(i, name, f, d):
    """The group r15 on the copy d: tb_r15 (depth 8, then 4), tb_regs, tb_fifo (8 and 4) + check_fifo_trace. A compile
    error or a bench without its closing line is no verdict; any bench judging FAIL is a detection."""
    inc = ["-I", SPEC, "-I", os.path.join(R14, "tb"), "-I", os.path.join(d, "build")]
    runs = [("tb_r15", [], SRC + OLD + [os.path.join(R14, "tb", "tb_r15.sv")], [], ("PASS: tb_r15", "FAIL: tb_r15"), 1800),
            ("tb_r15_f4", ["-DFIFO4"], SRC + OLD + [os.path.join(R14, "tb", "tb_r15.sv")], [], ("PASS: tb_r15", "FAIL: tb_r15"), 1800),
            ("tb_regs", [], ["eeg_regs.sv", os.path.join(R14, "tb", "tb_regs.sv")], [], ("PASS: tb_regs", "FAIL: tb_regs"), 600),
            ("tb_fifo", [], ["eeg_fifo.sv", os.path.join(R14, "tb", "tb_fifo.sv")],
             ["+n=400000", "+trace=build/fifo_trace.txt"], ("PASS: tb_fifo", "FAIL: "), 3600),
            ("tb_fifo4", ["-DDEPTH4"], ["eeg_fifo.sv", os.path.join(R14, "tb", "tb_fifo.sv")],
             ["+n=400000", "+trace=build/fifo4_trace.txt"], ("PASS: tb_fifo", "FAIL: "), 3600)]
    fails, notes = [], []
    for nm, defs, srcs, args, closing, tmo in runs:
        c = subprocess.run(["iverilog", "-g2012"] + defs + inc + ["-o", f"build/{nm}.vvp"] + srcs, cwd=d,
                           capture_output=True, text=True)
        if c.returncode:
            return i, name, "COMPILE ERROR", f"{nm}: " + (c.stderr.strip().splitlines() or ["?"])[-1][:140]
        if port_width(c):
            fails.append(f"{nm}: a port connected at another width: " + port_width(c))
            continue
        try:
            v = subprocess.run(["nice", "-n", "10", "vvp", "-n", f"build/{nm}.vvp"] + args, cwd=d, capture_output=True,
                               text=True, timeout=tmo)
        except subprocess.TimeoutExpired:
            return i, name, "TIMEOUT", f"{nm}: no end within {tmo} s (undecided: rerun)"
        if not bench_ended(v, closing):
            return i, name, "SIM ERROR", sim_tail(v, nm)
        ok_ = closing[0] in v.stdout and "FAIL" not in v.stdout
        if nm.startswith("tb_fifo"):
            tr = os.path.join(d, "build", "fifo_trace.txt" if nm == "tb_fifo" else "fifo4_trace.txt")
            k = subprocess.run([sys.executable, os.path.join(HERE, "check_fifo_trace.py"), tr], capture_output=True,
                               text=True)
            hd = next((ln for ln in k.stdout.splitlines() if "mismatches" in ln), "")
            if not hd and ok_:
                return i, name, "CHECKER ERROR", f"{nm}: " + (k.stderr.strip().splitlines() or ["no output"])[-1][:140]
            if hd and (int(hd.split(":")[1].split()[0]) != 0 or k.returncode != 0):
                ok_ = False
                notes.append(f"{nm}: " + next((ln.strip() for ln in k.stdout.splitlines() if ln.startswith("  line")), hd))
        if not ok_:
            fails.append(next((f"{nm}: " + ln.strip() for ln in v.stdout.splitlines()
                               if ln.startswith(("ERROR", "FAIL"))), notes[-1] if notes else f"{nm}: FAIL")[:150])
    first = fails[0] if fails else "tb_r15 (8, 4), tb_regs, tb_fifo (8, 4) passed"
    if f is None:
        return i, name, ("baseline ok" if not fails else "BASELINE FAILS"), first
    return i, name, ("detected" if fails else "MISSED"), first
''')

# ---- run(): the r15 group after the shared inputs are copied
rep('''            return i, name, "TOOL ERROR", f"the shared input build/{x} changed during the run (another run_tests_r14.sh?)"
    tb = {''', '''            return i, name, "TOOL ERROR", f"the shared input build/{x} changed during the run (another run_tests_r14.sh?)"
    if bench == "r15":
        return run_r15(i, name, f, d)
    tb = {''')

# ---- main(): the r15 list in both checks, its tasks, its title, the log's name
rep('''    for g, lst in (("top", MUTATIONS), ("spi", SPI_MUTATIONS), ("seq", SEQ_MUTATIONS), ("fifo", FIFO_MUTATIONS),
                   ("regs", REGS_MUTATIONS), ("chop1", CHOP1_MUTATIONS), ("rnd", RND_MUTATIONS),
                   ("struct", STRUCT_MUTATIONS), ("ovl", OVL_MUTATIONS)):''',
    '''    for g, lst in (("top", MUTATIONS), ("spi", SPI_MUTATIONS), ("seq", SEQ_MUTATIONS), ("fifo", FIFO_MUTATIONS),
                   ("regs", REGS_MUTATIONS), ("chop1", CHOP1_MUTATIONS), ("rnd", RND_MUTATIONS),
                   ("struct", STRUCT_MUTATIONS), ("ovl", OVL_MUTATIONS), ("r15", R15_MUTATIONS)):''', n=2)
rep('''    if which in ("ovl", "all"):
        tasks += [(i, m, "ovl") for i, m in enumerate(OVL_MUTATIONS)]''',
    '''    if which in ("ovl", "all"):
        tasks += [(i, m, "ovl") for i, m in enumerate(OVL_MUTATIONS)]
    if which in ("r15", "all"):
        tasks += [(i, m, "r15") for i, m in enumerate(R15_MUTATIONS)]''')
rep('''             "ovl": "tb_ovl + check_ovl (regmap.OVL_RULE: detector, hits, interval flags)"}''',
    '''             "ovl": "tb_ovl + check_ovl (regmap.OVL_RULE: detector, hits, interval flags)",
             "r15": "tb_r15 (8 and 4), tb_regs, tb_fifo (8 and 4) + check_fifo_trace (r15: CFG_GEN, DROP_CNT, LATEST)"}''')
rep('''        fo.write(f"mutate_top_r14.py {' '.join(sys.argv[1:])}: started {t0:%Y-%m-%d %H:%M:%S}, "   # keeps what it did''',
    '''        fo.write(f"mutate_top_r15.py {' '.join(sys.argv[1:])}: started {t0:%Y-%m-%d %H:%M:%S}, "   # keeps what it did''')
open(f"{R}/mutate_top_r15.py", "w", encoding="utf-8").write(t)
print("wrote", f"{R}/mutate_top_r15.py", len(t.splitlines()), "lines")
