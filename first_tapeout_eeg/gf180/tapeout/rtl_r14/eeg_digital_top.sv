// eeg_digital_top - digital block of the GF180 EEG ADC, r14 (the new digital control).
//
// Same ports as rtl/eeg_digital_top.sv (the macro outline and pins stay; NFR-08). Specification:
// documentation/gf180_digital_control_requirements_20261119.md (r3) and gf180_digital_control_spec_20261119.md, with
// the machine-readable sources in gf180/tapeout/rtl/spec/.
//   * eeg_seq (new): the sequencer; ticks from eeg_clkgen (the middle of chopper phase A, frame cycle 24), output
//     times from the CIC (cycle 8). AFE_RST is its register; every analog setting changes at a tick (e25).
//   * eeg_regs (new map): shadow / active analog settings, W1C flags, the pending command, SOFT_RESET.
//   * eeg_spi_slave (new protocol): R/W + address header, STATUS first, fixed-length writes with optional CRC.
//   * eeg_cic3: no FILTER_CLEAR; cleared at an output time in ALIGN, the output grid fixed from reset release.
//   * eeg_fifo: START, APPLY with its pulse (the AFE running) and FLUSH empty it (and a reset); status byte {VALID,
//     OVERRUN, OVL, CHANGED, ERR, 0, 0, 0}; SEQ = the output's number since RESET_N release (every output time counts,
//     also during a SOFT_RESET).
//   * eeg_ovl (new): overload from the extreme quantizer codes.
//   * CHOP_DLY is gone (tied to 0 in eeg_clkgen); eeg_adc_dig, eeg_chop1, eeg_raw are unchanged (../rtl/).
// Resets: RESET_N (asynchronous assert, 2-FF release) resets everything. SOFT_RESET (the command; a registered reset
// for 5 MCLK) resets only the control side: registers, sequencer, SPI, FIFO, flags, CHANGED, DRDY_N. The timing and
// the data path keep running from RESET_N: frame counter and choppers (eeg_clkgen), CHOP1, the CIC, the overload
// detector, SEQ, the raw stream and eeg_adc_dig (ADC_RST_N), so chips sharing MCLK and RESET_N stay aligned (same SEQ
// = same time) through a SOFT_RESET of one of them.
`timescale 1ns / 1ps
`default_nettype none

module eeg_digital_top #(
    parameter int DAC_LOAD_CYCLE = 2,
    parameter int FIFO_DEPTH     = 8
) (
    input  logic        MCLK,
    input  logic        RESET_N,
    input  logic        SCLK,
    input  logic        CS_N,
    input  logic        MOSI,
    output logic        MISO,
    output logic        MISO_OE,
    output logic        DRDY_N,               // level: FIFO not empty; pulse mode: 128 MCLK (4 frames) per sample
    output logic        RAW_DATA,
    output logic        RAW_CLK,
    output logic        ADC_RST_N,
    output logic        TH_CAPTURE,
    output logic        DAC_LOAD,
    output logic        DWA_EN,
    input  logic [4:0]  CODE,
    output logic        CMP_STROBE,
    output logic        DAC_CLK,
    output logic        CHOP,
    output logic        CHOP_OUT,
    output logic        CHOP_BLANK,
    output logic        AFE_RST,
    output logic        CHOP_EN,
    output logic [7:0]  TEST_CFG,
    output logic [3:0]  CPF_TRIM,
    output logic [1:0]  AFE_IBIAS,
    output logic [1:0]  BTRIM_P,
    output logic [1:0]  BTRIM_N,
    output logic [9:0]  OFM,
    output logic        OFS,
    output logic [3:0]  OFEN,
    output logic        CHOP1
);

`include "eeg_regs_defs.svh"

    // ------------------------------------------------------------------ resets
    logic [1:0] rst_sync;
    logic       pin_rst_n, rst_n;
    wire        soft_req;                             // SOFT_RESET's commit cycle (eeg_regs; a net, so tests can force it)
    logic [2:0] soft_cnt;

    always_ff @(posedge MCLK or negedge RESET_N) begin
        if (!RESET_N) rst_sync <= 2'b00;
        else          rst_sync <= {rst_sync[0], 1'b1};
    end
    assign pin_rst_n = rst_sync[1];

    always_ff @(posedge MCLK or negedge pin_rst_n) begin
        if (!pin_rst_n) begin
            soft_cnt <= 3'd0;
            rst_n    <= 1'b0;
        end else begin
            if (soft_req)              soft_cnt <= 3'd4;
            else if (soft_cnt != 3'd0) soft_cnt <= soft_cnt - 3'd1;
            rst_n <= !(soft_req || (soft_cnt != 3'd0));
        end
    end
    logic tm_rst_n;                                   // timing and data path: RESET_N only
    assign tm_rst_n  = pin_rst_n;
    assign ADC_RST_N = tm_rst_n;

    // ------------------------------------------------------------------ frame timing
    logic [4:0] cycle;
    logic       th_capture, dac_load, cic_en, raw_clk, gen_blank, tick;
    logic       a_chop_fast;
    logic [3:0] a_blank_len;

    eeg_clkgen #(.DAC_LOAD_CYCLE(DAC_LOAD_CYCLE)) u_clkgen (
        .clk(MCLK), .rst_n(tm_rst_n), .chop_fast(a_chop_fast), .chop_dly(8'd0), .blank_len(a_blank_len),
        .cycle(cycle), .cmp_strobe(CMP_STROBE), .th_capture(th_capture), .dac_load(dac_load), .cic_en(cic_en),
        .chop(CHOP), .chop_out(CHOP_OUT), .chop_blank(gen_blank), .raw_clk(raw_clk), .tick(tick));

    assign TH_CAPTURE = th_capture;
    assign DAC_LOAD   = dac_load;

    logic frame_stb;
    assign frame_stb = (cycle == 5'd31);

    // ------------------------------------------------------------------ decimation and overload
    logic [23:0] cic_data;
    logic        cic_stb, cic_valid, cic_arm;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        cic_settling;                    // not used by r14 (the sequencer counts the outputs)
    /* verilator lint_on UNUSEDSIGNAL */

    // The CIC takes ALIGN's clear at the edge that starts the output-time cycle, from cic_arm in the cycle before
    // (its step 3). A SOFT_RESET committed in that cycle cancels the clear like every other event of its commit
    // cycle (the sequencer is reset from the next edge; fsm_spec RESET/OUT: no clear). One committed in the output-time
    // cycle itself comes after the clear (audit round 5, 11/20)
    eeg_cic3 u_cic (.clk(MCLK), .rst_n(tm_rst_n), .arm(cic_arm & ~soft_req), .en(cic_en), .code(CODE),
                    .dout(cic_data), .dout_stb(cic_stb), .dout_valid(cic_valid), .settling(cic_settling));

    logic ovl_now, ovl_hit, ovl_seen;
    eeg_ovl u_ovl (.clk(MCLK), .rst_n(tm_rst_n), .en(cic_en), .code(CODE), .out_stb(cic_stb), .ovl_now(ovl_now),
                   .ovl_hit(ovl_hit), .ovl_seen(ovl_seen));

    // a sample's OVL: an extreme code taken during a detected overload in any of the three output intervals of its
    // sinc^3 window (this one and the two before). The first 3 extreme codes of a detection are not hits; sparse, they
    // can span up to 31 frames and fall in the newest inputs of the previous window, whose weight there is at most
    // 1.3e-6 (under 0.1 LSB at 16 bits; audit round 7: was "3 frames, below 1e-8", true only for consecutive codes).
    // At the output time every input of the interval is in (its last at cycle 3), so ovl_seen holds it
    logic       ovl_iv;                               // this output interval
    logic [1:0] ovl_hist;                             // the two previous intervals
    assign ovl_iv = ovl_seen;                         // (ovl_hist's register follows the FIFO, below)

    // ------------------------------------------------------------------ registers and SPI
    logic [6:0]  reg_addr;
    logic [7:0]  reg_rdata, reg_wdata, status_byte, cmd_code;
    logic        reg_addr_ok, reg_we, frame_err, crc_err, addr_err, cmd_valid, cmd_ack;
    logic        apply, cfg_ok, nr_ok, crc_en, drdy_mode, alert, dflag_overrun;
    logic        a_dwa, a_atpen, a_cstop, a_azero, raw_en;
    logic [2:0]  a_c1;
    logic [3:0]  a_atpsel;
    logic [1:0]  dbg_sel;
    logic [7:0]  t_warm, t_elec, t_rec, t_pre, t_rst;
    logic [3:0]  seq_state, fifo_level;
    logic        seq_afe_rst, seq_flush, seq_store, seq_mark, seq_serr, seq_cerr;
    logic        fifo_nonempty, ovr_set, push_ok, smp_snap, smp_pop;
    logic [47:0] smp_word;

    eeg_spi_slave u_spi (
        .clk(MCLK), .rst_n(rst_n), .sclk(SCLK), .cs_n(CS_N), .mosi(MOSI), .miso(MISO), .miso_oe(MISO_OE),
        .status_byte(status_byte), .reg_addr(reg_addr), .reg_rdata(reg_rdata), .reg_addr_ok(reg_addr_ok),
        .reg_we(reg_we), .reg_wdata(reg_wdata), .crc_en(crc_en), .smp_word(smp_word), .smp_snap(smp_snap),
        .smp_pop(smp_pop),
        .frame_err(frame_err), .crc_err(crc_err), .addr_err(addr_err));

    eeg_regs #(.FIFO_DEPTH(FIFO_DEPTH)) u_regs (
        .clk(MCLK), .rst_n(rst_n), .addr(reg_addr), .rdata(reg_rdata), .addr_ok(reg_addr_ok), .we(reg_we),
        .wdata(reg_wdata), .frame_err_set(frame_err), .crc_err_set(crc_err), .addr_err_set(addr_err),
        .state(seq_state), .afe_rst(seq_afe_rst), .fifo_nonempty(fifo_nonempty), .fifo_level(fifo_level),
        .ovl_now(ovl_now), .ovr_set(ovr_set),
        .ovl_set(ovl_hit && ((seq_state == ST_FILL) || (seq_state == ST_RUN))),
        .seq_state_err(seq_serr), .seq_cfg_err(seq_cerr), .cmd_valid(cmd_valid), .cmd_code(cmd_code),
        .cmd_ack(cmd_ack), .soft_reset(soft_req), .apply(apply), .cfg_ok(cfg_ok), .nr_ok(nr_ok),
        .off_mag(OFM), .off_sign(OFS), .ofen(OFEN), .afe_ibias(AFE_IBIAS), .cpf_trim(CPF_TRIM),
        .btrim_p(BTRIM_P), .btrim_n(BTRIM_N), .chop_fast(a_chop_fast), .dwa_en(a_dwa), .chop1_rate(a_c1),
        .blank_len(a_blank_len), .atp_en(a_atpen), .atp_sel(a_atpsel), .chop_stop(a_cstop), .adc_zero(a_azero),
        .raw_en(raw_en), .dbg_sel(dbg_sel), .crc_en(crc_en), .drdy_mode(drdy_mode), .t_warm(t_warm),
        .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst), .status_byte(status_byte), .alert(alert),
        .dflag_overrun(dflag_overrun));

    // ------------------------------------------------------------------ sequencer
    // The commit cycle of SOFT_RESET (soft_req; rst_n falls at the next edge): the sequencer takes neither the tick
    // nor an output time in it (fsm_spec: RST wins over every event of its cycle; RESET/OUT only counts SEQ). Without
    // this, a tick in that cycle would give AFE_RST and the applied pins (OFM, OFS, OFEN, trims, TEST_CFG, CHOP_EN,
    // DWA_EN) their new value at the edge, and the asynchronous reset would take it back one reset-tree delay later:
    // a runt on the pads (NFR-06; audit round 4, 11/20)
    logic tick_s, out_s;
    assign tick_s = tick & ~soft_req;
    assign out_s  = cic_stb & ~soft_req;
    eeg_seq u_seq (
        .clk(MCLK), .rst_n(rst_n), .tick(tick_s), .frame_stb(frame_stb), .out_stb(out_s), .out_valid(cic_valid),
        .cmd_valid(cmd_valid), .cmd_code(cmd_code), .cmd_ack(cmd_ack), .cfg_ok(cfg_ok), .nr_ok(nr_ok),
        .t_warm(t_warm), .t_elec(t_elec), .t_rec(t_rec), .t_pre(t_pre), .t_rst(t_rst), .state(seq_state),
        .afe_rst(seq_afe_rst), .apply(apply), .flush(seq_flush), .cic_arm(cic_arm), .store(seq_store),
        .mark(seq_mark), .state_err(seq_serr), .cfg_err(seq_cerr));

    assign AFE_RST = seq_afe_rst;

    // ------------------------------------------------------------------ SEQ, CHANGED, FIFO, DRDY_N
    logic [15:0] seq_cnt;                        // output times since RESET_N release (wraps after 65.536 s)
    logic [8:0]  chg_cnt;                        // outputs still to mark CHANGED
    logic        chg_now;
    assign chg_now = (chg_cnt != 9'd0);
    logic [7:0]  smp_status, empty_status;       // built below from the generated bit positions (audit round 8)

    always_ff @(posedge MCLK or negedge tm_rst_n) begin
        if (!tm_rst_n)    seq_cnt <= 16'd0;
        else if (cic_stb) seq_cnt <= seq_cnt + 16'd1;
    end
    // APPLY_NR in RUN: the windows that straddle the step (3) and the electrode's settling (T_ELEC, 1 ms = 1 output).
    // A new mark keeps a longer remaining one (the earlier step's electrode is still settling; the mark is at a tick,
    // never in the cycle of an output). Leaving RUN cancels the rest (APPLY, STOP: the data starts again with a cleared
    // CIC after the waits, so no window of the next RUN straddles the step; samples are stored only in RUN)
    logic [8:0] chg_new;
    assign chg_new = 9'd3 + {1'b0, t_elec};
    always_ff @(posedge MCLK or negedge rst_n) begin
        if (!rst_n)                   chg_cnt <= 9'd0;
        else if (seq_mark)            chg_cnt <= (chg_cnt > chg_new) ? chg_cnt : chg_new;
        else if (seq_state != ST_RUN) chg_cnt <= 9'd0;
        else if (cic_stb && chg_now)  chg_cnt <= chg_cnt - 9'd1;
    end

    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (
        .clk(MCLK), .rst_n(rst_n), .flush(seq_flush), .push(seq_store),
        .status_in(smp_status),
        .seq_in(seq_cnt), .data_in(cic_data), .ovr_set(ovr_set), .push_ok(push_ok), .snap(smp_snap), .pop(smp_pop),
        .empty_status(empty_status), .rd_word(smp_word),
        .nonempty(fifo_nonempty), .level(fifo_level));

    // the sample's status byte and the empty word's, from the generated bit positions (audit round 8)
    always_comb begin
        smp_status                  = 8'h00;
        smp_status[SMP_VALID_LSB]   = 1'b1;
        smp_status[SMP_OVERRUN_LSB] = dflag_overrun;
        smp_status[SMP_OVL_LSB]     = ovl_iv | ovl_hist[0] | ovl_hist[1];
        smp_status[SMP_CHANGED_LSB] = chg_now;
        smp_status[SMP_ERR_LSB]     = alert;
        empty_status                  = 8'h00;  // VALID 0, CHANGED 0, SEQ and DATA 0 (spec 3.4)
        empty_status[SMP_OVERRUN_LSB] = dflag_overrun;
        empty_status[SMP_OVL_LSB]     = ovl_now;
        empty_status[SMP_ERR_LSB]     = alert;
    end

    // the OVL history advances at every output time (stored or not: the sinc^3 window counts output intervals)
    always_ff @(posedge MCLK or negedge tm_rst_n) begin
        if (!tm_rst_n)    ovl_hist <= 2'b00;
        else if (cic_stb) ovl_hist <= {ovl_hist[0], ovl_iv};
    end

    // DRDY_N: level mode = FIFO not empty (a register, as before); pulse mode = low for exactly 128 MCLK (4 frames)
    // from each stored sample, from its own register (no decode glitch on the pad). In the commit cycle of SOFT_RESET
    // it is set high (its reset value), so a store in the cycle before cannot make it fall for a reset-tree delay.
    // A sample is stored only at the CIC output cycle (frame cycle 8), so counting that cycle's edges counts whole
    // frames from the store.
    localparam logic [4:0] STORE_CYCLE = 5'd8;
    logic [2:0] drdy_cnt, drdy_nxt;
    logic       drdy_pulse;
    assign drdy_nxt = push_ok ? 3'd4 :
                      ((cycle == STORE_CYCLE && drdy_cnt != 3'd0) ? drdy_cnt - 3'd1 : drdy_cnt);
    logic       drdy_n_q;                        // the pad is driven by a register in both modes (NFR-06)
    always_ff @(posedge MCLK or negedge rst_n) begin
        if (!rst_n) begin
            drdy_cnt   <= 3'd0;
            drdy_pulse <= 1'b0;
            drdy_n_q   <= 1'b1;
        end else begin
            drdy_cnt   <= drdy_nxt;
            drdy_pulse <= (drdy_nxt != 3'd0);
            drdy_n_q   <= soft_req ? 1'b1 : (drdy_mode ? ~drdy_pulse : ~fifo_nonempty);   // high into a SOFT_RESET
        end
    end
    assign DRDY_N = drdy_n_q;

    // ------------------------------------------------------------------ analog controls and the rest
    assign DWA_EN     = a_dwa;
    assign CHOP_EN    = ~a_cstop;
    assign CHOP_BLANK = gen_blank | a_azero;
    assign TEST_CFG   = {dbg_sel, a_azero, a_atpen, a_atpsel};

    localparam logic [4:0] DAC_CLK_CYCLE = 5'(DAC_LOAD_CYCLE + 1);
    always_ff @(posedge MCLK or negedge tm_rst_n) begin
        if (!tm_rst_n) DAC_CLK <= 1'b0;
        else           DAC_CLK <= (cycle == DAC_CLK_CYCLE);
    end

    eeg_chop1 u_chop1 (.clk(MCLK), .rst_n(tm_rst_n), .cycle(cycle), .chop1_rate(a_c1), .chop1(CHOP1));

    eeg_raw u_raw (.clk(MCLK), .rst_n(tm_rst_n), .raw_en(raw_en), .cycle(cycle), .raw_clk(raw_clk), .code(CODE),
                   .dbg_sel(dbg_sel), .dbg_clk({CHOP_BLANK, CHOP, CMP_STROBE}), .dbg_data({CHOP1, CHOP_OUT, DAC_CLK}),
                   .raw_data_o(RAW_DATA), .raw_clk_o(RAW_CLK));

endmodule

`default_nettype wire
