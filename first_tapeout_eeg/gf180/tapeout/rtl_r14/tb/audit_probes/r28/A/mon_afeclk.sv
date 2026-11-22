// mon_afeclk - audit round 28, auditor A: a second top-level module compiled with tb_top_r14. It models the AFE clock
// driver's logic from gf180/tapeout/afe/eeg_afe_clk.spice (PH0 = CHOP or not CHOP_EN; COE = CHOP_OUT or not CHOP_EN;
// CDA = COE and not CHOP_BLANK; CDB = not COE and not CHOP_BLANK) on the macro's pins and checks, at every MCLK outside
// a reset, that the input-chopper reference PH0 changes only with a CHOP edge, the output-chopper reference COE only
// with a CHOP_OUT edge, and CDA / CDB only with a CHOP_OUT or CHOP_BLANK edge; it counts the CDA / CDB changes caused
// at a tick edge (ADC_ZERO applied or removed) and any PH0 / COE change at a tick edge (CHOP_EN changed in phase B).
// It also checks that AFE_RST changes outside a reset only right after a tick and with CHOP = 1 (phase A).
`timescale 1ns / 1ps
module mon_afeclk;
    wire mclk = tb_top_r14.MCLK;
    wire ph0 = tb_top_r14.CHOP | ~tb_top_r14.CHOP_EN;
    wire coe = tb_top_r14.CHOP_OUT | ~tb_top_r14.CHOP_EN;
    wire cda = coe & ~tb_top_r14.CHOP_BLANK;
    wire cdb = ~coe & ~tb_top_r14.CHOP_BLANK;
    logic p_ph0, p_coe, p_cda, p_cdb, p_chop, p_chop_out, p_blank, p_afe, p_en, p_tick, p_azero;
    logic inreset;
    integer n_ph0 = 0, n_coe = 0, n_cd = 0, n_en = 0, n_en_tick = 0, n_cd_tick = 0, n_afe = 0, n_bad = 0, n_cyc = 0;
    integer n_azero = 0;
    initial inreset = 1'b1;
    always @(negedge tb_top_r14.RESET_N or negedge tb_top_r14.dut.rst_n) inreset = 1'b1;
    always @(negedge mclk) begin
        if (tb_top_r14.RESET_N === 1'b1 && tb_top_r14.dut.rst_n === 1'b1 && !inreset) begin
            n_cyc++;
            if (ph0 !== p_ph0) begin
                n_ph0++;
                if (tb_top_r14.CHOP === p_chop) begin
                    n_bad++;
                    if (n_bad <= 20) $display("MON ERROR @%0t: PH0 %b->%b without a CHOP edge (CHOP_EN %b->%b, tick %b)",
                                              $time, p_ph0, ph0, p_en, tb_top_r14.CHOP_EN, p_tick);
                end
            end
            if (coe !== p_coe) begin
                n_coe++;
                if (tb_top_r14.CHOP_OUT === p_chop_out) begin
                    n_bad++;
                    if (n_bad <= 20) $display("MON ERROR @%0t: COE %b->%b without a CHOP_OUT edge", $time, p_coe, coe);
                end
            end
            if (cda !== p_cda || cdb !== p_cdb) begin
                n_cd++;
                if (tb_top_r14.CHOP_OUT === p_chop_out && tb_top_r14.CHOP_BLANK === p_blank) begin
                    n_bad++;
                    if (n_bad <= 20) $display("MON ERROR @%0t: CDA/CDB changed without a CHOP_OUT or CHOP_BLANK edge", $time);
                end
                if (p_tick) n_cd_tick++;
            end
            if (tb_top_r14.CHOP_EN !== p_en) begin
                n_en++;
                if (p_tick) n_en_tick++;
                if (ph0 !== p_ph0 || coe !== p_coe) begin
                    n_bad++;
                    if (n_bad <= 20) $display("MON ERROR @%0t: CHOP_EN change moved PH0/COE (CHOP %b)", $time, tb_top_r14.CHOP);
                end
            end
            if (tb_top_r14.dut.a_azero !== p_azero) n_azero++;
            if (tb_top_r14.AFE_RST !== p_afe) begin
                n_afe++;
                if (!p_tick || tb_top_r14.CHOP !== 1'b1) begin
                    n_bad++;
                    if (n_bad <= 20) $display("MON ERROR @%0t: AFE_RST %b->%b (tick before %b, CHOP %b)", $time, p_afe,
                                              tb_top_r14.AFE_RST, p_tick, tb_top_r14.CHOP);
                end
            end
        end else if (tb_top_r14.RESET_N === 1'b1 && tb_top_r14.dut.rst_n === 1'b1) begin
            inreset = 1'b0;                          // the first sample after a reset only takes the values
        end
        p_ph0 = ph0; p_coe = coe; p_cda = cda; p_cdb = cdb; p_chop = tb_top_r14.CHOP; p_chop_out = tb_top_r14.CHOP_OUT;
        p_blank = tb_top_r14.CHOP_BLANK; p_afe = tb_top_r14.AFE_RST; p_en = tb_top_r14.CHOP_EN;
        p_tick = tb_top_r14.dut.tick; p_azero = tb_top_r14.dut.a_azero;
    end
    final $display("MON: %0d cycles; PH0 changes %0d, COE %0d, CDA/CDB %0d (%0d at a tick edge), CHOP_EN changes %0d (%0d at a tick edge), ADC_ZERO changes %0d, AFE_RST changes %0d; violations %0d",
                   n_cyc, n_ph0, n_coe, n_cd, n_cd_tick, n_en, n_en_tick, n_azero, n_afe, n_bad);
endmodule
