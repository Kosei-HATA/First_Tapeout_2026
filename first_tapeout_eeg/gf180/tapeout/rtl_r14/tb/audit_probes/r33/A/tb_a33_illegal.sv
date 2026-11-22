// tb_a33_illegal - audit round 33 (A): the sequencer's illegal-state return (NFR-05) during a host's RUN wait.
// START, then one MCLK of an illegal state value (9) in WARMUP (or, +pulse, in PULSE after an APPLY in RUN); the
// host polls STATE, STATUS and ERR with CRC reads every 0.5 ms as step 5 does, up to 20 ms after the command.
`timescale 1ns / 1ps
`default_nettype none
module tb_a33_illegal;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd13 + 5'($urandom % 6);
    logic [7:0] v, st, stat, err;
    real t_cmd, t_inj;
    integer k, seen_run;
    initial begin
        #(10.0 * TMCLK); RESET_N = 1'b1; #(20.0 * TMCLK);
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_write(7'h55, 8'h01); bfm_crc_en = 1'b1;          // CRC on (step 3)
        r14_write(7'h51, 8'd0);                               // T_ELEC 0
        r14_read(7'h06, v); r14_write(7'h06, v);
        r14_cmd(CMD_START); t_cmd = $realtime;
        if ($test$plusargs("pulse")) begin
            wait (dut.seq_state == ST_RUN);
            #(200000.0);
            r14_cmd(CMD_APPLY); t_cmd = $realtime;
            wait (dut.seq_state == ST_PULSE);
        end else begin
            #(2.0e6);                                         // in WARMUP
        end
        @(posedge MCLK); #1; force dut.u_seq.state = 4'd9; t_inj = $realtime;
        @(posedge MCLK); #1; release dut.u_seq.state;
        $display("injected state 9 at %0.3f ms after the command (state now %0d, AFE_RST %b)",
                 (t_inj - t_cmd) / 1.0e6, dut.seq_state, AFE_RST);
        seen_run = 0;
        for (k = 0; k < 40; k++) begin
            #(500000.0);
            r14_read(7'h04, st); r14_read(7'h03, stat); r14_read(7'h06, err);
            if (st == ST_RUN) seen_run = 1;
            if (k % 4 == 3 || k < 2)
                $display("t = %6.3f ms after the command: STATE %0d, STATUS 0x%02h (ALERT %b READY %b AFE_RST %b), ERR 0x%02h (RESET_FLAG %b)",
                         ($realtime - t_cmd) / 1.0e6, st, stat, stat[5], stat[3], stat[0], err, err[0]);
        end
        $display("RUN reached within 20 ms: %0d; host RUN-wait bound T_WARM + T_REC + T_ELEC + 5 ms = %0.2f ms; SPI errors %0d",
                 seen_run, 5.0 + 0.25 + 0.0 + 5.0, spi_errors);
        $finish;
    end
endmodule
`default_nettype wire
