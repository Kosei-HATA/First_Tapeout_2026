// audit 37 A probe: the bounds of "the last AFE_RST release -> ALIGN's CIC clear" for an APPLY in RUN (T_ELEC 0,
// default timers T_PRE 3, T_RST 13, T_REC 32), both chopper rates. The APPLY is placed on chosen ticks of the
// 1024-frame output grid (frame index since the RESET_N release, mod 1024): the RECOVER -> ALIGN tick then lands
// 6 frames (128 kHz) or 12 frames (64 kHz) before an output frame (the shortest ALIGN) or 1022 / 1020 frames before
// it (the longest), and the neighbouring ticks. Requirements 5.4 step 7 / SEQ-03 quote "0.28 .. 1.23 ms" from a
// 16-position sweep (audit round 36, tb_a36_release.sv).
`timescale 1ns / 1ps
`default_nettype none
module tb_a37_relbound;
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
    integer mclk = 0, frame = -1, m_fall = 0, m_clear = 0, m_apply = 0, f_apply = 0;
    always @(posedge MCLK) begin
        #1;
        mclk = mclk + 1;
        if (dut.cycle == 5'd0 && RESET_N) frame = frame + 1;              // frame index since the release (frame 0 first)
        if (dut.cic_stb && dut.seq_state == ST_ALIGN) m_clear = mclk;     // e8 of the clear's output frame
    end
    always @(negedge AFE_RST) if (RESET_N) m_fall = mclk + 1;            // (the monitor above counts this edge next)
    always @(posedge MCLK) if (dut.apply && dut.seq_state == ST_RUN) begin m_apply = mclk + 1; f_apply = frame; end
    task automatic wait_state(input logic [3:0] s);
        integer n; n = 0;
        while (dut.seq_state !== s && n < 8000000) begin @(posedge MCLK); n = n + 1; end
        if (n >= 8000000) begin $display("TIMEOUT state %0d", s); $finish; end
    endtask
    task automatic cmd_at(input logic [7:0] c, input integer tick_frame);
        // commit the command between the tick before tick_frame and tick_frame (mod 1024): start the 2-byte write
        // 7 frames before it (a write takes about 5 us here)
        while (((frame - (tick_frame - 7)) % 1024 + 1024) % 1024 != 0 || dut.cycle != 5'd2) @(posedge MCLK);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    integer i, rate, a, d, d_min, d_max;
    integer targets128 [0:5];
    integer targets64 [0:5];
    initial begin
        // 128 kHz: ALIGN entry a + 384 frames (PRE 24, PULSE 104, RECOVER 256); shortest ALIGN at a + 384 = 1017 (mod
        // 1024) -> a = 633; longest at a + 384 = 1 -> a = 641; neighbours 625, 649 and two others
        targets128[0] = 633; targets128[1] = 641; targets128[2] = 625; targets128[3] = 649; targets128[4] = 1; targets128[5] = 513;
        // 64 kHz: PRE 32, PULSE 112, RECOVER 256 (tick to tick) -> ALIGN at a + 400; shortest at 1011 -> a = 611;
        // longest at 3 -> a = 627
        targets64[0] = 611; targets64[1] = 627; targets64[2] = 595; targets64[3] = 643; targets64[4] = 3; targets64[5] = 515;
        spi_high = 130.0; spi_low = 160.0;
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        for (rate = 1; rate >= 0; rate = rate - 1) begin
            r14_write(7'h26, 8'(rate));
            if (dut.seq_state == ST_IDLE) begin r14_cmd(8'h11); while (dut.cmd_valid === 1'b1) @(posedge MCLK); end
            else begin r14_cmd(8'h33); while (dut.cmd_valid === 1'b1) @(posedge MCLK); end
            wait_state(ST_RUN);
            d_min = 1 << 30; d_max = -1;
            for (i = 0; i < 6; i = i + 1) begin
                a = rate ? targets128[i] : targets64[i];
                cmd_at(8'h33, a);
                wait_state(ST_PRE);
                wait_state(ST_RUN);
                d = m_clear - m_fall;
                if (d < d_min) d_min = d;
                if (d > d_max) d_max = d;
                $display("%0d kHz: APPLY taken at frame %0d (mod 1024 %0d, target %0d): release -> clear %0d MCLK = %0.1f us",
                         rate ? 128 : 64, f_apply, f_apply % 1024, a, d, d * TMCLK / 1000.0);
            end
            $display("%0d kHz: release -> clear %0d .. %0d MCLK = %0.1f .. %0.1f us over these placements",
                     rate ? 128 : 64, d_min, d_max, d_min * TMCLK / 1000.0, d_max * TMCLK / 1000.0);
        end
        $finish;
    end
endmodule
`default_nettype wire
