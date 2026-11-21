// eeg_regs - registers of the digital control (r14).
//
// Specification: gf180/tapeout/rtl/spec/regmap.py (addresses, fields, reset values, legal ranges, classes; the
// constants come from the generated eeg_regs_defs.svh) and documentation/gf180_digital_control_spec_20261119.md.
//   * analog settings: a shadow (written over SPI) and an active copy (to the pins), copied on `apply` (the
//     sequencer's START / APPLY / APPLY_NR, at a tick). The active copy reads at address + 0x10.
//   * a write is committed by the SPI slave (we) only after the frame and CRC checks; here: an undefined or
//     read-only address, or a locked test register -> ADDR_ERR; a value outside the field's legal range ->
//     RANGE_ERR (nothing written); COMMAND while a command is pending -> STATE_ERR; an unknown code -> CMD_ERR
//     (pending or not); SOFT_RESET is always taken. While a command is pending, a write to a shadow (a register
//     with fields applied at the tick) or a timer (GUARDED_ADDRS) -> STATE_ERR, nothing written. TEST_KEY: 0x3C unlocks, 0x00 locks, any other value locks and
//     flags CMD_ERR (a one-bit error neither unlocks nor locks silently).
//   * ERR and DFLAG are W1C; a set event in the same cycle as its clear wins. RESET_FLAG resets to 1.
//   * cfg_ok: the shadow M fits the shadow range (range 0: the DAC is off, M is not looked at).
//     nr_ok: shadow and active differ only by one step of the signed offset-DAC value, in the same range.
`timescale 1ns / 1ps
`default_nettype none

module eeg_regs #(
    parameter int FIFO_DEPTH = 8
) (
    input  logic       clk,
    input  logic       rst_n,
    // SPI slave
    input  logic [6:0] addr,
    output logic [7:0] rdata,               // combinational, for addr
    output logic       addr_ok,             // addr is defined (header of a read)
    input  logic       we,                  // commit (after the frame and CRC checks)
    input  logic [7:0] wdata,
    input  logic       frame_err_set,
    input  logic       crc_err_set,
    input  logic       addr_err_set,        // a read frame's header address is undefined
    // status inputs
    input  logic [3:0] state,
    input  logic       afe_rst,
    input  logic       fifo_nonempty,
    input  logic [3:0] fifo_level,
    input  logic       ovl_now,
    input  logic       ovr_set,             // FIFO: a sample was dropped
    input  logic       ovl_set,             // overload while FILL or RUN
    input  logic       seq_state_err,
    input  logic       seq_cfg_err,
    // commands
    output logic       cmd_valid,
    output logic [7:0] cmd_code,
    input  logic       cmd_ack,             // the sequencer took the command at a tick
    output logic       soft_reset,          // pulse: SOFT_RESET committed
    // shadow -> active
    input  logic       apply,
    output logic       cfg_ok,
    output logic       nr_ok,
    // active analog settings
    // the offset DAC's pins are registers loaded at `apply` (no decode after the flip-flops: no glitch when the
    // range and M change together); range 0 drives M = 0, S = 0, OFEN = 0
    output logic [9:0] off_mag,
    output logic       off_sign,
    output logic [3:0] ofen,                // thermometer of the range (1..4 groups)
    output logic [1:0] afe_ibias,
    output logic [3:0] cpf_trim,
    output logic [1:0] btrim_p,
    output logic [1:0] btrim_n,
    output logic       chop_fast,
    output logic       dwa_en,
    output logic [2:0] chop1_rate,
    output logic [3:0] blank_len,           // 15 while the offset DAC is on (range >= 1)
    output logic       atp_en,
    output logic [3:0] atp_sel,
    output logic       chop_stop,
    output logic       adc_zero,
    // immediate
    output logic       raw_en,
    output logic [1:0] dbg_sel,
    output logic       crc_en,
    output logic       drdy_mode,
    output logic [7:0] t_warm,
    output logic [7:0] t_elec,
    output logic [7:0] t_rec,
    output logic [7:0] t_pre,
    output logic [7:0] t_rst,
    // to the SPI and the FIFO
    output logic [7:0] status_byte,
    output logic       alert,
    output logic       dflag_overrun
);

`include "eeg_regs_defs.svh"

    localparam logic [3:0] DEPTH4 = 4'(FIFO_DEPTH);

    // ---------------- storage
    // shadows (s_) and actives (a_) of the analog settings
    logic [9:0] s_m, a_m;
    logic       s_sign, a_sign;
    logic [2:0] s_range, a_range;
    logic [1:0] s_ibias, a_ibias;
    logic [3:0] s_cpf, a_cpf;
    logic [1:0] s_bp, a_bp, s_bn, a_bn;
    logic       s_fast, a_fast;
    logic       s_dwa, a_dwa;
    logic [2:0] s_c1, a_c1;
    logic [3:0] s_blank, a_blank;
    logic       s_atpen, a_atpen;
    logic [3:0] s_atpsel, a_atpsel;
    logic       s_cstop, a_cstop;
    logic       s_azero, a_azero;
    // immediate
    logic [7:0] r_mask, r_tw, r_te, r_trec, r_tpre, r_trst;
    logic [ALERT_MASK_D_ALERT_MASK_D_W-1:0] r_mask_d;
    logic [1:0] r_dbg;
    logic       r_raw, r_crc, r_drdy, unlocked;
    // flags
    logic [7:0] err;                         // ERR: 7 CMD 6 STATE 5 CFG 4 RANGE 3 ADDR 2 CRC 1 FRAME 0 RESET_FLAG
    logic [1:0] dflag;                       // DFLAG: 1 OVL 0 OVERRUN
    logic [9:0] o_ofm;                       // the offset DAC's pin registers
    logic       o_ofs;
    logic [3:0] o_ofen;
    logic       pend;
    logic [7:0] pcode;

    // ---------------- decode of a committed write
    logic       wr_def, wr_ro, wr_locked, wr_range_bad;
    logic       is_cmd_code, is_soft;
    logic [7:0] ev_err;                      // error events of this cycle (before the external ones)

    always_comb begin
        wr_def    = 1'b1;
        wr_ro     = 1'b0;
        wr_locked = 1'b0;
        wr_range_bad = 1'b0;
        case (addr)
            A_ID, A_VERSION, A_CAPS, A_STATUS, A_STATE, A_FIFO_LEVEL, A_ODR_H, A_ODR_L, A_FORMAT, A_SAMPLE,
            A_OFF_M_H_ACT, A_OFF_M_L_ACT, A_OFF_CTRL_ACT, A_AFE_IBIAS_ACT, A_CPF_TRIM_ACT, A_BOOST_TRIM_ACT,
            A_CHOP_CFG_ACT, A_ADC_CFG_ACT, A_BLANK_ACT, A_TEST_MUX_ACT, A_TEST_CTRL_ACT:
                wr_ro = 1'b1;
            A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,
            A_CPF_TRIM, A_BOOST_TRIM, A_CHOP_CFG, A_ADC_CFG, A_IF_CFG:
                ;
            A_OFF_CTRL:  wr_range_bad = (wdata[2:0] > OFF_CTRL_RANGE_MAX);
            A_BLANK:     wr_range_bad = (wdata[3:0] < BLANK_BLANK_LEN_MIN);
            A_T_WARM:    wr_range_bad = (wdata < T_WARM_T_WARM_MIN);
            A_T_ELEC:    ;
            A_T_REC:     wr_range_bad = (wdata < T_REC_T_REC_MIN);
            A_T_PRE:     wr_range_bad = (wdata < T_PRE_T_PRE_MIN);
            A_T_RST:     wr_range_bad = (wdata < T_RST_T_RST_MIN);
            A_TEST_MUX, A_TEST_CTRL, A_DEBUG: wr_locked = !unlocked;
            default:     wr_def = 1'b0;
        endcase
        if (addr == A_ADC_CFG) wr_range_bad = (wdata[2:0] > ADC_CFG_CHOP1_RATE_MAX);
    end

    assign is_soft     = (wdata == CMD_SOFT_RESET);
    assign is_cmd_code = (wdata == CMD_START) || (wdata == CMD_STOP) || (wdata == CMD_APPLY) ||
                         (wdata == CMD_APPLY_NR) || (wdata == CMD_FLUSH);

    logic w_ok;                              // the write is carried out
    always_comb begin
        ev_err = 8'h00;
        w_ok   = 1'b0;
        if (we) begin
            if (!wr_def || wr_ro || wr_locked) begin
                ev_err[ERR_ADDR_ERR_LSB] = 1'b1;
            end else if (pend && !cmd_ack && GUARDED_ADDRS[addr]) begin
                ev_err[ERR_STATE_ERR_LSB] = 1'b1;                // no write between a command and its tick
            end else if (wr_range_bad) begin
                ev_err[ERR_RANGE_ERR_LSB] = 1'b1;
            end else if (addr == A_COMMAND) begin
                if (is_soft) begin
                    ;                                            // handled by soft_reset (pending or not)
                end else if (!is_cmd_code) begin
                    ev_err[ERR_CMD_ERR_LSB] = 1'b1;              // unknown code, pending or not
                end else if (pend && !cmd_ack) begin
                    ev_err[ERR_STATE_ERR_LSB] = 1'b1;            // one command at a time
                end else begin
                    w_ok = 1'b1;
                end
            end else if (addr == A_TEST_KEY) begin
                w_ok = 1'b1;                                     // 0x3C unlocks, anything else locks
                if (wdata != TEST_KEY_VALUE && wdata != 8'h00) ev_err[ERR_CMD_ERR_LSB] = 1'b1;
            end else begin
                w_ok = 1'b1;
            end
        end
        ev_err[ERR_STATE_ERR_LSB] = ev_err[ERR_STATE_ERR_LSB] | seq_state_err;
        ev_err[ERR_CFG_ERR_LSB]   = seq_cfg_err;
        ev_err[ERR_FRAME_ERR_LSB] = frame_err_set;
        ev_err[ERR_CRC_ERR_LSB]   = crc_err_set;
        ev_err[ERR_ADDR_ERR_LSB]  = ev_err[ERR_ADDR_ERR_LSB] | addr_err_set;
    end

    assign soft_reset = we && wr_def && !wr_ro && (addr == A_COMMAND) && is_soft;

    // ---------------- registers
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_m <= {OFF_M_H_M_H_RST, OFF_M_L_M_L_RST};      a_m <= {OFF_M_H_M_H_RST, OFF_M_L_M_L_RST};
            s_sign <= OFF_CTRL_SIGN_RST;                    a_sign <= OFF_CTRL_SIGN_RST;
            s_range <= OFF_CTRL_RANGE_RST;                  a_range <= OFF_CTRL_RANGE_RST;
            s_ibias <= AFE_IBIAS_AFE_IBIAS_RST;             a_ibias <= AFE_IBIAS_AFE_IBIAS_RST;
            s_cpf <= CPF_TRIM_CPF_TRIM_RST;                 a_cpf <= CPF_TRIM_CPF_TRIM_RST;
            s_bp <= BOOST_TRIM_BTRIM_P_RST;                 a_bp <= BOOST_TRIM_BTRIM_P_RST;
            s_bn <= BOOST_TRIM_BTRIM_N_RST;                 a_bn <= BOOST_TRIM_BTRIM_N_RST;
            s_fast <= CHOP_CFG_CHOP_FAST_RST;               a_fast <= CHOP_CFG_CHOP_FAST_RST;
            s_dwa <= ADC_CFG_DWA_EN_RST;                    a_dwa <= ADC_CFG_DWA_EN_RST;
            s_c1 <= ADC_CFG_CHOP1_RATE_RST;                 a_c1 <= ADC_CFG_CHOP1_RATE_RST;
            s_blank <= BLANK_BLANK_LEN_RST;                 a_blank <= BLANK_BLANK_LEN_RST;
            s_atpen <= TEST_MUX_ATP_EN_RST;                 a_atpen <= TEST_MUX_ATP_EN_RST;
            s_atpsel <= TEST_MUX_ATP_SEL_RST;               a_atpsel <= TEST_MUX_ATP_SEL_RST;
            s_cstop <= TEST_CTRL_CHOP_STOP_RST;             a_cstop <= TEST_CTRL_CHOP_STOP_RST;
            s_azero <= TEST_CTRL_ADC_ZERO_RST;              a_azero <= TEST_CTRL_ADC_ZERO_RST;
            r_mask <= ALERT_MASK_ALERT_MASK_RST;            r_mask_d <= ALERT_MASK_D_ALERT_MASK_D_RST;
            r_tw <= T_WARM_T_WARM_RST;  r_te <= T_ELEC_T_ELEC_RST;  r_trec <= T_REC_T_REC_RST;
            r_tpre <= T_PRE_T_PRE_RST;  r_trst <= T_RST_T_RST_RST;
            r_raw <= DEBUG_RAW_EN_RST;  r_dbg <= DEBUG_DBG_SEL_RST;
            r_crc <= IF_CFG_CRC_EN_RST; r_drdy <= IF_CFG_DRDY_MODE_RST;
            unlocked <= 1'b0;
            o_ofm <= 10'd0;  o_ofs <= 1'b0;  o_ofen <= 4'd0;
            err <= 8'h01;                                   // RESET_FLAG = 1 after any reset
            dflag <= 2'b00;
            pend <= 1'b0;
            pcode <= 8'h00;
        end else begin
            if (w_ok) begin
                case (addr)
                    A_OFF_M_H:      s_m[9:8] <= wdata[1:0];
                    A_OFF_M_L:      s_m[7:0] <= wdata;
                    A_OFF_CTRL:     begin s_range <= wdata[2:0]; s_sign <= wdata[4]; end
                    A_AFE_IBIAS:    s_ibias <= wdata[1:0];
                    A_CPF_TRIM:     s_cpf <= wdata[3:0];
                    A_BOOST_TRIM:   begin s_bp <= wdata[1:0]; s_bn <= wdata[5:4]; end
                    A_CHOP_CFG:     s_fast <= wdata[0];
                    A_ADC_CFG:      begin s_c1 <= wdata[2:0]; s_dwa <= wdata[4]; end
                    A_BLANK:        s_blank <= wdata[3:0];
                    A_TEST_MUX:     begin s_atpsel <= wdata[3:0]; s_atpen <= wdata[4]; end
                    A_TEST_CTRL:    begin s_azero <= wdata[0]; s_cstop <= wdata[1]; end
                    A_DEBUG:        begin r_raw <= wdata[0]; r_dbg <= wdata[2:1]; end
                    A_ALERT_MASK:   r_mask <= wdata;
                    A_ALERT_MASK_D: r_mask_d <= wdata[ALERT_MASK_D_ALERT_MASK_D_LSB +: ALERT_MASK_D_ALERT_MASK_D_W];
                    A_T_WARM:       r_tw <= wdata;
                    A_T_ELEC:       r_te <= wdata;
                    A_T_REC:        r_trec <= wdata;
                    A_T_PRE:        r_tpre <= wdata;
                    A_T_RST:        r_trst <= wdata;
                    A_IF_CFG:       begin r_crc <= wdata[0]; r_drdy <= wdata[1]; end
                    A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);
                    default:        ;
                endcase
            end
            if (apply) begin
                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;
                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;
                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;
                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;
                o_ofm  <= (s_range == 3'd0) ? 10'd0 : s_m;
                o_ofs  <= (s_range == 3'd0) ? 1'b0  : s_sign;
                o_ofen <= ofen_of_range(s_range);   // regmap.ofen_of_range (generated)
            end
            // command: taken by the sequencer at a tick; a new one only when none is pending (else STATE_ERR)
            if (w_ok && addr == A_COMMAND) begin
                pend  <= 1'b1;
                pcode <= wdata;
            end else if (cmd_ack) begin
                pend  <= 1'b0;
            end
            // W1C flags: set events win
            err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;
            dflag <= (dflag & ~((we && w_ok && addr == A_DFLAG) ? {wdata[DFLAG_OVL_LSB], wdata[DFLAG_OVERRUN_LSB]}
                                                                : 2'b00)) | {ovl_set, ovr_set};
        end
    end

    // ---------------- outputs
    assign cmd_valid  = pend;
    assign cmd_code   = pcode;
    assign off_mag    = o_ofm;
    assign off_sign   = o_ofs;
    assign ofen       = o_ofen;
    assign afe_ibias  = a_ibias;
    assign cpf_trim   = a_cpf;
    assign btrim_p    = a_bp;
    assign btrim_n    = a_bn;
    assign chop_fast  = a_fast;
    assign dwa_en     = a_dwa;
    assign chop1_rate = a_c1;
    assign blank_len  = (a_range != 3'd0) ? BLANK_WITH_DAC : a_blank;
    assign atp_en     = a_atpen;
    assign atp_sel    = a_atpsel;
    assign chop_stop  = a_cstop;
    assign adc_zero   = a_azero;
    assign raw_en     = r_raw;
    assign dbg_sel    = r_dbg;
    assign crc_en     = r_crc;
    assign drdy_mode  = r_drdy;
    assign t_warm     = r_tw;
    assign t_elec     = r_te;
    assign t_rec      = r_trec;
    assign t_pre      = r_tpre;
    assign t_rst      = r_trst;
    assign dflag_overrun = dflag[0];

    // DFLAG and ALERT_MASK_D as bytes at the map's positions (generated *_LSB; audit round 11, auditor C: the positions
    // were written here by hand, so a field moved in regmap.py passed every test while the chip kept the old bit)
    logic [7:0] dflag_byte, mask_d_byte;
    always_comb begin
        dflag_byte = 8'h00;
        dflag_byte[DFLAG_OVL_LSB]     = dflag[1];
        dflag_byte[DFLAG_OVERRUN_LSB] = dflag[0];
        mask_d_byte = 8'h00;
        mask_d_byte[ALERT_MASK_D_ALERT_MASK_D_LSB +: ALERT_MASK_D_ALERT_MASK_D_W] = r_mask_d;
    end
    assign alert       = |(err & r_mask) || |(dflag_byte & mask_d_byte);
    // the bit positions from the generated constants (audit round 8: a hand-written order could differ from the map)
    always_comb begin
        status_byte                         = 8'h00;
        status_byte[STATUS_MARK1_LSB]       = STATUS_MARK1_RST;     // the fixed bits (MISO without a response)
        status_byte[STATUS_MARK0_LSB]       = STATUS_MARK0_RST;
        status_byte[STATUS_ALERT_LSB]       = alert;
        status_byte[STATUS_CMD_PENDING_LSB] = pend;
        status_byte[STATUS_READY_LSB]       = (state == ST_RUN);
        status_byte[STATUS_DATA_LSB]        = fifo_nonempty;
        status_byte[STATUS_OVL_NOW_LSB]     = ovl_now;
        status_byte[STATUS_AFE_RST_LSB]     = afe_rst;
    end

    // cfg_ok and nr_ok (gf180/tapeout/rtl/spec/regmap.py cfg_ok, nr_ok; range_max_m generated from RANGE_MAX_M)
    logic signed [11:0] sv_s, sv_a, dsv;
    assign sv_s   = s_sign ? -$signed({2'b00, s_m}) : $signed({2'b00, s_m});
    assign sv_a   = a_sign ? -$signed({2'b00, a_m}) : $signed({2'b00, a_m});
    assign dsv    = sv_s - sv_a;
    assign cfg_ok = (s_m <= range_max_m(s_range));
    assign nr_ok  = (s_range == a_range) && (dsv >= -12'sd1) && (dsv <= 12'sd1) &&
                    (s_ibias == a_ibias) && (s_cpf == a_cpf) && (s_bp == a_bp) && (s_bn == a_bn) &&
                    (s_fast == a_fast) && (s_dwa == a_dwa) && (s_c1 == a_c1) && (s_blank == a_blank) &&
                    (s_atpen == a_atpen) && (s_atpsel == a_atpsel) && (s_cstop == a_cstop) && (s_azero == a_azero);

    // ---------------- read
    always_comb begin
        addr_ok = 1'b1;
        rdata   = 8'h00;
        case (addr)
            A_ID:             rdata = ID_ID_RST;
            A_VERSION:        rdata = VERSION_VERSION_RST;
            A_CAPS:           rdata = {3'b000, 1'b1, DEPTH4};
            A_STATUS:         rdata = status_byte;
            A_STATE:          begin rdata = 8'h00; rdata[STATE_STATE_LSB +: STATE_STATE_W] = state; end
            A_FIFO_LEVEL:     begin rdata = 8'h00; rdata[FIFO_LEVEL_LEVEL_LSB +: FIFO_LEVEL_LEVEL_W] = fifo_level; end
            A_ERR:            rdata = err;
            A_DFLAG:          rdata = dflag_byte;
            A_ALERT_MASK:     rdata = r_mask;
            A_ALERT_MASK_D:   rdata = mask_d_byte;
            A_ODR_H:          rdata = ODR_H_ODR_H_RST;
            A_ODR_L:          rdata = ODR_L_ODR_L_RST;
            A_FORMAT:         rdata = {4'h0, FORMAT_QBITS_RST};
            A_COMMAND, A_TEST_KEY, A_SAMPLE: rdata = 8'h00;    // write only; the window is the SPI's
            A_OFF_M_H:        rdata = {6'd0, s_m[9:8]};
            A_OFF_M_L:        rdata = s_m[7:0];
            A_OFF_CTRL:       rdata = {3'd0, s_sign, 1'b0, s_range};
            A_AFE_IBIAS:      rdata = {6'd0, s_ibias};
            A_CPF_TRIM:       rdata = {4'd0, s_cpf};
            A_BOOST_TRIM:     rdata = {2'd0, s_bn, 2'd0, s_bp};
            A_CHOP_CFG:       rdata = {7'd0, s_fast};
            A_ADC_CFG:        rdata = {3'd0, s_dwa, 1'b0, s_c1};
            A_BLANK:          rdata = {4'd0, s_blank};
            A_OFF_M_H_ACT:    rdata = {6'd0, a_m[9:8]};
            A_OFF_M_L_ACT:    rdata = a_m[7:0];
            A_OFF_CTRL_ACT:   rdata = {3'd0, a_sign, 1'b0, a_range};
            A_AFE_IBIAS_ACT:  rdata = {6'd0, a_ibias};
            A_CPF_TRIM_ACT:   rdata = {4'd0, a_cpf};
            A_BOOST_TRIM_ACT: rdata = {2'd0, a_bn, 2'd0, a_bp};
            A_CHOP_CFG_ACT:   rdata = {7'd0, a_fast};
            A_ADC_CFG_ACT:    rdata = {3'd0, a_dwa, 1'b0, a_c1};
            A_BLANK_ACT:      rdata = {4'd0, a_blank};
            A_T_WARM:         rdata = r_tw;
            A_T_ELEC:         rdata = r_te;
            A_T_REC:          rdata = r_trec;
            A_T_PRE:          rdata = r_tpre;
            A_T_RST:          rdata = r_trst;
            A_IF_CFG:         rdata = {6'd0, r_drdy, r_crc};
            A_TEST_MUX:       rdata = {3'd0, s_atpen, s_atpsel};
            A_TEST_CTRL:      rdata = {6'd0, s_cstop, s_azero};
            A_DEBUG:          rdata = {5'd0, r_dbg, r_raw};
            A_TEST_MUX_ACT:   rdata = {3'd0, a_atpen, a_atpsel};
            A_TEST_CTRL_ACT:  rdata = {6'd0, a_cstop, a_azero};
            default:          addr_ok = 1'b0;
        endcase
    end

endmodule

`default_nettype wire
