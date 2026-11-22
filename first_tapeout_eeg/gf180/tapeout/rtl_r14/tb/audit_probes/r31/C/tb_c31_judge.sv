// tb_c31_judge - audit round 31 (C): the cfg_ok judgment of an APPLY taken in the acknowledge cycle of a racing
// shadow write (spec 7.4a: the tick applies the shadow before the write, as cfg_ok / nr_ok judged it). 64 kHz, range 1
// (M at most 127), M 5 applied in IDLE. Each round: shadow M_L <- A (the value the APPLY must be judged on), APPLY
// pending, then M_L <- B committed in 1/4-MCLK steps across the acknowledging tick.
//   S1: A = 200 (inconsistent), B = 5: the APPLY must be refused (CFG_ERR) in every case; OFM must never show 200.
//   S2: A = 5 (consistent), B = 200: the APPLY must be accepted (no CFG_ERR) in every case (phase Z1 of tb_top_r14,
//       whose target equals the active value, cannot tell an accepted APPLY from a refused one; it checks STATE_ERR only)
`timescale 1ns / 1ps
`default_nettype none
module tb_c31_judge;
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
    integer nb, ns, na, nbad;
    logic [7:0] e, sh, ac;
    logic [9:0] ofm_max;
    always @(posedge MCLK) if (dut.cmd_ack) t_ack = $realtime;
    always @(posedge MCLK) if (dut.reg_we && dut.reg_addr == 7'h21) t_c = $realtime;
    always @(posedge MCLK) if (OFM > ofm_max) ofm_max = OFM;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h26, 8'h00); r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd5);
        r14_cmd(8'h33); #(40000.0);                                   // 64 kHz, range 1, M 5 applied in IDLE
        t0 = $realtime; r14_write(7'h21, 8'd5); L = t_c - t0;          // start -> commit edge of a 2-byte write
        for (int sc = 1; sc <= 2; sc++) begin
            logic [7:0] va, vb;
            va = (sc == 1) ? 8'd200 : 8'd5;
            vb = (sc == 1) ? 8'd5 : 8'd200;
            nb = 0; ns = 0; na = 0; nbad = 0; ofm_max = 0;
            for (int k = -12; k <= 12; k++) begin
                r14_write(7'h21, va); r14_write(7'h06, 8'hFF);
                @(posedge dut.u_clkgen.tick); t0 = $realtime;
                #(512.0 * TMCLK - L + 6.0 * TMCLK); r14_cmd(8'h33);     // APPLY pending ~6 MCLK after T0
                #(t0 + 1024.0 * TMCLK + k * TMCLK / 4.0 - L - $realtime);
                r14_write(7'h21, vb);
                repeat (700) @(posedge MCLK);
                r14_read(7'h06, e); r14_read(7'h21, sh); r14_read(7'h31, ac);
                if (t_c == t_ack) ns++; else if (t_c < t_ack) nb++; else na++;
                if ((sc == 1 && (e[5] !== 1'b1 || ac !== 8'd5)) || (sc == 2 && e[5] !== 1'b0)) begin
                    nbad++;
                    $display("S%0d k %0d: commit %0.2f MCLK from the ack edge (%s): ERR 0x%02h, shadow M_L %0d, active M_L %0d, OFM %0d, range %0d",
                             sc, k, (t_c - t_ack) / TMCLK, (t_c == t_ack) ? "in the ack cycle" : (t_c < t_ack) ? "before" : "after",
                             e, sh, ac, OFM, dut.u_regs.a_range);
                end
                r14_write(7'h21, 8'd5); r14_cmd(8'h33); #(40000.0);    // back to M 5 applied
            end
            $display("S%0d (shadow %0d, racing write %0d): commits before the ack cycle %0d, in it %0d, after %0d; wrong outcomes %0d; largest OFM seen %0d",
                     sc, va, vb, nb, ns, na, nbad, ofm_max);
        end
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
