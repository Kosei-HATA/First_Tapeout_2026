// audit 36 A probe: an APPLY in RUN (T_ELEC 0, default timers) at 16 positions of the output interval, both chopper
// rates: AFE_RST's fall (the last release) -> ALIGN's CIC clear (the output time ALIGN takes) -> the first store
// (FILL -> RUN). The first stored window is the 3 intervals after the clear, so it starts at the clear (+1 frame).
`timescale 1ns / 1ps
`default_nettype none
module tb_a36_release;
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
    real t_fall = 0, t_clear = 0, t_store = 0, t_tick = 0;
    always @(negedge AFE_RST) if (RESET_N) t_fall = $realtime;
    always @(posedge MCLK) begin
        if (dut.cic_stb && dut.seq_state == ST_ALIGN) t_clear = $realtime;
        if (dut.cic_stb && dut.seq_state == ST_FILL && dut.cic_valid) t_store = $realtime;
        if (dut.apply && dut.seq_state == ST_RUN) t_tick = $realtime;
    end
    task automatic wait_state(input logic [3:0] s);
        integer n; n = 0;
        while (dut.seq_state !== s && n < 8000000) begin @(posedge MCLK); n = n + 1; end
        if (n >= 8000000) begin $display("TIMEOUT state %0d", s); $finish; end
    endtask
    task automatic cmd(input logic [7:0] c);
        r14_cmd(c);
        while (dut.cmd_valid === 1'b1) @(posedge MCLK);
    endtask
    integer k, rate;
    real mn, mx, d;
    initial begin
        repeat (5) @(posedge MCLK); RESET_N = 1'b1; repeat (20) @(posedge MCLK);
        for (rate = 1; rate >= 0; rate = rate - 1) begin
            r14_write(7'h26, 8'(rate));                    // CHOP_CFG
            r14_write(7'h22, 8'h01); r14_write(7'h21, 8'd40);
            if (dut.seq_state == ST_IDLE) cmd(8'h11); else cmd(8'h33);
            wait_state(ST_RUN);
            mn = 1e9; mx = -1e9;
            for (k = 0; k < 16; k = k + 1) begin
                @(posedge MCLK); while (!dut.cic_stb) @(posedge MCLK);       // an output time in RUN
                #(k * 62500.0);                                               // k x 62.5 us into the interval
                r14_write(7'h21, 8'(41 + k));
                cmd(8'h33);                                                   // APPLY in RUN
                wait_state(ST_RUN);
                d = (t_clear - t_fall) / 1000.0;
                if (d < mn) mn = d;
                if (d > mx) mx = d;
                $display("%0d kHz k=%2d: tick->fall %7.2f us, fall->clear %7.2f us, clear->first store %7.2f us",
                         rate ? 128 : 64, k, (t_fall - t_tick) / 1000.0, d, (t_store - t_clear) / 1000.0);
            end
            $display("%0d kHz: the first stored window starts %.2f .. %.2f us after the last release (T_ELEC 0, T_REC %0d)",
                     rate ? 128 : 64, mn, mx, dut.t_rec);
        end
        $finish;
    end
endmodule
`default_nettype wire
