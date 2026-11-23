# audit37 C: RTL mutants (one designer error per copy). Paths relative to gf180/tapeout.
R = "rtl_r14/eeg_regs.sv"
T = "rtl_r14/eeg_digital_top.sv"
S = "rtl_r14/eeg_spi_slave.sv"
Q = "rtl_r14/eeg_seq.sv"
F = "rtl_r14/eeg_fifo.sv"
C = "rtl_r14/eeg_clkgen.sv"
APPLY_OLD = ("                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;\n"
             "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;\n"
             "                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;\n"
             "                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;\n")
MUTS = {
    # M1: an APPLY_NR leaves the chopper settings alone (CHOP_FAST, CHOP1_RATE, BLANK_LEN): "the chopper changes only
    # with START or APPLY". Equal to the clean RTL wherever nr_ok holds (they must be equal there); differs for an
    # APPLY_NR in IDLE / WARMUP, which table 5.1-2 makes a full apply.
    "m1_nr_chopper": [(R, APPLY_OLD,
        "                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;\n"
        "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;\n"
        "                a_dwa <= s_dwa;     a_atpen <= s_atpen;\n"
        "                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;\n"
        "                if (pcode != CMD_APPLY_NR) begin      // the chopper changes only with START / APPLY (PRE)\n"
        "                    a_fast <= s_fast; a_c1 <= s_c1; a_blank <= s_blank;\n"
        "                end\n")],
}
MUTS["m2_nr_testctrl"] = [(R, APPLY_OLD,
    "                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;\n"
    "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;\n"
    "                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;\n"
    "                a_atpsel <= s_atpsel;\n"
    "                if (pcode != CMD_APPLY_NR) begin      // the test modes (CHOP_STOP, ADC_ZERO): START / APPLY only\n"
    "                    a_cstop <= s_cstop; a_azero <= s_azero;\n"
    "                end\n")]
# M3: an accepted configuration (START / APPLY / APPLY_NR applied) clears the CFG_ERR of an earlier refusal
# ("CFG_ERR tells the shadow is inconsistent; a consistent apply ends that"). REG-02: only the W1C clears ERR.
MUTS["m3_apply_clears_cfgerr"] = [(R,
    "            err   <= (err & ~((we && w_ok && addr == A_ERR) ? wdata : 8'h00)) | ev_err;",
    "            err   <= (err & ~(((we && w_ok && addr == A_ERR) ? wdata : 8'h00) |\n"
    "                              (apply ? (8'h01 << ERR_CFG_ERR_LSB) : 8'h00))) | ev_err;   // a consistent apply ends CFG_ERR")]
# M5: the test settings (TEST_MUX, TEST_CTRL) are applied only while the AFE is held in reset (AFE_RST = 1: IDLE,
# WARMUP), an interlock read into 4.10's "いずれも AFE_RST ＝ 1 の間か、パルス付き": an APPLY in RUN (with its pulse)
# then leaves them, against table 5.1-2 (APPLY: apply) and host step 4's restore of a test setting by an APPLY in RUN.
MUTS["m5_test_only_in_reset"] = [(R, APPLY_OLD,
    "                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;\n"
    "                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;\n"
    "                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;\n"
    "                if (afe_rst) begin                     // the test settings only while the AFE is held in reset\n"
    "                    a_atpen <= s_atpen; a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;\n"
    "                end\n")]
