// tb_c33_twarm - audit round 33, auditor C: T_WARM above 127 through the register block to the sequencer.
// T_WARM is written (128, 200, 255), START is issued, and the time from START's tick to AFE_RST's release is measured
// for 128 only up to 2 ms (it must not be released within 2 ms); the sequencer's timer right after the tick must be
// T_WARM x 1024 frames (eeg_seq.sv load_of).
`timescale 1ns / 1ps
`default_nettype none
module tb_c33_twarm;
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
    integer nbad = 0;
    initial begin
        int tw [3];
        tw = '{128, 200, 255};
        repeat (10) @(posedge MCLK);
        RESET_N = 1'b1;
        repeat (40) @(posedge MCLK);
        for (int i = 0; i < 3; i++) begin
            real t0;
            logic [7:0] rb;
            logic [17:0] tl;
            r14_write(7'h50, 8'(tw[i]));
            r14_read(7'h50, rb);
            r14_cmd(8'h11);                                          // START
            while (dut.seq_state !== 4'd1) @(posedge MCLK);
            t0 = $realtime;
            repeat (2) @(posedge MCLK);
            tl = dut.u_seq.timer;
            while (dut.seq_state === 4'd1 && $realtime - t0 < 2.0e6) @(posedge MCLK);   // 2 ms at most
            if (dut.seq_state === 4'd1)
                $display("T_WARM %0d (read back %0d): sequencer timer loaded %0d frames at START (expected %0d); still in WARMUP after 2 ms",
                         tw[i], rb, tl, tw[i] * 1024);
            else
                $display("T_WARM %0d (read back %0d): sequencer timer loaded %0d frames at START (expected %0d); WARMUP left after %0.1f us, AFE_RST %b",
                         tw[i], rb, tl, tw[i] * 1024, ($realtime - t0) / 1000.0, AFE_RST);
            if (dut.seq_state !== 4'd1 || tl != tw[i] * 1024) nbad++;
            r14_cmd(8'h22);                                          // STOP
            while (dut.seq_state !== 4'd0) @(posedge MCLK);
        end
        $display("tb_c33_twarm: %0d of 3 settings released early", nbad);
        $finish;
    end
endmodule
`default_nettype wire
