// Audit 36, auditor C: T_REC written in WARMUP and T_RST written in PRE (the guard is over once the command's tick has
// taken it). Spec 4.2 "値はタイマの開始時に取り込む", SPI-12 "START と APPLY の T_RST、T_REC ... はそれぞれの待ちの始まりに
// 読むので、ガードの終わったあとの書き込みは進行中の START や APPLY に効く". RECOVER (STATE) and the AFE_RST pulse (pin).
`timescale 1ns / 1ps
`default_nettype none
module tb_c36_trec;
    logic MCLK = 1'b0, RESET_N = 1'b0, SCLK = 1'b0, CS_N = 1'b1, MOSI = 1'b0;
    wire  MISO, MISO_OE, DRDY_N, RAW_DATA, RAW_CLK, ADC_RST_N, TH_CAPTURE, DAC_LOAD, DWA_EN, CMP_STROBE, DAC_CLK;
    wire  CHOP, CHOP_OUT, CHOP_BLANK, AFE_RST, CHOP_EN, CHOP1, OFS;
    wire [7:0] TEST_CFG; wire [3:0] CPF_TRIM, OFEN; wire [1:0] AFE_IBIAS, BTRIM_P, BTRIM_N; wire [9:0] OFM;
    logic [4:0] CODE = 5'd15;
    localparam real TMCLK = 1000.0 / 32.768;
    always #(TMCLK / 2.0) MCLK = ~MCLK;
    eeg_digital_top dut (.*);
    `include "eeg_regs_defs.svh"
    `include "spi_bfm_r14.svh"
    real t0, t1, trec, tpulse;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(2000.0);
        // A: START with T_REC 32 (250 us), then T_REC 200 (1562.5 us) written in WARMUP
        r14_cmd(8'h11);
        wait (dut.seq_state == 4'd1); #(20000.0);
        r14_write(7'h52, 8'd200);
        r14_read(7'h06, spi_rx[100]);
        wait (dut.seq_state == 4'd2); t0 = $realtime;
        wait (dut.seq_state != 4'd2); t1 = $realtime; trec = (t1 - t0) / 1000.0;
        $display("A: ERR after the WARMUP write 0x%02h; RECOVER %0.1f us (T_REC 200 written in WARMUP: 1562.5 expected; 250 = the value at START)",
                 spi_rx[100], trec);
        // B: in RUN, T_PRE 20 (156 us), APPLY with T_RST 13 (101.6 us), then T_RST 64 (500 us) written in PRE
        wait (dut.seq_state == 4'd6); #(5000.0);
        r14_write(7'h53, 8'd20);
        r14_cmd(8'h33);
        wait (dut.seq_state == 4'd7); #(5000.0);
        r14_write(7'h54, 8'd64);
        r14_read(7'h06, spi_rx[101]);
        @(posedge AFE_RST); t0 = $realtime;
        @(negedge AFE_RST); t1 = $realtime; tpulse = (t1 - t0) / 1000.0;
        $display("B: ERR after the PRE write 0x%02h; AFE_RST pulse %0.1f us at the pin (T_RST 64 written in PRE: 500.0 expected; 101.6 = the value at APPLY)",
                 spi_rx[101], tpulse);
        $display("%s", (trec > 1500.0 && tpulse > 490.0) ? "RESULT: timers taken at the start of their waits (spec 4.2, SPI-12)"
                                                           : "RESULT: VIOLATION of spec 4.2 / SPI-12 (timer taken before its wait)");
        $finish;
    end
    initial begin #(40.0e6); $display("watchdog"); $finish; end
endmodule
`default_nettype wire
