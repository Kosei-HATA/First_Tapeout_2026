R14 = "gf180/tapeout/rtl_r14"
OLD = "gf180/tapeout/rtl"
REGS = f"{R14}/eeg_regs.sv"
MUTANTS = {}

# X1: the shadows written through a next-state function, and `apply` copies that next state: a shadow write committed
# in the acknowledge cycle of START / APPLY / APPLY_NR (accepted: busy ends at cmd_ack) reaches the active copy and the
# pins at that tick, although cfg_ok / nr_ok judged the shadow before the write (e.g. M above the range's top applied)
_APPLY_OLD = """            if (apply) begin
                a_m <= s_m;         a_sign <= s_sign;     a_range <= s_range;   a_ibias <= s_ibias;
                a_cpf <= s_cpf;     a_bp <= s_bp;         a_bn <= s_bn;         a_fast <= s_fast;
                a_dwa <= s_dwa;     a_c1 <= s_c1;         a_blank <= s_blank;   a_atpen <= s_atpen;
                a_atpsel <= s_atpsel; a_cstop <= s_cstop; a_azero <= s_azero;
                o_ofm  <= (s_range == 3'd0) ? 10'd0 : s_m;
                o_ofs  <= (s_range == 3'd0) ? 1'b0  : s_sign;
                o_ofen <= ofen_of_range(s_range);   // regmap.ofen_of_range (generated)
            end"""
_APPLY_NEW = """            if (apply) begin
                a_m <= n_m;         a_sign <= n_sign;     a_range <= n_range;   a_ibias <= n_ibias;
                a_cpf <= n_cpf;     a_bp <= n_bp;         a_bn <= n_bn;         a_fast <= n_fast;
                a_dwa <= n_dwa;     a_c1 <= n_c1;         a_blank <= n_blank;   a_atpen <= n_atpen;
                a_atpsel <= n_atpsel; a_cstop <= n_cstop; a_azero <= n_azero;
                o_ofm  <= (n_range == 3'd0) ? 10'd0 : n_m;
                o_ofs  <= (n_range == 3'd0) ? 1'b0  : n_sign;
                o_ofen <= ofen_of_range(n_range);   // regmap.ofen_of_range (generated)
            end"""
_NEXT = """    // ---------------- registers
    // the shadows after this edge (a write of this cycle included)
    logic [9:0] n_m; logic n_sign; logic [2:0] n_range; logic [1:0] n_ibias; logic [3:0] n_cpf; logic [1:0] n_bp, n_bn;
    logic n_fast, n_dwa; logic [2:0] n_c1; logic [3:0] n_blank; logic n_atpen; logic [3:0] n_atpsel; logic n_cstop, n_azero;
    always_comb begin
        n_m = s_m; n_sign = s_sign; n_range = s_range; n_ibias = s_ibias; n_cpf = s_cpf; n_bp = s_bp; n_bn = s_bn;
        n_fast = s_fast; n_dwa = s_dwa; n_c1 = s_c1; n_blank = s_blank; n_atpen = s_atpen; n_atpsel = s_atpsel;
        n_cstop = s_cstop; n_azero = s_azero;
        if (w_ok) begin
            case (addr)
                A_OFF_M_H:    n_m[9:8] = wdata[1:0];
                A_OFF_M_L:    n_m[7:0] = wdata;
                A_OFF_CTRL:   begin n_range = wdata[2:0]; n_sign = wdata[4]; end
                A_AFE_IBIAS:  n_ibias = wdata[1:0];
                A_CPF_TRIM:   n_cpf = wdata[3:0];
                A_BOOST_TRIM: begin n_bp = wdata[1:0]; n_bn = wdata[5:4]; end
                A_CHOP_CFG:   n_fast = wdata[0];
                A_ADC_CFG:    begin n_c1 = wdata[2:0]; n_dwa = wdata[4]; end
                A_BLANK:      n_blank = wdata[3:0];
                A_TEST_MUX:   begin n_atpsel = wdata[3:0]; n_atpen = wdata[4]; end
                A_TEST_CTRL:  begin n_azero = wdata[0]; n_cstop = wdata[1]; end
                default:      ;
            endcase
        end
    end
"""
MUTANTS["x1_apply_next"] = [(REGS, _APPLY_OLD, _APPLY_NEW), (REGS, "    // ---------------- registers\n", _NEXT)]

# X14: the key's value written to any writable address unlocks the test registers (the unlock taken from the data
# alone, as round 28's data-only SOFT_RESET); writes to TEST_KEY still lock / unlock as before
MUTANTS["x14_key_by_data"] = [(REGS,
    "                    A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);\n                    default:        ;\n                endcase\n            end",
    "                    A_TEST_KEY:     unlocked <= (wdata == TEST_KEY_VALUE);\n                    default:        if (wdata == TEST_KEY_VALUE) unlocked <= 1'b1;\n                endcase\n            end")]
