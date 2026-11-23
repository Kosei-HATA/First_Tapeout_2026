// Audit 36, auditor C: APPLY_NR in IDLE applies every shadow (table 5.1-2: IDLE / APPLY_NR [cfg_ok] -> apply; REG-08:
// unapplied test shadows are applied by the next START, APPLY or IDLE / WARMUP APPLY_NR). AFE_IBIAS 1 and CPF_TRIM 5
// written in IDLE, then APPLY_NR: the pins and the active copies.
`timescale 1ns / 1ps
`default_nettype none
module tb_c36_nr;
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
    logic [7:0] e, a23, a24;
    initial begin
        #(10 * TMCLK); RESET_N = 1'b1; #(2000.0);
        r14_write(7'h06, 8'hFF);
        r14_write(7'h23, 8'h01);                         // AFE_IBIAS 1 (reset 3)
        r14_write(7'h24, 8'h05);                         // CPF_TRIM 5
        r14_cmd(8'h44);                                  // APPLY_NR in IDLE (cfg_ok: range 0)
        #(30000.0);
        r14_read(7'h06, e); r14_read(7'h33, a23); r14_read(7'h34, a24);
        $display("ERR 0x%02h; AFE_IBIAS pin %0d active 0x%02h, CPF_TRIM pin %0d active 0x%02h -> %s", e, AFE_IBIAS, a23,
                 CPF_TRIM, a24, (AFE_IBIAS == 2'd1 && CPF_TRIM == 4'd5) ? "applied (table, REG-08)" : "NOT applied");
        $finish;
    end
endmodule
`default_nettype wire
