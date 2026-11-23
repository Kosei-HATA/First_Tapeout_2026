// Audit 36, auditor C: DFLAG standing across an accepted START (REG-02, FLG-02: only DFLAG's W1C clears it). RUN with
// the FIFO left unread until it overflows (DFLAG.OVERRUN), STOP, then START, DFLAG read after the START's tick.
`timescale 1ns / 1ps
`default_nettype none
module tb_c36_dflag;
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
    logic [7:0] e0, f0, e1, f1;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(2000.0);
        r14_write(7'h06, 8'hFF);                         // RESET_FLAG cleared
        r14_cmd(8'h11);                                  // START
        wait (dut.seq_state == 4'd6);
        #(10.0e6);                                       // 10 ms unread: the 8-deep FIFO overflows
        r14_cmd(8'h22);                                  // STOP
        wait (dut.seq_state == 4'd0); #(20000.0);
        r14_read(7'h06, e0); r14_read(7'h07, f0);
        r14_cmd(8'h11);                                  // START (accepted)
        wait (dut.seq_state == 4'd1); #(20000.0);
        r14_read(7'h06, e1); r14_read(7'h07, f1);
        $display("before START: ERR 0x%02h DFLAG 0x%02h; after the accepted START: ERR 0x%02h DFLAG 0x%02h -> %s",
                 e0, f0, e1, f1, (f1 === f0 && f0 !== 8'h00) ? "DFLAG kept (REG-02)" : "VIOLATION: DFLAG cleared by START");
        $finish;
    end
    initial begin #(60.0e6); $display("watchdog"); $finish; end
endmodule
`default_nettype wire
