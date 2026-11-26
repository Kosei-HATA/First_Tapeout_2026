// audit 48 A probe 2: after an APPLY_NR (or APPLY) taken in WARMUP, T_REC and T_ELEC are read at the waits' starts
// (WARMUP's and RECOVER's expiry), as after a START: a write after the command's tick (no command pending, so the
// guard lets it through) sets RECOVER's length and WAIT_E. regmap.guarded_addrs' note names only a START's and an
// APPLY_NR's in RECOVER.
`timescale 1ns / 1ps
`default_nettype none
module tb_a48_warmnr;
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
    always @(posedge MCLK) if (dut.cycle == 5'd1) CODE <= 5'd12 + 5'($urandom % 8);
    real t_in [0:8];
    real t_len [0:8];
    logic [3:0] st_q = 4'd0;
    integer n_pre = 0, n_pulse = 0;
    always @(posedge MCLK) begin #0.2; if (dut.seq_state == ST_PRE && st_q != ST_PRE) n_pre++; if (dut.seq_state == ST_PULSE && st_q != ST_PULSE) n_pulse++; end
    always @(posedge MCLK) begin
        #0.1;
        if (dut.seq_state !== st_q) begin
            if (st_q <= 8) t_len[st_q] = $realtime - t_in[st_q];
            if (dut.seq_state <= 8) t_in[dut.seq_state] = $realtime;
        end
        st_q = dut.seq_state;
    end
    logic [7:0] e1, e2;
    initial begin
        repeat (5) @(negedge MCLK);
        RESET_N = 1'b1;
        #2000;
        r14_write(7'h06, 8'hFF);
        r14_cmd(8'h11);                                   // START (T_REC 32, T_ELEC 0)
        wait (dut.seq_state == ST_WARMUP);
        #1.0e6;
        r14_write(7'h21, 8'd1);                           // a one-step shadow change (range 0: any M)
        r14_cmd($test$plusargs("apply") ? 8'h33 : 8'h44); // APPLY_NR (or APPLY) in WARMUP: apply and restart T_WARM
        wait (dut.cmd_valid == 1'b0);
        #2000;
        r14_write(7'h52, 8'd100);                         // T_REC 100 (781.25 us), written after the tick
        r14_write(7'h51, 8'd2);                           // T_ELEC 2 ms, written after the tick
        r14_read(7'h06, e1);
        wait (dut.seq_state == ST_RUN);
        $display("%s in WARMUP: ERR after the writes 0x%02h; PRE entered %0d, PULSE entered %0d; WARMUP %0.3f ms (restarted at the APPLY_NR), RECOVER %0.2f us (T_REC 100 read at WARMUP's expiry, not 32 at the APPLY_NR's tick), WAIT_E %0.3f ms (T_ELEC 2 read at RECOVER's expiry)",
                 $test$plusargs("apply") ? "APPLY" : "APPLY_NR", e1, n_pre, n_pulse, t_len[ST_WARMUP] / 1e6, t_len[ST_RECOVER] / 1000.0, t_len[ST_WAIT_E] / 1e6);
        $finish;
    end
endmodule
`default_nettype wire
