// tb_c30_race - audit round 30 (C): a shadow write whose commit is swept in 1/4-MCLK steps across the tick that takes a
// pending APPLY, in RUN-less IDLE at 64 kHz (as round 29 B's tb_b29_guard), but with range 1 (M at most 127) and the
// racing value M_L = 200 (out of the range). Expected (fsm_spec: busy ends at the acknowledge; apply copies the shadow
// the decision judged): before the tick's cycle STATE_ERR and nothing written; at it or later written, and the APPLY
// applies the old shadow M = 5: OFM never shows 200. Counts the commits in the very cycle of the tick (cmd_ack) and
// checks OFM / the active copy after each.
`timescale 1ns / 1ps
`default_nettype none
module tb_c30_race;
`include "eeg_regs_defs.svh"
    localparam real TMCLK = 1000.0 / 32.768;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN;
    logic [4:0] CODE = 5'd16;
    wire  CMP_STROBE, DAC_CLK, CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, OFS, CHOP1;
    wire [7:0] TEST_CFG;
    wire [3:0] CPF_TRIM, OFEN;
    wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N;
    wire [9:0] OFM;
    eeg_digital_top #(.DAC_LOAD_CYCLE(2), .FIFO_DEPTH(8)) dut (.*);
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    `include "spi_bfm_r14.svh"
    realtime t_ack, t_c, t0, L;
    integer nserr, nok, nbad, nsame, nbefore, nafter, nofm, nlost;
    logic [7:0] e, sh, ac;
    always @(posedge MCLK) if (dut.cmd_ack) t_ack = $realtime;
    always @(posedge MCLK) if (dut.reg_we && dut.reg_addr == 7'h21) t_c = $realtime;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h26, 8'h00); r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd5);
        r14_cmd(8'h33); #(40000.0);                                   // 64 kHz, range 1, M 5 applied in IDLE
        $display("applied: range %0d M %0d OFM %0d OFEN %b, chop_fast %0d", dut.u_regs.a_range, dut.u_regs.a_m, OFM,
                 OFEN, dut.a_chop_fast);
        t0 = $realtime; r14_write(7'h21, 8'd5); L = t_c - t0;          // start -> commit edge of a 2-byte write
        nserr = 0; nok = 0; nbad = 0; nsame = 0; nbefore = 0; nafter = 0; nofm = 0; nlost = 0;
        for (int k = -12; k <= 12; k++) begin
            r14_write(7'h21, 8'd5); r14_write(7'h06, 8'hFF);
            @(posedge dut.u_clkgen.tick); t0 = $realtime;
            #(512.0 * TMCLK - L + 6.0 * TMCLK); r14_cmd(8'h33);         // APPLY pending ~6 MCLK after T0
            #(t0 + 1024.0 * TMCLK + k * TMCLK / 4.0 - L - $realtime);
            r14_write(7'h21, 8'd200);                                    // M_L 200: above range 1's 127
            repeat (700) @(posedge MCLK);
            if (OFM == 10'd200) nofm++;
            r14_read(7'h06, e); r14_read(7'h21, sh); r14_read(7'h31, ac);
            if (e[6]) nserr++; else nok++;
            if (t_c == t_ack) nsame++; else if (t_c < t_ack) nbefore++; else nafter++;
            if (!e[6] && sh != 8'd200) begin
                nlost++;
                $display("k %0d: commit %0.2f MCLK from the ack edge: no flag (ERR 0x%02h) but the shadow M_L reads %0d, not 200 (the write lost)",
                         k, (t_c - t_ack) / TMCLK, e, sh);
            end
            if (ac == 8'd200 || OFM == 10'd200) begin
                nbad++;
                $display("k %0d: commit %0.2f MCLK from the ack edge: active M_L %0d, OFM %0d in range %0d (M above the range applied; cfg_ok judged M 5)",
                         k, (t_c - t_ack) / TMCLK, ac, OFM, dut.u_regs.a_range);
            end
        end
        $display("sweep: commit before the tick's edge %0d, at it %0d, after %0d; STATE_ERR %0d, written %0d; racing value applied %0d (OFM 200: %0d); written without a flag but lost %0d",
                 nbefore, nsame, nafter, nserr, nok, nbad, nofm, nlost);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
