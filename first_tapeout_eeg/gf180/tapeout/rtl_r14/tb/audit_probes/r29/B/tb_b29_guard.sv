// tb_b29_guard - audit round 29 (B): a write to a guarded shadow (OFF_M_L, 5 -> 7) whose commit is swept in 1/4-MCLK
// steps across the tick that takes a pending APPLY (IDLE, 64 kHz so that a write frame fits between two ticks, CRC
// off). Expected (SPI busy, fsm_spec): commit before the tick's cycle -> STATE_ERR, nothing written; in the tick's
// cycle or later -> written, and the APPLY applies the old shadow: the active copy never takes the racing value.
`timescale 1ns / 1ps
`default_nettype none
module tb_b29_guard;
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
    integer nserr, nok, nbad, nsame, nbefore, nafter;
    logic [7:0] e, sh, ac;
    always @(posedge MCLK) if (dut.cmd_ack) t_ack = $realtime;
    always @(posedge MCLK) if (dut.reg_we && dut.reg_addr == 7'h21) t_c = $realtime;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_write(7'h26, 8'h00); r14_cmd(8'h33); #(40000.0);          // 64 kHz applied in IDLE
        t0 = $realtime; r14_write(7'h21, 8'd5); L = t_c - t0;          // start -> commit edge of a 2-byte write
        $display("write start -> commit: %0.1f MCLK; chop_fast %0d", L / TMCLK, dut.a_chop_fast);
        nserr = 0; nok = 0; nbad = 0; nsame = 0; nbefore = 0; nafter = 0;
        for (int k = -24; k <= 24; k++) begin
            r14_write(7'h21, 8'd5); r14_write(7'h06, 8'hFF);
            @(posedge dut.u_clkgen.tick); t0 = $realtime;              // tick Tm; T0 = Tm + 512, T1 = Tm + 1024
            #(512.0 * TMCLK - L + 6.0 * TMCLK); r14_cmd(8'h33);         // APPLY commits ~6 MCLK after T0: pending
            #(t0 + 1024.0 * TMCLK + k * TMCLK / 4.0 - L - $realtime);
            r14_write(7'h21, 8'd7);                                      // commit ~ k/4 MCLK from T1
            repeat (700) @(posedge MCLK);
            r14_read(7'h06, e); r14_read(7'h21, sh); r14_read(7'h31, ac);
            if (e[6]) nserr++; else nok++;
            if (ac == 8'd7) begin nbad++; $display("k %0d: the active copy took the racing write", k); end
            if (t_c == t_ack) nsame++; else if (t_c < t_ack) nbefore++; else nafter++;
            if ((t_c < t_ack) != e[6] || (e[6] && sh != 8'd5) || (!e[6] && sh != 8'd7))
                $display("k %0d: commit %0.2f MCLK from the ack edge, ERR %02h, shadow %0d, copy %0d: UNEXPECTED", k,
                         (t_c - t_ack) / TMCLK, e, sh, ac);
        end
        $display("sweep: commit before the tick's edge %0d, at it %0d, after %0d; STATE_ERR %0d, written %0d; copy = racing value %0d",
                 nbefore, nsame, nafter, nserr, nok, nbad);
        $display("SPI errors %0d", spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
